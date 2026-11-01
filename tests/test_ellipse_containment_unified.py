"""One containment metric for ellipses: the length-based EllipseFrame.boundary_gap,
for axis-aligned and tilted ellipses and elliptical arcs/sectors alike."""
from __future__ import annotations

import math

import pytest
import sympy as sp
import sympy.geometry as spg

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.checks import _contains
from geometry_diagrams.ir.errors import IRCompileError
from geometry_diagrams.ir.to_sympy import EllipticalArc, compile_defs, point_on_arc

CANVAS = {"xmin": -500, "xmax": 500, "ymin": -500, "ymax": 500}
A, B = 4.0, 2.0


def _pt(x, y):
    return spg.Point(x, y)


def _ellipse_sym(rotation_deg):
    d = ir.DiagramIR.model_validate({"canvas": CANVAS, "define": [
        {"id": "O", "kind": "point_fixed", "x": 0, "y": 0},
        {"id": "E", "kind": "ellipse_center_axes", "center": "O", "hradius": A, "vradius": B,
         "rotation_deg": rotation_deg},
    ]})
    return compile_defs(d)["E"]


def _outside(gap):
    """A point on the +x vertex pushed ``gap`` (a length) outside the ellipse."""
    return _pt(A + gap, 0.0)


@pytest.mark.parametrize("gap,tol,expected", [
    (0.001, 5e-3, True), (0.004, 5e-3, True), (0.02, 5e-3, False), (0.02, 0.05, True),
])
def test_axis_aligned_ellipse_uses_length_gap(gap, tol, expected):
    assert _contains(_ellipse_sym(0), _outside(gap), tol) is expected


@pytest.mark.parametrize("gap", [0.001, 0.004, 0.006, 0.02])
def test_axis_aligned_agrees_with_tilted_marker(gap):
    # A zero rotation is an exact spg.Ellipse, a tiny nonzero one the tilted
    # marker; the same borderline point must get the same verdict from both.
    p = _pt(A + gap, 0.0)
    flat, tilted = _ellipse_sym(0), _ellipse_sym(1e-6)
    assert type(flat) is not type(tilted)
    assert _contains(flat, p, 5e-3) == _contains(tilted, p, 5e-3)


def _arc(hr, vr):
    d = ir.DiagramIR.model_validate({"canvas": CANVAS, "define": [
        {"id": "O", "kind": "point_fixed", "x": 0, "y": 0},
        {"id": "S", "kind": "point_fixed", "x": hr, "y": 0},
        {"id": "T", "kind": "point_fixed", "x": 0, "y": vr},
        {"id": "AR", "kind": "elliptical_arc_center_start_end", "center": "O",
         "hradius": hr, "vradius": vr, "start": "S", "end": "T"},
    ]})
    return compile_defs(d)["AR"]


def test_elliptical_arc_uses_length_gap_within_sweep():
    arc = _arc(A, B)
    t = math.radians(40)
    on = _pt(A * math.cos(t), B * math.sin(t))
    assert point_on_arc(on, arc, 1e-9)
    # pushed outward along the (approximate) normal by 0.004 / 0.02 lengths
    nx, ny = B * math.cos(t), A * math.sin(t)
    n = math.hypot(nx, ny)
    near = _pt(on.x + 0.004 * nx / n, on.y + 0.004 * ny / n)
    far = _pt(on.x + 0.02 * nx / n, on.y + 0.02 * ny / n)
    assert point_on_arc(near, arc, 5e-3)
    assert not point_on_arc(far, arc, 5e-3)
    # outside the sweep (third quadrant) is not on the arc
    t2 = math.radians(220)
    assert not point_on_arc(_pt(A * math.cos(t2), B * math.sin(t2)), arc, 5e-3)


@pytest.mark.parametrize("hr,vr", [(0, 2), (3, 0)])
def test_zero_radius_is_a_clean_error(hr, vr):
    o = _pt(0, 0)
    arc = EllipticalArc(o, _pt(1, 0), _pt(0, 1), sp.S(hr), sp.S(vr))
    with pytest.raises(IRCompileError, match="radius"):
        point_on_arc(_pt(1, 0), arc, 5e-3)
