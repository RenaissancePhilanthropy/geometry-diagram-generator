# tests/test_recipe_strategy.py
"""Mocked LLM tests for RecipeStrategy.

All LLM calls (via get_chat_model) and the IR pipeline are mocked so
no network, Docker, or renderer is required.
"""
from __future__ import annotations

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
    return StructuredRunResult(diagram_ir=fake_ir, tikz="\\tkzInit", svg="<svg/>",
                               sym_table={}, sym_full={})


def _make_raw_response(dsl: RecipeDSL) -> dict:
    """Wrap a RecipeDSL in the include_raw=True response dict format."""
    raw = MagicMock()
    raw.response_metadata = {"usage": {"input_tokens": 5, "output_tokens": 8}}
    return {"raw": raw, "parsed": dsl, "parsing_error": None}


def _make_mock_llm(selector_text: str = '{"selected_recipes": [], "unmatched_concepts": []}',
                   gen_dsl: RecipeDSL | None = None):
    """Return a mock chat model that handles both selector (ainvoke) and generator (with_structured_output) calls."""
    if gen_dsl is None:
        gen_dsl = RecipeDSL.model_validate(SIMPLE_DSL)

    # Selector response (plain ainvoke)
    selector_response = MagicMock()
    selector_response.content = selector_text
    selector_response.response_metadata = {"usage": {"input_tokens": 5, "output_tokens": 8}}

    # Generator structured output mock — returns include_raw=True dict format
    structured_mock = MagicMock()
    structured_mock.ainvoke = AsyncMock(return_value=_make_raw_response(gen_dsl))

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=selector_response)
    mock_llm.with_structured_output = MagicMock(return_value=structured_mock)

    return mock_llm


# ---------------------------------------------------------------------------
# Test 1: successful run returns StructuredRunResult with metadata
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recipe_strategy_returns_result():
    """RecipeStrategy.run() returns a StructuredRunResult with recipe_metadata."""
    strategy = RecipeStrategy()
    fake_result = _make_fake_result()
    mock_llm = _make_mock_llm()

    with (
        patch("strategies.recipe.get_chat_model", return_value=mock_llm),
        patch("strategies.recipe._run_ir_pipeline", new=AsyncMock(return_value=fake_result)),
        patch("strategies.recipe.load_catalog", return_value=[]),
        patch("strategies.recipe.build_selection_prompt", return_value="select this"),
        patch("strategies.recipe.build_generation_prompt", return_value="generate this"),
        patch("strategies.recipe.lower_to_ir", return_value=MagicMock()),
    ):
        result = await strategy.run("draw two points", model="anthropic:claude-haiku-4-5-20251001")

    assert isinstance(result, StructuredRunResult)
    assert result.recipe_metadata is not None
    assert result.recipe_metadata.selected_recipes == []


# ---------------------------------------------------------------------------
# Test 2: retry on lowering error — second attempt succeeds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recipe_strategy_retries_on_lowering_error():
    """First lowering raises LoweringError; second attempt succeeds."""
    strategy = RecipeStrategy()
    fake_result = _make_fake_result()
    mock_llm = _make_mock_llm()

    lower_calls = {"count": 0}

    def side_effect_lower(*args, **kwargs):
        lower_calls["count"] += 1
        if lower_calls["count"] == 1:
            raise LoweringError("bad dsl")
        return MagicMock()

    with (
        patch("strategies.recipe.get_chat_model", return_value=mock_llm),
        patch("strategies.recipe.lower_to_ir", side_effect=side_effect_lower),
        patch("strategies.recipe._run_ir_pipeline", new=AsyncMock(return_value=fake_result)),
        patch("strategies.recipe.load_catalog", return_value=[]),
        patch("strategies.recipe.build_selection_prompt", return_value="select"),
        patch("strategies.recipe.build_generation_prompt", return_value="generate"),
    ):
        result = await strategy.run("draw something", model="anthropic:claude-haiku-4-5-20251001")

    assert isinstance(result, StructuredRunResult)
    assert lower_calls["count"] == 2


# ---------------------------------------------------------------------------
# Test 3: raises RuntimeError after MAX_RETRIES exhausted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recipe_strategy_raises_after_max_retries():
    """All attempts fail with LoweringError; RuntimeError raised after MAX_RETRIES."""
    from strategies.recipe import MAX_RETRIES

    strategy = RecipeStrategy()
    mock_llm = _make_mock_llm()

    with (
        patch("strategies.recipe.get_chat_model", return_value=mock_llm),
        patch("strategies.recipe.lower_to_ir", side_effect=LoweringError("always fails")),
        patch("strategies.recipe.load_catalog", return_value=[]),
        patch("strategies.recipe.build_selection_prompt", return_value="select"),
        patch("strategies.recipe.build_generation_prompt", return_value="generate"),
    ):
        with pytest.raises(RuntimeError, match="RecipeStrategy failed after"):
            await strategy.run("draw something", model="anthropic:claude-haiku-4-5-20251001")

    traces = strategy._partial_recipe_metadata.attempt_traces
    assert len(traces) == MAX_RETRIES
