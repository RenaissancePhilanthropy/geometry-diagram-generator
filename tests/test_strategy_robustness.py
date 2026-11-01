"""Robustness fixes in the strategies: non-IR pipeline errors retry, cache blocks
only for Anthropic, stale warnings, token accounting, config validation.

LLM calls are mocked; no network or Docker.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from geometry_diagrams.ir.ir import DiagramIR
from geometry_diagrams.recipe.dsl import RecipeDSL
from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
from geometry_diagrams.strategies.python_full import PydslScriptOutput, PythonFullStrategy
from geometry_diagrams.strategies.recipe import RecipeStrategy
from geometry_diagrams.strategies.structured import StructureStrategy
from geometry_diagrams.ir.renderer import SVGRenderer


def _fake_result() -> StructuredRunResult:
    return StructuredRunResult(
        diagram_ir=DiagramIR(define=[], checks=[], render=[]),
        tikz="", svg="<svg/>", sym_table={}, sym_full={},
    )


def _raw(in_tok: int = 10, out_tok: int = 5) -> MagicMock:
    raw = MagicMock()
    raw.usage_metadata = {"input_tokens": in_tok, "output_tokens": out_tok}
    raw.response_metadata = {}
    raw.content = ""
    return raw


def _structured_llm(parsed_values: list) -> MagicMock:
    structured = MagicMock()
    structured.ainvoke = AsyncMock(side_effect=[
        {"raw": _raw(), "parsed": p, "parsing_error": None} for p in parsed_values
    ])
    llm = MagicMock()
    llm.with_structured_output = MagicMock(return_value=structured)
    selector = MagicMock()
    selector.content = '{"selected_recipes": [], "unmatched_concepts": []}'
    selector.usage_metadata = {"input_tokens": 1, "output_tokens": 1}
    selector.response_metadata = {}
    llm.ainvoke = AsyncMock(return_value=selector)
    return llm


VALID_SCRIPT = (
    "a = point(0, 0)\nb = point(4, 0)\nc = point(0, 3)\nt = triangle(a, b, c)\ndraw(t)\n"
)


def _flaky_pipeline(exc: Exception):
    calls = {"n": 0}

    async def pipeline(diagram_ir, renderer=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise exc
        return _fake_result()

    return pipeline, calls


# --- A1: non-IR errors in pipeline nodes are retried -------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [ValueError("bad value"), TypeError("bad type")])
async def test_recipe_pipeline_node_retries_non_ir_errors(exc):
    llm = _structured_llm([RecipeDSL(construction=[]), RecipeDSL(construction=[])])
    pipeline, calls = _flaky_pipeline(exc)
    with (
        patch("geometry_diagrams.strategies.recipe.get_chat_model", return_value=llm),
        patch("geometry_diagrams.strategies.recipe.lower_to_ir", return_value=MagicMock()),
        patch("geometry_diagrams.strategies.recipe.require_features"),
        patch("geometry_diagrams.strategies.recipe._run_ir_pipeline", new=pipeline),
    ):
        result = await RecipeStrategy().run("draw", model="anthropic:claude-sonnet-4-6")
    assert result.svg == "<svg/>"
    assert calls["n"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [ValueError("bad value"), TypeError("bad type")])
async def test_structured_pipeline_node_retries_non_ir_errors(exc):
    ir = DiagramIR(define=[], checks=[], render=[])
    llm = _structured_llm([ir, ir])
    pipeline, calls = _flaky_pipeline(exc)
    with (
        patch("geometry_diagrams.strategies.structured.get_chat_model", return_value=llm),
        patch("geometry_diagrams.strategies.structured._run_ir_pipeline", new=pipeline),
    ):
        result = await StructureStrategy().run("draw", model="anthropic:claude-sonnet-4-6")
    assert result.svg == "<svg/>"
    assert calls["n"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [ValueError("bad value"), TypeError("bad type")])
async def test_python_full_pipeline_node_retries_non_ir_errors(exc):
    llm = _structured_llm([PydslScriptOutput(script=VALID_SCRIPT)] * 2)
    pipeline, calls = _flaky_pipeline(exc)
    with (
        patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=llm),
        patch("geometry_diagrams.strategies.python_full.run_ir_pipeline", new=pipeline),
    ):
        result = await PythonFullStrategy().run(
            "draw", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer(),
        )
    assert result.svg == "<svg/>"
    assert calls["n"] == 2
