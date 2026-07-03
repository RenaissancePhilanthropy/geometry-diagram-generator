# Confidence / metacognition sub-study — does the model know when its construction is wrong?

**Date:** 2026-07-01 · **Model:** Qwen2.5-7B-Instruct (bf16), Qwen2.5-32B-AWQ ·
**Depends on:** [METHODOLOGY.md](METHODOLOGY.md), [RESULTS.md](RESULTS.md)

## Question
When the model writes a geometry construction, does its residual stream carry a signal
of whether that construction is **correct** (compiles + passes every `must`-check)? If
so, *where* — and is it genuine self-assessment or an artifact?

## TL;DR (verdict as of 2026-07-01)
On the existing captures (which read at an **entity token**), a correctness probe hits
~0.78 cross-prompt — but this is almost entirely explained by two confounds: problem
**difficulty** (0.90–0.97 AUROC) and the **read site** (the token we read at co-varies
with correctness). After controlling both, **no computed self-assessment is established
at that read site.** The fix — reading at a fixed, content-neutral `Confidence:` token —
was built and **run on two models (Qwen2.5-7B and GLM-4.7-Flash); see Results below.**

## Results — the confidence-slot runs (2026-07-02)

Ran the fixed-slot experiment on two models: **Qwen2.5-7B** (single-turn `--elicit-confidence`, 657 records, read at the digit slot) and **GLM-4.7-Flash** (30B-A3B MoE, **two-turn** `--confidence-followup`, 720 records, read at the *decision* token — the token that generates the number). Two-turn was **required for GLM**: the single-turn instruction truncated its (verbose, pretty-printed) JSON — 0/4 success, 50% unbalanced braces — confounding correctness. Generating the construction first and eliciting confidence separately fixed it (25% success, 0/12 unbalanced).

**1. The read-site fix works — on both models.** At the confidence slot, layer-0 (raw-embedding) within-prompt AUROC = **0.48 (Qwen) / 0.50 (GLM)** ≈ chance, vs **0.74–0.83** at the entity token. The content-neutral slot removes the read-site confound regardless of model.

**2. Verbalized confidence: useless at 7B, calibrated at 30B** (AUROC for predicting own correctness):

| | verbalized | internal probe | difficulty (baseline) |
|---|---|---|---|
| Qwen-7B | **0.53** — collapsed at ~99, right 14% | 0.70 | 0.92 |
| GLM-Flash | **0.72** — mean 89, separates ok 95 / fail 88 | 0.81 | 0.85 |

Both show **internal > verbalized** ("knows more than it says"); the bigger model's *words* are also far more informative.

**3. The decisive #ops incremental control — genuine metacognition only at 30B.** The sharp test (`interp/analysis/incremental_ops.py`): within-prompt (difficulty fixed), does adding the confidence-slot activation improve correctness prediction *beyond* the #ops/output-shape features?

| within-prompt AUROC | Qwen-7B | GLM-Flash |
|---|---|---|
| surface-only (#ops/shape) | 0.85 | 0.69 |
| activation-only | ~0.55 (≈ chance) | 0.72 |
| surface + activation | 0.68–0.74 (*worse*) | **0.78–0.79** |
| **activation's increment over #ops** | **−0.12 to −0.18** | **+0.07 to +0.10** |

GLM's activation adds a real **+0.10** beyond #ops — **+0.00 at layer 0 rising to +0.10 mid-late (L24–47)**, the textbook signature of a *computed* representation, with activation and #ops **complementary** (combined beats either alone). Qwen's activation is ~chance and adds nothing (its entire apparent signal was output-shape).

**Verdict:** with a proper read-site + difficulty + #ops control, **GLM-4.7-Flash has a genuine, computed internal signal of its own correctness that survives all three confounds; Qwen-7B does not.** Together with GLM's calibrated verbalized confidence, this suggests **metacognition emerges/sharpens with capability.**

**Caveats:** Qwen was single-turn / digit-read vs GLM two-turn / decision-read — a **Qwen two-turn re-run** would make the comparison fully apples-to-apples (and rule out that read-site/elicitation, not scale, drives the gap). Qwen's data is thinner (21 vs 44 mixed-outcome prompts). Single-seed; linear probes at a single token. Analyses: `incremental_ops.py`, `confidence_vs_difficulty.py`, `verbalized_vs_internal.py`.

## The cascade of controls (how we avoided fooling ourselves)

| step | question | result |
|---|---|---|
| 1. decodability | is correctness linearly decodable? | **yes** — cross-prompt acc ~0.78 (7B), chance early, rises to a mid-late peak ~L18–20 (multi-seed) |
| 2. difficulty | is it just "which prompt is hard"? | prompt base-rate alone predicts correctness at **0.90–0.97 AUROC** — i.e. *most* of step 1 |
| 3. within-prompt | beyond difficulty (same prompt, pass vs fail)? | probe still ranks pass>fail within a prompt at **0.63–0.80**; sign 9/12 (big30), 13/16 (q32) — some attempt-level signal |
| 4. surface (fair) | is that just output shape? | raw size features (len, #ops, #id-mentions) are **weak** (~0.5–0.61); **but layer-0 embeddings at the read site alone = 0.74–0.83** within-prompt, and the deep layers beat that by only ~**+0.03** |
| 5. diagnosis | why is layer-0 already that good? | the read site is an **entity token** whose identity/position **co-varies with correctness**. The `#entities` feature is also inflated by a capture artifact: passing constructions store ~2× more entities (**6.5 vs 2.7**) because failures don't compile — though what the model actually *wrote* barely differs (**n_ops 7.5 vs 6.0**) |

**Verdict:** the entity read site is **fundamentally confounded**, so we cannot claim
computed self-assessment from it. (Analogy: judging honesty by always reading the *last
word* of a sentence — you end up measuring sentence length, not honesty.)

## The fix — a fixed, content-neutral read site
Ask the model to end its answer with `Confidence: N` and read the residual stream **at
the digit token**. That slot always has the same local context ("Confidence:") and is a
bare number, so:
- its **layer-0 embedding does not encode which entities exist** → layer-0 within-prompt
  AUROC should fall to ~0.5 (the confound is gone);
- any **mid-late** within-prompt signal that beats layer-0 **and** the surface baseline is
  genuine **computed** self-assessment;
- the stated `N` is a **verbalized** confidence to calibrate against the grade and compare
  head-to-head with the internal probe.

## What's built (all offline-tested, no GPU)
- `interp/confidence.py` — `CONFIDENCE_INSTRUCTION`, `add_confidence_request`,
  `parse_confidence`, `confidence_positions`.
- `interp/capture.py --elicit-confidence` — appends the request; stores `conf_value` +
  `conf_positions`; keeps the conf slot (+ entities) on disk (a few GB, **not** the tens
  of GB a full `--keep-positions all` would cost).
- `interp/probe.py` → labeler `correctness_conf` reads the fixed conf slot;
  `correctness` / `correctness_first` now **exclude** the conf slot so entity reads stay
  entity reads.
- `interp/analysis/confidence_vs_difficulty.py --read conf` — difficulty + within-prompt +
  **fair** (compile-independent) surface controls, at the conf slot.
- `interp/analysis/verbalized_vs_internal.py` — difficulty vs verbalized vs internal AUROC,
  plus a verbalized reliability table.
- Tests: `interp/test_confidence.py` (+ the `correctness` tests in `test_probe.py`) — green.

## Runbook (24 GB GPU — RTX 4090 / A10 / L4; see [PROPOSAL.md](PROPOSAL.md))
GPU sizing: 7B bf16 needs ~15 GB weights + a couple GB for the forward pass — 24 GB is
plenty; 32B-AWQ 4-bit also fits 24 GB; only full-precision 32B needs 80 GB (not required).

**1. Recapture with confidence, keeping failures (NO `--only-valid`) and many UNIQUE prompts:**
```bash
python interp/capture.py --device cuda --n 90 --few-shot relevant:4 \
    --samples 8 --temperature 0.8 --keep-positions entities \
    --elicit-confidence --out-dir interp/activations/conf7b
```
~720 generations, <1 h, ~$1–3. (Add `--tier 1` to restrict difficulty; **drop** it for more
unique prompts — data thinness, not GPU, was the limiter.)

**2. Analyze (all CPU-only, offline):**
```bash
python interp/probe.py --act-dir interp/activations/conf7b --labeler correctness_conf
python interp/analysis/confidence_vs_difficulty.py --act-dir interp/activations/conf7b --read conf
python interp/analysis/verbalized_vs_internal.py --act-dir interp/activations/conf7b
```

## How to read the results (decision rules)
- **SANITY:** at the conf slot, layer-0 within-prompt AUROC should be ≈0.5. If it's still
  high, the slot isn't content-neutral (the model may leak structure right before the
  number) — inspect completions.
- **COMPUTED self-assessment:** if a mid-late layer's within-prompt AUROC beats **both**
  layer-0 and the surface baseline by > ~0.05, the model internally represents whether it's
  right, independent of difficulty and output shape. That's the result we're after.
- **KNOWS-MORE-THAN-IT-SAYS:** if internal-probe AUROC > verbalized AUROC, the activations
  predict failure better than the stated number → a usable **abstain/retry** signal (the
  product hook for the proposal).
- **CALIBRATION:** the reliability table shows whether the stated numbers mean anything
  (watch for mode-collapse at ~90).

## Caveats / how to strengthen
- **Data thinness** was the real limiter (only 6–16 mixed-outcome prompts). Spend the GPU
  budget on more **unique** prompts, not more samples per prompt.
- Single-pass verbalized confidence relies on the model following the `Confidence: N`
  format; a **two-pass P(True)** elicitation ("Is this construction correct? yes/no", read
  P(yes)) is a robust fallback and gives a logit-based confidence too.
- Everything here is a **linear** probe at a single token (matching how the model reads);
  a computed signal could still exist non-linearly or across multiple tokens.
