# tests/test_pydsl_basic_ops.py
"""Tests for the point() and line_through() API functions and their handles."""
import pytest

from geometry_diagrams.pydsl.api import line_through, point
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


def test_point_creates_point_fixed_def_and_returns_handle():
    with new_builder_context():
        p = point(1.5, -2.0)
        ir = get_builder().build()
    assert len(ir.define) == 1
    d = ir.define[0]
    assert d.kind == "point_fixed"
    assert d.x == 1.5 and d.y == -2.0
    assert p.id == d.id


def test_line_through_references_both_points():
    with new_builder_context():
        a = point(0, 0)
        b = point(1, 1)
        line = line_through(a, b)
        ir = get_builder().build()
    line_defs = [d for d in ir.define if d.kind == "line_through"]
    assert len(line_defs) == 1
    assert line_defs[0].p == a.id
    assert line_defs[0].q == b.id
    assert line.id == line_defs[0].id


def test_api_functions_raise_outside_builder_context():
    with pytest.raises(RuntimeError, match="no active Builder"):
        point(0, 0)
