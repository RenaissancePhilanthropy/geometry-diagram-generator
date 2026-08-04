# tests/test_pydsl_point_on_and_rotate.py
"""Tests for point_on(), rotate_point(), reflect_point(), and dilate_point() —
exposing the IR's existing PointOn/PointRotate/PointReflect constructs
(previously only reachable via the DSL), plus a brand-new PointDilate."""
import math

from geometry_diagrams.pydsl.api import (
    dilate_point, line_through, point, point_on, reflect_point, rotate_point,
)
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context
from geometry_diagrams.ir.ir import PointDilate, PointOn, PointOnParam, PointReflect, PointRotate
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


def test_reflect_point_across_a_point_appends_point_reflect_def():
    with new_builder_context() as builder:
        center = point(1, 1)
        source = point(3, 1)
        reflected = reflect_point(source, center)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, PointReflect) and d.id == reflected.id]
    assert len(defs) == 1
    assert defs[0].source == source.id
    assert defs[0].across == center.id


def test_reflect_point_across_a_point_is_point_symmetry():
    with new_builder_context() as builder:
        center = point(1, 1)
        source = point(3, 1)
        reflected = reflect_point(source, center)
        ir = builder.build()
    sym = compile_defs(ir)
    rx, ry = float(sym[reflected.id].x), float(sym[reflected.id].y)
    # 2*center - source = (2*1-3, 2*1-1) = (-1, 1)
    assert math.isclose(rx, -1.0, abs_tol=1e-9)
    assert math.isclose(ry, 1.0, abs_tol=1e-9)


def test_reflect_point_across_a_line_mirrors_it():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(0, 1)  # the y-axis
        mirror = line_through(a, b)
        source = point(3, 2)
        reflected = reflect_point(source, mirror)
        ir = builder.build()
    sym = compile_defs(ir)
    rx, ry = float(sym[reflected.id].x), float(sym[reflected.id].y)
    assert math.isclose(rx, -3.0, abs_tol=1e-9)
    assert math.isclose(ry, 2.0, abs_tol=1e-9)


def test_dilate_point_appends_point_dilate_def():
    with new_builder_context() as builder:
        center = point(1, 1)
        source = point(3, 1)
        dilated = dilate_point(source, center, 2.0)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, PointDilate) and d.id == dilated.id]
    assert len(defs) == 1
    assert defs[0].center == center.id
    assert defs[0].source == source.id
    assert defs[0].ratio == 2.0


def test_dilate_point_scales_about_center():
    with new_builder_context() as builder:
        center = point(1, 1)
        source = point(3, 1)
        dilated = dilate_point(source, center, 2.0)
        ir = builder.build()
    sym = compile_defs(ir)
    dx, dy = float(sym[dilated.id].x), float(sym[dilated.id].y)
    # center + 2*(source-center) = (1,1) + 2*(2,0) = (5, 1)
    assert math.isclose(dx, 5.0, abs_tol=1e-9)
    assert math.isclose(dy, 1.0, abs_tol=1e-9)
