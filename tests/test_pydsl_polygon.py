"""Tests for the Polygon handle and polygon() op."""
import pytest

from geometry_diagrams.pydsl.api import point, polygon, polyline
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


def test_polyline_requires_at_least_two_points():
    with new_builder_context():
        with pytest.raises(ValueError, match="at least 2"):
            polyline(point(0, 0))


def test_polyline_rejects_consecutive_coincident_points():
    with new_builder_context():
        a, b = point(0, 0), point(1, 0)
        with pytest.raises(ValueError, match="coincident"):
            polyline(a, a, b)  # a, a are CONSECUTIVE and coincident


def test_polyline_allows_first_and_last_coincident_no_wraparound_check():
    with new_builder_context():
        a, b = point(0, 0), point(1, 0)
        pl = polyline(a, b, a)  # first and last coincide, but no CONSECUTIVE pair does
        assert pl.vertices == (a, b, a)


def test_polyline_builds_polyline_open_def():
    with new_builder_context():
        pts = [point(0, 0), point(1, 0), point(1, 1)]
        pl = polyline(*pts)
        ir = get_builder().build()
    polyline_defs = [d for d in ir.define if d.kind == "polyline_open"]
    assert len(polyline_defs) == 1
    assert polyline_defs[0].points == [pt.id for pt in pts]
    assert pl.id == polyline_defs[0].id


def test_polyline_renders_through_real_sandbox():
    from geometry_diagrams.pydsl.sandbox import run_script

    script = (
        "p0 = point(0, 0)\n"
        "p1 = point(1, 0)\n"
        "p2 = point(1, 1)\n"
        "pl = polyline(p0, p1, p2)\n"
        "draw(pl)\n"
    )
    result = run_script(script, timeout_seconds=10.0)
    assert result.error is None, result.error
    assert result.diagram_ir is not None
    polyline_defs = [d for d in result.diagram_ir.define if d.kind == "polyline_open"]
    assert len(polyline_defs) == 1
    assert len(polyline_defs[0].points) == 3
