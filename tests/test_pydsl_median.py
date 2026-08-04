"""Tests for the Median handle and median() op."""
import pytest

from geometry_diagrams.pydsl.api import median, point, triangle
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


def test_median_midpoint_is_midpoint_of_opposite_side():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(0, 4)
        t = triangle(a, b, c)
        m = median(t, from_vertex=a)
        mid = m.midpoint
        ir = get_builder().build()
    mid_defs = [d for d in ir.define if d.kind == "point_midpoint"]
    assert len(mid_defs) == 1
    assert {mid_defs[0].p, mid_defs[0].q} == {b.id, c.id}
    assert mid.id == mid_defs[0].id


def test_median_segment_connects_vertex_to_midpoint():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(0, 4)
        t = triangle(a, b, c)
        m = median(t, from_vertex=a)
        seg = m.segment
        ir = get_builder().build()
    seg_defs = [d for d in ir.define if d.kind == "segment" and d.id == seg.id]
    assert len(seg_defs) == 1
    assert seg_defs[0].a == a.id
    assert seg_defs[0].b == m.midpoint.id


def test_median_raises_for_vertex_not_in_triangle():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(0, 4)
        outside = point(9, 9)
        t = triangle(a, b, c)
        with pytest.raises(ValueError, match="not a vertex"):
            median(t, from_vertex=outside)
