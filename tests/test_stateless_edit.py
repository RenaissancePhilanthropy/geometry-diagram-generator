# tests/test_stateless_edit.py
"""Stateless edit entry points: StructureStrategy.run(previous_ir=...),
PythonFullStrategy.edit(...), and the facade routing of previous_dsl /
previous_script / previous_ir to the strategy that owns each.

No LLM calls or renderer container required — all external calls are mocked.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from geometry_diagrams.config import GeometryConfig
from geometry_diagrams.facade import (
    DiagramResult,
    _make_strategy,
    edit_geometry_diagram,
    render_geometry_diagram,
)
from geometry_diagrams.ir.ir import DiagramIR
from geometry_diagrams.strategies import python_full as pf
from geometry_diagrams.strategies import structured as st
from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
from geometry_diagrams.strategies.python_full import PythonFullStrategy
from geometry_diagrams.strategies.recipe import RecipeStrategy
from geometry_diagrams.strategies.structured import StructureStrategy


@pytest.fixture(autouse=True)
def reset_tracing():
    from geometry_diagrams.util import tracing
    tracing._reset()
    yield
    tracing._reset()


def _ir() -> DiagramIR:
    return DiagramIR(define=[], render=[])


def _result(script: str = "", svg: str = "<svg/>") -> StructuredRunResult:
    return StructuredRunResult(
        diagram_ir=_ir(), tikz="", svg=svg, sym_table={}, sym_full={}, script=script,
        entity_manifest={"named": [], "anonymous": []},
    )


# ---------------------------------------------------------------------------
# StructureStrategy.run(previous_ir=...)
# ---------------------------------------------------------------------------

class _FakeGraph:
    def __init__(self, result):
        self.result = result
        self.state = None

    async def ainvoke(self, state, config=None):
        self.state = state
        return {"result": self.result, "input_tokens": 1, "output_tokens": 2, "cost_usd": 0.0}


@pytest.mark.asyncio
async def test_structured_run_without_previous_ir_sends_bare_prompt(monkeypatch):
    graph = _FakeGraph(_result())
    monkeypatch.setattr(st, "_build_structured_graph", lambda: graph)
    await StructureStrategy().run("draw a triangle")
    assert graph.state["prompt"] == "draw a triangle"


@pytest.mark.asyncio
@pytest.mark.parametrize("as_dict", [True, False])
async def test_structured_run_previous_ir_is_embedded_in_prompt(monkeypatch, as_dict):
    graph = _FakeGraph(_result())
    monkeypatch.setattr(st, "_build_structured_graph", lambda: graph)
    prior = _ir()
    await StructureStrategy().run(
        "make it bigger", previous_ir=prior.model_dump() if as_dict else prior,
    )
    prompt = graph.state["prompt"]
    assert prompt.startswith("make it bigger")
    assert prior.model_dump_json(indent=2) in prompt


@pytest.mark.asyncio
async def test_structured_run_invalid_previous_ir_raises_value_error(monkeypatch):
    monkeypatch.setattr(st, "_build_structured_graph", lambda: _FakeGraph(_result()))
    with pytest.raises(ValueError, match="previous_ir is not a valid DiagramIR"):
        await StructureStrategy().run("edit", previous_ir={"define": "nope"})


# ---------------------------------------------------------------------------
# PythonFullStrategy.edit(...)
# ---------------------------------------------------------------------------

PREV = "a = point(0, 0)\ndraw_points(a)\n"


@pytest.mark.asyncio
async def test_python_full_edit_full_rewrite_prompt_carries_script_and_manifest(monkeypatch):
    rebuilt = _result(PREV)
    rebuilt.entity_manifest = {"named": [{"name": "a", "type": "point_fixed"}], "anonymous": []}
    baseline_calls = []

    async def fake_from_script(script, renderer, *a, **kw):
        baseline_calls.append(script)
        return rebuilt

    prompts = []

    async def fake_run(self, prompt, model="m", renderer=None, sandbox_timeout_seconds=2.5, **kw):
        prompts.append(prompt)
        return _result("a = point(0, 1)\n")

    monkeypatch.setattr(pf, "_run_from_script", fake_from_script)
    monkeypatch.setattr(PythonFullStrategy, "run", fake_run)

    out = await PythonFullStrategy().edit(
        "move a up", PREV, model="m", edit_generation_mode="full_rewrite",
    )
    assert baseline_calls == [PREV]  # previous script re-run to rebuild the manifest
    assert out.script == "a = point(0, 1)\n"
    assert "move a up" in prompts[0] and PREV in prompts[0]
    assert '"point_fixed"' in prompts[0]


@pytest.mark.asyncio
async def test_python_full_edit_search_replace_applies_blocks_to_previous_script(monkeypatch):
    seen_scripts = []

    async def fake_from_script(script, renderer, *a, **kw):
        seen_scripts.append(script)
        return _result(script)

    async def fake_gen(prompt, model):
        return [{"old_string": "point(0, 0)", "new_string": "point(0, 5)"}], 11, 7, 0.01

    monkeypatch.setattr(pf, "_run_from_script", fake_from_script)
    monkeypatch.setattr(pf, "generate_search_replace", fake_gen)

    await PythonFullStrategy().edit("move a up", PREV, model="m")  # default mode
    assert seen_scripts == [PREV, "a = point(0, 5)\ndraw_points(a)\n"]


@pytest.mark.asyncio
async def test_python_full_edit_previous_script_that_fails_raises_value_error(monkeypatch):
    async def boom(script, renderer, *a, **kw):
        raise RuntimeError("patch-mode script failed: NameError")

    monkeypatch.setattr(pf, "_run_from_script", boom)
    with pytest.raises(ValueError, match="previous_script did not run"):
        await PythonFullStrategy().edit("x", "garbage(", model="m")


@pytest.mark.asyncio
async def test_python_full_edit_error_message_drops_internal_patch_mode_prefix(monkeypatch):
    async def boom(script, renderer, *a, **kw):
        raise RuntimeError("patch-mode script failed: NameError: zz")

    monkeypatch.setattr(pf, "_run_from_script", boom)
    with pytest.raises(ValueError) as exc:
        await PythonFullStrategy().edit("x", "zz", model="m")
    assert str(exc.value) == "previous_script did not run: NameError: zz"


@pytest.mark.asyncio
async def test_python_full_edit_baseline_uses_svg_renderer_edit_uses_callers(monkeypatch):
    from geometry_diagrams.ir.renderer import SVGRenderer

    renderers = []

    async def fake_from_script(script, renderer, *a, **kw):
        renderers.append(renderer)
        return _result(script)

    async def fake_gen(prompt, model):
        return [{"old_string": "point(0, 0)", "new_string": "point(0, 5)"}], 0, 0, None

    monkeypatch.setattr(pf, "_run_from_script", fake_from_script)
    monkeypatch.setattr(pf, "generate_search_replace", fake_gen)

    caller_renderer = MagicMock(name="tikz_like")
    await PythonFullStrategy().edit("up", PREV, model="m", renderer=caller_renderer)
    assert isinstance(renderers[0], SVGRenderer)  # baseline: never the caller's (TikZ) renderer
    assert renderers[1] is caller_renderer        # the edit itself renders with it


@pytest.mark.asyncio
async def test_python_full_edit_rejects_blank_previous_script():
    with pytest.raises(ValueError, match="previous_script"):
        await PythonFullStrategy().edit("x", "   \n", model="m")


# ---------------------------------------------------------------------------
# Facade routing
# ---------------------------------------------------------------------------

def test_make_strategy_structured():
    assert isinstance(_make_strategy(GeometryConfig(strategy="structured")), StructureStrategy)


@pytest.mark.asyncio
async def test_facade_python_full_previous_script_calls_edit_with_config(monkeypatch):
    captured = {}

    async def fake_edit(self, request, previous_script, **kw):
        captured.update(request=request, previous_script=previous_script, **kw)
        return _result("new script")

    async def no_run(*a, **kw):
        raise AssertionError("run() must not be called on an edit")

    monkeypatch.setattr(PythonFullStrategy, "edit", fake_edit)
    monkeypatch.setattr(PythonFullStrategy, "run", no_run)

    cfg = GeometryConfig(
        strategy="python_full", renderer="svg", edit_generation_mode="hashline",
        hash_algorithm="xxhash", sandbox_timeout_seconds=4.0,
    )
    res = await render_geometry_diagram("move it", config=cfg, previous_script=PREV)
    assert captured["request"] == "move it"
    assert captured["previous_script"] == PREV
    assert captured["edit_generation_mode"] == "hashline"
    assert captured["hash_algorithm"] == "xxhash"
    assert captured["sandbox_timeout_seconds"] == 4.0
    assert res.script == "new script"


@pytest.mark.asyncio
async def test_facade_structured_generates_and_edits(monkeypatch):
    captured = {}

    async def fake_run(self, prompt, model=None, renderer=None, previous_ir=None, **kw):
        captured["previous_ir"] = previous_ir
        return _result()

    monkeypatch.setattr(StructureStrategy, "run", fake_run)
    cfg = GeometryConfig(strategy="structured", renderer="svg")

    res = await render_geometry_diagram("a triangle", config=cfg)
    assert captured["previous_ir"] is None
    assert isinstance(res, DiagramResult)
    assert res.diagram_ir == _ir().model_dump()
    assert res.dsl is None and res.recipes is None and res.script is None

    prior = res.diagram_ir
    await edit_geometry_diagram("bigger", config=cfg, previous_ir=prior)
    assert captured["previous_ir"] == prior


@pytest.mark.asyncio
async def test_facade_edit_geometry_diagram_python_full_previous_script(monkeypatch):
    captured = {}

    async def fake_edit(self, request, previous_script, **kw):
        captured["previous_script"] = previous_script
        return _result("s")

    monkeypatch.setattr(PythonFullStrategy, "edit", fake_edit)
    await edit_geometry_diagram(
        "x", config=GeometryConfig(strategy="python_full", renderer="svg"), previous_script=PREV,
    )
    assert captured["previous_script"] == PREV


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "strategy, kwargs, match",
    [
        ("recipe", {"previous_script": "x"}, "previous_script is only supported"),
        ("recipe", {"previous_ir": {}}, "previous_ir is only supported"),
        ("python_full", {"previous_dsl": {}}, "previous_dsl is only supported"),
        ("python_full", {"previous_ir": {}}, "previous_ir is only supported"),
        ("structured", {"previous_dsl": {}}, "previous_dsl is only supported"),
        ("structured", {"previous_script": "x"}, "previous_script is only supported"),
        ("recipe", {"previous_dsl": {}, "previous_script": "x"}, "at most one"),
    ],
)
async def test_facade_rejects_previous_state_for_the_wrong_strategy(strategy, kwargs, match):
    with pytest.raises(ValueError, match=match):
        await render_geometry_diagram("edit", strategy=strategy, renderer="svg", **kwargs)


@pytest.mark.asyncio
async def test_facade_edit_requires_exactly_one_previous():
    with pytest.raises(ValueError, match="exactly one"):
        await edit_geometry_diagram("x", config=GeometryConfig(renderer="svg"))
    with pytest.raises(ValueError, match="exactly one"):
        await edit_geometry_diagram(
            "x", {}, config=GeometryConfig(renderer="svg"), previous_script="s",
        )


@pytest.mark.asyncio
async def test_facade_recipe_edit_still_passes_previous_dsl(monkeypatch):
    captured = {}

    async def fake_run(self, prompt, model=None, renderer=None, previous_dsl=None, **kw):
        captured["previous_dsl"] = previous_dsl
        return _result()

    monkeypatch.setattr(RecipeStrategy, "run", fake_run)
    await edit_geometry_diagram("x", {"mode": "abstract"}, config=GeometryConfig(renderer="svg"))
    assert captured["previous_dsl"] == {"mode": "abstract"}
