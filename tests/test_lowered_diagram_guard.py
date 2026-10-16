"""Guard against serializing render-time views (block-stacks ticket 14).

``OrderedPolygon`` stays outside the validated ``RenderOp`` union, so a lowered
diagram (``derived.lower_render``) cannot round-trip and the effective diagram
(``derived.effective_diagram``) loses ``_synthesized_by`` on a round-trip. Both
are internal views: they refuse ``model_dump`` / ``model_dump_json``, and no
production path may dump or re-validate one."""
from __future__ import annotations

import asyncio
import json
import re
import warnings as pywarnings
from pathlib import Path

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.derived import effective_diagram, lower_render
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_svg import ir_to_svg
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz
from geometry_diagrams.recipe.dsl import RecipeDSL
from geometry_diagrams.recipe.lower import lower_to_ir
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline

ROOT = Path(__file__).parent.parent


def _stack() -> ir.DiagramIR:
    return ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=0, y=0),
                ir.BlockStack(id="S", origin="O", heights=[[2, 1], [1, 3]])],
        render=[ir.Draw(obj="S")],
    )


def _prism() -> ir.DiagramIR:
    return ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=0, y=0),
                ir.RectangularPrism(id="P", origin="O", length=4, width=3, height=2)],
        render=[ir.Draw(obj="P")],
    )


def _recipe_stack() -> ir.DiagramIR:
    return lower_to_ir(RecipeDSL.model_validate({
        "construction": [{"op": "point", "id": "O", "coords": [0, 0]},
                         {"op": "stack", "id": "S", "origin": "O", "heights": [[1, 2], [3, 0]]}],
        "annotations": {},
        "checks": [],
    }))


# --- the views refuse serialization ------------------------------------------------

@pytest.mark.parametrize("build", [_stack, _prism])
@pytest.mark.parametrize("view", [lambda d: lower_render(d, compile_defs(d)), effective_diagram,
                                  lambda d: lower_render(effective_diagram(d), compile_defs(d))])
@pytest.mark.parametrize("method", ["model_dump", "model_dump_json"])
def test_render_views_refuse_serialization(build, view, method):
    v = view(build())
    assert v is not build() and type(v) is not ir.DiagramIR
    with pytest.raises(TypeError, match="internal render-time view"):
        getattr(v, method)()
    with pytest.raises(TypeError, match="dump the authored DiagramIR"):
        getattr(v, method)(mode="json")


def test_lowered_stack_has_ordered_polygons_and_still_copies():
    d = _stack()
    v = lower_render(effective_diagram(d), compile_defs(d))
    assert any(isinstance(op, ir.OrderedPolygon) for op in v.render)
    c = v.model_copy(update={"styles": {}})
    assert c.render == v.render
    with pytest.raises(TypeError, match="internal render-time view"):
        c.model_dump()


def test_authored_diagram_dump_is_unchanged_and_clean():
    d = _stack()
    with pywarnings.catch_warnings():
        pywarnings.simplefilter("error")
        dumped = d.model_dump()
        text = d.model_dump_json()
    assert type(d) is ir.DiagramIR
    assert dumped["define"][1]["kind"] == "block_stack"
    assert dumped["render"][0]["kind"] == "draw" and dumped["render"][0]["obj"] == "S"
    assert set(dumped) == {"params", "canvas", "define", "checks", "render",
                           "pending_angle_pairs", "styles"}
    assert ir.DiagramIR.model_validate_json(text) == d
    # authored dumping is unaffected by having rendered it
    asyncio.run(run_ir_pipeline(d, SVGRenderer()))
    assert d.model_dump() == dumped


# --- production never dumps or re-validates a view ---------------------------------

def _is_view(d) -> bool:
    return (type(d) is not ir.DiagramIR
            or any(getattr(s, "_synthesized_by", None) for s in d.define)
            or any(isinstance(op, ir.OrderedPolygon) for op in d.render))


@pytest.fixture
def spy(monkeypatch):
    seen: list[str] = []
    for name in ("model_dump", "model_dump_json"):
        orig = getattr(ir.DiagramIR, name)

        def wrapper(self, *a, _orig=orig, _name=name, **k):
            if _is_view(self):
                seen.append(_name)
                raise AssertionError(f"production code called {_name} on a render-time view")
            return _orig(self, *a, **k)
        monkeypatch.setattr(ir.DiagramIR, name, wrapper)
    for name in ("model_validate", "model_validate_json"):
        orig = getattr(ir.DiagramIR, name).__func__

        def vwrapper(cls, obj, *a, _orig=orig, _name=name, **k):
            if isinstance(obj, ir.DiagramIR) and _is_view(obj):
                seen.append(_name)
                raise AssertionError(f"production code called {_name} on a render-time view")
            return _orig(cls, obj, *a, **k)
        monkeypatch.setattr(ir.DiagramIR, name, classmethod(vwrapper))
    return seen


@pytest.mark.parametrize("build", [_stack, _prism, _recipe_stack])
def test_pipeline_and_both_renderers_never_dump_a_view(build, spy):
    d = build()
    result = asyncio.run(run_ir_pipeline(d, SVGRenderer()))
    assert "<svg" in result.svg
    sym = compile_defs(d)
    assert "<svg" in ir_to_svg(d, sym)
    assert ir_to_tikz(d, sym)
    assert spy == []


# --- the warning is documented ------------------------------------------------------

PHRASE = "internal render-time views"


def test_lowering_docstring_and_spec_carry_the_warning():
    from geometry_diagrams.ir.derived import Lowering, lower_render as lr
    assert PHRASE in re.sub(r"\s+", " ", Lowering.__doc__)
    assert PHRASE in re.sub(r"\s+", " ", lr.__doc__)
    spec = (ROOT / "docs" / "geometry-dsl-spec.md").read_text()
    section = spec.split("### Ordered polygons", 1)[1].split("\n### ", 1)[0]
    assert PHRASE in re.sub(r"\s+", " ", section)
