"""
Unit tests for util/message_helpers.py and evals/run.py output formatting.

No LLM or Docker required.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import yaml

from langchain_core.messages import AIMessage, ToolMessage

from geometry_diagrams.util.message_helpers import count_tool_calls, extract_tool_call_args, extract_tool_return


# ---------------------------------------------------------------------------
# Helpers — build synthetic LangChain message lists
# ---------------------------------------------------------------------------

def _make_return(tool_name: str, content: str) -> ToolMessage:
    return ToolMessage(content=content, name=tool_name, tool_call_id="x")


def _make_call(tool_name: str, args) -> AIMessage:
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            # Keep as string — will be tested for None result
            return AIMessage(content="", tool_calls=[{"name": tool_name, "args": args, "id": "y", "type": "tool_call"}])
    return AIMessage(content="", tool_calls=[{"name": tool_name, "args": args, "id": "y", "type": "tool_call"}])


# ---------------------------------------------------------------------------
# extract_tool_return
# ---------------------------------------------------------------------------

def test_extract_tool_return_string_content():
    messages = [_make_return("render_diagram", '{"svg": "<svg/>"}')]
    result = extract_tool_return(messages, "render_diagram")
    assert result == '{"svg": "<svg/>"}'


def test_extract_tool_return_finds_last_match():
    messages = [
        _make_return("render_diagram", "first"),
        _make_return("render_diagram", "second"),
    ]
    result = extract_tool_return(messages, "render_diagram")
    assert result == "second"


def test_extract_tool_return_wrong_tool():
    messages = [_make_return("other_tool", "data")]
    assert extract_tool_return(messages, "render_diagram") is None


def test_extract_tool_return_empty_messages():
    assert extract_tool_return([], "render_diagram") is None


def test_extract_tool_return_ignores_non_tool_message():
    messages = [_make_call("render_diagram", {})]  # AIMessage, not ToolMessage
    assert extract_tool_return(messages, "render_diagram") is None


# ---------------------------------------------------------------------------
# extract_tool_call_args
# ---------------------------------------------------------------------------

def test_extract_tool_call_args_dict():
    messages = [_make_call("render_diagram", {"tikz": "\\tkzDefPoint(0,0){A}"})]
    result = extract_tool_call_args(messages, "render_diagram")
    assert result == {"tikz": "\\tkzDefPoint(0,0){A}"}


def test_extract_tool_call_args_finds_last_call():
    messages = [
        _make_call("render_diagram", {"tikz": "first"}),
        _make_call("render_diagram", {"tikz": "second"}),
    ]
    result = extract_tool_call_args(messages, "render_diagram")
    assert result == {"tikz": "second"}


def test_extract_tool_call_args_wrong_tool():
    messages = [_make_call("other_tool", {"tikz": "code"})]
    assert extract_tool_call_args(messages, "render_diagram") is None


# ---------------------------------------------------------------------------
# count_tool_calls
# ---------------------------------------------------------------------------

def test_count_tool_calls_multiple():
    messages = [
        _make_call("render_diagram", {}),
        _make_call("render_diagram", {}),
        _make_call("other_tool", {}),
    ]
    assert count_tool_calls(messages, "render_diagram") == 2


def test_count_tool_calls_none():
    messages = [_make_call("other_tool", {})]
    assert count_tool_calls(messages, "render_diagram") == 0


def test_count_tool_calls_ignores_returns():
    messages = [
        _make_call("render_diagram", {}),
        _make_return("render_diagram", "result"),  # ToolMessage, not AIMessage
    ]
    assert count_tool_calls(messages, "render_diagram") == 1


# ---------------------------------------------------------------------------
# _print_record and _print_summary (from evals/run.py)
# ---------------------------------------------------------------------------

def _capture(fn, *args, **kwargs) -> str:
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        fn(*args, **kwargs)
    finally:
        sys.stdout = old
    return buf.getvalue()


def _base_record(**overrides) -> dict:
    r = {
        "scenario_id": "right-triangle",
        "strategy": "raw_code",
        "repeat_index": 1,
        "generation_success": True,
        "svg_rendered": True,
        "svg_checks": {"passed": True, "failures": []},
        "tikz_checks": None,
        "llm_judge_score": None,
        "llm_judge_reasoning": None,
        "retries": 0,
        "duration_s": 3.5,
        "error": None,
    }
    r.update(overrides)
    return r


def test_print_record_ok():
    from evals.reporting import _print_record
    output = _capture(_print_record, _base_record(generation_success=True))
    assert "[OK ]" in output


def test_print_record_err():
    from evals.reporting import _print_record
    output = _capture(_print_record, _base_record(generation_success=False, svg_rendered=False, svg_checks=None))
    assert "[ERR]" in output


def test_print_record_shows_judge_score():
    from evals.reporting import _print_record
    output = _capture(_print_record, _base_record(llm_judge_score=4))
    assert "J:4/5" in output


def test_print_summary_aggregates():
    from evals.reporting import _print_summary
    records = [
        _base_record(generation_success=True, svg_rendered=True),
        _base_record(generation_success=True, svg_rendered=True),
        _base_record(generation_success=False, svg_rendered=False, svg_checks=None),
    ]
    output = _capture(_print_summary, records)
    assert "raw_code" in output
    assert "gen:2/3" in output
    assert "gate:" in output


# ---------------------------------------------------------------------------
# Scenario validation and gate status
# ---------------------------------------------------------------------------

def test_validate_scenarios_accepts_grid_metadata():
    from evals.scenarios import _validate_scenarios

    scenarios = _validate_scenarios([{
        "id": "grid-right-triangle",
        "tier": 2,
        "tags": ["grid", "core"],
        "prompt": "Draw a triangle on a grid.",
        "required_canvas": {"grid": True, "axes": True},
        "expected_points": {"A": [0, 0], "B": [4, 0], "C": [0, 3]},
        "coordinate_tolerance": 1e-4,
        "expected_properties": [{"name": "right", "type": "right_angle", "args": ["B", "A", "C"]}],
    }])
    assert scenarios[0]["required_canvas"] == {"grid": True, "axes": True}
    assert scenarios[0]["expected_points"]["B"] == [4.0, 0.0]


def test_finalize_gate_status_pass():
    from evals.run import _finalize_gate_status

    record = _base_record(
        tikz_checks={"right_angle": {"passed": True, "type": "right_angle", "skipped": False}},
        canvas_checks={"passed": True, "missing": [], "features": {"grid": True, "axes": True}},
        expected_point_checks={"passed": True, "missing": [], "mismatches": {}},
    )
    _finalize_gate_status(record)
    assert record["deterministic_pass"] is True
    assert record["gate_status"] == "pass"
    assert record["gate_failures"] == []


def test_finalize_gate_status_soft_pass_on_skipped_check():
    from evals.run import _finalize_gate_status

    record = _base_record(
        tikz_checks={"transversal": {"passed": None, "type": "parallel", "skipped": True}},
    )
    _finalize_gate_status(record)
    assert record["deterministic_pass"] is None
    assert record["gate_status"] == "soft_pass"


def test_finalize_gate_status_fail_on_expected_point_mismatch():
    from evals.run import _finalize_gate_status

    record = _base_record(
        expected_point_checks={
            "passed": False,
            "missing": [],
            "mismatches": {"A": {"expected": [0.0, 0.0], "actual": [1.0, 0.0]}},
        },
    )
    _finalize_gate_status(record)
    assert record["deterministic_pass"] is False
    assert record["gate_status"] == "fail"
    assert "point:A:mismatch" in record["gate_failures"]


def test_finalize_gate_status_fail_on_generation_failure():
    from evals.run import _finalize_gate_status

    record = _base_record(generation_success=False, svg_rendered=False, svg_checks=None)
    _finalize_gate_status(record)
    assert record["gate_status"] == "fail"
    assert "generation" in record["gate_failures"]


def test_load_retry_timeout_counts_counts_per_scenario(tmp_path: Path):
    from evals.run import _load_retry_timeout_counts

    records = [
        {"scenario_id": "a", "error": "scenario timed out after 180s"},
        {"scenario_id": "a", "error": "scenario timed out after 180s"},
        {"scenario_id": "b", "error": "scenario timed out after 180s"},
        {"scenario_id": "a", "error": None},
        {"scenario_id": "c", "error": "RecipeStrategy failed after 3 attempts. Last error: ..."},
    ]
    path = tmp_path / "results.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    assert _load_retry_timeout_counts(path) == {"a": 2, "b": 1}


def test_load_retry_timeout_counts_empty_when_no_timeouts(tmp_path: Path):
    from evals.run import _load_retry_timeout_counts

    records = [{"scenario_id": "a", "error": None}, {"scenario_id": "b", "error": "some other failure"}]
    path = tmp_path / "results.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    assert _load_retry_timeout_counts(path) == {}


def test_load_retry_timeout_counts_skips_blank_lines(tmp_path: Path):
    from evals.run import _load_retry_timeout_counts

    path = tmp_path / "results.jsonl"
    path.write_text('{"scenario_id": "a", "error": "scenario timed out after 180s"}\n\n')

    assert _load_retry_timeout_counts(path) == {"a": 1}


def test_core_scenarios_include_grid_cases():
    from evals.scenarios import _validate_scenarios

    path = Path("evals/scenarios_core.yaml")
    scenarios = _validate_scenarios(yaml.safe_load(path.read_text()))
    ids = {scenario["id"] for scenario in scenarios}
    assert "grid-right-triangle" in ids
    assert "grid-midpoint-bisector" in ids
    assert "similar-triangles" in ids


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
