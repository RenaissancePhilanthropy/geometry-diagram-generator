"""Tests for PythonFullStrategy and its LangGraph pipeline.

Only the LLM call is mocked — the real pydsl sandbox and the real
compile/check/render pipeline run for real (SVGRenderer, no Docker needed).
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from geometry_diagrams.strategies.python_full import (
    PythonFullStrategy, PydslScriptOutput, MAX_RETRIES, _run_script_node,
    _extract_script_from_raw_text,
)
from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.pydsl.sandbox import ScriptResult


VALID_SCRIPT = """
a = point(0, 0)
b = point(4, 0)
c = point(0, 3)
t = triangle(a, b, c)
draw(t)
"""

TYPO_SCRIPT = """
a = point(0, 0)
b = point(4, 0)
c = point(0, 3)
t = triangel(a, b, c)
draw(t)
"""

NO_DRAW_SCRIPT = """
a = point(0, 0)
b = point(4, 0)
c = point(0, 3)
t = triangle(a, b, c)
"""


def _make_script_response(script: str) -> dict:
    raw = MagicMock()
    raw.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 20}}
    raw.usage_metadata = {"input_tokens": 10, "output_tokens": 20}
    return {"raw": raw, "parsed": PydslScriptOutput(script=script), "parsing_error": None}


def _make_script_fail_response() -> dict:
    raw = MagicMock()
    raw.response_metadata = {"usage": {"input_tokens": 5, "output_tokens": 2}}
    raw.usage_metadata = {"input_tokens": 5, "output_tokens": 2}
    return {"raw": raw, "parsed": None, "parsing_error": "bad JSON from LLM"}


def _make_mock_llm(side_effects: list):
    """Return a mock LLM where with_structured_output().ainvoke() uses side_effects."""
    structured_mock = MagicMock()
    structured_mock.ainvoke = AsyncMock(side_effect=side_effects)
    mock_llm = MagicMock()
    mock_llm.with_structured_output = MagicMock(return_value=structured_mock)
    return mock_llm


@pytest.mark.asyncio
async def test_first_attempt_success():
    mock_llm = _make_mock_llm([_make_script_response(VALID_SCRIPT)])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert isinstance(result, StructuredRunResult)
    assert result.retries == 0
    assert len(result.diagram_ir.define) > 0
    assert len(result.diagram_ir.render) > 0


@pytest.mark.asyncio
async def test_script_gen_failure_costs_one_attempt():
    """Mirrors test_structured_strategy.py's test_ir_gen_failure_costs_one_attempt:
    after script generation fails once, the sandbox must still run on the next
    attempt — _run_script_node must not double-count a generation failure."""
    mock_llm = _make_mock_llm([
        _make_script_fail_response(),
        _make_script_response(VALID_SCRIPT),
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert isinstance(result, StructuredRunResult)
    assert result.retries == 1


@pytest.mark.asyncio
async def test_sandbox_failure_retries_with_did_you_mean_and_succeeds():
    mock_llm = _make_mock_llm([
        _make_script_response(TYPO_SCRIPT),
        _make_script_response(VALID_SCRIPT),
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert isinstance(result, StructuredRunResult)
    assert result.retries == 1


@pytest.mark.asyncio
async def test_nothing_drawn_guard_retries_and_succeeds():
    mock_llm = _make_mock_llm([
        _make_script_response(NO_DRAW_SCRIPT),
        _make_script_response(VALID_SCRIPT),
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert isinstance(result, StructuredRunResult)
    assert result.retries == 1


@pytest.mark.asyncio
async def test_exhausts_retries_and_raises():
    mock_llm = _make_mock_llm([_make_script_response(TYPO_SCRIPT)] * MAX_RETRIES)
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        with pytest.raises(RuntimeError, match="PythonFullStrategy failed"):
            await strategy.run(
                "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
            )


@pytest.mark.asyncio
async def test_run_script_node_falls_back_to_error_when_retry_message_is_none():
    """sandbox.py's ExecutionTimeoutError branch always sets retry_message=None —
    _run_script_node must fall back to result.error so last_error is never empty.
    Tested directly against a canned ScriptResult (not a real timing-dependent
    sandbox race) since this is a deterministic fallback-logic check, not an
    integration behavior."""
    fake_result = ScriptResult(
        diagram_ir=None, error="boom, timed out", error_type="timeout", retry_message=None,
    )
    with patch("geometry_diagrams.strategies.python_full.run_script", return_value=fake_result):
        state = {"script": "point(0, 0)", "attempt": 0, "renderer": SVGRenderer()}
        update = await _run_script_node(state)
    assert update["last_error"] == "boom, timed out"
    assert update["attempt"] == 1


def test_build_agent_raises_not_implemented():
    strategy = PythonFullStrategy()
    with pytest.raises(NotImplementedError):
        strategy.build_agent(model="anthropic:claude-sonnet-4-6")


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


# ---------------------------------------------------------------------------
# Fallback: some models don't honor the structured-output contract and just
# write plain/fenced code instead of JSON. _extract_script_from_raw_text lets
# _generate_script_node salvage a usable script from that raw text rather than
# treating it as an unrecoverable parse failure.
# ---------------------------------------------------------------------------

def test_extract_script_from_python_fenced_code_block():
    text = "Here's the script:\n```python\na = point(0, 0)\ndraw(a)\n```"
    assert _extract_script_from_raw_text(text) == "a = point(0, 0)\ndraw(a)"


def test_extract_script_from_bare_fenced_code_block():
    text = "```\na = point(0, 0)\ndraw(a)\n```"
    assert _extract_script_from_raw_text(text) == "a = point(0, 0)\ndraw(a)"


def test_extract_script_falls_back_to_raw_text_when_no_fence_present():
    text = "a = point(0, 0)\ndraw(a)"
    assert _extract_script_from_raw_text(text) == "a = point(0, 0)\ndraw(a)"


def test_extract_script_returns_none_for_empty_text():
    assert _extract_script_from_raw_text("") is None
    assert _extract_script_from_raw_text("   \n  ") is None


def _make_unparsed_response(raw_content: str) -> dict:
    """A with_structured_output(include_raw=True) response where JSON parsing
    failed but the underlying model message still carries usable text."""
    raw = MagicMock()
    raw.response_metadata = {"usage": {"input_tokens": 8, "output_tokens": 12}}
    raw.usage_metadata = {"input_tokens": 8, "output_tokens": 12}
    raw.content = raw_content
    return {"raw": raw, "parsed": None, "parsing_error": "Invalid JSON: expected value at line 1 column 1"}


@pytest.mark.asyncio
async def test_generate_script_node_salvages_a_script_from_fenced_raw_text_on_parse_failure():
    """The exact failure mode seen from a real weaker model: with_structured_output
    can't parse the model's markdown-fenced code as JSON, but the code itself is
    fine — this must succeed via the fallback, not be treated as a bare failure."""
    mock_llm = _make_mock_llm([
        _make_unparsed_response(f"```python\n{VALID_SCRIPT.strip()}\n```"),
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert isinstance(result, StructuredRunResult)
    assert result.retries == 0
    assert result.python_full_metadata.attempt_traces[0].stage == "success"


@pytest.mark.asyncio
async def test_generate_script_node_still_fails_when_raw_text_is_empty():
    """If there's truly nothing to salvage (empty raw content), this must still
    be a real generation failure, not silently succeed with an empty script."""
    mock_llm = _make_mock_llm([
        _make_unparsed_response(""),
        _make_script_response(VALID_SCRIPT),
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert isinstance(result, StructuredRunResult)
    assert result.retries == 1
    assert result.python_full_metadata.attempt_traces[0].stage == "generation"
    assert result.python_full_metadata.attempt_traces[0].script is None
