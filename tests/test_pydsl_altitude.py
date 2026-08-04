"""Tests for the Altitude handle and altitude() op."""
import pytest

from geometry_diagrams.pydsl.api import altitude, point, triangle
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


def test_altitude_foot_is_a_point_foot_def():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        alt = altitude(t, from_vertex=a)
        foot = alt.foot
        ir = get_builder().build()
    foot_defs = [d for d in ir.define if d.kind == "point_foot"]
    assert len(foot_defs) == 1
    assert foot_defs[0].source == a.id
    assert foot.id == foot_defs[0].id


def test_altitude_line_is_perpendicular_through_the_vertex():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        alt = altitude(t, from_vertex=a)
        line = alt.line
        ir = get_builder().build()
    perp_defs = [d for d in ir.define if d.kind == "line_perp_through" and d.id == line.id]
    assert len(perp_defs) == 1
    assert perp_defs[0].through == a.id


def test_altitude_base_line_connects_the_other_two_vertices():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        alt = altitude(t, from_vertex=a)
        ir = get_builder().build()
    base_defs = [d for d in ir.define if d.kind == "line_through"]
    assert len(base_defs) == 1
    assert {base_defs[0].p, base_defs[0].q} == {b.id, c.id}


def test_altitude_raises_for_vertex_not_in_triangle():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        outside = point(9, 9)
        t = triangle(a, b, c)
        with pytest.raises(ValueError, match="not a vertex"):
            altitude(t, from_vertex=outside)


def test_altitude_segment_connects_vertex_to_foot():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        alt = altitude(t, from_vertex=a)
        seg = alt.segment
        ir = get_builder().build()
    seg_defs = [d for d in ir.define if d.kind == "segment" and d.id == seg.id]
    assert len(seg_defs) == 1
    assert seg_defs[0].a == a.id
    assert seg_defs[0].b == alt.foot.id
