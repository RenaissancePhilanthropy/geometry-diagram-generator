"""Curve length / perimeter helper: circular closed forms, elliptical accuracy.

Elliptical references use direct mpmath quadrature of the arc-length integrand
over an independently chosen parametric sweep (never the helper's own
elliptic-integral code path).
"""

from __future__ import annotations

import math

import mpmath
import pytest
import sympy
import sympy.geometry as spg

from geometry_diagrams.ir.curve_measures import CurveMeasureError, curve_length
from geometry_diagrams.ir.to_sympy import Arc, EllipticalArc, EllipticalSector, Sector

TAU = 2 * math.pi


def _on_ellipse(cx, cy, a, b, t):
    return spg.Point(cx + a * math.cos(t), cy + b * math.sin(t))


def _ref_length(a, b, t0, t1):
    with mpmath.workdps(30):
        f = lambda t: mpmath.sqrt((a * mpmath.sin(t)) ** 2 + (b * mpmath.cos(t)) ** 2)
        # split at quarter turns so quadrature stays accurate over long sweeps
        n = max(1, int(math.ceil((t1 - t0) / (math.pi / 2))))
        pts = [t0 + (t1 - t0) * i / n for i in range(n + 1)]
        return float(mpmath.quad(f, pts))


def _close(actual, expected, rel=1e-9):
    assert actual == pytest.approx(expected, rel=rel, abs=0)


# --- circular -------------------------------------------------------------


def test_circle_circumference():
    _close(curve_length(spg.Circle(spg.Point(1, 2), 3)), TAU * 3, 1e-14)


def test_circular_arc_minor_and_reflex_differ():
    c = spg.Point(0, 0)
    s, e = spg.Point(2, 0), spg.Point(0, 2)
    minor = curve_length(Arc(c, s, e, sympy.Integer(2), reflex=False))
    reflex = curve_length(Arc(c, s, e, sympy.Integer(2), reflex=True))
    _close(minor, 2 * math.pi / 2, 1e-14)
    _close(reflex, 2 * 3 * math.pi / 2, 1e-14)


def test_circular_sector_is_curved_edge_only():
    c = spg.Point(0, 0)
    sec = Sector(c, spg.Point(2, 0), spg.Point(0, 2), sympy.Integer(2), reflex=False)
    _close(curve_length(sec), math.pi, 1e-14)


# --- elliptical -----------------------------------------------------------


@pytest.mark.parametrize("a,b", [(5, 3), (10, 1), (1, 10), (7, 7.0)])
def test_full_ellipse_perimeter(a, b):
    ell = spg.Ellipse(spg.Point(0, 0), a, b)
    _close(curve_length(ell), _ref_length(a, b, 0, TAU))


def test_ellipse_perimeter_concentric_offset():
    ell = spg.Ellipse(spg.Point(4, -3), 6, 2)
    _close(curve_length(ell), _ref_length(6, 2, 0, TAU))


ARC_CASES = [
    # (a, b, t_start, t_end, reflex, ref_start, ref_end)
    ("minor", 5, 3, 0.3, 1.2, False, 0.3, 1.2),
    ("reflex", 5, 3, 0.3, 1.2, True, 1.2, 0.3 + TAU),
    ("axis-crossing", 6, 2, 1.0, 2.2, False, 1.0, 2.2),  # crosses t = pi/2
    ("crosses-0", 6, 2, TAU - 0.5, 0.7, False, TAU - 0.5, TAU + 0.7),
    ("eccentric-minor", 10, 1, 0.1, 1.5, False, 0.1, 1.5),
    ("eccentric-reflex", 10, 1, 0.1, 1.5, True, 1.5, 0.1 + TAU),
    ("eccentric-tall", 1, 10, 2.0, 5.0, False, 2.0, 5.0),
    ("eccentric-tall-reflex", 1, 10, 2.0, 3.0, True, 3.0, 2.0 + TAU),
    ("full-turn", 10, 1, 0.7, 0.7, False, 0.7, 0.7 + TAU),
]


@pytest.mark.parametrize("name,a,b,t0,t1,reflex,r0,r1", ARC_CASES, ids=[c[0] for c in ARC_CASES])
@pytest.mark.parametrize("kind", [EllipticalArc, EllipticalSector])
def test_elliptical_arc_and_sector(kind, name, a, b, t0, t1, reflex, r0, r1):
    cx, cy = 1.5, -2.0
    obj = kind(
        spg.Point(cx, cy),
        _on_ellipse(cx, cy, a, b, t0),
        _on_ellipse(cx, cy, a, b, t1),
        sympy.Float(a),
        sympy.Float(b),
        reflex=reflex,
    )
    _close(curve_length(obj), _ref_length(a, b, r0, r1))


def test_elliptical_arc_equal_radii_is_circular():
    cx, cy, r = 0.0, 0.0, 3.0
    obj = EllipticalArc(
        spg.Point(cx, cy),
        _on_ellipse(cx, cy, r, r, 0.4),
        _on_ellipse(cx, cy, r, r, 2.9),
        sympy.Float(r),
        sympy.Float(r),
    )
    _close(curve_length(obj), r * (2.9 - 0.4), 1e-12)


# --- errors ---------------------------------------------------------------


def test_zero_radius_raises_named_error():
    with pytest.raises(CurveMeasureError, match="Arc"):
        curve_length(Arc(spg.Point(0, 0), spg.Point(1, 0), spg.Point(0, 1), sympy.Integer(0)))


def test_zero_radius_elliptical_raises():
    with pytest.raises(CurveMeasureError, match="EllipticalArc"):
        curve_length(
            EllipticalArc(spg.Point(0, 0), spg.Point(1, 0), spg.Point(0, 1), sympy.Float(0), sympy.Float(2))
        )


@pytest.mark.parametrize("bad", [spg.Point(1, 2), spg.Segment(spg.Point(0, 0), spg.Point(1, 1)), "x", None])
def test_non_curve_raises_naming_type(bad):
    with pytest.raises(CurveMeasureError, match=type(bad).__name__):
        curve_length(bad)


def test_error_is_value_error():
    assert issubclass(CurveMeasureError, ValueError)


def _spy_ellipe(monkeypatch):
    import geometry_diagrams.ir.curve_measures as cm

    calls = []
    real = cm.mpmath.ellipe

    def spy(*a, **k):
        calls.append(a)
        return real(*a, **k)

    monkeypatch.setattr(cm.mpmath, "ellipe", spy)
    return calls


def test_near_equal_radii_take_the_circular_path_like_radii_equal(monkeypatch):
    # Radii within 1e-12 relative are "equal" under the shared radii_equal (1e-9) helper, so the
    # closed-form circular length is used and the elliptic integral is never evaluated.
    calls = _spy_ellipe(monkeypatch)
    a = 3.0
    b = a * (1 + 1e-12)
    ell = spg.Ellipse(spg.Point(0, 0), hradius=a, vradius=b)
    _close(curve_length(ell), 2 * math.pi * a, 1e-9)
    arc = EllipticalArc(
        spg.Point(0, 0),
        _on_ellipse(0.0, 0.0, a, b, 0.4),
        _on_ellipse(0.0, 0.0, a, b, 2.9),
        sympy.Float(a),
        sympy.Float(b),
    )
    _close(curve_length(arc), a * (2.9 - 0.4), 1e-9)
    assert calls == []


def test_radii_differing_by_1e3_relative_still_take_the_elliptic_path(monkeypatch):
    calls = _spy_ellipe(monkeypatch)
    a = 3.0
    ell = spg.Ellipse(spg.Point(0, 0), hradius=a, vradius=a * (1 + 1e-3))
    curve_length(ell)
    assert calls
