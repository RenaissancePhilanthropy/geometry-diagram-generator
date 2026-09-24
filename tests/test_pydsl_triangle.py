# tests/test_pydsl_triangle.py
"""Tests for the Triangle handle and triangle() op."""
import pytest

from geometry_diagrams.pydsl.api import intersection, line_through, point, triangle
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


def test_triangle_area_for_concrete_vertices():
    with new_builder_context():
        # 3-4-5 right triangle: area = (1/2) * 3 * 4 = 6.0
        a, b, c = point(0, 0), point(4, 0), point(0, 3)
        t = triangle(a, b, c)
    assert t.area == pytest.approx(6.0)


def test_triangle_perimeter_for_concrete_vertices():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(0, 3)
        t = triangle(a, b, c)
    assert t.perimeter == pytest.approx(3.0 + 4.0 + 5.0)


def test_triangle_area_and_perimeter_resolve_for_vertex_derived_from_intersection():
    """One vertex is not a literal coordinate but the intersection of two
    lines, resolving to (0, 3) only via Point.x/.y's lazy builder
    resolution -- confirms area/perimeter don't only work for the simplest,
    already-literal inputs."""
    with new_builder_context():
        a, b = point(0, 0), point(4, 0)
        h1, h2 = point(-1, 3), point(1, 3)  # line y = 3
        v1, v2 = point(0, -1), point(0, 5)  # line x = 0
        horiz = line_through(h1, h2)
        vert = line_through(v1, v2)
        c = intersection(horiz, vert)  # resolves to (0, 3)
        t = triangle(a, b, c)
    # Same 3-4-5 right triangle as the concrete-vertex tests above.
    assert t.area == pytest.approx(6.0)
    assert t.perimeter == pytest.approx(12.0)
