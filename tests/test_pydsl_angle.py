"""Tests for AngleRef, Triangle/Polygon.angle_at(), angle(), and mark_angle()."""
import math

import pytest

from geometry_diagrams.pydsl.api import (
    angle, intersection, line_through, mark_angle, point, polygon, triangle,
)
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


def test_angle_builds_ref_with_given_vertex_and_ray_endpoints():
    """angle(a, o, b) is for a non-triangle/polygon-vertex angle — e.g. a
    linear pair at a point on a line, matching Triangle.angle_at()'s
    existing o-is-the-vertex argument convention."""
    with new_builder_context():
        a, o, b = point(0, 0), point(1, 0), point(2, 1)
        ref = angle(a, o, b)
    assert ref.o.id == o.id
    assert {ref.a.id, ref.b.id} == {a.id, b.id}


def test_angle_rejects_vertex_coincident_with_a_ray_endpoint():
    with new_builder_context():
        a, o = point(0, 0), point(1, 0)
        with pytest.raises(ValueError, match="must be distinct"):
            angle(a, o, o)


def test_triangle_angle_at_returns_angle_ref_with_other_two_vertices():
    with new_builder_context():
        a, b, c = point(0, 0), point(1, 0), point(0, 1)
        t = triangle(a, b, c)
        ref = t.angle_at(b)
    assert ref.o.id == b.id
    assert {ref.a.id, ref.b.id} == {a.id, c.id}


def test_polygon_angle_at_uses_adjacent_vertices():
    with new_builder_context():
        p0, p1, p2, p3 = point(0, 0), point(1, 0), point(1, 1), point(0, 1)
        poly = polygon(p0, p1, p2, p3)
        ref = poly.angle_at(p1)
    assert ref.o.id == p1.id
    assert {ref.a.id, ref.b.id} == {p0.id, p2.id}


def test_angle_ref_radians_and_degrees_for_right_angle():
    with new_builder_context():
        a, o, b = point(1, 0), point(0, 0), point(0, 1)
        ref = angle(a, o, b)
    assert ref.radians == pytest.approx(math.pi / 2)
    assert ref.degrees == pytest.approx(90.0)


def test_angle_ref_degrees_matches_radians_conversion():
    with new_builder_context():
        a, o, b = point(1, 0), point(0, 0), point(1, 1)  # 45 degrees
        ref = angle(a, o, b)
    assert ref.degrees == pytest.approx(math.degrees(ref.radians))
    assert ref.degrees == pytest.approx(45.0)


def test_angle_ref_radians_matches_checks_angle_at_convention():
    """Direct cross-check against geometry_diagrams.ir.checks._angle_at for
    the same three points, so the two unsigned-angle conventions can never
    silently drift apart (see ticket 05's note on this)."""
    import sympy.geometry as spg

    from geometry_diagrams.ir.checks import _angle_at

    with new_builder_context():
        a, o, b = point(3, 1), point(0, 0), point(-2, 5)
        ref = angle(a, o, b)
    expected = _angle_at(
        spg.Point2D(a.x, a.y, evaluate=False),
        spg.Point2D(o.x, o.y, evaluate=False),
        spg.Point2D(b.x, b.y, evaluate=False),
    )
    assert ref.radians == pytest.approx(float(expected))


def test_angle_ref_degrees_resolves_for_vertex_derived_from_intersection():
    """The vertex o is not a literal coordinate but the intersection of two
    lines, resolving to (0, 0) only via Point.x/.y's lazy builder
    resolution -- confirms degrees/radians don't only work for the
    simplest, already-literal inputs."""
    with new_builder_context():
        h1, h2 = point(-1, 0), point(1, 0)  # line y = 0
        v1, v2 = point(0, -1), point(0, 1)  # line x = 0
        horiz = line_through(h1, h2)
        vert = line_through(v1, v2)
        o = intersection(horiz, vert)  # resolves to (0, 0)
        a, b = point(1, 0), point(0, 1)
        ref = angle(a, o, b)
    assert ref.degrees == pytest.approx(90.0)


def test_mark_angle_appends_a_render_op():
    with new_builder_context():
        a, b, c = point(0, 0), point(1, 0), point(0, 1)
        t = triangle(a, b, c)
        ref = t.angle_at(b)
        mark_angle(ref, group=1)
        ir = get_builder().build()
    assert len(ir.render) == 1
    assert ir.render[0].kind == "mark_angles"
    assert ir.render[0].group == "1"
    assert ir.render[0].angles[0].o == b.id
