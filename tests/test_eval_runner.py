"""
Unit tests for util/message_helpers.py and evals/run.py output formatting.

No LLM or Docker required.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import yaml

from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart

from util.message_helpers import count_tool_calls, extract_tool_call_args, extract_tool_return


# ---------------------------------------------------------------------------
# Helpers — build synthetic message lists
# ---------------------------------------------------------------------------

def _make_return(tool_name: str, content: str) -> ModelRequest:
    return ModelRequest(parts=[ToolReturnPart(tool_name=tool_name, content=content, tool_call_id="x")])


def _make_call(tool_name: str, args) -> ModelResponse:
    if isinstance(args, dict):
        import json
        args = json.dumps(args)
    return ModelResponse(parts=[ToolCallPart(tool_name=tool_name, args=args, tool_call_id="y")])


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


def test_extract_tool_return_ignores_non_request():
    messages = [_make_call("render_diagram", "{}")]  # ModelResponse, not ModelRequest
    assert extract_tool_return(messages, "render_diagram") is None


# ---------------------------------------------------------------------------
# extract_tool_call_args
# ---------------------------------------------------------------------------

def test_extract_tool_call_args_json_string():
    messages = [_make_call("render_diagram", '{"tikz": "\\\\tkzDefPoint(0,0){A}"}')]
    result = extract_tool_call_args(messages, "render_diagram")
    assert result == {"tikz": "\\tkzDefPoint(0,0){A}"}


def test_extract_tool_call_args_dict():
    from pydantic_ai.messages import ToolCallPart
    # ToolCallPart accepts dict directly for args
    part = ToolCallPart(tool_name="render_diagram", args={"tikz": "code"}, tool_call_id="z")
    messages = [ModelResponse(parts=[part])]
    result = extract_tool_call_args(messages, "render_diagram")
    assert result == {"tikz": "code"}


def test_extract_tool_call_args_bad_json():
    messages = [_make_call("render_diagram", "not valid json {")]
    result = extract_tool_call_args(messages, "render_diagram")
    assert result is None


def test_extract_tool_call_args_finds_last_call():
    messages = [
        _make_call("render_diagram", '{"tikz": "first"}'),
        _make_call("render_diagram", '{"tikz": "second"}'),
    ]
    result = extract_tool_call_args(messages, "render_diagram")
    assert result == {"tikz": "second"}


def test_extract_tool_call_args_wrong_tool():
    messages = [_make_call("other_tool", '{"tikz": "code"}')]
    assert extract_tool_call_args(messages, "render_diagram") is None


# ---------------------------------------------------------------------------
# count_tool_calls
# ---------------------------------------------------------------------------

def test_count_tool_calls_multiple():
    messages = [
        _make_call("render_diagram", "{}"),
        _make_call("render_diagram", "{}"),
        _make_call("other_tool", "{}"),
    ]
    assert count_tool_calls(messages, "render_diagram") == 2


def test_count_tool_calls_none():
    messages = [_make_call("other_tool", "{}")]
    assert count_tool_calls(messages, "render_diagram") == 0


def test_count_tool_calls_ignores_returns():
    messages = [
        _make_call("render_diagram", "{}"),
        _make_return("render_diagram", "result"),  # ToolReturn, not call
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
    from evals.run import _print_record
    output = _capture(_print_record, _base_record(generation_success=True))
    assert "[OK ]" in output


def test_print_record_err():
    from evals.run import _print_record
    output = _capture(_print_record, _base_record(generation_success=False, svg_rendered=False, svg_checks=None))
    assert "[ERR]" in output


def test_print_record_shows_judge_score():
    from evals.run import _print_record
    output = _capture(_print_record, _base_record(llm_judge_score=4))
    assert "J:4/5" in output


def test_print_summary_aggregates():
    from evals.run import _print_summary
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
    from evals.run import _validate_scenarios

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


def test_core_scenarios_include_grid_cases():
    from evals.run import _validate_scenarios

    path = Path("evals/scenarios_core.yaml")
    scenarios = _validate_scenarios(yaml.safe_load(path.read_text()))
    ids = {scenario["id"] for scenario in scenarios}
    assert "grid-right-triangle" in ids
    assert "grid-midpoint-bisector" in ids
    assert "similar-triangles" in ids
