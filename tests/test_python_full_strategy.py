"""Tests for PythonFullStrategy and its LangGraph pipeline.

Only the LLM call is mocked — the real pydsl sandbox and the real
compile/check/render pipeline run for real (SVGRenderer, no Docker needed).
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from geometry_diagrams.strategies.python_full import (
    PythonFullStrategy, PydslScriptOutput, MAX_RETRIES, _run_script_node,
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
    return {"raw": raw, "parsed": PydslScriptOutput(script=script), "parsing_error": None}


def _make_script_fail_response() -> dict:
    raw = MagicMock()
    raw.response_metadata = {"usage": {"input_tokens": 5, "output_tokens": 2}}
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
