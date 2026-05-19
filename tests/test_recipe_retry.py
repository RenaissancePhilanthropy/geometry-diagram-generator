"""
Tests for RecipeStrategy retry behaviour and contextual error hints.

All LLM calls are mocked — no network or Docker required.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import pydantic
from langchain_core.exceptions import OutputParserException

from recipe.dsl import RecipeDSL
from strategies.recipe import RecipeStrategy, MAX_RETRIES, RecipeAttemptTrace, _build_retry_hints
from strategies.structured import StructuredRunResult
from ir.ir import DiagramIR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_result() -> StructuredRunResult:
    fake_ir = DiagramIR(define=[], checks=[], render=[])
    return StructuredRunResult(diagram_ir=fake_ir, tikz="", svg="<svg/>",
                               sym_table={}, sym_full={})


def _make_valid_dsl() -> RecipeDSL:
    return RecipeDSL(construction=[])


def _wrap_dsl(dsl: RecipeDSL) -> dict:
    """Wrap a RecipeDSL in the include_raw=True response dict format."""
    raw = MagicMock()
    raw.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 5}}
    return {"raw": raw, "parsed": dsl, "parsing_error": None}


def _make_mock_llm(gen_side_effects: list):
    """Return a mock LLM where with_structured_output().ainvoke() uses gen_side_effects."""
    # Selector response
    selector_response = MagicMock()
    selector_response.content = '{"selected_recipes": [], "unmatched_concepts": []}'
    selector_response.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 5}}

    structured_mock = MagicMock()
    structured_mock.ainvoke = AsyncMock(side_effect=gen_side_effects)

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=selector_response)
    mock_llm.with_structured_output = MagicMock(return_value=structured_mock)
    return mock_llm


def _common_patches(mock_llm, pipeline_mock=None):
    """Return context manager patches common to all recipe retry tests."""
    fake_result = _make_fake_result()
    return (
        patch("strategies.recipe.get_chat_model", return_value=mock_llm),
        patch("strategies.recipe.lower_to_ir", return_value=MagicMock()),
        patch("strategies.recipe._run_ir_pipeline",
              new=AsyncMock(return_value=fake_result) if pipeline_mock is None else pipeline_mock),
        patch("strategies.recipe.load_catalog", return_value=[]),
        patch("strategies.recipe.build_selection_prompt", return_value="select"),
        patch("strategies.recipe.build_generation_prompt", return_value="generate this RecipeDSL"),
    )


# ---------------------------------------------------------------------------
# Unit tests for _build_retry_hints
# ---------------------------------------------------------------------------

def test_build_retry_hints_angle_equal():
    error = "Geometric checks failed: AngleEqual(A,B,C) != AngleEqual(D,E,F)"
    hints = _build_retry_hints(error)
    assert "AngleEqual" in hints or "angle" in hints.lower()


def test_build_retry_hints_mark_right_angle():
    error = "Geometric checks failed: mark_right_angle(A,M,C) is 153°"
    hints = _build_retry_hints(error)
    assert hints  # Should produce some hint


def test_build_retry_hints_circular():
    error = "IR compilation failed: circular dependency detected"
    hints = _build_retry_hints(error)
    assert hints


def test_build_retry_hints_between_selector():
    error = "no candidate lies between 'A' and 'B' (nearest is beyond 'B', t≈1.40)"
    hints = _build_retry_hints(error)
    assert hints


def test_build_retry_hints_no_match_returns_empty():
    error = "Points A and B coincide"
    hints = _build_retry_hints(error)
    assert hints == ""


# ---------------------------------------------------------------------------
# Test 1: OutputParserException caught and becomes retriable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recipe_strategy_catches_output_parser_exception():
    """Generation raises OutputParserException twice, then succeeds."""
    error = OutputParserException("Failed to parse RecipeDSL")
    valid_dsl = _make_valid_dsl()
    mock_llm = _make_mock_llm([error, error, _wrap_dsl(valid_dsl)])

    p1, p2, p3, p4, p5, p6 = _common_patches(mock_llm)
    with p1, p2, p3, p4, p5, p6:
        strategy = RecipeStrategy()
        result = await strategy.run("Draw a triangle.")

    traces = result.recipe_metadata.attempt_traces
    stages = [t.stage for t in traces]
    assert "output_validation" in stages
    assert stages[-1] == "success"


# ---------------------------------------------------------------------------
# Test 2: All retries exhausted → RuntimeError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recipe_strategy_all_retries_exhaust_raises():
    """All MAX_RETRIES attempts raise OutputParserException → RuntimeError."""
    error = OutputParserException("Failed to parse RecipeDSL")
    mock_llm = _make_mock_llm([error] * MAX_RETRIES)

    p1, p2, p3, p4, p5, p6 = _common_patches(mock_llm)
    with p1, p2, p3, p4, p5, p6:
        strategy = RecipeStrategy()
        with pytest.raises(RuntimeError, match="RecipeStrategy failed"):
            await strategy.run("Draw a triangle.")

    traces = strategy._partial_recipe_metadata.attempt_traces
    assert len(traces) == MAX_RETRIES
    assert all(t.stage == "output_validation" for t in traces)


# ---------------------------------------------------------------------------
# Test 3: IR pipeline failure triggers retry with error in next prompt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recipe_strategy_retries_on_pipeline_failure():
    """IR pipeline fails once, then succeeds. Two DSL generation attempts made."""
    valid_dsl = _make_valid_dsl()
    mock_llm = _make_mock_llm([_wrap_dsl(valid_dsl), _wrap_dsl(valid_dsl)])

    fake_result = _make_fake_result()
    pipeline_call_count = {"n": 0}

    async def mock_pipeline(*args, **kwargs):
        pipeline_call_count["n"] += 1
        if pipeline_call_count["n"] == 1:
            raise RuntimeError("Geometric checks failed: some check")
        return fake_result

    p1, p2, p4, p5, p6 = (
        patch("strategies.recipe.get_chat_model", return_value=mock_llm),
        patch("strategies.recipe.lower_to_ir", return_value=MagicMock()),
        patch("strategies.recipe.load_catalog", return_value=[]),
        patch("strategies.recipe.build_selection_prompt", return_value="select"),
        patch("strategies.recipe.build_generation_prompt", return_value="generate RecipeDSL"),
    )
    with p1, p2, patch("strategies.recipe._run_ir_pipeline", new=mock_pipeline), p4, p5, p6:
        strategy = RecipeStrategy()
        result = await strategy.run("Draw a triangle.")

    assert isinstance(result, StructuredRunResult)
    assert pipeline_call_count["n"] == 2


# ---------------------------------------------------------------------------
# Test 4: AngleEqual hint appended on retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_angle_hint_appended_on_retry():
    """When IR pipeline fails with AngleEqual error, retry prompt includes hint."""
    valid_dsl = _make_valid_dsl()
    captured_messages = []

    # Wrap ainvoke to capture the messages argument
    call_count = {"n": 0}

    async def capturing_ainvoke(messages):
        captured_messages.append(messages)
        call_count["n"] += 1
        return _wrap_dsl(valid_dsl)

    structured_mock = MagicMock()
    structured_mock.ainvoke = capturing_ainvoke

    selector_response = MagicMock()
    selector_response.content = '{"selected_recipes": [], "unmatched_concepts": []}'
    selector_response.response_metadata = {"usage": {"input_tokens": 5, "output_tokens": 3}}

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=selector_response)
    mock_llm.with_structured_output = MagicMock(return_value=structured_mock)

    fake_result = _make_fake_result()
    pipeline_call_count = {"n": 0}

    async def mock_pipeline(*args, **kwargs):
        pipeline_call_count["n"] += 1
        if pipeline_call_count["n"] == 1:
            raise RuntimeError("AngleEqual check failed: angles not equal")
        return fake_result

    with (
        patch("strategies.recipe.get_chat_model", return_value=mock_llm),
        patch("strategies.recipe.lower_to_ir", return_value=MagicMock()),
        patch("strategies.recipe._run_ir_pipeline", new=mock_pipeline),
        patch("strategies.recipe.load_catalog", return_value=[]),
        patch("strategies.recipe.build_selection_prompt", return_value="select"),
        patch("strategies.recipe.build_generation_prompt", return_value="generate RecipeDSL"),
    ):
        strategy = RecipeStrategy()
        result = await strategy.run("Draw a triangle.")

    assert call_count["n"] >= 2, "Expected at least 2 DSL generation calls"
    # The second call's HumanMessage must contain BOTH the original error text AND
    # the specific hint injected by _build_retry_hints — not just boilerplate "angle".
    from langchain_core.messages import HumanMessage as LCHumanMessage
    second_call_messages = captured_messages[1]
    human_msgs = [m for m in second_call_messages if isinstance(m, LCHumanMessage)]
    assert human_msgs, "No HumanMessage in second DSL gen call"
    human_content = str(human_msgs[-1].content)
    assert "AngleEqual" in human_content, (
        f"Expected error text 'AngleEqual' in retry human message, got: {human_content[:300]}"
    )
    assert "three distinct points" in human_content, (
        f"Expected hint text 'three distinct points' in retry human message, got: {human_content[:300]}"
    )
