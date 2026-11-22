"""max_attempts: the number of generation attempts per run, replacing each strategy's
MAX_RETRIES of 3 (config field, GEOMETRY_MAX_ATTEMPTS, per-call kwarg)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from geometry_diagrams import GeometryConfig, render_geometry_diagram
from geometry_diagrams.config import resolve_config, validate_max_attempts
from geometry_diagrams.errors import GenerationFailedError
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.recipe.lower import LoweringError
from geometry_diagrams.strategies.python_full import PythonFullStrategy
from geometry_diagrams.strategies.recipe import RecipeStrategy
from tests.test_python_full_strategy import _make_raw_ainvoke_mock_llm
from tests.test_recipe_strategy import _make_mock_llm


@pytest.mark.parametrize("bad", [0, -1, 1.5, "3", True])
def test_rejects_bad_values(bad):
    with pytest.raises(ValueError, match="max_attempts"):
        validate_max_attempts(bad)


def test_none_and_positive_ints_pass():
    assert validate_max_attempts(None) is None and validate_max_attempts(5) == 5


def test_config_env_and_resolve(monkeypatch):
    assert GeometryConfig.from_env().max_attempts is None
    monkeypatch.setenv("GEOMETRY_MAX_ATTEMPTS", "2")
    assert GeometryConfig.from_env().max_attempts == 2
    assert resolve_config(GeometryConfig(max_attempts=2)).max_attempts == 2
    assert resolve_config(GeometryConfig(max_attempts=2), max_attempts=4).max_attempts == 4
    monkeypatch.setenv("GEOMETRY_MAX_ATTEMPTS", "0")
    with pytest.raises(ValueError):
        GeometryConfig.from_env()


@pytest.mark.asyncio
@pytest.mark.parametrize("attempts", [1, 2, 5])
async def test_python_full_stops_at_the_limit(attempts):
    llm = _make_raw_ainvoke_mock_llm(None)
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=llm):
        with pytest.raises(GenerationFailedError) as info:
            await PythonFullStrategy().run(
                "a right triangle", model="vercel:meta/muse-spark-1.2-contributor",
                renderer=SVGRenderer(), max_attempts=attempts,
            )
    assert info.value.attempts == attempts and llm.ainvoke.call_count == attempts


@pytest.mark.asyncio
@pytest.mark.parametrize("attempts", [1, 2, 4])
async def test_recipe_stops_at_the_limit(attempts):
    llm = _make_mock_llm()
    with (
        patch("geometry_diagrams.strategies.recipe.get_chat_model", return_value=llm),
        patch("geometry_diagrams.strategies.recipe.lower_to_ir", side_effect=LoweringError("always fails")),
        patch("geometry_diagrams.strategies.recipe.load_catalog", return_value=[]),
        patch("geometry_diagrams.strategies.recipe.build_selection_prompt", return_value="select"),
        patch("geometry_diagrams.strategies.recipe.build_generation_prompt", return_value="generate"),
    ):
        strategy = RecipeStrategy()
        with pytest.raises(GenerationFailedError) as info:
            await strategy.run("draw something", model="anthropic:claude-haiku-4-5-20251001", max_attempts=attempts)
    assert info.value.attempts == attempts
    assert len(strategy._partial_recipe_metadata.attempt_traces) == attempts


@pytest.mark.asyncio
async def test_default_is_still_three():
    llm = _make_raw_ainvoke_mock_llm(None)
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=llm):
        with pytest.raises(GenerationFailedError) as info:
            await PythonFullStrategy().run(
                "a right triangle", model="vercel:meta/muse-spark-1.2-contributor", renderer=SVGRenderer(),
            )
    assert info.value.attempts == 3


@pytest.mark.asyncio
async def test_facade_passes_the_config_value_to_every_strategy():
    for strategy_name, cls in (("python_full", PythonFullStrategy), ("recipe", RecipeStrategy)):
        run = AsyncMock(side_effect=RuntimeError("stop"))
        with patch.object(cls, "run", run):
            with pytest.raises(RuntimeError, match="stop"):
                await render_geometry_diagram(
                    "a triangle", config=GeometryConfig(strategy=strategy_name, renderer="svg", max_attempts=2),
                )
        assert run.call_args.kwargs["max_attempts"] == 2
    run = AsyncMock(side_effect=RuntimeError("stop"))
    with patch.object(RecipeStrategy, "run", run):
        with pytest.raises(RuntimeError):
            await render_geometry_diagram("a triangle", config=GeometryConfig(strategy="recipe", renderer="svg"))
    assert "max_attempts" not in run.call_args.kwargs
