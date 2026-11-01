"""Token/cost accounting: pre-assert step, recipe selector and generation cost,
and retry_on_apply_failure only firing on apply failures."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.recipe.dsl import RecipeDSL
from geometry_diagrams.strategies import pre_assert_step as pas
from geometry_diagrams.strategies import python_full as pf
from geometry_diagrams.strategies import recipe as recipe_mod
from geometry_diagrams.strategies.llm import extract_cost
from geometry_diagrams.strategies.python_full import PydslScriptOutput, PythonFullStrategy
from geometry_diagrams.strategies.recipe import RecipeStrategy, select_recipes
from tests.test_strategy_robustness import VALID_SCRIPT, _fake_result, _raw, _structured_llm


def _ai(content: str, in_tok: int, out_tok: int, cost: float | None = None) -> AIMessage:
    meta = {"token_usage": {"cost": cost}} if cost is not None else {}
    return AIMessage(
        content=content, response_metadata=meta,
        usage_metadata={"input_tokens": in_tok, "output_tokens": out_tok, "total_tokens": in_tok + out_tok},
    )


def test_extract_cost_ignores_non_numeric_values():
    assert extract_cost(MagicMock()) is None
    assert extract_cost(_ai("x", 1, 1, 0.5)) == 0.5
    assert extract_cost(AIMessage(content="x")) is None


# --- pre-assert step usage ---------------------------------------------------


@pytest.mark.asyncio
async def test_propose_and_filter_checks_reports_usage_including_the_retry():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=[
        _ai("assert_equal(O, A)\n", 100, 10, 0.01),     # hallucinated name -> retry
        _ai("assert_distinct_points(O, A)\n", 120, 12, 0.02),
    ])
    with patch.object(pas, "get_chat_model", return_value=llm):
        result = await pas.propose_and_filter_checks(
            "a circle through A with center O", "anthropic:claude-sonnet-4-6",
        )
    assert result.retried is True
    assert (result.input_tokens, result.output_tokens) == (220, 22)
    assert result.cost_usd == pytest.approx(0.03)


@pytest.mark.asyncio
async def test_pre_assert_usage_is_added_to_the_python_full_run_total():
    fake = pas.PreAssertProposalResult(
        raw_response="", retried=False, filtered_checks=[], unparsed_lines=[], advisory_text="",
        input_tokens=7, output_tokens=3, cost_usd=0.5,
    )
    llm = _structured_llm([PydslScriptOutput(script=VALID_SCRIPT)])
    with (
        patch.object(pf, "propose_and_filter_checks", new=AsyncMock(return_value=fake)),
        patch.object(pf, "get_chat_model", return_value=llm),
    ):
        result = await PythonFullStrategy().run(
            "a triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer(),
            use_pre_assert_step=True,
        )
    assert result.input_tokens == 7 + 10   # pre-step + one generation call (_raw: 10 in)
    assert result.output_tokens == 3 + 5
    assert result.cost_usd == pytest.approx(0.5)


# --- recipe selector / generation cost --------------------------------------


@pytest.mark.asyncio
async def test_recipe_run_reports_selector_and_generation_cost():
    llm = _structured_llm([RecipeDSL(construction=[])])
    llm.ainvoke = AsyncMock(return_value=_ai('{"selected_recipes": []}', 4, 2, 0.01))
    structured = llm.with_structured_output.return_value
    structured.ainvoke = AsyncMock(return_value={
        "raw": _ai("", 10, 5, 0.02), "parsed": RecipeDSL(construction=[]), "parsing_error": None,
    })
    with (
        patch.object(recipe_mod, "get_chat_model", return_value=llm),
        patch.object(recipe_mod, "load_catalog", return_value=[]),
        patch.object(recipe_mod, "lower_to_ir", return_value=MagicMock()),
        patch.object(recipe_mod, "require_features"),
        patch.object(recipe_mod, "_run_ir_pipeline", new=AsyncMock(return_value=_fake_result())),
    ):
        result = await RecipeStrategy().run("draw", model="anthropic:claude-sonnet-4-6")
    assert result.cost_usd == pytest.approx(0.03)
    assert (result.input_tokens, result.output_tokens) == (14, 7)


@pytest.mark.asyncio
async def test_recipe_cost_is_none_when_nothing_reported():
    llm = _structured_llm([RecipeDSL(construction=[])])
    with (
        patch.object(recipe_mod, "get_chat_model", return_value=llm),
        patch.object(recipe_mod, "load_catalog", return_value=[]),
        patch.object(recipe_mod, "lower_to_ir", return_value=MagicMock()),
        patch.object(recipe_mod, "require_features"),
        patch.object(recipe_mod, "_run_ir_pipeline", new=AsyncMock(return_value=_fake_result())),
    ):
        result = await RecipeStrategy().run("draw", model="anthropic:claude-sonnet-4-6")
    assert result.cost_usd is None


@pytest.mark.asyncio
async def test_standalone_select_recipes_reports_cost():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=_ai("{}", 4, 2, 0.01))
    with (
        patch.object(recipe_mod, "get_chat_model", return_value=llm),
        patch.object(recipe_mod, "load_catalog", return_value=[]),
    ):
        result = await select_recipes("a triangle")
    assert result.cost_usd == pytest.approx(0.01)


# --- retry_on_apply_failure only on apply failures ---------------------------

_NOT_FOUND = "<<<<<<< SEARCH\nno such line\n=======\nx\n>>>>>>> REPLACE"
_GOOD = "<<<<<<< SEARCH\nc = point(0, 3)\n=======\nc = point(0, 5)\n>>>>>>> REPLACE"


async def _edit_with_replies(replies: list[str]) -> tuple[MagicMock, Exception | None]:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=[_ai(r, 1, 1) for r in replies])
    err = None
    with patch.object(pf, "get_chat_model", return_value=llm):
        try:
            await PythonFullStrategy().edit(
                "move c", VALID_SCRIPT, model="anthropic:claude-sonnet-4-6",
                renderer=SVGRenderer(), edit_generation_mode="search_replace",
                retry_on_apply_failure=True,
            )
        except Exception as exc:  # noqa: BLE001 - the test inspects it
            err = exc
    return llm, err


@pytest.mark.asyncio
async def test_retry_on_apply_failure_does_not_fire_on_unparseable_generation():
    llm, err = await _edit_with_replies(["I cannot do that, sorry."])
    assert isinstance(err, ValueError)
    assert llm.ainvoke.await_count == 1


@pytest.mark.asyncio
async def test_retry_on_apply_failure_still_fires_on_apply_failure():
    llm, err = await _edit_with_replies([_NOT_FOUND, _GOOD])
    assert err is None
    assert llm.ainvoke.await_count == 2
