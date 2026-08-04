# tests/test_pydsl_point_on_and_rotate.py
"""Tests for point_on() and rotate_point() — exposing the IR's existing
PointOn/PointRotate constructs, previously only reachable via the DSL."""
import math

from geometry_diagrams.pydsl.api import line_through, point, point_on, rotate_point
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context
from geometry_diagrams.ir.ir import PointOn, PointOnParam, PointRotate
from geometry_diagrams.ir.to_sympy import compile_defs


def test_point_on_appends_point_on_def_with_param_t():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        line = line_through(a, b)
        p = point_on(line, 0.5)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, PointOn) and d.id == p.id]
    assert len(defs) == 1
    assert defs[0].on == line.id
    assert isinstance(defs[0].how, PointOnParam)
    assert defs[0].how.t == 0.5


def test_point_on_a_line_extends_beyond_the_defining_points():
    """t outside [0, 1] must extend past the two points used to define the
    line — this is the actual capability the transversal-angles/
    triangle-proportionality bugs needed and didn't have."""
    with new_builder_context() as builder:
        a, b = point(3, 3), point(5, 0)
        line = line_through(a, b)
        beyond = point_on(line, 1.5)
        before = point_on(line, -0.5)
        ir = builder.build()
    sym = compile_defs(ir)
    bx, by = float(sym[beyond.id].x), float(sym[beyond.id].y)
    px, py = float(sym[before.id].x), float(sym[before.id].y)
    # a=(3,3), b=(5,0): direction (2,-3). t=1.5 -> a + 1.5*(2,-3) = (6, -1.5)
    assert math.isclose(bx, 6.0, abs_tol=1e-9)
    assert math.isclose(by, -1.5, abs_tol=1e-9)
    # t=-0.5 -> a + (-0.5)*(2,-3) = (2, 4.5)
    assert math.isclose(px, 2.0, abs_tol=1e-9)
    assert math.isclose(py, 4.5, abs_tol=1e-9)


def test_point_on_a_segment_interpolates_between_its_endpoints():
    with new_builder_context() as builder:
        a, b, c = point(4, 8), point(0, 0), point(8, 0)
        from geometry_diagrams.pydsl.api import triangle
        t = triangle(a, b, c)
        seg_ab = t.side(a, b)
        d = point_on(seg_ab, 0.6)
        ir = builder.build()
    sym = compile_defs(ir)
    dx, dy = float(sym[d.id].x), float(sym[d.id].y)
    # a=(4,8), b=(0,0): a + 0.6*(b-a) = (4 - 2.4, 8 - 4.8) = (1.6, 3.2)
    assert math.isclose(dx, 1.6, abs_tol=1e-9)
    assert math.isclose(dy, 3.2, abs_tol=1e-9)


def test_rotate_point_appends_point_rotate_def():
    with new_builder_context() as builder:
        center = point(0, 0)
        source = point(1, 0)
        rotated = rotate_point(source, center, math.pi / 2)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, PointRotate) and d.id == rotated.id]
    assert len(defs) == 1
    assert defs[0].center == center.id
    assert defs[0].source == source.id
    assert defs[0].angle == math.pi / 2


def test_rotate_point_rotates_counterclockwise_by_a_positive_angle():
    with new_builder_context() as builder:
        center = point(0, 0)
        source = point(1, 0)
        rotated = rotate_point(source, center, math.pi / 2)
        ir = builder.build()
    sym = compile_defs(ir)
    rx, ry = float(sym[rotated.id].x), float(sym[rotated.id].y)
    assert math.isclose(rx, 0.0, abs_tol=1e-9)
    assert math.isclose(ry, 1.0, abs_tol=1e-9)
