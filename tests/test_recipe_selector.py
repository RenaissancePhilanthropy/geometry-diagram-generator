"""Recipe selector: robust parsing, one shared parser, env-driven model for the
standalone entrypoint, and the selector seeing the raw request."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from geometry_diagrams.recipe.dsl import RecipeDSL
from geometry_diagrams.strategies import recipe as recipe_mod
from geometry_diagrams.strategies.recipe import (
    RecipeStrategy,
    _parse_selection,
    select_recipes,
)
from tests.test_strategy_robustness import _fake_result, _structured_llm


@pytest.mark.parametrize("reply", [
    '{"selected_recipes": null}',
    '{"selected_recipes": "triangle"}',
    '{"selected_recipes": [1, null, "ok"], "unmatched_concepts": null}',
    '{"selected_recipes": {"a": 1}, "confidence": 7, "is_geometry_request": null}',
    "no json here",
    "{not json}",
    "[1, 2]",
])
def test_parse_selection_never_raises_on_malformed_fields(reply):
    sel = _parse_selection(reply)
    assert isinstance(sel.selected_recipes, list)
    assert all(isinstance(r, str) for r in sel.selected_recipes)
    assert isinstance(sel.unmatched_concepts, list)
    assert sel.confidence in ("high", "medium", "low")
    assert sel.is_geometry_request is True


def test_parse_selection_reads_well_formed_reply():
    sel = _parse_selection(
        'x {"selected_recipes": ["a"], "unmatched_concepts": ["b"], '
        '"confidence": "low", "is_geometry_request": false} y'
    )
    assert (sel.selected_recipes, sel.unmatched_concepts, sel.confidence, sel.is_geometry_request) == (
        ["a"], ["b"], "low", False,
    )


def test_parse_selection_accepts_legacy_selected_key():
    assert _parse_selection('{"selected": ["a"]}').selected_recipes == ["a"]


def _selector_llm(reply: str) -> MagicMock:
    response = MagicMock()
    response.content = reply
    response.usage_metadata = {"input_tokens": 3, "output_tokens": 2}
    response.response_metadata = {}
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=response)
    return llm


@pytest.mark.asyncio
async def test_standalone_select_recipes_survives_null_selected_recipes():
    llm = _selector_llm('{"selected_recipes": null, "is_geometry_request": true}')
    with (
        patch.object(recipe_mod, "get_chat_model", return_value=llm),
        patch.object(recipe_mod, "load_catalog", return_value=[]),
        patch.object(recipe_mod, "build_selection_prompt", return_value="p"),
    ):
        result = await select_recipes("a triangle")
    assert result.selected_recipes == []
    assert (result.input_tokens, result.output_tokens) == (3, 2)


@pytest.mark.asyncio
async def test_standalone_select_recipes_honours_env_selector_model(monkeypatch):
    monkeypatch.setenv("GEOMETRY_SELECTOR_MODEL", "anthropic:env-selector")
    llm = _selector_llm("{}")
    with (
        patch.object(recipe_mod, "get_chat_model", return_value=llm) as get_model,
        patch.object(recipe_mod, "load_catalog", return_value=[]),
        patch.object(recipe_mod, "build_selection_prompt", return_value="p"),
    ):
        await select_recipes("a triangle")
        assert get_model.call_args.args[0] == "anthropic:env-selector"
        await select_recipes("a triangle", model="anthropic:explicit")
        assert get_model.call_args.args[0] == "anthropic:explicit"


@pytest.mark.asyncio
async def test_selector_sees_raw_request_not_previous_dsl_augmented_prompt():
    gen_llm = _structured_llm([RecipeDSL(construction=[])])
    selector_prompts = []

    def fake_selection_prompt(request, catalog):
        selector_prompts.append(request)
        return "p"

    prior = RecipeDSL(construction=[]).model_dump()
    with (
        patch.object(recipe_mod, "get_chat_model", return_value=gen_llm),
        patch.object(recipe_mod, "load_catalog", return_value=[]),
        patch.object(recipe_mod, "build_selection_prompt", side_effect=fake_selection_prompt),
        patch.object(recipe_mod, "lower_to_ir", return_value=MagicMock()),
        patch.object(recipe_mod, "require_features"),
        patch.object(recipe_mod, "_run_ir_pipeline", new=AsyncMock(return_value=_fake_result())),
    ):
        await RecipeStrategy().run("make it bigger", model="anthropic:claude-sonnet-4-6", previous_dsl=prior)
    assert selector_prompts == ["make it bigger"]
    sent = gen_llm.with_structured_output.return_value.ainvoke.call_args.args[0][-1].content
    assert "Previous RecipeDSL" in str(sent)
