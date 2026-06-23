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
    """Label each token whose text names a geometric relation with that relation."""
    out: dict[int, str] = {}
    for i, tok in enumerate(rec["tokens"]):
        nt = _norm_token(tok)
        for kw, cls in _RELATION_KEYWORDS.items():
            if kw in nt:
                out[i] = cls
                break
    return out


LABELERS = {"relation": label_relation}


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
            "meta": meta[pid],
        })
    return records


def build_xy(records: list[dict], layer_pos: int, labeler):
    """Stack (activation, label) pairs at one layer across all records."""
    import numpy as np

    X, y = [], []
    for rec in records:
        labels = labeler(rec["meta"] if "tokens" not in rec else _rec_for_labeler(rec))
        acts = rec["acts"]               # [L, P, D]
        P = acts.shape[1]
        for pos, lab in labels.items():
            if 0 <= pos < P:
                X.append(acts[layer_pos, pos, :].astype("float32"))
                y.append(lab)
    if not X:
        return np.empty((0, 0)), np.array([])
    return np.stack(X), np.array(y)


def _rec_for_labeler(rec: dict) -> dict:
    # labelers expect a meta-like dict with "tokens"; capture stores tokens in meta too
    m = dict(rec["meta"])
    m.setdefault("tokens", rec["tokens"])
    return m


def run_probe(act_dir: pathlib.Path, labeler_name: str, test_frac: float, seed: int):
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split

    records = load_dataset(act_dir)
    if not records:
        raise SystemExit(f"no .npz records found in {act_dir}")
    labeler = LABELERS[labeler_name]
    n_layers = records[0]["acts"].shape[0]
    layer_ids = records[0]["layer_ids"]
    print(f"{len(records)} prompts, {n_layers} layers; labeler={labeler_name}")

    curve = []
    for li in range(n_layers):
        X, y = build_xy(records, li, labeler)
        classes, counts = np.unique(y, return_counts=True)
        if len(y) < 10 or len(classes) < 2:
            print(f"layer {layer_ids[li]:>3}: too few labeled samples "
                  f"({len(y)} pts, {len(classes)} classes) — skipping")
            continue
        Xtr, Xte, ytr, yte = train_test_split(
            X, y, test_size=test_frac, random_state=seed, stratify=y)
        clf = LogisticRegression(max_iter=2000, C=1.0)
        clf.fit(Xtr, ytr)
        acc = clf.score(Xte, yte)
        baseline = counts.max() / counts.sum()  # majority-class
        curve.append({"layer": int(layer_ids[li]), "acc": round(float(acc), 4),
                      "baseline": round(float(baseline), 4), "n": int(len(y))})
        bar = "#" * int(acc * 40)
        print(f"layer {layer_ids[li]:>3}: acc={acc:.3f} (base {baseline:.3f}) n={len(y):<5} {bar}")

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
