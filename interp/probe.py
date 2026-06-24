"""
Phase 2 — linear probes over captured activations (the core experiment).

Loads a capture run (interp/capture.py output: per-prompt .npz + meta.jsonl),
derives per-token labels via a pluggable labeler, and trains one linear probe per
layer to measure WHERE a geometric property becomes linearly decodable from the
residual stream. Prints a decodability-vs-layer curve and saves it as JSON.

No model / GPU needed — pure sklearn over saved float16 arrays.

    interp/.venv/bin/python interp/probe.py --act-dir interp/activations/tier1 \
        --labeler relation

Labelers (extend `LABELERS`):
  relation : multiclass over geometric-relation tokens (perp / parallel /
             midpoint / tangent / intersection / bisector) — "is the relation
             identity linearly decodable here, and at which layer?"
Richer targets (point coordinates via SymPy, the prompt's numeric angle,
intersection disambiguation) plug in as new labelers returning {pos: label}.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ----- labelers: meta-record -> {completion_token_index: class_label} -----

# token-substring -> relation class (BPE space markers stripped before matching)
_RELATION_KEYWORDS = {
    "perp": "perpendicular",
    "parallel": "parallel",
    "midpoint": "midpoint",
    "mid": "midpoint",
    "tangent": "tangent",
    "inter": "intersection",
    "bisect": "bisector",
}


def _norm_token(t: str) -> str:
    return t.replace("Ġ", "").replace("▁", "").replace("Ċ", "").lower()


def label_relation(rec: dict) -> dict[int, str]:
    """SANITY/BASELINE labeler — label each token whose text names a geometric
    relation with that relation.

    CAVEAT: this decodes the CURRENT token's identity, which late layers encode
    near-trivially (it is what the unembedding reads out). A rising curve here is
    a plumbing sanity check, NOT a spatial-representation result. The real targets
    decode properties that are NOT the current token — see METHODOLOGY.md.
    """
    out: dict[int, str] = {}
    for i, tok in enumerate(rec["tokens"]):
        nt = _norm_token(tok)
        for kw, cls in _RELATION_KEYWORDS.items():
            if kw in nt:
                out[i] = cls
                break
    return out


def _id_token_positions(rec: dict, entity_id: str) -> list[int]:
    """Token positions where ``entity_id`` is written as a quoted JSON value.

    Uses the saved char offsets to map every occurrence of "<id>" in the
    completion back to the covering token(s). Quoting avoids matching the id as a
    substring of another name (e.g. "A" inside "AB").
    """
    completion = rec.get("completion", "") or ""
    offsets = rec.get("offsets")
    if offsets is None or not completion:
        return []
    needle = f'"{entity_id}"'
    spans, start = [], 0
    while True:
        j = completion.find(needle, start)
        if j == -1:
            break
        spans.append((j + 1, j + 1 + len(entity_id)))  # the id chars, inside quotes
        start = j + 1
    out = []
    for pos, (s, e) in enumerate(offsets):
        if any(s < ce and e > cs for (cs, ce) in spans):   # token span ∩ id span
            out.append(pos)
    return out


def label_entity_relation(rec: dict) -> dict[int, str]:
    """NON-TRIVIAL — at each token that writes an entity's name, label it with the
    geometric RELATION that entity embodies (midpoint / perpendicular /
    intersection / tangent / ...), sourced from the ground-truth defs.

    The token string is just a name (e.g. "M"); whether M is a *midpoint* is not
    in the token — it comes from how M was constructed. So a rising decodability
    curve here is real evidence the model represents the relation, not token id.
    """
    gt = (rec.get("meta") or {}).get("ground_truth") or {}
    rels = gt.get("entity_relations") or {}
    out: dict[int, str] = {}
    for entity_id, relation in rels.items():
        for pos in _id_token_positions(rec, entity_id):
            out[pos] = relation
    return out


LABELERS = {"relation": label_relation, "entity_relation": label_entity_relation}


# ----- dataset loading -----

def load_dataset(act_dir: pathlib.Path) -> list[dict]:
    """Yield {acts:[L,P,D], layer_ids, tokens, pid} joined with meta.jsonl."""
    import numpy as np

    meta = {}
    with (act_dir / "meta.jsonl").open() as f:
        for line in f:
            r = json.loads(line)
            meta[r["pid"]] = r

    records = []
    for npz_path in sorted(act_dir.glob("*.npz")):
        pid = npz_path.stem
        if pid not in meta:
            continue
        d = np.load(npz_path)
        records.append({
            "pid": pid,
            "acts": d["acts"],                 # [L, P, D] float16
            "layer_ids": list(d["layer_ids"]),
            "tokens": meta[pid]["tokens"],
            "offsets": d["offsets"].tolist() if "offsets" in d else None,
            "completion": meta[pid].get("completion", ""),
            "meta": meta[pid],                 # carries ground_truth, grade, etc.
        })
    return records


def build_xy(records: list[dict], layer_pos: int, labeler):
    """Stack (activation, label, group) at one layer across all records.

    ``group`` is the prompt index, so the train/test split can keep all positions
    of a prompt on one side (no within-prompt leakage). Special-token positions
    (zero-width offset / flagged) are dropped — they carry no geometric content.
    """
    import numpy as np

    X, y, groups = [], [], []
    for gi, rec in enumerate(records):
        labels = labeler(rec)
        acts = rec["acts"]               # [L, P, D]
        P = acts.shape[1]
        special = rec["meta"].get("is_special", [0] * P)
        for pos, lab in labels.items():
            if 0 <= pos < P and not special[pos]:
                X.append(acts[layer_pos, pos, :].astype("float32"))
                y.append(lab)
                groups.append(gi)
    if not X:
        return np.empty((0, 0)), np.array([]), np.array([])
    return np.stack(X), np.array(y), np.array(groups)


def run_probe(act_dir: pathlib.Path, labeler_name: str, test_frac: float, seed: int):
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupShuffleSplit
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    records = load_dataset(act_dir)
    if not records:
        raise SystemExit(f"no .npz records found in {act_dir}")
    labeler = LABELERS[labeler_name]
    n_layers = records[0]["acts"].shape[0]
    layer_ids = records[0]["layer_ids"]
    print(f"{len(records)} prompts, {n_layers} layers; labeler={labeler_name}")

    # one PROMPT-LEVEL split, reused across layers so the curve is comparable
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_frac, random_state=seed)

    curve = []
    for li in range(n_layers):
        X, y, groups = build_xy(records, li, labeler)
        classes, counts = np.unique(y, return_counts=True)
        n_train_groups = len(set(groups)) if len(groups) else 0
        if len(y) < 10 or len(classes) < 2 or n_train_groups < 2:
            print(f"layer {layer_ids[li]:>3}: too few labeled samples "
                  f"({len(y)} pts, {len(classes)} classes, {n_train_groups} prompts) — skipping")
            continue
        tr, te = next(splitter.split(X, y, groups))   # prompts disjoint across tr/te
        # standardize per layer (residual-stream norm grows with depth)
        clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0))
        clf.fit(X[tr], y[tr])
        acc = clf.score(X[te], y[te])
        # baseline = majority class measured on the TEST fold
        _, te_counts = np.unique(y[te], return_counts=True)
        baseline = te_counts.max() / te_counts.sum()
        curve.append({"layer": int(layer_ids[li]), "acc": round(float(acc), 4),
                      "baseline": round(float(baseline), 4), "n": int(len(y)),
                      "n_test": int(len(te))})
        bar = "#" * int(acc * 40)
        print(f"layer {layer_ids[li]:>3}: acc={acc:.3f} (base {baseline:.3f}) "
              f"n={len(y):<5} {bar}")

    out = {"act_dir": str(act_dir), "labeler": labeler_name, "curve": curve}
    out_path = act_dir / f"probe_{labeler_name}.json"
    out_path.write_text(json.dumps(out, indent=2))
    if curve:
        best = max(curve, key=lambda c: c["acc"])
        print(f"\npeak decodability: layer {best['layer']} acc={best['acc']:.3f} "
              f"(baseline {best['baseline']:.3f}) -> {out_path.name}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--act-dir", required=True, help="capture output dir (has meta.jsonl + *.npz)")
    ap.add_argument("--labeler", default="relation", choices=list(LABELERS))
    ap.add_argument("--test-frac", type=float, default=0.3)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    run_probe(pathlib.Path(args.act_dir), args.labeler, args.test_frac, args.seed)


if __name__ == "__main__":
    main()
