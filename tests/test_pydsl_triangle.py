# tests/test_pydsl_triangle.py
"""Tests for the Triangle handle and triangle() op."""
import pytest

from geometry_diagrams.pydsl.api import point, triangle
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


def test_triangle_creates_triangle_def_with_vertex_ids():
    with new_builder_context():
        a, b, c = point(0, 0), point(1, 0), point(0, 1)
        t = triangle(a, b, c)
        ir = get_builder().build()
    tri_defs = [d for d in ir.define if d.kind == "triangle"]
    assert len(tri_defs) == 1
    assert (tri_defs[0].a, tri_defs[0].b, tri_defs[0].c) == (a.id, b.id, c.id)
    assert t.id == tri_defs[0].id


def test_vertices_accessor_returns_point_handles_in_order():
    with new_builder_context():
        a, b, c = point(0, 0), point(1, 0), point(0, 1)
        t = triangle(a, b, c)
        assert [v.id for v in t.vertices] == [a.id, b.id, c.id]


def test_side_is_order_independent():
    with new_builder_context():
        a, b, c = point(0, 0), point(1, 0), point(0, 1)
        t = triangle(a, b, c)
        s1 = t.side(a, b)
        s2 = t.side(b, a)
        assert s1.id == s2.id


def test_side_creates_exactly_one_segment_def():
    with new_builder_context():
        a, b, c = point(0, 0), point(1, 0), point(0, 1)
        t = triangle(a, b, c)
        t.side(a, b)
        t.side(b, a)  # same pair, reversed order — must not create a second Segment
        ir = get_builder().build()
    seg_defs = [d for d in ir.define if d.kind == "segment"]
    assert len(seg_defs) == 1


def test_side_raises_for_non_vertex_point():
    with new_builder_context():
        a, b, c = point(0, 0), point(1, 0), point(0, 1)
        outside = point(5, 5)
        t = triangle(a, b, c)
        with pytest.raises(ValueError, match="not a vertex"):
            t.side(a, outside)
