"""
Cross-format probe transfer — does a probe trained on one surface format
read the same information out of the residual stream in another format?

Loads reading-mode captures (capture_reading.py) for a source format and one
or more target formats of the SAME figures, trains per-layer linear probes on
the source, and evaluates them frozen on the targets.

Conditions per (labeler, layer, target-format):
  in_domain       — source-trained probe on held-out figures, source format
  transfer_strict — source-trained probe on held-out figures, target format
                    (tests format transfer AND figure generalization at once)
  transfer_seen   — source-trained probe on TRAIN figures, target format
                    (format transfer only; diagnostic)
  ceiling         — target-trained probe on held-out figures, target format
  floor           — token-identity baseline on target (clf only); the corpus
                    randomizes entity names, so this should sit near majority

The figure-level train/test split is IDENTICAL across formats (matched corpus),
so held-out means held out of every format's training everywhere.

Usage:
  interp/.venv/bin/python interp/transfer/probe_transfer.py \
      --act-root interp/activations/transfer_q15 --train-format recipe \
      --labelers entity_relation,point_coord,angle --seeds 5 \
      --out interp/transfer/results_q15.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys

import numpy as np

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from interp.probe import build_xy, load_dataset  # noqa: E402


# ---------------------------------------------------------------------------
# span-based labelers (the corpus records exact id char spans per format —
# no quoted-JSON convention needed, unlike interp.probe's labelers)
# ---------------------------------------------------------------------------

def _id_positions_spans(rec: dict, entity_id: str) -> list[int]:
    spans = (rec["meta"].get("id_spans") or {}).get(entity_id) or []
    offsets = rec.get("offsets")
    if not spans or offsets is None:
        return []
    spans = [tuple(s) for s in spans]
    return [pos for pos, (s, e) in enumerate(offsets)
            if s != e and any(s < ce and e > cs for (cs, ce) in spans)]


def label_entity_relation(rec: dict) -> dict[int, str]:
    gt = rec["meta"].get("ground_truth") or {}
    out: dict[int, str] = {}
    for eid, relation in (gt.get("entity_relations") or {}).items():
        for pos in _id_positions_spans(rec, eid):
            out[pos] = relation
    return out


def label_point_coord(rec: dict) -> dict[int, list]:
    gt = rec["meta"].get("ground_truth") or {}
    coords = gt.get("point_coords") or {}
    if len(coords) < 2:
        return {}
    xs = [c[0] for c in coords.values()]
    ys = [c[1] for c in coords.values()]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    wx, wy = (x1 - x0) or 1.0, (y1 - y0) or 1.0
    out: dict[int, list] = {}
    for eid, (x, y) in coords.items():
        norm = [(x - x0) / wx, (y - y0) / wy]
        for pos in _id_positions_spans(rec, eid):
            out[pos] = norm
    return out


def label_angle(rec: dict) -> dict[int, list]:
    gt = rec["meta"].get("ground_truth") or {}
    out: dict[int, list] = {}
    for vid, deg in (gt.get("vertex_angles") or {}).items():
        for pos in _id_positions_spans(rec, vid):
            out[pos] = [float(deg)]
    return out


LABELERS = {
    "entity_relation": (label_entity_relation, "clf"),
    "point_coord": (label_point_coord, "reg"),
    "angle": (label_angle, "reg"),
}


# ---------------------------------------------------------------------------
# probe fitting / scoring
# ---------------------------------------------------------------------------

def make_probe(task: str, n_train: int, pca: int):
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression, Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    steps = [StandardScaler()]
    if pca and pca > 0:
        steps.append(PCA(n_components=max(2, min(pca, n_train - 1)),
                         random_state=0))
    est = (LogisticRegression(max_iter=2000) if task == "clf"
           else Ridge(alpha=1.0))
    steps.append(est)
    return make_pipeline(*steps)


def score(pipe, X, y, task: str) -> float:
    if len(y) == 0:
        return float("nan")
    if task == "clf":
        return float((pipe.predict(X) == y).mean())
    from sklearn.metrics import r2_score
    return float(r2_score(np.stack(y), pipe.predict(X)))


def token_floor(toks_tr, y_tr, toks_te, y_te) -> float:
    """Majority label per token string on train, applied to test (clf)."""
    from collections import Counter, defaultdict
    by_tok = defaultdict(Counter)
    for t, lab in zip(toks_tr, y_tr):
        by_tok[t][lab] += 1
    major = Counter(y_tr).most_common(1)[0][0]
    preds = [by_tok[t].most_common(1)[0][0] if by_tok.get(t) else major
             for t in toks_te]
    return float(np.mean([p == t for p, t in zip(preds, y_te)]))


def split_figures(all_groups: list[str], test_frac: float, seed: int):
    figs = sorted(set(all_groups))
    rng = random.Random(seed)
    rng.shuffle(figs)
    n_te = max(1, int(round(len(figs) * test_frac)))
    return set(figs[n_te:]), set(figs[:n_te])   # train, test


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def run(act_root: pathlib.Path, train_format: str, eval_formats: list[str],
        labeler_names: list[str], n_seeds: int, test_frac: float, pca: int):
    datasets = {}
    for fmt in [train_format] + eval_formats:
        d = load_dataset(act_root / fmt)
        if not d:
            raise SystemExit(f"no records in {act_root / fmt}")
        datasets[fmt] = d
    layer_ids = datasets[train_format][0]["layer_ids"]
    n_layers = len(layer_ids)

    results = {"train_format": train_format, "eval_formats": eval_formats,
               "n_seeds": n_seeds, "test_frac": test_frac, "pca": pca,
               "layer_ids": [int(l) for l in layer_ids], "labelers": {}}

    for lname in labeler_names:
        labeler, task = LABELERS[lname]
        print(f"\n=== labeler: {lname} ({task}) ===", flush=True)
        # per layer per condition -> list over seeds
        curves: dict[str, dict[str, list[list[float]]]] = {}

        for seed in range(n_seeds):
            src_groups_all = [r["pid"] for r in datasets[train_format]]
            tr_figs, te_figs = split_figures(src_groups_all, test_frac, seed)

            for li in range(n_layers):
                xs = {fmt: build_xy(datasets[fmt], li, labeler)
                      for fmt in datasets}
                Xs, ys, gs, ts = xs[train_format]
                if len(ys) < 20:
                    continue
                s_tr = np.array([g in tr_figs for g in gs])
                s_te = ~s_tr
                if task == "clf" and len(set(ys[s_tr])) < 2:
                    continue
                probe = make_probe(task, int(s_tr.sum()), pca)
                y_tr = ys[s_tr] if task == "clf" else np.stack(ys[s_tr])
                probe.fit(Xs[s_tr], y_tr)

                def rec_(cond: str, val: float):
                    curves.setdefault(cond, {}).setdefault(str(li), []).append(val)

                rec_("in_domain", score(probe, Xs[s_te], ys[s_te], task))

                for fmt in eval_formats:
                    Xt, yt, gt_, tt = xs[fmt]
                    if len(yt) == 0:
                        continue
                    t_te = np.array([g in te_figs for g in gt_])
                    t_tr = ~t_te
                    rec_(f"transfer_strict:{fmt}",
                         score(probe, Xt[t_te], yt[t_te], task))
                    rec_(f"transfer_seen:{fmt}",
                         score(probe, Xt[t_tr], yt[t_tr], task))
                    # ceiling: target-trained probe, same split
                    if t_tr.sum() >= 10 and (task == "reg"
                                             or len(set(yt[t_tr])) >= 2):
                        ceil = make_probe(task, int(t_tr.sum()), pca)
                        yt_tr = yt[t_tr] if task == "clf" else np.stack(yt[t_tr])
                        ceil.fit(Xt[t_tr], yt_tr)
                        rec_(f"ceiling:{fmt}",
                             score(ceil, Xt[t_te], yt[t_te], task))
                    if task == "clf" and li == 0:
                        rec_(f"floor:{fmt}",
                             token_floor(tt[t_tr], yt[t_tr], tt[t_te], yt[t_te]))
            print(f"  seed {seed} done", flush=True)

        agg = {}
        for cond, by_layer in curves.items():
            agg[cond] = {li: [float(np.mean(v)), float(np.std(v))]
                         for li, v in sorted(by_layer.items(), key=lambda kv: int(kv[0]))}
        results["labelers"][lname] = agg

        # console summary at the source in-domain peak layer
        indom = agg.get("in_domain", {})
        if indom:
            peak = max(indom, key=lambda li: indom[li][0])
            print(f"  peak in-domain layer {peak}: "
                  f"{indom[peak][0]:.3f} ± {indom[peak][1]:.3f}")
            for cond in sorted(agg):
                if cond == "in_domain":
                    continue
                v = agg[cond].get(peak) or agg[cond].get("0")
                if v:
                    print(f"    {cond:28s} @L{peak}: {v[0]:.3f} ± {v[1]:.3f}")
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--act-root", required=True)
    ap.add_argument("--train-format", default="recipe")
    ap.add_argument("--eval-formats", default="tikz,svg,english")
    ap.add_argument("--labelers", default="entity_relation,point_coord,angle")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--test-frac", type=float, default=0.3)
    ap.add_argument("--pca", type=int, default=100)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    results = run(pathlib.Path(args.act_root), args.train_format,
                  [f for f in args.eval_formats.split(",") if f],
                  [l for l in args.labelers.split(",") if l],
                  args.seeds, args.test_frac, args.pca)
    if args.out:
        pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w") as f:
            json.dump(results, f, indent=1)
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
