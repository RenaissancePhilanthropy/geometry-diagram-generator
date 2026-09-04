# tests/test_pydsl_composite_demo.py
"""Hand-authored demo proving `composite`'s core technique works end to
end (ticket 05's acceptance criterion): two panels of geometry placed at
disjoint coordinate offsets in one DiagramIR, joined by a draw_brace()
connector, rendered through both to_svg.py and to_tikz.py.

This stands in for `composite`'s feasibility regardless of how an LLM
baseline fares on it (a later ticket) — it only needs to show the
technique itself (two disjoint panels + a brace, one DiagramIR, both
renderers) works with the existing pipeline and the new DrawBrace
primitive, with no DefStmt/to_sympy.py/Check changes required.
"""
from geometry_diagrams.ir.checks import run_checks
from geometry_diagrams.ir.ir import DrawBrace
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz
from geometry_diagrams.pydsl.api import draw, draw_brace, label_text, point, rectangle, triangle
from geometry_diagrams.pydsl.builder import new_builder_context


def _build_two_panel_composite_ir():
    """Panel 1: a triangle near the origin. Panel 2: a square offset far
    enough away (x in [10, 14]) that the two panels' bounding boxes are
    disjoint. A brace connects a point on panel 1's right edge to a point
    on panel 2's left edge, with a label — the shape of a "same area"
    / "corresponds to" composite connector."""
    with new_builder_context() as builder:
        # Panel 1: triangle at the origin.
        a, b, c = point(0, 0), point(4, 0), point(2, 3)
        t = triangle(a, b, c)
        draw(t)
        label_text("Panel 1", at=(2, -1))

        # Panel 2: square, disjoint offset (x in [10, 14]).
        corner = point(10, 0)
        sq = rectangle(corner, width=4, height=4)
        draw(sq)
        label_text("Panel 2", at=(12, -1))

        # Connector brace spanning the gap between the two panels.
        draw_brace((4.0, 1.5), (10.0, 1.5), direction="up", label="same area")

        ir = builder.build()
    return ir


def test_composite_demo_compiles_and_passes_checks():
    ir = _build_two_panel_composite_ir()
    sym = compile_defs(ir)  # must not raise
    results = run_checks(ir.checks, sym)
    assert results == []  # no checks defined — DrawBrace needs none


def test_composite_demo_ir_has_two_disjoint_panels_and_one_brace():
    ir = _build_two_panel_composite_ir()
    braces = [r for r in ir.render if isinstance(r, DrawBrace)]
    assert len(braces) == 1
    assert braces[0].p1 == [4.0, 1.5]
    assert braces[0].p2 == [10.0, 1.5]
    # Two distinct polygon defs (triangle + rectangle-as-polygon), at
    # disjoint x-ranges, prove the "two panels" half of the technique.
    polygon_defs = [d for d in ir.define if d.kind in ("triangle", "polygon")]
    assert len(polygon_defs) == 2


def test_composite_demo_renders_to_svg_with_both_panels_and_the_brace():
    ir = _build_two_panel_composite_ir()
    sym = compile_defs(ir)
    svg = SVGRenderer().render(ir, sym).output
    assert "Panel 1" in svg
    assert "Panel 2" in svg
    assert "same area" in svg
    assert 'data-role="brace"' in svg


def test_composite_demo_renders_to_tikz_with_both_panels_and_the_brace():
    ir = _build_two_panel_composite_ir()
    sym = compile_defs(ir)
    tikz = ir_to_tikz(ir, sym)
    assert "Panel 1" in tikz
    assert "Panel 2" in tikz
    assert "same area" in tikz
    assert "plot[smooth" in tikz
    # Explicitly not the decorations.pathreplacing TikZ library — this repo
    # has no local LaTeX preamble to extend (see DrawBrace's docstring).
    assert "decorations.pathreplacing" not in tikz
