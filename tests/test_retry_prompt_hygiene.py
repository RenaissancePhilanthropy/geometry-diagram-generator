"""Retry prompts: no stale warnings after a 'nothing drawn' failure, and an
accurate lead-in for the previous error text."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.recipe.dsl import RecipeDSL
from geometry_diagrams.strategies import recipe as recipe_mod
from geometry_diagrams.strategies.ir_pipeline import PipelineError
from geometry_diagrams.strategies.python_full import PydslScriptOutput, PythonFullStrategy
from geometry_diagrams.strategies.recipe import RecipeStrategy
from tests.test_strategy_robustness import VALID_SCRIPT, _fake_result, _structured_llm

NO_DRAW = "a = point(0, 0)\nb = point(4, 0)\nc = point(0, 3)\nt = triangle(a, b, c)\n"


def _sent_texts(llm: MagicMock) -> list[str]:
    return [
        str(call.args[0][-1].content)
        for call in llm.with_structured_output.return_value.ainvoke.call_args_list
    ]


@pytest.mark.asyncio
async def test_python_full_nothing_drawn_does_not_resend_stale_warnings():
    llm = _structured_llm([
        PydslScriptOutput(script=VALID_SCRIPT),
        PydslScriptOutput(script=NO_DRAW),
        PydslScriptOutput(script=VALID_SCRIPT),
    ])
    calls = {"n": 0}

    async def pipeline(diagram_ir, renderer=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PipelineError("checks failed", ["STALE-WARNING"])
        return _fake_result()

    with (
        patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=llm),
        patch("geometry_diagrams.strategies.python_full.run_ir_pipeline", new=pipeline),
    ):
        await PythonFullStrategy().run(
            "draw", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer(),
        )
    texts = _sent_texts(llm)
    assert "STALE-WARNING" in texts[1]       # fed back once, after the pipeline failure
    assert "nothing was drawn" not in texts[1]
    assert "nothing was" in texts[2] and "STALE-WARNING" not in texts[2]


@pytest.mark.asyncio
async def test_recipe_retry_prompt_does_not_claim_error_text_is_a_stage():
    llm = _structured_llm([RecipeDSL(construction=[]), RecipeDSL(construction=[])])
    calls = {"n": 0}

    async def pipeline(diagram_ir, renderer=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Geometric checks failed: x")
        return _fake_result()

    with (
        patch.object(recipe_mod, "get_chat_model", return_value=llm),
        patch.object(recipe_mod, "load_catalog", return_value=[]),
        patch.object(recipe_mod, "lower_to_ir", return_value=MagicMock()),
        patch.object(recipe_mod, "require_features"),
        patch.object(recipe_mod, "_run_ir_pipeline", new=pipeline),
    ):
        await RecipeStrategy().run("draw", model="anthropic:claude-sonnet-4-6")
    second = _sent_texts(llm)[1]
    assert "Previous attempt failed: Geometric checks failed: x" in second
    assert "failed at stage" not in second
