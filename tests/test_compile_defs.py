"""
Unit tests for ir/to_sympy.py compile_defs.
No Docker or renderer required — pure Python / SymPy logic.
"""
from __future__ import annotations

import math
from random import Random

import pytest
import sympy as sp
import sympy.geometry as spg

from ir.ir import (
    Canvas, Params,
    DiagramIR,
    PointFixed, PointFree, PointOn, PointMidpoint, PointRotate, PointReflect,
    PointTriangleCenter, PointIntersection, PointBetween,
    Segment, Ray,
    LineThrough, LineParallelThrough, LinePerpendicularThrough,
    LineAngleBisector, LineTangent,
    CircleCenterPoint, CircleCenterRadius, CircleThrough3,
    Triangle, Polygon,
    PointOnParam, PointOnRandom,
    PickIndex, PickClosestTo, PickOnObject,
)
from ir.to_sympy import compile_defs
from ir.errors import UndefinedRefError, IntersectionError, PickError, ExprEvalError

# Import the scenario registry populated at module load time
import ir.test_scenarios as _ts
SCENARIOS = _ts.SCENARIOS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compile(*stmts, **kwargs) -> dict:
    """Compile a DiagramIR built from the given define statements."""
    return compile_defs(DiagramIR(define=list(stmts), **kwargs))


def approx(a, b, tol=1e-9) -> bool:
    return abs(float(a) - float(b)) < tol


# ---------------------------------------------------------------------------
# 1. Basic definitions
# ---------------------------------------------------------------------------

def test_point_fixed():
    sym = _compile(PointFixed(id="A", x=3, y=4))
    assert isinstance(sym["A"], spg.Point)
    assert sym["A"] == spg.Point(3, 4)


def test_point_fixed_str_expr():
    sym = _compile(PointFixed(id="A", x="2+1", y="sqrt(2)"))
    assert sym["A"].x == sp.Integer(3)
    assert sym["A"].y == sp.sqrt(2)


def test_point_free_with_hint():
    sym = _compile(PointFree(id="P", hint_xy=(1.0, 2.0)))
    assert approx(sym["P"].x, 1.0)
    assert approx(sym["P"].y, 2.0)


def test_point_free_random_within_canvas():
    canvas = Canvas(xmin=-5, xmax=5, ymin=-5, ymax=5)
    sym = compile_defs(
        DiagramIR(define=[PointFree(id="P")], canvas=canvas),
        rng=Random(0),
    )
    x, y = float(sym["P"].x), float(sym["P"].y)
    assert -5 <= x <= 5
    assert -5 <= y <= 5


def test_segment():
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=3, y=0),
        Segment(id="s", a="A", b="B"),
    )
    assert isinstance(sym["s"], spg.Segment)
    assert sym["s"].length == sp.Integer(3)


def test_ray():
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=1, y=0),
        Ray(id="r", a="A", b="B"),
    )
    assert isinstance(sym["r"], spg.Ray)


def test_line_through():
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=1, y=1),
        LineThrough(id="l", p="A", q="B"),
    )
    assert isinstance(sym["l"], spg.Line)


def test_triangle():
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        PointFixed(id="C", x=0, y=3),
        Triangle(id="T", a="A", b="B", c="C"),
    )
    assert isinstance(sym["T"], spg.Triangle)


def test_polygon():
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=2, y=0),
        PointFixed(id="C", x=2, y=2),
        PointFixed(id="D", x=0, y=2),
        Polygon(id="sq", points=["A", "B", "C", "D"]),
    )
    assert isinstance(sym["sq"], spg.Polygon)


# ---------------------------------------------------------------------------
# 2. Derived points
# ---------------------------------------------------------------------------

def test_point_between_float_ratio():
    """ratio=0.25 → 1/4 of the way from A to B."""
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        PointBetween(id="D", a="A", b="B", ratio=0.25),
    )
    assert approx(sym["D"].x, 1.0)
    assert approx(sym["D"].y, 0.0)


def test_point_between_string_ratio():
    """'1:2' → 1/(1+2) = 1/3 from A to B."""
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=3, y=0),
        PointBetween(id="D", a="A", b="B", ratio="1:2"),
    )
    assert approx(sym["D"].x, 1.0)
    assert approx(sym["D"].y, 0.0)


def test_point_between_default_midpoint():
    """ratio=None defaults to 0.5 (midpoint)."""
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        PointBetween(id="M", a="A", b="B"),
    )
    assert approx(sym["M"].x, 2.0)
    assert approx(sym["M"].y, 0.0)


def test_point_between_diagonal():
    """Works for non-axis-aligned segments."""
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=4),
        PointBetween(id="D", a="A", b="B", ratio=0.5),
    )
    assert approx(sym["D"].x, 2.0)
    assert approx(sym["D"].y, 2.0)

def test_point_midpoint():
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        Segment(id="s", a="A", b="B"),
        PointMidpoint(id="M", p="A", q="B"),
    )
    assert sym["M"] == spg.Point(2, 0)


def test_point_rotate_numeric():
    sym = _compile(
        PointFixed(id="O", x=0, y=0),
        PointFixed(id="P", x=1, y=0),
        PointRotate(id="R", center="O", source="P", angle=math.pi / 2),
    )
    assert approx(sym["R"].x, 0.0)
    assert approx(sym["R"].y, 1.0)


def test_point_rotate_str_angle():
    sym = _compile(
        PointFixed(id="O", x=0, y=0),
        PointFixed(id="P", x=1, y=0),
        PointRotate(id="R", center="O", source="P", angle="pi/2"),
    )
    # symbolic rotation: x component is cos(pi/2) = 0
    assert sym["R"].x.simplify() == sp.Integer(0)
    assert sym["R"].y.simplify() == sp.Integer(1)


def test_point_triangle_center_circumcenter():
    # Right triangle: circumcenter is midpoint of hypotenuse
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        PointFixed(id="C", x=0, y=3),
        Triangle(id="T", a="A", b="B", c="C"),
        PointTriangleCenter(id="O", tri="T", which="circumcenter"),
    )
    assert approx(sym["O"].x, 2.0)
    assert approx(sym["O"].y, 1.5)


def test_point_triangle_center_centroid():
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=6, y=0),
        PointFixed(id="C", x=0, y=3),
        Triangle(id="T", a="A", b="B", c="C"),
        PointTriangleCenter(id="G", tri="T", which="centroid"),
    )
    assert approx(sym["G"].x, 2.0)
    assert approx(sym["G"].y, 1.0)


def test_point_triangle_center_all():
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        PointFixed(id="C", x=1, y=3),
        Triangle(id="T", a="A", b="B", c="C"),
        PointTriangleCenter(id="Oc", tri="T", which="circumcenter"),
        PointTriangleCenter(id="I", tri="T", which="incenter"),
        PointTriangleCenter(id="G", tri="T", which="centroid"),
        PointTriangleCenter(id="H", tri="T", which="orthocenter"),
    )
    for key in ("Oc", "I", "G", "H"):
        assert isinstance(sym[key], spg.Point), f"{key} should be a Point"


# ---------------------------------------------------------------------------
# 3. Lines
# ---------------------------------------------------------------------------

def test_line_parallel_through():
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=1, y=0),
        LineThrough(id="l_AB", p="A", q="B"),
        PointFixed(id="P", x=0, y=2),
        LineParallelThrough(id="l_par", through="P", to_line="l_AB"),
    )
    # Parallel to x-axis through (0,2): every point has y=2
    l = sym["l_par"]
    assert l.contains(spg.Point(5, 2))
    assert not l.contains(spg.Point(5, 0))


def test_line_perpendicular_through():
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=1, y=0),
        LineThrough(id="l_AB", p="A", q="B"),
        PointFixed(id="P", x=2, y=0),
        LinePerpendicularThrough(id="l_perp", through="P", to_line="l_AB"),
    )
    # Perpendicular to x-axis through (2,0): x=2
    l = sym["l_perp"]
    assert l.contains(spg.Point(2, 5))
    assert not l.contains(spg.Point(3, 5))


def test_line_angle_bisector():
    # 90-degree angle at origin, legs along negative x and positive y
    sym = _compile(
        PointFixed(id="A", x=-1, y=0),
        PointFixed(id="V", x=0, y=0),
        PointFixed(id="B", x=0, y=1),
        LineAngleBisector(id="bis", a="A", vertex="V", b="B"),
    )
    l = sym["bis"]
    assert isinstance(l, spg.Line)
    assert l.contains(spg.Point(0, 0))
    # Bisector of this 90-degree angle goes through (-1, 1) direction
    assert l.contains(spg.Point(-1, 1))


# ---------------------------------------------------------------------------
# 4. Circles
# ---------------------------------------------------------------------------

def test_circle_center_point():
    sym = _compile(
        PointFixed(id="O", x=0, y=0),
        PointFixed(id="P", x=3, y=0),
        CircleCenterPoint(id="c", center="O", through="P"),
    )
    assert isinstance(sym["c"], spg.Circle)
    assert sym["c"].radius == sp.Integer(3)


def test_circle_center_radius():
    sym = _compile(
        PointFixed(id="O", x=1, y=2),
        CircleCenterRadius(id="c", center="O", radius=5),
    )
    assert sym["c"].radius == sp.Integer(5)
    assert sym["c"].center == spg.Point(1, 2)


def test_circle_through3():
    # Three points on a circle of radius 1 centered at origin
    sym = _compile(
        PointFixed(id="A", x=1, y=0),
        PointFixed(id="B", x=0, y=1),
        PointFixed(id="C", x=-1, y=0),
        CircleThrough3(id="c", a="A", b="B", c="C"),
    )
    assert isinstance(sym["c"], spg.Circle)
    assert sym["c"].center == spg.Point(0, 0)
    assert sym["c"].radius == sp.Integer(1)


# ---------------------------------------------------------------------------
# 5. PointOn — parametric placement
# ---------------------------------------------------------------------------

def test_point_on_segment_start():
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        Segment(id="s", a="A", b="B"),
        PointOn(id="P", on="s", how=PointOnParam(t=0)),
    )
    assert sym["P"] == spg.Point(0, 0)


def test_point_on_segment_end():
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        Segment(id="s", a="A", b="B"),
        PointOn(id="P", on="s", how=PointOnParam(t=1)),
    )
    assert sym["P"] == spg.Point(4, 0)


def test_point_on_segment_midpoint():
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        Segment(id="s", a="A", b="B"),
        PointOn(id="P", on="s", how=PointOnParam(t=0.5)),
    )
    assert sym["P"] == spg.Point(2, 0)


def test_point_on_segment_beyond():
    # t=1.5 extends 50% past endpoint — used for exterior-angle construction
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=2, y=0),
        Segment(id="s", a="A", b="B"),
        PointOn(id="D", on="s", how=PointOnParam(t=1.5)),
    )
    assert approx(sym["D"].x, 3.0)
    assert approx(sym["D"].y, 0.0)


def test_point_on_circle_zero():
    sym = _compile(
        PointFixed(id="O", x=0, y=0),
        CircleCenterRadius(id="c", center="O", radius=3),
        PointOn(id="P", on="c", how=PointOnParam(t=0)),
    )
    assert approx(sym["P"].x, 3.0)
    assert approx(sym["P"].y, 0.0)


def test_point_on_circle_quarter():
    sym = _compile(
        PointFixed(id="O", x=0, y=0),
        CircleCenterRadius(id="c", center="O", radius=3),
        PointOn(id="P", on="c", how=PointOnParam(t=math.pi / 2)),
    )
    assert approx(sym["P"].x, 0.0)
    assert approx(sym["P"].y, 3.0)


def test_point_on_ray_param():
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=1, y=0),
        Ray(id="r", a="A", b="B"),
        PointOn(id="P", on="r", how=PointOnParam(t=0.5)),
    )
    assert isinstance(sym["P"], spg.Point)


def test_point_on_random_deterministic():
    diag = DiagramIR(define=[
        PointFixed(id="O", x=0, y=0),
        CircleCenterRadius(id="c", center="O", radius=1),
        PointOn(id="P", on="c", how=PointOnRandom()),
    ])
    sym1 = compile_defs(diag, rng=Random(7))
    sym2 = compile_defs(diag, rng=Random(7))
    assert approx(sym1["P"].x, sym2["P"].x)
    assert approx(sym1["P"].y, sym2["P"].y)


# ---------------------------------------------------------------------------
# 6. Intersections and pick rules
# ---------------------------------------------------------------------------

def test_intersection_line_line_unique():
    # y=x and y=2-x intersect at (1,1)
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=2, y=2),
        LineThrough(id="l1", p="A", q="B"),
        PointFixed(id="C", x=0, y=2),
        PointFixed(id="D", x=2, y=0),
        LineThrough(id="l2", p="C", q="D"),
        PointIntersection(id="P", obj1="l1", obj2="l2"),
    )
    assert sym["P"] == spg.Point(1, 1)


def test_intersection_line_circle_pick_index():
    # Horizontal line y=0 intersects unit circle at (-1,0) and (1,0)
    sym0 = _compile(
        PointFixed(id="O", x=0, y=0),
        CircleCenterRadius(id="c", center="O", radius=1),
        PointFixed(id="L", x=-2, y=0),
        PointFixed(id="R", x=2, y=0),
        LineThrough(id="l", p="L", q="R"),
        PointIntersection(id="P", obj1="l", obj2="c", pick=PickIndex(k=0)),
    )
    sym1 = _compile(
        PointFixed(id="O", x=0, y=0),
        CircleCenterRadius(id="c", center="O", radius=1),
        PointFixed(id="L", x=-2, y=0),
        PointFixed(id="R", x=2, y=0),
        LineThrough(id="l", p="L", q="R"),
        PointIntersection(id="P", obj1="l", obj2="c", pick=PickIndex(k=1)),
    )
    p0, p1 = sym0["P"], sym1["P"]
    assert p0 != p1
    assert {approx(p0.x, -1) or approx(p0.x, 1), approx(p1.x, -1) or approx(p1.x, 1)}


def test_pick_closest_to():
    sym = _compile(
        PointFixed(id="O", x=0, y=0),
        CircleCenterRadius(id="c", center="O", radius=1),
        PointFixed(id="L", x=-2, y=0),
        PointFixed(id="R", x=2, y=0),
        LineThrough(id="l", p="L", q="R"),
        PointFixed(id="ref", x=2, y=0),  # close to (1,0)
        PointIntersection(id="P", obj1="l", obj2="c", pick=PickClosestTo(p="ref")),
    )
    assert approx(sym["P"].x, 1.0)


def test_pick_on_object():
    # Circle-line intersects at (-1,0) and (1,0); pick the one on the segment [0,2]-[2,0] side
    sym = _compile(
        PointFixed(id="O", x=0, y=0),
        CircleCenterRadius(id="c", center="O", radius=1),
        PointFixed(id="L", x=-2, y=0),
        PointFixed(id="R", x=2, y=0),
        LineThrough(id="l", p="L", q="R"),
        PointFixed(id="segA", x=0, y=0),
        PointFixed(id="segB", x=2, y=0),
        Segment(id="s", a="segA", b="segB"),
        PointIntersection(id="P", obj1="l", obj2="c", pick=PickOnObject(obj="s")),
    )
    # (1,0) lies on segment [0,0]-[2,0]; (-1,0) does not
    assert approx(sym["P"].x, 1.0)


# ---------------------------------------------------------------------------
# 7. LineTangent
# ---------------------------------------------------------------------------

def test_line_tangent():
    sym = _compile(
        PointFixed(id="O", x=0, y=0),
        CircleCenterRadius(id="c", center="O", radius=1),
        PointFixed(id="P", x=3, y=0),
        LineTangent(id="t", point="P", circle="c", pick=PickIndex(k=0)),
    )
    tang = sym["t"]
    assert isinstance(tang, spg.Line)
    assert tang.contains(spg.Point(3, 0))


# ---------------------------------------------------------------------------
# 8. Error cases
# ---------------------------------------------------------------------------

def test_undefined_ref():
    with pytest.raises(UndefinedRefError):
        _compile(Segment(id="s", a="missing_A", b="missing_B"))


def test_no_intersection_parallel_lines():
    with pytest.raises(IntersectionError):
        _compile(
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=1, y=0),
            LineThrough(id="l1", p="A", q="B"),
            PointFixed(id="C", x=0, y=1),
            PointFixed(id="D", x=1, y=1),
            LineThrough(id="l2", p="C", q="D"),
            PointIntersection(id="P", obj1="l1", obj2="l2"),
        )


def test_ambiguous_pick_no_rule():
    with pytest.raises(PickError):
        _compile(
            PointFixed(id="O", x=0, y=0),
            CircleCenterRadius(id="c", center="O", radius=1),
            PointFixed(id="L", x=-2, y=0),
            PointFixed(id="R", x=2, y=0),
            LineThrough(id="l", p="L", q="R"),
            PointIntersection(id="P", obj1="l", obj2="c"),  # no pick, 2 candidates
        )


def test_bad_expr():
    with pytest.raises(ExprEvalError):
        _compile(PointFixed(id="A", x="not_valid!!!@#", y=0))


# ---------------------------------------------------------------------------
# 9. Full scenario round-trips
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario_id,diagram", SCENARIOS, ids=[s for s, _ in SCENARIOS])
def test_scenario_compiles(scenario_id: str, diagram: DiagramIR):
    sym = compile_defs(diagram)
    assert isinstance(sym, dict)
    assert len(sym) == len(diagram.define), (
        f"{scenario_id}: expected {len(diagram.define)} objects, got {len(sym)}"
    )


# ---------------------------------------------------------------------------
# 10. PointReflect
# ---------------------------------------------------------------------------

def test_point_reflect_across_point():
    """Reflection of A=(1,2) across O=(3,3) should be (5,4)."""
    sym = _compile(
        PointFixed(id="A", x=1, y=2),
        PointFixed(id="O", x=3, y=3),
        PointReflect(id="A_prime", source="A", across="O"),
    )
    assert approx(sym["A_prime"].x, 5.0)
    assert approx(sym["A_prime"].y, 4.0)


def test_point_reflect_across_line():
    """Reflection of A=(2,0) across the y-axis (x=0) should be (-2,0)."""
    sym = _compile(
        PointFixed(id="A", x=2, y=0),
        PointFixed(id="P", x=0, y=0),
        PointFixed(id="Q", x=0, y=1),
        LineThrough(id="y_axis", p="P", q="Q"),
        PointReflect(id="A_prime", source="A", across="y_axis"),
    )
    assert approx(sym["A_prime"].x, -2.0)
    assert approx(sym["A_prime"].y, 0.0)


def test_point_reflect_across_segment():
    """Reflection across a segment should use the underlying line."""
    sym = _compile(
        PointFixed(id="A", x=0, y=2),
        PointFixed(id="P", x=0, y=0),
        PointFixed(id="Q", x=4, y=0),
        Segment(id="seg", a="P", b="Q"),
        PointReflect(id="A_prime", source="A", across="seg"),
    )
    assert approx(sym["A_prime"].x, 0.0)
    assert approx(sym["A_prime"].y, -2.0)


# ---------------------------------------------------------------------------
# 11. Params
# ---------------------------------------------------------------------------

def test_params_assign():
    diag = DiagramIR(
        params=Params(assign={"a": 3}),
        define=[PointFixed(id="P", x="a", y="a+1")],
    )
    sym = compile_defs(diag)
    assert sym["P"].x == sp.Integer(3)
    assert sym["P"].y == sp.Integer(4)
