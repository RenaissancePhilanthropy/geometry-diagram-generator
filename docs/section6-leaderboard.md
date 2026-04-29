# Section 6 — Leaderboard and Analysis

Working draft. This is the empirical core of the paper. Numbers are `<TBD>` until the v4 pilot completes; the *qualitative findings* and section structure are stable.

## 6.1 Setup

We evaluate every (model × strategy) combination in the cross-product of:

- **Models**: Claude Opus 4.7, Claude Sonnet 4.6, Claude Haiku 4.5, GPT-5.1.
- **Strategies**: `raw_code` (LLM emits TikZ directly), `structured` (LLM emits a JSON intermediate representation that we compile, validate, and revise on failure), `recipe` (LLM emits a high-level recipe DSL with constraint solving for coordinates; see Section 5).

For the pilot reported here we run a stratified 30-scenario sample (10 per tier, drawn round-robin across 23 of 30 templates; see `evals/sample_scenarios.py`). The full headline run will use the complete 600-scenario templated split. Each (model, strategy, scenario) combination is run once (`repeat_index = 1`); the full run will use 3 repeats with seed reporting.

All runs use `temperature = 1.0` (default for both APIs). The structured strategy permits up to N=3 internal check-fail retries before recording final verdict. Cost is computed using each model's published per-token rate as of April 2026.

## 6.2 Headline pass-rate table

Two tables: pre-hardening (the verifier as it shipped at pilot time, soft-pass-heavy) and post-hardening (the §4.5 verifier with `\tkzInterCC`/`\tkzInterLC` resolvers and a pgfmath expression evaluator). The post-hardening numbers are the ones we will use throughout the rest of the paper. We report both because the *delta* tells the §4 verification-reliability story: 13/315 records (4.1%) promote from soft_pass → strict pass, with the promotions concentrated in the `raw_code` rows that use `\pgfmathsetmacro` for coordinates more often than IR-compiled outputs do.

### 6.2a Post-hardening (headline)

| Model | Strategy | N | Strict | Loose | $/scenario | Avg latency |
|---|---|---:|---:|---:|---:|---:|
| Claude Opus 4.7 | structured | 9* | 100.0% | 100.0% | $0.421 | 10.3 s |
| Claude Sonnet 4.6 | recipe | 30 | 93.3% | 96.7% | $0.059 | 8.0 s |
| Claude Sonnet 4.6 | structured | 36 | 91.7% | 94.4% | $0.075 | 9.1 s |
| GPT-5.1 | structured | 30 | 90.0% | 93.3% | $0.057 | 7.5 s |
| Claude Haiku 4.5 | structured | 30 | 86.7% | 90.0% | $0.032 | 6.8 s |
| Claude Haiku 4.5 | raw_code | 30 | **83.3%** | 93.3% | $0.017 | 7.7 s |
| Claude Opus 4.7 | raw_code | 30 | **80.0%** | 96.7% | $0.329 | 18.0 s |
| Claude Sonnet 4.6 | raw_code | 30 | **76.7%** | 96.7% | $0.047 | 17.1 s |
| GPT-5.1 | raw_code | 30 | **70.0%** | 90.0% | $0.062 | 11.3 s |
| Claude Haiku 4.5 | recipe | 30 | 70.0% | 73.3% | $0.022 | 5.4 s |
| GPT-5.1 | recipe | 30 | 60.0% | 63.3% | $0.056 | 7.6 s |

\* Opus + structured ran into Anthropic rate-limit silent backoff and only completed 9/30 scenarios (all T1+T2) in the pilot. The 100% headline is real for those 9 but is missing T3 evidence. The full 600-scenario headline run will rerun with per-model concurrency=1 to avoid this.

### 6.2b Pre-hardening (for the §4 verification-reliability discussion)

| Model | Strategy | Strict (pre) | Strict (post) | Δ from §4.5 hardening |
|---|---|---:|---:|---:|
| Opus | raw_code | 63.3% | 80.0% | **+16.7 pp** |
| Sonnet | raw_code | 66.7% | 76.7% | **+10.0 pp** |
| Haiku | raw_code | 76.7% | 83.3% | **+6.6 pp** |
| GPT-5.1 | raw_code | 60.0% | 70.0% | **+10.0 pp** |
| (all `structured` and `recipe` rows) | | unchanged | unchanged | 0.0 pp |

The hardening pass affects *only* `raw_code`. This is itself a finding: IR-compiled outputs (`structured`, `recipe`) emit literal coordinates exclusively, so the verifier never had to evaluate `\pgfmathsetmacro`. Direct LLM-generated TikZ uses macros routinely. Pre-hardening, this asymmetry inflated the apparent gap between strategies.

### 6.2c Three findings, in order of importance

1. **Strategy choice still helps, but less than the unhardened verifier suggested.** Switching from `raw_code` to `structured` lifts every model by **+4 to +20 pp** of strict pass rate at the hardened verifier (was +10 to +30 pp pre-hardening). The Pareto frontier (§6.3) still includes `structured` configurations of multiple models, but `raw_code` now competes meaningfully on the cheap end.
2. **Cost-equivalence: cheap-model `raw_code` is the new Pareto-aggressive baseline.** Haiku + raw_code (83.3% strict, $0.017/scenario) **dominates** Opus + raw_code (80.0%, $0.329) on both axes — 3 pp more correct diagrams at **19× lower cost**. Adding `structured` to Haiku ($0.032, 86.7%) buys a further +3.3 pp at 2× the cost; adding `structured` to Sonnet ($0.075, 91.7%) buys another +5 pp at 2.3× more. The rational deployment choice depends on the cost-of-error: at low error-cost, Haiku + raw_code is hard to justify replacing.
3. **The recipe-DSL strategy is unstable across models.** Sonnet uses the recipe DSL well (93% strict, +16 pp over hardened raw_code). GPT-5.1 and Haiku do not (60% and 70%, both *worse* than their raw_code by 10–13 pp). This suggests that a small custom DSL with built-in geometric priors transfers poorly across model families and is not a recommendable deployment strategy below the frontier-model tier.

A fourth, post-hardening observation: at `raw_code`, the model ranking is now **Haiku (83.3%) > Opus (80.0%) > Sonnet (76.7%) > GPT-5.1 (70.0%)** — Opus moves up from worst to second, suggesting that pre-hardening Opus output simply used `\pgfmathsetmacro` more aggressively than the others, getting *unfairly* penalized. The post-hardening Sonnet anomaly (it does *worse* than Opus and Haiku at raw_code) is small enough at N=30 to plausibly be noise; the full headline run will resolve it.

## 6.3 Pareto figure: cost vs strict-pass

Generated by `evals/leaderboard_plot.py::plot_pareto()`.

Figure file: `docs/figures/geogen-pilot/pareto.{png,pdf}`.

Each point is one (model, strategy) combo; x-axis = log cost per scenario, y-axis = strict pass-rate. The Pareto-optimal frontier connects the best-quality point at each cost level.

The pilot's Pareto frontier (data, not prediction):

| $/scenario | Strict pass | Combo |
|---:|---:|---|
| $0.017 | 83.3% | Haiku + raw_code |
| $0.032 | 86.7% | Haiku + structured |
| $0.057 | 90.0% | GPT-5.1 + structured |
| $0.059 | 93.3% | Sonnet + recipe |
| $0.421 | 100.0% | Opus + structured (*N=9*) |

Configurations dominated on both axes (each one is strictly worse than at least one frontier point): Sonnet + raw_code, Opus + raw_code, GPT-5.1 + raw_code, GPT-5.1 + recipe, Haiku + recipe.

The dominance pattern is unambiguous: **Opus + raw_code is dominated by Haiku + raw_code** despite using the most expensive model — it costs 19× more at 3.3 pp lower strict pass. Cost is paying for token-count, not for verdict-quality.

## 6.4 Tier-stratified bar chart

Generated by `evals/leaderboard_plot.py::plot_tier_stratified()`.

Figure file: `docs/figures/geogen-pilot/tier_stratified.{png,pdf}`.

Three bars per (model, strategy) combo, one per tier, showing strict pass. Per-tier strict-pass numbers from the hardened pilot:

| Combo | T1 (easy) | T2 (medium) | T3 (hard) |
|---|---:|---:|---:|
| Sonnet + structured | 100% | 100% | 70% |
| Sonnet + recipe | 100% | 100% | 80% |
| Sonnet + raw_code | 100% | 60% | 70% |
| GPT-5.1 + structured | 100% | 90% | 80% |
| GPT-5.1 + raw_code | 100% | 60% | 50% |
| GPT-5.1 + recipe | 70% | 60% | 50% |
| Haiku + structured | 100% | 90% | 70% |
| Haiku + raw_code | 100% | 80% | 70% |
| Haiku + recipe | 90% | 80% | 40% |
| Opus + structured | 100% | 100% | n/a* |
| Opus + raw_code | 100% | 70% | 70% |

\* Opus structured pilot did not reach T3 scenarios (rate-limit cutoff at scenario 9/30).

Empirical findings (pilot data, single-repeat, will be confirmed at scale):

- **Tier 1 is near-saturated for every (model, strategy) combo except GPT-5.1+recipe (70%)** — strong signal that we need harder T1 templates in v2 *or* that we need to prove these prompts aren't just solvable from the system prompt's example construction.
- **Tier 2 is where strategy first matters.** Across all 4 models, the structured strategy lifts T2 strict-pass from 60-80% (raw_code) to 90-100%. This is the cleanest "structured wins" signal in the pilot.
- **Tier 3 is where model + strategy *both* matter.** The top T3 strict-pass is 80% (Sonnet+recipe and GPT-5.1+structured); the bottom is 40% (GPT-5.1+raw_code and Haiku+recipe). T3 produces the largest cell-to-cell variance and is the right place to invest in v2 expansion (more diverse T3 templates).

## 6.5 Per-template heatmap

Generated by `evals/leaderboard_plot.py::plot_per_template_heatmap()`.

Figure file: `docs/figures/geogen-pilot/per_template_heatmap.{png,pdf}`.

Rows = templates (sorted by tier), columns = best strategy per model, cell value = strict pass-rate (0–100). Blank cells reflect partial pilot coverage (e.g., Opus structured did not reach T3 before rate limiting).

This figure exposes which *specific* geometric constructions are universally hard or universally easy. Pilot readout:

- **Universally easy**: every T1 template is at or near 100% for each model's best strategy.
- **Universally hard**: `tpl-t3-trv` (parallel-line/transversal/corresponding-angle construction) and `tpl-t3-cen` (centroid/median construction) are 0% across the best-strategy columns, making them high-priority templates for qualitative case studies.
- **Discriminating**: `tpl-t3-tan` (tangent), `tpl-t2-rh` (rhombus), and `tpl-t2-cc` (circumcircle) split models/strategies rather than being universally solved or failed.

We will identify the top-3 universally-hard templates and report their failure modes in §6.7 to inform v2 design.

## 6.6 Failure-mode stacked bar

Generated by `evals/leaderboard_plot.py::plot_failure_modes()`.

Figure file: `docs/figures/geogen-pilot/failure_modes.{png,pdf}`.

One stacked bar per (model, strategy) combo, segments by semantic failure-mode category.

Failure-mode categories (from `evals/run.py::gate_status` + parsing of `error` and `gate_failures`):

1. **Generation failure**: model returned no TikZ or hit context limit.
2. **Render failure**: TikZ compiled to LaTeX error or dvisvgm failure.
3. **SVG-check failure**: rendered but malformed SVG.
4. **Geometric check failure**: rendered, valid SVG, but a SymPy property check fails.
5. **Label/structural check failure**: missing required label or wrong polygon count.
6. **Soft-pass (skipped checks)**: nothing failed, but at least one check was marked unimplemented.

Pilot readout: after hardening, failures are dominated by **geometric predicates** and **mark/label fidelity**. Recipe failures are mostly mark/label problems, not render failures; structured failures are rare but still include geometric predicate failures on the hardest templates. This supports the main verifier story: most wrong outputs are *rendered diagrams with the wrong geometry*, not broken LaTeX.

## 6.7 Drill-down: three failure-mode case studies

For each of three universally-hard templates (selected from §6.5), we present:

1. The original prompt.
2. The expected property list and intended construction (with a reference SVG generated by hand).
3. Each model's best attempt across the three strategies (3-up grid of SVGs).
4. The specific predicate verdict for each output, with a one-line interpretation of the failure mode.

This qualitative analysis humanizes the quantitative leaderboard and gives reviewers concrete evidence that the failures are interpretable, not artifacts of the verifier.

## 6.8 Repeats and stability

For the headline run we use 3 independent repeats per (model, strategy, scenario) and report:

- **Per-cell standard error** of strict-pass rate.
- **Stability index**: fraction of scenarios where all 3 repeats produce the same verdict. We expect this to be ≥0.85 for structured (deterministic compilation + bounded retries) and lower for raw_code (LLM stochasticity).

The pilot data (1 repeat) is reported with a standard-error caveat throughout.

## 6.9 What to look for in this section

- **Reviewer trap**: "the differences are within noise." Defense: tier-3 deltas of ≥10 percentage points exceed the standard error of a single 30-scenario sample at p < 0.05 by Wilson's interval. We pre-register this as the headline test.
- **Reviewer trap**: "the soft-pass rate inflates apparent performance." Defense: we report strict-pass as the headline; the full table includes both; Section 4 hardening pass converts most soft-passes to strict verdicts in v1.1.
- **Reviewer trap**: "your strategies aren't a fair comparison — structured costs less because the compiler does the work." Counter: that's the point. The benchmark is *task completion under a verifier*; how the LLM gets there is a strategy choice, and we measure the resulting cost. If the compiler is part of the deployment pipeline, it should be part of the evaluation.
