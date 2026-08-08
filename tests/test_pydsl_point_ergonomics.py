# tests/test_pydsl_point_ergonomics.py
"""Tests for Point.x/.y and arithmetic operators (+, -, *, __rmul__).

Motivation (found diagnosing real eval failures): models kept hand-deriving
coordinates via separate plain-float bookkeeping alongside point() calls,
because Point handles carried no coordinates at all — not even for literal
point(x, y) calls, where the model already knows the numbers. This let
models write natural, less error-prone code like `center + k * (source -
center)` for a dilation, directly on the handles they already have, instead
of re-deriving the same arithmetic with parallel float variables.
"""
import math

import pytest

from geometry_diagrams.pydsl.api import point, point_on, line_through
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context
from geometry_diagrams.ir.ir import PointFixed


def test_point_literal_exposes_its_own_coordinates():
    with new_builder_context():
        p = point(3, 4)
    assert p.x == 3.0
    assert p.y == 4.0


def test_add_two_literal_points_records_a_new_point_fixed():
    with new_builder_context() as builder:
        a = point(1, 2)
        b = point(3, 4)
        c = a + b
        ir = builder.build()
    assert c.x == 4.0
    assert c.y == 6.0
    defs = [d for d in ir.define if isinstance(d, PointFixed) and d.id == c.id]
    assert len(defs) == 1
    assert defs[0].x == 4.0 and defs[0].y == 6.0


def test_subtract_two_literal_points():
    with new_builder_context():
        a = point(5, 7)
        b = point(2, 1)
        c = a - b
    assert c.x == 3.0
    assert c.y == 6.0


def test_multiply_point_by_scalar_both_orders():
    with new_builder_context():
        a = point(2, 3)
        b = a * 2.5
        c = 2.5 * a
    assert (b.x, b.y) == (5.0, 7.5)
    assert (c.x, c.y) == (5.0, 7.5)


def test_dilation_via_plain_operators_matches_dilate_point():
    """The exact motivating case: for literal points, dilation should just
    work as ordinary arithmetic, no dedicated primitive required."""
    from geometry_diagrams.pydsl.api import dilate_point

    with new_builder_context() as builder:
        center = point(1, 1)
        source = point(3, 1)
        k = 2.0
        via_operators = center + (source - center) * k
        via_primitive = dilate_point(source, center, k)
        ir = builder.build()

    from geometry_diagrams.ir.to_sympy import compile_defs
    sym = compile_defs(ir)
    assert float(sym[via_operators.id].x) == pytest.approx(float(sym[via_primitive.id].x))
    assert float(sym[via_operators.id].y) == pytest.approx(float(sym[via_primitive.id].y))


def test_addition_works_when_one_operand_is_a_constructed_point():
    with new_builder_context():
        a = point(0, 0)
        b = point(4, 0)
        line = line_through(a, b)
        mid = point_on(line, 0.5)
        result = a + mid
    assert (result.x, result.y) == pytest.approx((2.0, 0.0))


def test_multiplying_a_constructed_point_by_a_scalar_works():
    from geometry_diagrams.pydsl.api import rotate_point

    with new_builder_context():
        origin = point(0, 0)
        far = point(1, 0)
        rotated = rotate_point(far, origin, math.pi / 4)
        doubled = rotated * 2
    assert (doubled.x, doubled.y) == pytest.approx((2 * math.cos(math.pi / 4), 2 * math.sin(math.pi / 4)))


def test_direct_x_and_y_access_on_a_constructed_point_now_resolves():
    """Historical note: a model reading .x/.y directly (not through
    +/-/*) on a constructed point used to silently get None back, and
    whatever it did next raised a bare, contextless TypeError instead of
    a clear error. This design closed the gap the other way: these now
    resolve to real numbers instead of needing to raise at all."""
    from geometry_diagrams.pydsl.api import centroid, triangle

    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(0, 3)
        t = triangle(a, b, c)
        g = centroid(t)
    assert (g.x, g.y) == pytest.approx((4.0 / 3, 1.0))


def test_distance_between_two_literal_points():
    from geometry_diagrams.pydsl.api import distance

    with new_builder_context():
        a = point(0, 0)
        b = point(3, 4)
    assert distance(a, b) == pytest.approx(5.0)


def test_distance_works_for_a_constructed_point():
    from geometry_diagrams.pydsl.api import distance

    with new_builder_context():
        a = point(0.0, 0.0)
        b = point(4.0, 0.0)
        line = line_through(a, b)
        mid = point_on(line, 0.5)
    assert distance(a, mid) == pytest.approx(2.0)


def test_x_and_y_resolve_for_every_constructed_point_kind():
    """Each of these previously left _x=_y=None permanently."""
    from geometry_diagrams.pydsl.api import (
        centroid, dilate_point, foot_of_perpendicular, perpendicular_bisector,
        reflect_point, rotate_point, triangle,
    )

    with new_builder_context():
        a = point(0.0, 0.0)
        b = point(4.0, 0.0)
        line = line_through(a, b)

        on_line = point_on(line, 0.5)
        assert (on_line.x, on_line.y) == pytest.approx((2.0, 0.0))

        rotated = rotate_point(point(1.0, 0.0), a, math.pi / 2)
        assert (rotated.x, rotated.y) == pytest.approx((0.0, 1.0))

        reflected = reflect_point(point(1.0, 1.0), line)
        assert (reflected.x, reflected.y) == pytest.approx((1.0, -1.0))

        dilated = dilate_point(b, a, 0.5)
        assert (dilated.x, dilated.y) == pytest.approx((2.0, 0.0))

        c = point(0.0, 3.0)
        t = triangle(a, b, c)
        g = centroid(t)
        assert (g.x, g.y) == pytest.approx((4.0 / 3, 1.0))

        foot = foot_of_perpendicular(point(2.0, 5.0), line)
        assert (foot.x, foot.y) == pytest.approx((2.0, 0.0))

        pb = perpendicular_bisector(a, b)
        assert (pb.midpoint.x, pb.midpoint.y) == pytest.approx((2.0, 0.0))


def test_x_and_y_resolve_for_intersection_with_and_without_explicit_pick():
    from geometry_diagrams.pydsl.api import intersection

    with new_builder_context():
        a, b = point(0.0, 0.0), point(4.0, 0.0)
        c, d = point(2.0, -2.0), point(2.0, 2.0)
        l1 = line_through(a, b)
        l2 = line_through(c, d)
        auto = intersection(l1, l2)
        assert (auto.x, auto.y) == pytest.approx((2.0, 0.0))

        near = intersection(l1, l2, near=point(2.0, 0.0))
        assert (near.x, near.y) == pytest.approx((2.0, 0.0))


def test_triangle_angle_at_vertex_handle_reads_literal_coordinates_from_cache():
    """Bug fix found during design review: angle_at() re-mints a fresh
    Point handle for each vertex with no coordinates carried over, even
    when the underlying point is a plain literal already sitting in
    builder._coord_floats."""
    from geometry_diagrams.pydsl.api import triangle

    with new_builder_context():
        a, b, c = point(0.0, 0.0), point(4.0, 0.0), point(0.0, 3.0)
        t = triangle(a, b, c)
        ref = t.angle_at(b)
    assert (ref.a.x, ref.a.y) in {(0.0, 0.0), (0.0, 3.0)}
    assert (ref.o.x, ref.o.y) == pytest.approx((4.0, 0.0))


def test_point_arithmetic_works_through_the_real_sandbox():
    """Regression test: Point.__add__ previously called get_builder(), which
    only succeeds inside a _bind_to_builder-wrapped top-level call — a
    script's own top-level `a + b` statement is not one, so this raised
    RuntimeError: no active Builder in the real sandbox despite passing
    every direct-new_builder_context() test above."""
    from geometry_diagrams.pydsl.sandbox import run_script

    script = "a = point(0, 0)\nb = point(4, 0)\nc = a + b\ndraw_points(a, b, c)\n"
    result = run_script(script, timeout_seconds=10.0)
    assert result.error is None, result.error
    assert result.diagram_ir is not None
