"""Structured strategy usage reporting: tokens (and provider cost) are summed over every
LLM attempt and exposed on the result, and survive a total failure for the eval harness.

These tests use real LangChain AIMessages carrying ``usage_metadata`` (what the chat
models actually populate); the older structured tests mock ``response_metadata``, which
the usage extraction never reads, so they could not see a missing total.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from evals.run import _populate_partial_metadata_on_failure
from geometry_diagrams.ir.ir import DiagramIR
from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
from geometry_diagrams.strategies.structured import StructureStrategy


def _raw(in_tok: int, out_tok: int, cost: "float | None" = None) -> AIMessage:
    meta = {"token_usage": {"cost": cost}} if cost is not None else {}
    return AIMessage(
        content="",
        usage_metadata={"input_tokens": in_tok, "output_tokens": out_tok,
                        "total_tokens": in_tok + out_tok},
        response_metadata=meta,
    )


def _ok(in_tok, out_tok, cost=None):
    return {"raw": _raw(in_tok, out_tok, cost),
            "parsed": DiagramIR(define=[], checks=[], render=[]), "parsing_error": None}


def _unparseable(in_tok, out_tok, cost=None):
    return {"raw": _raw(in_tok, out_tok, cost), "parsed": None, "parsing_error": "bad JSON"}


def _llm(responses):
    structured = MagicMock()
    structured.ainvoke = AsyncMock(side_effect=responses)
    llm = MagicMock()
    llm.with_structured_output = MagicMock(return_value=structured)
    llm.bind_tools = MagicMock(return_value=structured)
    return llm


def _fake_result() -> StructuredRunResult:
    return StructuredRunResult(
        diagram_ir=DiagramIR(define=[], checks=[], render=[]),
        tikz="", svg="<svg/>", sym_table={}, sym_full={},
    )


async def _run(responses, pipeline=None):
    async def ok_pipeline(diagram_ir, renderer=None):
        return _fake_result()

    strategy = StructureStrategy()
    with (
        patch("geometry_diagrams.strategies.structured.get_chat_model", return_value=_llm(responses)),
        patch("geometry_diagrams.strategies.structured._run_ir_pipeline", new=pipeline or ok_pipeline),
    ):
        try:
            result = await strategy.run("draw a circle", model="anthropic:claude-sonnet-4-6")
        except RuntimeError as exc:
            return strategy, exc
    return strategy, result


@pytest.mark.asyncio
async def test_result_carries_tokens_summed_over_every_attempt():
    strategy, result = await _run([_unparseable(5, 2), _ok(10, 20)])
    assert isinstance(result, StructuredRunResult)
    assert (result.input_tokens, result.output_tokens) == (15, 22)
    assert result.retries == 1


@pytest.mark.asyncio
async def test_single_attempt_reports_its_own_tokens():
    strategy, result = await _run([_ok(1234, 56)])
    assert (result.input_tokens, result.output_tokens) == (1234, 56)


@pytest.mark.asyncio
async def test_tokens_survive_a_total_failure_on_the_strategy():
    strategy, exc = await _run([_unparseable(5, 2), _unparseable(6, 3), _unparseable(7, 4)])
    assert isinstance(exc, RuntimeError)
    assert strategy._partial_input_tokens == 18
    assert strategy._partial_output_tokens == 9


@pytest.mark.asyncio
async def test_eval_harness_records_partial_tokens_for_a_failed_structured_run():
    strategy, exc = await _run([_unparseable(5, 2), _unparseable(6, 3), _unparseable(7, 4)])
    record: dict = {"retries": 0}
    _populate_partial_metadata_on_failure(record, strategy)
    assert record["input_tokens"] == 18
    assert record["output_tokens"] == 9
    assert record["cost_usd"] is None


@pytest.mark.asyncio
async def test_provider_cost_is_summed_when_reported():
    strategy, result = await _run([_unparseable(5, 2, cost=0.001), _ok(10, 20, cost=0.002)])
    assert result.cost_usd == pytest.approx(0.003)


@pytest.mark.asyncio
async def test_cost_stays_none_when_the_provider_reports_none():
    """None, not 0.0: an unreported cost must not read as 'confirmed free'."""
    strategy, result = await _run([_ok(10, 20)])
    assert result.cost_usd is None


@pytest.mark.asyncio
async def test_state_for_a_retry_after_pipeline_failure_keeps_counting():
    calls = {"n": 0}

    async def flaky_pipeline(diagram_ir, renderer=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Geometric checks failed")
        return _fake_result()

    strategy, result = await _run([_ok(10, 20), _ok(11, 21)], pipeline=flaky_pipeline)
    assert (result.input_tokens, result.output_tokens) == (21, 41)
    assert result.retries == 1
