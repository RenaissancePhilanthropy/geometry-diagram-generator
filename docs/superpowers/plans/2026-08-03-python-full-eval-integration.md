# python_full Eval Harness Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register `PythonFullStrategy` with `evals/run.py` so it's benchmarkable via `--strategies python_full`, with per-attempt diagnostics (generated script + retry/failure history) captured for both successful-but-imperfect runs and total failures.

**Architecture:** A new dedicated `python_full_metadata` field on the shared `StructuredRunResult` (parallel to, but never sharing, `recipe_metadata`) carries a `PythonFullMetadata`/`PythonFullAttemptTrace` pair populated by `python_full.py`'s own `StateGraph` nodes, mirroring `RecipeStrategy`'s existing diagnostic-capture pattern in shape only — no code or type import from `recipe.py`. `evals/run.py` gains a `_STRATEGY_MAP` entry, an opt-in-only default-strategies mechanism, a judge skip-list entry, and two small extracted helpers (`_populate_strategy_metadata`, `_populate_partial_metadata_on_failure`) so both the success and total-failure paths populate the right record fields — independently testable without driving the full `run_scenario` scaffolding.

**Tech Stack:** Python 3.11, dataclasses, LangGraph state (no new graph shape — existing `python_full.py` nodes gain new responsibilities), pytest.

## Global Constraints

- `python_full` is **opt-in only** — absent from `evals/run.py`'s default `--strategies` set, present in `choices`. Implemented via a named `_OPT_IN_ONLY_STRATEGIES = {"python_full"}` set (not a bare inline exclusion), so future unproven strategies have an obvious place to register the same fact.
- The TikZ-code LLM judge is skipped for `python_full`, exactly as it already is for `"structured"` — both produce deterministically-rendered TikZ/SVG, not LLM-authored code.
- `python_full`'s diagnostics live in a **new, dedicated** `python_full_metadata: Any = None` field on `StructuredRunResult` — **never** written to or read from `recipe_metadata`. This is required, not a style preference: `geometry_diagrams/facade.py:99-101` unconditionally accesses `.selected_recipes`/`.attempt_traces` on any non-`None` `recipe_metadata`, so a `PythonFullMetadata` there would raise `AttributeError` the moment facade integration (a future step) exercises it.
- **No code or type sharing with `recipe.py`'s DSL/catalog/selector system.** `PythonFullMetadata`/`PythonFullAttemptTrace` are standalone dataclasses defined in `python_full.py`. Nothing in this plan imports `RecipeMetadata`, `RecipeAttemptTrace`, `RecipeStrategy`, or anything from `geometry_diagrams/recipe/`. `recipe.py` is read only as a naming/structural pattern to imitate, in the same file (`evals/run.py`) that already imports it for its own pre-existing, unrelated branch.
- Total-failure diagnostics (retry exhaustion) must be captured, not just successful-but-imperfect runs — `PythonFullStrategy.run()` sets `self._partial_python_full_metadata`/`_partial_input_tokens`/`_partial_output_tokens` from `final_state` **before** raising `RuntimeError`, mirroring `recipe.py:598-601` exactly.
- No changes to `PythonFullStrategy`'s actual generation/retry logic (`MAX_RETRIES`, `SANDBOX_TIMEOUT_SECONDS`, the nothing-drawn guard) — this plan only adds observability into existing behavior.
- No `evals/scenarios*.yaml` changes — scenario prompts are strategy-agnostic.
- `geometry_diagrams/facade.py` / main-app wiring is explicitly out of scope — a separate, later step.

---

## File Structure

```
geometry_diagrams/strategies/
    ir_pipeline.py       # MODIFY: StructuredRunResult gains python_full_metadata: Any = None
    python_full.py         # MODIFY: PythonFullAttemptTrace/PythonFullMetadata dataclasses;
                            #   _generate_script_node/_run_script_node populate them;
                            #   PythonFullStrategy.run() attaches final + partial-on-failure metadata

evals/
    run.py                # MODIFY: import + register PythonFullStrategy; _OPT_IN_ONLY_STRATEGIES/
                            #   _DEFAULT_STRATEGIES; judge skip-list + message fix; two new helpers
                            #   (_populate_strategy_metadata, _populate_partial_metadata_on_failure)
                            #   wired into run_scenario
    eval_viewer.py          # MODIFY: _record_metadata's strip-list gains "python_full_metadata"

tests/
    test_ir_pipeline.py      # NEW: the new field defaults to None, can be set
    test_python_full_strategy.py  # MODIFY: extend with metadata + partial-capture-on-failure tests
    test_eval_runner.py       # MODIFY: extend with strategy-map/default-set/judge-skip/helper tests
```

---

### Task 1: `python_full_metadata` field on `StructuredRunResult`

**Files:**
- Modify: `geometry_diagrams/strategies/ir_pipeline.py`
- Test: `tests/test_ir_pipeline.py` (new)

**Interfaces:**
- Consumes: nothing new.
- Produces: `StructuredRunResult.python_full_metadata: Any = None` — a new field, independent of `recipe_metadata`, defaulting to `None` for every strategy that doesn't set it (which, after this task, is every strategy except `python_full` after Task 2).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ir_pipeline.py
"""Tests for the shared StructuredRunResult dataclass."""
from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
from geometry_diagrams.ir.ir import DiagramIR


def _make_minimal_result(**overrides) -> StructuredRunResult:
    defaults = dict(
        diagram_ir=DiagramIR(define=[], checks=[], render=[]),
        tikz="", svg="", sym_table={}, sym_full={},
    )
    defaults.update(overrides)
    return StructuredRunResult(**defaults)


def test_python_full_metadata_defaults_to_none():
    result = _make_minimal_result()
    assert result.python_full_metadata is None
    assert result.recipe_metadata is None  # unaffected, still independently None


def test_python_full_metadata_can_be_set_independently_of_recipe_metadata():
    result = _make_minimal_result(python_full_metadata={"attempt_traces": []})
    assert result.python_full_metadata == {"attempt_traces": []}
    assert result.recipe_metadata is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ir_pipeline.py -v`
Expected: FAIL — `TypeError: StructuredRunResult.__init__() got an unexpected keyword argument 'python_full_metadata'`

- [ ] **Step 3: Add the field**

```python
# geometry_diagrams/strategies/ir_pipeline.py — change the StructuredRunResult class:
@dataclass
class StructuredRunResult:
    diagram_ir: DiagramIR
    tikz: str
    svg: str
    sym_table: dict  # id -> (float, float) coords
    sym_full: dict   # id -> sympy object
    input_tokens: int = 0
    output_tokens: int = 0
    recipe_metadata: Any = None
    python_full_metadata: Any = None
    retries: int = 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_ir_pipeline.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the structured/recipe regression suites to confirm no breakage**

Run: `.venv/bin/python -m pytest tests/test_structured_strategy.py tests/test_recipe_strategy.py tests/test_recipe_retry.py tests/test_python_full_strategy.py -q`
Expected: PASS, same counts as before this task (a new dataclass field with a default doesn't change any existing construction call)

- [ ] **Step 6: Commit**

```bash
git add geometry_diagrams/strategies/ir_pipeline.py tests/test_ir_pipeline.py
git commit -m "Add python_full_metadata field to StructuredRunResult

Dedicated to python_full's own diagnostics, independent of recipe_metadata
— facade.py unconditionally accesses .selected_recipes/.attempt_traces on
any non-None recipe_metadata, so reusing that field for a differently-shaped
PythonFullMetadata would raise AttributeError there."
```

---

### Task 2: `PythonFullAttemptTrace`/`PythonFullMetadata` — per-attempt diagnostic capture in `python_full.py`

**Files:**
- Modify: `geometry_diagrams/strategies/python_full.py`
- Modify: `tests/test_python_full_strategy.py`

**Interfaces:**
- Consumes: `StructuredRunResult.python_full_metadata` (Task 1).
- Produces: `PythonFullAttemptTrace` (`attempt: int`, `script: str | None`, `error: str | None`, `stage: str`), `PythonFullMetadata` (`attempt_traces: list[PythonFullAttemptTrace]`). `PythonFullPipelineState` gains a `metadata: PythonFullMetadata` key. `PythonFullStrategy` gains `self._partial_python_full_metadata`, `self._partial_input_tokens`, `self._partial_output_tokens` (set before raising on retry exhaustion, mirroring `recipe.py:598-601`).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_python_full_strategy.py

from geometry_diagrams.strategies.python_full import PythonFullMetadata


@pytest.mark.asyncio
async def test_metadata_records_one_trace_per_attempt_and_final_stage_success():
    """Retry-then-succeed: python_full_metadata (the dedicated field, never
    recipe_metadata) must have one trace per attempt, with the sandbox
    failure's message on the first and stage='success' on the second."""
    mock_llm = _make_mock_llm([
        _make_script_response(TYPO_SCRIPT),
        _make_script_response(VALID_SCRIPT),
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert result.recipe_metadata is None  # never touched
    meta = result.python_full_metadata
    assert isinstance(meta, PythonFullMetadata)
    assert len(meta.attempt_traces) == 2
    assert meta.attempt_traces[0].script == TYPO_SCRIPT
    assert meta.attempt_traces[0].stage == "sandbox"
    assert meta.attempt_traces[0].error is not None
    assert meta.attempt_traces[1].script == VALID_SCRIPT
    assert meta.attempt_traces[1].stage == "success"
    assert meta.attempt_traces[1].error is None


@pytest.mark.asyncio
async def test_metadata_records_nothing_drawn_stage():
    mock_llm = _make_mock_llm([
        _make_script_response(NO_DRAW_SCRIPT),
        _make_script_response(VALID_SCRIPT),
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert result.python_full_metadata.attempt_traces[0].stage == "nothing_drawn"


@pytest.mark.asyncio
async def test_metadata_records_generation_failure_stage_without_double_counting():
    """Covers the script-is-None early-return path: _run_script_node must NOT
    touch the trace _generate_script_node already recorded for this attempt."""
    mock_llm = _make_mock_llm([
        _make_script_fail_response(),
        _make_script_response(VALID_SCRIPT),
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    meta = result.python_full_metadata
    assert len(meta.attempt_traces) == 2
    assert meta.attempt_traces[0].stage == "generation"
    assert meta.attempt_traces[0].script is None
    assert meta.attempt_traces[0].error == "bad JSON from LLM"


@pytest.mark.asyncio
async def test_run_reports_total_tokens_across_all_attempts():
    """Pre-existing bug caught while wiring metadata through run(): the current
    PythonFullStrategy.run() returns final_state["result"] directly without ever
    copying final_state's accumulated input_tokens/output_tokens onto it — so
    result.input_tokens/output_tokens are always 0 regardless of actual LLM
    usage (nothing previously asserted on these fields, so it went uncaught).
    A 2-attempt run must report tokens summed across BOTH generation calls."""
    mock_llm = _make_mock_llm([
        _make_script_fail_response(),  # 5 in / 2 out
        _make_script_response(VALID_SCRIPT),  # 10 in / 20 out
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert result.input_tokens == 15
    assert result.output_tokens == 22


@pytest.mark.asyncio
async def test_partial_metadata_captured_on_total_failure():
    """The exhausts-all-retries case — the single most important scenario for
    diagnostics, and the one the original design draft missed entirely."""
    mock_llm = _make_mock_llm([_make_script_response(TYPO_SCRIPT)] * MAX_RETRIES)
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        with pytest.raises(RuntimeError, match="PythonFullStrategy failed"):
            await strategy.run(
                "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
            )
    assert isinstance(strategy._partial_python_full_metadata, PythonFullMetadata)
    assert len(strategy._partial_python_full_metadata.attempt_traces) == MAX_RETRIES
    assert all(t.stage == "sandbox" for t in strategy._partial_python_full_metadata.attempt_traces)
    assert strategy._partial_input_tokens > 0
    assert strategy._partial_output_tokens > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_python_full_strategy.py -v -k "metadata or partial_metadata"`
Expected: FAIL — `ImportError: cannot import name 'PythonFullMetadata'`

- [ ] **Step 3: Implement the dataclasses and wire them through the graph**

```python
# geometry_diagrams/strategies/python_full.py — add near the top, after imports:
from dataclasses import dataclass, field
```

```python
# add after the PydslScriptOutput class:
@dataclass
class PythonFullAttemptTrace:
    attempt: int
    script: "str | None"
    error: "str | None"
    stage: str  # "generation" | "sandbox" | "nothing_drawn" | "ir_pipeline" | "success"


@dataclass
class PythonFullMetadata:
    attempt_traces: list[PythonFullAttemptTrace] = field(default_factory=list)
```

```python
# change PythonFullPipelineState to add one key:
class PythonFullPipelineState(TypedDict):
    prompt: str
    model_id: str
    enable_cache: bool
    attempt: int
    last_error: str
    script: Optional[str]
    result: Optional[StructuredRunResult]
    input_tokens: int
    output_tokens: int
    renderer: Optional[Any]
    metadata: PythonFullMetadata
```

```python
# change _generate_script_node: append a trace on every call (success or
# failure), using `attempt + 1` as the human-facing attempt number (matches
# the existing attempt+1 convention already used when incrementing on
# failure). Full replacement of the function body from the docstring down:
async def _generate_script_node(state: PythonFullPipelineState) -> dict:
    """Call the LLM to generate a pydsl script from the prompt."""
    model_id = state["model_id"]
    enable_cache = state.get("enable_cache", False)
    attempt = state["attempt"]
    last_error = state.get("last_error", "")
    metadata = state["metadata"]

    prompt = state["prompt"]
    if attempt > 0 and last_error:
        prompt = f"{prompt}\n\nPrevious attempt failed: {last_error}\nPlease produce a corrected script."

    from langchain_core.messages import HumanMessage
    messages = [
        make_system_message(build_python_full_instructions(), enable_cache=enable_cache),
        HumanMessage(content=prompt),
    ]

    try:
        llm = get_chat_model(model_id, enable_cache=enable_cache)
        if is_gemini_model(model_id):
            structured = llm.with_structured_output(PydslScriptOutput, method="json_mode", include_raw=True)
        else:
            structured = llm.with_structured_output(PydslScriptOutput, include_raw=True)

        response = await structured.ainvoke(messages)
        raw_msg = response.get("raw")
        parsed = response.get("parsed")
        in_tok, out_tok = extract_usage(raw_msg) if raw_msg else (0, 0)

        if parsed is None:
            parsing_error = response.get("parsing_error") or "Failed to parse script output"
            metadata.attempt_traces.append(PythonFullAttemptTrace(
                attempt=attempt + 1, script=None, error=str(parsing_error), stage="generation",
            ))
            return {
                "script": None,
                "last_error": str(parsing_error),
                "attempt": attempt + 1,
                "input_tokens": state["input_tokens"] + in_tok,
                "output_tokens": state["output_tokens"] + out_tok,
            }

        metadata.attempt_traces.append(PythonFullAttemptTrace(
            attempt=attempt + 1, script=parsed.script, error=None, stage="generation",
        ))
        return {
            "script": parsed.script,
            "last_error": "",
            "input_tokens": state["input_tokens"] + in_tok,
            "output_tokens": state["output_tokens"] + out_tok,
        }
    except Exception as exc:
        logger.warning(f"_generate_script_node attempt {attempt} failed: {exc}")
        metadata.attempt_traces.append(PythonFullAttemptTrace(
            attempt=attempt + 1, script=None, error=str(exc), stage="generation",
        ))
        return {
            "script": None,
            "last_error": str(exc),
            "attempt": attempt + 1,
        }
```

```python
# change _run_script_node: retroactively update the LAST trace's stage/error
# for every outcome except the script-is-None early return (which must NOT
# touch the trace — _generate_script_node already recorded everything there
# is to say about this attempt). Full replacement of the function body:
async def _run_script_node(state: PythonFullPipelineState) -> dict:
    """Run the sandboxed script, then the deterministic compile/check/render pipeline."""
    script = state["script"]
    renderer = state.get("renderer")
    metadata = state["metadata"]

    if script is None:
        # _generate_script_node already incremented attempt on failure — don't double-count,
        # and don't touch the trace it already appended for this attempt.
        return {"last_error": "No script available to run"}

    result = await asyncio.to_thread(run_script, script, timeout_seconds=SANDBOX_TIMEOUT_SECONDS)

    if result.error is not None:
        # retry_message is None for ExecutionTimeoutError (sandbox.py's timeout branch never
        # sets it) — fall back to result.error so last_error is never empty on that path.
        error_text = result.retry_message or result.error
        metadata.attempt_traces[-1].stage = "sandbox"
        metadata.attempt_traces[-1].error = error_text
        return {
            "last_error": error_text,
            "attempt": state["attempt"] + 1,
            "result": None,
        }

    diagram_ir = result.diagram_ir
    if not diagram_ir.render:
        error_text = (
            f"Diagram has {len(diagram_ir.define)} definitions but nothing was "
            "drawn — call draw()/draw_points() on what should be visible before finishing."
        )
        metadata.attempt_traces[-1].stage = "nothing_drawn"
        metadata.attempt_traces[-1].error = error_text
        return {
            "last_error": error_text,
            "attempt": state["attempt"] + 1,
            "result": None,
        }

    try:
        pipeline_result = await run_ir_pipeline(diagram_ir, renderer)
        pipeline_result.retries = state["attempt"]
        metadata.attempt_traces[-1].stage = "success"
        return {"result": pipeline_result}
    except (IRCompileError, RuntimeError) as e:
        metadata.attempt_traces[-1].stage = "ir_pipeline"
        metadata.attempt_traces[-1].error = str(e)
        return {
            "last_error": str(e),
            "attempt": state["attempt"] + 1,
            "result": None,
        }
```

```python
# change PythonFullStrategy.run(): add "metadata": PythonFullMetadata() to
# initial_state, attach it to the result on success, and capture partial
# metadata + tokens before raising on exhaustion. Full replacement:
class PythonFullStrategy(SubstanceStrategy):
    """pydsl-based strategy: LLM writes a sandboxed Python script, compiled + rendered deterministically."""

    async def run(
        self,
        prompt: str,
        model: str = DEFAULT_AGENT_MODEL,
        renderer: Renderer | None = None,
    ) -> StructuredRunResult:
        graph = _build_python_full_graph()
        initial_state: PythonFullPipelineState = {
            "prompt": prompt,
            "model_id": model,
            "enable_cache": self.enable_cache,
            "attempt": 0,
            "last_error": "",
            "script": None,
            "result": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "renderer": renderer,
            "metadata": PythonFullMetadata(),
        }
        final_state = await graph.ainvoke(initial_state, config=self._run_config)

        # Expose partial metadata for the eval harness, before the possible raise below.
        self._partial_python_full_metadata = final_state.get("metadata")
        self._partial_input_tokens = final_state.get("input_tokens", 0)
        self._partial_output_tokens = final_state.get("output_tokens", 0)

        if final_state.get("result") is None:
            raise RuntimeError(
                f"PythonFullStrategy failed after {MAX_RETRIES} attempts. "
                f"Last error: {final_state.get('last_error', 'unknown')}"
            )
        result = final_state["result"]
        result.python_full_metadata = final_state.get("metadata")
        result.input_tokens = final_state.get("input_tokens", 0)
        result.output_tokens = final_state.get("output_tokens", 0)
        return result

    def build_agent(self, model: str = DEFAULT_AGENT_MODEL, renderer=None):
        """Not implemented for this PoC — this strategy has no conversational-agent
        requirement yet. Real chat wiring (render_diagram/query_diagram tools, as
        structured.py provides) is deferred until this strategy actually needs it."""
        raise NotImplementedError(
            "PythonFullStrategy doesn't support build_agent() yet — use .run() directly."
        )
```

Note: `result.input_tokens`/`result.output_tokens` were already set correctly by `run_ir_pipeline` returning a fresh `StructuredRunResult` with defaults `0`/`0` — this explicit re-assignment in `run()` mirrors `recipe.py`'s own pattern of setting them on the final result from `final_state`, ensuring the token counts reflect the whole multi-attempt run (all generation calls), not just whatever `run_ir_pipeline` itself saw (which is always `0`/`0`, since it never calls an LLM).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_python_full_strategy.py -v`
Expected: PASS (all tests in the file, including the 5 new ones)

- [ ] **Step 5: Run the full test suite to confirm no regressions**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass, same count as before plus the 5 new tests

- [ ] **Step 6: Commit**

```bash
git add geometry_diagrams/strategies/python_full.py tests/test_python_full_strategy.py
git commit -m "Capture per-attempt diagnostics in PythonFullStrategy

PythonFullMetadata/PythonFullAttemptTrace record each attempt's script,
error, and stage (generation/sandbox/nothing_drawn/ir_pipeline/success),
attached to the new python_full_metadata field on success. Also captures
partial metadata + token counts before raising on retry exhaustion,
mirroring recipe.py's _partial_* pattern — the exhausts-all-retries case
is exactly where 'what did the model write, what failed' matters most,
and the original design draft missed it.

Also fixes a pre-existing bug found while touching run(): result.input_tokens/
output_tokens were never copied from the accumulated final_state, so they
were always 0 regardless of actual LLM usage across retries. No prior test
asserted on these fields, so it went uncaught until now."
```

---

### Task 3: `evals/run.py` registration + `eval_viewer.py` strip-list

**Files:**
- Modify: `evals/run.py`
- Modify: `evals/eval_viewer.py`
- Modify: `tests/test_eval_runner.py`

**Interfaces:**
- Consumes: `PythonFullStrategy`, `PythonFullMetadata` (Task 2), `StructuredRunResult.python_full_metadata` (Task 1).
- Produces: `"python_full"` in `_STRATEGY_MAP` and `--strategies` `choices`, absent from `_DEFAULT_STRATEGIES`. `_populate_strategy_metadata(record: dict, result: StructuredRunResult) -> None` and `_populate_partial_metadata_on_failure(record: dict, strategy: SubstanceStrategy) -> None` — both directly importable/testable, both called from `run_scenario`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_eval_runner.py
from evals.run import (
    _STRATEGY_MAP, _DEFAULT_STRATEGIES, _OPT_IN_ONLY_STRATEGIES,
    _populate_strategy_metadata, _populate_partial_metadata_on_failure,
)
from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
from geometry_diagrams.strategies.python_full import PythonFullMetadata, PythonFullAttemptTrace
from geometry_diagrams.strategies.recipe import RecipeMetadata, RecipeAttemptTrace
from geometry_diagrams.ir.ir import DiagramIR


def _make_result(**overrides) -> StructuredRunResult:
    defaults = dict(
        diagram_ir=DiagramIR(define=[], checks=[], render=[]),
        tikz="", svg="", sym_table={}, sym_full={},
    )
    defaults.update(overrides)
    return StructuredRunResult(**defaults)


def test_python_full_is_registered_and_opt_in_only():
    assert "python_full" in _STRATEGY_MAP
    assert "python_full" in _OPT_IN_ONLY_STRATEGIES
    assert "python_full" not in _DEFAULT_STRATEGIES
    assert set(_DEFAULT_STRATEGIES) == set(_STRATEGY_MAP) - _OPT_IN_ONLY_STRATEGIES


def test_populate_strategy_metadata_handles_python_full_result():
    result = _make_result(python_full_metadata=PythonFullMetadata(attempt_traces=[
        PythonFullAttemptTrace(attempt=1, script="point(0, 0)", error=None, stage="success"),
    ]))
    record: dict = {"retries": 0}
    _populate_strategy_metadata(record, result)
    assert record["python_full_metadata"]["attempt_traces"] == [
        {"attempt": 1, "script": "point(0, 0)", "error": None, "stage": "success"},
    ]
    assert "recipe_metadata" not in record  # no cross-talk


def test_populate_strategy_metadata_handles_recipe_result_unchanged():
    """Regression: this refactor must not alter RecipeStrategy's existing eval behavior."""
    result = _make_result(recipe_metadata=RecipeMetadata(
        selected_recipes=["triangle_basic"], unmatched_concepts=[],
        confidence="high", is_geometry_request=True,
        selection_input_tokens=5, selection_output_tokens=3,
        attempt_traces=[RecipeAttemptTrace(attempt=1, dsl_json={"x": 1}, error=None, stage="success")],
    ))
    record: dict = {"retries": 0}
    _populate_strategy_metadata(record, result)
    assert record["recipe_metadata"]["selected_recipes"] == ["triangle_basic"]
    assert record["recipe_metadata"]["attempt_traces"] == [
        {"attempt": 1, "dsl_json": {"x": 1}, "error": None, "stage": "success"},
    ]
    assert "python_full_metadata" not in record  # no cross-talk


def test_populate_strategy_metadata_no_metadata_leaves_recipe_metadata_none():
    result = _make_result()
    record: dict = {"retries": 0}
    _populate_strategy_metadata(record, result)
    assert record["recipe_metadata"] is None
    assert "python_full_metadata" not in record


def test_populate_partial_metadata_on_failure_for_python_full():
    class _FakePythonFullStrategy:
        pass
    from geometry_diagrams.strategies.python_full import PythonFullStrategy
    strategy = PythonFullStrategy.__new__(PythonFullStrategy)
    strategy._partial_python_full_metadata = PythonFullMetadata(attempt_traces=[
        PythonFullAttemptTrace(attempt=1, script="bad(", error="syntax error", stage="sandbox"),
    ])
    strategy._partial_input_tokens = 42
    strategy._partial_output_tokens = 7

    record: dict = {"retries": 0}
    _populate_partial_metadata_on_failure(record, strategy)

    assert record["input_tokens"] == 42
    assert record["output_tokens"] == 7
    assert record["python_full_metadata"]["attempt_traces"][0]["error"] == "syntax error"
    assert record["retries"] == 0  # max(0, 1 - 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_eval_runner.py -v -k "python_full or populate_strategy or populate_partial"`
Expected: FAIL — `ImportError: cannot import name '_DEFAULT_STRATEGIES'`

- [ ] **Step 3: Implement the `evals/run.py` changes**

```python
# evals/run.py — add this import near the other strategy imports (after
# the existing `from geometry_diagrams.strategies.recipe import RecipeStrategy`):
from geometry_diagrams.strategies.python_full import PythonFullStrategy
```

```python
# evals/run.py — change _STRATEGY_MAP and add the opt-in-only mechanism
# right after it (replaces lines 83-88):
_STRATEGY_MAP: dict[str, type[SubstanceStrategy]] = {
    "raw_code": RawCodeStrategy,
    "raw_code_with_revise": RawCodeWithReviseStrategy,
    "structured": StructureStrategy,
    "recipe": RecipeStrategy,
    "python_full": PythonFullStrategy,
}

# Strategies excluded from the default --strategies set: new/unproven
# strategies that shouldn't silently join every default eval invocation's
# cost/runtime until deliberately benchmarked at least once. Still fully
# selectable via --strategies <name> (see the "choices" argparse entry).
_OPT_IN_ONLY_STRATEGIES = {"python_full"}
_DEFAULT_STRATEGIES = [name for name in _STRATEGY_MAP if name not in _OPT_IN_ONLY_STRATEGIES]
```

```python
# evals/run.py — new helper functions, added just above run_scenario (before
# "async def run_scenario("):
def _populate_strategy_metadata(record: dict, result: StructuredRunResult) -> None:
    """Populate record['recipe_metadata'] / record['python_full_metadata'] from
    whichever strategy-specific diagnostic field the result actually carries.
    The two fields are independent — a result only ever populates one of them,
    since RecipeStrategy and PythonFullStrategy never share code or types."""
    if result.recipe_metadata is not None:
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
    else:
        record["recipe_metadata"] = None

    if result.python_full_metadata is not None:
        record["python_full_metadata"] = {
            "attempt_traces": [
                {"attempt": t.attempt, "script": t.script, "error": t.error, "stage": t.stage}
                for t in result.python_full_metadata.attempt_traces
            ],
        }
        # NOT re-assigning record["retries"] here: result.retries (set two lines
        # up in run_scenario, from pipeline_result.retries = state["attempt"] in
        # python_full.py's _run_script_node) is already correct for python_full.
        # recipe.py's branch above recomputes retries from attempt_traces because
        # RecipeStrategy's own result.retries isn't reliably set the same way —
        # not the case here, so no duplicate computation is needed.


def _populate_partial_metadata_on_failure(record: dict, strategy: SubstanceStrategy) -> None:
    """Populate whatever diagnostics survive a total failure (retry exhaustion) —
    the strategy raised before returning a StructuredRunResult, so this reads the
    strategy's own _partial_* attributes instead."""
    if isinstance(strategy, RecipeStrategy):
        record["input_tokens"] = getattr(strategy, "_partial_input_tokens", 0)
        record["output_tokens"] = getattr(strategy, "_partial_output_tokens", 0)
        partial_meta = getattr(strategy, "_partial_recipe_metadata", None)
        if partial_meta is not None:
            record["recipe_metadata"] = {
                "selected_recipes": partial_meta.selected_recipes,
                "unmatched_concepts": partial_meta.unmatched_concepts,
                "selection_input_tokens": partial_meta.selection_input_tokens,
                "selection_output_tokens": partial_meta.selection_output_tokens,
                "attempt_traces": [
                    {"attempt": t.attempt, "dsl_json": t.dsl_json, "error": t.error, "stage": t.stage}
                    for t in partial_meta.attempt_traces
                ],
            }
            record["retries"] = max(0, len(partial_meta.attempt_traces) - 1)
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

```python
# evals/run.py — replace the exception-path block inside run_scenario
# (currently lines 274-293) with a call to the new helper:
    except Exception as e:
        record["duration_s"] = round(time.monotonic() - start, 2)
        record["error"] = str(e)
        _populate_partial_metadata_on_failure(record, strategy)
        return record
```

```python
# evals/run.py — replace the recipe_metadata block inside run_scenario
# (currently lines 320-333) with a call to the new helper. This sits right
# after the existing `record["sympy_property_checks"] = sympy_property_checks`
# line and before the "# Query eval phase" comment:
        _populate_strategy_metadata(record, result)
```

```python
# evals/run.py — change the judge skip-list (currently lines 474, 489-491):
    if llm_judge and tikz_code:
        if strategy_name not in ("structured", "python_full"):
            try:
                from geometry_diagrams.util.llm_judge import judge_tikz_code
                judge_result = await judge_tikz_code(
                    prompt=scenario["prompt"],
                    tikz_code=tikz_code,
                    model=judge_model,
                    enable_cache=enable_cache,
                )
                record["llm_judge_score"] = judge_result["score"]
                record["llm_judge_reasoning"] = judge_result["reasoning"]
                record["llm_judge_details"] = judge_result
            except Exception as e:
                record["llm_judge_score"] = None
                record["llm_judge_reasoning"] = f"Judge error: {e}"
        else:
            record["llm_judge_score"] = None
            record["llm_judge_reasoning"] = f"(skipped for {strategy_name} strategy)"
```

```python
# evals/run.py — change the --strategies argparse default (currently line 703):
    parser.add_argument(
        "--strategies",
        nargs="+",
        default=_DEFAULT_STRATEGIES,
        choices=list(_STRATEGY_MAP.keys()),
        help="Strategies to evaluate",
    )
```

- [ ] **Step 4: Fix `evals/eval_viewer.py`'s strip-list**

The new `python_full_metadata` record field can hold full script texts across every retry attempt — it must be stripped from list-view payloads exactly like `recipe_metadata` already is, or the viewer's list endpoint bloats.

```python
# evals/eval_viewer.py — change _record_metadata (currently line ~90-91):
def _record_metadata(record: dict) -> dict:
    """Strip large fields for list views."""
    return {
        k: v for k, v in record.items()
        if k not in ("tikz_code", "diagram_ir", "recipe_dsl", "recipe_metadata", "python_full_metadata")
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_eval_runner.py -v`
Expected: PASS (all tests in the file, including the 5 new ones)

- [ ] **Step 6: Run the full regression suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass — this task must not change `RecipeStrategy`'s or `StructureStrategy`'s existing eval behavior (`test_populate_strategy_metadata_handles_recipe_result_unchanged` is the direct regression check, but the full suite confirms nothing else moved)

- [ ] **Step 7: Sanity-check the CLI wiring manually**

Run: `.venv/bin/python -m evals.run --help 2>&1 | grep -A3 "strategies"` and confirm `python_full` appears as a valid choice but is not silently included if you inspect the printed default (or run `.venv/bin/python -c "from evals.run import _DEFAULT_STRATEGIES, _STRATEGY_MAP; print(_DEFAULT_STRATEGIES); print(list(_STRATEGY_MAP))"`) — `python_full` must appear in the second line, not the first.

- [ ] **Step 8: Commit**

```bash
git add evals/run.py evals/eval_viewer.py tests/test_eval_runner.py
git commit -m "Register python_full with the eval harness, opt-in only

Adds python_full to _STRATEGY_MAP (selectable via --strategies python_full,
excluded from the default set via _OPT_IN_ONLY_STRATEGIES), skips the
TikZ-code LLM judge for it (same reasoning as structured: deterministically
rendered, not LLM-authored code), and extracts _populate_strategy_metadata/
_populate_partial_metadata_on_failure so both the success and total-failure
paths populate the right record fields for recipe_metadata and
python_full_metadata independently — no cross-talk, no isinstance checks
needed since each strategy owns a distinct field. Also fixes
eval_viewer.py's list-view strip-list, which would otherwise bloat on full
per-attempt script texts."
```

---

## Self-Review Notes

- **Spec coverage:** every Design Decision and Component in the spec maps to a task above — the opt-in mechanism, the judge skip-list (plus its message-text fix, a spec-level detail easy to drop), the dedicated `python_full_metadata` field, the per-attempt trace capture including the `script is None` no-touch case, the total-failure `_partial_*` capture, and the extracted-helper test factorability the spec asked for.
- **Gap caught during planning, not in the original spec:** the spec's own reasoning that "both hazards disappear by construction" once `python_full` gets a dedicated field was only true for the `facade.py` crash hazard — `eval_viewer.py`'s strip-list hazard does NOT disappear automatically, since a *new* key name still needs to be added to that list explicitly (the old reasoning conflated "won't crash" with "won't bloat the payload"). Task 3 Step 4 fixes this directly; call it out to whoever reviews this plan against the spec, since the spec's Components section doesn't list `eval_viewer.py` as a file to modify at all.
- **Second gap caught during planning:** `PythonFullStrategy.run()` (already-shipped code, prior plan) never copies `final_state["input_tokens"]`/`["output_tokens"]` onto the returned result — `result.input_tokens`/`output_tokens` are always `0` regardless of actual LLM usage across retries, uncaught because no existing test asserted on them. Task 2 fixes this as a natural side effect of touching `run()` for metadata wiring, with its own dedicated test (`test_run_reports_total_tokens_across_all_attempts`) rather than folding it silently into an unrelated assertion.
- **Type consistency check:** `PythonFullAttemptTrace`/`PythonFullMetadata` field names (`attempt`, `script`, `error`, `stage`, `attempt_traces`) are used identically in Task 2 (definition + population) and Task 3 (the `_populate_strategy_metadata`/`_populate_partial_metadata_on_failure` dict-building code) — verified by re-reading both against each other. `result.python_full_metadata`/`strategy._partial_python_full_metadata` names match across `ir_pipeline.py` (Task 1), `python_full.py` (Task 2), and `evals/run.py` (Task 3).
