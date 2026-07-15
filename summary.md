
## Target

The current work has focused on improving the recipe strategy to the point where it is on par or better to the structured approach described in the paper. Additionally, as models become better, cheaper alternatives (open weights or open source) perform at a similar level to frontier models. Allowing the project to use them opens up additional avenues for improvements which are not possible with closed source models.

## Approach
The project has been updated to support recipe strategy with a fallback to structured strategy. Most of the work focused on open models. Having already a strong deterministic gate and scenarios, this in turn opened the path for automatically searching for DSL, generation prompts improvements. For all llm judge evaluation Google Gemma4 31B was used. On top of the actual generation, we spent effort to find ways to evaluate if we can find a reliable predictor of success. 

## Themes & Results

### Harness robustness

#### Generation & fallback

Produce a correct diagram more often; tolerate model/backend quirks.
- open models support via ollama models (which can run both local, as well as cloud). Primarily focused on runs using 1 open source model (Google's Gemma4 31B) and one open weights model (Deepseek v4 flash seemed the fastest competent choice). The pass rate of both models matches or exceeds the reference used (the structured strategy run from the end of april paper)
- recipe strategy fallback to structured strategy has improved scoring across the board, regardless of model used (records used_fallback)
- Error-text-driven retry hints (triangle-spec ambiguity, mark_angle mismatch, undefined id, right-angle candidates) instead of generic advice.
- Recover diagrams from text responses when a model emits JSON as plain text instead of via the tool call; treat HTTP errors as transport failures, not retryable model mistakes.
- Ollama compatibility (null-content patching, reasoning-effort so thinking surfaces) + thinking/prompt_overrides plumbing;   

#### Checker false-positive elimination
Stop penalizing correct diagrams for naming/style/cosmetic mismatches
- one of the most common gate failure was prime notation which failed many scenarios when it actually worked properly but there was a mismatch between expectation and request
- DSL ergonomics: turn common model mistakes into fixable retries.
- Actionable "extra inputs not permitted" errors (list permitted fields); annotations shape coercion (list / JSON-string → object); check-error provenance (reports originating file:line).

#### Tooling
- Re-score without regenerating: Make old saved runs comparable to current checkers without re-paying LLM costs :
    - rescore_gate.py (recompute gate checks from saved TikZ)
    - rescore_cot.py (backfill top-level CoT + re-analyze)
    - extract_failing_scenarios.py (build a failing-subset YAML from gate failures).
- Eval harness upgrades (evals/run.py). New flags: --thinking, --cot-analysis, --confidence-mode, --geometric-planning, --use-optimized-prompts, --timeout, --visual-judge, --llm-judge. Plus per-scenario timeout (intentional 300s guardrail), failure-path CoT capture, and enriched result records.
- One-command entry points for the above, with fixed judge model + auto-named logs.
    - profile_single_scenario.py — per-phase timing (backs the model latency/quality benchmark).
    - Eval launchers: run_geometry_{curriculum,hard_intersect,stress,hard_stress}_eval.sh.
    - GEPA runs: run_gepa_{challenge,intersection,varied_10x10}.sh.
    - Analysis wrappers: run_embedding_judge.sh, analyze_confidence.sh; check_eval.sh.
    - start_tikz_renderer.sh — bare-metal renderer launcher for this Docker-less box. (Infra that the rest of the tooling depends on; rolled here, not a standalone feature.)

#### Results & recommendation
These improvements should be included in the mainline as they make the whole thing more robust, regardless of model chosen. This is visible also from re-running and re-scoring of the reference run from april's paper.

### Optimized prompts

#### Approach
Automate prompt improvement and measure it cleanly via https://pydantic.dev/articles/prompt-optimization-with-gepa
- Evolutionary optimizer + adapter over recipe prompt components, with efficiency-aware scoring (retries + duration vs a seed baseline).
- Optimized generation prompt (~6.9k→~17k chars: property-by-name, 3D/rotation, render-artifact avoidance, label placement, multi-panel, fallback prevention).
- Prompt ablation harness (--use-optimized-prompts) — flips on-disk GEPA vs prior pre-GEPA prompts at runtime with code/checkers unchanged.
- Three LLMs involved : mutator, trainer and evaluator. They can be independently configured as to use a smarter model for mutation and avoid over fitting when using same train & evaluate model.

#### Results & recommendation
Quality of output seems to be highly dependent on model and there is no one size fits all prompt. More so, as the models improve, it's likely to need less strong guardrails. This is evident also from the result for one of the optimization runs which ranked highest an empty system generation prompt. Overall positive, both models beat the baseline by a good margin. Detailed results at https://github.com/RenaissancePhilanthropy/geometry-diagram-generator/blob/feat/recipe-improvements/changes.md#findings 
Probably the best approach would be to start from the optimized prompts but also do a comprehensive run whenever a new model is attempted, since per-model tailoring of prompts can yield improvements. This comes at the cost of maintenance when a large number of models is supported. 
One interesting finding is the degradation of results when trying to augment the DSL prompt with relevant recipe parts, even with only  sections that are present in recipe but apply across the board. This shows that, with a larger prompt, the model can get confused or we could inject contracticting instructions (https://github.com/RenaissancePhilanthropy/geometry-diagram-generator/blob/feat/recipe-improvements/changes.md#validation-results--v2-run-deepseek--gemma4-2026-06-23)

### Confidence && success prediction
We attempted various ways to evaluate if we can predict success, rather than just rely on post-generation judge. If successful, this could be deployed online and skip generation altogether when confidence in result is low. Despite multiple approaches, none seems like a clear winner, though, again, this can be more or less successful depending on model 
#### Approaches 
- CoT analyzer: both LLM (same model as generation, models are always confident in their thinking) and deterministic (text-only uncertainty-marker counter)
- Self-reported, metadata-first confidence: prospective self-rating before construction, via `structured` or `prelude` elicitation (`--confidence-mode`); generation prompt refactored so the prelude shares the real call's context.
- Think-before-write / geometric planning (`--geometric-planning`): opt-in free-form `geometric_analysis` planning field filled before the construction.
- Embedding judge: cosine(cot↔answer) over 4 text renderings of the diagram, chunked to the embeddinggemma cap, per `(model × scenario)`.
- Across-run embedding convergence: does a generator produce similar diagrams across repeats? Pairwise/centroid cosine + spread vs pass rate.
- We used 3 embedding models: embeddinggemma (300M), qwen 4B and qwen 8B with no discernable value brought by larger models. Gemmaembeddings though suffers from a very small context window so needs chunking, which might distort the results. Qwen 4B seems the better approach 

#### Results & recommendation
Overall low confidence in any of the approaches as a hard gate as success predictor. For harder scenarios it does have some value, though one would need to evaluate the complexity of scenario in an online setting. 
- CoT generally proves quite confident, regardless of success rate.
- Self-report confidence, as well as plan before generation falls into the same category, where the model will confidently do the same thing with little differentiation between success and failure scenarios. When planning first (as a separate run) and then generate, the results do scale with complexity though still quite a weak predictor (https://github.com/RenaissancePhilanthropy/geometry-diagram-generator/blob/feat/recipe-improvements/changes.md#what-we-found). Per model calibration could be useful here if the number of models used is going to be small. 
- Embedding judge for in-run (i.e. is the thinking process similar to the actual output?) is not a good predictor and also highly dependent on the model. Deepseek tends to offer a richer CoT, while gemma4 is quite terse. 
- Embedding judge across runs (i.e. is the output & thinking similar across runs for the same scenario) is a somewhat better predictor but needs calibration and scales with complexity (https://github.com/RenaissancePhilanthropy/geometry-diagram-generator/blob/feat/recipe-improvements/changes.md#across-run-convergence-a-second-cleaner-embedding-signal)
 
