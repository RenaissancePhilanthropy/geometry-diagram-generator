# feat/recipe-improvements — Change Inventory

_Last updated: 2026-06-25_

**Baseline:** last commit `db17ae5` on `master`. Everything below is the content of the `feat/recipe-improvements` branch (tip `dc61c41`, pushed to `origin`) vs that baseline. The top of this file is a **change inventory** (what changed and why, by theme); the **Results data** sections below record the experiments and whether they actually helped (GEPA payoff, CoT-analysis, self-reported confidence, DSL_DOCS lift, etc.) — each leads with a TL;DR.

---

## Themes

- **Tolerate model quirks** — backends without tool-call support, models that emit annotations in the wrong shape, and cryptic validation errors.
- **Better retry guidance** — use the actual error text to give specific advice instead of generic hints.
- **Fallback path** — when the recipe strategy runs out of retries, try the structured strategy so a diagram is still produced.
- **GEPA prompt work** — optimized prompts, plus a way to run the optimized vs the prior prompts with everything else unchanged.
- **Confidence signal from CoT** — read the model's reasoning to flag low-confidence outputs and compare against the pass/fail gate.
- **Self-reported confidence (metadata-first)** — ask the model to rate its confidence *before* it constructs the diagram (prospective, not retrospective). A cheap ranking signal that beats the CoT analyzer and the LLM judge on the hard tier, but miscalibrated — a ranking, not a trustable probability.
- **Fix false-positives in checkers** — labels and marks were flagged as missing on correct diagrams.
- **Eval harness upgrades** — timeouts, thinking, CoT analysis, prompt switching, and scoring on failures (not just successes).
- **Re-score without regenerating** — recompute saved runs from their stored TikZ/CoT so old results match the current checkers.

---

## Generation & strategy

- **Recipe strategy fallback** — after retries are exhausted, hand off to the structured strategy; records whether the diagram came from the fallback or the recipe path. *Why: produce something instead of nothing on hard scenarios.* — `strategies/recipe.py`
- **Targeted retry hints** — three new hints (triangle-spec ambiguity, `mark_angle` mismatches, undefined id references) and an improved right-angle hint that lists candidate triples from the checker. *Why: each retry should address the actual failure.* — `strategies/recipe.py`, `strategies/recipe_hints.py` (new — hint texts moved here so GEPA can override them)
- **Thinking + prompt overrides** — the recipe strategy accepts `thinking` and `prompt_overrides`, and the structured strategy accepts `thinking` (used by the fallback path); selector model changed to the local gemma4 backend. *Why: enable extended reasoning and swap prompts at runtime.* — `strategies/recipe.py`, `strategies/base.py`, `strategies/structured.py`
- **Recover diagrams from text responses** — when a model returns JSON as plain text instead of calling the structured-output tool (surfaced as `UnexpectedModelBehavior`), parse it from the captured messages instead of failing; backend HTTP errors (`ModelHTTPError`) are logged and re-raised rather than retried as if they were model mistakes. *Why: support backends that don't support tool calls, and don't waste retries on transport errors.* — `strategies/structured.py`
- **Ollama compatibility** — patch null content in assistant messages; set reasoning effort so thinking is surfaced for ollama models. *Why: make ollama backends work correctly.* — `strategies/__init__.py`, `strategies/base.py`, `util/ollama_compat.py` (new)

## Prompts & GEPA

- **Optimized generation prompt** — the GEPA-improved `RECIPE_GENERATION_SYSTEM` (grew from ~6.9K to ~17K chars) with new guideline sections: satisfying expected properties by exact name, rotation solids / 3D diagrams, avoiding rendering artifacts, label placement, multi-panel layouts, fallback prevention. *Why: address the failure modes GEPA found.* — `strategies/instructions_recipe.py`
- **GEPA optimizer + adapter** — evolutionary prompt optimization over the recipe strategy's prompt components (generation/selection system prompts, DSL docs, hint texts), with a scorer that accounts for retries and duration vs a seed baseline. *Why: automate prompt improvement.* — `optimize_recipe_prompts.py` (new), `gepa_adapter/` (new)
- **Prompt ablation harness** — a boolean flag switches between the on-disk (GEPA-optimized) prompts and the prior (pre-GEPA, git-HEAD) prompts at runtime, with all code and checkers unchanged; the prior prompts are stored in a JSON extracted programmatically from HEAD. *Why: measure the effect of the GEPA prompts separately from the code/checker changes.* — `evals/run.py` (`--use-optimized-prompts`), `strategies/recipe_original_prompts_overrides.json` (new — lives alongside the recipe strategy's other prompt files: `instructions_recipe.py`, `recipe_hints.py`)

## CoT analysis & confidence

- **Deterministic confidence analyzer** — a text-only analyzer (no LLM, no ground truth) that counts uncertainty markers in the chain-of-thought and lowers confidence on struggle/self-contradiction. Replaces an LLM judge that returned a near-constant 5 regardless of correctness. *Why: a usable low-confidence signal in production where there are no verification checks.* — `util/cot_analyzer.py` (new)
- **LLM CoT judge kept** — the original LLM-based CoT judge is still available as an alternative. — `util/llm_judge.py`
- **Eval-harness integration** — `--cot-analysis` runs the confidence judge on both success and failure paths, captures top-level CoT, and derives a calibration label (agree/over/under-confident) vs the deterministic gate. *Why: score confidence even on failures and catch overconfidence.* — `evals/run.py`
- **CoT backfill** — recover CoT that was captured in attempt traces but never reached the top-level field (the all-fail-then-fallback path), and re-run analysis without regenerating. *Why: repair pre-fix runs.* — `evals/rescore_cot.py` (new), `strategies/recipe.py` (fallback now sets CoT)
- **Self-reported, metadata-first confidence** — ask the model to emit a structured self-assessment *before* it commits to the construction (prospective, not retrospective). Two elicitation methods share one schema: **hard** (a separate fenced `[[INTERNAL_METADATA]]` prelude call) and **soft** (the first field of the structured generation output); a `confidence_mode` toggle selects none/structured/prelude/both. *Why: post-hoc signals (the CoT analyzer, the LLM judge) rationalize the artifact the model already produced; a prospective self-report avoids that anchoring. Findings: hard discriminates on the hard tier and beats the CoT analyzer + LLM judge; soft is flat; all are miscalibrated (silently overconfident) — a ranking signal, not a probability.* See the **Self-reported, metadata-first confidence** section below. — `strategies/confidence.py` (new), `strategies/recipe.py`, `evals/run.py` (`--confidence-mode`), `evals/analyze_confidence.py` (new)

## Checker fixes (false-positive elimination)

- **Prime-notation normalization** — resolve `A'` / `A''` / `C'1` etc. against model naming variants (`A_prime`, `A_p`, `A_p2`…) before lookup; cut 129 false-negative property failures to 1. *Why: stop blaming correct geometry for naming differences.* — `evals/sympy_checks.py` (detail in GEPA section below)
- **Label & mark checker fixes** — recognize free-text `\node {$m$}` labels (lines/regions/axes), tick-segment and arc-angle multiplicity, and right-angle counts; map the scenario mark vocabulary to the kinds the extractor can actually produce (semantic marks like midpoint/radius stay intentionally uncheckable). *Why: stop flagging correct diagrams for label-placement style and tick/arc count mismatches.* — `util/tikz_extraction.py`, `util/tikz_geometry.py`, `util/tikz_validation.py`
- **Gate re-scoring** — recompute all tikz-based gate checks (expected_properties incl. marks/angles/collinearity, required_labels, required_entities, canvas, expected_points) from saved TikZ and re-finalize the gate, without regenerating. *Why: repair old runs hit by the checker false-positives (mark_present, free-node labels) so they're comparable to runs scored with the current checkers.* — `evals/rescore_gate.py` (new)
- **Check-error provenance** — check failures now report the originating file:line, not just the exception string. *Why: faster debugging.* — `ir/checks.py`

## DSL ergonomics

- **Actionable "extra inputs not permitted" errors** — resolve the rejected field's location to its Pydantic model and list the permitted fields, so the model gets a fixable hint instead of a cryptic pydantic error. *Why: turn a common failure into an easy retry.* — `recipe/dsl.py`
- **Annotations shape coercion** — tolerate models that emit `annotations` as a list or JSON string instead of an object. *Why: handle a frequent model mistake.* — `recipe/dsl.py`

## Eval harness & scenarios

- **Per-scenario timeout** — each scenario is capped (default 300s, intentional guardrail against slow cloud backends); on timeout a zeroed record with an error is written. *Why: one stuck scenario can't stall the batch.* — `evals/run.py`
- **Thinking + CoT-analysis flags** — `--thinking` and `--cot-analysis` passed through to strategies and the judge; failure-path CoT capture so scored failures still get a confidence score. — `evals/run.py`
- **Enriched records** — `attempts`, `used_fallback`, top-level `cot`, CoT-analysis score/signals/reasoning, and `confidence_calibration` added to result records. — `evals/run.py`
- **Confidence mode** — `--confidence-mode {none,structured,prelude,both}` (default `both`) selects the self-reported-confidence elicitation; records carry flat `self_confidence_hard_score` / `self_confidence_soft_score` and nested `recipe_metadata.evaluation_metadata_{hard,soft}`. — `evals/run.py`
- **Curriculum scenario tweaks** — small edits to the curriculum scenarios. — `evals/scenarios_geometry_curriculum.yaml`
- **New scenario files** — hard-intersection / hard3 / hard-failures / hard-stress / smoke variants and GEPA train/val/challenge sets, for running failing and stress subsets. — `evals/scenarios_*.yaml` (new)

## Tooling scripts (new, untracked)

- **Run scripts** — per-benchmark eval launchers (curriculum, hard-intersect, stress, hard-stress) with fixed judge model and auto-named logs. — `run_geometry_*_eval.sh`
- **Renderer start script** — start the bare-metal TikZ renderer. — `start_tikz_renderer.sh`
- **Profiling** — per-phase timing of one scenario (selection → generation → lowering → IR → judge). — `profile_single_scenario.py`
- **Failing-scenario extraction** — build a new scenarios YAML from the gate-failures of one or more runs (intersection/union). *Why: re-run evals over just what's failing.* — `evals/extract_failing_scenarios.py`
- **Confidence analysis** — wrapper for `evals/analyze_confidence.py`: pick results JSONL(s) (defaults to newest `evals/results/*.jsonl`), strict/lenient truth label, bootstrap CIs, optional JSON report; `--help` documents all params inline. *Why: one-command confidence-vs-gate analysis with the help/params in the script itself.* — `analyze_confidence.sh`

## Tests (new + expanded)

- New: `tests/test_cot_analyzer.py`, `tests/test_cot_analysis_failure.py`, `tests/test_dsl_validation.py`, `tests/test_gepa_adapter.py`, `tests/test_sympy_checks.py`, `tests/test_ollama_compat.py`, `tests/test_confidence.py`, `tests/test_analyze_confidence.py`
- Expanded: `tests/test_recipe_retry.py` (fallback + new hints), `tests/test_tikz_analysis.py` (label/mark multiplicity), `tests/test_recipe_dsl.py` (annotations coercion), `tests/test_checks.py` (error provenance), `tests/test_eval_runner.py` (label re-scoring), `tests/test_to_tikz.py`, `tests/test_llm_judge.py`

## Dependencies & build

- Added `logfire>=4.34.0` and a hatchling `[build-system]` section. — `pyproject.toml`, `uv.lock`

## ⚠️ To clean before committing

- `util/llm_judge.py` has hardcoded local model overrides and debug `print()`s / logfire instrumentation that look like local-only changes.
- Many untracked run logs / output txts / a PDF / vim swap files / `nohup.out` / `ollama_run.txt` — should stay out of git.

---

# Results data (kept for reference; analysis deferred)

## Model Latency & Quality Benchmarks (2026-06-05)

> **TL;DR** — LLM API calls are 90–99% of total latency; local compute
> (lowering, IR pipeline, SVG render) is 20–250 ms regardless of model. On the
> hard scenario, five models solve first-try at 4–5/5 — deepseek-v4-flash
> (55s, 4/5), qwen3.5:397b (64s, 5/5), kimi-k2.6 (77s, 5/5), gemini-3-flash
> (102s, 4/5), deepseek-v4-pro (166s, 5/5); qwen3.5 is the quality+speed sweet
> spot. Retry cost is the hidden killer — models that fail output validation
> burn 100s of seconds (GLM-5.1 439s, nemotron-ultra 188s).

**Why:** profile single scenarios to choose which models drive the recipe
strategy — separating the cheap, fixed local-IR cost from the dominant,
variable LLM cost, and finding the tier that solves hard problems without
retries.

Single-scenario profiling using `profile_single_scenario.py` (recipe strategy, SVG renderer, thinking ON, gemma4:31b-cloud as visual judge where applicable).

### Easy Scenario — Right triangle on coordinate grid

| Model | Selection | Generation | IR Pipeline | Judge | Total w/ judge | Out tok/s | Outcome |
|---|---|---|---|---|---|---|---|
| gemma4:31b-cloud | 2.4s | 18.7s | 0.06s | 3.2s (5/5) | 24.5s | 69 | ✓ |
| nemotron-3-super:cloud | 2.6s | 9.9s | 0.03s | 0.4s (err†) | 13.0s | 109 | ✓ |
| nemotron-3-ultra:cloud | 1.2s | 39.3s | 0.02s | 0.4s (err†) | 41.0s | 42 | ✓ |
| glm-5.1:cloud | 3.3s | 8.8s | 0.03s | 0.4s (err†) | 12.6s | 92 | ✓ |

† These models don't support image input; visual judge failed fast with 400 error.

### Hard Scenario — Trapezoid with two reflections (12 vertices)

| Model | Selection | Generation (all attempts) | Retries wasted | IR Pipeline | Judge (gemma4) | Total w/ judge | Out tok/s | Judge Score | Outcome |
|---|---|---|---|---|---|---|---|---|---|
| **deepseek-v4-flash:cloud** | 1.4s | 46.8s (1 attempt) | 0s | 0.18s | 6.7s | **55.2s** | 182 | **4/5** | ✓ first try, tick marks off |
| **qwen3.5:397b-cloud** | 2.4s | 54.4s (1 attempt) | 0s | 0.25s | 6.7s | **63.8s** | 55 | **5/5** | ✓ first try |
| **kimi-k2.6:cloud** | 2.7s | 71.8s (1 attempt) | 0s | 0.17s | 2.3s | **77.0s** | 161 | **5/5** | ✓ first try |
| gemma4:31b-cloud | 1.5s | 83.0s (2 attempts) | 50.5s | 0.24s | 5.0s | 89.8s | 62 | 1/5 | ✓ but poor quality |
| gemini-3-flash-preview:cloud | 9.1s | 87.8s (1 attempt) | 0s | 0.23s | 4.7s | 102.0s | 182 | 4/5 | ✓ first try, label issues |
| **deepseek-v4-pro:cloud** | 9.6s | 152.9s (1 attempt) | 0s | 0.25s | 2.9s | **165.7s** | 65 | **5/5** | ✓ first try, slow |
| nemotron-3-ultra:cloud | 1.2s | 451.6s (2 attempts) | 187.5s | 0.22s | 2.9s | 456.2s | 11 | 5/5 | ✓ but very slow |
| minimax-m3:cloud | 1.1s | 428.8s (1 attempt) | 0s | 0.17s | 11.3s | 441.5s | 66 | 2/5 | ✓ but poor quality |
| glm-5.1:cloud | 1.4s | 606.7s (3 attempts) | 438.5s | 0.20s | 5.6s | 614.1s | 42 | 3/5 | ✓ after 3 tries |
| gpt-oss:120b-cloud | 1.2s | 112.3s (3 attempts) | 64.5s | 0.52s | 4.2s | 118.5s | 67 | 1/5 | ✓ but unreadable output |
| nemotron-3-super:cloud | 1.0s | 118.4s (3 attempts) | 118.4s | — | — | 119.7s | — | — | ✗ all 3 retries failed |

### Key Findings

1. **LLM API calls are 90–99% of total latency** — local computation (lowering, IR pipeline, SVG render) is 20–250ms regardless of model.
2. **DeepSeek-V4-Flash is the fastest capable model** — 55s total, 4/5 score, first-attempt success, and the highest throughput (182 out-tok/s). Only lost a point on tick mark placement.
3. **Qwen3.5:397b is the quality+speed champion** — 5/5 on first attempt at 64s. The sweet spot of quality and speed.
4. **Kimi-K2.6 is a strong contender** — also 5/5 on first attempt at 77s with 161 out-tok/s throughput. Slightly slower than qwen3.5 but with much higher throughput, suggesting it generates more thinking tokens. Bested deepseek-v4-pro (5/5, 166s) at half the latency.
5. **DeepSeek-V4-Pro gets 5/5 but isn't cost-effective** — 166s total is 2.6× slower than qwen3.5 and 2.1× slower than kimi-k2.6 for the same quality.
6. **Gemini-3-Flash-Preview is impressive for a "flash" model** — 102s total, 4/5 score, 182 out-tok/s throughput. Lost a point on labeling consistency.
7. **Five models achieved first-attempt success with 4–5/5 scores**: deepseek-flash (4/5, 55s), qwen3.5 (5/5, 64s), kimi-k2.6 (5/5, 77s), gemini-flash (4/5, 102s), deepseek-pro (5/5, 166s). This is the key tier — models that can solve hard problems without retries.
8. **Faster/smaller models fail on harder ones** — nemotron-super was fastest on easy (13s) but failed all 3 attempts on hard, wasting 119s.
9. **Retry cost is the hidden killer** — models that fail output validation waste enormous time: GLM-5.1 burned 439s on two failed attempts; nemotron-ultra burned 188s.
10. **MiniMax-M3 is a trap** — succeeded structurally on attempt 1 but produced 28k output tokens for a 2/5 score (429s wasted).
11. **Only gemma4 supports image input** for visual judging; using gemma4 as a dedicated judge works for all models.

---

## GEPA Prompt Optimization (2026-06-08)

> **TL;DR** — This section bundles three changes from the GEPA pass: (1) the
> recipe `generation_system` prompt was evolved — the empty prompt won
> (0.911 vs seed 0.802) but isn't production-viable, so **candidate 10** (0.900,
> a 2.4× longer JSON-wrapped prompt adding property/3D/rotation guidance) is the
> practical winner. (2) **Efficiency scoring** (retry + duration, weights
> 0.08/0.04) was added to the GEPA fitness so evolution rewards fewer retries
> and faster runs. (3) **Prime-notation normalization** in eval checks
> eliminated 129/130 false-negative property failures (noise GEPA was climbing
> against), +4.0pp pass rate.

**Why:** optimize the recipe generation prompt by evolution (GEPA); while
doing so, fix two things GEPA exposed — the fitness function didn't penalize
retry/latency, and the eval checker's prime-notation mismatch was injecting
false-negative noise into the very score GEPA was optimizing.

### What is GEPA?

GEPA (Genetic-Pareto Prompt Evolution) is an evolutionary prompt optimizer. It evaluates candidate prompts on a training set, builds reflective feedback from failures, and proposes mutations via a reflection LLM. The goal is to find improved versions of the recipe strategy's generation system prompt.

### Efficiency Scoring — Retries and Duration

The composite scoring function (`gepa_adapter/scoring.py`) now includes an **efficiency component** that rewards prompts that produce correct diagrams in fewer retries and less wall-clock time, relative to the seed baseline.

**Scoring formula:**

```
score = 0.35×gen_render + 0.22×gate + 0.18×props + 0.13×judge
      + 0.08×(baseline_attempts / actual_attempts)
      + 0.04×(baseline_duration_s / actual_duration_s)
```

| Component | Weight | Description |
|-----------|--------|-------------|
| Generation + rendering | 0.35 | Binary: did we produce a diagram? |
| Gate quality | 0.22 | Pass=0.22, soft_pass=0.13, fail=0.02–0.09 |
| Property checks | 0–0.18 | Pass rate of SymPy geometric checks |
| LLM judge | 0–0.13 | Subjective quality (optional) |
| **Retry efficiency** | **0.08** | `baseline_attempts / actual_attempts` — bonus for fewer retries, penalty for more |
| **Duration efficiency** | **0.04** | `baseline_duration_s / actual_duration_s` — bonus for faster, penalty for slower |

**Key design decisions:**

- **Both ratios are unbounded above**: a prompt that solves in 1 attempt what the seed took 3 attempts for gets a 3× retry bonus (0.24). This strongly rewards efficiency improvements.
- **Baseline from seed evaluation**: the first GEPA evaluation (always the seed candidate) records per-scenario attempt counts and durations. All subsequent evaluations compare against those baselines. If no baseline exists (shouldn't happen in normal use), both efficiency factors default to 1.0 (neutral).
- **Duration is total wall-clock** for `strategy.run()` (including recipe selection, generation, retries, and fallback). This is simpler and more representative than trying to isolate only generation time.
- **Hard failures short-circuit**: `generation_success=False` → score 0.0, regardless of efficiency.
- **Score capped at 1.0**: a perfect quality + strong efficiency bonus still caps at 1.0 via `min(score, 1.0)`.

### Files Changed for Efficiency Scoring

| File | Change |
|------|--------|
| `gepa_adapter/scoring.py` | Added `attempts` and `used_fallback` fields to `ScenarioResult`; rewrote `compute_score()` with new weights (0.35/0.22/0.18/0.13 + 0.08 retry + 0.04 duration); added efficiency info to `build_failure_feedback()` |
| `gepa_adapter/adapter.py` | Added `_baselines` dict for per-scenario seed tracking; timed `strategy.run()` with `time.monotonic()`; populated `duration_s`, `attempts`, `used_fallback` from `RecipeMetadata`; passed baselines to `compute_score()`; added efficiency metrics to reflective dataset |
| `optimize_recipe_prompts.py` | Added `seed_baselines.json` save; added baseline summary to printed output |
| `evals/run.py` | Added `attempts` and `used_fallback` extraction from `RecipeMetadata` in success and error paths |
| `tests/test_gepa_adapter.py` | Updated existing score expectations for new weights; added `TestEfficiencyScoring` class with 13 new tests covering retry/duration bonuses and penalties |

### Prime Notation Normalization in Eval Checks

**Problem:** Scenario YAML files use mathematical prime notation (`A'`, `A''`, `P'`) for point names in `expected_properties`, but the model produces different naming conventions (`A_prime`, `A_double`, `Aprime`, `A_p`, `A_p2`). The `pt()` helper in `evals/sympy_checks.py` did a direct `sym_float.get(name)` lookup, which failed with `KeyError` for every prime-notation point — causing 129 property check failures across 52 scenarios, all false negatives (the geometry was correct, just the naming was different).

**Impact on GEPA:** These false-negative property check failures (0.18 weight in the composite score) were a major noise source. GEPA's best candidate learned to tell the model "don't use primes" — but the model already used `_prime`/`_double` variants. The prompt change didn't fix the checker mismatch, and GEPA was optimizing against the wrong signal.

**Fix:** Added `_resolve_point_name()` in `evals/sympy_checks.py` that tries multiple naming variants when a direct lookup fails:

| Scenario notation | Model variants tried |
|---|---|
| `A'` | `A_prime`, `Aprime`, `A_p`, `Ap`, `A1`, `A_1` |
| `A''` | `A_double`, `A_double_prime`, `Adouble`, `Adoubleprime`, `A_p2`, `Ap2`, `A2`, `A_2` |
| `C'1` | `C_prime_1`, `C_prime1`, `C_p_1`, `C_p1`, `C1_prime`, `C1_p`, `C1prime`, `C1p` |
| `P1'` | `P1_prime`, `P1prime`, `P1_p`, `P1p`, `P1_1` |

**Results on eval data (201 scenarios):**
- Prime-notation lookup failures: **129 → 1** (99% elimination; the 1 remaining is a genuine model failure — the point wasn't created at all)
- Total property check pass rate: **86.1% → 90.1%** (+46 checks, +4.0pp)
- 13 scenarios fully fixed (all prime-related failures resolved), 4 partially fixed

**Files changed:**

| File | Change |
|------|--------|
| `evals/sympy_checks.py` | Added `_resolve_point_name()` with prime notation normalization; `pt()` now uses it for lookups |
| `tests/test_sympy_checks.py` | New test file with 29 tests: 20 for `_resolve_point_name`, 9 integration tests for `_validate_properties_sympy` with prime notation |

### GEPA Challenge Run Results (2026-06-09)

18 candidates explored over 9 hours (1720 metric calls / 1791 actual), optimizing the `generation_system` prompt on 86 challenge scenarios (61 curriculum failures + 12 tier-3 + 13 stress). Model: `ollama:gemma4:31b-cloud` with `ollama:deepseek-v4-pro:cloud` as reflection LM. Concurrency: 5 (effective ~2.3× speedup due to ollama.com throttling).

#### Score Progression

| Candidate | Score | Δ vs Seed | Prompt Length | Format |
|---|---|---|---|---|
| 0 (seed) | 0.8015 | — | 6,922 | Plain text |
| 2 | 0.8548 | +0.0533 | 6,945 | Plain text |
| 10 | 0.8997 | +0.0982 | 16,833 | JSON-wrapped |
| **15 (best)** | **0.9110** | **+0.1095** | **0** | **Empty** |

#### Key Findings

1. **The empty prompt won (0.911 vs seed 0.802)**, improving on 53 scenarios, regressing on 9. This means the model performs better when the system prompt is empty and it relies entirely on the user prompt (which contains the scenario, DSL docs, and recipe examples). The system prompt was likely adding conflicting or redundant instructions that hurt performance.

2. **7 scenarios went from 0 → nonzero** with the empty prompt — all were hard scenarios (3D solids, tangents) where the seed prompt's instructions may have confused the model. The seed prompt's rules about grid mode, polygon_exterior, etc. may have caused the model to over-constrain its output.

3. **The best non-empty prompt (cand 10, 0.900)** is a 2.4× longer JSON-wrapped version that adds detailed guidelines for expected properties, rotation solids, and 3D diagrams. This is a real improvement but still 1.1pp behind the empty prompt.

4. **The empty prompt regressed on only 2 perfect scenarios** (equilateral-triangle: 1.0→0.975, cyclic-quadrilateral-diagonals: 1.0→0.984) — tiny drops.

5. **The real practical winner is candidate 10** (0.900, 16.8K chars). The empty prompt isn't viable for production — it means no system-level control. Cand 10 adds ~9.6K chars of new guidance around property naming, 3D diagrams, and rotation solids, which are genuine improvements.

#### Recommendation

Use **candidate 10** as the new seed for a next round, or manually merge its additions into the current prompt. The empty prompt result tells us the current system prompt has room to be shorter/cleaner, but an empty prompt is not a valid production choice.

#### GEPA Metric Call Budget

`max_metric_calls` counts individual scenario evaluations, not rounds. Each GEPA iteration costs ~92 calls (3+3 train minibatch + 86 full val eval), plus 86 for the seed. With 86 scenarios, `max_metric_calls=1720` yielded 18 candidates over ~17 effective iterations. The initial run with `max_metric_calls=30` completed only the seed evaluation (86 calls > 30 budget) and stopped immediately.

---

## GEPA prompt ablation vs April reference (2026-06-22)

> **TL;DR** — On the 43 hard-intersection scenarios, every recipe run beats the
> gate-rescored April reference (structured/sonnet) on the deterministic gate
> (best +16pp), while April still leads on raw robustness/speed (40/43 gen, 0
> timeouts, 14s median). GEPA-optimized vs prior prompts is **mixed and
> model-dependent**: gemma4 +4.9pp (retry-aware), deepseek −9.9pp — and
> deepseek's optimized run is overconfident (CoT 4.95 vs a 37.5% gate). n=1 per
> cell, so none of the before→after deltas are separable from run-to-run
> backend noise yet.

This is the deferred analysis: does the recipe strategy with the current harness/checker changes and the GEPA-optimized prompts actually beat the prior prompts and the published April reference, on the 43 hard-intersection scenarios (`evals/scenarios_hard_intersection3.yaml`)? All code and checkers held fixed; only the recipe prompt text swaps between prior (pre-GEPA, git-HEAD) and on-disk GEPA-optimized via `--use-optimized-prompts`.

### Runs compared (clean runs only)

| label | jsonl | strategy / model | prompts |
|---|---|---|---|
| April ref | `20260413-170204_rescored_full.jsonl` | structured / claude-sonnet-4-6 | — (published) |
| recipe before, gemma4 | `20260622-123558.jsonl` | recipe / gemma4:31b-cloud | prior |
| recipe after, gemma4 | `20260620-194957.jsonl` | recipe / gemma4:31b-cloud | optimized |
| recipe before, deepseek | `20260622-123632.jsonl` | recipe / deepseek-v4-flash:cloud | prior |
| recipe after, deepseek | `20260620-195029.jsonl` | recipe / deepseek-v4-flash:cloud | optimized |

All recipe runs: tikz renderer, `--thinking --cot-analysis`, judge `ollama:gemma4:31b-cloud`, repeats=1. The April reference is the published structured/sonnet run on the 201-scenario curriculum; the 43 hard-intersection scenarios are a subset. It predates the judge and CoT analysis, so it has no judge/CoT cells.

The April reference was scored with the old checkers, so its stored gate on the 43 was 0/43 pass — almost entirely the mark_present / free-node-label false-positives that the current changes fix. To compare fairly its tikz-based gate checks were recomputed from its saved `tikz_code` with the current checkers (the curriculum yaml diff touches none of these 43 scenarios, so their `expected_properties` are unchanged). 11 records flipped fail→pass/soft. The rescored file is `20260413-170204_rescored_rescored_gate.jsonl`, produced by `evals/rescore_gate.py` (the full gate rescorer).

### Timeout classification

The 300s per-scenario timeout is an intentional guardrail against slow ollama-cloud backends, not a quality signal. A timeout can mean either the scenario kept retrying until the wall (retry-driven, prompt-attributable) or the backend was just slow that run (not prompt-attributable). The saved timeout records are zeroed (no attempt count), so the retry count is recovered by proxy: for each timeout, look at the same scenario in the paired run — if the paired run needed ≥2 attempts, the timeout is retry-driven; if it did it in 1 attempt, the timeout was backend-slow; if it also timed out, it's a both-timeout (scenario-hardness/backend, excluded from both sides).

Retry-aware gate: count retry-driven timeouts as fails; exclude backend-slow and both-timeout from the denominator.

| run | timeouts | retry / backend / both |
|---|---|---|
| April ref | 0 | — |
| recipe before, gemma4 | 6 | 2 / 3 / 1 |
| recipe after, gemma4 | 1 | 0 / 0 / 1 |
| recipe before, deepseek | 7 | 2 / 2 / 3 |
| recipe after, deepseek | 3 | 0 / 0 / 3 |

A direct check on whether the before's extra timeouts are a real quality difference: of deepseek's 7 before-timeouts, in the after run 3 also timed out and 4 completed but failed the gate — zero became passes. The after's lower timeout count is the optimized prompt bailing earlier (and a less-loaded 20:42 backend), not solving those scenarios. Every one of the 7 fails under both prompts. (gemma4 differs: 2 of its backend-slow before-timeouts passed in the after — backend-luck asymmetry at n=1.)

### Results on the 43 scenarios

| run | gate incl-timeout | gate retry-aware | gen/svg | judge | CoT conf | prop checks | dur median |
|---|---|---|---|---|---|---|---|
| April ref (sonnet/structured) | 11/43 = 25.6% | 25.6% | 40/43 | n/a | n/a | 85.2%† | 14s |
| recipe before, gemma4 (prior) | 12/43 = 27.9% | 12/39 = 30.8% | 37/43 | 3.51 (n=37) | 3.41 | 87.6% | 95s |
| recipe after, gemma4 (optim) | 15/43 = 34.9% | 15/42 = 35.7% | 42/43 | 3.52 (n=42) | 4.88 | 89.4% | 75s |
| recipe before, deepseek (prior) | 18/43 = 41.9% | 18/38 = 47.4% | 35/43 | 3.57 (n=35) | 2.53 | 91.6% | 73s |
| recipe after, deepseek (optim) | 15/43 = 34.9% | 15/40 = 37.5% | 38/43 | 3.58 (n=38) | 4.95 | 89.0% | 31s |

† April prop-checks use the old `sympy_checks.py` (not in the gate); treat as indicative only.

### Findings

1. **Every recipe run beats the April reference on the deterministic gate.** Even the worst recipe run (gemma4 before, 27.9% incl-timeout) clears April's 25.6%; the best (deepseek before, 41.9%) is +16pp. The recipe strategy plus the harness/checker changes beat the published April structured/sonnet result on these 43 hard scenarios, regardless of prompt variant.

2. **April still leads on raw robustness and speed.** 40/43 gen/svg (best), 0 timeouts, 14s median — sonnet renders reliably, but its diagrams fail more geometric checks (the gate gap). The recipe runs on ollama-cloud backends pay in timeouts and latency but produce more geometrically-correct diagrams.

3. **GEPA-optimized prompts vs prior: mixed, model-dependent.** gemma4 +4.9pp retry-aware (and +7pp incl-timeout, mostly from fewer timeouts). deepseek −9.9pp retry-aware (−7pp incl). The optimized prompts sharply raise CoT confidence for both models (gemma4 3.41→4.88, deepseek 2.53→4.95) — but for deepseek that confidence is misaligned with a lower gate: the prior run was underconfident (2.53 conf / 50% gate), the optimized run is overconfident (4.95 conf / 37.5% gate). Judge scores are flat (~3.5) across all recipe runs and don't discriminate.

4. **Per-scenario flips (retry-aware):** gemma4 net +1; deepseek net −3 (3 regressions — perpendicular-bisector-theorem, shadow-similar-triangles, arc-length-two-circles — and 0 improvements).

### Caveats

- n=1 per cell; none of the before→after deltas are separable from run-to-run backend noise at this sample size. A repeats≥3 re-run on both models and both prompt sets is the way to confirm, especially the deepseek negative.
- The residual `radius_marked` and other semantic mark_types remain uncheckable by design and floor all runs equally (visible as `radius_marked` in every run's top gate-failures).
- The deepseek −9.9pp is robust to the timeout convention: incl-timeout = −7pp, excl-all-timeouts = −12.5pp, retry-aware = −9.9pp; net flips −3 in all three.
## GEPA intersection run — candidate-15 evaluation (2026-06-23)

> **TL;DR** — Candidate 15 (a second GEPA step seeded from the first-GEPA
> optimized prompt) is **Pareto-better across both benchmarked models**: it
> keeps gemma4's first-GEPA gain (flat vs first-GEPA, +3 net vs pre-GEPA with no
> losses) and recovers deepseek (34.9→44.2%, +4 net flips vs first-GEPA with no
> losses). CoT confidence moves back toward healthy levels (deepseek 4.95→2.64
> alongside a *higher* gate). All three cand15 runs beat the gate-rescored
> April reference. n=1 per cell — not separable from backend noise.

A second GEPA optimization step (`gepa_runs/intersection`) re-optimized only the recipe `generation_system` prompt, starting from the on-disk optimized prompt (the first-GEPA "after" prompt above) as its seed. 18 candidates, best = idx 15 (val score 0.8614 vs seed 0.8162, +4.5pp on 28 val scenarios, clear max). Candidate 15's prompt (27013 chars) was written into `strategies/instructions_recipe.py` (`RECIPE_GENERATION_SYSTEM`), so `--use-optimized-prompts` now selects it. The seed = prior on-disk optimized prompt; recoverable via `gepa_runs/intersection/seed_candidate.json` and git commit `19c5230`. `RECIPE_SELECTION_SYSTEM` and `RECIPE_DSL_QUICK_REF` were unchanged by this run and remain unchanged.

### Runs compared (clean runs; n=43 hard-intersection)

| label | jsonl | strategy / model | prompts |
|---|---|---|---|
| April ref (gate-rescored) | `20260413-170204_rescored_rescored_gate.jsonl` | structured / sonnet-4-6 | — (published) |
| recipe before, gemma4 | `20260622-123558.jsonl` | recipe / gemma4:31b-cloud | prior (pre-GEPA) |
| recipe after, gemma4 | `20260620-194957.jsonl` | recipe / gemma4:31b-cloud | first-GEPA-opt |
| recipe cand15, gemma4 | `20260623-093231.jsonl` | recipe / gemma4:31b-cloud | intersection-GEPA |
| recipe before, deepseek | `20260622-123632.jsonl` | recipe / deepseek-v4-flash:cloud | prior (pre-GEPA) |
| recipe after, deepseek | `20260620-195029.jsonl` | recipe / deepseek-v4-flash:cloud | first-GEPA-opt |
| recipe cand15, deepseek | `20260623-093338.jsonl` | recipe / deepseek-v4-flash:cloud | intersection-GEPA |
| recipe cand15, qwen3.5 | `20260623-095106.jsonl` | recipe / qwen3.5:cloud | intersection-GEPA |

All recipe runs: tikz renderer, `--thinking --cot-analysis`, judge `ollama:gemma4:31b-cloud`, repeats=1. qwen3.5 has no pre-GEPA / first-GEPA baseline (first time run on this set). April reference: same rescored-gate file as the 2026-06-22 section (tikz gate recomputed from saved `tikz_code` with current checkers via `evals/rescore_gate.py`).

### Results on the 43 scenarios (gate = pass+soft)

| run | gate | gen/svg | timeouts | judge | CoT conf | dur median |
|---|---|---|---|---|---|---|
| April ref (sonnet/structured) | 8+3 = 25.6% | 40/43 | 0 | n/a | n/a | 14s |
| gemma4 before (prior) | 9+3 = 27.9% | 37/43 | 6 | 3.51 | 3.41 | 95s |
| gemma4 after (first-GEPA) | 11+4 = 34.9% | 42/43 | 1 | 3.52 | 4.88 | 75s |
| gemma4 cand15 (intersection) | 10+5 = 34.9% | 40/43 | 3 | 3.73 | 3.73 | 98s |
| deepseek before (prior) | 12+6 = 41.9% | 35/43 | 7 | 3.57 | 2.53 | 73s |
| deepseek after (first-GEPA) | 11+4 = 34.9% | 38/43 | 3 | 3.58 | 4.95 | 31s |
| deepseek cand15 (intersection) | 13+6 = 44.2% | 41/43 | 1 | 3.88 | 2.64 | 49s |
| qwen3.5 cand15 (intersection) | 10+2 = 27.9% | 35/43 | 8 | 3.74 | 4.17 | 108s |

All candidate-15 timeouts are backend-slow (single 300s hit, zero retries, `attempts` unset), not retry-driven.

### Per-scenario gate flips (pass+soft set)

vs April ref: gemma4 cand15 +5/−1 (net +4); deepseek cand15 +8/−0 (net +8); qwen3.5 cand15 +3/−2 (net +1).

Across the same-model progression:
- gemma4: before→first-GEPA +4/−1 (net +3); first-GEPA→cand15 +3/−3 (net 0, churn); before→cand15 +3/−0 (net +3, clean).
- deepseek: before→first-GEPA +0/−3 (net −3); first-GEPA→cand15 +4/−0 (net +4); before→cand15 +2/−1 (net +1).

### Findings

1. **Candidate 15 is Pareto-better than both prior prompts across the two benchmarked models.** The first-GEPA run was lopsided: it lifted gemma4 (+7pp, 27.9→34.9) but hurt deepseek (−7pp, 41.9→34.9) while inflating deepseek CoT confidence (2.53→4.95) — overconfidence vs a lower gate. Candidate 15 keeps the gemma4 gain (flat vs first-GEPA, +3 net vs pre-GEPA with no losses) and recovers deepseek (34.9→44.2, +4 net vs first-GEPA with no losses; +1 net vs its own pre-GEPA baseline). Net vs the pre-GEPA baseline: gemma4 +3, deepseek +1. Net vs April (rescored): gemma4 +4, deepseek +8.

2. **CoT confidence moves back toward pre-GEPA levels under candidate 15.** gemma4 4.88→3.73, deepseek 4.95→2.64 — i.e. the intersection prompt trades the first-GEPA run's verbose confidence for correctness, the healthier direction (deepseek: lower confidence, higher gate). Judge scores also peak at candidate 15 for both (gemma4 3.52→3.73; deepseek 3.58→3.88).

3. **All three candidate-15 runs beat the gate-rescored April reference on the deterministic gate** (gemma4 34.9% vs 25.6% = +9.3pp; deepseek 44.2% vs 25.6% = +18.6pp; qwen3.5 27.9% vs 25.6% = +2.3pp). April still leads raw robustness/speed (40/43 gen, 0 timeouts, 14s median); the recipe runs on ollama-cloud backends pay in timeouts/latency but produce more geometrically-correct diagrams.

4. **qwen3.5 (new model, candidate-15 only) is the weakest on robustness:** 8 backend timeouts, 35/43 generated. Gate (27.9%) still clears April but barely; no pre-GEPA/first-GEPA baseline exists to say whether candidate 15 helps qwen specifically.

### Caveats

- n=1 per cell; the deepseek +4 vs first-GEPA and the gemma4 +3/−3 churn are not separable from run-to-run backend noise. A repeats≥3 re-run across all three prompt sets (prior / first-GEPA / candidate-15) on gemma4 and deepseek is the way to confirm the deepseek recovery and the gemma4 churn-vs-flat.
- April has no judge/CoT cells (predates those), so only the gate column is directly comparable there.
- The residual `radius_marked` and other semantic mark_types remain uncheckable by design and floor all runs equally.
## DSL_DOCS guidance lift + op-coverage gaps (2026-06-23)

> **TL;DR** — Lifted cross-cutting rules + per-op notes + missing-op docs into
> `DSL_DOCS` (the always-on DSL reference). A/B'd across 4 runs (deepseek +
> gemma4 × v1/v2): **net-negative-to-neutral, never positive** — +0 new passes
> vs base in all four runs. Decision: **reverted** to HEAD
> (`recipe/catalog.py` back to 12,628 chars); candidate-15 alone remains the
> optimized generation prompt. The op-coverage gaps are real docs gaps, but
> documenting them did not help the gate. n=1 per cell.

Two-pronged improvement to the recipe-strategy **DSL reference** (`DSL_DOCS` in `recipe/catalog.py`), the always-on text injected into every generation prompt via `build_generation_prompt`. This is the *other* GEPA-able prompt surface (alongside `RECIPE_GENERATION_SYSTEM`); `RECIPE_SELECTION_SYSTEM`, `RECIPE_DSL_QUICK_REF` (still dead code), and the candidate-15 generation prompt are unchanged.

Motivation: the recipe selector picks 0 recipes ~49% of the time, so half of generations go through a "freehand" path that gets the DSL reference but **no** recipe `notes` (those are only delivered when a recipe is selected). The freehand path therefore never sees the cross-cutting survival rules the recipe notes encode, and — worse — DSL_DOCS itself was missing several ops the recipes actively use.

### Method: note-filtering pass

Dumped all 92 `notes` items across the 20 recipes in `recipe/recipes/default/*.yaml` (via `load_recipe`, i.e. exactly what `build_generation_prompt` sends on selection) and classified each into three tiers. Full mapping in `tmp/dsl_docs_note_mapping.md` (scratch, gitignored).

- **Tier 1 — cross-cutting (→ new general-rules block):** 5 rules recurring across recipes, not owned by a single op.
- **Tier 2 — op-generic (→ inline next to the op's reference line):** guidance that applies whenever that DSL op is used.
- **Tier 3 — recipe-specific (→ stays in the YAML):** per-recipe construction rationale, coordinate choices, vertex naming, domain math facts, and the transversal angle-pair scheme. ~50–55 of 92. Already delivered on the selection path; lifting would be noise for the 51% of generations where the recipe is irrelevant.

### What changed in DSL_DOCS (12,628 → 18,459 chars)

1. **New "Construction rules (apply to every op)" block** near the top, with the 5 Tier-1 rules: define-before-reference / construction order; hide scaffolding (`visible:false` for helper points, symmetry axes, transversal guides, infinite lines); prefer named constructions over hand-placed coords (let SymPy compute); disambiguate every intersection (concrete selector, never bare/`index`); inconsistent constraints → closest valid build + `label_only`.

2. **Inline per-op HOW notes** (Tier 2): altitude (foot outside base for obtuse), circumcircle (circumcenter outside for obtuse), perpendicular_bisector (infinite line → `visible:false` + segments; define P/Q first; `mid` field), angle_bisector (`between` selector for opposite-side hit), ellipse (hradius = axis/2; prefer `show_coords` over hardcoded text), polygon_exterior (`ref_point`/`vertices` semantics), polygon_from_angles_and_sides (index semantics, angle-sum = (N−2)·180, parallelogram angle pattern, closure-failure handling), tangent_line (P outside circle; selector disambiguation; segment not line), plus a `mark_right_angle` addendum (mark at the real foot/tangent point, not a free interior point).

3. **Op-coverage gaps (higher-leverage than the prose — ops the recipes use but DSL_DOCS never documented):**
   - `polygon_from_sides` — a separate op from the Foundation `polygon` (computes vertices from side lengths; max-area/cyclic placement; polygon inequality; no angle constraints); the recipe literally named after it used an op the model had never been shown.
   - `circle_through_3` — circumcircle through any 3 points (chain after the polygon when circumscribing).
   - `point_foot` — foot of perpendicular from a point onto a segment/line/ray, with its `CRITICAL` constraint that `onto` MUST be a segment id, not a Triangle id.
   - `mark_equal_lengths` / `mark_parallel` / `mark_proportional` — added in a new `annotations.marks` subsection (DSL_DOCS previously documented only `mark_angle`/`mark_right_angle`).

### Verification

`recipe.catalog` imports; `build_generation_prompt` builds (18,738 chars, new header present); 145 recipe/eval tests + 37 catalog tests pass (`test_recipe_catalog.py` only asserts `DSL_DOCS` is a `str` of length >100, so unaffected). No renderer/LLM needed — this is a prompt-text change.

### Validation results — first run (DSL_DOCS v1: 5-rule block + inline notes + op entries)

A/B vs the candidate-15 baseline (pre-DSL_DOCS-edit) on the 43 hard-intersection scenarios. Same config (tikz, `--thinking --cot-analysis`, judge `ollama:gemma4:31b-cloud`, repeats=1). Run files: deepseek `20260623-150256.jsonl`, gemma4 `20260623-150218.jsonl` (still running at analysis time, 37/43).

| run | n | gate (pass+soft) | gen/svg | timeouts | judge | CoT conf | dur med |
|---|---|---|---|---|---|---|---|
| deepseek cand15 (base) | 43 | 44.2% (13+6) | 41/43 | 1 | 3.88 | 2.64 | 49s |
| deepseek DSL_DOCS v1 | 43 | 37.2% (12+4) | 37/43 | 6 | 4.08 | 2.89 | 45s |
| gemma4 cand15 (base, same 37) | 37 | 40.5% (10+5) | 34/37 | 3 | 3.82 | 3.71 | 98s |
| gemma4 DSL_DOCS v1 (37/43) | 37 | 40.5% (11+4) | 33/37 | 4 | 3.70 | 4.00 | 105s |

Per-scenario gate flips vs base: deepseek **+0 / −3** (net −3); gemma4 (same 37) **+2 / −2** (net 0). Label/geometry failure counts dipped slightly (deepseek label 15→9, geometry 20→17; gemma4 geometry 27→23) but that did not translate into gate gains — offset by more timeouts and lost scenarios.

**Verdict: not an improvement.** deepseek regressed (−7pp, +5 timeouts, −3 net flips); gemma4 net-neutral on the same 37 (pass+soft count identical at 15, +2/−2 flips). The +5 deepseek timeouts coincided with US-morning cloud load (a likely confounder — some timeouts plausibly transient), but the DSL_DOCS v1 prompt was also ~5.8k chars larger (12,628→18,459), which raises latency/timeout pressure on the slow backend. n=1 per cell → not separable from run noise; repeats≥3 needed to confirm the deepseek regression.

### Validation results — v2 run (deepseek + gemma4, 2026-06-23)

v2 = DSL_DOCS with the 5-rule block held out (op-entries + inline notes only, 16,677 chars) + the `perpendicular_bisector` note fix. Run files: deepseek `20260623-175648.jsonl` (43), gemma4 `20260623-191432.jsonl` (43).

| run | n | gate (pass+soft) | gen/svg | timeouts | judge | CoT conf | dur med |
|---|---|---|---|---|---|---|---|
| deepseek cand15 (base) | 43 | 44.2% (13+6) | 41/43 | 1 | 3.88 | 2.64 | 49s |
| deepseek DSL_DOCS v1 | 43 | 37.2% (12+4) | 37/43 | 6 | 4.08 | 2.89 | 45s |
| deepseek DSL_DOCS v2 | 43 | 34.9% (10+5) | 39/43 | 3 | 3.87 | 2.98 | 46s |
| gemma4 cand15 (base) | 43 | 34.9% (10+5) | 40/43 | 3 | 3.73 | 3.73 | 98s |
| gemma4 DSL_DOCS v1 | 43 | 34.9% (11+4) | 37/43 | 6 | 3.62 | 3.97 | 105s |
| gemma4 DSL_DOCS v2 | 43 | 32.6% (10+4) | 41/43 | 2 | 3.76 | 3.83 | 89s |

Per-scenario flips vs base: **deepseek v2 +0 / −4** (net −4); **gemma4 v2 +0 / −1** (net −1; lost `rotation-function`). v2 vs v1: deepseek +1 / −2 (net −1); gemma4 +1 / −2 (net −1; recovered `perpendicular-bisector-theorem`, lost `trapezoid-midsegment` + `quadrilateral-hierarchy`).

**Combined verdict across all 4 runs (deepseek v1/v2 + gemma4 v1/v2): the DSL_DOCS change is net-negative-to-neutral, never positive.** The decisive signal: **+0 gained vs base in all four runs** — the DSL_DOCS edit (any variant, either model) did not unlock a single new pass that base was failing. The op-coverage hypothesis (newly-documented ops help the freehand path) is not borne out: deepseek likely already used those ops adequately (strong model), and gemma4's variance is dominated by selection/freehand noise, not op availability. Net per model: deepseek clearly negative (v1 −3, v2 −4; gate 44.2→37.2→34.9); gemma4 neutral-to-slightly-negative (v1 0, v2 −1; gate 34.9→34.9→32.6, within n=1 noise).

**Two real but non-decisive effects of the v2 trim:** (1) robustness improved — gemma4 v2 gen 41/43, timeouts 2, dur 89s (best of the three); deepseek v2 timeouts 6→3, gen 37→39. Supports the smaller-prompt → less-timeout-pressure hypothesis, partly confounded by run timing (v2 off-peak evening vs v1/base daytime). (2) The `perpendicular_bisector` fix was **model-dependent**: it recovered `perpendicular-bisector-theorem` for gemma4 (v1 fail missing `['l']` → v2 soft_pass) but NOT for deepseek (still fail missing `['l']`). So inline-note micro-tuning has weak and inconsistent causal leverage on the gate relative to run noise.

**The v2 losses are generation/selection variance, not op-spec defects:**
- deepseek `exterior-angles-polygon`: base selected `polygon_from_sides` (pass); v1+v2 both went freehand (selection drift unrelated to DSL_DOCS); v2 failed `exterior_angle_at_B/C`. Freehand variance.
- deepseek `shadow-similar-triangles`: same recipe (`similar_triangles`) in base/v1/v2; v2 failed `right_angle_at_B/D` + perpendicularity. Generation variance within an unchanged recipe.
- deepseek `trapezoid-midsegment`: still fails `D_on_segment_MT` (freehand, persistent v1→v2).
- gemma4 `rotation-function`: lost in v1 and v2 (`mark_rotation_angle`, freehand) — likely the uncheckable-semantic-mark floor or mark noise.

**Decision: revert DSL_DOCS to pre-edit (git HEAD).** The DSL_DOCS surface isn't paying off — it costs deepseek ~7-9pp and gains nothing on either model — so the clean state is candidate-15 alone as the optimized generation prompt. The experiment record is preserved in this changes.md section + the `DSL_CONSTRUCTION_RULES` constant + `tmp/dsl_docs_note_mapping.md` for any future evidence-driven re-introduction. The op-coverage gaps (`polygon_from_sides`, `circle_through_3`, `point_foot`, the mark kinds) are real documentation gaps, but documenting them did not help the gate, so they revert to undocumented for now (recoverable from git diff).

**Revert applied (2026-06-23):** `git checkout HEAD -- recipe/catalog.py` — DSL_DOCS back to 12,628 chars (pre-edit), `DSL_CONSTRUCTION_RULES` constant removed. `recipe/catalog.py` clean at HEAD; only `changes.md` carries the experiment record. Optimized prompt remains candidate-15 (`RECIPE_GENERATION_SYSTEM` in `strategies/instructions_recipe.py`, unchanged). Next eval A/B should use this clean baseline.

### Root-cause dive on the lost scenarios

Inspected each lost scenario's failing checks + construction (base-pass vs new-fail):

- **`perpendicular_bisector_theorem` — deepseek AND gemma4 (the only shared regression).** Same recipe selected in base and new (`perpendicular_bisector`), so this is a generation change, not selection. Both new runs failed `required_labels` **missing `['l']`** — the perpendicular bisector line the prompt explicitly says to "call it line l" was not drawn/labeled. Root cause: the v1 inline `perpendicular_bisector` note said "It is an infinite line — set visible:false and draw what to show as explicit segment ops"; the model applied "hide the infinite line" to line `l`, which is the *requested* object, not scaffolding. Read as a specific, reproducible (both models) op-spec defect at the time. **A fix was applied for v2** (condition `visible:false` on scaffolding-vs-requested); the v2 run showed it was **model-dependent** — it recovered the scenario for gemma4 (v1 fail → v2 soft_pass) but NOT for deepseek (still fail missing `['l']`). The earlier "reproducible defect" read was over-confident; the outcome is dominated by run/model variance, not the note text (see "Validation results — v2 run" above).
- **`sas_proof_circle` — deepseek.** `required_labels` missing `C'1, C'2`. Selection changed (base `similar_triangles` → new `polygon_from_angles_and_sides`, a newly-documented op); the new op didn't produce/label the constructed third-vertex labels the scenario expects. Mixed: a mis-selection (likely noise — the selection prompt and catalog descriptions were not touched) plus a possible labeling gap in `polygon_from_angles_and_sides` usage. Not cleanly attributable at n=1.
- **`trapezoid_midsegment` — deepseek.** `D_on_segment_MT` (geometry). Both runs freehand (`sel=[]`); new placed D off segment MT. Freehand coordinate slip — plausibly noise.
- **`rotation_function` — gemma4.** `mark_rotation_angle` (mark). Both freehand. A mark check flipped — likely the uncheckable-semantic-mark floor (see memory `mark-present-checker-fix`) or mark noise. Not op-spec-tied.

Summary: 1 clear op-spec defect (`perpendicular_bisector` `visible:false` over-generalization, both models — fixed); 1 ambiguous (`polygon_from_angles_and_sides` mis-selection + labeling); 2 likely-noise freehand slips.

### DSL_DOCS v2 (current on-disk state)

Two changes after the v1 analysis:

1. **5-rule "Construction rules" block held out** (ablation, per the op-coverage-only hypothesis). The block text is preserved as a separate `DSL_CONSTRUCTION_RULES` constant in `recipe/catalog.py` (not injected into the prompt) so it can be edited and re-injected later (fold into `DSL_DOCS`, or pass via `prompt_overrides["dsl_docs"]` for a clean A/B). `DSL_DOCS` is now op-entries + inline per-op notes only (18,459 → 16,677 chars). This is the smaller-prompt variant that should cut the timeout pressure while keeping the coverage.
2. **`perpendicular_bisector` inline note fixed** to condition `visible:false` on scaffolding-vs-requested: "If the prompt asks for the bisector itself (e.g. 'call it line l'), DRAW and LABEL it. Only set visible:false when the bisector is pure scaffolding." The same EXCEPTION caveat was added to `DSL_CONSTRUCTION_RULES` rule 2 so re-injection won't reintroduce the bug. **Note: the v2 deepseek run showed this fix was ineffective for its target scenario** (see v2 results above).

v2 deepseek run: done (negative — see above). v2 gemma4 run: in progress. Revert decision held pending gemma4.

### Caveats

- n=1 per cell throughout; the deepseek −7pp / −3 flips / +5 timeouts are not separable from run-to-run backend noise (compounded by US-morning cloud load on the timeout count). repeats≥3 on deepseek (cand15-base vs DSL_DOCS v2) is the way to confirm.
- DSL_DOCS is always injected, so the edit affects both the selected-recipe and freehand paths.
- DSL_DOCS is a GEPA-able surface; a future GEPA run could mutate it. The inline notes and `DSL_CONSTRUCTION_RULES` are written terse/rule-like to survive optimization.
- The cross-cutting "coordinate/canvas convention" (`axes:true` + `show_coords:true`) was deliberately NOT added — DSL_DOCS already has a dedicated "Coordinate geometry canvas setup" section covering it; elevating it would duplicate.

## Self-reported, metadata-first confidence

> **TL;DR** — We asked the model to rate its own confidence *before* it builds the
> diagram (not after). The verdict: it is a real **ranking** signal — it
> separates passing diagrams from failing ones better than the free CoT analyzer
> and the expensive LLM judge on the hard tier — but it is **not a trustable
> number**: failures still come scored 85–100, so you can't gate on an absolute
> threshold. Use it as a relative "flag the least-confident" signal after
> per-model recalibration, not as a probability. One pre-construction call
> ("hard") carries the signal; the in-call structured field ("soft") is flat.
> The three reported dimensions are redundant. The earliest pipeline failures
> (unparseable output) are invisible to it by construction.

### Why we tried this

We want a cheap model-internal confidence signal for generated diagrams, usable
online — where sampling many candidates to measure entropy is too slow. Two
prior signals failed to be useful:

- the **LLM judge** reviews the *finished* diagram and tends to rationalize it
  (returned a near-constant score);
- the deterministic **`cot_analyzer`** scans the chain-of-thought *after* the
  fact and inverts on terse-confident models (it flags clean passes and misses
  terse-wrong fails).

Both are *post-hoc* — they assess an artifact the model already committed to.
The hypothesis here: elicit the assessment **before** the model commits to the
construction (a *prospective* prediction), so it can't anchor on / rationalize
its own output.

### The idea: hard vs soft

One shared schema (`EvaluationMetadata`: three 0–100 dimensions —
`geometric_correctness`, `request_ambiguity`, `end_to_end` — plus a
`contradictions_found` flag). Two ways to elicit it, differing in how strongly
the assessment precedes the construction:

- **hard** — a *separate, independent* model call that emits a fenced
  `[[INTERNAL_METADATA]]…[[END_METADATA]]` block before any construction
  exists. Strongest pre-commitment guarantee (no construction tokens at all).
- **soft** — `evaluation_metadata` as the **first field** of the structured
  generation output, emitted before the `recipe` construction within the same
  call. Weaker guarantee (the model is already in "build mode").

Both see the same prompt context (DSL reference + selected recipes + the
request) and the same generation rules. The prelude reuses the generation system
prompt with only its "output RecipeDSL" line stripped (so it doesn't contradict
the fence request); the real generation call keeps that line. The prelude is an
independent agent, so the hard score is not anchored to the soft score — they're
directly comparable per record.

### What we found

Two runs (deepseek-v4-flash + gemma4, 43 hard-intersection scenarios each,
repeats=1). Tier-2 is the only adequately-powered cell (n≈22); tier-3 is n=3–6
(directional only). Numbers below are the lenient label (pass+soft_pass vs fail);
the strict label (pass vs fail) agrees within ~0.02 on tier-2.

**1. Hard discriminates; soft is flat — the pre-commitment ordering wins.**

| cell | hard AUC [95% CI] | soft AUC | cot (free) | judge (costly) |
|---|---|---|---|---|
| deepseek t2 | **0.82 [0.65, 0.96]** | 0.55 | 0.62 | 0.57 |
| gemma4 t2   | **0.69 [0.57, 0.81]** | 0.50 | 0.58 | 0.68 |

Hard beats the free CoT baseline on both and beats the costly judge on deepseek.
Soft is flat (~0.50: passes and fails both score ~93–100). The pure-prospective
prelude is more honest than the structured field emitted mid-construction — the
anti-anchoring hypothesis holds. **The extra prelude call earns its keep; soft
is not worth gating on.**

**2. But it is badly miscalibrated and silently overconfident — not a trustable
probability.** Brier 0.5–0.67, ECE 0.5–0.67. Failures score 85–100; the
silently-overconfident rate (fail ∧ score ≥ 80) is 86–100% on adequate cells.
Absolute-threshold flagging is useless (`score<40 → fail` recall ~0.06–0.14 —
failures sit at ~85–92, not low). The score is a **ranking signal, not a
probability.** The decision gate (`AUC>0.5 ∧ beats-cot ∧ overconf-ok`) fails the
last condition everywhere — real discrimination, but not safe for absolute-
threshold trust-gating.

**3. The three dimensions are redundant — no per-dimension value.**
`geometric_correctness` and `end_to_end` are nearly identical (corr ~0.985;
literally equal 33% of deepseek runs / 76% of gemma4). `request_ambiguity` is
weakly distinct (corr ~0.5) but *not* consistently better (weaker on deepseek,
marginally better on gemma4 t2). No dimension dominates; the headline hard AUC
(uses `geometric_correctness`) is representative. **Collapse to a single
confidence; don't expect per-subsystem diagnosis.**

**4. No pipeline-stage correlation — and the worst failures are invisible.**
Record-level failures are almost all one bucket: the diagram rendered but a
deterministic geometric/label property was wrong (only ~1 generation failure).
At the attempt level, confidence exists only for `success` and `ir_pipeline`
stages — `lowering`/`output_validation` failures have **no soft score** because
the output didn't parse. So confidence is structurally blind to the earliest
(worst) failures. The one faint signal: deepseek scores ~4–5 points lower on
attempts that fail at ir_pipeline; gemma4 is flat at 100. (A coverage-gap note:
gemma4 had 14/61 attempts with no soft, all 14 failed — soft AUC is over the
parseable subset only; hard covers those.)

**5. Model-dependent; gemma4 inverts on the hard tier.** deepseek's hard
confidence spreads on tier-3 (passes ~80, fails as low as 0/20/60). gemma4
*inverts* on tier-3 (more confident on the scenarios it fails) — the
terse-confident-wrong pattern. n=3–5, directional only, but it means hard can't
be trusted as a raw signal for gemma4 on hard tiers without per-model
recalibration.

**6. `contradictions_found` is a marginal binary booster** — 0.75 precision-
for-fail (4 records flagged, 3 failed), tiny n. Not stage-correlated, just
weakly fail-correlated.

### What to do with this

- **Keep hard; don't gate on soft.** Record both (soft is free — it's a field in
  the call we already make), but only hard is actionable.
- **Don't use the raw 0–100 as a trust probability.** For online use, either
  recalibrate per model (isotonic/Platt on a labeled set, so the 85–100 band maps
  to real fail rates) or use it **relatively** (flag the bottom-N per batch), not
  an absolute threshold.
- **Get more, independent data.** Prefer the 201-scenario curriculum **once** over
  43×3. 201×1 gives 201 independent (confidence, outcome) pairs and is the
  online-relevant quantity (one draw per request); 43×3 gives 129 records but only
  43 independent scenarios (pseudoreplication — the record-level bootstrap CIs
  would be anti-conservative), and it averages over draws you won't have in
  production. 201×1 also firms up tier-3 and tests generalization beyond the
  intersection slice.
- **If per-stage diagnosis becomes a goal**, elicit confidence *after*
  lowering/compile (a two-pass reflection) — the pre-construction prelude can't
  see unparseable-output failures by design.

### How it's wired (reference)

- **`strategies/confidence.py`** — `EvaluationMetadata` schema (3 dims +
  contradictions, `extra="ignore"`); `RecipeGenerationOutput` wrapper (soft);
  fence parser + `PRELUDE_OUTPUT_INSTRUCTION` (hard);
  `strip_generation_output_instruction` (strips the generation output-format
  line for the prelude only); `geo_correctness_score` helper.
- **`strategies/recipe.py`** — `RecipeStrategy.confidence_mode: none|structured|
  prelude|both`. Class default `none` (so the web app / `dry_run` keep the old
  pipeline); eval default `both`. Hard/soft metadata persisted on
  `RecipeAttemptTrace` and `RecipeMetadata` (on success and on lowering/ir-
  pipeline failure; on output-validation failure the hard prelude score still
  survives). On the failure path the nested fields fall back to the last
  attempt's metadata (consistent with the flat fields), so complete failures
  aren't silently dropped from the analysis.
- **`evals/run.py`** — `--confidence-mode` flag; per-record flat
  `self_confidence_hard_score` / `self_confidence_soft_score` and nested
  `recipe_metadata.evaluation_metadata_{hard,soft}`.
- **`evals/analyze_confidence.py`** — pure-stdlib analyzer (no numpy/scipy/
  sklearn in this env): AUC-ROC via Mann-Whitney ranks + bootstrap 95% CIs,
  Brier, ECE, Cohen's d, PR of `flag<T→fail`, silently-overconfident rate,
  contradictions precision, coverage gap. Stratified by model×tier (never
  pooled). Truth label: strict `pass vs fail` (default) or `--lenient`
  (pass+soft_pass vs fail). Decision gate per cell. All knobs are named
  constants (quick-reference table in the module docstring).
- **Tests** — `tests/test_confidence.py` (24) + `tests/test_analyze_confidence.py`
  (13): schema/field-order, fence-parser variants, the four modes, hard/soft
  independence, the prelude-uses-generation-rules-and-real-call-keeps-the-line
  invariant, metadata capture on lowering failure, the hard-on-complete-failure
  fallback, and lenient vs strict labels.

### Reproducing the numbers

Source runs: `output_run_hard_intersect_tikz_{deepseek-v4-flash_1_7,gemma4_1_9}.txt`
→ `evals/results/20260625-134136.jsonl` (deepseek) and
`evals/results/20260625-134130.jsonl` (gemma4).

```
python -m evals.analyze_confidence --results <jsonl> --n-boot 2000          # strict
python -m evals.analyze_confidence --results <jsonl> --n-boot 2000 --lenient # pass+soft_pass vs fail
```

Caveats on these two runs: repeats=1 (wide CIs, especially tier-3 n=3–6 — treat
tier-3 as directional); the hard-intersection slice is narrow (intersection
problems only, not the full curriculum); both runs used the GEPA-optimized
on-disk prompts. Strict and lenient agree on the tier-2 headline (0.82 / 0.69),
so the conclusion is robust to the label choice.
