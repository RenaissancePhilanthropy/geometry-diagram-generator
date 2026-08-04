"""Tests for the Polygon handle and polygon() op."""
import pytest

from geometry_diagrams.pydsl.api import point, polygon
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


def test_polygon_creates_polygon_def_with_vertex_ids_in_order():
    with new_builder_context():
        pts = [point(0, 0), point(1, 0), point(1, 1), point(0, 1)]
        p = polygon(*pts)
        ir = get_builder().build()
    poly_defs = [d for d in ir.define if d.kind == "polygon"]
    assert len(poly_defs) == 1
    assert poly_defs[0].points == [pt.id for pt in pts]
    assert p.id == poly_defs[0].id


def test_polygon_requires_at_least_three_vertices():
    with new_builder_context():
        with pytest.raises(ValueError, match="at least 3"):
            polygon(point(0, 0), point(1, 0))


def test_side_accepts_adjacent_vertices_either_order():
    with new_builder_context():
        a, b, c, d = point(0, 0), point(1, 0), point(1, 1), point(0, 1)
        p = polygon(a, b, c, d)
        s1 = p.side(a, b)
        s2 = p.side(b, a)
        assert s1.id == s2.id
        s_wrap = p.side(d, a)  # last vertex to first — also adjacent
        assert s_wrap.id != s1.id


def test_side_raises_for_non_adjacent_vertices():
    with new_builder_context():
        a, b, c, d = point(0, 0), point(1, 0), point(1, 1), point(0, 1)
        p = polygon(a, b, c, d)
        with pytest.raises(ValueError, match="not adjacent"):
            p.side(a, c)  # diagonal, not an edge
