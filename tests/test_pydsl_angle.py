"""Tests for AngleRef, Triangle/Polygon.angle_at(), angle(), and mark_angle()."""
import pytest

from geometry_diagrams.pydsl.api import angle, mark_angle, point, polygon, triangle
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
