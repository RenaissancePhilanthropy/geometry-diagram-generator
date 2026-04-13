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
    PointFixed, PointFree, PointOn, PointMidpoint, PointFoot, PointRotate, PointReflect,
    PointTriangleCenter, PointIntersection, PointBetween,
    Segment, Ray,
    LineThrough, LineParallelThrough, LinePerpendicularThrough,
    LineAngleBisector, LineTangent,
    CircleCenterPoint, CircleCenterRadius, CircleThrough3,
    EllipseCenterAxes, EllipseBBox, EllipseFoci, EllipseCenterEccentricity,
    Triangle, Polygon, PolygonExterior,
    PointOnParam, PointOnRandom, PointOnIntent,
    SameSideConstraint, NotNearConstraint,
    PickIndex, PickClosestTo, PickOnObject,
)
from ir.to_sympy import compile_defs
from ir.errors import IRCompileError, UndefinedRefError, IntersectionError, PickError, ExprEvalError
from ir.auto_checks import generate_auto_checks, run_auto_checks

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


def test_point_between_fraction_string_ratio():
    """'1/3' fraction string → 1/3 of the way from A to B."""
    sym = _compile(
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=3, y=0),
        PointBetween(id="D", a="A", b="B", ratio="1/3"),
    )
    assert approx(sym["D"].x, 1.0)
    assert approx(sym["D"].y, 0.0)

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
# Ellipses
# ---------------------------------------------------------------------------

def test_ellipse_center_axes():
    sym = _compile(
        PointFixed(id="O", x=1, y=3),
        EllipseCenterAxes(id="E", center="O", hradius=1.5, vradius=2),
    )
    assert isinstance(sym["E"], spg.Ellipse)
    assert not isinstance(sym["E"], spg.Circle)
    assert approx(float(sym["E"].hradius), 1.5)
    assert approx(float(sym["E"].vradius), 2.0)
    assert sym["E"].center == spg.Point(1, 3)


def test_ellipse_bbox():
    sym = _compile(
        PointFixed(id="C1", x=0, y=1),
        PointFixed(id="C2", x=3, y=5),
        EllipseBBox(id="E", corner1="C1", corner2="C2"),
    )
    assert isinstance(sym["E"], spg.Ellipse)
    assert approx(float(sym["E"].center.x), 1.5)
    assert approx(float(sym["E"].center.y), 3.0)
    assert approx(float(sym["E"].hradius), 1.5)
    assert approx(float(sym["E"].vradius), 2.0)


def test_ellipse_foci_major_axis():
    # Ellipse with foci at (-3,0) and (3,0) and major_axis=10 (a=5, c=3, b=4)
    sym = _compile(
        PointFixed(id="F1", x=-3, y=0),
        PointFixed(id="F2", x=3, y=0),
        EllipseFoci(id="E", focus1="F1", focus2="F2", major_axis=10),
    )
    assert isinstance(sym["E"], spg.Ellipse)
    assert approx(float(sym["E"].center.x), 0.0)
    assert approx(float(sym["E"].center.y), 0.0)
    assert approx(float(sym["E"].hradius), 5.0)
    assert approx(float(sym["E"].vradius), 4.0)


def test_ellipse_foci_through_point():
    # Same ellipse but specified via a through-point at (5, 0)
    sym = _compile(
        PointFixed(id="F1", x=-3, y=0),
        PointFixed(id="F2", x=3, y=0),
        PointFixed(id="P", x=5, y=0),
        EllipseFoci(id="E", focus1="F1", focus2="F2", through="P"),
    )
    assert isinstance(sym["E"], spg.Ellipse)
    assert approx(float(sym["E"].hradius), 5.0)
    assert approx(float(sym["E"].vradius), 4.0)


def test_ellipse_foci_non_axis_aligned_raises():
    from ir.errors import IRCompileError
    with pytest.raises(IRCompileError, match="axis-aligned"):
        _compile(
            PointFixed(id="F1", x=0, y=0),
            PointFixed(id="F2", x=1, y=1),
            EllipseFoci(id="E", focus1="F1", focus2="F2", major_axis=4),
        )


def test_ellipse_center_eccentricity_horizontal():
    # a=5, e=0.6, b = 5*sqrt(1-0.36) = 5*sqrt(0.64) = 4
    sym = _compile(
        PointFixed(id="O", x=0, y=0),
        EllipseCenterEccentricity(id="E", center="O", semi_major=5, eccentricity=0.6, orientation="horizontal"),
    )
    assert isinstance(sym["E"], spg.Ellipse)
    assert approx(float(sym["E"].hradius), 5.0)
    assert approx(float(sym["E"].vradius), 4.0)


def test_ellipse_center_eccentricity_vertical():
    sym = _compile(
        PointFixed(id="O", x=0, y=0),
        EllipseCenterEccentricity(id="E", center="O", semi_major=5, eccentricity=0.6, orientation="vertical"),
    )
    assert isinstance(sym["E"], spg.Ellipse)
    assert approx(float(sym["E"].hradius), 4.0)
    assert approx(float(sym["E"].vradius), 5.0)


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
    # With auto-pick heuristic, no PickError is raised; one of the two
    # candidates is returned deterministically via centroid tiebreaker.
    sym = _compile(
        PointFixed(id="O", x=0, y=0),
        CircleCenterRadius(id="c", center="O", radius=1),
        PointFixed(id="L", x=-2, y=0),
        PointFixed(id="R", x=2, y=0),
        LineThrough(id="l", p="L", q="R"),
        PointIntersection(id="P", obj1="l", obj2="c"),  # no pick, uses auto-pick
    )
    P = sym["P"]
    assert isinstance(P, spg.Point)
    assert approx(P.y, 0.0)
    assert abs(abs(float(P.x)) - 1.0) < 1e-9


def test_auto_pick_line_circle_no_pick_rule():
    """With no pick rule and 2 intersection candidates, auto-pick should resolve
    to one candidate without raising PickError."""
    canvas = Canvas(xmin=-5, xmax=5, ymin=-5, ymax=5)
    sym = compile_defs(DiagramIR(
        canvas=canvas,
        define=[
            PointFixed(id="O", x=0, y=0),
            PointFixed(id="R", x=2, y=0),
            CircleCenterPoint(id="c", center="O", through="R"),
            PointFixed(id="P", x=0, y=-3),
            PointFixed(id="Q", x=0, y=3),
            LineThrough(id="l", p="P", q="Q"),
            # No pick rule — should use auto-pick heuristic
            PointIntersection(id="T", obj1="c", obj2="l"),
        ]
    ))
    T = sym["T"]
    # Should be one of (0, 2) or (0, -2)
    assert approx(T.x, 0.0)
    assert abs(abs(float(T.y)) - 2.0) < 1e-9


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
    # sym may have more entries than define when primitives register sub-points
    # (e.g. PolygonExterior registers {id}_v{i} for each vertex)
    assert len(sym) >= len(diagram.define), (
        f"{scenario_id}: expected at least {len(diagram.define)} objects, got {len(sym)}"
    )
    assert all(stmt.id in sym for stmt in diagram.define), (
        f"{scenario_id}: not all define IDs are in sym"
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


# ---------------------------------------------------------------------------
# 12. PointOnIntent — constraint-based placement
# ---------------------------------------------------------------------------

def test_point_on_intent_same_side():
    """PointOnIntent with same_side constraint: point on circle must be
    on the same side of the x-axis as reference point ref=(0,1)."""
    canvas = Canvas(xmin=-5, xmax=5, ymin=-5, ymax=5)
    sym = compile_defs(DiagramIR(
        canvas=canvas,
        define=[
            PointFixed(id="O", x=0, y=0),
            PointFixed(id="R", x=2, y=0),
            PointFixed(id="L", x=-2, y=0),
            LineThrough(id="x_axis", p="R", q="L"),
            CircleCenterPoint(id="c", center="O", through="R"),
            PointFixed(id="ref", x=0, y=1),  # above x-axis
            PointOn(id="P", on="c", how=PointOnIntent(constraints=[
                SameSideConstraint(line=["R", "L"], ref="ref"),
            ])),
        ]
    ), rng=Random(1))
    P = sym["P"]
    # P should be on the upper semicircle (y > 0)
    assert float(P.y) > 0


def test_point_on_intent_not_near():
    """PointOnIntent with not_near constraint."""
    canvas = Canvas(xmin=-5, xmax=5, ymin=-5, ymax=5)
    sym = compile_defs(DiagramIR(
        canvas=canvas,
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            Segment(id="s", a="A", b="B"),
            PointOn(id="D", on="s", how=PointOnIntent(constraints=[
                NotNearConstraint(point="A", min_dist=1.5),
            ])),
        ]
    ), rng=Random(0))
    D = sym["D"]
    d = math.sqrt(float(D.x)**2 + float(D.y)**2)
    assert d > 1.5


# ---------------------------------------------------------------------------
# 13. Auto-checks
# ---------------------------------------------------------------------------

def test_auto_checks_intersection_contains():
    """Auto-checks for PointIntersection verify containment on both parents."""
    diag = DiagramIR(define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        PointFixed(id="C", x=2, y=-2),
        PointFixed(id="D", x=2, y=2),
        Segment(id="s_AB", a="A", b="B"),
        Segment(id="s_CD", a="C", b="D"),
        PointIntersection(id="I", obj1="s_AB", obj2="s_CD"),
    ])
    sym = compile_defs(diag)
    checks = generate_auto_checks(diag)
    # Should have 2 contains checks (I on s_AB and I on s_CD)
    assert len([c for c in checks if c.kind == "contains"]) == 2
    results = run_auto_checks(diag, sym)
    assert all(r.passed for r in results), [r.message for r in results if not r.passed]


def test_auto_checks_foot_contains():
    """Auto-checks for PointFoot verify foot lies on the target line."""
    diag = DiagramIR(define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        PointFixed(id="C", x=2, y=3),
        LineThrough(id="l_AB", p="A", q="B"),
        PointFoot(id="H", source="C", onto="l_AB"),
    ])
    sym = compile_defs(diag)
    results = run_auto_checks(diag, sym)
    assert all(r.passed for r in results)


# ---------------------------------------------------------------------------
# PolygonExterior
# ---------------------------------------------------------------------------

def _cross_sign_float(ax, ay, bx, by, px, py) -> float:
    """Sign of cross product (b-a) x (p-a)."""
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)


class TestPolygonExterior:
    """Verify PolygonExterior places the polygon on the exterior side of the edge."""

    def _square_on_edge(self, a, b, ref):
        """Compile a square on edge a-b, exterior to ref point."""
        stmts = [
            PointFixed(id="A", x=a[0], y=a[1]),
            PointFixed(id="B", x=b[0], y=b[1]),
            PointFixed(id="C", x=ref[0], y=ref[1]),
            PolygonExterior(id="sq", a="A", b="B", ref="C", sides=4),
        ]
        return compile_defs(DiagramIR(define=stmts))

    def test_square_returns_polygon(self):
        sym = self._square_on_edge((0, 0), (1, 0), (0.5, 1))
        assert isinstance(sym["sq"], spg.Polygon)

    def test_square_has_four_vertices(self):
        sym = self._square_on_edge((0, 0), (1, 0), (0.5, 1))
        assert len(sym["sq"].vertices) == 4

    def test_sub_points_registered(self):
        sym = self._square_on_edge((0, 0), (1, 0), (0.5, 1))
        for i in range(4):
            assert f"sq_v{i}" in sym, f"sq_v{i} not in sym"
        assert isinstance(sym["sq_v2"], spg.Point)
        assert isinstance(sym["sq_v3"], spg.Point)

    def test_exterior_vertices_opposite_side_from_ref(self):
        """New vertices (v2, v3) must be on opposite side of edge AB from ref C."""
        a, b, ref = (0.0, 0.0), (1.0, 0.0), (0.5, 1.0)
        sym = self._square_on_edge(a, b, ref)
        ax, ay = a
        bx, by = b
        ref_sign = _cross_sign_float(ax, ay, bx, by, ref[0], ref[1])
        for i in (2, 3):
            vx = float(sym[f"sq_v{i}"].x.evalf())
            vy = float(sym[f"sq_v{i}"].y.evalf())
            v_sign = _cross_sign_float(ax, ay, bx, by, vx, vy)
            assert ref_sign * v_sign < 0, f"sq_v{i} is on same side as ref (wrong side)"

    def test_exterior_opposite_winding_ccw(self):
        """Works for CCW-wound triangle: ref below edge."""
        a, b, ref = (0.0, 0.0), (1.0, 0.0), (0.5, -1.0)
        sym = self._square_on_edge(a, b, ref)
        ax, ay = a
        bx, by = b
        ref_sign = _cross_sign_float(ax, ay, bx, by, ref[0], ref[1])
        for i in (2, 3):
            vx = float(sym[f"sq_v{i}"].x.evalf())
            vy = float(sym[f"sq_v{i}"].y.evalf())
            v_sign = _cross_sign_float(ax, ay, bx, by, vx, vy)
            assert ref_sign * v_sign < 0, f"sq_v{i} is on same side as ref (wrong side)"

    def test_pythagorean_all_squares_exterior(self):
        """All three squares on the Pythagorean right triangle are on the exterior."""
        stmts = [
            PointFixed(id="A", x=0, y=3),
            PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=0, y=0),
            PolygonExterior(id="sq_AB", a="A", b="B", ref="C", sides=4),
            PolygonExterior(id="sq_AC", a="A", b="C", ref="B", sides=4),
            PolygonExterior(id="sq_BC", a="B", b="C", ref="A", sides=4),
        ]
        sym = compile_defs(DiagramIR(define=stmts))
        for sq_id, (ax, ay), (bx, by), (refx, refy) in [
            ("sq_AB", (0, 3), (4, 0), (0, 0)),
            ("sq_AC", (0, 3), (0, 0), (4, 0)),
            ("sq_BC", (4, 0), (0, 0), (0, 3)),
        ]:
            ref_sign = _cross_sign_float(ax, ay, bx, by, refx, refy)
            for i in (2, 3):
                vx = float(sym[f"{sq_id}_v{i}"].x.evalf())
                vy = float(sym[f"{sq_id}_v{i}"].y.evalf())
                v_sign = _cross_sign_float(ax, ay, bx, by, vx, vy)
                assert ref_sign * v_sign < 0, (
                    f"{sq_id}_v{i} is on same side as ref — square is interior, not exterior"
                )

    def test_ref_on_line_raises(self):
        from ir.errors import IRCompileError
        stmts = [
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=2, y=0),
            PointFixed(id="C", x=1, y=0),  # C is on line AB
            PolygonExterior(id="sq", a="A", b="B", ref="C", sides=4),
        ]
        with pytest.raises(IRCompileError):
            compile_defs(DiagramIR(define=stmts))

    def test_sides_less_than_3_raises(self):
        from ir.errors import IRCompileError
        stmts = [
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=1, y=0),
            PointFixed(id="C", x=0.5, y=1),
            PolygonExterior(id="sq", a="A", b="B", ref="C", sides=2),
        ]
        with pytest.raises(IRCompileError):
            compile_defs(DiagramIR(define=stmts))

    def test_equilateral_triangle_exterior(self):
        """polygon_exterior with sides=3 builds an equilateral triangle exterior to ref."""
        stmts = [
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=2, y=0),
            PointFixed(id="C", x=1, y=math.sqrt(3)),  # equilateral triangle above edge
            PolygonExterior(id="tri_ext", a="A", b="B", ref="C", sides=3),
        ]
        sym = compile_defs(DiagramIR(define=stmts))
        assert isinstance(sym["tri_ext"], spg.Polygon)
        assert len(sym["tri_ext"].vertices) == 3
        # v2 should be below the x-axis (opposite from C which is above)
        v2y = float(sym["tri_ext_v2"].y.evalf())
        assert v2y < 0, f"Exterior triangle vertex should be below x-axis, got y={v2y}"
        # All edges must be equal length (actually equilateral)
        verts = [(float(sym[f"tri_ext_v{i}"].x.evalf()), float(sym[f"tri_ext_v{i}"].y.evalf())) for i in range(3)]
        edge_lengths = [math.hypot(verts[(i+1)%3][0]-verts[i][0], verts[(i+1)%3][1]-verts[i][1]) for i in range(3)]
        assert abs(edge_lengths[0] - 2.0) < 1e-9, f"Edge 0 length {edge_lengths[0]} != 2"
        assert abs(edge_lengths[1] - edge_lengths[0]) < 1e-9, f"Edges not equal: {edge_lengths}"
        assert abs(edge_lengths[2] - edge_lengths[0]) < 1e-9, f"Edges not equal: {edge_lengths}"

    def test_pentagon_exterior(self):
        """polygon_exterior with sides=5 builds a regular pentagon exterior to ref."""
        stmts = [
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=2, y=0),
            PointFixed(id="ref", x=1, y=1),  # ref above edge
            PolygonExterior(id="pent", a="A", b="B", ref="ref", sides=5),
        ]
        sym = compile_defs(DiagramIR(define=stmts))
        assert isinstance(sym["pent"], spg.Polygon)
        assert len(sym["pent"].vertices) == 5
        # All sub-points registered
        for i in range(5):
            assert f"pent_v{i}" in sym
        # All edges must be equal length (regular pentagon)
        verts = [(float(sym[f"pent_v{i}"].x.evalf()), float(sym[f"pent_v{i}"].y.evalf())) for i in range(5)]
        edge_len = math.hypot(verts[1][0]-verts[0][0], verts[1][1]-verts[0][1])
        for i in range(1, 5):
            l = math.hypot(verts[(i+1)%5][0]-verts[i][0], verts[(i+1)%5][1]-verts[i][1])
            assert abs(l - edge_len) < 1e-9, f"Pentagon edge {i} length {l} != {edge_len}"
        # Vertices v2..v4 should be below the x-axis (opposite side from ref)
        for i in range(2, 5):
            vy = float(sym[f"pent_v{i}"].y.evalf())
            assert vy < 0, f"pent_v{i} should be below x-axis, got y={vy}"


# ---------------------------------------------------------------------------
# Topological sort and forward reference tests
# ---------------------------------------------------------------------------

class TestToposort:
    def test_forward_reference_resolves(self):
        """compile_defs handles forward references by sorting topologically."""
        # M references A and B, but is listed before them — should still work.
        stmts = [
            PointMidpoint(id="M", p="A", q="B"),
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
        ]
        sym = compile_defs(DiagramIR(define=stmts))
        assert approx(float(sym["M"].x), 2.0)
        assert approx(float(sym["M"].y), 0.0)

    def test_correct_order_unchanged(self):
        """Definitions already in correct order compile as before."""
        stmts = [
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            PointMidpoint(id="M", p="A", q="B"),
        ]
        sym = compile_defs(DiagramIR(define=stmts))
        assert approx(float(sym["M"].x), 2.0)

    def test_circular_dependency_raises(self):
        """Circular dependencies raise IRCompileError."""
        # PointReflect A across B, and B across A — direct cycle
        stmts = [
            PointFixed(id="P", x=0, y=0),
            PointReflect(id="A", source="P", across="B"),
            PointReflect(id="B", source="P", across="A"),
        ]
        with pytest.raises(IRCompileError, match="Circular dependency"):
            compile_defs(DiagramIR(define=stmts))

    def test_undefined_id_error(self):
        """Truly undefined IDs (not defined anywhere) still raise UndefinedRefError."""
        stmts = [
            PointMidpoint(id="M", p="A", q="NONEXISTENT"),
            PointFixed(id="A", x=0, y=0),
        ]
        with pytest.raises(UndefinedRefError, match="undefined id 'NONEXISTENT'"):
            compile_defs(DiagramIR(define=stmts))

    def test_forward_reference_error_message(self):
        """When toposort is bypassed (e.g. cycles prevent it), error is descriptive."""
        # This tests the _resolve path — with toposort active this won't normally
        # trigger, but if it does the message should be clear. We verify the
        # undefined-id path still works with a genuinely missing reference.
        stmts = [PointMidpoint(id="M", p="X", q="Y")]
        with pytest.raises(UndefinedRefError):
            compile_defs(DiagramIR(define=stmts))

    def test_reflection_over_bisector_forward_ref(self):
        """Real-world pattern: reflect D over perpendicular bisector 'axis' defined later."""
        # This mirrors what the LLM generates for isosceles trapezoid:
        # D and C defined before 'axis', but axis is listed after them in DSL.
        from ir.ir import LineThrough, LinePerpendicularThrough
        stmts = [
            PointFixed(id="A", x=-2, y=0),
            PointFixed(id="B", x=2, y=0),
            PointFixed(id="D", x=-1, y=2),
            PointReflect(id="C", source="D", across="axis"),   # forward ref to axis
            PointMidpoint(id="M", p="A", q="B"),
            LineThrough(id="__axis_base", p="A", q="B"),
            LinePerpendicularThrough(id="axis", through="M", to_line="__axis_base"),
        ]
        sym = compile_defs(DiagramIR(define=stmts))
        # C should be the mirror of D over the y-axis (perpendicular bisector of AB)
        assert approx(float(sym["C"].x), 1.0)   # mirrored: -1 -> +1
        assert approx(float(sym["C"].y), 2.0)   # y unchanged
