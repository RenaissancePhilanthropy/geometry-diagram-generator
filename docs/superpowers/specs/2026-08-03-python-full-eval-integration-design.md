# python_full Eval Harness Integration — Design

**Status:** Approved for implementation planning
**Scope:** Register `PythonFullStrategy` with `evals/run.py` so it can be benchmarked against `structured`/`recipe` via the existing eval harness (`--strategies python_full`), including per-attempt diagnostics (generated script + retry history) in eval output records. This is the first of two follow-up integration steps agreed after the `python_full` PoC (docs/superpowers/plans/2026-08-03-python-full-strategy.md) landed; the second (wiring into `geometry_diagrams/facade.py`) is explicitly out of scope here and follows once this step has produced evidence.
**Prereq context:** `docs/superpowers/specs/2026-08-03-python-full-strategy-design.md` (the PoC this integrates), `evals/run.py` (existing eval harness), `geometry_diagrams/strategies/recipe.py` (the pattern this mirrors for per-attempt diagnostics).

## Goal

Make `python_full` runnable through the same eval harness every other strategy uses — `uv run python -m evals.run --strategies python_full --scenarios evals/scenarios.yaml` — with enough per-attempt diagnostic capture that a failing eval scenario is debuggable (what script did the model write, what failed, at which stage), not just a pass/fail row with a rendered image.

## Design decisions (from brainstorming discussion)

- **`python_full` is opt-in, not part of the default `--strategies` set.** It's a new, unproven strategy — it should not silently join every default eval invocation's cost/runtime until it's been deliberately benchmarked at least once. `evals/run.py` currently derives its default from `_STRATEGY_MAP.keys()` directly; this needs a separate `_DEFAULT_STRATEGIES` list that excludes it, while `choices` (validation for `--strategies`) still includes it via `_STRATEGY_MAP.keys()`.
- **The TikZ-code LLM judge is skipped for `python_full`, same as `structured`.** `evals/run.py:474` already skips this judge for `"structured"` specifically, because structured's TikZ/SVG is deterministically generated from a compiled `DiagramIR`, not LLM-authored code — judging "code quality" of auto-generated TikZ as if a model wrote it doesn't mean anything. `python_full`'s TikZ/SVG is generated exactly the same deterministic way (the LLM-authored artifact is the pydsl script, not the TikZ); the same reasoning applies, so it joins the skip-list.
- **Per-attempt diagnostics are captured, mirroring `RecipeStrategy`'s existing pattern — but require a genuinely new branch in `evals/run.py`, not just a strategy-map entry.** `RecipeStrategy` already captures its own diagnostic payload (`selected_recipes`, per-attempt DSL JSON, errors) in `result.recipe_metadata`, an `Any`-typed field on the shared `StructuredRunResult` meant for exactly this kind of strategy-specific extra data. However, `evals/run.py`'s current handling of that field (lines 320-330) is **not actually generic** — it hardcodes `RecipeMetadata`'s exact shape (`.selected_recipes`, `.unmatched_concepts`, `.selection_input_tokens`, `.selection_output_tokens`, `.attempt_traces[].dsl_json`) and would raise `AttributeError` if handed a differently-shaped object. `python_full`'s metadata has a different, DSL-JSON-free shape (script text + per-attempt error/stage), so this integration adds a `PythonFullMetadata`/`PythonFullAttemptTrace` pair (mirroring `RecipeMetadata`/`RecipeAttemptTrace`'s pattern) and a **type-checked branch** in `evals/run.py` — `isinstance(result.recipe_metadata, RecipeMetadata)` vs `isinstance(result.recipe_metadata, PythonFullMetadata)` — writing to a new, distinctly-named `record["python_full_metadata"]` key rather than overloading the `recipe_metadata` record key with non-recipe data.

## Components

### 1. `PythonFullAttemptTrace` / `PythonFullMetadata`

**File:** `geometry_diagrams/strategies/python_full.py` (add)

```python
@dataclass
class PythonFullAttemptTrace:
    attempt: int
    script: str | None
    error: str | None
    stage: str  # "generation" | "sandbox" | "nothing_drawn" | "ir_pipeline" | "success"


@dataclass
class PythonFullMetadata:
    attempt_traces: list[PythonFullAttemptTrace] = field(default_factory=list)
```

Mirrors `RecipeAttemptTrace`/`RecipeMetadata` (`geometry_diagrams/strategies/recipe.py`) in shape and role — a mutable object created once per `.run()` call, carried through `PythonFullPipelineState` as a new `metadata: PythonFullMetadata` key, and mutated in place by both graph nodes exactly as `recipe.py`'s nodes mutate `state["recipe_metadata"]`:

- `_generate_script_node`: on every call (success or failure), append a new `PythonFullAttemptTrace(attempt=attempt+1, script=<generated script or None>, error=<parse error or None>, stage="generation")`.
- `_run_script_node`: on the current attempt's outcome, update the **last** trace's `stage`/`error` in place — `"sandbox"` + the sandbox's error message on sandbox failure, `"nothing_drawn"` + the guard's message on the nothing-drawn guard, `"ir_pipeline"` + the pipeline exception message on pipeline failure, or `"success"` (error stays `None`) when it succeeds. This exactly mirrors `recipe.py`'s pattern of retroactively updating `metadata.attempt_traces[-1].stage`/`.error` from a later node in the same attempt (`recipe.py:398-400`, `:412`, `:421-423`).
- `PythonFullStrategy.run()`: before returning, sets `final_state["result"].recipe_metadata = final_state["metadata"]` (the shared `Any`-typed field on `StructuredRunResult`, populated the same way `RecipeStrategy.run()` already does).

### 2. `evals/run.py` registration

**File:** `evals/run.py` (modify)

- Add `from geometry_diagrams.strategies.python_full import PythonFullStrategy, PythonFullMetadata` and `from geometry_diagrams.strategies.recipe import RecipeMetadata` (if not already imported by name — verify at implementation time; `recipe.py`'s `RecipeMetadata` class may currently only be referenced implicitly via `result.recipe_metadata`'s duck-typed access, not imported by name in `evals/run.py`, in which case this is a new import).
- Add `"python_full": PythonFullStrategy` to `_STRATEGY_MAP` (evals/run.py:83-87ish).
- Add, near `_STRATEGY_MAP`:
  ```python
  _DEFAULT_STRATEGIES = [name for name in _STRATEGY_MAP if name != "python_full"]
  ```
  and change the `--strategies` argparse entry (currently `default=list(_STRATEGY_MAP.keys())`) to `default=_DEFAULT_STRATEGIES`, keeping `choices=list(_STRATEGY_MAP.keys())` unchanged so `--strategies python_full` is still explicitly selectable.
- Change line 474's judge skip-list from `if strategy_name not in ("structured",):` to `if strategy_name not in ("structured", "python_full"):`.
- Replace the unconditional `RecipeMetadata`-shaped block at lines 320-330 with a type-checked branch:
  ```python
  if result.recipe_metadata is not None:
      if isinstance(result.recipe_metadata, RecipeMetadata):
          record["recipe_metadata"] = {
              "selected_recipes": result.recipe_metadata.selected_recipes,
              "unmatched_concepts": result.recipe_metadata.unmatched_concepts,
              "selection_input_tokens": result.recipe_metadata.selection_input_tokens,
              "selection_output_tokens": result.recipe_metadata.selection_output_tokens,
              "attempt_traces": [
                  {"attempt": t.attempt, "dsl_json": t.dsl_json, "error": t.error, "stage": t.stage}
                  for t in result.recipe_metadata.attempt_traces
              ],
          }
          record["retries"] = max(0, len(result.recipe_metadata.attempt_traces) - 1)
      elif isinstance(result.recipe_metadata, PythonFullMetadata):
          record["python_full_metadata"] = {
              "attempt_traces": [
                  {"attempt": t.attempt, "script": t.script, "error": t.error, "stage": t.stage}
                  for t in result.recipe_metadata.attempt_traces
              ],
          }
          record["retries"] = max(0, len(result.recipe_metadata.attempt_traces) - 1)
  else:
      record["recipe_metadata"] = None
  ```
  Verified against the actual `record` initialization (evals/run.py's `record: dict[str, Any] = {...}` literal, ~line 230): `recipe_metadata` is **not** among its initial keys — it's only ever set inside this conditional block (and the analogous exception-path block at ~line 282). So this new branch introduces no inconsistency: `record["python_full_metadata"]` is simply absent from the row for any non-`python_full` strategy (matching how `recipe_metadata` is already absent from `raw_code`/`raw_svg` rows today — the record's key set already varies by strategy, and downstream consumers already tolerate that). No new default-key bookkeeping is needed.

## Testing

- **`tests/test_python_full_strategy.py`**: extend with a retry scenario (reuse the existing sandbox-failure-then-success fixture scripts) asserting `result.recipe_metadata` is a `PythonFullMetadata` whose `attempt_traces` has exactly 2 entries — the first with `stage="sandbox"` and a non-None `error`, the second with `stage="success"` and `error is None` — and that `.script` on each trace matches the script text actually generated for that attempt.
- **New tests covering `evals/run.py`'s changes** (extend `tests/test_eval_runner.py` or add a new file):
  - `"python_full"` is present in `_STRATEGY_MAP` and in the `--strategies` `choices` list.
  - `"python_full"` is absent from `_DEFAULT_STRATEGIES`.
  - Feeding a fake `StructuredRunResult` with a `PythonFullMetadata` through the metadata-branch logic produces `record["python_full_metadata"]` with the expected shape, and does not raise `AttributeError` (the exact failure mode the unconditional old code would have hit).
  - Feeding a fake `StructuredRunResult` with a real `RecipeMetadata` still produces the original `record["recipe_metadata"]` shape, unchanged (regression check — this refactor must not alter `RecipeStrategy`'s existing eval behavior).
  - The judge skip-list includes `"python_full"`.

## Out of scope for this step

- `geometry_diagrams/facade.py` / main-app wiring (the second agreed follow-up step, done after this one produces evidence).
- Any change to `PythonFullStrategy`'s actual generation/retry logic (`MAX_RETRIES`, `SANDBOX_TIMEOUT_SECONDS`, the nothing-drawn guard, etc.) — this step only adds observability into the existing behavior, it does not tune it.
- Adding `python_full` to any specific `evals/scenarios*.yaml` scenario file's expectations beyond what already exists generically (scenario prompts are strategy-agnostic; no scenario-file changes are anticipated).
