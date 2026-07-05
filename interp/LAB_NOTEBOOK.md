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

## Verdict (as of 2026-07-03)
**Metacognition here is a capability *gradient*, not a switch.**
- **Read-site fix is robust** — content-neutral `Confidence:` slot gives layer-0 ≈ 0.5 on both
  models (vs 0.74–0.83 at the entity token).
- **Verbalized calibration scales cleanly** — Qwen-7B's stated confidence is useless
  (AUROC ~0.52, mode-collapsed at ~99) **regardless of elicitation**; GLM-Flash's is
  genuinely calibrated (0.72). The difference is the model, **not** the method.
- **Computed self-assessment (beyond output-shape) is clear at 30B, marginal at 7B** — the
  #ops-incremental gain is **+0.10 (GLM)** vs **+0.02 (Qwen, two-turn)**.
- **"Knows more than it says"** holds on both (internal probe ≫ verbalized).
- **The read-site/elicitation mattered more than expected:** Qwen's incremental went
  **−0.15 (single-turn) → +0.02 (two-turn)**, so the *single-turn* cross-model comparison
  had **overstated** the gap. What survives at matched protocol is real but smaller.

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

**Caveats.** High internal *PRE* reads on some models (Mistral 0.88 @ L20, Gemma-4 0.70 @ L2)
largely reflect **difficulty decodable from the prompt**, not metacognition — hence within-question
is the metric for the "genuine self-monitoring" claim. Single dataset seed; within-question data is
thin (21–42 mixed-outcome prompts). Gemma-4 needed `--max-new-tokens 2560` (its verbose pretty-printed
JSON truncated at 1024 → false parse failures).

**Next:** the same 3-turn protocol on QA benchmarks (MMLU / MedQA / GSM8K) to test **cross-domain**
generalization — pilot (Gemma-4 × MedQA) in progress.

---

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
- **Datasets** (local `interp/activations/`, gitignored): `conf7b` (Qwen single-turn),
  `qwen7_2turn`, `glm7_2turn`.
- **Code:** `confidence.py`, `capture.py` (`--elicit-confidence`/`--confidence-followup`/
  `--no-think`), `probe.py` (`correctness*` labelers), `analysis/{confidence_vs_difficulty,
  verbalized_vs_internal,incremental_ops}.py`, tests `test_confidence.py`.
- **Related docs:** `CONFIDENCE.md` (design + read-site backstory), `METHODOLOGY.md`
  (general probing protocol), `RESULTS.md` (spatial decodability, 7B/32B).
