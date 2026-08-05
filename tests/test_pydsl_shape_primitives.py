# tests/test_pydsl_shape_primitives.py
"""Tests for pydsl's new shape-primitive functions: ray(), ellipse(),
regular_polygon(), rectangle(), walk() — plus polygon()'s coincident-vertex
guard. ray()/ellipse() wrap existing IR DefStmt kinds; the rest compute
literal coordinates with plain arithmetic and hand them to polygon()."""
import math

import pytest

from geometry_diagrams.pydsl.api import point, polygon, ray
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


def test_ray_records_ray_def_from_a_through_b():
    with new_builder_context():
        a, b = point(0, 0), point(1, 1)
        r = ray(a, b)
        ir = get_builder().build()
    ray_defs = [d for d in ir.define if d.kind == "ray" and d.id == r.id]
    assert len(ray_defs) == 1
    assert ray_defs[0].a == a.id
    assert ray_defs[0].b == b.id


def test_polygon_rejects_coincident_consecutive_vertices():
    with new_builder_context():
        a, b, c, d = point(0, 0), point(4, 0), point(4, 4), point(4, 4)
        with pytest.raises(ValueError, match="coincident"):
            polygon(a, b, c, d)


def test_polygon_rejects_repeated_first_point_as_last():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(4, 4)
        closing_repeat = point(0, 0)
        with pytest.raises(ValueError, match="coincident"):
            polygon(a, b, c, closing_repeat)


def test_polygon_allows_unknown_coordinate_vertices_without_false_positive():
    from geometry_diagrams.ir.ir import LineThrough

    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        c, d = point(4, 4), point(0, 4)
        line_id = builder._fresh_hidden_id("line")
        builder._add(LineThrough(id=line_id, p=a.id, q=d.id))
        from geometry_diagrams.pydsl.handles import Line
        from geometry_diagrams.pydsl.api import point_on

        on_line = point_on(Line(id=line_id), 0.5)  # coordinates unknown until compile
        p = polygon(a, b, c, on_line)
    assert p.id is not None


def test_polygon_still_builds_valid_non_coincident_shape():
    with new_builder_context():
        pts = [point(0, 0), point(1, 0), point(1, 1), point(0, 1)]
        p = polygon(*pts)
    assert p.vertices == tuple(pts)
