"""The recipe prompt-cache content block is an Anthropic extension: only Anthropic
models may receive it."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from geometry_diagrams.recipe.dsl import RecipeDSL
from geometry_diagrams.strategies import recipe as recipe_mod
from geometry_diagrams.strategies.recipe import RecipeStrategy
from tests.test_strategy_robustness import _fake_result, _structured_llm

STATIC = "STATIC-DSL-DOCS"


async def _run_recipe_with_cache(model_id: str, monkeypatch) -> MagicMock:
    monkeypatch.setenv("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")
    monkeypatch.setenv("FIREWORKS_API_KEY", "test-key")
    llm = _structured_llm([RecipeDSL(construction=[])])
    with (
        patch.object(recipe_mod, "get_chat_model", return_value=llm),
        patch.object(recipe_mod, "build_generation_prompt_static_block", return_value=STATIC),
        patch.object(recipe_mod, "build_generation_prompt", return_value=f"{STATIC}\n\ndynamic part"),
        patch.object(recipe_mod, "load_catalog", return_value=[]),
        patch.object(recipe_mod, "lower_to_ir", return_value=MagicMock()),
        patch.object(recipe_mod, "require_features"),
        patch.object(recipe_mod, "_run_ir_pipeline", new=AsyncMock(return_value=_fake_result())),
    ):
        await RecipeStrategy(enable_cache=True).run("draw", model=model_id)
    return llm


def _sent_human_content(llm: MagicMock):
    return llm.with_structured_output.return_value.ainvoke.call_args.args[0][-1].content


@pytest.mark.asyncio
async def test_recipe_cache_block_used_for_anthropic(monkeypatch):
    content = _sent_human_content(await _run_recipe_with_cache("anthropic:claude-sonnet-4-6", monkeypatch))
    assert isinstance(content, list)
    assert content[0]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.asyncio
async def test_recipe_cache_block_not_used_for_non_anthropic(monkeypatch):
    content = _sent_human_content(await _run_recipe_with_cache("fireworks:llama-4-maverick", monkeypatch))
    assert isinstance(content, str)
    assert STATIC in content
