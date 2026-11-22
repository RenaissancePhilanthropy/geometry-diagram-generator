"""GenerationFailedError: the typed failure a strategy raises when it runs out of attempts."""
from unittest.mock import patch

import pytest

import geometry_diagrams
from geometry_diagrams.errors import GenerationFailedError
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.recipe.lower import LoweringError
from geometry_diagrams.strategies.python_full import MAX_RETRIES, PythonFullStrategy
from geometry_diagrams.strategies.recipe import RecipeStrategy
from tests.test_python_full_strategy import _make_raw_ainvoke_mock_llm
from tests.test_recipe_strategy import _make_mock_llm


def test_message_and_fields():
    err = GenerationFailedError("RecipeStrategy", 3, "boom", input_tokens=10, output_tokens=5, cost_usd=0.02)
    assert isinstance(err, RuntimeError)
    assert str(err) == "RecipeStrategy failed after 3 attempts. Last error: boom"
    assert (err.strategy, err.attempts, err.last_error) == ("RecipeStrategy", 3, "boom")
    assert (err.input_tokens, err.output_tokens, err.cost_usd) == (10, 5, 0.02)


def test_cost_defaults_to_unknown_not_free():
    assert GenerationFailedError("S", 1, "x").cost_usd is None


def test_exported_from_package():
    assert geometry_diagrams.GenerationFailedError is GenerationFailedError


@pytest.mark.asyncio
async def test_python_full_failure_carries_attempts_and_usage():
    mock_llm = _make_raw_ainvoke_mock_llm(None)
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        with pytest.raises(GenerationFailedError) as info:
            await PythonFullStrategy().run(
                "a right triangle", model="vercel:meta/muse-spark-1.2-contributor", renderer=SVGRenderer()
            )
    assert info.value.strategy == "PythonFullStrategy"
    assert info.value.attempts == MAX_RETRIES
    assert info.value.last_error


@pytest.mark.asyncio
async def test_recipe_failure_carries_attempts():
    from geometry_diagrams.strategies.recipe import MAX_RETRIES as RECIPE_RETRIES

    with (
        patch("geometry_diagrams.strategies.recipe.get_chat_model", return_value=_make_mock_llm()),
        patch("geometry_diagrams.strategies.recipe.lower_to_ir", side_effect=LoweringError("always fails")),
        patch("geometry_diagrams.strategies.recipe.load_catalog", return_value=[]),
        patch("geometry_diagrams.strategies.recipe.build_selection_prompt", return_value="select"),
        patch("geometry_diagrams.strategies.recipe.build_generation_prompt", return_value="generate"),
    ):
        with pytest.raises(GenerationFailedError) as info:
            await RecipeStrategy().run("draw something", model="anthropic:claude-haiku-4-5-20251001")
    assert info.value.attempts == RECIPE_RETRIES
    assert "always fails" in info.value.last_error
