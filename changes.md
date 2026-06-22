# feat/recipe-improvements — Change Inventory

_Last updated: 2026-06-22_

**Baseline:** last commit `db17ae5` on `master`. Everything below is the content of the `feat/recipe-improvements` branch (commit `19c5230`, pushed to `origin`) vs that baseline. Analysis of whether the changes actually helped (GEPA payoff, CoT-analysis usefulness, etc.) is deferred — this file is just an inventory of what changed and why.

---

## Themes

- **Tolerate model quirks** — backends without tool-call support, models that emit annotations in the wrong shape, and cryptic validation errors.
- **Better retry guidance** — use the actual error text to give specific advice instead of generic hints.
- **Fallback path** — when the recipe strategy runs out of retries, try the structured strategy so a diagram is still produced.
- **GEPA prompt work** — optimized prompts, plus a way to run the optimized vs the prior prompts with everything else unchanged.
- **Confidence signal from CoT** — read the model's reasoning to flag low-confidence outputs and compare against the pass/fail gate.
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
- **Curriculum scenario tweaks** — small edits to the curriculum scenarios. — `evals/scenarios_geometry_curriculum.yaml`
- **New scenario files** — hard-intersection / hard3 / hard-failures / hard-stress / smoke variants and GEPA train/val/challenge sets, for running failing and stress subsets. — `evals/scenarios_*.yaml` (new)

## Tooling scripts (new, untracked)

- **Run scripts** — per-benchmark eval launchers (curriculum, hard-intersect, stress, hard-stress) with fixed judge model and auto-named logs. — `run_geometry_*_eval.sh`
- **Renderer start script** — start the bare-metal TikZ renderer. — `start_tikz_renderer.sh`
- **Profiling** — per-phase timing of one scenario (selection → generation → lowering → IR → judge). — `profile_single_scenario.py`
- **Failing-scenario extraction** — build a new scenarios YAML from the gate-failures of one or more runs (intersection/union). *Why: re-run evals over just what's failing.* — `evals/extract_failing_scenarios.py`

## Tests (new + expanded)

- New: `tests/test_cot_analyzer.py`, `tests/test_cot_analysis_failure.py`, `tests/test_dsl_validation.py`, `tests/test_gepa_adapter.py`, `tests/test_sympy_checks.py`, `tests/test_ollama_compat.py`
- Expanded: `tests/test_recipe_retry.py` (fallback + new hints), `tests/test_tikz_analysis.py` (label/mark multiplicity), `tests/test_recipe_dsl.py` (annotations coercion), `tests/test_checks.py` (error provenance), `tests/test_eval_runner.py` (label re-scoring), `tests/test_to_tikz.py`, `tests/test_llm_judge.py`

## Dependencies & build

- Added `logfire>=4.34.0` and a hatchling `[build-system]` section. — `pyproject.toml`, `uv.lock`

## ⚠️ To clean before committing

- `util/llm_judge.py` has hardcoded local model overrides and debug `print()`s / logfire instrumentation that look like local-only changes.
- Many untracked run logs / output txts / a PDF / vim swap files / `nohup.out` / `ollama_run.txt` — should stay out of git.

---

# Results data (kept for reference; analysis deferred)

## Model Latency & Quality Benchmarks (2026-06-05)

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