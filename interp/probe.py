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
  relation    : multiclass over geometric-relation tokens (perp / parallel /
                midpoint / tangent / intersection / bisector) — "is the relation
                identity linearly decodable here, and at which layer?"
  correctness : METACOGNITION — binary ok/fail of the whole construction (from the
                render-free grade), read at one position per generation. "Does the
                residual stream encode whether the construction is RIGHT, and where
                does that self-assessment emerge relative to the geometry itself?"
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
    """Completion-token positions where ``entity_id`` is written (shared logic)."""
    from interp.geometry_labels import id_positions
    return id_positions(rec.get("completion", "") or "", rec.get("offsets"), entity_id)


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


def label_point_coord(rec: dict) -> dict[int, list]:
    """NON-TRIVIAL (regression) — at each token writing a point's name, the target
    is that point's position, normalized to [0,1] within the figure's bounding box.

    A point's coordinates are NOT in its name token, and normalizing per-figure
    removes the trivial "canvas scale" cue, so this asks: does the residual stream
    encode WHERE the point sits in the construction? Sourced from compiled SymPy.
    """
    gt = (rec.get("meta") or {}).get("ground_truth") or {}
    coords = gt.get("point_coords") or {}
    if len(coords) < 2:
        return {}
    xs = [c[0] for c in coords.values()]
    ys = [c[1] for c in coords.values()]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    wx, wy = (x1 - x0) or 1.0, (y1 - y0) or 1.0
    out: dict[int, list] = {}
    for pid, (x, y) in coords.items():
        norm = [(x - x0) / wx, (y - y0) / wy]
        for pos in _id_token_positions(rec, pid):
            out[pos] = norm
    return out


def label_angle(rec: dict) -> dict[int, list]:
    """NON-TRIVIAL (regression) — at each token writing a triangle vertex's name,
    target = that vertex's interior angle in degrees (from compiled geometry).
    A 1-number target (less data-hungry than 2-D coords); the vertex name doesn't
    encode its angle."""
    gt = (rec.get("meta") or {}).get("ground_truth") or {}
    angles = gt.get("vertex_angles") or {}
    out: dict[int, list] = {}
    for vid, deg in angles.items():
        for pos in _id_token_positions(rec, vid):
            out[pos] = [float(deg)]
    return out


def _grade_label(rec: dict) -> str | None:
    """'ok'/'fail' for the whole construction from the captured grade, or None."""
    grade = (rec.get("meta") or {}).get("grade") or {}
    return None if grade.get("ok") is None else ("ok" if grade["ok"] else "fail")


def _grade_read_pos(rec: dict, which: str = "last") -> int | None:
    """The single completion-token position to read a per-generation label at: the
    first/last STORED position (an entity token under --keep-positions entities), or
    the first/last non-special token if all positions were stored. Confidence-slot
    positions are excluded so this stays the last/first ENTITY even on an
    --elicit-confidence capture (the conf digits, appended last, would otherwise win
    max()). Always exists for a saved record, so no grade class is ever dropped."""
    meta = rec.get("meta") or {}
    conf = set(meta.get("conf_positions") or [])
    if meta.get("conf_decision_pos") is not None:
        conf.add(meta["conf_decision_pos"])
    pos_map = rec.get("pos_map")
    if pos_map:
        cand = [p for p in pos_map if p not in conf] or list(pos_map)
        return (max if which == "last" else min)(cand)
    special = (rec.get("meta") or {}).get("is_special") or []
    cand = [i for i in range(len(rec.get("tokens") or []))
            if not (i < len(special) and special[i]) and i not in conf]
    if not cand:
        return None
    return cand[-1] if which == "last" else cand[0]


def label_correctness(rec: dict) -> dict[int, str]:
    """METACOGNITION — label ONE position per construction with whether the whole
    construction GRADES OK (compiles + passes every ``must``-check), read straight
    off ``meta['grade']['ok']`` (interp.grade, computed at capture time).

    Unlike the geometry labelers ("WHAT did the model build"), this asks whether the
    residual stream encodes whether what it built is CORRECT — is there a linear
    'this construction is right' direction, and at which layer does it emerge?

    Read site: the LAST stored token (``max(pos_map)`` under --keep-positions
    entities; else the last non-special token). Exists for every saved record
    regardless of grade (failing constructions are not dropped) and carries no
    within-record pseudo-replication (one label per generation).

    CONFOUND WARNING (see interp/analysis/confidence_vs_difficulty.py): the last
    entity token's POSITION moves with the number of entities, which itself tracks
    the grade — so this read site is confounded by output shape. For a clean read,
    use a fixed-position confidence token (label_correctness_conf) once captured.

    Correctness is in no single token string, so a rising curve is genuine
    self-assessment, not naming. NEEDS a capture that KEPT failing completions
    (no --only-valid); otherwise there is one class and every layer is skipped.
    """
    lab = _grade_label(rec)
    if lab is None:
        return {}
    pos = _grade_read_pos(rec, "last")
    return {pos: lab} if pos is not None else {}


def label_correctness_first(rec: dict) -> dict[int, str]:
    """Like label_correctness but reads the FIRST stored token (``min(pos_map)``).
    The first entity sits near the construction's start, so its position barely
    moves with entity count — a partial control for the output-shape confound that
    cripples the last-token read on existing (entity-only) captures."""
    lab = _grade_label(rec)
    if lab is None:
        return {}
    pos = _grade_read_pos(rec, "first")
    return {pos: lab} if pos is not None else {}


def label_correctness_conf(rec: dict) -> dict[int, str]:
    """FIXED-SLOT metacognition read — label the confidence DECISION token with the
    whole construction's grade. The decision token (``conf_decision_pos``: the
    ':'/space that GENERATES the number, from an --elicit-confidence capture) is where
    the model reads out its confidence, and its local context is identical on every
    record, so its layer-0 embedding cannot encode the answer: layer 0 should be
    ~chance and any mid-late signal is genuine computed self-assessment, free of the
    entity read-site confound that sinks label_correctness. Falls back to the last
    digit token if no decision position was stored (older captures). Empty unless
    captured with --elicit-confidence."""
    lab = _grade_label(rec)
    if lab is None:
        return {}
    meta = rec.get("meta") or {}
    dpos = meta.get("conf_decision_pos")
    if dpos is not None:
        return {dpos: lab}
    conf = meta.get("conf_positions") or []
    return {max(conf): lab} if conf else {}


def label_correctness_conf_digit(rec: dict) -> dict[int, str]:
    """Comparison read site — at the confidence DIGIT (last number token): the state
    AFTER the model commits the value. Contrast with label_correctness_conf (the
    decision token that generates it) to see whether reading post-commitment leaks the
    emitted value vs the pre-commitment internal state."""
    lab = _grade_label(rec)
    if lab is None:
        return {}
    conf = (rec.get("meta") or {}).get("conf_positions") or []
    return {max(conf): lab} if conf else {}


# name -> (labeler, task). task "clf" = classification, "reg" = regression.
LABELERS = {
    "relation": (label_relation, "clf"),
    "entity_relation": (label_entity_relation, "clf"),
    "point_coord": (label_point_coord, "reg"),
    "angle": (label_angle, "reg"),
    "correctness": (label_correctness, "clf"),
    "correctness_first": (label_correctness_first, "clf"),
    "correctness_conf": (label_correctness_conf, "clf"),
    "correctness_conf_digit": (label_correctness_conf_digit, "clf"),
}


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
        # If capture kept only a subset of token positions, `positions` holds the
        # ORIGINAL completion-token index of each stored slot -> map orig->slot.
        pos_map = None
        if "positions" in d:
            pos_map = {int(orig): i for i, orig in enumerate(d["positions"].tolist())}
        records.append({
            "pid": pid,
            "acts": d["acts"],                 # [L, n_stored, D] float16
            "layer_ids": list(d["layer_ids"]),
            "tokens": meta[pid]["tokens"],
            "offsets": d["offsets"].tolist() if "offsets" in d else None,
            "completion": meta[pid].get("completion", ""),
            "pos_map": pos_map,                # None = all positions stored
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
    import re

    X, y, groups, toks = [], [], [], []
    for gi, rec in enumerate(records):
        # Group by BASE PROMPT (strip a trailing _s<N> sample suffix), not by
        # record/sample. Multi-sample captures store K completions of one prompt
        # (same point names + geometry); grouping by sample would let the split
        # put siblings on both sides -> leakage. Falls back to gi if no pid.
        base = re.sub(r"_s\d+$", "", rec.get("pid", str(gi))) or str(gi)
        labels = labeler(rec)
        acts = rec["acts"]               # [L, n_stored, D]
        pos_map = rec.get("pos_map")     # orig completion idx -> stored slot, or None
        special = rec["meta"].get("is_special") or []
        tokens = rec["tokens"]
        for pos, lab in labels.items():   # pos = ORIGINAL completion-token index
            if pos < 0:
                continue
            if special and pos < len(special) and special[pos]:
                continue
            if pos_map is None:
                if pos >= acts.shape[1]:
                    continue
                ai = pos
            else:
                ai = pos_map.get(pos)
                if ai is None:            # this position wasn't stored
                    continue
            X.append(acts[layer_pos, ai, :].astype("float32"))
            y.append(lab)
            groups.append(base)
            toks.append(tokens[pos] if pos < len(tokens) else "")
    if not X:
        return np.empty((0, 0)), np.array([]), np.array([]), np.array([])
    return np.stack(X), np.array(y), np.array(groups), np.array(toks)


def _token_identity_baseline(toks, y, groups, tr, te) -> float:
    """CONTROL — predict the (clf) label from the TOKEN STRING alone (no
    activations): majority label per token on train, applied to test. If the
    residual-stream probe barely beats this, the 'decodability' is just naming
    convention, not a computed representation.
    """
    from collections import Counter, defaultdict
    by_tok = defaultdict(Counter)
    for i in tr:
        by_tok[toks[i]][y[i]] += 1
    global_major = Counter(y[i] for i in tr).most_common(1)[0][0]
    correct = 0
    for i in te:
        pred = by_tok[toks[i]].most_common(1)[0][0] if by_tok.get(toks[i]) else global_major
        correct += (pred == y[i])
    return correct / len(te) if len(te) else 0.0


def run_probe(act_dir: pathlib.Path, labeler_name: str, test_frac: float, seed: int,
              pca: int = 100):
    import numpy as np
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression, Ridge
    from sklearn.model_selection import GroupShuffleSplit
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    def _pipeline(estimator, n_train, n_features):
        # PCA before the linear probe: residual dim (3584) >> #samples otherwise,
        # which makes regression overfit (negative R^2). Components must be
        # < n_train and <= n_features.
        steps = [StandardScaler()]
        if pca and pca > 0:
            n_comp = max(2, min(pca, n_train - 1, n_features))
            steps.append(PCA(n_components=n_comp, random_state=0))
        steps.append(estimator)
        return make_pipeline(*steps)

    records = load_dataset(act_dir)
    if not records:
        raise SystemExit(f"no .npz records found in {act_dir}")
    labeler, task = LABELERS[labeler_name]
    n_layers = records[0]["acts"].shape[0]
    layer_ids = records[0]["layer_ids"]
    print(f"{len(records)} prompts, {n_layers} layers; labeler={labeler_name} ({task})")

    # one PROMPT-LEVEL split, reused across layers so the curve is comparable
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_frac, random_state=seed)
    tok_base = None

    curve = []
    for li in range(n_layers):
        X, y, groups, toks = build_xy(records, li, labeler)
        n_train_groups = len(set(groups)) if len(groups) else 0
        if len(y) < 10 or n_train_groups < 2:
            print(f"layer {layer_ids[li]:>3}: too few samples ({len(y)} pts, "
                  f"{n_train_groups} prompts) — skipping")
            continue
        if task == "clf" and len(np.unique(y)) < 2:
            print(f"layer {layer_ids[li]:>3}: <2 classes — skipping")
            continue
        tr, te = next(splitter.split(X, y, groups))   # prompts disjoint across tr/te

        if task == "clf":
            model = _pipeline(LogisticRegression(max_iter=2000, C=1.0), len(tr), X.shape[1])
            model.fit(X[tr], y[tr])
            score = model.score(X[te], y[te])          # accuracy
            _, te_counts = np.unique(y[te], return_counts=True)
            baseline = te_counts.max() / te_counts.sum()   # majority class
            if tok_base is None:                        # token-identity control (once)
                tok_base = _token_identity_baseline(toks, y, groups, tr, te)
            metric = "acc"
        else:  # regression (e.g. coordinates): R^2, baseline 0 = predicting the mean
            model = _pipeline(Ridge(alpha=1.0), len(tr), X.shape[1])
            Y = np.stack(y)
            model.fit(X[tr], Y[tr])
            score = model.score(X[te], Y[te])          # R^2 (avg over outputs)
            baseline = 0.0
            metric = "R2"

        curve.append({"layer": int(layer_ids[li]), "score": round(float(score), 4),
                      "baseline": round(float(baseline), 4), "n": int(len(y)),
                      "n_test": int(len(te))})
        bar = "#" * max(0, int(score * 40))
        print(f"layer {layer_ids[li]:>3}: {metric}={score:.3f} (base {baseline:.3f}) "
              f"n={len(y):<5} {bar}")

    out = {"act_dir": str(act_dir), "labeler": labeler_name, "task": task,
           "token_baseline": tok_base, "curve": curve}
    out_path = act_dir / f"probe_{labeler_name}.json"
    out_path.write_text(json.dumps(out, indent=2))
    if curve:
        best = max(curve, key=lambda c: c["score"])
        print(f"\npeak: layer {best['layer']} score={best['score']:.3f} "
              f"(baseline {best['baseline']:.3f})")
        if tok_base is not None:
            verdict = ("⚠️ probe barely beats naming — likely a token-identity confound"
                       if best["score"] <= tok_base + 0.03
                       else "✓ probe beats the token-only baseline — real signal beyond naming")
            print(f"token-identity baseline (clf): {tok_base:.3f}  →  {verdict}")
        print(f"-> {out_path.name}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--act-dir", required=True, help="capture output dir (has meta.jsonl + *.npz)")
    ap.add_argument("--labeler", default="relation", choices=list(LABELERS))
    ap.add_argument("--test-frac", type=float, default=0.3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--pca", type=int, default=100,
                    help="PCA components before the probe (0 = off). Cap < n_train.")
    args = ap.parse_args()
    run_probe(pathlib.Path(args.act_dir), args.labeler, args.test_frac, args.seed, args.pca)


if __name__ == "__main__":
    main()
