# How AUROC is calculated (detailed note)

*Reviewed by Codex — tie handling corrected (see notes inline).*

Context: for each **cell** (one model × one benchmark), every attempt *i* gets a real-valued
**score** `s_i` from a readout (the verbalized confidence number, the probe's output, the lens
projection `r·h`, …) and a ground-truth **label** `y_i ∈ {0,1}` from the external grader
(1 = correct). Let the correct set be **P** with `n₊ = |P|`, the wrong set **N** with `n₋ = |N|`.
AUROC scores how well `s` separates P from N.

## Two equivalent definitions

**(1) Geometric — the trapezoidal area under the ROC curve.**
For a decision threshold `t`, define
- True-positive rate:  `TPR(t) = |{ i ∈ P : s_i > t }| / n₊`
- False-positive rate: `FPR(t) = |{ j ∈ N : s_j > t }| / n₋`

As `t` **decreases** from `+∞` to `−∞`, the point `(FPR(t), TPR(t))` traces the **ROC curve** from
`(0,0)` to `(1,1)`, and AUROC is the **trapezoidal area** under it. When several examples share a
score, the standard curve connects the before/after points of that tied block by a straight line —
the geometric version of giving ties half credit.

**(2) Probabilistic / rank form — what we actually compute.**
AUROC is the probability that a random correct attempt outscores a random wrong one, **with ties
split evenly**:

  `AUROC = Pr(s₊ > s₋) + ½·Pr(s₊ = s₋)`
        `= (1 / (n₊ n₋)) · Σ_{i∈P} Σ_{j∈N} [ 1(s_i > s_j) + ½·1(s_i = s_j) ]`

The ½-for-ties term is not cosmetic here: verbalized confidence bunches at values like 95, so ties
are common. This is the normalized **Mann–Whitney U** statistic (with average ranks for ties):
`AUROC = U / (n₊ n₋)`. Definitions (1) and (2) are provably equal.

## Interpretation
- `0.5` = chance-level **ranking** — a random correct/wrong pair is no more likely to be ordered
  right than wrong. (This is about ordering; a *non-monotone* score could still carry information
  yet score ≈ 0.5.)
- `1.0` = perfect — every correct attempt outranks every wrong one.
- `< 0.5` = the score is anti-correlated (negating it gives `1 − AUROC`).

## Why we use it
- **Threshold-free** — integrates over every cutoff, so no arbitrary "confident if ≥ 70" line.
- **Invariant to any *strictly* increasing transform of the scores** — only the *ordering* matters,
  so a bunched/saturated confidence scale doesn't distort it. ("Strictly" matters: a non-strict
  transform can collapse distinct scores into ties and change the value.)
- **Prevalence-invariant** — because it averages over correct/wrong *pairs*, a high base
  correctness rate can't mechanically inflate it (plain accuracy can be fooled that way). It can
  still be noisy when one class is small.
- **Measures discrimination, not calibration** — "does the score *separate* right from wrong," not
  "does 0.8 mean 80% correct." Calibration is a separate metric (ECE).

## How we compute it in practice
- `s_i`: the readout — verbalized `N`; P(True); probe `predict_proba`; lens projection `r·h`.
- `y_i`: the grader's pass/fail, external, never shown to the model.
- The probe's scores are **out-of-fold**: `cross_val_predict` with `GroupKFold` grouped by base
  question, so a question and its siblings never straddle train/test → no leakage.
- `sklearn.metrics.roc_auc_score(y, s)` (label 1 = positive; ties by average ranks). It is
  **undefined for a single-class cell** — those cells / bootstrap resamples return NaN and are skipped.
- Reported per cell; uncertainty via bootstrap resampling of questions.

## Worked micro-example
Correct scores `{.91, .80, .55}` (n₊=3), wrong scores `{.62, .30}` (n₋=2). All 3×2 = 6 pairs:
`.91>.62 ✓, .91>.30 ✓, .80>.62 ✓, .80>.30 ✓, .55<.62 ✗, .55>.30 ✓` → 5 wins, 0 ties, 1 loss →
`AUROC = 5/6 ≈ 0.83`.
