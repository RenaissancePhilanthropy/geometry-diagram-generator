# tests/test_confidence.py
"""Tests for self-reported, metadata-first confidence (strategies/confidence.py)
and its wiring into RecipeStrategy (confidence_mode: none/structured/prelude/both).

Schema + parser tests are pure (no mocking). The mode tests mock
`strategies.recipe.Agent` and `_run_ir_pipeline` so no network/Docker/renderer
is required, mirroring tests/test_recipe_strategy.py.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import ValidationError

from recipe.dsl import RecipeDSL
from strategies.confidence import (
    DimensionScore,
    EvaluationMetadata,
    RecipeGenerationOutput,
    FENCE_START,
    FENCE_END,
    GEN_OUTPUT_INSTRUCTION_LINE,
    geo_correctness_score,
    parse_metadata_fence,
    strip_generation_output_instruction,
)
from strategies.instructions import RECIPE_GENERATION_SYSTEM
from strategies.recipe import RecipeStrategy
from strategies.structured import StructuredRunResult
from ir.ir import DiagramIR


# ---------------------------------------------------------------------------
# Fixtures / helpers
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


def _meta_dict(
    geo: int = 80,
    amb: int = 70,
    e2e: int = 75,
    contradictions: bool = False,
) -> dict:
    return {
        "geometric_correctness": {"confidence_score": geo, "flags": []},
        "request_ambiguity": {"confidence_score": amb, "flags": []},
        "end_to_end": {"confidence_score": e2e, "flags": []},
        "contradictions_found": contradictions,
        "contradiction_detail": [],
    }


def _fence(meta: dict) -> str:
    return f"{FENCE_START}\n{json.dumps(meta)}\n{FENCE_END}"


def _make_fake_ir_result() -> StructuredRunResult:
    fake_ir = DiagramIR(define=[], checks=[], render=[])
    return StructuredRunResult(diagram_ir=fake_ir, tikz="\\tkzInit", svg="<svg/>")


def _usage(inp: int = 10, out: int = 20):
    u = MagicMock()
    u.input_tokens = inp
    u.output_tokens = out
    m = MagicMock()
    m.usage.return_value = u
    return m


def _gen_response_structured(geo: int = 80) -> MagicMock:
    """Generation response whose .output is a RecipeGenerationOutput."""
    m = _usage()
    m.output = RecipeGenerationOutput.model_validate(
        {"evaluation_metadata": _meta_dict(geo=geo), "recipe": SIMPLE_DSL}
    )
    return m


def _gen_response_plain() -> MagicMock:
    """Generation response whose .output is a plain RecipeDSL (none/prelude)."""
    m = _usage()
    m.output = RecipeDSL.model_validate(SIMPLE_DSL)
    return m


def _prelude_response(meta: dict | None) -> MagicMock:
    """Prelude response: .output is the fenced text (or garbage if meta is None)."""
    m = _usage(inp=3, out=7)
    if meta is None:
        m.output = "this is not a fence or json at all"
    else:
        m.output = _fence(meta)
    return m


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def test_dimension_score_bounds():
    DimensionScore(confidence_score=0)
    DimensionScore(confidence_score=100)
    with pytest.raises(ValidationError):
        DimensionScore(confidence_score=-1)
    with pytest.raises(ValidationError):
        DimensionScore(confidence_score=101)


def test_dimension_score_extra_keys_ignored():
    # Free-text prelude JSON may include stray fields; they must be dropped,
    # not fatal (extra="ignore").
    d = DimensionScore.model_validate({"confidence_score": 50, "flags": [], "junk": 1})
    assert d.confidence_score == 50
    assert not hasattr(d, "junk")


def test_evaluation_metadata_required_dims_and_contradictions():
    EvaluationMetadata.model_validate(_meta_dict())
    # Missing a dimension -> rejected
    bad = _meta_dict()
    del bad["request_ambiguity"]
    with pytest.raises(ValidationError):
        EvaluationMetadata.model_validate(bad)
    # Missing contradictions_found -> rejected
    bad2 = _meta_dict()
    del bad2["contradictions_found"]
    with pytest.raises(ValidationError):
        EvaluationMetadata.model_validate(bad2)
    # Extra top-level key -> dropped (ignore), not fatal
    extra = _meta_dict()
    extra["surprise"] = 1
    ev = EvaluationMetadata.model_validate(extra)
    assert not hasattr(ev, "surprise")


def test_recipe_generation_output_field_order():
    # evaluation_metadata MUST be the first field so the model emits it before
    # the construction (the soft anti-anchoring guarantee).
    fields = list(RecipeGenerationOutput.model_fields.keys())
    assert fields[0] == "evaluation_metadata"
    assert fields[1] == "recipe"


def test_recipe_generation_output_round_trip():
    obj = RecipeGenerationOutput.model_validate(
        {"evaluation_metadata": _meta_dict(geo=42), "recipe": SIMPLE_DSL}
    )
    assert isinstance(obj.recipe, RecipeDSL)
    assert obj.evaluation_metadata.geometric_correctness.confidence_score == 42


# ---------------------------------------------------------------------------
# Fence parser
# ---------------------------------------------------------------------------

def test_parse_well_formed_fence():
    ev = parse_metadata_fence(_fence(_meta_dict(geo=33)))
    assert ev is not None
    assert ev.geometric_correctness.confidence_score == 33


def test_parse_fence_with_surrounding_prose():
    text = (
        "Sure, here is my assessment.\n"
        + _fence(_meta_dict(geo=60))
        + "\nHope that helps."
    )
    ev = parse_metadata_fence(text)
    assert ev is not None
    assert ev.geometric_correctness.confidence_score == 60


def test_parse_fence_with_markdown_code_fence_inside():
    text = f"{FENCE_START}\n```json\n{json.dumps(_meta_dict(geo=12))}\n```\n{FENCE_END}"
    ev = parse_metadata_fence(text)
    assert ev is not None
    assert ev.geometric_correctness.confidence_score == 12


def test_parse_no_fence_whole_text_json():
    ev = parse_metadata_fence(json.dumps(_meta_dict(geo=88)))
    assert ev is not None
    assert ev.geometric_correctness.confidence_score == 88


def test_parse_malformed_returns_none():
    assert parse_metadata_fence(f"{FENCE_START}\nnot json at all\n{FENCE_END}") is None
    assert parse_metadata_fence("{ broken json") is None


def test_parse_none_and_empty_returns_none():
    assert parse_metadata_fence(None) is None
    assert parse_metadata_fence("") is None
    assert parse_metadata_fence("   ") is None


def test_parse_tolerates_missing_optional_lists():
    # flags/contradiction_detail are optional; model may omit them.
    body = {
        "geometric_correctness": {"confidence_score": 50},
        "request_ambiguity": {"confidence_score": 50},
        "end_to_end": {"confidence_score": 50},
        "contradictions_found": False,
    }
    ev = parse_metadata_fence(json.dumps(body))
    assert ev is not None
    assert ev.geometric_correctness.flags == []


# ---------------------------------------------------------------------------
# geo_correctness_score helper
# ---------------------------------------------------------------------------

def test_geo_correctness_score():
    assert geo_correctness_score(_meta_dict(geo=77)) == 77
    assert geo_correctness_score(None) is None
    assert geo_correctness_score({}) is None
    assert geo_correctness_score({"geometric_correctness": {}}) is None


# ---------------------------------------------------------------------------
# RecipeStrategy confidence_mode
# ---------------------------------------------------------------------------

def test_default_confidence_mode_is_none():
    # `none` preserves the pre-confidence pipeline for existing callers
    # (web app, dry_run) that don't pass confidence_mode.
    assert RecipeStrategy().confidence_mode == "none"


def test_invalid_confidence_mode_raises():
    with pytest.raises(ValueError):
        RecipeStrategy(confidence_mode="bogus")


# ---------------------------------------------------------------------------
# Mode integration (mocked Agent + IR pipeline)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_none_mode_no_metadata():
    """confidence_mode=none: no prelude call, plain RecipeDSL output, no metadata."""
    strategy = RecipeStrategy(use_recipes=False, confidence_mode="none")
    fake = _make_fake_ir_result()
    gen = _gen_response_plain()

    with (
        patch("strategies.recipe.Agent") as MockAgent,
        patch("strategies.recipe._run_ir_pipeline", new=AsyncMock(return_value=fake)),
    ):
        inst = MagicMock()
        inst.run = AsyncMock(return_value=gen)
        MockAgent.return_value = inst
        result = await strategy.run("draw two points", model="test-model")

    assert result.recipe_metadata.evaluation_metadata_hard is None
    assert result.recipe_metadata.evaluation_metadata_soft is None
    # Only the generation Agent is constructed (no prelude).
    assert MockAgent.call_count == 1


@pytest.mark.asyncio
async def test_structured_mode_records_soft_only():
    """confidence_mode=structured: no prelude; soft score from the wrapper's first field."""
    strategy = RecipeStrategy(use_recipes=False, confidence_mode="structured")
    fake = _make_fake_ir_result()
    gen = _gen_response_structured(geo=64)

    with (
        patch("strategies.recipe.Agent") as MockAgent,
        patch("strategies.recipe._run_ir_pipeline", new=AsyncMock(return_value=fake)),
    ):
        inst = MagicMock()
        inst.run = AsyncMock(return_value=gen)
        MockAgent.return_value = inst
        result = await strategy.run("draw two points", model="test-model")

    assert result.recipe_metadata.evaluation_metadata_hard is None
    soft = result.recipe_metadata.evaluation_metadata_soft
    assert soft is not None
    assert geo_correctness_score(soft) == 64
    assert MockAgent.call_count == 1  # no prelude


@pytest.mark.asyncio
async def test_prelude_mode_records_hard_only():
    """confidence_mode=prelude: prelude fence gives hard score; gen uses plain RecipeDSL."""
    strategy = RecipeStrategy(use_recipes=False, confidence_mode="prelude")
    fake = _make_fake_ir_result()
    prelude = _prelude_response(_meta_dict(geo=55))
    gen = _gen_response_plain()

    with (
        patch("strategies.recipe.Agent") as MockAgent,
        patch("strategies.recipe._run_ir_pipeline", new=AsyncMock(return_value=fake)),
    ):
        inst = MagicMock()
        # prelude call first, then generation call
        inst.run = AsyncMock(side_effect=[prelude, gen])
        MockAgent.return_value = inst
        result = await strategy.run("draw two points", model="test-model")

    hard = result.recipe_metadata.evaluation_metadata_hard
    assert hard is not None
    assert geo_correctness_score(hard) == 55
    assert result.recipe_metadata.evaluation_metadata_soft is None
    assert MockAgent.call_count == 2  # prelude + generation


@pytest.mark.asyncio
async def test_both_mode_records_hard_and_soft_independently():
    """confidence_mode=both: independent prelude (hard) + structured (soft)."""
    strategy = RecipeStrategy(use_recipes=False, confidence_mode="both")
    fake = _make_fake_ir_result()
    # Distinct scores to prove the two reports are independent (not anchored).
    prelude = _prelude_response(_meta_dict(geo=40))
    gen = _gen_response_structured(geo=90)

    with (
        patch("strategies.recipe.Agent") as MockAgent,
        patch("strategies.recipe._run_ir_pipeline", new=AsyncMock(return_value=fake)),
    ):
        inst = MagicMock()
        inst.run = AsyncMock(side_effect=[prelude, gen])
        MockAgent.return_value = inst
        result = await strategy.run("draw two points", model="test-model")

    assert geo_correctness_score(result.recipe_metadata.evaluation_metadata_hard) == 40
    assert geo_correctness_score(result.recipe_metadata.evaluation_metadata_soft) == 90
    assert MockAgent.call_count == 2  # prelude + generation


@pytest.mark.asyncio
async def test_both_mode_prelude_parse_failure_keeps_soft():
    """If the prelude fence is unparseable, hard=None but the soft score survives."""
    strategy = RecipeStrategy(use_recipes=False, confidence_mode="both")
    fake = _make_fake_ir_result()
    prelude = _prelude_response(None)  # garbage text -> parse fails
    gen = _gen_response_structured(geo=72)

    with (
        patch("strategies.recipe.Agent") as MockAgent,
        patch("strategies.recipe._run_ir_pipeline", new=AsyncMock(return_value=fake)),
    ):
        inst = MagicMock()
        inst.run = AsyncMock(side_effect=[prelude, gen])
        MockAgent.return_value = inst
        result = await strategy.run("draw two points", model="test-model")

    assert result.recipe_metadata.evaluation_metadata_hard is None
    assert geo_correctness_score(result.recipe_metadata.evaluation_metadata_soft) == 72


@pytest.mark.asyncio
async def test_both_mode_metadata_captured_on_lowering_failure():
    """Metadata is recorded on the lowering-failure trace (it's in hand by then)."""
    from recipe.lower import LoweringError

    strategy = RecipeStrategy(use_recipes=False, confidence_mode="both")
    prelude = _prelude_response(_meta_dict(geo=20))
    gen = _gen_response_structured(geo=25)

    with (
        patch("strategies.recipe.Agent") as MockAgent,
        patch("strategies.recipe.lower_to_ir", side_effect=LoweringError("bad")),
    ):
        inst = MagicMock()
        inst.run = AsyncMock(side_effect=[prelude, gen, gen, gen])
        MockAgent.return_value = inst
        with pytest.raises(RuntimeError, match="RecipeStrategy failed after"):
            await strategy.run("draw something", model="test-model")

    # The prelude ran once up-front; generation ran MAX_RETRIES times.
    from strategies.recipe import MAX_RETRIES
    assert MockAgent.call_count == 1 + MAX_RETRIES


@pytest.mark.asyncio
async def test_both_mode_passes_prelude_prompt_not_generation_prompt():
    """The prelude call gets the fence-asking prompt, NOT generation_prompt.

    Regression guard for the prelude-parse drift bug: feeding generation_prompt
    (whose output line says "Respond with a valid RecipeDSL JSON object only")
    made the model emit a construction instead of the metadata fence. The prelude
    must receive build_prelude_prompt, which asks for the fence.
    """
    strategy = RecipeStrategy(use_recipes=False, confidence_mode="both")
    fake = _make_fake_ir_result()
    prelude = _prelude_response(_meta_dict(geo=40))
    gen = _gen_response_structured(geo=90)

    with (
        patch("strategies.recipe.Agent") as MockAgent,
        patch("strategies.recipe._run_ir_pipeline", new=AsyncMock(return_value=fake)),
    ):
        inst = MagicMock()
        inst.run = AsyncMock(side_effect=[prelude, gen])
        MockAgent.return_value = inst
        await strategy.run("draw two points", model="test-model")

    # First agent.run call is the prelude; its prompt must ask for the fence,
    # not for a RecipeDSL construction.
    first_arg = inst.run.call_args_list[0].args[0]
    assert "[[INTERNAL_METADATA]]" in first_arg
    assert "Do NOT produce a RecipeDSL construction" in first_arg
    # The generation prompt's signature output line must NOT appear in the prelude prompt.
    assert "Respond with a valid RecipeDSL JSON object only" not in first_arg


def test_strip_generation_output_instruction():
    """The extracted output-format line is removed (override arm still embeds it)."""
    with_line = (
        "You generate RecipeDSL JSON objects.\n\n"
        + GEN_OUTPUT_INSTRUCTION_LINE
        + "\n\nKey rules:\n- foo"
    )
    stripped = strip_generation_output_instruction(with_line)
    assert GEN_OUTPUT_INSTRUCTION_LINE not in stripped
    assert "Key rules:" in stripped  # surrounding content preserved
    # No-op when the line is absent.
    without = "You generate RecipeDSL JSON objects.\n\nKey rules:\n- foo"
    assert strip_generation_output_instruction(without) == without
    # Empty input is safe.
    assert strip_generation_output_instruction("") == ""


@pytest.mark.asyncio
async def test_prelude_uses_generation_rules_as_system_prompt():
    """The prelude's system prompt is the generation rules (output-stripped), and
    its user message shares the generation body — only the output format differs.
    """
    strategy = RecipeStrategy(use_recipes=False, confidence_mode="both")
    fake = _make_fake_ir_result()
    prelude = _prelude_response(_meta_dict(geo=40))
    gen = _gen_response_structured(geo=90)

    with (
        patch("strategies.recipe.Agent") as MockAgent,
        patch("strategies.recipe._run_ir_pipeline", new=AsyncMock(return_value=fake)),
    ):
        inst = MagicMock()
        inst.run = AsyncMock(side_effect=[prelude, gen])
        MockAgent.return_value = inst
        await strategy.run("draw two points", model="test-model")

    # First Agent construction is the prelude; its system instructions are the
    # generation rules with the output-format line STRIPPED (so it doesn't
    # contradict the fence request), while still carrying the rest of the rules.
    prelude_instr = MockAgent.call_args_list[0].kwargs["instructions"]
    assert GEN_OUTPUT_INSTRUCTION_LINE not in prelude_instr
    assert "RecipeDSL JSON objects" in prelude_instr  # the generation rules are present

    # Second Agent construction is the real generation call; its system
    # instructions KEEP the output-format line (it's useful for the real call,
    # whose output_type enforces the schema — only the prelude strips it).
    gen_instr = MockAgent.call_args_list[1].kwargs["instructions"]
    assert GEN_OUTPUT_INSTRUCTION_LINE in gen_instr

    # The prelude user message shares the body with the generation call (DSL
    # reference + the request) and asks for the fence, not a construction.
    prelude_user = inst.run.call_args_list[0].args[0]
    assert "DSL Reference" in prelude_user
    assert "draw two points" in prelude_user
    assert "[[INTERNAL_METADATA]]" in prelude_user
    assert "Respond with a valid RecipeDSL JSON object only" not in prelude_user