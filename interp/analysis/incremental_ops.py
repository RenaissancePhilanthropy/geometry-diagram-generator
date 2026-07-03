"""
Incremental-validity control — does the confidence-slot activation predict correctness
BEYOND the #ops / output-shape surface features?

confidence_vs_difficulty.py compares the probe vs surface SEPARATELY. This asks the
sharper question: within-prompt (difficulty held fixed), if a logistic model already
has the surface features (n_tokens, n_ops, n_id_mentions), does ADDING the residual-
stream activation raise within-prompt AUROC? A positive, stable delta => the activation
carries correctness signal output-shape does not, i.e. genuine computed self-assessment
beyond #ops. (This is what decides whether GLM's borderline +0.03 vs surface is real.)

All out-of-fold (GroupKFold by base prompt), positive class = ok, read site =
label_correctness_conf (the decision token; falls back to the digit on older captures).

    interp/.venv/bin/python interp/analysis/incremental_ops.py \
        --act-dir interp/activations/glm7_2turn --layers 0,16,24,32,40,47
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")  # benign PCA zero-variance-component divides

REPO = pathlib.Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from interp.probe import build_xy, label_correctness_conf, load_dataset  # noqa: E402
from interp.analysis.confidence_vs_difficulty import (  # noqa: E402
    _within_prompt_auroc,
    build_surface,
)


def _oof(X_surf, X_act, y_ok, groups, n_splits, use_surf, use_act, pca=100):
    """Out-of-fold P(ok) from a logistic model over surface feats and/or PCA(activation).
    GroupKFold splits only on `groups`, so surf/act/both share identical folds -> a fair
    within-prompt comparison."""
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold
    from sklearn.preprocessing import StandardScaler

    p = np.full(len(y_ok), np.nan)
    for tr, te in GroupKFold(n_splits=n_splits).split(X_surf, y_ok, groups):
        if len(np.unique(y_ok[tr])) < 2:
            continue
        cols_tr, cols_te = [], []
        if use_surf:
            sc = StandardScaler().fit(X_surf[tr])
            cols_tr.append(sc.transform(X_surf[tr])); cols_te.append(sc.transform(X_surf[te]))
        if use_act:
            sc = StandardScaler().fit(X_act[tr])
            a_tr, a_te = sc.transform(X_act[tr]), sc.transform(X_act[te])
            k = max(2, min(pca, len(tr) - 1, X_act.shape[1]))
            pc = PCA(n_components=k, random_state=0).fit(a_tr)
            cols_tr.append(pc.transform(a_tr)); cols_te.append(pc.transform(a_te))
        model = LogisticRegression(max_iter=2000, C=1.0).fit(np.hstack(cols_tr), y_ok[tr])
        p[te] = model.predict_proba(np.hstack(cols_te))[:, list(model.classes_).index(1)]
    return p


def run(act_dir: pathlib.Path, layers) -> None:
    records = load_dataset(act_dir)
    if not records:
        raise SystemExit(f"no records in {act_dir}")
    Xs, ys, gs = build_surface(records, label_correctness_conf)
    if len(ys) == 0:
        raise SystemExit("no confidence-slot records (need an --elicit-confidence / "
                         "--confidence-followup capture)")
    y_ok = (ys == "ok").astype(int)
    n_groups = len(set(gs))
    mixed = sum(1 for g in set(gs) if 0 < y_ok[gs == g].sum() < int((gs == g).sum()))
    n_splits = min(5, n_groups)
    n_layers = records[0]["acts"].shape[0]
    layer_ids = [int(x) for x in records[0]["layer_ids"]]

    print(f"{act_dir.name}: {len(ys)} records, {n_groups} prompts, {mixed} mixed-outcome; "
          f"GroupKFold k={n_splits}")
    p_surf = _oof(Xs, Xs, y_ok, gs, n_splits, True, False)
    a_surf = _within_prompt_auroc(p_surf, y_ok, gs)[0]
    print(f"  surface-only (n_tokens/n_ops/n_id) within-prompt AUROC = {a_surf:.3f}\n")
    print(f"  {'layer':>5} {'act-only':>9} {'surf+act':>9} {'Δ over surface':>16}")

    best = None
    for li in range(n_layers):
        if layers is not None and layer_ids[li] not in layers:
            continue
        Xa, ya, ga, _ = build_xy(records, li, label_correctness_conf)
        assert np.array_equal(ya, ys), "activation rows misaligned with surface rows"
        a_act = _within_prompt_auroc(_oof(Xs, Xa, y_ok, gs, n_splits, False, True), y_ok, gs)[0]
        a_both = _within_prompt_auroc(_oof(Xs, Xa, y_ok, gs, n_splits, True, True), y_ok, gs)[0]
        inc = a_both - a_surf
        print(f"  {layer_ids[li]:>5} {a_act:>9.3f} {a_both:>9.3f} {inc:>+16.3f}")
        if best is None or inc > best[1]:
            best = (layer_ids[li], inc, a_both, a_act)

    if best:
        print(f"\n  best: layer {best[0]} surf+act {best[2]:.3f} vs surf-only {a_surf:.3f} "
              f"=> activation adds {best[1]:+.3f} over #ops/shape")
        verdict = ("activation predicts correctness BEYOND output-shape (computed self-assessment)"
                   if best[1] > 0.03 else
                   "activation adds little over #ops -> not clearly beyond output-shape")
        print(f"  => {verdict}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--act-dir", required=True)
    ap.add_argument("--layers", default="", help="comma list of hidden-state indices (default all)")
    args = ap.parse_args()
    layers = ([int(x) for x in args.layers.split(",") if x.strip()] if args.layers else None)
    run(pathlib.Path(args.act_dir), layers)


if __name__ == "__main__":
    main()
