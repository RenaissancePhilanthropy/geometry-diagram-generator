"""PointIntersection near tangency for float-built circles and lines.

SymPy rounds float coordinates/radii to fractions at construction, so objects that
are tangent by construction land on either side of exact tangency at random
(no points, or two points ~1e-8 apart). These tests pin the intended behaviour:
an intended tangency yields exactly one point, genuine misses still error with a
descriptive message, and real crossings are unchanged.
"""
from __future__ import annotations

import math
from random import Random

import pytest

from geometry_diagrams.ir.errors import IntersectionError
from geometry_diagrams.ir.ir import (
    ArcCenterStartEnd,
    CircleCenterRadius,
    DiagramIR,
    EllipseCenterAxes,
    LineThrough,
    PickBeyond,
    PickLowerOfLine,
    PickOnObject,
    PickUpperOfLine,
    PointFixed,
    PointIntersection,
)
from geometry_diagrams.ir.to_sympy import compile_defs


def _compile(*stmts):
    return compile_defs(DiagramIR(define=list(stmts)))


def _xy(point):
    return float(point.x.evalf()), float(point.y.evalf())


def _circle_pair(rng, kind, offset=(0.0, 0.0), scale=1.0):
    """Float-built circles tangent by construction. Returns (defs, expected tangent xy)."""
    ang = rng.uniform(0, 2 * math.pi)
    d = rng.uniform(0.5, 50) * scale
    x, y = d * math.cos(ang), d * math.sin(ang)
    dd = math.hypot(x, y)
    if kind == "external":
        r1 = rng.uniform(0.1, 0.9) * dd
        r2 = dd - r1
    else:
        r2 = rng.uniform(0.1, 0.9) * dd
        r1 = dd + r2
    ox, oy = offset
    defs = [
        PointFixed(id="A", x=ox, y=oy),
        PointFixed(id="B", x=ox + x, y=oy + y),
        CircleCenterRadius(id="c1", center="A", radius=r1),
        CircleCenterRadius(id="c2", center="B", radius=r2),
        PointIntersection(id="T", obj1="c1", obj2="c2"),
    ]
    expected = (ox + x / dd * r1, oy + y / dd * r1)
    return defs, expected, dd


@pytest.mark.parametrize("kind", ["external", "internal"])
def test_float_tangent_circles_give_one_point(kind):
    rng = Random(21)
    for _ in range(60):
        defs, expected, dd = _circle_pair(rng, kind)
        got = _xy(_compile(*defs)["T"])
        assert math.dist(got, expected) < 1e-6 * dd


@pytest.mark.parametrize("kind", ["external", "internal"])
def test_float_tangent_small_circles_far_from_origin(kind):
    rng = Random(22)
    for _ in range(40):
        defs, expected, dd = _circle_pair(rng, kind, offset=(1000.0, -750.0), scale=0.02)
        got = _xy(_compile(*defs)["T"])
        assert math.dist(got, expected) < 1e-6 * max(dd, 1.0)


def test_float_tangent_line_and_circle_give_one_point():
    rng = Random(23)
    for _ in range(60):
        r = rng.uniform(0.5, 20)
        th = rng.uniform(0, 2 * math.pi)
        px, py = r * math.cos(th), r * math.sin(th)
        sym = _compile(
            PointFixed(id="O", x=0, y=0),
            PointFixed(id="P", x=px, y=py),
            PointFixed(id="Q", x=px - math.sin(th), y=py + math.cos(th)),
            LineThrough(id="l", p="P", q="Q"),
            CircleCenterRadius(id="c", center="O", radius=r),
            PointIntersection(id="T", obj1="l", obj2="c"),
        )
        assert math.dist(_xy(sym["T"]), (px, py)) < 1e-6 * r


def test_genuine_miss_still_errors_and_reports_the_gap():
    defs = [
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=5 * (1 + 1e-5), y=0),
        CircleCenterRadius(id="c1", center="A", radius=3.0),
        CircleCenterRadius(id="c2", center="B", radius=2.0),
        PointIntersection(id="T", obj1="c1", obj2="c2"),
    ]
    with pytest.raises(IntersectionError, match=r"disjoint.*gap"):
        _compile(*defs)


@pytest.mark.parametrize(
    "bx, r1, r2, word",
    [
        (0.5, 3.0, 1.0, "contained"),
        (0.0, 3.0, 1.0, "concentric"),
        (0.0, 3.0, 3.0, "identical"),
    ],
)
def test_no_intersection_cases_are_named(bx, r1, r2, word):
    defs = [
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=bx, y=0),
        CircleCenterRadius(id="c1", center="A", radius=r1),
        CircleCenterRadius(id="c2", center="B", radius=r2),
        PointIntersection(id="T", obj1="c1", obj2="c2"),
    ]
    with pytest.raises(IntersectionError, match=word):
        _compile(*defs)


def test_genuine_crossing_is_unchanged_and_pick_chooses_a_side():
    base = [
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        CircleCenterRadius(id="c1", center="A", radius=3),
        CircleCenterRadius(id="c2", center="B", radius=2),
    ]
    up = _compile(*base, PointIntersection(id="T", obj1="c1", obj2="c2", pick=PickUpperOfLine(a="A", b="B")))
    down = _compile(*base, PointIntersection(id="T", obj1="c1", obj2="c2", pick=PickLowerOfLine(a="A", b="B")))
    assert _xy(up["T"])[1] > 0 > _xy(down["T"])[1]
    assert _xy(up["T"])[0] == pytest.approx(_xy(down["T"])[0])


@pytest.mark.parametrize("pick_kind", ["upper", "lower"])
def test_side_pick_accepts_a_snapped_tangent_point_on_the_line(pick_kind):
    rng = Random(24)
    pick_cls = PickUpperOfLine if pick_kind == "upper" else PickLowerOfLine
    for _ in range(60):
        r1 = rng.uniform(0.5, 5.0)
        r2 = rng.uniform(0.5, 5.0)
        d = r1 + r2
        sym = _compile(
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=d, y=0),
            CircleCenterRadius(id="c1", center="A", radius=r1),
            CircleCenterRadius(id="c2", center="B", radius=r2),
            PointIntersection(id="T", obj1="c1", obj2="c2", pick=pick_cls(a="A", b="B")),
        )
        assert _xy(sym["T"]) == pytest.approx((r1, 0.0), abs=1e-6)


def test_on_object_pick_accepts_a_snapped_tangent_point():
    rng = Random(25)
    for _ in range(60):
        defs, expected, dd = _circle_pair(rng, "external")
        defs[-1] = PointIntersection(id="T", obj1="c1", obj2="c2", pick=PickOnObject(obj="c1"))
        got = _xy(_compile(*defs)["T"])
        assert math.dist(got, expected) < 1e-6 * dd


def test_arc_whose_end_is_the_tangent_point_still_intersects():
    rng = Random(26)
    for _ in range(60):
        r1 = rng.uniform(1.0, 5.0)
        r2 = rng.uniform(1.0, 5.0)
        th = rng.uniform(0.3, 2.5)
        tx, ty = r1 * math.cos(th), r1 * math.sin(th)
        bx, by = (r1 + r2) * math.cos(th), (r1 + r2) * math.sin(th)
        sym = _compile(
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="S", x=r1, y=0),
            PointFixed(id="E", x=tx, y=ty),
            PointFixed(id="B", x=bx, y=by),
            ArcCenterStartEnd(id="arc", center="A", start="S", end="E"),
            CircleCenterRadius(id="c2", center="B", radius=r2),
            PointIntersection(id="T", obj1="arc", obj2="c2"),
        )
        assert math.dist(_xy(sym["T"]), (tx, ty)) < 1e-6 * r1


# ---------------------------------------------------------------------------
# Ellipse x line
# ---------------------------------------------------------------------------

def _ellipse_tangent_case(rng, a_range=(1, 8), b_range=(1, 8), offset_range=5.0):
    a, b = rng.uniform(*a_range), rng.uniform(*b_range)
    phi = rng.uniform(0, 2 * math.pi)
    cx, cy = rng.uniform(-offset_range, offset_range), rng.uniform(-offset_range, offset_range)
    px, py = cx + a * math.cos(phi), cy + b * math.sin(phi)
    tx, ty = -a * math.sin(phi), b * math.cos(phi)
    defs = [
        PointFixed(id="C", x=cx, y=cy),
        PointFixed(id="P", x=px, y=py),
        PointFixed(id="Q", x=px + tx, y=py + ty),
        LineThrough(id="l", p="P", q="Q"),
        EllipseCenterAxes(id="e", center="C", hradius=a, vradius=b),
        PointIntersection(id="T", obj1="l", obj2="e"),
    ]
    return defs, (px, py), max(a, b)


def test_float_tangent_line_and_ellipse_give_one_point():
    rng = Random(31)
    for _ in range(60):
        defs, expected, size = _ellipse_tangent_case(rng)
        assert math.dist(_xy(_compile(*defs)["T"]), expected) < 1e-6 * size


def test_float_tangent_line_and_eccentric_ellipse():
    rng = Random(32)
    for _ in range(40):
        defs, expected, size = _ellipse_tangent_case(rng, a_range=(10, 30), b_range=(0.3, 1.0))
        assert math.dist(_xy(_compile(*defs)["T"]), expected) < 1e-6 * size


def test_float_tangent_line_and_ellipse_far_from_origin():
    rng = Random(33)
    for _ in range(40):
        defs, expected, size = _ellipse_tangent_case(
            rng, a_range=(0.01, 0.05), b_range=(0.01, 0.05), offset_range=800.0
        )
        assert math.dist(_xy(_compile(*defs)["T"]), expected) < 1e-6 * 800


def test_line_missing_an_ellipse_reports_the_gap():
    with pytest.raises(IntersectionError, match=r"disjoint.*gap"):
        _compile(
            PointFixed(id="C", x=0, y=0),
            EllipseCenterAxes(id="e", center="C", hradius=3.0, vradius=2.0),
            PointFixed(id="P", x=0, y=2.001),
            PointFixed(id="Q", x=1, y=2.001),
            LineThrough(id="l", p="P", q="Q"),
            PointIntersection(id="T", obj1="l", obj2="e"),
        )


def test_line_crossing_an_ellipse_is_unchanged():
    base = [
        PointFixed(id="C", x=0, y=0),
        EllipseCenterAxes(id="e", center="C", hradius=3.0, vradius=2.0),
        PointFixed(id="P", x=0, y=1.0),
        PointFixed(id="Q", x=1, y=1.0),
        LineThrough(id="l", p="P", q="Q"),
    ]
    x = 3.0 * math.sqrt(1 - 0.25)
    right = _compile(*base, PointIntersection(id="T", obj1="l", obj2="e", pick=PickBeyond(from_point="C", past_point="Q")))
    assert _xy(right["T"]) == pytest.approx((x, 1.0), abs=1e-6)


# ---------------------------------------------------------------------------
# Ellipse x ellipse/circle: SymPy returns nothing for float-valued four-point crossings
# ---------------------------------------------------------------------------

def _two_ellipses(h1, v1, c2, h2, v2):
    return [
        PointFixed(id="C1", x=0, y=0),
        PointFixed(id="C2", x=c2[0], y=c2[1]),
        EllipseCenterAxes(id="e1", center="C1", hradius=h1, vradius=v1),
        EllipseCenterAxes(id="e2", center="C2", hradius=h2, vradius=v2),
        PointIntersection(id="T", obj1="e1", obj2="e2"),
    ]


def test_ellipses_that_cross_but_sympy_cannot_solve_say_so():
    with pytest.raises(IntersectionError, match=r"cross at 4 points.*could not solve"):
        _compile(*_two_ellipses(5.0, 2.0, (1.3, 0.7), 2.1, 4.7))


def test_disjoint_ellipses_keep_the_generic_message():
    with pytest.raises(IntersectionError) as exc:
        _compile(*_two_ellipses(2.0, 1.0, (20.0, 0.0), 2.0, 1.0))
    assert "could not solve" not in str(exc.value)
