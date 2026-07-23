# Lab notebook — Metacognition in geometry construction

**The central write-up for the confidence/self-assessment sub-study.** Consolidates what
was scattered across `CONFIDENCE.md` (design/backstory), `METHODOLOGY.md` (general probing
protocol), and `RESULTS.md` (spatial-decodability). Append **dated entries** as the work
progresses; keep the *Verdict* and *Results table* current.

---

## Question
When a model writes a geometry construction, does its **residual stream encode whether that
construction is correct** — a genuine internal self-assessment — and *where*? And how does
that internal signal compare to the confidence the model **verbally states**?

## Ground truth & models
- **Task:** the model emits a RecipeDSL construction; the real pipeline grades it
  (`parse → validate → lower → compile → check`) → **binary ok/fail** (+ furthest stage).
  Exact, structured correctness labels — the rare clean part.
- **Models:** Qwen2.5-7B-Instruct (bf16) and GLM-4.7-Flash (30B-A3B MoE, bf16). Builds on
  the spatial-decodability probes (7B/32B) in `RESULTS.md`.

## Method (consolidated)
1. **Capture** (`capture.py`): generate the completion, then **one forward pass** over the
   realized `[prompt+completion]` ids with `output_hidden_states=True`; save the residual
   stream (fp16) at the kept token positions + metadata (grade, conf value/positions).
2. **Probe** (`probe.py`): per-layer `StandardScaler → PCA(≤100) → LogisticRegression`,
   **train/test split grouped by base prompt** (no leakage), token-identity baseline. One
   probe per layer → a decodability-vs-layer curve. Linear, to match how the model reads
   its own stream.
3. **Read site — the crux.** Reading at an **entity token** is confounded: its identity
   co-varies with correctness, so layer-0 (raw embeddings) alone separates pass/fail
   (0.74–0.83). Fix: read at a **fixed, content-neutral `Confidence:` slot** — specifically
   the **decision token** (the `:`/space that *generates* the number). There, layer-0 ≈ 0.5,
   so any deeper signal is genuinely *computed*.
4. **Two-turn elicitation** (`--confidence-followup`): a single-turn "…end with Confidence:N"
   **truncates** the construction JSON (esp. GLM), confounding correctness. So: generate the
   construction *cleanly* (turn 1), then elicit confidence in a *separate* turn (turn 2) and
   read the decision token there. (`--no-think` disables GLM's `<think>`.)
5. **Control cascade** (each result must survive all):
   - **difficulty** — measured *within-prompt* (same prompt, pass vs fail); prompt base-rate
     AUROC quantifies the confound.
   - **surface / #ops** — `confidence_vs_difficulty.py`: layer-0 embedding + output-shape
     (length, #ops, #id-mentions) baselines the signal must beat.
   - **#ops incremental validity** — `incremental_ops.py`: does adding the activation improve
     within-prompt prediction *over #ops alone*? (The decisive test.)
   - **verbalized vs internal** — `verbalized_vs_internal.py`: does the probe beat the stated
     number at predicting correctness?

Metric: **AUROC** (robust to the heavy pass/fail imbalance), cross-prompt and within-prompt.

---

## Verdict (as of 2026-07-07)
**"Knows more than it says" is robust and architecture-general; per-attempt self-monitoring
needs the right task difficulty; and the internal↔verbalized gap is largest where errors are silent.**
- **Internal ≫ verbalized in 15/16 cells** across 4 models × 4 domains (geometry, MMLU-Pro,
  GSM8K, MATH). Honest **band-mean** readout (mean over the 0.5–0.9 depth band, *not* the
  cherry-picked best layer): mean gap **+0.11**; robust to layer selection.
- **Largest on MATH — a "knowing vs saying" gap.** Verbalized is near-useless (0.52–0.73,
  post < pre) while internal is the strongest domain (band 0.76–0.90, best up to 0.96): the model
  silently knows its `\boxed{}` answer is wrong but reports high confidence.
- **Read-site fix holds** — content-neutral `Confidence:` decision token gives layer-0 AUROC
  ≈ 0.39 (≪ the 0.76–0.90 deep signal), so the signal is genuinely computed mid/late.
- **Per-attempt self-monitoring (within-question, difficulty fixed) is real but power-limited** —
  it shows up where a model has enough mixed-outcome attempts (GLM at ~50% pass: **0.55–0.71**).
  The earlier "Qwen3.6 within-question standout" was thin-data (3 mixed prompts) and does **not**
  replicate on better-powered QA.
- **Small-model backstory (still true):** at 7B computed self-assessment beyond output-shape is
  marginal (#ops-incremental +0.02) vs clear at 30B (+0.10) — a scale *gradient*.
- **Two corrections in flight:** a QA confidence-prompt wording bug (geometry text leaked into the
  QA confidence turns) and a MATH grader bug (fixed offline). Corrected re-run staged (tasks
  #11/#12); the bug-free no-elicitation PRE read already supports "internal > verbalized," and the
  bug degrades rather than inflates, so the headline is expected to hold.

## Results table (within-prompt AUROC unless noted; decision-site read for two-turn)
| | Qwen-7B (single) | Qwen-7B (two-turn) | GLM-Flash (two-turn) |
|---|---|---|---|
| dataset | `conf7b` (657) | `qwen7_2turn` (720) | `glm7_2turn` (720) |
| pass rate | 14% | 13% | 21% |
| mixed-outcome prompts | 21 | 24 | 44 |
| layer-0 (read-site check) | 0.48 | 0.50 | 0.50 |
| difficulty (baseline) | 0.92 | 0.90 | 0.85 |
| **verbalized** | 0.53 | 0.52 | **0.72** |
| internal (probe) | 0.70 | 0.79 | 0.72–0.81 |
| surface (#ops) | 0.86 | 0.84 | 0.69 |
| **#ops increment** | **−0.15** | **+0.02** | **+0.10** |

---

## Lab-book entries

### 2026-07-01 — Qwen-7B, single-turn (`conf7b`, 657 records, digit-site read)
First fixed-slot run. Read-site fix works (layer-0 within-prompt **0.48** vs 0.74–0.83 at
the entity token). Verbalized confidence useless (**0.53**, collapsed at ~99, right 14%).
Internal > verbalized (**0.70** vs 0.53). But #ops-incremental **−0.15** → the apparent
signal is entirely output-shape; **no computed self-assessment** at 7B (single-turn).

### 2026-07-02 — GLM-4.7-Flash, two-turn (`glm7_2turn`, 720 records, decision-site)
Two-turn required: single-turn truncated GLM's verbose JSON (0/4 success, 50% unbalanced
braces). Two-turn clean (25% success, 0/12 unbalanced). Read-site fix holds (layer-0 **0.50**).
Verbalized **calibrated (0.72)**, mean 89, separates ok 95/fail 88. Internal **0.81** >
verbalized. **#ops-incremental +0.10** (best L47; +0.00 at layer 0 → +0.10 mid-late, the
computed signature; activation and #ops complementary) → **genuine computed self-assessment.**

### 2026-07-03 — Qwen-7B, two-turn (`qwen7_2turn`, 720 records, decision-site) — the clean comparison
Same protocol as GLM (two-turn, decision-site) → apples-to-apples. Read-site fix holds
(layer-0 **0.50**). Verbalized **still collapsed (0.52**, mean 99.1) — the two-turn setup did
**not** rescue Qwen's words, so GLM's calibration is a scale effect, not method.
#ops-incremental **+0.02** (borderline, doesn't clear) vs GLM's +0.10 — but *much* better than
single-turn's −0.15, so part of the original gap was read-site/elicitation. → the scale story
survives but is a **gradient**, and was **overstated** by the single-turn comparison.

### 2026-07-05 — 3-turn TEMPORAL confidence across 4 modern models (geometry)

A major extension: a **3-turn protocol** — pre-task confidence → produce the construction →
post-task confidence — run on **four current ~24–30B models spanning architectures**, all graded
by the render-free checker (grade never shown to the model). 91 GeoGenBench prompts × 4 samples
= 364 records/model. Pre-registered plan: [QA_STUDY_PLAN.md](QA_STUDY_PLAN.md). Capture:
`capture_temporal.py` (VLM-aware load); analysis: `analysis/confidence_temporal.py` (bootstrap CIs,
surface-length control). Reads: content-neutral `Confidence:` decision token (pre & post) + the
no-elicitation last-prompt token.

| geometry, 3-turn | Qwen3.6-27B (hybrid-Mamba) | GLM-4.7-Flash (MoE) | Mistral-Small-24B (dense) | Gemma-4-26B-A4B (MoE-VLM) |
|---|---|---|---|---|
| pass rate | 39% | 24% | 21% | 22% |
| PRE-conf AUROC | 0.57 | 0.62 | 0.52 | 0.58 |
| **POST-conf AUROC** | **0.70** | 0.66 | 0.66 | 0.66 |
| self-correction Δ(fail) / Δ(ok) | **−27** / −5 | −9 / −2 | −5 / +5 | −13 / −5 |
| downward-revision → fail AUROC | 0.68 | 0.63 | 0.70 | 0.64 |
| internal probe (post, best layer) | 0.83 | 0.75 | 0.84 | 0.75 |
| internal > verbalized? | ✅ | ✅ | ✅ | ✅ |
| **within-question post** (difficulty fixed) | **0.68** | 0.55 | 0.45 | 0.53 |

**Finding 1 — the phenomena are architecture-general.** All four (hybrid-Mamba / MoE / dense /
MoE-VLM) show **post > pre** calibration, **internal > verbalized** ("knows more than it says"),
and **blind self-correction** — confidence drops more on failures with the grade never revealed
(grading is external). Bootstrap CIs are non-overlapping where it matters (e.g. Qwen PRE 0.57
[0.53, 0.61] vs POST 0.70 [0.65, 0.75]); confidence clears the surface-length baseline (~0.40) on all.

**Finding 2 — genuine per-attempt self-monitoring is a Qwen3.6 standout.** Only Qwen3.6 (**0.68**)
tracks *this attempt's* correctness at fixed difficulty (within-question). GLM / Gemma-4 / Mistral
(0.45–0.55 ≈ chance) calibrate mostly on **difficulty** (which problem is hard), not on whether a
*particular* attempt is right. So cross-problem calibration is universal; **per-attempt
metacognition is not** — it separates Qwen3.6 from the pack.

> **[Superseded 2026-07-07]** This Qwen3.6 "standout" does **not** hold up. It rests on very thin
> data — the current `qwen36_temporal` is only n=77 with **3** mixed-outcome prompts — and on
> better-powered QA, Qwen3.6's within-question is 0.42–0.53 (unremarkable). **GLM** (at ~50% pass,
> 73–118 mixed prompts/cell) is the real within-question performer (0.55–0.71). Full-n Qwen3.6
> geometry re-capture is pending (task #12). See the 2026-07-07 entry.

**Caveats.** High internal *PRE* reads on some models (Mistral 0.88 @ L20, Gemma-4 0.70 @ L2)
largely reflect **difficulty decodable from the prompt**, not metacognition — hence within-question
is the metric for the "genuine self-monitoring" claim. Single dataset seed; within-question data is
thin (21–42 mixed-outcome prompts). Gemma-4 needed `--max-new-tokens 2560` (its verbose pretty-printed
JSON truncated at 1024 → false parse failures).

**Next:** the same 3-turn protocol on QA benchmarks (MMLU / MedQA / GSM8K) to test **cross-domain**
generalization — pilot (Gemma-4 × MedQA) in progress.

### 2026-07-07 — 3-turn TEMPORAL confidence on QA (4 models × MMLU-Pro/GSM8K/MATH) + rigor pass

Cross-domain extension: same 4 models × {MMLU-Pro, GSM8K, MATH}, n=250 × 2 samples = 500
records/cell (12 cells). Capture `capture_qa.py` (task adapters in `tasks_qa.py`); grading =
letter-match (MC) / numeric (GSM8K) / symbolic-equivalence (MATH). Same content-neutral
`Confidence:` decision-token reads. Aggregated + rigor-corrected by `analysis/matrix_report.py`.

**POST-confidence AUROC — verbalized → internal (honest band-mean over 0.5–0.9 depth), (pass rate):**
| | MMLU-Pro | GSM8K | MATH |
|---|---|---|---|
| Qwen3.6-27B | 0.67→**0.84** (.78) | 0.59→0.77 (.94) | 0.66→**0.90** (.85) |
| GLM-4.7-Flash | 0.67→0.77 (.50) | 0.56→**0.85** (.45) | 0.66→0.76 (.44) |
| Mistral-24B | 0.69→0.78 (.68) | 0.57→0.63 (.90) | 0.73→0.80 (.67) |
| Gemma-4-26B | 0.72→0.76 (.84) | 0.51→0.63 (.95) | 0.52→**0.78** (.92) |

**Finding 1 — "internal > verbalized" is universal and robust to layer selection.** Internal
band-mean beats verbalized POST in **15/16 cells** (incl. geometry), mean gap **+0.11**. Best-layer
was optimistic (inflates ~+0.05–0.13) but the band-mean still clears, so this is not a
multiple-comparison artifact. Read-site control passes: POST layer-0 AUROC mean **0.39** (≪ 0.76–0.90 deep).

**Finding 2 — MATH is a "knowing vs saying" gap, the largest of any domain (+0.17 mean).**
Verbalized on MATH is near-useless (0.52–0.73, and post < pre), yet internal is the *strongest*
domain (band 0.76–0.90; best up to **0.96**, Qwen3.6). The model silently knows whether its
`\boxed{}` answer is right almost perfectly but doesn't say so — the gap is largest exactly where a
wrong answer looks as clean as a right one. Internal POST > PRE on MATH too, so the "MATH
self-assessment inverts" seen in the *verbalized* numbers is a verbalization failure, not a
representational one.

**Finding 3 — per-attempt self-monitoring needs the right difficulty; GLM supplies it.** GLM sits
at ~50% pass → **73–118 mixed-outcome prompts/cell** (vs 2–35 for the others) → within-question
AUROC **0.55–0.71** (difficulty held fixed). Genuine per-attempt metacognition *is* present on QA;
you need a model failing often enough to measure it.

**Correction to 2026-07-05 Finding 2** (noted inline above): the Qwen3.6 within-question "standout"
does not replicate; GLM is the real performer; Qwen3.6 geometry re-capture pending (task #12).

**Two grading/prompt issues (both material, both handled):**
- *MATH grader* — the string-normalize grader false-negatived formatting-equivalent answers
  (`\frac{a}{b}` vs `a/b`, `\$`, decimal↔fraction), under-counting pass and polluting "failures".
  Fixed with **`math_verify`** offline (`analysis/regrade_math.py`, re-grades from stored
  completions — no GPU): rescued **5–9%/model, 0 demoted**. Pass rates above are post-fix.
- *QA confidence-prompt bug* — `capture_qa.py` reused the **geometry-worded** confidence prompts
  ("produce a correct, valid **construction**" / "**geometrically correct and valid**") on QA
  confidence turns 1 & 3 (turn-2 answers were correctly task-worded). So the QA internal
  POST/elicited-PRE reads sit on a mildly nonsensical prompt. **Mitigations:** the *no-elicitation*
  PRE read (`prompt_dtoken`) is bug-free and still beats verbalized PRE (e.g. Mistral geometry 0.88
  vs 0.52); the odd wording would *degrade*, not inflate. Corrected code (QA-worded prompts +
  per-turn thinking) is staged in `rerun_driver.sh`; clean re-run tracked as **task #11**.

**Caveats.** POST/elicited-PRE reads await the corrected re-run. Best-layer AUROC is optimistic —
use band-mean. Single dataset seed. GSM8K is ceiling'd for Gemma-4/Qwen3.6/Mistral (90–95%, low
signal) but not GLM (45%). Per-turn thinking was global-off (`--no-think`) on Qwen3.6/GLM here, so
those two answered below peak — the re-run fixes this too.

### 2026-07-07 — Expert review (feedback) + tiered forward plan

Full self-audit with the mech-interp-reviewer hat on. **Strengths:** the control discipline
(read-site, within-question, grouped OOF, grader validation, pre-registration + §10 deviations log,
band-mean readout, self-caught bugs + one retraction); 4-architecture × 4-domain breadth; the MATH
knowing–saying gap as a crisp headline. **Weaknesses, ranked by threat:**

1. **No causal evidence — the top gap.** Probing ≠ use. `patch_confidence.py` (RQ8: dose-response
   steering at the decision token, random-direction control, log-prob-diff readout) is built but was
   **never run to completion** (no results file). Until steering moves behavior, this is a
   descriptive probing study.
2. **Missing output-distribution baseline.** Kadavath et al. 2022: token-level probabilities are
   calibrated where words aren't. If answer-logprob / P(True) matches the internal probe,
   "internal ≫ verbalized" is already known. Logits aren't stored → the re-run must capture
   **answer-token logprobs + a P(True) turn**. The novelty test: does the *residual stream* beat the
   *output distribution*?
3. **Surface-incremental control never run on the matrix probes** — and several POST curves peak
   *early* (Gemma-4 MATH best L5/30, Qwen3.6 MATH L11/64), hinting the probe may partly read surface
   features of the in-context answer. Offline-fixable.
4. **Layer-0 = 0.39 is not "≈ chance"** — a systematically reversed signal. Diagnose (fold-pooling
   artifact vs real leak); don't hand-wave.
5. **GLM's within-question "win" is partly a power artifact** (50% pass ⇒ 30× more mixed-outcome
   prompts than Gemma-4). Frame as "detectable when powered"; cross-model comparison needs
   difficulty-matched items.
6. **Positioning.** Prior art: Kadavath (P(True)/P(IK)), Azaria & Mitchell (internal truthfulness),
   Burns (CCS), Marks & Tegmark (truth directions), semantic entropy (Farquhar/Kuhn), RepE (Zou),
   verbalized-calibration (Lin, Tian), introspection (Binder; Anthropic 2025). **What's ours:**
   temporal pre/post within *own attempts*; **blind** (no-feedback) confidence updating; the
   knowing–saying dissociation *by domain*; own-output correctness (not truth of a given statement)
   at a content-neutral read site, ×4 architectures.

   **[Added 2026-07-10] Anthropic's Global Workspace / Jacobian-lens** (*"Verbalizable
   Representations Form a Global Workspace in Language Models"*, 2026;
   github.com/anthropics/jacobian-lens) is the closest neighboring result: their J-lens finds
   "bug detection before identification" — knowing-without-saying, in their domain. Two uses for
   us (task #16): (a) **mechanistic hypothesis for WHY verbalization fails** — information is
   reportable iff it enters the workspace; prediction: on MATH failures the correctness signal
   exists (probe) but does not enter J-space, hence unreportable; (b) **a fourth, zero-shot
   readout leg** — fit the lens once per model (GPU), then score failure-words offline on our
   *saved* decision-token activations (lens = unembed(J_l·h)); if an unsupervised readout matches
   the supervised probe, probe-overfitting critiques die. Bonus: J_lᵀ·W_U["wrong"] is a
   **label-free steering direction** for the gap-closing demo.

**The groundbreaking path:** close the knowing–saying gap **causally** — steer the probe direction
at the confidence decision token on MATH and show verbalized calibration jumps (target 0.66→~0.85)
*without changing the answers* (specificity control), dose-responsive, random-direction-controlled,
across the 4 architectures. Multipliers: (a) a **domain-general correctness direction** (cross-domain
probe transfer — zero GPU, data in hand); (b) **probe > logprob** (needs the re-run capture).

**Forward plan (tiers) — the standing to-do:**
- **Tier 1 — offline now, no GPU (`analysis/tier1_review.py`):** ① cross-domain + cross-site probe
  transfer at a fixed 0.7-depth layer + direction cosines; ② surface-incremental control on the
  matrix probes (+ early-layer diagnosis); ③ pre/post decomposition (residualize post-scores on
  pre-scores → attempt-specific component) + within-question *internal* AUROC; ④ internal-probe
  selective prediction vs verbalized; ⑤ paired bootstrap per cell + the layer-0 pooled-vs-per-fold
  diagnosis.
- **Tier 2 — corrected re-run additions (tasks #11–#13):** answer-token logprobs + P(True) turn;
  5–8 samples/question on MMLU-Pro + MATH (drop ceiling'd GSM8K); GPQA-Diamond; consider one
  **base-model** arm (is the knowing–saying gap an RLHF artifact?).
- **Tier 3 — causal session (GPU):** run RQ8 steering on the 27B models at the decision token
  (dose-response, random-direction + answer-invariance controls); the MATH gap-closing demo; if it
  works, one mechanism sketch (attention attribution into the decision token).

**Tier-1 RESULTS (run same day; `analysis/tier1_review.py`, full dump
`tier1_review.json` + scratchpad/tier1_full.txt; fixed 0.7-depth layer throughout):**

1. **TRANSFER — the correctness direction is largely domain-general.** Off-diagonal/diagonal
   AUROC retention ≈ 87–90% (Qwen3.6 0.71/0.81, GLM 0.66/0.77, Mistral 0.68/0.75; Gemma-4 79%).
   Within QA sometimes lossless (Qwen3.6 MMLU-Pro→MATH 0.863 vs in-domain 0.910; Gemma-4
   MMLU-Pro→MATH 0.792 vs 0.797); QA↔QA direction cosines 0.42–0.85. Geometry is partially
   special (lower cosines); Gemma-4 geometry→QA *anti-transfers* (0.31–0.39) while QA→geometry
   works (~0.70) — geometry-trained probes latch onto task-specific features, QA-trained probes
   find the general direction.
2. **Within-question INTERNAL (new — previously verbalized-only): genuine per-attempt
   self-monitoring, representationally.** Powered cells: GLM×GSM8K **0.917** (n=108 mixed) vs
   verbalized 0.565; GLM×MATH 0.805 (n=118) vs 0.631; GLM×MMLU-Pro 0.712 (n=73); Qwen3.6×MATH
   1.00 (n=17). Decomposition: residualizing post-scores on pre-scores leaves AUROC 0.59–0.87 →
   the post signal is attempt-specific, **not re-expressed difficulty**; cross-site post→pre
   transfer is weak (0.39–0.67) → the post direction is largely distinct from the pre/difficulty
   direction.
3. **Layer-0 = 0.39 RESOLVED — a fold-pooling artifact, 16/16 cells.** Per-fold layer-0 AUROC is
   exactly **0.500 in every cell** (pooling OOF scores across folds with different offsets drags
   the pooled number off 0.5); deep layers unaffected (per-fold ≈ pooled). Read-site control
   passes cleanly.
4. **Surface-incremental control passes: 15/16 cells**, mean increment **+0.22** over
   surface-only. Exception: GLM geometry *across*-question (surface 0.73 ≈ act 0.71) — the old
   within-prompt +0.10 (incremental_ops) remains the relevant GLM-geometry number.
5. **Paired bootstrap (internal − verbalized), fixed layer:** significant-positive **10/16**,
   positive 14/16, never significantly negative. **Selective prediction:** internal abstention ≫
   verbalized where verbalized fails — GLM×GSM8K cov40%: **0.81 vs 0.43** (verbalized abstention
   there is worse than random).
6. **New caveat — the MATH early-layer channel.** On MATH, the 0.15-depth layer matches/beats
   0.7-depth (Qwen3.6 0.953, Gemma-4 0.907), NOT explained by the crude surface features; the
   boxed answer is adjacent to the read site, so an answer-*lexical* channel (weird-looking
   answers are more often wrong) may contribute — and within-question cannot fully exclude it
   (attempts differ exactly in answer text). **The Tier-3 steering test is the discriminator.**
   (QA surface features are also right-censored: stored answers truncate at 200 chars.)

### 2026-07-10 — Talk narrative draft (motivation / setup / strategy) — seeds the results deck

*Draft intro for the HTML results deck; edit freely. The three sections below are the first
three slide groups.*

**MOTIVATION — do models know when they're wrong?**
Language models fail confidently. Ask one for its confidence and you'll usually hear "95" —
right or wrong. The deployment question is whether that's the whole story: a model that *errs*
is a fact of life, but a model that errs *and knows it* is deployable — it can abstain, retry,
or escalate exactly when needed. So the question splits in two:
1. **Do models know?** Is there an internal signal of "this answer is wrong" at all?
2. **Do they say it?** If the knowledge exists but the stated confidence doesn't carry it,
   that gap — *knowing vs saying* — is both recoverable signal (a free safety margin nobody
   is using) and a scientific finding about machine introspection.
Psychology makes a distinction we borrow: *prospective* metacognition ("will I get this
right?" — feeling-of-knowing, before attempting) vs *retrospective* ("did I get it right?").
Nobody had measured both, cleanly, inside open LLMs.
Origin story (one slide): this grew out of a geometry-diagram pipeline whose compiler gives
**exact, machine-checkable correctness** — the rare ground-truth label you can fully trust.
That grader seeded the probe program; we then generalized to standard benchmarks.

**SETUP — the 3-turn temporal protocol.**
For each problem, three turns: ① *"how confident are you that you'll get this right?"* —
answer with one line, `Confidence: N` ② solve the problem (reasoning allowed here, and only
here) ③ *"how confident are you that your answer is correct?"*. Grading is **external and
never shown to the model** — so any confidence drop after a failure is *blind*
self-assessment, not feedback.
What we record per attempt: the two stated numbers; the **residual stream at a
content-neutral read site** (the token that *generates* the confidence number — same local
context every time, so layer-0 decodes at chance and anything deeper is computed);
the model's own **output-distribution confidence** (P(True), answer log-probs); and the
external grade. Scale: **4 architectures** (hybrid-Mamba, MoE, dense, MoE-VLM) × **4 domains**
(geometry construction, MMLU-Pro, MATH, GPQA) × 750 attempts/cell, 5 samples per question.

**STRATEGY — a ladder of increasingly hard-to-fake claims.**
Each rung kills a specific deflationary explanation:
1. *Decodable* — a linear probe reads correctness from the residual stream. (Could be anything.)
2. *Beyond difficulty* — holds **within-question**: same question, multiple attempts, the probe
   separates the successful ones. Kills "it just knows which questions are hard."
3. *Beyond surface* — survives answer-length/shape controls and a content-neutral read site.
   Kills "it's reading output artifacts."
4. *Beyond the output distribution* — the race vs **P(True)** and answer log-probs
   (Kadavath-style). Kills "the logits already tell you this" — the novelty-deciding rung.
5. *Causal* — steering the direction moves what the model *says* (dose-response, random-direction
   and answer-invariance controls); amplifying its own signal should close the knowing–saying
   gap with no labels. Kills "decodable but epiphenomenal."
6. *Mechanistic* (opening) — does the correctness signal enter the **global workspace**
   (J-lens)? A candidate answer to *why* verbalization fails.
Two process principles worth a slide: **metacognition is failure-hungry** (benchmarks chosen
by the model's error rate, not popularity — ceiling'd GSM8K/MedQA dropped), and **the controls
found real bugs** (grader false-negatives, a prompt-wording leak → caught, fixed, re-run —
the deviations log is a feature, not an embarrassment).

---

### 2026-07-15 — Independent code review (Codex, read-only) + fixes; J-lens code debugged offline

**Codex review of the result-critical scripts — 4 MODERATE findings, no CRITICAL, all logged:**
1. *(tier1 transfer)* test domain was re-standardized with a fresh scaler → coordinate mismatch
   with the A-trained probe. **FIXED** (transform B with training scaler `sA`). Exploratory only.
2. *(tier1 cross-site)* PRE scaler fit on all groups incl. held-out → mild transductive leak.
   **FIXED** (fit on train groups per fold).
3. *(steer_confidence, amplify)* the random-direction control is **not norm-matched to the realized
   perturbation** — amplify scales `|proj−μ|`, and the correctness direction has larger projection
   variance than a random one, so "steer" gets bigger nudges than "random." ⚠️ **The amplify
   "random-flat" control is weaker than stated.** NOT offline-fixable — needs a re-run with a
   magnitude-matched random control. **Mitigation:** the *add-mode* result used a properly
   norm-matched random control and also showed steer≫random, so causality is not unsupported; but
   the amplify control must be redone. Logged as a known limitation for the causal claim.
4. *(make_plots)* probe vs verbalized/P(True) computed on different non-NaN subsets → not
   same-record. **FIXED** (common mask). Recompute changed the headline by <0.001 (parse failures
   were random) — internal≫verbalized holds identically; a follow-on mask over-restriction that
   dropped geometry from fig1 was corrected (probe-vs-verbalized needs only those two; P(True)
   mask applies to fig3 only). Verdict: the review found **no result-inverting bug**.

**J-lens code debugged end-to-end offline (no GPU), root-causing the earlier crashes:** the arm
had never produced a readout for purely operational reasons. Fixed in `jlens_fit.py`: (a) corpus
bug (`Salesforce/wikitext` + task-corpus fallback); (b) `target_layer` out-of-range → use default;
(c) prompts must exceed `skip_first`; (d) stale-checkpoint resume-param mismatch (confirms
`resume=True` works — a killed fit *can* resume); (e) `--source-layers` fits only the read layer(s)
(~L× faster: 39 s vs a 30 h all-layer fit on a 0.5B CPU probe); (f) the real bug — the lens stores
`lens.jacobians` as a **dict {source_layer: [d,d]}**, not a stacked tensor, so `locate_J` found
nothing; extraction rewritten to read the dict; (g) loader order fixed (`.load()` works locally,
`from_pretrained` hangs on a local path). Orientation **confirmed** via probe2: `W_U(J·h)` matches
the package's `apply` (transpose gives pure garbage), so the readout `r_w = Jᵀu_w` is correct. The
**self-validation gate works** — it refused to save a degenerate 6-prompt toy lens (3/10 overlap).
A 60-prompt confirm-fit is running to show the gate passes on a non-degenerate lens. Net: J-lens is
**code-ready and turnkey** for the next GPU box; only the actual per-model fits remain (GPU).

## Caveats & open questions
- **Single-seed** point estimates; thin within-prompt data (21–44 mixed-outcome prompts).
- Linear probes at a **single token**; a non-linear / multi-token readout could differ.
- Only **two model sizes** — to trace the gradient, add intermediate sizes (e.g. 14B) and
  the 355B flagship (needs a multi-GPU node; see `CONFIDENCE.md`).
- **Causal** test not yet run — patch the confidence direction (`patch.py`) to move from
  "decodable" to "the model uses it."
- Multi-seed error bars + a #ops-matched analysis would firm up the +0.02 vs +0.10 gap.

## Reproduce
Capture (GPU; 24 GB fits 7B, 96 GB for GLM-Flash bf16; ~150 GB disk for GLM):
```bash
python interp/capture.py --device cuda --model <hf-id> --n 90 --samples 8 \
    --few-shot relevant:4 --keep-positions entities --confidence-followup \
    [--no-think for GLM] --out-dir interp/activations/<run>
```
Analyze (CPU, offline, on the pulled data):
```bash
python interp/probe.py --act-dir interp/activations/<run> --labeler correctness_conf
python interp/analysis/confidence_vs_difficulty.py --act-dir <run> --read conf
python interp/analysis/verbalized_vs_internal.py   --act-dir <run>
python interp/analysis/incremental_ops.py          --act-dir <run>
```

## Data & code index
- **Datasets** (local `interp/activations/`, gitignored): 7B/GLM scale study `conf7b`,
  `qwen7_2turn`, `glm7_2turn`; geometry 3-turn `{gemma4,qwen36,glm,mistral}_temporal`
  (qwen36 only n=77 → re-capture task #12); QA matrix `mtx_{gemma4,qwen36,glm,mistral}_{mmlu_pro,gsm8k,math}`
  (12 cells, MATH re-graded); pilots `gemma4_{medqa,mmlupro}`.
- **Code:** `confidence.py`, `capture.py` / `capture_temporal.py` (geometry 3-turn) /
  `capture_qa.py` (QA 3-turn) with `--no-think` / `--per-turn-think`, `tasks_qa.py` (per-benchmark
  load/prompt/validated-grade), `probe.py` (`correctness*` labelers), `analysis/{confidence_temporal,
  matrix_report,regrade_math,confidence_vs_difficulty,verbalized_vs_internal,incremental_ops}.py`,
  `rerun_driver.sh` (corrected re-run), tests `test_confidence.py`.
- **Related docs:** `CONFIDENCE.md` (design + read-site backstory), `METHODOLOGY.md`
  (general probing protocol), `RESULTS.md` (spatial decodability, 7B/32B).

---

## 2026-07-22 — Team deck rebuilt: visual-first, RP-branded, 25 slides (presentation-ready)

**What exists now.** `slides/metacognition_progress.html` is the team presentation
("Do models know when they're wrong?"), fully reworked across several sessions with Claude Code:

- **Structure (25 slides):** dark title (says-vs-thinks speech/thought bubbles) → audience quiz
  ("Spot the wrong answer": 3×4 perimeter ✓14 vs octagon diagonals ✗28, real answer 20) →
  bluffing-vs-clueless → "we can just look" → **BLUF slide** (It knows / You can read it /
  Gauge, not wheel) → mech-interp 101 ×2 (residual stream, read-then-poke) → **method up-close ×3**
  (probe + guardrails, J-lens "phrasebook", steering + 3 controls) → testbeds → 3-turn protocol →
  verbatim prompts ×2 → read-site + layer curve → results ×7 (fig1 AUROC eq, gap-by-domain,
  within-question, lens-agrees, dense-only table, smear, steering) → verdict cards → open questions.
- **Numbers were re-audited against `interp/activations/plot_cache.json`** — deck + script now say
  probe wins **12/16** cells (1 tie; probe 0.57–0.95 vs stated 0.54–0.87; MATH +0.20, geometry
  +0.02; within-question GLM·MATH 0.89 vs P(True) 0.48). The old "0.69–0.96 vs 0.51–0.73 /
  beats every time" was stale (best-layer era) — don't reintroduce it.
- **Brand:** Renaissance Philanthropy palette (coral #F87248, ink #131318, muted #737382) +
  embedded subset webfonts (`slides/fonts/*.woff`: Manrope + Newsreader, variable, ~118 KB).
- **Figures:** `interp/analysis/make_plots.py` gained a deck-SVG path (`fig*_deck.svg`,
  transparent, no titles, RP palette) — regenerates offline from `plot_cache.json`. The five SVGs
  are force-added in `interp/figures/` (dir is gitignored).
- **Controls:** → reveals fragments / advances · ← back · `#N` deep-links (fragments auto-reveal) ·
  **N toggles hidden speaker notes** — full presenter-voice narration embedded per slide
  (`<aside class="notes">`). `slides/metacognition_SPEAKER_SCRIPT.md` = the deeper layer
  (staging, anticipated Q&A, numbers cheat-sheet).

**Published artifact (private, updated in-place all along):**
https://claude.ai/code/artifact/f2c31891-529f-4fd8-9d23-69c16592ff1b

**To rebuild/republish the self-contained copy** (fonts + figures inlined as data URIs — the repo
HTML references them as files): ask Claude Code to "re-inline and republish the deck to the same
artifact URL", or replicate: base64-inline `slides/fonts/*.woff` into the `@font-face` urls and
`interp/figures/fig[1-5]_deck.svg` into the `img src` refs, then publish the single file.

**2026-07-22 substance pass:** tone de-cheeked ("all you need", "Receipts", "kill it" etc. removed);
speaker notes substantially expanded per slide from `METHODS_MATH.md` (logistic-regression/PCA detail,
GroupKFold out-of-fold, fixed-0.7L rationale, Jacobian definition + averaged-map conservatism, amplify-gain
no-op baseline + assessment-turn-only injection, AUROC rank/imbalance properties, within-question bootstrap,
read-site 0.74-layer-0 precedent, ECE 0.31→0.13); slides gained one technical line each (update equation,
read/write equations, probe internals, J-lens formal line, 5× sampling, dampening/ECE numbers). Slide
heights re-checked ≤ pre-existing tolerance. Artifact republished (label `substance-pass`).

**Same day, two more revisions (deck now 26 slides):** slide 5 reworked from "We looked. Here's
what we found." to direct findings-with-evidence ("Models track their own correctness — better than
they report it"; cards carry 0.95 AUROC / 12-of-16, lens 0.76–0.88, 80→43 + ECE halved). New
**slide 11 — methodology roster**: 5-model table (Mistral-Small-24B dense · Qwen3.6-27B hybrid Mamba ·
GLM-4.7-Flash MoE · Gemma-4-26B MoE/VLM · Qwen2.5-14B dense lens-control) × 4 domains, 150 q × 5
attempts = 750 records/cell, 16 cells; later slides renumbered (+1 from old 11), speaker script
renumbered to 26 with new Slide-11 section. Artifact republished (label `bluf-evidence+roster`).
Slide 5 then restacked as vertical finding rows (finding · evidence sentence · key stat: 12/16,
0.76–0.88, 80→43); closing line replaced with the epistemic standard (out-of-fold, fixed layer,
layer-0 check, dose/random/sign controls); slide-26 filler line dropped. Label `stacked-findings`.
Title slide iterated to final form: octagon question + speech/thought bubbles on the right;
left side = title + three-beat outline ("exist inside? read it? use it?") + plain scope line.
**Deck now 27 slides, fundamentals-first structure:** findings BLUF moved from slide 5 → slide 11
(after the toolkit); mech-interp 101 expanded to 3 slides — 1/3 stream end-to-end (new SVG:
embedding lookup → additive blocks → vector snapshots at layers 0/20/40 → decode scores whole
vocab, "28 wins and ships"), NEW 2/3 "inside one block" (four token streams; attention = only
cross-token step; MLP per token; coral ring = the probe's read: one token · one depth · ~5k dims),
3/3 read-then-poke. Speaker script restructured/renumbered to 27. Label `fundamentals-first`.
**Codex review pass** (20 findings; session in `.context/codex-session-id`): fixed stale script
numbers (probe "0.75–0.98" → audited 0.57–0.95; steering "~87→43" → 80→65→43 with correct
answers 97→96→89), "all five"→"all four matrix models" for probe claims, read-site duplicate
line, Result 4→4a/4b/4c, "one wiring" rephrased (dense = stable transport, not input-invariant
attention), speakable-wiring scoped to dense, "access problem"→"largely an access problem",
single-seed caveat now visible on roster slide, accuracy-steering (GLM×GPQA 0.38 vs 0.41)
tagged **preliminary — provenance not in audited docs, needs H-DRIVER run-record check before
presenting "Drive ✗" as settled**. Deferred (user to decide): title "five models" phrasing,
BLUF placement (kept at 11 deliberately), further claim-softening (#13–17). Label `codex-fixes`.
**Story-threading pass** (results imported from `study_onepager.html`, audited numbers kept —
the one-pager's own headline range 0.69–0.96/"all 16" is the retired best-layer era, NOT
reintroduced): title Q1/Q2/Q3 (exist? read? use?) now tag the findings rows, every result
eyebrow carries "evidence for finding N", closing slide reworked to "Asked at the start —
answered now" with Q1 YES / Q2 YES / Q3 AS A GAUGE cards. Imported results: blind
self-correction (confidence revised downward post-failure with zero feedback, geometry +
MMLU-Pro) added to Result 2; dense-vs-MoE/Mamba field rule added to Result 4b. fig2 34vh to
fit. Label `threaded-story`.
**Pre/post beat added to Result 3** (label `pre-post-beat`): retrospective > prospective
(geometry POST 0.66–0.70 vs PRE 0.52–0.62); PRE internal reads peak early/mid and largely encode
prompt difficulty (Mistral 0.88@L20, Gemma 0.70@L2 — caveated in the 2026-07-05 entry), POST is
layer-0-chance → mid/late peak; post→pre transfer 0.39–0.67, post residualized on pre keeps
0.59–0.87 → distinct directions. NB: no checked-in pre-vs-post *layer-curve figure* exists —
regenerating one needs the activations on the GPU box; fig5 remains POST-only.

**Open items:** (a) ~~two-screen presenter view~~ **done 2026-07-22** — press **P** in the deck:
opens a presenter-console popup (slide count + build progress, elapsed timer click-to-reset,
wall clock, current notes large, next-slide preview; arrow keys sync from either window,
falls back to the N-notes overlay if the popup is blocked). Also added `<meta charset="utf-8">`
to the deck (was mojibake when served over plain HTTP without a charset header);
(b) architecture-control broadening + per-input variance
measurement remain the science asks (slide 25); (c) title-slide speech bubble still says
"…so the answer is 28" (deliberate — matches quiz slide's wrong answer).
