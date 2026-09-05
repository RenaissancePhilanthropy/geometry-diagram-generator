#!/usr/bin/env python
"""Probe accuracy against depth, at the PRE and POST read sites, for one cell.

The question this answers: is the probe reading "this question is hard" or "this
attempt went wrong"? Difficulty is fully present *before* the model attempts, so a
difficulty probe should read just as well at the PRE site as at the POST site. An
attempt-specific signal should be near chance at PRE and rise at POST.

Two sites, both content-neutral:
  PRE   `prompt_dtoken`  last prompt token, no confidence question asked at all
  POST  `post_dtoken`    the token that generates the confidence digit, after the attempt

For every layer we fit the same probe used everywhere else in this study
(StandardScaler -> PCA(50) -> LogisticRegression), scored out-of-fold with folds
grouped by base question so a question's samples never straddle the split.

Also reports, at the fixed 0.7-depth layer:
  * per-record correlation between the PRE and POST probe scores
  * the POST-trained probe evaluated at the PRE site (train POST, test PRE, held-out
    groups) -- if the direction is difficulty it transfers; if it is attempt-specific
    it collapses to chance

Usage:
    python interp/analysis/pre_post_layer_curve.py \
        --act-dir interp/activations/mtx_mistral_mmlu_pro --label "MMLU-Pro" \
        --out interp/results/curve_mmlu_pro.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re

import numpy as np


def _pipe(k: int):
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression
    return make_pipeline(StandardScaler(), PCA(k, random_state=0),
                         LogisticRegression(max_iter=2000))


def oof_scores(X, y, groups, pca=50, folds=5):
    """Grouped out-of-fold decision scores. NaN where a fold could not be scored."""
    from sklearn.model_selection import GroupKFold
    X = np.asarray(X, np.float32)
    y = np.asarray(y)
    scores = np.full(len(y), np.nan)
    ns = min(folds, len(set(groups.tolist())))
    if ns < 2 or len(set(y.tolist())) < 2:
        return scores
    for tr, te in GroupKFold(ns).split(X, y, groups):
        if len(set(y[tr].tolist())) < 2:
            continue
        k = min(pca, len(tr) - 1, X.shape[1])
        scores[te] = _pipe(k).fit(X[tr], y[tr]).decision_function(X[te])
    return scores


def auroc(y, s):
    from sklearn.metrics import roc_auc_score
    m = ~np.isnan(s)
    if m.sum() < 10 or len(set(y[m].tolist())) < 2:
        return float("nan")
    return float(roc_auc_score(y[m], s[m]))


def cross_site(Xtrain, Xtest, y, groups, pca=50, folds=5):
    """Train at one site, evaluate at the other, on held-out groups."""
    from sklearn.model_selection import GroupKFold
    scores = np.full(len(y), np.nan)
    ns = min(folds, len(set(groups.tolist())))
    if ns < 2:
        return scores
    for tr, te in GroupKFold(ns).split(Xtrain, y, groups):
        if len(set(y[tr].tolist())) < 2:
            continue
        k = min(pca, len(tr) - 1, Xtrain.shape[1])
        p = _pipe(k).fit(Xtrain[tr], y[tr])
        scores[te] = p.decision_function(Xtest[te])       # same rows, other site
    return scores


def load(act_dir: pathlib.Path):
    """Return (y, groups, PRE[n,L,d], POST[n,L,d]) keeping only records with both sites."""
    meta = [json.loads(l) for l in (act_dir / "meta.jsonl").read_text().splitlines()]
    y, g, pre, post = [], [], [], []
    for r in meta:
        f = act_dir / f"{r['pid']}.npz"
        if not f.exists():
            continue
        z = np.load(f)
        if "prompt_dtoken" not in z or "post_dtoken" not in z:
            continue
        pre.append(z["prompt_dtoken"].astype(np.float32))
        post.append(z["post_dtoken"].astype(np.float32))
        y.append(1 if r["grade"]["ok"] else 0)
        g.append(re.sub(r"_s\d+$", "", r["pid"]))
    return (np.array(y), np.array(g), np.stack(pre), np.stack(post))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--act-dir", required=True)
    ap.add_argument("--label", required=True, help="display name, e.g. 'MMLU-Pro'")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pca", type=int, default=50)
    args = ap.parse_args()

    d = pathlib.Path(args.act_dir)
    y, g, PRE, POST = load(d)
    n, L, dim = PRE.shape
    fixed = int(round(0.7 * (L - 1)))                     # same layer the study reports
    print(f"{args.label}: n={n}  layers={L}  dim={dim}  pass={y.mean():.2f}  fixed layer={fixed}")

    curve = {"pre": [], "post": []}
    for li in range(L):
        s_pre = oof_scores(PRE[:, li, :], y, g, args.pca)
        s_post = oof_scores(POST[:, li, :], y, g, args.pca)
        a_pre, a_post = auroc(y, s_pre), auroc(y, s_post)
        curve["pre"].append(a_pre)
        curve["post"].append(a_post)
        print(f"  layer {li:>3}/{L-1}   pre {a_pre:.3f}   post {a_post:.3f}")

    # --- at the fixed layer: correlation, and the POST direction read at PRE ---
    s_pre_f = oof_scores(PRE[:, fixed, :], y, g, args.pca)
    s_post_f = oof_scores(POST[:, fixed, :], y, g, args.pca)
    m = ~np.isnan(s_pre_f) & ~np.isnan(s_post_f)
    corr = float(np.corrcoef(s_pre_f[m], s_post_f[m])[0, 1])
    s_xs = cross_site(POST[:, fixed, :], PRE[:, fixed, :], y, g, args.pca)
    xs = auroc(y, s_xs)

    out = {
        "label": args.label, "act_dir": str(d), "n": int(n), "layers": int(L),
        "dim": int(dim), "pass_rate": float(y.mean()), "fixed_layer": fixed,
        "curve": curve,
        "at_fixed_layer": {
            "pre": auroc(y, s_pre_f),
            "post": auroc(y, s_post_f),
            "corr_pre_post_scores": corr,
            "post_probe_read_at_pre_site": xs,
        },
    }
    pathlib.Path(args.out).write_text(json.dumps(out, indent=1))
    f = out["at_fixed_layer"]
    print(f"\nat layer {fixed}:  pre {f['pre']:.3f}   post {f['post']:.3f}   "
          f"corr(pre,post scores) {corr:+.2f}   POST probe at PRE site {xs:.3f}")
    print("saved", args.out)


if __name__ == "__main__":
    main()
