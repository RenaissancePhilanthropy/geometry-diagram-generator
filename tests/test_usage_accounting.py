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


def _gemini(model: str, in_tok: int, out_tok: int, **meta) -> AIMessage:
    return AIMessage(
        content="x",
        response_metadata={"model_name": model, "model_provider": "google_genai", **meta},
        usage_metadata={"input_tokens": in_tok, "output_tokens": out_tok, "total_tokens": in_tok + out_tok},
    )


def test_extract_cost_prices_google_usage_from_genai_prices():
    pytest.importorskip("genai_prices")
    # gemini-4-hydrogen is $1.50/M input, $7.50/M output (genai-prices data).
    cost = extract_cost(_gemini("gemini-4-hydrogen", 1_000_000, 100_000))
    assert cost == pytest.approx(1.5 + 0.75)


def test_extract_cost_prefers_provider_reported_cost_over_estimate():
    msg = _gemini("gemini-4-hydrogen", 1000, 1000, token_usage={"cost": 0.25})
    assert extract_cost(msg) == 0.25


def test_extract_cost_is_none_for_unknown_google_model_or_missing_usage():
    pytest.importorskip("genai_prices")
    assert extract_cost(_gemini("gemini-99-nonexistent", 10, 10)) is None
    no_usage = AIMessage(content="x", response_metadata={"model_name": "gemini-4-hydrogen", "model_provider": "google_genai"})
    assert extract_cost(no_usage) is None


def _claude(model: str, in_tok: int, out_tok: int, **details) -> AIMessage:
    return AIMessage(
        content="x",
        response_metadata={"model_name": model, "model_provider": "anthropic"},
        usage_metadata={
            "input_tokens": in_tok, "output_tokens": out_tok, "total_tokens": in_tok + out_tok,
            "input_token_details": details,
        },
    )


def test_extract_cost_prices_anthropic_usage_including_cache_tokens():
    pytest.importorskip("genai_prices")
    plain = extract_cost(_claude("claude-sonnet-5-5", 10_000, 1_000))
    cached = extract_cost(_claude("claude-sonnet-5-5", 10_000, 1_000, cache_read=8_000, cache_creation=1_000))
    assert plain == pytest.approx(0.03)
    # input_tokens already includes the cache tokens; cache reads are cheaper than fresh input.
    assert cached is not None and cached < plain


def test_extract_cost_sums_anthropic_ttl_specific_cache_writes():
    pytest.importorskip("genai_prices")
    split = extract_cost(_claude(
        "claude-sonnet-5-5", 10_000, 1_000,
        cache_creation=0, ephemeral_5m_input_tokens=600, ephemeral_1h_input_tokens=400,
    ))
    generic = extract_cost(_claude("claude-sonnet-5-5", 10_000, 1_000, cache_creation=1_000))
    assert split == pytest.approx(generic)


def test_extract_cost_does_not_estimate_for_openai_compatible_endpoints():
    # ChatOpenAI reports model_provider "openai" for every OpenAI-compatible endpoint
    # (Baseten, Tinker, Mantle, ...), so a bare name like gpt-oss-120b would be priced
    # at OpenAI's rates even when another host served it.
    msg = AIMessage(
        content="x",
        response_metadata={"model_name": "gpt-oss-120b", "model_provider": "openai"},
        usage_metadata={"input_tokens": 1000, "output_tokens": 1000, "total_tokens": 2000},
    )
    assert extract_cost(msg) is None


def test_extract_cost_is_none_when_genai_prices_is_not_installed(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.split(".")[0] == "genai_prices":
            raise ImportError(name)
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert extract_cost(_gemini("gemini-4-hydrogen", 1000, 1000)) is None


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


# --- real-OpenAI estimate (flagged by DirectChatOpenAI) -----------------------


def _openai(model: str, in_tok: int, out_tok: int, details=None, **meta) -> AIMessage:
    return AIMessage(
        content="x",
        response_metadata={"model_name": model, "model_provider": "openai", **meta},
        usage_metadata={
            "input_tokens": in_tok, "output_tokens": out_tok, "total_tokens": in_tok + out_tok,
            "input_token_details": details or {},
        },
    )


def test_extract_cost_prices_flagged_openai_with_snapshot_name_and_cache_reads():
    pytest.importorskip("genai_prices")
    plain = extract_cost(_openai("gpt-5-2025-08-07", 10_000, 1_000, openai_direct=True))
    cached = extract_cost(_openai("gpt-5-2025-08-07", 10_000, 1_000, {"cache_read": 8_000}, openai_direct=True))
    assert plain == pytest.approx(0.0225)
    assert cached == pytest.approx(0.0035 + 0.01)  # 8k cached at 0.125/M, 2k at 1.25/M, 1k out at 10/M


def test_extract_cost_applies_openai_service_tier_to_price_and_cache_reads():
    pytest.importorskip("genai_prices")
    default = extract_cost(_openai("gpt-5-2025-08-07", 10_000, 1_000, {"cache_read": 8_000}, openai_direct=True))
    flex = extract_cost(_openai(
        "gpt-5-2025-08-07", 10_000, 1_000, {"flex_cache_read": 8_000},
        openai_direct=True, service_tier="flex",
    ))
    priority = extract_cost(_openai(
        "gpt-5-2025-08-07", 10_000, 1_000, {"priority_cache_read": 8_000},
        openai_direct=True, service_tier="priority",
    ))
    assert flex == pytest.approx(default / 2)
    assert priority == pytest.approx(default * 2)


def test_extract_cost_is_none_for_flagged_openai_model_genai_prices_cannot_price():
    pytest.importorskip("genai_prices")
    assert extract_cost(_openai("ft:gpt-4o:acme::abc", 10, 10, openai_direct=True)) is None
    # cache_read > input_tokens is inconsistent usage; genai-prices raises ValueError
    assert extract_cost(_openai("gpt-5-2025-08-07", 10, 10, {"cache_read": 99}, openai_direct=True)) is None


def test_extract_cost_ignores_a_non_true_openai_direct_flag():
    assert extract_cost(_openai("gpt-5-2025-08-07", 10, 10, openai_direct="yes")) is None
