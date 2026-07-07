# Pre-registered analysis plan — metacognition across tasks & models

**Status:** pre-registered (written before the QA/benchmark data exists). **Date:** 2026-07-05.
**Depends on:** [LAB_NOTEBOOK.md](LAB_NOTEBOOK.md) (geometry results), [CONFIDENCE.md](CONFIDENCE.md) (read-site design).

## 1. Question
Are the metacognition phenomena we found on geometry construction **task-general** — do they
replicate across model families *and* across task types? We fix the geometry finding as the
prior and test whether it holds on standard benchmarks.

## 2. Hypotheses (pre-specified, falsifiable)
- **H1 — Post > Pre.** Post-task verbalized confidence predicts correctness better than pre-task
  (AUROC_post > AUROC_pre). *Doing the task sharpens self-assessment.*
- **H2 — Blind self-correction.** Confidence is revised **down** more on failures than successes
  (mean Δ_fail ≪ Δ_ok; AUROC(−Δ → failure) > 0.5) — with **no feedback** given (grading is external).
- **H3 — Internal > verbalized.** A linear probe on the residual stream at the confidence decision
  token predicts correctness at least as well as the stated number.
- **H4 — Computed, late, content-neutral.** Internal decodability is ≈ chance at layer 0 (read-site
  sanity) and rises to a **late-layer** peak.
- **H5 — Genuine self-monitoring.** Post-confidence predicts correctness **within a question**
  (fixed difficulty; within-question AUROC > 0.5), not only across questions.
- **H6 — Capability gradient (exploratory).** Metacognitive sharpness co-varies with model capability.

## 3. Design
- **Models (4, fixed):** Qwen3.6-27B, GLM-4.7-Flash, Mistral-Small-24B, Gemma-4-26B-A4B.
- **Tasks:** geometry construction (done) + **MMLU**, **MedQA**, **GSM8K**; **GPQA** as a
  contamination-robust cross-check.
- **Protocol (3-turn, identical to geometry):** pre-conf → answer → post-conf. Grading is **external**
  (the model never sees the verdict — see H2).
- **Read sites:** the content-neutral `Confidence:` **decision token** (pre and post), plus the
  **last prompt token** (a no-elicitation pre-task read, no anchoring).
- **Items:** a **fixed subset per benchmark (shared seed → identical across all 4 models)**,
  n ≈ 250–500, × 2 samples (for the within-question control). Same prompt template per task across models.

## 4. Confidence measures (triangulated — do not rely on one)
1. **Verbalized** (stated 0–100) — may mode-collapse; report reliability.
2. **Internal** — linear probe on the decision-token residual stream (per-layer, grouped OOF).
3. **Answer-token log-prob** — the model's probability on its *chosen* option (MC), an
   elicitation-free confidence; plus a **P(True)** ("is this correct? yes/no") cross-check.

## 5. Controls & validity threats
- **Read-site (H4 gate):** report layer-0 within-question AUROC; must be ≈ 0.5.
- **Difficulty (within-question):** ≥2 samples/item; report **within-question** AUROC (difficulty fixed).
- **Surface confound:** incremental-validity test — does confidence beat **answer/reasoning length**
  (the QA analog of the geometry #ops control)?
- **Label validity (QA-critical):** report the **answer-extraction failure rate** and **spot-check
  ~20** `(model answer → extracted → gold → verdict)` tuples per benchmark before analysis. A flaky
  grader silently poisons every downstream number.
- **Contamination:** MMLU/MedQA are likely in pretraining → inflated accuracy and a possibly
  *memorized* pre-task signal. Mitigation: include **GPQA** (Google-proof) as a cross-check; caveat throughout.
- **Fair comparison:** identical items + seed + template + #samples across all 4 models.
- **No leakage:** probe train/test split **grouped by question**; out-of-fold scores only.

## 6. Analysis plan (per hypothesis)
| H | metric | test / decision rule |
|---|---|---|
| H1 | AUROC(conf → correct), pre vs post | H1 holds if AUROC_post − AUROC_pre > 0 with non-overlapping bootstrap CIs |
| H2 | Δ = post − pre, by outcome; AUROC(−Δ → fail) | holds if Δ_fail < Δ_ok and AUROC > 0.5 (CI excludes 0.5) |
| H3 | best-layer internal AUROC vs verbalized AUROC | holds if internal ≥ verbalized (CI) |
| H4 | per-layer internal AUROC curve | holds if layer-0 ≈ 0.5 and a later layer clears it by > 0.05 |
| H5 | within-question AUROC(post → correct) | holds if > 0.5 (CI excludes 0.5) on mixed-outcome questions |
| H6 | the above × model | exploratory: rank models; no confirmatory claim |

## 7. Statistics
- **Bootstrap 95% CIs** on every AUROC (resample items; for within-question, resample questions).
- Report **ECE + Brier + reliability diagram** for calibration, not just AUROC.
- **Multiple comparisons:** H1–H5 are the confirmatory family per (model × task); everything else is
  exploratory and labeled as such. No selective reporting — all pre-registered cells reported.

## 8. Caveats / limitations
- **Contamination** can inflate accuracy and confound the pre-task "do I know this" signal (→ GPQA cross-check).
- Probes are **linear at a single token**; a non-linear / multi-token readout could differ.
- Single dataset seed per (model × task) unless noted; CIs quantify item-sampling noise, not seed noise.
- MC/short-answer correctness is cleaner but *coarser* than geometry's staged grade (no partial-credit structure).

## 9. Pipeline (what produces these)
`capture_qa.py` (3-turn QA capture, VLM-aware) + `tasks_qa.py` (per-benchmark load/prompt/**validated** grade)
→ same meta/npz format as geometry → `analysis/confidence_temporal.py` (+ the surface/CI/logprob additions
listed in §4–5). Task-agnostic below the grader, so geometry and QA are analyzed identically.

## 10. Amendments & deviations (logged post-data; §§1–9 above are the frozen pre-registration)

Transparency log of everything that changed after data collection.

**A. Benchmark set (difficulty calibration).** Planned MC set was MMLU / MedQA / GSM8K. Pilots showed
**MMLU and MedQA ceiling'd** (~92%) for these models → almost no failures → nothing to calibrate.
Replaced with **MMLU-Pro** (harder, real spread) and added **MATH**. Final set: **MMLU-Pro, GSM8K,
MATH**. GSM8K was *also* ceiling'd for 3/4 models (90–95%) but retained — well-powered for GLM (45%
pass) and a within-model difficulty contrast. *Lesson: metacognition is failure-hungry; pick benchmarks
by the target model's error rate, not popularity.*

**B. Within-question power (H5).** At 2 samples/item, high-accuracy models yield very few
mixed-outcome questions (2–35), so H5 is underpowered for them. It is well-powered only near 50% pass
(**GLM**: 73–118 mixed prompts/cell, within-question 0.55–0.71). *Lesson: H5 needs the right difficulty
(a ~50%-pass model) or many more samples/item — n alone doesn't fix it.* Bumping samples to 5–8 is the
clean fix (staged in the re-run).

**C. H3 readout (best-layer → band-mean).** Reporting the **best** layer's OOF AUROC is optimistic
(selection over 30–64 honest per-layer estimates). Headline switched to a **band-mean** (0.5–0.9 depth)
+ **fixed@0.7-depth** readout (`analysis/matrix_report.py`). Internal > verbalized still holds in
**15/16 cells** (mean +0.11) under the honest readout — H3 survives.

**D. Label-validity control fired (§5 worked).** Extraction-failure was 0%, but the MATH grader's
**equivalence match** false-negatived formatting-equivalent answers (`\frac{a}{b}` vs `a/b`, `\$`,
decimal↔fraction) — under-counting pass and polluting "failures". Fixed with **`math_verify`** + offline
re-grade from stored completions (`analysis/regrade_math.py`; rescued 5–9%/model, 0 demoted).
*Lesson: extraction-success ≠ grading-correct; validate the match, not just that something was extracted.*

**E. QA confidence-prompt bug → QA POST numbers are provisional.** `capture_qa.py` reused the
**geometry-worded** confidence prompts on the QA confidence turns (asked about a "construction" being
"geometrically correct"). Turn-2 answers were correctly task-worded (accuracy/grading unaffected), but
the QA **POST and elicited-PRE internal reads are provisional** pending a corrected re-run. The bug-free
**no-elicitation PRE** read is unaffected and already supports H3. Corrected QA-worded prompts +
**per-turn thinking** (a deviation from the global `--no-think` used here, which ran Qwen3.6/GLM below
peak) are staged in `rerun_driver.sh`. **Re-run pending (task #11); Qwen3.6 full-n geometry re-capture
pending (task #12).**

**F. Not yet run.** GPQA cross-check (§3, contamination robustness) — task #13, optional. Answer-token
log-prob / P(True) triangulation (§4.3) — deferred until the corrected re-run.
