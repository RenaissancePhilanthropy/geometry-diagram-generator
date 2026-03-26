# tests/test_recipe_strategy.py
"""Mocked LLM tests for RecipeStrategy.

All LLM calls (pydantic_ai.Agent.run) and the IR pipeline are mocked so
no network, Docker, or renderer is required.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from recipe.dsl import RecipeDSL
from strategies.recipe import RecipeStrategy
from strategies.structured import StructuredRunResult
from ir.ir import DiagramIR
from recipe.lower import LoweringError


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SIMPLE_DSL = {
    "mode": "grid",
    "construction": [
        {"op": "point", "id": "A", "coords": [0.0, 0.0]},
        {"op": "point", "id": "B", "coords": [3.0, 0.0]},
        {"op": "segment", "id": "s1", "endpoints": ["A", "B"]},
    ],
    "annotations": {"auto_draw_all": True, "auto_label_points": False},
}


def _make_fake_result() -> StructuredRunResult:
    fake_ir = DiagramIR(define=[], checks=[], render=[])
    return StructuredRunResult(diagram_ir=fake_ir, tikz="\\tkzInit", svg="<svg/>")


def _make_gen_response(dsl: RecipeDSL | None = None) -> MagicMock:
    """Build a mock Agent.run() return value for the generation call."""
    mock_usage = MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 20

    mock_response = MagicMock()
    mock_response.output = dsl if dsl is not None else RecipeDSL.model_validate(SIMPLE_DSL)
    mock_response.usage.return_value = mock_usage
    return mock_response


def _make_sel_response(body: str | None = None) -> MagicMock:
    """Build a mock Agent.run() return value for the selector call."""
    mock_usage = MagicMock()
    mock_usage.input_tokens = 5
    mock_usage.output_tokens = 8

    mock_response = MagicMock()
    mock_response.output = body or '{"selected_recipes": [], "unmatched_concepts": []}'
    mock_response.usage.return_value = mock_usage
    return mock_response


# ---------------------------------------------------------------------------
# Test 1: use_recipes=False — single Agent call, result is StructuredRunResult
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recipe_strategy_no_recipes_returns_result():
    """With use_recipes=False, one Agent call; result carries empty selected_recipes."""
    strategy = RecipeStrategy(use_recipes=False)
    fake_result = _make_fake_result()
    gen_response = _make_gen_response()

    with (
        patch("strategies.recipe.Agent") as MockAgent,
        patch("strategies.recipe._run_ir_pipeline", new=AsyncMock(return_value=fake_result)),
    ):
        mock_agent_instance = MagicMock()
        mock_agent_instance.run = AsyncMock(return_value=gen_response)
        MockAgent.return_value = mock_agent_instance

        result = await strategy.run("draw two points", model="test-model")

    assert isinstance(result, StructuredRunResult)
    assert result.recipe_metadata is not None
    assert result.recipe_metadata.selected_recipes == []


# ---------------------------------------------------------------------------
# Test 2: use_recipes=True — selector called first, then generation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recipe_strategy_with_recipes_calls_selector():
    """With use_recipes=True, Agent is instantiated twice (selector + generator)."""
    strategy = RecipeStrategy(use_recipes=True)
    fake_result = _make_fake_result()
    sel_response = _make_sel_response()
    gen_response = _make_gen_response()

    call_responses = [sel_response, gen_response]

    with (
        patch("strategies.recipe.Agent") as MockAgent,
        patch("strategies.recipe._run_ir_pipeline", new=AsyncMock(return_value=fake_result)),
        patch("strategies.recipe.load_catalog", return_value=[]),
        patch("strategies.recipe.load_recipe", side_effect=KeyError("not found")),
    ):
        mock_agent_instance = MagicMock()
        mock_agent_instance.run = AsyncMock(side_effect=call_responses)
        MockAgent.return_value = mock_agent_instance

        result = await strategy.run("draw a triangle", model="test-model")

    assert isinstance(result, StructuredRunResult)
    assert result.recipe_metadata is not None
    # Agent was constructed twice (once for selector, once for generator)
    assert MockAgent.call_count == 2


# ---------------------------------------------------------------------------
# Test 3: retry on lowering error — second attempt succeeds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recipe_strategy_retries_on_lowering_error():
    """First lowering raises LoweringError; second attempt succeeds."""
    strategy = RecipeStrategy(use_recipes=False)
    fake_result = _make_fake_result()
    gen_response = _make_gen_response()

    with (
        patch("strategies.recipe.Agent") as MockAgent,
        patch(
            "strategies.recipe.lower_to_ir",
            side_effect=[LoweringError("bad dsl"), MagicMock()],
        ),
        patch("strategies.recipe._run_ir_pipeline", new=AsyncMock(return_value=fake_result)),
    ):
        mock_agent_instance = MagicMock()
        # Both calls return a valid RecipeDSL response
        mock_agent_instance.run = AsyncMock(return_value=gen_response)
        MockAgent.return_value = mock_agent_instance

        result = await strategy.run("draw something", model="test-model")

    assert isinstance(result, StructuredRunResult)


# ---------------------------------------------------------------------------
# Test 4: raises RuntimeError after MAX_RETRIES exhausted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recipe_strategy_raises_after_max_retries():
    """All attempts fail with LoweringError; RuntimeError raised after MAX_RETRIES."""
    from strategies.recipe import MAX_RETRIES

    strategy = RecipeStrategy(use_recipes=False)
    gen_response = _make_gen_response()

    with (
        patch("strategies.recipe.Agent") as MockAgent,
        patch(
            "strategies.recipe.lower_to_ir",
            side_effect=LoweringError("always fails"),
        ),
    ):
        mock_agent_instance = MagicMock()
        mock_agent_instance.run = AsyncMock(return_value=gen_response)
        MockAgent.return_value = mock_agent_instance

        with pytest.raises(RuntimeError, match="RecipeStrategy failed after"):
            await strategy.run("draw something", model="test-model")

    # Agent was constructed MAX_RETRIES times (one per attempt)
    assert MockAgent.call_count == MAX_RETRIES
