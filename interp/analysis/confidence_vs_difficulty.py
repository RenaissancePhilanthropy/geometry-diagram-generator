"""
Is the correctness probe reading ATTEMPT-correctness ("this generation is going
wrong") or just PROBLEM-difficulty ("this prompt is hard")?  Under a cross-prompt
split the two are indistinguishable -- a probe that only knows difficulty still
predicts held-out prompts well.  This script isolates them by holding the prompt
FIXED.

Within one base prompt, temperature sampling produced K completions; some pass,
some fail, but the prompt (=> its difficulty) is IDENTICAL across them.  So if the
correctness direction ranks a prompt's passing samples above its failing ones,
that separation cannot be difficulty -- it must be attempt-level.

All probe scores are OUT-OF-FOLD (GroupKFold by base prompt: every sample is
scored by a probe that never trained on its prompt), so nothing leaks.  Positive
class = "ok".

  AUROC_difficulty   predict each sample by its prompt's leave-one-out pass rate.
                     The confound's CEILING -- how far "just know the prompt" gets.
  AUROC_crossprompt  the probe's OOF AUROC over all samples (difficulty + attempt
                     mixed together) -- what the deployed probe actually achieves.
  AUROC_withinprompt over pass/fail pairs WITHIN the same prompt, pooled across
                     mixed-outcome prompts (difficulty removed by construction).
                     THE control: > 0.5 => real attempt signal; ~0.5 => the probe
                     was only riding difficulty.
  sign test          # mixed-outcome prompts where mean P(ok|pass) > mean P(ok|fail).

    interp/.venv/bin/python interp/analysis/confidence_vs_difficulty.py \
        --act-dir interp/activations/big30
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np

REPO = pathlib.Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from interp.probe import (  # noqa: E402
    build_xy,
    label_correctness,
    label_correctness_conf,
    label_correctness_conf_digit,
    label_correctness_first,
    load_dataset,
)


def _pipeline(n_train: int, n_features: int, pca: int = 100):
    """Same recipe as probe.run_probe: StandardScaler -> PCA -> LogisticRegression
    (with predict_proba for ranking). PCA capped < n_train and <= n_features."""
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    n_comp = max(2, min(pca, n_train - 1, n_features))
    return make_pipeline(StandardScaler(),
                         PCA(n_components=n_comp, random_state=0),
                         LogisticRegression(max_iter=2000, C=1.0))


def _oof_pok(X, y_ok, groups, n_splits: int):
    """Out-of-fold P(ok) per sample via GroupKFold on base prompt: a sample's score
    always comes from a probe that never saw its prompt (leakage-free)."""
    from sklearn.model_selection import GroupKFold

    p = np.full(len(y_ok), np.nan)
    for tr, te in GroupKFold(n_splits=n_splits).split(X, y_ok, groups):
        if len(np.unique(y_ok[tr])) < 2:
            continue                                   # degenerate train fold
        model = _pipeline(len(tr), X.shape[1])
        model.fit(X[tr], y_ok[tr])
        ok_col = list(model.classes_).index(1)
        p[te] = model.predict_proba(X[te])[:, ok_col]
    return p


def _within_prompt_auroc(p_ok, y_ok, groups):
    """Fraction of within-prompt (pass, fail) pairs the probe ranks correctly,
    pooled over prompts that contain BOTH a pass and a fail (== within-group AUROC).
    Returns (auroc, n_pairs, per_prompt_mean_diffs)."""
    wins = pairs = 0.0
    diffs = []
    for g in set(groups):
        m = (groups == g) & ~np.isnan(p_ok)
        pos = p_ok[m & (y_ok == 1)]
        neg = p_ok[m & (y_ok == 0)]
        if len(pos) == 0 or len(neg) == 0:
            continue                                   # not a mixed-outcome prompt
        wins += sum((a > b) + 0.5 * (a == b) for a in pos for b in neg)
        pairs += len(pos) * len(neg)
        diffs.append(float(pos.mean() - neg.mean()))
    return (wins / pairs if pairs else float("nan")), int(pairs), diffs


def _difficulty_auroc(y_ok, groups) -> float:
    """AUROC of the leave-one-out prompt pass-rate -- the pure-difficulty predictor
    (knows only how often this prompt succeeds, nothing about the attempt)."""
    from sklearn.metrics import roc_auc_score

    score = np.zeros(len(y_ok), dtype=float)
    for g in set(groups):
        idx = np.where(groups == g)[0]
        tot = y_ok[idx].sum()
        for i in idx:
            score[i] = (tot - y_ok[i]) / (len(idx) - 1) if len(idx) > 1 else tot / len(idx)
    return roc_auc_score(y_ok, score)


# --- surface baseline: can pass/fail be told apart from the OUTPUT'S SHAPE alone? ---
SURFACE_NAMES = ["n_tokens", "n_ops", "n_id_mentions"]


def _surface_features(rec: dict) -> list[float]:
    """Cheap 'shape of the output' features from the RAW completion (so nothing
    leaks the grade the way compile-dependent stored-entity counts do): how long the
    completion is (tokens), how many construction ops it emitted (parse-time), and
    how many entity ids it mentions in the text. If THESE separate pass from fail
    within a prompt, the signal is surface form -- not the model knowing it is wrong."""
    grade = (rec.get("meta") or {}).get("grade") or {}
    comp = rec.get("completion") or ""
    return [float(len(rec.get("tokens") or [])),
            float(grade.get("n_ops") or 0),
            float(comp.count('"id"'))]             # raw id-mentions; compile-independent


def build_surface(records: list[dict], labeler=label_correctness):
    """One surface-feature row per labeled record, in build_xy's sample order (the
    correctness labelers tag exactly one non-special, always-stored position per
    record, so surface rows stay aligned row-for-row with the activation rows)."""
    import re

    Xs, y, groups = [], [], []
    for gi, rec in enumerate(records):
        labels = labeler(rec)
        if not labels:
            continue
        base = re.sub(r"_s\d+$", "", rec.get("pid", str(gi))) or str(gi)
        Xs.append(_surface_features(rec))
        y.append(next(iter(labels.values())))
        groups.append(base)
    return np.array(Xs, dtype=float), np.array(y), np.array(groups)


def run(act_dir: pathlib.Path, layers, read: str = "last") -> None:
    from sklearn.metrics import roc_auc_score

    records = load_dataset(act_dir)
    if not records:
        raise SystemExit(f"no .npz records in {act_dir}")
    labeler = {"last": label_correctness, "first": label_correctness_first,
               "conf": label_correctness_conf,
               "conf_digit": label_correctness_conf_digit}[read]
    n_layers = records[0]["acts"].shape[0]
    layer_ids = [int(x) for x in records[0]["layer_ids"]]

    # groups/labels are layer-independent -> compute the difficulty baseline once
    _, y0, groups0, _ = build_xy(records, 0, labeler)
    if len(y0) == 0:
        raise SystemExit(f"no labeled samples in {act_dir.name} for read={read} "
                         "('--read conf' needs an --elicit-confidence capture)")
    y_ok0 = (y0 == "ok").astype(int)
    n_groups = len(set(groups0))
    mixed = [g for g in set(groups0)
             if 0 < y_ok0[groups0 == g].sum() < int((groups0 == g).sum())]
    n_mixed_samples = int(sum((groups0 == g).sum() for g in mixed))
    n_splits = min(5, n_groups)

    print(f"{act_dir.name}: {len(y0)} samples, {n_groups} prompts "
          f"({int(y_ok0.sum())} ok / {int((1 - y_ok0).sum())} fail); "
          f"{len(mixed)} mixed-outcome prompts ({n_mixed_samples} samples); "
          f"GroupKFold k={n_splits}; read-site={read}")
    print(f"  AUROC_difficulty (prompt base-rate only) = {_difficulty_auroc(y_ok0, groups0):.3f}"
          f"   <- how far 'just know the prompt' gets")

    # ---- baselines the activations must BEAT to count as computed self-assessment ----
    # (a) layer-0 embeddings = everything the read token's identity+position encode.
    p0 = _oof_pok(build_xy(records, 0, labeler)[0], y_ok0, groups0, n_splits)
    surf_embed, _, _ = _within_prompt_auroc(p0, y_ok0, groups0)
    # (b) hand-crafted output-shape features (length / #ops / #id-mentions), same OOF probe.
    Xs, ys, gs = build_surface(records, labeler)
    assert np.array_equal(ys, y0), "surface rows misaligned with activation rows"
    ys_ok = (ys == "ok").astype(int)
    surf_hand, _, _ = _within_prompt_auroc(_oof_pok(Xs, ys_ok, gs, n_splits), ys_ok, gs)
    per_feat = {name: _within_prompt_auroc(Xs[:, j], ys_ok, gs)[0]
                for j, name in enumerate(SURFACE_NAMES)}
    surface_ref = max(surf_embed, surf_hand)
    print(f"  within-prompt SURFACE baselines (must be beaten): "
          f"layer-0 embed = {surf_embed:.3f} | output-shape = {surf_hand:.3f} "
          f"[{', '.join(f'{k} {v:.2f}' for k, v in per_feat.items())}]")
    print(f"  --> the bar for 'computed' = {surface_ref:.3f}\n")

    print(f"  {'layer':>5} {'cross-prompt':>12} {'within-prompt':>13} "
          f"{'lift_vs_surface':>16} {'sign(pass>fail)':>16}")

    best = None
    for li in range(n_layers):
        if layers is not None and layer_ids[li] not in layers:
            continue
        X, y, groups, _ = build_xy(records, li, labeler)
        y_ok = (y == "ok").astype(int)
        p = _oof_pok(X, y_ok, groups, n_splits)
        ok = ~np.isnan(p)
        cross = (roc_auc_score(y_ok[ok], p[ok])
                 if len(np.unique(y_ok[ok])) > 1 else float("nan"))
        within, n_pairs, diffs = _within_prompt_auroc(p, y_ok, groups)
        lift = within - surface_ref
        npos = sum(d > 0 for d in diffs)
        print(f"  {layer_ids[li]:>5} {cross:>12.3f} {within:>13.3f} {lift:>+16.3f} "
              f"{npos:>7}/{len(diffs):<8}")
        if not np.isnan(within) and (best is None or within > best[1]):
            best = (layer_ids[li], within, cross, npos, len(diffs))

    if best:
        lift = best[1] - surface_ref
        print(f"\n  best within-prompt AUROC: layer {best[0]} = {best[1]:.3f} "
              f"(cross-prompt {best[2]:.3f}); pass>fail in {best[3]}/{best[4]} mixed prompts")
        print(f"  computed lift over surface = {lift:+.3f}  "
              + ("=> deep layers BEAT surface: genuine computed self-assessment."
                 if lift > 0.05 else
                 "=> deep layers do NOT clearly beat surface: signal is largely output-shape."))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--act-dir", required=True)
    ap.add_argument("--layers", default="",
                    help="comma list of hidden-state indices (default: all)")
    ap.add_argument("--read", choices=("last", "first", "conf", "conf_digit"),
                    default="last",
                    help="which stored token to read the per-generation label at: "
                         "last/first entity; 'conf' = the confidence DECISION token "
                         "(generates the number); 'conf_digit' = the number itself "
                         "(needs an --elicit-confidence capture)")
    args = ap.parse_args()
    layers = ([int(x) for x in args.layers.split(",") if x.strip()]
              if args.layers else None)
    run(pathlib.Path(args.act_dir), layers, read=args.read)


if __name__ == "__main__":
    main()
