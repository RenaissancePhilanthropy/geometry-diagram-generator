"""Regression tests for the solids final-review fix wave (items A-E): typed
style-conflict error, recipe segment reuse of prism edges, pre-assert stub
features, the unit_cubes not-drawn warning and guidance, and non-finite prism
dimensions."""
from __future__ import annotations

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.derived import effective_diagram, lower_render
from geometry_diagrams.ir.errors import IRCompileError
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline


def _prism(**overrides) -> ir.RectangularPrism:
    fields = dict(id="P", origin="O", length=4, width=3, height=2)
    fields.update(overrides)
    return ir.RectangularPrism(**fields)


def _diagram(prism=None, render=None, styles=None) -> ir.DiagramIR:
    return ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=0, y=0), prism or _prism()],
        render=render if render is not None else [ir.Draw(obj="P")],
        styles=styles or {},
    )


# --- A: style-name conflict is a typed, retry-feedable error ---------------

_CONFLICT = {"__P_hidden": {"color": "red"}}


def test_lowering_style_conflict_is_an_ir_compile_error_naming_the_style():
    diagram = _diagram(styles=_CONFLICT)
    with pytest.raises(IRCompileError) as exc:
        lower_render(effective_diagram(diagram))
    assert exc.value.def_id == "P"
    assert "__P_hidden" in str(exc.value)


@pytest.mark.asyncio
async def test_lowering_style_conflict_reaches_the_shared_pipeline_typed():
    diagram = _diagram(styles=_CONFLICT)
    with pytest.raises(IRCompileError):
        await run_ir_pipeline(diagram, SVGRenderer())


# --- B: a recipe `segment` op along one prism edge reuses that edge ---------

from geometry_diagrams.ir.to_sympy import compile_defs  # noqa: E402
from geometry_diagrams.ir.to_svg import ir_to_svg  # noqa: E402
from geometry_diagrams.recipe.dsl import RecipeDSL  # noqa: E402
from geometry_diagrams.recipe.lower import lower_to_ir  # noqa: E402


def _recipe(extra_ops=(), annotations=None, prism=None) -> RecipeDSL:
    p = {"op": "prism", "id": "P", "origin": "O", "length": 4, "width": 3, "height": 2}
    p.update(prism or {})
    return RecipeDSL.model_validate({
        "construction": [{"op": "point", "id": "O", "coords": [0, 0]}, p, *extra_ops],
        "annotations": annotations or {},
    })


def _svg(diagram: ir.DiagramIR) -> str:
    return ir_to_svg(diagram, compile_defs(diagram))


def _segments_between(diagram, p, q):
    return [d for d in diagram.define if isinstance(d, ir.Segment) and {d.a, d.b} == {p, q}]


_EDGE_SEG = {"op": "segment", "id": "s", "endpoints": ["P_v000", "P_v010"]}


def test_segment_op_along_a_prism_edge_adds_no_segment_and_no_stroke():
    with_seg = lower_to_ir(_recipe([_EDGE_SEG]))
    without = lower_to_ir(_recipe())
    assert _segments_between(with_seg, "P_v000", "P_v010") == []
    assert not any(isinstance(r, ir.Draw) and r.obj == "s" for r in with_seg.render)
    assert with_seg.render == without.render
    assert _svg(with_seg) == _svg(without)


def test_segment_op_along_an_edge_still_resolves_when_another_op_references_it():
    # Intersection of the edge-segment s (bottom front edge, y=0) with a line.
    d = lower_to_ir(_recipe([
        {"op": "segment", "id": "s", "endpoints": ["P_v000", "P_v100"]},
        {"op": "point", "id": "Q1", "coords": [2, -1]},
        {"op": "point", "id": "Q2", "coords": [2, 1]},
        {"op": "line_through", "id": "L", "points": ["Q1", "Q2"]},
        {"op": "intersection", "id": "X", "of": ["s", "L"]},
    ]))
    sym = compile_defs(d)
    assert (float(sym["X"].x), float(sym["X"].y)) == pytest.approx((2.0, 0.0))
    assert not any(isinstance(r, ir.Draw) and r.obj == "s" for r in d.render)


def test_explicit_draw_of_an_edge_segment_op_draws_the_prism_edge():
    d = lower_to_ir(_recipe([_EDGE_SEG], annotations={
        "auto_draw_all": False,
        "draws": [{"obj": "P"}, {"obj": "s", "style": "red"}],
    }))
    draws = [(r.obj, r.style) for r in d.render if isinstance(r, ir.Draw)]
    assert ("P_e_000_010", "red") in draws
    assert not any(obj == "s" for obj, _ in draws)
    compile_defs(d)


def test_edge_segment_op_is_drawn_as_the_edge_when_its_prism_is_hidden():
    d = lower_to_ir(_recipe([_EDGE_SEG], prism={"visible": False}))
    draws = [r.obj for r in d.render if isinstance(r, ir.Draw)]
    assert "P" not in draws and "P_e_000_010" in draws


def test_diagonal_and_non_prism_segment_ops_are_unchanged():
    d = lower_to_ir(_recipe([
        {"op": "segment", "id": "diag", "endpoints": ["P_v000", "P_v111"]},
        {"op": "point", "id": "A", "coords": [6, 0]},
        {"op": "point", "id": "B", "coords": [7, 1]},
        {"op": "segment", "id": "ab", "endpoints": ["A", "B"]},
    ]))
    segs = {s.id: (s.a, s.b) for s in d.define if isinstance(s, ir.Segment)}
    assert segs == {"diag": ("P_v000", "P_v111"), "ab": ("A", "B")}
    draws = [r.obj for r in d.render if isinstance(r, ir.Draw)]
    assert "diag" in draws and "ab" in draws
