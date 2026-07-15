# Knowing versus saying: internal correctness signals and verbalized confidence in language models

**Working draft — v0.1, July 2026.** A running synthesis of the study, in paper shape. Numbers are
current; two MATH cells are at reduced n and the J-lens (workspace) arm is still in progress — flagged
inline. Companion docs: [METHODS_MATH.md](METHODS_MATH.md) (formal methods),
[PROGRESS_REPORT.md](PROGRESS_REPORT.md) (intuition), [LAB_NOTEBOOK.md](LAB_NOTEBOOK.md) (dated results),
[QA_STUDY_PLAN.md](QA_STUDY_PLAN.md) (pre-registration + deviations).

---

## Abstract

Language models often answer incorrectly while reporting high confidence. We ask whether this reflects
an absence of self-knowledge or a failure to express it, and separate the two by reading the residual
stream directly. Across **four open models spanning distinct architectures** (hybrid Mamba–attention,
mixture-of-experts, dense, and an MoE vision-language model) and **four task domains** (a
compiler-verified geometry construction task, MMLU-Pro, MATH, and GPQA-Diamond), we elicit confidence in
a three-turn protocol with external, hidden grading, and read a linear "am-I-correct?" signal at a
content-neutral token. We find that (i) a linear probe on the residual stream predicts an attempt's
correctness better than the model's own stated confidence in **15 of 16 model×domain cells** (mean gap
+0.11 AUROC); (ii) this **knowing–saying gap is largest on MATH**, where a wrong answer is
surface-identical to a right one (stated 0.57 vs internal 0.78 for one model); (iii) under a
within-question control that fixes difficulty, the model's own output-probability signal (P(True))
collapses toward chance while the residual-stream probe holds — the internal signal tracks *this
attempt*, not merely *which questions are hard*; and (iv) **the signal is causal**: amplifying a model's
own internal correctness direction — using no labels at intervention time — lowers its stated confidence
on wrong answers from 80 to 43 while leaving correct answers near 90 and halving calibration error, with
a matched random direction having no effect. Effects are architecture-dependent in their causal form,
which we argue is itself the finding. Models substantially know when they are wrong; whether they say so
is a separate, and partly steerable, property.

---

## 1. Introduction

A model that errs is unavoidable; a model that errs *and knows it* is deployable — it can abstain, retry,
or escalate. Yet stated confidence is a weak guide to correctness. We decompose the problem into two
questions: **do models internally represent that an output is wrong (knowing)**, and **does that
representation reach what they report (saying)?** The gap between them, if it exists, is both an unused
safety signal and a concrete claim about machine introspection.

We borrow a distinction from metacognition research — *prospective* ("will I get this right?") vs
*retrospective* ("did I?") — and measure both, per attempt, inside the model. Our contributions:

1. A **three-turn, blind-graded protocol** that elicits pre- and post-attempt confidence while capturing
   the residual stream at a content-neutral read site, plus the model's output-distribution confidence
   (P(True), answer log-probabilities) — four readouts of the same latent quantity on identical records.
2. A **claim ladder** of increasingly hard-to-deflate controls (decodable → beyond-difficulty →
   beyond-surface → beyond-the-output-distribution → causal → mechanistic), each killing one boring
   explanation.
3. Evidence, across four architectures and four domains, that the **internal signal exceeds verbalized
   confidence**, is **attempt-specific** (survives a within-question difficulty control), **exceeds the
   model's own bets** on most architectures, and is **causally used** to set stated confidence.

## 2. Related work (brief)

Kadavath et al. (2022) showed models' output probabilities (P(True), P(IK)) are often well-calibrated
even where verbalization is not; we treat this as the baseline our internal readout must beat, and test
it under a difficulty control that prior work rarely applies. Work on internal truthfulness directions
(Azaria & Mitchell; Marks & Tegmark; Burns et al., CCS) reads *truth of a given statement*; we read
*correctness of the model's own output* on open-ended and multi-choice tasks. Verbalized-calibration
studies (Lin et al.; Tian et al.) measure stated confidence; we contrast it head-to-head with the
internal signal and then intervene. Our causal and mechanistic arms connect to representation
engineering (Zou et al.) and to Anthropic's (2026) global-workspace/Jacobian-lens account of
verbalizable representations, which motivates our final experiment. What is distinctive here is the
combination: temporal (pre/post) elicitation over the model's *own attempts*, blind (no-feedback)
updating, a domain-resolved knowing–saying dissociation, and a compiler-verified generative testbed.

## 3. Methods

*(Formalized in [METHODS_MATH.md](METHODS_MATH.md); summarized here.)*

**Models.** Qwen3.6-27B (hybrid Mamba+attention), GLM-4.7-Flash (MoE), Mistral-Small-24B (dense),
Gemma-4-26B-A4B (MoE, VLM-derived). Spanning architectures so no result is a single-family artifact.

**Domains and grading.** Geometry: the model emits a construction program graded by a
`parse→validate→lower→compile→check` pipeline (SymPy) — exact, machine-checkable, and hard (13–39% pass).
MMLU-Pro (letter match), MATH (`math_verify` symbolic equivalence), GPQA-Diamond (letter match). We drop
benchmarks the models ceiling on (GSM8K, MedQA at 90–95%): metacognition is failure-hungry, so
benchmarks are chosen by error rate, not popularity.

**Protocol.** Three turns per problem — (1) prospective confidence, (2) attempt, (3) retrospective
confidence — with grading external and never shown to the model, so post-failure confidence drops are
*blind* self-assessment. For hybrid reasoners, extended thinking is on for the attempt, off for the
confidence turns (to keep the read site content-neutral). Scale: 4 models × 4 domains × 150 problems ×
5 samples ≈ 750 records/cell (two MATH cells at 494–548 due to a mid-run hardware failure; still
well-powered).

**Readouts.** *Verbalized* (stated 0–100); *P(True)* and *answer log-prob* (output distribution,
teacher-forced, no generation); *probe* (logistic regression on the residual stream at the confidence
decision token, StandardScaler→PCA(50)→LogReg, grouped out-of-fold, reported at fixed depth or mid-late
band mean); *J-lens* (unsupervised — in progress). Scored by AUROC; calibration by ECE; 95% CIs by
bootstrap (resampling questions for within-question metrics).

**Controls.** Read-site content-neutrality (layer-0 AUROC = 0.500 per-fold in all cells); within-question
difficulty control (mixed-outcome questions only); surface/answer-length incremental validity; grader
validity (extraction-failure rate + spot-checks). A public deviations log records a train/test leak, a
confounded read site, a MATH-grader bug, and a prompt-wording leak — each caught by a planned control,
fixed, and re-run.

## 4. Results

### 4.1 Internal ≫ verbalized, across architectures and domains

Using the honest band-mean readout (not best-of-layer), the residual-stream probe predicts correctness
better than the model's stated confidence in **15 of 16 cells** (mean gap **+0.11** AUROC). The read-site
control passes everywhere: layer-0 per-fold AUROC is exactly 0.500, so the signal is computed in mid/late
layers, not lexical. Representative post-attempt cells:

| model × domain | verbalized | probe (internal) |
|---|---|---|
| Gemma-4 × MATH | 0.57 | **0.78** |
| Qwen3.6 × MMLU-Pro | 0.67 | **0.85** (best-layer) / 0.84 band |
| GLM × MMLU-Pro | 0.67 | **0.85** |
| Mistral × MATH | 0.79 | **0.83** |

### 4.2 The knowing–saying gap is largest where errors look clean

The gap is widest on MATH, where a wrong `\boxed{answer}` is surface-indistinguishable from a right one:
verbalized confidence there is near-useless (0.57 for Gemma-4) while the internal signal is the strongest
of any domain (band 0.76–0.90; up to 0.96 best-layer). Post-attempt internal readouts exceed pre-attempt
ones — doing the work sharpens the *internal* signal even where it degrades the *stated* one. In other
words, the MATH "confidence gets worse after answering" effect is a verbalization failure, not a
representational one.

### 4.3 The internal signal is attempt-specific; the model's bets are not

The sharpest control holds difficulty fixed (within a question, across its 5 samples). Here the model's
own P(True) collapses toward chance while the probe holds:

| within-question (difficulty fixed) | probe | P(True) |
|---|---|---|
| Qwen3.6 × MMLU-Pro | **0.74** | 0.47 |
| GLM × MMLU-Pro | **0.73** | 0.59 |
| Mistral × MATH | **0.72** | 0.59 |

Interpretation: **P(True) largely re-derives which questions are hard; the residual-stream probe tracks
whether this particular attempt succeeded.** Across cells, the probe beats P(True) on 3 of 4
architectures (decisively on GLM, 0.85 vs 0.60); Gemma-4 is the exception where P(True) is competitive —
one instance of the architecture-dependence that recurs throughout.

### 4.4 Blind self-correction

Without any feedback that it failed, confidence is revised *downward* more on failures than successes on
geometry and MMLU-Pro (e.g. mean post−pre change on failures is strongly negative), consistent with a
genuine, if under-expressed, self-monitoring process.

### 4.5 The signal is causal

Steering at the confidence token (turn 3 only, so the answer is unchanged by construction) establishes
use, not mere presence. **Amplifying a model's own projection onto its correctness direction — with no
labels at intervention time** — closes the gap on Mistral × MATH: as gain increases (1→2→4), stated
confidence on *failed* answers falls **80 → 65 → 43** while *correct* answers hold near **90**;
calibration error drops **0.31 → 0.13**; a random direction of equal norm is flat; dampening the signal
(gain < 1) increases overconfidence (bidirectional dose–response). Add-mode corroborates a monotonic,
control-beating dose–response.

Replication is **architecture-dependent**: Gemma-4 shows the correct specificity (steering moves only the
failed answers) but its near-ceiling MATH cell is underpowered (GPQA rerun pending); GLM is null at tested
gains — its stated confidence saturates near 100 under greedy decoding, i.e. the *speech channel appears
decoupled* precisely in the model where the probe most exceeds P(True). We read this not as a failed
replication but as evidence that *how much internal knowledge reaches speech* varies by model.

### 4.6 Mechanism (in progress)

Whether the correctness signal enters the *verbalizable* subspace is being tested with an unsupervised
Jacobian lens (Anthropic 2026): if the lens's failure-word readout matches the supervised probe, the
knowledge is speakable and suppressed; if the lens is at chance while the probe is strong, it is an
*access* failure. This arm has not yet produced results (infrastructure). The lens also enables reading
correctness drift *during* a geometry construction (entity-token snapshots) — when in the process the
model "knows."

## 5. Discussion

**Architecture-dependence is the through-line.** Internal≫verbalized is universal; the *causal* and
*output-distribution* pictures are not. GLM carries strong internal correctness information that its
stated confidence does not express and steering (at tested settings) does not move; Mistral's is fully
expressible and steerable; Gemma-4 uniquely lets P(True) compete. A single-model study would have
reported any one of these as "the" result. The honest claim is a *spectrum* of how internal self-knowledge
couples to speech.

**Why the gap is largest on MATH.** Multi-step computation yields well-formed but wrong answers with no
surface tell, so verbalized confidence — which appears to lean on surface fluency — fails, while the
internal state, which encodes the computation, does not. This predicts the gap should track *error
detectability from the surface*, testable across more domains.

**Practical upshot.** The internal readout supports selective prediction: abstaining on its lowest-scoring
outputs raises accuracy far more than abstaining on low *stated* confidence (risk–coverage curves), and
the steering result suggests calibration can be improved by amplification rather than retraining.

## 6. Limitations

Linear probes and lens at a single token (nonlinear/multi-token signal would be undercounted); the
averaged Jacobian under-sees context-gated content; best-of-layer selection is optimistic (we report
fixed/band); single dataset seed per cell; two MATH cells at reduced n; the causal arm is one clean model
plus one under-powered and one null replication; the mechanism arm is unfinished. Grader validity gates
every number — one MATH-grader bug materially shifted results before it was fixed. These are recorded in
the deviations log rather than hidden.

## 7. Conclusion

Across four architectures and four domains, open language models carry a linear internal signal of their
own correctness that (i) exceeds their stated confidence, (ii) is specific to the individual attempt
rather than the question's difficulty, (iii) on most architectures exceeds even the model's own
output-probability estimates, and (iv) is causally used — amplifying it, with no labels, makes a model's
stated confidence honest on the answers it gets wrong. Models substantially **know** when they are wrong;
whether they **say** so is a separate property that varies by architecture and can, at least sometimes,
be steered. The remaining question — *why* some models' knowledge fails to reach speech — is what the
mechanism (workspace) arm is built to answer.
