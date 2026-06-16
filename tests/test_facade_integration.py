# tests/test_facade_integration.py
"""Pure-unit tests covering facade integration: _build_run_config, DiagramResult artifacts,
previous_dsl seeding, and render_diagram @tool output.

No LLM calls or renderer container required — all external calls are mocked.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from geometry_diagrams.strategies.base import SubstanceStrategy, DEFAULT_AGENT_MODEL
from geometry_diagrams.strategies.recipe import (
    RecipeStrategy,
    RecipeMetadata,
    RecipeAttemptTrace,
)
from geometry_diagrams.strategies.structured import StructuredRunResult
from geometry_diagrams.facade import DiagramResult, render_geometry_diagram
from geometry_diagrams import render_diagram  # the @tool


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_tracing():
    """Reset tracing module singleton before/after each test."""
    from geometry_diagrams.util import tracing
    tracing._reset()
    yield
    tracing._reset()


class _StubStrategy(SubstanceStrategy):
    """Minimal concrete subclass to test SubstanceStrategy methods."""

    def build_agent(self, model: str = DEFAULT_AGENT_MODEL, renderer=None):
        return MagicMock()


def _make_fake_structured_result(
    svg: str = "<svg/>",
    tikz: str = "",
    input_tokens: int = 10,
    output_tokens: int = 5,
    diagram_ir=None,
    recipe_metadata=None,
) -> StructuredRunResult:
    ir = diagram_ir if diagram_ir is not None else MagicMock()
    ir.model_dump = MagicMock(return_value={"canvas": {}})
    r = StructuredRunResult(
        diagram_ir=ir,
        tikz=tikz,
        svg=svg,
        sym_table={},
        sym_full={},
    )
    r.input_tokens = input_tokens
    r.output_tokens = output_tokens
    r.recipe_metadata = recipe_metadata
    return r


# ---------------------------------------------------------------------------
# Test Group 1 — _build_run_config on SubstanceStrategy
# ---------------------------------------------------------------------------

class TestBuildRunConfig:

    def test_build_run_config_no_args(self):
        """No args → {} when get_callback_handler() returns None."""
        strategy = _StubStrategy()
        with patch("geometry_diagrams.util.tracing.get_callback_handler", return_value=None):
            result = strategy._build_run_config()
        assert result == {}

    def test_build_run_config_env_handler_included(self):
        """When get_callback_handler() returns a sentinel, it appears in callbacks."""
        strategy = _StubStrategy()
        sentinel = MagicMock(name="env_handler")
        with patch("geometry_diagrams.util.tracing.get_callback_handler", return_value=sentinel):
            result = strategy._build_run_config()
        assert "callbacks" in result
        assert sentinel in result["callbacks"]

    def test_build_run_config_caller_config_callbacks_merged(self):
        """config callbacks + explicit callbacks + env handler are all present."""
        strategy = _StubStrategy()
        h1, h2, h3 = MagicMock(name="h1"), MagicMock(name="h2"), MagicMock(name="h3")
        with patch("geometry_diagrams.util.tracing.get_callback_handler", return_value=h3):
            result = strategy._build_run_config(config={"callbacks": [h1]}, callbacks=[h2])
        cbs = result["callbacks"]
        assert h1 in cbs
        assert h2 in cbs
        assert h3 in cbs
        # h1 first (from config), then h2, then h3
        assert cbs.index(h1) < cbs.index(h2) < cbs.index(h3)

    def test_build_run_config_dedup_env_handler(self):
        """Env handler already present in config callbacks → appears only once."""
        strategy = _StubStrategy()
        h = MagicMock(name="h")
        with patch("geometry_diagrams.util.tracing.get_callback_handler", return_value=h):
            result = strategy._build_run_config(config={"callbacks": [h]})
        assert result["callbacks"].count(h) == 1

    def test_build_run_config_preserves_metadata_tags(self):
        """metadata and tags from config are preserved in the result."""
        strategy = _StubStrategy()
        h1 = MagicMock(name="h1")
        with patch("geometry_diagrams.util.tracing.get_callback_handler", return_value=None):
            result = strategy._build_run_config(
                config={"callbacks": [h1], "metadata": {"trace": "x"}, "tags": ["foo"]}
            )
        assert result["metadata"] == {"trace": "x"}
        assert result["tags"] == ["foo"]

    def test_build_run_config_nonlist_manager_returned_as_is(self):
        """Non-list callback manager → returned as-is; env handler NOT added."""
        strategy = _StubStrategy()
        manager_mock = MagicMock(name="manager")  # not a list
        env_handler = MagicMock(name="env_handler")
        with patch("geometry_diagrams.util.tracing.get_callback_handler", return_value=env_handler):
            result = strategy._build_run_config(config={"callbacks": manager_mock})
        assert result == {"callbacks": manager_mock}
        assert env_handler not in result.get("callbacks", [])

    def test_run_config_property_delegates(self):
        """_run_config property returns same result as _build_run_config()."""
        strategy = _StubStrategy()
        with patch("geometry_diagrams.util.tracing.get_callback_handler", return_value=None):
            from_property = strategy._run_config
            from_method = strategy._build_run_config()
        assert from_property == from_method


# ---------------------------------------------------------------------------
# Test Group 2 — render_geometry_diagram forwards config/callbacks to strategy.run
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_render_geometry_diagram_forwards_config_to_strategy(monkeypatch):
    """config= and callbacks= passed to render_geometry_diagram reach RecipeStrategy.run."""
    captured = {}

    fake_result = _make_fake_structured_result(
        recipe_metadata=RecipeMetadata(
            selected_recipes=["triangle"],
            attempt_traces=[
                RecipeAttemptTrace(
                    attempt=1,
                    dsl_json={"mode": "abstract", "construction": []},
                    error=None,
                    stage="success",
                )
            ],
        )
    )

    async def fake_run(self, prompt, *, model=None, renderer=None,
                       config=None, callbacks=None, previous_dsl=None):
        captured["config"] = config
        captured["callbacks"] = callbacks
        return fake_result

    monkeypatch.setattr("geometry_diagrams.strategies.recipe.RecipeStrategy.run", fake_run)

    h_caller = MagicMock(name="caller_handler")
    await render_geometry_diagram(
        "draw a triangle",
        run_config={"callbacks": [h_caller], "tags": ["test"]},
        callbacks=[],
    )
    # Assert callbacks were forwarded to strategy.run
    assert captured["config"] == {"callbacks": [h_caller], "tags": ["test"]}
    assert captured["callbacks"] == []


# ---------------------------------------------------------------------------
# Test Group 3 — DiagramResult artifacts populated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_diagram_result_artifacts_populated(monkeypatch):
    """DiagramResult.dsl, .diagram_ir, .recipes are extracted from strategy result."""
    dsl_json = {"mode": "abstract", "construction": []}
    ir_mock = MagicMock()
    ir_mock.model_dump = MagicMock(return_value={"canvas": {}})

    metadata = RecipeMetadata(
        selected_recipes=["triangle"],
        attempt_traces=[
            RecipeAttemptTrace(
                attempt=1,
                dsl_json=dsl_json,
                error=None,
                stage="success",
            )
        ],
    )
    fake_result = _make_fake_structured_result(
        svg="<svg/>",
        tikz="",
        input_tokens=10,
        output_tokens=5,
        diagram_ir=ir_mock,
        recipe_metadata=metadata,
    )

    async def fake_run(self, prompt, *, model=None, renderer=None,
                       config=None, callbacks=None, previous_dsl=None):
        return fake_result

    monkeypatch.setattr("geometry_diagrams.strategies.recipe.RecipeStrategy.run", fake_run)

    result = await render_geometry_diagram("draw a triangle")

    assert result.dsl == dsl_json
    assert result.diagram_ir == {"canvas": {}}
    assert result.recipes == ["triangle"]
    assert result.input_tokens == 10
    assert result.output_tokens == 5


@pytest.mark.asyncio
async def test_diagram_result_dsl_none_when_no_success_trace(monkeypatch):
    """When recipe_metadata has no successful traces, dsl is None."""
    ir_mock = MagicMock()
    ir_mock.model_dump = MagicMock(return_value={"canvas": {}})

    metadata = RecipeMetadata(
        selected_recipes=[],
        attempt_traces=[
            RecipeAttemptTrace(
                attempt=1,
                dsl_json=None,
                error="Something failed",
                stage="lowering",
            )
        ],
    )
    fake_result = _make_fake_structured_result(
        diagram_ir=ir_mock,
        recipe_metadata=metadata,
    )

    async def fake_run(self, prompt, *, model=None, renderer=None,
                       config=None, callbacks=None, previous_dsl=None):
        return fake_result

    monkeypatch.setattr("geometry_diagrams.strategies.recipe.RecipeStrategy.run", fake_run)

    result = await render_geometry_diagram("draw something")
    assert result.dsl is None


@pytest.mark.asyncio
async def test_diagram_result_uses_last_successful_dsl(monkeypatch):
    """When there are two success traces, the last one's dsl_json is used."""
    ir_mock = MagicMock()
    ir_mock.model_dump = MagicMock(return_value={"canvas": {}})

    metadata = RecipeMetadata(
        selected_recipes=["triangle"],
        attempt_traces=[
            RecipeAttemptTrace(
                attempt=1,
                dsl_json={"mode": "abstract"},
                error=None,
                stage="success",
            ),
            RecipeAttemptTrace(
                attempt=2,
                dsl_json={"mode": "grid"},
                error=None,
                stage="success",
            ),
        ],
    )
    fake_result = _make_fake_structured_result(
        diagram_ir=ir_mock,
        recipe_metadata=metadata,
    )

    async def fake_run(self, prompt, *, model=None, renderer=None,
                       config=None, callbacks=None, previous_dsl=None):
        return fake_result

    monkeypatch.setattr("geometry_diagrams.strategies.recipe.RecipeStrategy.run", fake_run)

    result = await render_geometry_diagram("draw a triangle")
    assert result.dsl == {"mode": "grid"}


# ---------------------------------------------------------------------------
# Test Group 4 — previous_dsl seeds the modification prompt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_previous_dsl_seeds_prompt(monkeypatch):
    """When previous_dsl is provided, prompt contains modification preamble with prior DSL."""
    captured_state: dict = {}
    dsl_json = {
        "mode": "grid",
        "construction": [
            {"op": "point", "id": "A", "coords": [0.0, 0.0]},
        ],
    }

    ir_mock = MagicMock()
    ir_mock.model_dump = MagicMock(return_value={"canvas": {}})
    metadata = RecipeMetadata(
        selected_recipes=[],
        attempt_traces=[
            RecipeAttemptTrace(attempt=1, dsl_json={}, error=None, stage="success")
        ],
    )
    fake_result = _make_fake_structured_result(
        diagram_ir=ir_mock, recipe_metadata=metadata
    )

    fake_graph = MagicMock()

    async def fake_ainvoke(state, config=None):
        captured_state.update(state)
        return {
            "result": fake_result,
            "input_tokens": 0,
            "output_tokens": 0,
            "recipe_metadata": metadata,
        }

    fake_graph.ainvoke = fake_ainvoke
    monkeypatch.setattr(
        "geometry_diagrams.strategies.recipe._build_recipe_graph",
        lambda: fake_graph,
    )

    strategy = RecipeStrategy()
    await strategy.run(
        "add a label",
        model=DEFAULT_AGENT_MODEL,
        previous_dsl=dsl_json,
    )

    prompt = captured_state.get("prompt", "")
    assert "Previous RecipeDSL" in prompt
    # The serialized DSL content should appear
    assert "point" in prompt or "coords" in prompt or "construction" in prompt


@pytest.mark.asyncio
async def test_previous_dsl_none_passes_bare_prompt(monkeypatch):
    """No previous_dsl → prompt is the original request, unmodified."""
    captured_state: dict = {}

    ir_mock = MagicMock()
    ir_mock.model_dump = MagicMock(return_value={"canvas": {}})
    metadata = RecipeMetadata(
        selected_recipes=[],
        attempt_traces=[
            RecipeAttemptTrace(attempt=1, dsl_json={}, error=None, stage="success")
        ],
    )
    fake_result = _make_fake_structured_result(
        diagram_ir=ir_mock, recipe_metadata=metadata
    )

    fake_graph = MagicMock()

    async def fake_ainvoke(state, config=None):
        captured_state.update(state)
        return {
            "result": fake_result,
            "input_tokens": 0,
            "output_tokens": 0,
            "recipe_metadata": metadata,
        }

    fake_graph.ainvoke = fake_ainvoke
    monkeypatch.setattr(
        "geometry_diagrams.strategies.recipe._build_recipe_graph",
        lambda: fake_graph,
    )

    strategy = RecipeStrategy()
    original_prompt = "draw two points"
    await strategy.run(original_prompt, model=DEFAULT_AGENT_MODEL, previous_dsl=None)

    assert captured_state.get("prompt") == original_prompt


def test_previous_dsl_invalid_raises_value_error():
    """Passing an invalid dict as previous_dsl raises ValueError."""
    import asyncio

    strategy = RecipeStrategy()
    with pytest.raises(ValueError, match="previous_dsl is not a valid RecipeDSL"):
        asyncio.run(
            strategy.run(
                "edit it",
                model=DEFAULT_AGENT_MODEL,
                previous_dsl={"invalid_field": 123},
            )
        )


# ---------------------------------------------------------------------------
# Test Group 5 — render_diagram @tool output
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_render_diagram_tool_output_includes_dsl_and_tokens(monkeypatch):
    """render_diagram @tool JSON includes dsl, input_tokens, output_tokens."""
    fake_diagram_result = DiagramResult(
        svg="<svg/>",
        tikz="\\tkzInit",
        input_tokens=42,
        output_tokens=17,
        dsl={"mode": "grid", "construction": []},
        diagram_ir={"canvas": {}},
        recipes=["triangle"],
    )

    async def fake_render(prompt, **kwargs):
        return fake_diagram_result

    monkeypatch.setattr(
        "geometry_diagrams.facade.render_geometry_diagram",
        fake_render,
    )

    output = await render_diagram.ainvoke({"prompt": "draw a triangle"})
    parsed = json.loads(output)

    assert parsed["dsl"] == {"mode": "grid", "construction": []}
    assert parsed["input_tokens"] == 42
    assert parsed["output_tokens"] == 17
    assert parsed["svg"] == "<svg/>"
    # diagram_ir and recipes intentionally omitted from @tool output
    assert "diagram_ir" not in parsed
    assert "recipes" not in parsed


@pytest.mark.asyncio
async def test_render_diagram_tool_error_returns_error_json(monkeypatch):
    """render_diagram @tool returns {"error": ...} on exception."""
    async def raise_error(prompt, **kwargs):
        raise RuntimeError("renderer offline")

    monkeypatch.setattr(
        "geometry_diagrams.facade.render_geometry_diagram",
        raise_error,
    )

    output = await render_diagram.ainvoke({"prompt": "draw something"})
    parsed = json.loads(output)

    assert "error" in parsed
    assert "renderer offline" in parsed["error"]
