# tests/test_pydsl_derived_constructions.py
"""Tests for pydsl derived-construction primitives: intersection(),
perpendicular_through(), parallel_through(), perpendicular_bisector(),
angle_bisector(), centroid(), foot_of_perpendicular(), tangent_line().
All wrap IR DefStmt kinds that already exist and are already compiled by
to_sympy.py — the recipe DSL already exposes equivalent ops for all eight,
confirming the composition each one needs."""
import pytest

from geometry_diagrams.pydsl.api import (
    angle_bisector, centroid, foot_of_perpendicular, line_through,
    parallel_through, perpendicular_through, point, triangle,
)
from geometry_diagrams.pydsl.builder import new_builder_context
from geometry_diagrams.ir.ir import (
    LineAngleBisector, LineParallelThrough, LinePerpendicularThrough,
    PointFoot, PointTriangleCenter,
)
from geometry_diagrams.pydsl.api import perpendicular_bisector
from geometry_diagrams.ir.ir import Draw, DrawPoints, PointMidpoint


def test_perpendicular_through_records_line_perpendicular_through():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        base = line_through(a, b)
        p = point(2, 5)
        result = perpendicular_through(p, base)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, LinePerpendicularThrough) and d.id == result.id]
    assert len(defs) == 1
    assert defs[0].through == p.id
    assert defs[0].to_line == base.id


def test_parallel_through_records_line_parallel_through():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        base = line_through(a, b)
        p = point(2, 5)
        result = parallel_through(p, base)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, LineParallelThrough) and d.id == result.id]
    assert len(defs) == 1
    assert defs[0].through == p.id
    assert defs[0].to_line == base.id


def test_angle_bisector_records_line_angle_bisector_with_correct_field_mapping():
    with new_builder_context() as builder:
        vertex = point(0, 0)
        toward1 = point(1, 1)
        toward2 = point(1, -1)
        result = angle_bisector(vertex, toward1, toward2)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, LineAngleBisector) and d.id == result.id]
    assert len(defs) == 1
    # toward1 -> a, toward2 -> b (matches recipe/lower.py's ray1_toward->a, ray2_toward->b)
    assert defs[0].a == toward1.id
    assert defs[0].vertex == vertex.id
    assert defs[0].b == toward2.id


def test_centroid_records_point_triangle_center_which_centroid():
    with new_builder_context() as builder:
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        result = centroid(t)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, PointTriangleCenter) and d.id == result.id]
    assert len(defs) == 1
    assert defs[0].tri == t.id
    assert defs[0].which == "centroid"


def test_foot_of_perpendicular_records_point_foot():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        base = line_through(a, b)
        p = point(2, 5)
        result = foot_of_perpendicular(p, base)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, PointFoot) and d.id == result.id]
    assert len(defs) == 1
    assert defs[0].source == p.id
    assert defs[0].onto == base.id


def test_perpendicular_bisector_composes_three_defs_in_dependency_order():
    with new_builder_context() as builder:
        p, q = point(0, 0), point(4, 0)
        result = perpendicular_bisector(p, q)
        ir = builder.build()
    kinds_in_order = [d.kind for d in ir.define]
    # p, q are point_fixed; then base line_through, then point_midpoint,
    # then line_perp_through, in that dependency order.
    assert kinds_in_order[-3:] == ["line_through", "point_midpoint", "line_perp_through"]
    assert ir.define[-1].id == result.id


def test_perpendicular_bisector_midpoint_accessor():
    with new_builder_context() as builder:
        p, q = point(0, 0), point(4, 0)
        result = perpendicular_bisector(p, q)
        ir = builder.build()
    mid_defs = [d for d in ir.define if isinstance(d, PointMidpoint)]
    assert len(mid_defs) == 1
    assert result.midpoint.id == mid_defs[0].id
    assert mid_defs[0].p == p.id
    assert mid_defs[0].q == q.id


def test_perpendicular_bisector_does_not_auto_draw():
    """Non-goal regression guard: unlike the DSL's PerpendicularBisectorOp,
    pydsl's perpendicular_bisector() must not auto-draw a base segment."""
    with new_builder_context() as builder:
        p, q = point(0, 0), point(4, 0)
        perpendicular_bisector(p, q)
        ir = builder.build()
    assert not any(isinstance(r, (Draw, DrawPoints)) for r in ir.render)


def test_perpendicular_bisector_line_appears_in_stub():
    from geometry_diagrams.pydsl.stub import generate_stub

    stub_text = generate_stub()
    assert "class PerpendicularBisectorLine:" in stub_text
    assert "midpoint: Point" in stub_text


from geometry_diagrams.pydsl.api import intersection
from geometry_diagrams.ir.ir import PickClosestTo, PickLowerOfLine, PickUpperOfLine, PointIntersection


def test_intersection_no_pick_records_pick_none():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 4)
        c, d = point(0, 4), point(4, 0)
        l1, l2 = line_through(a, b), line_through(c, d)
        result = intersection(l1, l2)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, PointIntersection) and d.id == result.id]
    assert len(defs) == 1
    assert defs[0].obj1 == l1.id
    assert defs[0].obj2 == l2.id
    assert defs[0].pick is None


def test_intersection_near_records_pick_closest_to():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 4)
        c, d = point(0, 4), point(4, 0)
        l1, l2 = line_through(a, b), line_through(c, d)
        ref = point(10, 10)
        result = intersection(l1, l2, near=ref)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, PointIntersection) and d.id == result.id]
    assert isinstance(defs[0].pick, PickClosestTo)
    assert defs[0].pick.p == ref.id


def test_intersection_side_left_records_pick_upper_of_line():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 4)
        c, d = point(0, 4), point(4, 0)
        l1, l2 = line_through(a, b), line_through(c, d)
        s1, s2 = point(0, 0), point(1, 0)
        result = intersection(l1, l2, side_of=(s1, s2), side="left")
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, PointIntersection) and d.id == result.id]
    assert isinstance(defs[0].pick, PickUpperOfLine)
    assert defs[0].pick.a == s1.id
    assert defs[0].pick.b == s2.id


def test_intersection_side_right_records_pick_lower_of_line():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 4)
        c, d = point(0, 4), point(4, 0)
        l1, l2 = line_through(a, b), line_through(c, d)
        s1, s2 = point(0, 0), point(1, 0)
        result = intersection(l1, l2, side_of=(s1, s2), side="right")
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, PointIntersection) and d.id == result.id]
    assert isinstance(defs[0].pick, PickLowerOfLine)


def test_intersection_near_and_side_of_together_raises():
    with new_builder_context():
        a, b = point(0, 0), point(4, 4)
        c, d = point(0, 4), point(4, 0)
        l1, l2 = line_through(a, b), line_through(c, d)
        ref = point(10, 10)
        s1, s2 = point(0, 0), point(1, 0)
        with pytest.raises(ValueError, match="at most one"):
            intersection(l1, l2, near=ref, side_of=(s1, s2), side="left")


def test_intersection_side_of_without_side_raises():
    with new_builder_context():
        a, b = point(0, 0), point(4, 4)
        c, d = point(0, 4), point(4, 0)
        l1, l2 = line_through(a, b), line_through(c, d)
        s1, s2 = point(0, 0), point(1, 0)
        with pytest.raises(ValueError, match="together"):
            intersection(l1, l2, side_of=(s1, s2))


def test_intersection_side_without_side_of_raises():
    with new_builder_context():
        a, b = point(0, 0), point(4, 4)
        c, d = point(0, 4), point(4, 0)
        l1, l2 = line_through(a, b), line_through(c, d)
        with pytest.raises(ValueError, match="together"):
            intersection(l1, l2, side="left")


def test_intersection_invalid_side_raises():
    with new_builder_context():
        a, b = point(0, 0), point(4, 4)
        c, d = point(0, 4), point(4, 0)
        l1, l2 = line_through(a, b), line_through(c, d)
        s1, s2 = point(0, 0), point(1, 0)
        with pytest.raises(ValueError, match="left.*right"):
            intersection(l1, l2, side_of=(s1, s2), side="up")


def test_intersection_numeric_result_matches_hand_computed_crossing():
    """Compile-level check: two lines through literal points crossing at a
    hand-computable point — proves the pydsl call reaches correct geometry,
    not just records a plausible-looking def."""
    from geometry_diagrams.ir.to_sympy import compile_defs

    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 4)   # y = x
        c, d = point(0, 4), point(4, 0)   # y = 4 - x
        l1, l2 = line_through(a, b), line_through(c, d)
        result = intersection(l1, l2)
        ir = builder.build()
    sym = compile_defs(ir)
    pt = sym[result.id]
    assert float(pt.x.evalf()) == pytest.approx(2.0)
    assert float(pt.y.evalf()) == pytest.approx(2.0)
