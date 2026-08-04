"""Tests for AngleRef, Triangle/Polygon.angle_at(), and mark_angle()."""
from geometry_diagrams.pydsl.api import mark_angle, point, polygon, triangle
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


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
