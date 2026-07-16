# Reading and steering a model's internal correctness signal — methodology (one page)

**One idea underlies everything:** a concept is a *direction* $u\in\mathbb{R}^d$ in the model's
residual stream $h\in\mathbb{R}^d$. **Reading** it is a projection $u^\top h$; **writing** it is an
addition $h + \alpha u$. Every method below is one of those two moves.

### Setup
As the model runs, each token position carries a residual-stream vector; layers update it additively,
$h_{\ell+1}=h_\ell + f_\ell(h_\ell)$, and the output logits are $W_U h_L$ (unembedding
$W_U\in\mathbb{R}^{|V|\times d}$). We read at the **confidence decision token** — the position that
emits the digit of `Confidence: N`. Its local context is identical across records, so its layer-0
embedding is problem-independent (empirically decodes at chance): any deeper signal is *computed*.
Ground truth $y\in\{0,1\}$ (correct/incorrect) comes from an external grader, never shown to the model.

### Protocol (3 turns, blind-graded)
(1) prospective confidence → (2) attempt → (3) retrospective confidence. Grading is external, so a
post-failure confidence drop is *blind* self-assessment. Four readouts per attempt: **verbalized** (the
stated number), **P(True)** and answer log-prob (output distribution), **probe** (supervised internal),
**J-lens** (unsupervised internal).

### 1 · Probe — supervised read
Logistic regression on a standardized, PCA-reduced state $\tilde h$:
$$\Pr(y{=}1\mid h)=\sigma(w^\top\tilde h + b),\qquad \sigma(z)=\tfrac{1}{1+e^{-z}},$$
minimizing cross-entropy $\;\mathcal L=-\sum_i\big[y_i\log p_i+(1-y_i)\log(1-p_i)\big]$, so
$\nabla_w\mathcal L=\sum_i(p_i-y_i)\tilde h_i$ drives $w$ to separate correct from incorrect. The
readout is the scalar $s_{\text{probe}}=w^\top\tilde h$. The un-whitened estimate of the same axis is
the **difference of means** $\;v=\bar h_{\text{ok}}-\bar h_{\text{fail}}\;$ (logistic ≈ LDA:
$w\propto\Sigma^{-1}v$). Fit with **group-$k$-fold by question** (no sibling leakage), scored
**out-of-fold**, reported at a fixed depth $0.7L$ or a $[0.5L,0.9L]$ band mean (not $\max_\ell$).

### 2 · Scoring
$$\mathrm{AUROC}=\Pr(s_+>s_-)=\frac{1}{n_+n_-}\sum_{i\in+}\sum_{j\in-}\mathbf 1[s_i>s_j]$$
(prob. a random correct attempt outranks a random incorrect one; $0.5$ chance, $1$ perfect;
rank-based, so robust to class imbalance and to a saturated stated number). Calibration of the stated
number: $\;\mathrm{ECE}=\sum_b \tfrac{n_b}{N}\,|\,\mathrm{acc}(b)-\overline{\mathrm{conf}}(b)\,|$. CIs by
bootstrap (resampling questions for within-question metrics).

### 3 · Jacobian lens — unsupervised read
A mid-layer state isn't yet in output coordinates. Learn the transport as a per-layer linear map:
$$J_\ell=\mathbb E\!\left[\frac{\partial h_L}{\partial h_\ell}\right]\in\mathbb R^{d\times d},\qquad
\mathrm{lens}_\ell(h)=W_U\,(J_\ell h),$$
the input–output Jacobian averaged over generic text (no labels). For a word $w$ with unembedding row
$u_w$, its lens-logit collapses to a single **readout vector**
$$u_w^\top(J_\ell h)=\big(\underbrace{J_\ell^\top u_w}_{r_{w,\ell}}\big)^{\!\top}h,$$
so scoring a stored state is one dot product. Our signal is
$s_{\text{jlens}}=\big(\overline{r}_{\text{fail}}-\overline{r}_{\text{ok}}\big)^\top h$. Agreement with
the supervised probe refutes "the probe fit an artifact"; the lens also asks whether the signal enters
the *verbalizable* subspace at all.

### 4 · Steering — causal write
Applied at the decision token during turn 3 only (answer unchanged by construction).
$$\textbf{add: } h\mapsto h+\alpha\,v \qquad\qquad
\textbf{amplify: } h\mapsto h+(g-1)\big(\hat v^\top h-\mu\big)\hat v,\;\; \mu=\mathbb E[\hat v^\top h]$$
Add sweeps a coefficient $\alpha$ along the diff-of-means direction $v$ (dose–response); amplify scales
the model's *own* projection onto $\hat v=v/\lVert v\rVert$ by gain $g$ (identity at $g{=}1$), using **no
labels at intervention time**. Causal use is claimed when the stated number moves monotonically **and**
a norm-matched **random direction** does not.

### Controls (each result must survive all)
**read-site** layer-0 $\approx 0.5$ (content-neutral) · **difficulty** within-question AUROC on
mixed-outcome questions · **surface** incremental validity over answer length/shape · **leakage**
grouped-OOF splits · **causal** random-direction + answer-invariance controls · **grader validity**
extraction-failure rate + spot-checks.

---
**The identity to remember:** $\;\text{read}=u^\top h,\quad \text{write}=h+\alpha u.$ The probe learns
$u$ from labels; diff-of-means estimates it crudely; the Jacobian lens derives it label-free from the
model's own output geometry; steering adds it back to prove the model uses it. Same vector, four
operations. *(Assumptions: linear, single-token readouts; the averaged Jacobian under-sees
context-gated features — both bias toward misses, not false positives.)*
