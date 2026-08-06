"""Tests for geometry_diagrams/ir/render_util.py."""
import math

import pytest

from geometry_diagrams.ir.render_util import tick_values


def test_tick_values_excludes_zero():
    assert 0 not in tick_values(-4, 4, 1)


def test_tick_values_excludes_endpoints_when_on_step():
    # Canvas boundary 0..7000 at step 1000: 7000 is the axis arrowhead's own
    # endpoint — a tick there overlaps the arrowhead and must be excluded.
    values = tick_values(0, 7000, 1000)
    assert 7000 not in values
    assert 0 not in values
    assert values == [1000, 2000, 3000, 4000, 5000, 6000]


def test_tick_values_excludes_negative_endpoint():
    values = tick_values(-3000, 3000, 1000)
    assert -3000 not in values
    assert 3000 not in values
    assert values == [-2000, -1000, 1000, 2000]


def test_tick_values_keeps_interior_values_when_endpoints_not_on_step():
    # Endpoints not exact multiples of step -> nothing to exclude beyond 0.
    values = tick_values(-3.5, 3.5, 1)
    assert values == [-3, -2, -1, 1, 2, 3]


def test_elliptical_arc_params_recovers_correct_angle_not_plain_atan2():
    """The exact Fable-verified worked example: hradius=4, vradius=1, t=60deg.

    Point on the ellipse at parametric angle t=60 degrees is
    (4*cos(60), 1*sin(60)) = (2.0, 0.8660...). The correct parametric-angle
    recovery formula atan2((y-cy)/vr, (x-cx)/hr) gives back 60.0 degrees.
    Plain atan2(y-cy, x-cx) gives 23.413 degrees -- a ~36.6 degree error --
    and feeding that wrong angle back into the parametric form
    (cx + hr*cos(t), cy + vr*sin(t)) lands nowhere near the original point.
    """
    from geometry_diagrams.ir.ir import DiagramIR, EllipticalArcCenterStartEnd, PointFixed
    from geometry_diagrams.ir.render_util import elliptical_arc_params
    from geometry_diagrams.ir.to_sympy import compile_defs

    t = math.radians(60.0)
    hr, vr = 4.0, 1.0
    sx, sy = hr * math.cos(t), vr * math.sin(t)
    assert sx == pytest.approx(2.0, abs=1e-3)
    assert sy == pytest.approx(0.8660, abs=1e-3)

    sym = compile_defs(DiagramIR(define=[
        PointFixed(id="c", x=0, y=0),
        PointFixed(id="s", x=sx, y=sy),
        PointFixed(id="e", x=0, y=vr),  # t=90deg
        EllipticalArcCenterStartEnd(id="ea1", center="c", hradius=hr, vradius=vr, start="s", end="e"),
    ]))
    cx, cy, hr_out, vr_out, s_deg, e_deg, sx_out, sy_out = elliptical_arc_params("ea1", sym)

    # Correct formula recovers the true start angle:
    assert s_deg == pytest.approx(60.0, abs=0.01)

    # Sanity: the WRONG plain-atan2 formula would have given ~23.413 degrees,
    # a completely different and incorrect angle -- assert the two disagree
    # by roughly the expected error margin, pinning the bug this fixes.
    wrong_deg = math.degrees(math.atan2(sy_out - cy, sx_out - cx)) % 360.0
    assert wrong_deg == pytest.approx(23.413, abs=0.01)
    assert abs(s_deg - wrong_deg) == pytest.approx(36.587, abs=0.01)


def test_expand_bounds_for_geometry_includes_elliptical_arc():
    from geometry_diagrams.ir.ir import DiagramIR, EllipticalArcCenterStartEnd, PointFixed
    from geometry_diagrams.ir.render_util import BOUNDS_PADDING, expand_bounds_for_geometry
    from geometry_diagrams.ir.to_sympy import compile_defs

    sym = compile_defs(DiagramIR(define=[
        PointFixed(id="c", x=0, y=0),
        PointFixed(id="s", x=4, y=0),
        PointFixed(id="e", x=0, y=1),
        EllipticalArcCenterStartEnd(id="ea1", center="c", hradius=4, vradius=1, start="s", end="e"),
    ]))
    xmin, xmax, ymin, ymax = expand_bounds_for_geometry(0.0, 0.0, 0.0, 0.0, sym)
    assert xmin == pytest.approx(-4.0 - BOUNDS_PADDING)
    assert xmax == pytest.approx(4.0 + BOUNDS_PADDING)
    assert ymin == pytest.approx(-1.0 - BOUNDS_PADDING)
    assert ymax == pytest.approx(1.0 + BOUNDS_PADDING)
