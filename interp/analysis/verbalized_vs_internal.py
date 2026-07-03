"""
The payoff comparison for the confidence experiment — run on an --elicit-confidence
capture: does the model's INTERNAL state predict its own correctness better than the
number it SAYS?

Three predictors of the grade (positive class = 'ok'), scored by AUROC:
  difficulty  : the prompt's leave-one-out pass-rate (the confound floor).
  verbalized  : the model's stated 'Confidence: N' (meta conf_value).
  internal    : an out-of-fold linear probe on the residual stream at the FIXED
                confidence slot (label_correctness_conf), cross-prompt (GroupKFold).

If internal > verbalized, the model 'knows more than it says'. We also print the
verbalized calibration (mean stated confidence for pass vs fail + a reliability
table). For the difficulty/surface-controlled view at the confidence slot, run
  confidence_vs_difficulty.py --act-dir <dir> --read conf

    interp/.venv/bin/python interp/analysis/verbalized_vs_internal.py \
        --act-dir interp/activations/conf7b
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

import numpy as np

REPO = pathlib.Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from interp.probe import build_xy, label_correctness_conf, load_dataset  # noqa: E402
from interp.analysis.confidence_vs_difficulty import (  # noqa: E402
    _difficulty_auroc,
    _oof_pok,
)


def _reliability(conf, ok, edges=(0, 20, 40, 60, 80, 101)):
    """Stated-confidence bucket -> actual pass rate (are the stated numbers calibrated?)."""
    rows = []
    for lo, hi in zip(edges, edges[1:]):
        m = (conf >= lo) & (conf < hi)
        if m.any():
            rows.append((lo, hi - 1, int(m.sum()), float(ok[m].mean())))
    return rows


def run(act_dir: pathlib.Path, layers=None) -> dict:
    from sklearn.metrics import roc_auc_score

    records = load_dataset(act_dir)
    recs = [r for r in records
            if r["meta"].get("conf_value") is not None
            and (r["meta"].get("grade") or {}).get("ok") is not None
            and r["meta"].get("conf_positions")]
    if not recs:
        raise SystemExit("no records with conf_value + conf_positions + grade "
                         "(capture with --elicit-confidence)")

    conf = np.array([r["meta"]["conf_value"] for r in recs], dtype=float)
    ok = np.array([1 if r["meta"]["grade"]["ok"] else 0 for r in recs])
    groups = np.array([re.sub(r"_s\d+$", "", r["pid"]) for r in recs])
    n = len(recs)
    print(f"{act_dir.name}: {n} records with stated confidence "
          f"({int(ok.sum())} ok / {int(n - ok.sum())} fail), {len(set(groups))} prompts")
    print(f"  stated confidence: mean {conf.mean():.1f} "
          f"(ok {conf[ok == 1].mean():.1f} / fail {conf[ok == 0].mean():.1f}), "
          f"range {conf.min():.0f}-{conf.max():.0f}")
    print("  reliability (stated bucket -> actual pass rate):")
    for lo, hi, cnt, rate in _reliability(conf, ok):
        print(f"    {lo:>3}-{hi:<3}: n={cnt:<4} actual pass={rate:.2f}")

    both = len(set(ok)) > 1
    diff_auroc = _difficulty_auroc(ok, groups) if both else float("nan")
    verb_auroc = roc_auc_score(ok, conf) if both else float("nan")

    # internal probe at the fixed confidence slot, cross-prompt OOF, best layer
    n_layers = recs[0]["acts"].shape[0]
    layer_ids = [int(x) for x in recs[0]["layer_ids"]]
    best = None
    for li in range(n_layers):
        if layers is not None and layer_ids[li] not in layers:
            continue
        X, y, g, _ = build_xy(recs, li, label_correctness_conf)
        if len(y) < 10:
            continue
        y_ok = (y == "ok").astype(int)
        p = _oof_pok(X, y_ok, g, min(5, len(set(g))))
        mask = ~np.isnan(p)
        if len(set(y_ok[mask].tolist())) < 2:
            continue
        a = roc_auc_score(y_ok[mask], p[mask])
        if best is None or a > best[1]:
            best = (layer_ids[li], float(a))

    print("\n  AUROC for predicting correctness (positive = ok):")
    print(f"    difficulty (prompt base-rate) : {diff_auroc:.3f}")
    print(f"    VERBALIZED (stated number)    : {verb_auroc:.3f}")
    if best:
        print(f"    INTERNAL probe @ conf slot L{best[0]} : {best[1]:.3f}")
        verdict = ("INTERNAL > verbalized: the model knows more than it says."
                   if best[1] > verb_auroc + 0.02
                   else "internal <= verbalized: no clear internal advantage.")
        print(f"  --> {verdict}")
    return {"n": n, "difficulty_auroc": diff_auroc, "verbalized_auroc": verb_auroc,
            "internal_best": best}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--act-dir", required=True)
    ap.add_argument("--layers", default="",
                    help="comma list of hidden-state indices (default: all)")
    args = ap.parse_args()
    layers = ([int(x) for x in args.layers.split(",") if x.strip()]
              if args.layers else None)
    run(pathlib.Path(args.act_dir), layers)


if __name__ == "__main__":
    main()
