# python_full Eval Harness Integration — Design

**Status:** Approved for implementation planning
**Scope:** Register `PythonFullStrategy` with `evals/run.py` so it can be benchmarked against `structured`/`recipe` via the existing eval harness (`--strategies python_full`), including per-attempt diagnostics (generated script + retry history) in eval output records. This is the first of two follow-up integration steps agreed after the `python_full` PoC (docs/superpowers/plans/2026-08-03-python-full-strategy.md) landed; the second (wiring into `geometry_diagrams/facade.py`) is explicitly out of scope here and follows once this step has produced evidence.
**Prereq context:** `docs/superpowers/specs/2026-08-03-python-full-strategy-design.md` (the PoC this integrates), `evals/run.py` (existing eval harness), `geometry_diagrams/strategies/recipe.py` (the pattern this mirrors for per-attempt diagnostics).

## Goal

Make `python_full` runnable through the same eval harness every other strategy uses — `uv run python -m evals.run --strategies python_full --scenarios evals/scenarios.yaml` — with enough per-attempt diagnostic capture that a failing eval scenario is debuggable (what script did the model write, what failed, at which stage), not just a pass/fail row with a rendered image.

## Design decisions (from brainstorming discussion)

- **`python_full` is opt-in, not part of the default `--strategies` set.** It's a new, unproven strategy — it should not silently join every default eval invocation's cost/runtime until it's been deliberately benchmarked at least once. `evals/run.py` currently derives its default from `_STRATEGY_MAP.keys()` directly; this needs a separate `_DEFAULT_STRATEGIES` list that excludes it, while `choices` (validation for `--strategies`) still includes it via `_STRATEGY_MAP.keys()`.
- **The TikZ-code LLM judge is skipped for `python_full`, same as `structured`.** `evals/run.py:474` already skips this judge for `"structured"` specifically, because structured's TikZ/SVG is deterministically generated from a compiled `DiagramIR`, not LLM-authored code — judging "code quality" of auto-generated TikZ as if a model wrote it doesn't mean anything. `python_full`'s TikZ/SVG is generated exactly the same deterministic way (the LLM-authored artifact is the pydsl script, not the TikZ); the same reasoning applies, so it joins the skip-list.
- **Per-attempt diagnostics are captured, mirroring `RecipeStrategy`'s existing pattern — but via a NEW, DEDICATED field, not by reusing `recipe_metadata`.** `RecipeStrategy` captures its own diagnostic payload in `result.recipe_metadata`, an `Any`-typed field on the shared `StructuredRunResult`. Reusing that same field for `python_full`'s differently-shaped metadata was the original idea, but a Fable design review caught two real hazards with it: (1) `geometry_diagrams/facade.py:99-101` already unconditionally accesses `.selected_recipes`/`.attempt_traces` on any non-`None` `recipe_metadata` — a `PythonFullMetadata` there would raise `AttributeError`, a live landmine for this plan's own step 2 (facade wiring); (2) `evals/eval_viewer.py:91` strips known-large keys (`recipe_metadata` among them) from list-view payloads — a same-named-but-differently-typed field wouldn't be caught by that strip-list, risking bloating that endpoint with full script texts. Both hazards disappear by construction if `python_full` gets its **own** field instead of overloading `recipe_metadata`: add `python_full_metadata: Any = None` to `StructuredRunResult` (`geometry_diagrams/strategies/ir_pipeline.py`). `evals/run.py`'s handling becomes two independent, non-`isinstance`-based conditionals (`if result.recipe_metadata is not None: ...` unchanged from today; `if result.python_full_metadata is not None: ...` new), each keyed to its own field — no type-checking needed, no risk of one strategy's code accidentally touching another's differently-shaped payload.
- **Total-failure diagnostics are captured too, not just successful-but-imperfect runs.** The single most important case for "what did the model write, what failed" is exactly when the strategy exhausts `MAX_RETRIES` and raises — and the original draft of this design missed it entirely. `RecipeStrategy.run()` sets `self._partial_recipe_metadata`/`_partial_input_tokens`/`_partial_output_tokens` from `final_state` **before** raising (`recipe.py:598-601`), and `evals/run.py`'s exception-path handler (`isinstance(strategy, RecipeStrategy)` at ~line 277) reads those attributes to populate the record even when `strategy.run()` raised. `PythonFullStrategy.run()` currently has no equivalent — a scenario that exhausts retries produces a record with zero traces and zero token counts, exactly backwards from this integration's stated goal. Fix: `PythonFullStrategy.run()` sets `self._partial_python_full_metadata`/`_partial_input_tokens`/`_partial_output_tokens` from `final_state` before raising (mirroring `recipe.py:598-601` exactly), and `evals/run.py`'s exception-path handler gains a parallel `isinstance(strategy, PythonFullStrategy)` branch.

## Components

### 0. New `python_full_metadata` field on the shared `StructuredRunResult`

**File:** `geometry_diagrams/strategies/ir_pipeline.py` (modify)

Add one field to the existing dataclass:

```python
@dataclass
class StructuredRunResult:
    diagram_ir: DiagramIR
    tikz: str
    svg: str
    sym_table: dict
    sym_full: dict
    input_tokens: int = 0
    output_tokens: int = 0
    recipe_metadata: Any = None
    python_full_metadata: Any = None  # NEW
    retries: int = 0
```

`structured.py` and `recipe.py` never set this field (stays `None` for them, same as `python_full.py` never touches `recipe_metadata`) — the two strategies' diagnostic payloads are now fully independent, not sharing one overloaded field.

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

Mirrors `RecipeAttemptTrace`/`RecipeMetadata` (`geometry_diagrams/strategies/recipe.py`) in shape and role — a mutable object created once per `.run()` call (in the initial state, e.g. `"metadata": PythonFullMetadata()`, matching `recipe.py`'s `"recipe_metadata": RecipeMetadata()` in its own initial state), carried through `PythonFullPipelineState` as a new `metadata: PythonFullMetadata` key, and mutated in place by both graph nodes exactly as `recipe.py`'s nodes mutate `state["recipe_metadata"]`. Verified sound: `recipe.py` creates `RecipeMetadata()` once in initial state and nodes mutate it in place without re-returning the key each time — this persists correctly because the compiled graph runs with no checkpointer, so LangGraph's default state channel keeps the same object reference across node calls (this would need re-examination only if a checkpointer/serialization were ever added — not the case here).

- `_generate_script_node`: on every call (success or failure), append a new `PythonFullAttemptTrace(attempt=attempt+1, script=<generated script or None>, error=<parse error or None>, stage="generation")`.
- `_run_script_node`: on the current attempt's outcome, update the **last** trace's `stage`/`error` in place — `"sandbox"` + the sandbox's error message on sandbox failure, `"nothing_drawn"` + the guard's message on the nothing-drawn guard, `"ir_pipeline"` + the pipeline exception message on pipeline failure, or `"success"` (error stays `None`) when it succeeds. This exactly mirrors `recipe.py`'s pattern of retroactively updating `metadata.attempt_traces[-1].stage`/`.error` from a later node in the same attempt (`recipe.py:398-400`, `:412`, `:421-423`). **Note the `script is None` early-return path** (`_run_script_node`'s existing None-guard, from the original PoC plan): when this fires, the trace correctly stays at `stage="generation"` with its already-set parse error — the guard must NOT touch the trace, since there's nothing new to report about this attempt beyond what `_generate_script_node` already recorded.
- `PythonFullStrategy.run()`: before returning, sets `final_state["result"].python_full_metadata = final_state["metadata"]` — the **new, dedicated** field on `StructuredRunResult` (see the Design Decisions section above for why this isn't `recipe_metadata`). Additionally, **before** the `raise RuntimeError(...)` on retry exhaustion, sets `self._partial_python_full_metadata = final_state.get("metadata")`, `self._partial_input_tokens = final_state.get("input_tokens", 0)`, `self._partial_output_tokens = final_state.get("output_tokens", 0)` — mirroring `recipe.py:598-601` exactly, so `evals/run.py`'s exception-path handler can still recover diagnostics from a totally-failed run.

### 2. `evals/run.py` registration

**File:** `evals/run.py` (modify)

- Add `from geometry_diagrams.strategies.python_full import PythonFullStrategy`.
- Add `"python_full": PythonFullStrategy` to `_STRATEGY_MAP` (evals/run.py:83-87ish).
- Add, near `_STRATEGY_MAP`:
  ```python
  _OPT_IN_ONLY_STRATEGIES = {"python_full"}
  _DEFAULT_STRATEGIES = [name for name in _STRATEGY_MAP if name not in _OPT_IN_ONLY_STRATEGIES]
  ```
  (a named set, not a bare inline exclusion — so the next unproven strategy that shouldn't join the default run has an obvious place to register that fact, rather than a one-off `!= "python_full"` check nobody thinks to extend) and change the `--strategies` argparse entry (currently `default=list(_STRATEGY_MAP.keys())`) to `default=_DEFAULT_STRATEGIES`, keeping `choices=list(_STRATEGY_MAP.keys())` unchanged so `--strategies python_full` is still explicitly selectable.
- Change line 474's judge skip-list from `if strategy_name not in ("structured",):` to `if strategy_name not in ("structured", "python_full"):`. Also update the corresponding skip-reasoning message (currently `"(skipped for structured strategy)"`, ~line 491) to name whichever strategy was actually skipped (e.g. `f"(skipped for {strategy_name} strategy)"`) rather than a message that's misleading when it's actually `python_full` being skipped.
- Add a new, independent conditional alongside the existing `recipe_metadata` block (lines 320-330, otherwise **unchanged** — no `isinstance` check needed since each strategy now owns a distinct field):
  ```python
  if result.python_full_metadata is not None:
      record["python_full_metadata"] = {
          "attempt_traces": [
              {"attempt": t.attempt, "script": t.script, "error": t.error, "stage": t.stage}
              for t in result.python_full_metadata.attempt_traces
          ],
      }
      # NOT re-assigned here: result.retries (set at line 300, from
      # pipeline_result.retries = state["attempt"] in python_full.py's
      # _run_script_node) is already correct for python_full and doesn't need
      # the len(attempt_traces)-1 recomputation recipe.py's branch does at
      # line 331 (that recomputation exists because RecipeStrategy's own
      # result.retries isn't reliably set the same way — not the case here).
  ```
  For test factorability (see Testing below), extract this new conditional plus the existing `recipe_metadata` block into a small helper, e.g. `_populate_strategy_metadata(record: dict, result: StructuredRunResult) -> None`, called from `run_scenario` — this lets tests exercise the metadata-population logic directly against a fake `StructuredRunResult` without needing to invoke all of `run_scenario`'s scaffolding (LLM calls, renderer, etc.).
- **Exception-path partial capture** (mirroring the existing `isinstance(strategy, RecipeStrategy)` branch at ~line 277-292): add a parallel branch —
  ```python
  elif isinstance(strategy, PythonFullStrategy):
      record["input_tokens"] = getattr(strategy, "_partial_input_tokens", 0)
      record["output_tokens"] = getattr(strategy, "_partial_output_tokens", 0)
      partial_meta = getattr(strategy, "_partial_python_full_metadata", None)
      if partial_meta is not None:
          record["python_full_metadata"] = {
              "attempt_traces": [
                  {"attempt": t.attempt, "script": t.script, "error": t.error, "stage": t.stage}
                  for t in partial_meta.attempt_traces
              ],
          }
          record["retries"] = max(0, len(partial_meta.attempt_traces) - 1)
  ```
  Without this, a scenario that exhausts `MAX_RETRIES` (exactly the case this integration's diagnostics matter most for) would produce a record with zero traces and zero token counts — the strategy's own `_partial_*` attributes (Component 1) exist specifically to make this branch possible.

## Testing

- **`tests/test_python_full_strategy.py`**: extend with two cases:
  - A retry-then-succeed scenario (reuse the existing sandbox-failure-then-success fixture scripts) asserting `result.python_full_metadata` (the new dedicated field, not `recipe_metadata`) is a `PythonFullMetadata` whose `attempt_traces` has exactly 2 entries — the first with `stage="sandbox"` and a non-None `error`, the second with `stage="success"` and `error is None` — and that `.script` on each trace matches the script text actually generated for that attempt.
  - An exhausts-all-retries scenario (reuse the existing `test_exhausts_retries_and_raises` setup) additionally asserting, after catching the `RuntimeError`, that `strategy._partial_python_full_metadata.attempt_traces` has `MAX_RETRIES` entries and `strategy._partial_input_tokens`/`_partial_output_tokens` are non-zero — this is the direct regression test for the total-failure diagnostics gap found in review.
- **New tests covering `evals/run.py`'s changes** (extend `tests/test_eval_runner.py` or add a new file), against the extracted `_populate_strategy_metadata(record, result)` helper directly (no need to drive full `run_scenario` scaffolding):
  - `"python_full"` is present in `_STRATEGY_MAP` and in the `--strategies` `choices` list.
  - `"python_full"` is absent from `_DEFAULT_STRATEGIES`, and `_OPT_IN_ONLY_STRATEGIES` contains exactly `{"python_full"}`.
  - Feeding a fake `StructuredRunResult` with `python_full_metadata` set produces `record["python_full_metadata"]` with the expected shape, and leaves `record["recipe_metadata"]` unset — no `AttributeError`, no cross-talk between the two fields.
  - Feeding a fake `StructuredRunResult` with `recipe_metadata` set (as `RecipeStrategy` actually produces it) still produces the original `record["recipe_metadata"]` shape, unchanged, and leaves `record["python_full_metadata"]` unset (regression check — this refactor must not alter `RecipeStrategy`'s existing eval behavior).
  - A separate test for the exception-path branch: a stub `PythonFullStrategy`-like object with `_partial_python_full_metadata`/`_partial_input_tokens`/`_partial_output_tokens` set produces a record with those values populated, mirroring the existing `RecipeStrategy` exception-path test if one exists (check `tests/test_eval_runner.py` for the pattern; if none exists for `RecipeStrategy` either, this is the first and should be written for both).
  - The judge skip-list includes `"python_full"`, and the skip-reasoning message names the actual strategy rather than a hardcoded `"structured"` string.

## Out of scope for this step

- `geometry_diagrams/facade.py` / main-app wiring (the second agreed follow-up step, done after this one produces evidence).
- Any change to `PythonFullStrategy`'s actual generation/retry logic (`MAX_RETRIES`, `SANDBOX_TIMEOUT_SECONDS`, the nothing-drawn guard, etc.) — this step only adds observability into the existing behavior, it does not tune it.
- Adding `python_full` to any specific `evals/scenarios*.yaml` scenario file's expectations beyond what already exists generically (scenario prompts are strategy-agnostic; no scenario-file changes are anticipated).
