# tests/test_pydsl_end_to_end.py
"""Phase 1a exit criterion: a hand-written pydsl script exercising every
handle/op in the Task 0 scope table produces a DiagramIR that resolves via
the unchanged to_sympy.py/checks.py pipeline, and — for the triangle-based
portion of the scope table — resolves to the same side lengths as an
equivalent hand-authored DSL recipe.
"""
import math

from geometry_diagrams.pydsl.api import (
    altitude, circumcircle, incircle, line_through, mark_angle, median,
    point, polygon, triangle,
)
from geometry_diagrams.pydsl.builder import new_builder_context
from geometry_diagrams.pydsl.sandbox import run_script

from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.checks import run_checks

from geometry_diagrams.recipe.dsl import RecipeDSL, TriangleOp, TriangleSpec
from geometry_diagrams.recipe.lower import lower_to_ir

# Vertices chosen so the triangle's side lengths are exact, checkable values:
# AB = 4.0, BC = sqrt(18), CA = sqrt(10).
_SCRIPT_TEXT = """
a = point(0, 0)
b = point(4, 0)
c = point(1, 3)
t = triangle(a, b, c)
t.side(a, b)
t.angle_at(b)
circ = circumcircle(t)
circ.center
inc = incircle(t)
inc.center
alt = altitude(t, from_vertex=a)
alt.foot
med = median(t, from_vertex=b)
med.midpoint
d = point(0, 0)
e = point(2, 0)
f = point(2, 2)
g = point(0, 2)
square = polygon(d, e, f, g)
square.side(d, e)
ref = square.angle_at(e)
mark_angle(ref, group=1)
line_through(a, b)
"""


def _build_pydsl_script_ir():
    with new_builder_context() as builder:
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        t.side(a, b)
        t.angle_at(b)
        circ = circumcircle(t)
        _ = circ.center
        inc = incircle(t)
        _ = inc.center
        alt = altitude(t, from_vertex=a)
        _ = alt.foot
        med = median(t, from_vertex=b)
        _ = med.midpoint
        d, e = point(0, 0), point(2, 0)
        f, g = point(2, 2), point(0, 2)
        square = polygon(d, e, f, g)
        square.side(d, e)
        ref = square.angle_at(e)
        mark_angle(ref, group=1)
        line_through(a, b)
        ir = builder.build()
    return ir, (a, b, c)


def _build_equivalent_dsl_triangle_ir():
    # The DSL-side comparison covers the triangle-anchored portion of the
    # scope table (Triangle, Segment, Circle, Altitude, Median) — the part
    # where "equivalent DSL construction" is a direct, unambiguous
    # translation. The polygon/mark_angle portion is exercised separately
    # by tests/test_pydsl_polygon.py and tests/test_pydsl_angle.py's own
    # unit tests; duplicating it here as a second DSL comparison wouldn't
    # add coverage beyond what those already assert.
    #
    # TriangleSpec() with no fields is NOT valid — solve_triangle raises
    # (verified against recipe/solve.py: it needs enough constraints to fix
    # the triangle, e.g. three sides). Use the exact SSS side lengths of the
    # pydsl triangle at (0,0)/(4,0)/(1,3) so the two constructions are
    # actually comparable, not just independently valid.
    dsl = RecipeDSL(construction=[
        TriangleOp(
            id="T", vertices=["A", "B", "C"],
            spec=TriangleSpec(side_AB=4.0, side_BC=math.sqrt(18), side_CA=math.sqrt(10)),
        ),
    ])
    ir = lower_to_ir(dsl)
    return ir


def test_pydsl_script_compiles_without_error():
    ir, _ = _build_pydsl_script_ir()
    sym = compile_defs(ir)  # must not raise
    results = run_checks(ir.checks, sym)
    assert results == []  # no checks are created in Phase 1a scope — see note above


def test_pydsl_triangle_side_lengths_match_equivalent_dsl_recipe():
    pydsl_ir, (a, b, c) = _build_pydsl_script_ir()
    pydsl_sym = compile_defs(pydsl_ir)
    pydsl_ab = float(pydsl_sym[a.id].distance(pydsl_sym[b.id]).evalf())
    pydsl_bc = float(pydsl_sym[b.id].distance(pydsl_sym[c.id]).evalf())
    pydsl_ca = float(pydsl_sym[c.id].distance(pydsl_sym[a.id]).evalf())

    dsl_ir = _build_equivalent_dsl_triangle_ir()
    dsl_sym = compile_defs(dsl_ir)
    dsl_ab = float(dsl_sym["A"].distance(dsl_sym["B"]).evalf())
    dsl_bc = float(dsl_sym["B"].distance(dsl_sym["C"]).evalf())
    dsl_ca = float(dsl_sym["C"].distance(dsl_sym["A"]).evalf())

    # The actual equivalence claim: both surfaces, given the same triangle
    # (same three side lengths), resolve to the same geometry through the
    # unchanged to_sympy.py — not just "both happen to produce some triangle."
    assert math.isclose(pydsl_ab, dsl_ab, abs_tol=1e-9)
    assert math.isclose(pydsl_bc, dsl_bc, abs_tol=1e-9)
    assert math.isclose(pydsl_ca, dsl_ca, abs_tol=1e-9)


def test_pydsl_script_covers_every_scope_table_kind():
    ir, _ = _build_pydsl_script_ir()
    kinds = {d.kind for d in ir.define}
    expected_kinds = {
        "point_fixed", "triangle", "segment", "point_triangle_center",
        "circle_center_point", "circle_center_radius", "line_perp_through",
        "point_foot", "point_midpoint", "polygon", "line_through",
    }
    missing = expected_kinds - kinds
    assert not missing, f"scope table kinds not exercised: {missing}"


def test_pydsl_script_runs_through_the_real_sandbox_end_to_end():
    # This is the one test in the whole plan that runs .side()/.angle_at()
    # through the actual LocalPythonExecutor path, not the direct
    # new_builder_context() path every other test uses — see this task's
    # Interfaces note on why that distinction matters.
    result = run_script(_SCRIPT_TEXT, timeout_seconds=10.0)
    assert result.error is None, result.error
    assert result.diagram_ir is not None
    kinds = {d.kind for d in result.diagram_ir.define}
    assert "segment" in kinds  # only reachable via t.side()/square.side()


def test_pydsl_labels_render_as_svg_text():
    from geometry_diagrams.pydsl.api import draw, draw_points, label_text, segment
    from geometry_diagrams.ir.renderer import SVGRenderer

    with new_builder_context() as builder:
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        a.label("Q")
        s = segment(a, b)
        s.label("RAD")
        label_text("T", centroid_of=t)
        draw(t)
        draw(s)
        draw_points(a, b, c)
        ir = builder.build()

    sym = compile_defs(ir)
    result = SVGRenderer().render(ir, sym)
    svg = result.output
    for expected_text in ("Q", "RAD", "T"):
        assert expected_text in svg, f"expected label {expected_text!r} not found in rendered SVG"
