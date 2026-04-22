"""
Tests for RecipeStrategy's handling of UnexpectedModelBehavior (structured-output
validation failures) during the generation agent call.

All tests mock out the pydantic-ai Agent so no real LLM calls are made.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pydantic
import pytest

from pydantic_ai.exceptions import UnexpectedModelBehavior

from recipe.dsl import RecipeDSL
from strategies.recipe import RecipeStrategy, MAX_RETRIES, RecipeAttemptTrace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_dsl() -> RecipeDSL:
    return RecipeDSL(construction=[])


def _make_agent_response(dsl: RecipeDSL) -> MagicMock:
    """Fake pydantic_ai agent result with a valid RecipeDSL output."""
    response = MagicMock()
    response.output = dsl
    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 50
    response.usage.return_value = usage
    return response


def _make_validation_error() -> pydantic.ValidationError:
    class _M(pydantic.BaseModel):
        x: int
    try:
        _M.model_validate({"x": "not-an-int"})
    except pydantic.ValidationError as e:
        return e
    raise AssertionError("unreachable")


# ---------------------------------------------------------------------------
# Mock setup utilities
# ---------------------------------------------------------------------------

def _patch_strategy_internals(monkeypatch, gen_agent_side_effects: list):
    """
    Patch out all the heavy machinery inside RecipeStrategy.run():
    - Selector agent produces empty selection
    - Generation agent uses provided side_effects list
    - lower_to_ir succeeds immediately
    - _run_ir_pipeline returns a minimal SVG result
    """
    # Selector agent mock (returns empty string, no recipe IDs)
    selector_response = MagicMock()
    selector_response.output = ""
    selector_usage = MagicMock()
    selector_usage.input_tokens = 10
    selector_usage.output_tokens = 5
    selector_response.usage.return_value = selector_usage

    # Build mock side_effects list for Agent constructor calls:
    # First call → selector, subsequent calls → generation agent
    call_count = {"n": 0}

    def make_agent_instance(model, **kwargs):
        inst = MagicMock()
        if call_count["n"] == 0:
            # Selector
            inst.run = AsyncMock(return_value=selector_response)
        else:
            # Generation agent: pull from side_effects in order
            idx = call_count["n"] - 1
            effect = gen_agent_side_effects[idx] if idx < len(gen_agent_side_effects) else gen_agent_side_effects[-1]
            if isinstance(effect, Exception):
                inst.run = AsyncMock(side_effect=effect)
            else:
                inst.run = AsyncMock(return_value=effect)
        call_count["n"] += 1
        return inst

    # Minimal IR pipeline result
    from strategies.structured import StructuredRunResult
    ir_result = MagicMock()
    ir_result.diagram_ir = MagicMock()
    ir_result.tikz = ""
    ir_result.svg = "<svg/>"
    ir_result.sym_table = {}
    ir_result.sym_full = {}

    return (
        patch("strategies.recipe.Agent", side_effect=make_agent_instance),
        patch("strategies.recipe.lower_to_ir", return_value=MagicMock()),
        patch("strategies.recipe._run_ir_pipeline", new=AsyncMock(return_value=ir_result)),
    )


# ---------------------------------------------------------------------------
# Test 1: UnexpectedModelBehavior is caught and becomes retriable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recipe_strategy_catches_unexpected_model_behavior(monkeypatch):
    """
    Generation agent raises UnexpectedModelBehavior twice, then succeeds.
    The strategy should succeed on the third attempt, recording two
    output_validation traces followed by a success trace.
    """
    error = UnexpectedModelBehavior("Exceeded maximum retries (1) for output validation")
    valid_response = _make_agent_response(_make_valid_dsl())

    effects = [error, error, valid_response]
    p_agent, p_lower, p_pipeline = _patch_strategy_internals(monkeypatch, effects)

    with p_agent, p_lower, p_pipeline:
        strategy = RecipeStrategy(use_recipes=True)
        from ir.renderer import SVGRenderer
        result = await strategy.run("Draw a triangle.", renderer=SVGRenderer())

    traces = result.recipe_metadata.attempt_traces
    stages = [t.stage for t in traces]
    assert stages == ["output_validation", "output_validation", "success"], stages
    assert traces[0].error is not None
    assert traces[1].error is not None
    assert traces[2].error is None


# ---------------------------------------------------------------------------
# Test 2: Validation error details are surfaced in the trace
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recipe_strategy_surfaces_validation_diagnostics(monkeypatch):
    """
    When UnexpectedModelBehavior is raised with a chained pydantic ValidationError,
    the trace should include the validation error's loc/msg and a raw_output field.
    """
    # Build a real ValidationError chained onto the UMB
    val_err = _make_validation_error()
    umb = UnexpectedModelBehavior("Exceeded maximum retries (1) for output validation")
    umb.__cause__ = val_err

    valid_response = _make_agent_response(_make_valid_dsl())
    effects = [umb, valid_response, valid_response]  # fail once, then succeed

    p_agent, p_lower, p_pipeline = _patch_strategy_internals(monkeypatch, effects)

    with p_agent, p_lower, p_pipeline:
        strategy = RecipeStrategy(use_recipes=True)
        from ir.renderer import SVGRenderer
        result = await strategy.run("Draw a triangle.", renderer=SVGRenderer())

    fail_trace = next(t for t in result.recipe_metadata.attempt_traces if t.stage == "output_validation")
    # Error string should mention the field name ('x') and the validation failure type
    assert fail_trace.error is not None
    assert "Output validation failed" in fail_trace.error
    # Should include loc and type from the pydantic error
    assert "loc=" in fail_trace.error


# ---------------------------------------------------------------------------
# Test 3: All retries exhausted → RuntimeError propagates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recipe_strategy_all_retries_exhaust_raises(monkeypatch):
    """
    When all MAX_RETRIES attempts raise UnexpectedModelBehavior, the strategy
    should raise RuntimeError mentioning the validation failure.
    """
    error = UnexpectedModelBehavior("Exceeded maximum retries (1) for output validation")
    effects = [error] * MAX_RETRIES

    p_agent, p_lower, p_pipeline = _patch_strategy_internals(monkeypatch, effects)

    with p_agent, p_lower, p_pipeline:
        strategy = RecipeStrategy(use_recipes=True)
        from ir.renderer import SVGRenderer
        with pytest.raises(RuntimeError, match="RecipeStrategy failed"):
            await strategy.run("Draw a triangle.", renderer=SVGRenderer())

    # All attempts should be recorded as output_validation failures
    traces = strategy._partial_recipe_metadata.attempt_traces
    assert len(traces) == MAX_RETRIES
    assert all(t.stage == "output_validation" for t in traces)


# ---------------------------------------------------------------------------
# Test 4: AngleEqual check failure appends a targeted hint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_prompt_includes_angle_hint(monkeypatch):
    """
    When retry error contains an AngleEqual-style failure message,
    the retry prompt should include a targeted hint about ensuring
    geometric similarity when two angles must be equal.
    """
    # Simulate a geometric check failure with AngleEqual error
    angle_error = (
        "Geometric checks failed:\n"
        "  - [annotation: mark_angle group=1] Angle B-S-A = 33.7° but D-T-C = 18.4°"
    )

    valid_response = _make_agent_response(_make_valid_dsl())

    # Track IR pipeline calls to fail on first, succeed on second
    pipeline_calls = {"count": 0}

    async def mock_pipeline(*args, **kwargs):
        pipeline_calls["count"] += 1
        if pipeline_calls["count"] == 1:
            raise RuntimeError(angle_error)
        else:
            ir_result = MagicMock()
            ir_result.diagram_ir = MagicMock()
            ir_result.tikz = ""
            ir_result.svg = "<svg/>"
            ir_result.sym_table = {}
            ir_result.sym_full = {}
            return ir_result

    # Track user messages passed to gen_agent.run
    captured_user_messages = {"messages": []}

    def patch_gen_agent_run(original_run):
        async def wrapper(user_msg):
            captured_user_messages["messages"].append(user_msg)
            return await original_run(user_msg)
        return wrapper

    # Use standard internal patches but hook the pipeline and message capture
    p_agent, p_lower, p_pipeline = _patch_strategy_internals(monkeypatch, [valid_response, valid_response])

    with p_agent as mock_agent_class, p_lower, patch("strategies.recipe._run_ir_pipeline", new=mock_pipeline):
        # Patch Agent to capture user messages
        original_make_agent = mock_agent_class.side_effect

        def patched_make_agent(*args, **kwargs):
            inst = original_make_agent(*args, **kwargs)
            inst.run = patch_gen_agent_run(inst.run)
            return inst

        mock_agent_class.side_effect = patched_make_agent

        strategy = RecipeStrategy(use_recipes=True)
        from ir.renderer import SVGRenderer
        result = await strategy.run("Draw a triangle.", renderer=SVGRenderer())

    # Should have at least 2 gen agent calls: initial + retry
    gen_messages = [m for m in captured_user_messages["messages"] if "RecipeDSL" in m]
    assert len(gen_messages) >= 2, f"Expected at least 2 gen messages, got {len(gen_messages)}"

    # The second gen message is the retry prompt
    retry_prompt = gen_messages[1]

    # Should contain the hint text about angle equality
    assert "When two angles must be equal" in retry_prompt, (
        f"Hint not found in retry prompt. Prompt:\n{retry_prompt}"
    )
    assert "geometrically similar" in retry_prompt
    assert "matching right_angle_at positions" in retry_prompt


@pytest.mark.asyncio
async def test_retry_prompt_no_hint_for_non_angle_errors(monkeypatch):
    """
    When retry error does NOT contain an AngleEqual-style message,
    the hint should NOT be appended.
    """
    # Non-angle error (e.g., some other geometric check)
    generic_error = "Geometric checks failed:\n  - Points A and B coincide"

    valid_response = _make_agent_response(_make_valid_dsl())

    # Track IR pipeline calls to fail on first, succeed on second
    pipeline_calls = {"count": 0}

    async def mock_pipeline(*args, **kwargs):
        pipeline_calls["count"] += 1
        if pipeline_calls["count"] == 1:
            raise RuntimeError(generic_error)
        else:
            ir_result = MagicMock()
            ir_result.diagram_ir = MagicMock()
            ir_result.tikz = ""
            ir_result.svg = "<svg/>"
            ir_result.sym_table = {}
            ir_result.sym_full = {}
            return ir_result

    # Track user messages passed to gen_agent.run
    captured_user_messages = {"messages": []}

    def patch_gen_agent_run(original_run):
        async def wrapper(user_msg):
            captured_user_messages["messages"].append(user_msg)
            return await original_run(user_msg)
        return wrapper

    # Use standard internal patches but hook the pipeline and message capture
    p_agent, p_lower, p_pipeline = _patch_strategy_internals(monkeypatch, [valid_response, valid_response])

    with p_agent as mock_agent_class, p_lower, patch("strategies.recipe._run_ir_pipeline", new=mock_pipeline):
        # Patch Agent to capture user messages
        original_make_agent = mock_agent_class.side_effect

        def patched_make_agent(*args, **kwargs):
            inst = original_make_agent(*args, **kwargs)
            inst.run = patch_gen_agent_run(inst.run)
            return inst

        mock_agent_class.side_effect = patched_make_agent

        strategy = RecipeStrategy(use_recipes=True)
        from ir.renderer import SVGRenderer
        result = await strategy.run("Draw a triangle.", renderer=SVGRenderer())

    # Should have at least 2 gen agent calls: initial + retry
    gen_messages = [m for m in captured_user_messages["messages"] if "RecipeDSL" in m]
    assert len(gen_messages) >= 2, f"Expected at least 2 gen messages, got {len(gen_messages)}"

    # The second gen message is the retry prompt
    retry_prompt = gen_messages[1]

    # Should NOT contain the angle hint
    assert "When two angles must be equal" not in retry_prompt, (
        f"Unexpected angle hint in retry prompt. Prompt:\n{retry_prompt}"
    )


# ---------------------------------------------------------------------------
# Test 5: mark_right_angle geometric check failure appends a targeted hint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_prompt_includes_mark_right_angle_hint(monkeypatch):
    """When retry error contains a mark_right_angle failure, hint about point_foot."""
    ra_error = (
        "Geometric checks failed:\n"
        "  - [annotation: mark_right_angle(A,M,C)] Angle A-M-C is 153.4°, not 90°"
    )

    valid_response = _make_agent_response(_make_valid_dsl())

    pipeline_calls = {"count": 0}

    async def mock_pipeline(*args, **kwargs):
        pipeline_calls["count"] += 1
        if pipeline_calls["count"] == 1:
            raise RuntimeError(ra_error)
        else:
            ir_result = MagicMock()
            ir_result.diagram_ir = MagicMock()
            ir_result.tikz = ""
            ir_result.svg = "<svg/>"
            ir_result.sym_table = {}
            ir_result.sym_full = {}
            return ir_result

    captured_user_messages = {"messages": []}

    def patch_gen_agent_run(original_run):
        async def wrapper(user_msg):
            captured_user_messages["messages"].append(user_msg)
            return await original_run(user_msg)
        return wrapper

    p_agent, p_lower, p_pipeline = _patch_strategy_internals(monkeypatch, [valid_response, valid_response])

    with p_agent as mock_agent_class, p_lower, patch("strategies.recipe._run_ir_pipeline", new=mock_pipeline):
        original_make_agent = mock_agent_class.side_effect

        def patched_make_agent(*args, **kwargs):
            inst = original_make_agent(*args, **kwargs)
            inst.run = patch_gen_agent_run(inst.run)
            return inst

        mock_agent_class.side_effect = patched_make_agent

        strategy = RecipeStrategy(use_recipes=True)
        from ir.renderer import SVGRenderer
        result = await strategy.run("Draw a triangle.", renderer=SVGRenderer())

    gen_messages = [m for m in captured_user_messages["messages"] if "RecipeDSL" in m]
    assert len(gen_messages) >= 2, f"Expected at least 2 gen messages, got {len(gen_messages)}"

    retry_prompt = gen_messages[1]

    assert "point_foot" in retry_prompt, (
        f"point_foot hint not found in retry prompt. Prompt:\n{retry_prompt}"
    )


# ---------------------------------------------------------------------------
# Test 6: between-selector mismatch appends a targeted hint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_prompt_includes_between_selector_hint(monkeypatch):
    """When retry error contains 'beyond … t≈', hint about chord/endpoint placement."""
    between_error = (
        "IR compilation failed: [E] no candidate lies between 'A' and 'B' "
        "(nearest candidate is beyond 'B', t≈1.40)"
    )

    valid_response = _make_agent_response(_make_valid_dsl())

    pipeline_calls = {"count": 0}

    async def mock_pipeline(*args, **kwargs):
        pipeline_calls["count"] += 1
        if pipeline_calls["count"] == 1:
            raise RuntimeError(between_error)
        else:
            ir_result = MagicMock()
            ir_result.diagram_ir = MagicMock()
            ir_result.tikz = ""
            ir_result.svg = "<svg/>"
            ir_result.sym_table = {}
            ir_result.sym_full = {}
            return ir_result

    captured_user_messages = {"messages": []}

    def patch_gen_agent_run(original_run):
        async def wrapper(user_msg):
            captured_user_messages["messages"].append(user_msg)
            return await original_run(user_msg)
        return wrapper

    p_agent, p_lower, p_pipeline = _patch_strategy_internals(monkeypatch, [valid_response, valid_response])

    with p_agent as mock_agent_class, p_lower, patch("strategies.recipe._run_ir_pipeline", new=mock_pipeline):
        original_make_agent = mock_agent_class.side_effect

        def patched_make_agent(*args, **kwargs):
            inst = original_make_agent(*args, **kwargs)
            inst.run = patch_gen_agent_run(inst.run)
            return inst

        mock_agent_class.side_effect = patched_make_agent

        strategy = RecipeStrategy(use_recipes=True)
        from ir.renderer import SVGRenderer
        result = await strategy.run("Draw a triangle.", renderer=SVGRenderer())

    gen_messages = [m for m in captured_user_messages["messages"] if "RecipeDSL" in m]
    assert len(gen_messages) >= 2, f"Expected at least 2 gen messages, got {len(gen_messages)}"

    retry_prompt = gen_messages[1]

    assert "beyond" in retry_prompt or "outside" in retry_prompt, (
        f"between-selector hint not found in retry prompt. Prompt:\n{retry_prompt}"
    )


# ---------------------------------------------------------------------------
# Test 7: Negative — unrelated errors do not get the mark_right_angle hint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_prompt_no_mark_right_angle_hint_for_other_errors(monkeypatch):
    """Unrelated errors do not get the mark_right_angle hint."""
    unrelated_error = "Geometric checks failed:\n  - Points A and B coincide"

    valid_response = _make_agent_response(_make_valid_dsl())

    pipeline_calls = {"count": 0}

    async def mock_pipeline(*args, **kwargs):
        pipeline_calls["count"] += 1
        if pipeline_calls["count"] == 1:
            raise RuntimeError(unrelated_error)
        else:
            ir_result = MagicMock()
            ir_result.diagram_ir = MagicMock()
            ir_result.tikz = ""
            ir_result.svg = "<svg/>"
            ir_result.sym_table = {}
            ir_result.sym_full = {}
            return ir_result

    captured_user_messages = {"messages": []}

    def patch_gen_agent_run(original_run):
        async def wrapper(user_msg):
            captured_user_messages["messages"].append(user_msg)
            return await original_run(user_msg)
        return wrapper

    p_agent, p_lower, p_pipeline = _patch_strategy_internals(monkeypatch, [valid_response, valid_response])

    with p_agent as mock_agent_class, p_lower, patch("strategies.recipe._run_ir_pipeline", new=mock_pipeline):
        original_make_agent = mock_agent_class.side_effect

        def patched_make_agent(*args, **kwargs):
            inst = original_make_agent(*args, **kwargs)
            inst.run = patch_gen_agent_run(inst.run)
            return inst

        mock_agent_class.side_effect = patched_make_agent

        strategy = RecipeStrategy(use_recipes=True)
        from ir.renderer import SVGRenderer
        result = await strategy.run("Draw a triangle.", renderer=SVGRenderer())

    gen_messages = [m for m in captured_user_messages["messages"] if "RecipeDSL" in m]
    assert len(gen_messages) >= 2, f"Expected at least 2 gen messages, got {len(gen_messages)}"

    retry_prompt = gen_messages[1]

    assert "point_foot" not in retry_prompt, (
        f"Unexpected point_foot hint in retry prompt. Prompt:\n{retry_prompt}"
    )
