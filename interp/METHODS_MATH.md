# Mathematical methods — the confidence / metacognition probe

*Formal companion to [PROGRESS_REPORT.md](PROGRESS_REPORT.md) (intuition) and
[LAB_NOTEBOOK.md](LAB_NOTEBOOK.md) (results). Every readout and intervention in the study is one of
four operations on a single object — the residual-stream vector. This document defines them
precisely; it is meant to seed a paper's Methods section.*

---

## 0. Setup and notation

A decoder LLM processes a token sequence through $L$ layers. At layer $\ell$ and token position $t$
the **residual stream** is a vector $h_\ell^{(t)} \in \mathbb{R}^d$ (our models: $d \in [4096, 5120]$,
$L \in [30, 64]$). Layers update it additively,

$$h_{\ell+1} = h_\ell + f_\ell(h_\ell),$$

so $h_\ell$ is a running sum that every layer reads and edits; the final logits are
$W_U\, h_L$ with unembedding matrix $W_U \in \mathbb{R}^{|V|\times d}$.

**Read site.** Unless noted, $h \equiv h_\ell^{(t^\*)}$ at the **confidence decision token** $t^\*$ —
the token position that generates the digit of `Confidence: N`. Its local context is identical across
records, so its layer-0 (embedding) content is independent of the problem; empirically the layer-0
probe is at chance (§2), certifying that any signal at deeper $\ell$ is *computed*, not lexical.

**Linear representation hypothesis.** The working assumption throughout: a concept corresponds to a
direction $u \in \mathbb{R}^d$; its presence in a state is the projection $u^\top h$, and it can be
written into a state by addition $h \mapsto h + \alpha u$. Reading is an inner product; writing is
vector addition. All four methods below are instances of this.

**Labels.** Each record carries a ground-truth correctness label $y \in \{0,1\}$ from an external
grader (geometry compiler / letter-match / `math_verify`), never shown to the model.

---

## 1. The linear probe (supervised read)

We estimate $\Pr(y{=}1\mid h)$ with $\ell_2$-regularized logistic regression on a standardized,
PCA-reduced state $\tilde h \in \mathbb{R}^{k}$ ($k=50$):

$$\Pr(y{=}1\mid h) = \sigma\!\big(w^\top \tilde h + b\big), \qquad \sigma(z)=\frac{1}{1+e^{-z}}.$$

Fitting minimizes cross-entropy

$$\mathcal{L}(w,b) = -\sum_i \Big[y_i \log p_i + (1-y_i)\log(1-p_i)\Big] + \tfrac{\lambda}{2}\lVert w\rVert^2,$$

with gradient $\nabla_w \mathcal{L} = \sum_i (p_i - y_i)\,\tilde h_i + \lambda w$. Gradient descent drives
$w$ toward the direction separating correct from incorrect states; the probe's scalar output is
$s_{\text{probe}} = w^\top \tilde h$. Mapped back through the PCA basis, $w$ is a **direction in
residual space** — the "am I correct?" axis this study is about.

**Baseline direction.** The un-whitened estimate is the class **difference of means**

$$v \;=\; \bar h_{\text{ok}} - \bar h_{\text{fail}},$$

used directly as the steering vector in §4. Logistic regression is approximately $v$ whitened by the
pooled covariance ($w \propto \Sigma^{-1} v$, LDA), so "probe direction" and "diff-of-means direction"
are the same object at different levels of conditioning.

**No leakage.** Train/test folds are grouped by **base question** (GroupKFold): the 5 sampled attempts
of a question never straddle the split, so the probe cannot memorize a question. All probe AUROCs are
**out-of-fold** (each record scored by a model that never saw it). Reported at a fixed relative depth
($0.7L$) or a mid-late band mean, *not* the best of $L$ layers (best-of-$L$ is optimistic by
multiple-comparison; §6).

**Difficulty control (within-question).** Cross-question AUROC conflates "knows which *questions* are
hard" with "knows whether *this attempt* worked." We isolate the latter: restrict to **mixed-outcome
questions** (both a pass and a fail among the 5 samples), compute AUROC *within* each such question, and
average. Difficulty is constant within a question, so a within-question AUROC $>0.5$ is genuine
per-attempt self-monitoring. (This is where P(True) collapses toward chance while the probe holds — the
study's central dissociation.)

---

## 2. Scoring readouts

Every reader — stated confidence, P(True), answer log-prob, probe, J-lens — emits a scalar $s$.

**AUROC** (threshold-free, imbalance-robust — essential since some cells are ~90% one class):

$$\mathrm{AUROC} = \Pr\big(s_{+} > s_{-}\big) = \frac{1}{n_+ n_-}\sum_{i\in+}\sum_{j\in-}\mathbf{1}[s_i>s_j],$$

the probability a random correct attempt outranks a random incorrect one (the Mann–Whitney statistic).
$0.5$ = chance, $1$ = perfect. Because it depends only on rank, a model that saturates its stated number
at 95 is scored fairly.

**Calibration (stated number only).** Expected Calibration Error over confidence bins $b$:

$$\mathrm{ECE} = \sum_b \frac{n_b}{N}\,\big|\,\mathrm{acc}(b) - \overline{\mathrm{conf}}(b)\,\big|,$$

the average gap between claimed confidence and realized accuracy. (Brier and reliability curves reported
alongside.) The steering result is an ECE collapse $0.31\to0.13$.

**Uncertainty.** 95% CIs by bootstrap over records ($10^3$ resamples); for within-question metrics we
resample *questions*, not records, to respect the grouping.

---

## 3. The Jacobian lens (unsupervised read)

**Motivation.** Decoding a mid-layer state with the output matrix directly (the *logit lens*,
$W_U h_\ell$) is biased: $h_\ell$ is not yet in final-layer coordinates. The Jacobian lens learns the
transport — how the final state responds to a perturbation of layer $\ell$ — as a per-layer linear map:

$$J_\ell \;=\; \mathbb{E}_{x,t}\!\left[\frac{\partial h_L^{(t')}}{\partial h_\ell^{(t)}}\right] \in \mathbb{R}^{d\times d},
\qquad \mathrm{lens}_\ell(h) = W_U\,(J_\ell\, h).$$

$J_\ell$ is the input–output Jacobian, **averaged over a text corpus** (positions $t$, future targets
$t'\!\ge t$, and prompts $x$). This is what the GPU "fit" computes: many backward passes accumulating the
expectation. Averaging trades exact per-input transport (the network is nonlinear) for a single reusable
linear map — the "typical" influence of a layer-$\ell$ direction on future outputs. Crucially the fit
uses **generic text and no labels**.

**Readout collapse.** For a single vocabulary item $w$ with unembedding row $u_w$, its lens-logit is

$$u_w^\top (J_\ell h) = \big(\underbrace{J_\ell^\top u_w}_{\textstyle r_{w,\ell}}\big)^{\!\top} h .$$

So each word reduces to **one readout vector** $r_{w,\ell}=J_\ell^\top u_w$, and scoring any stored state
is a dot product $r_{w,\ell}^\top h$ — computed offline. Our confidence signal is the failure-minus-success
disposition

$$s_{\text{jlens}} = \Big(\tfrac{1}{|F|}\!\sum_{w\in F} r_{w,\ell} - \tfrac{1}{|S|}\!\sum_{w\in S} r_{w,\ell}\Big)^{\!\top} h,$$

with $F=\{$wrong, error, mistake, …$\}$, $S=\{$correct, right, …$\}$. Because $J_\ell$ and $W_U$ never see
a label, agreement between $s_{\text{jlens}}$ and the supervised $s_{\text{probe}}$ refutes the
"probe fit a dataset artifact" objection, and lets us ask the *global-workspace* question: does the
correctness signal live in the **verbalizable** subspace this lens reads (§5 of the report)?

---

## 4. Steering (causal write)

Decodability ($w^\top h > 0$ separates classes) shows information is *present*. Causation requires
intervening. We add a direction at the decision token during turn-3 generation only (so the answer is
unchanged by construction — the answer-invariance control is structural).

**Add mode** — uniform dose–response along the diff-of-means direction $v$:

$$h \;\mapsto\; h + \alpha\, v, \qquad \alpha \in \{-16,\dots,16\}.$$

Causal use is claimed iff the stated confidence varies monotonically in $\alpha$ (dose–response) **and** a
random direction $r$ with $\lVert r\rVert=\lVert v\rVert$ produces no such trend (control). Coefficients
must be scaled to $\lVert h\rVert$: too-large $\alpha$ breaks generation (observed at $|\alpha|\ge 8$).

**Amplify mode** — magnify the model's *own* projection onto the unit direction $\hat v = v/\lVert v\rVert$,
relative to the corpus mean $\mu = \mathbb{E}[\hat v^\top h]$:

$$h \;\mapsto\; h + (g-1)\,\big(\hat v^\top h - \mu\big)\,\hat v, \qquad g \ge 0.$$

At $g=1$ this is the identity (exact no-op baseline). $g>1$ scales the correctness component *this*
record already computed — **using no labels at intervention time** (labels entered only in estimating
$\hat v$; the J-lens variant replaces $\hat v$ by $J_\ell^\top u_{\text{wrong}}$, removing labels
entirely). Result (Mistral × MATH): as $g:1\!\to\!2\!\to\!4$, stated confidence on *failed* answers
$80\to65\to43$ while *correct* answers hold at $\sim\!90$; $\mathrm{ECE}\,0.31\to0.13$; the random-direction
control is flat; dampening ($g<1$) increases overconfidence. Specificity (only failures move, only the
true direction works) rules out generic degradation.

---

## 5. One object, four operations

| operation | formula | direction comes from | question answered |
|---|---|---|---|
| probe (read) | $s = w^\top \tilde h$ | supervised labels | is correctness *present*? |
| diff-of-means | $v = \bar h_{\text{ok}}-\bar h_{\text{fail}}$ | class means | crude same direction |
| J-lens (read) | $s = (J_\ell^\top u_w)^\top h$ | model's output geometry, **no labels** | is it *verbalizable*? |
| steering (write) | $h \mapsto h + \alpha v$ / amplify | reuse $v$ or $J_\ell^\top u_w$ | does the model *use* it? |

The through-line: *a concept is a direction; reading is $u^\top h$, writing is $h+\alpha u$.* Everything
else is how $u$ is obtained and whether we read or write it.

---

## 6. Assumptions and honest limits

- **Linearity.** Both probe and lens assume the correctness feature is linearly accessible. A signal
  present only nonlinearly would be undercounted — a *null* J-lens result means "not in the *typical
  linear* verbalizable channel," not "absent."
- **Averaged Jacobian.** $J_\ell$ captures typical transport, diluting input-specific nonlinear routing;
  it under-sees content that only reaches output through contextual gates. Conservative for our claims
  (biases the lens toward misses, not false positives).
- **Layer selection.** Per-layer AUROC is honest (out-of-fold), but $\max_\ell$ over $L$ layers is
  optimistically biased. We report a fixed $0.7L$ layer and a $[0.5L,0.9L]$ band mean; the internal
  $\gg$ verbalized result survives both (15/16 cells, mean gap $+0.11$).
- **Read-site validity.** The layer-0-at-chance check is a *necessary* content-neutrality test, not
  sufficient; the "sentence-length" confound of the original entity-token read (layer-0 already 0.74–0.83)
  is the cautionary precedent that motivated the fixed decision-token site.
- **Grader validity.** All AUROCs inherit the grader's label noise; the `math_verify` fix corrected a
  systematic MATH false-negative that had biased every downstream statistic (see the deviations log).
- **Single seed** per (model, domain); CIs quantify item-sampling noise, not seed variance.
