"""The numeric conic kernel (ir/conic_kernel.py): circle/ellipse pairs, tilted or not.

Expectations are independent of the kernel: designed cases have a count known
by construction, random cases are checked against a brute-force oracle (a dense
sign-change count of the second conic's implicit form along the first curve),
and near-tangent cases follow the tolerance policy (a gap at or below
INTERSECT_TANGENT_TOL times the scale is one touch point, a larger positive
gap is a miss, a larger negative gap is two crossings).

The batteries run at the sizes the design note quotes (about 8 s in all).
"""
from __future__ import annotations

import math
import random

import numpy as np
import pytest

from geometry_diagrams.ir.conic_kernel import (
    CoincidentConicsError,
    EllipseFrame,
    intersect_conics,
    line_ellipse_crossings,
    tangent_touch_points,
    touch_point_for_line,
)
from geometry_diagrams.ir.to_sympy import INTERSECT_MERGE_TOL, INTERSECT_TANGENT_TOL


def E(cx, cy, a, b, deg=0.0):
    return EllipseFrame(cx, cy, a, b, math.radians(deg))


def isect(e1, e2, ids=("first", "second")):
    return intersect_conics(e1, e2, tangent_tol=INTERSECT_TANGENT_TOL, merge_tol=INTERSECT_MERGE_TOL, ids=ids)


# --- the oracle: brute force, independent of the kernel ----------------------

def oracle_count(e1, e2, n=200_000):
    """Sign changes of e2's implicit form along e1's curve, built from the
    textbook formulas here (not from the kernel's own helpers)."""
    t = (np.arange(n) + 0.5) * (2 * math.pi / n)  # never exactly on a multiple of pi/2
    c1, s1 = math.cos(e1.rotation), math.sin(e1.rotation)
    u, v = e1.a * np.cos(t), e1.b * np.sin(t)
    x, y = e1.cx + u * c1 - v * s1, e1.cy + u * s1 + v * c1
    c2, s2 = math.cos(e2.rotation), math.sin(e2.rotation)
    du, dv = x - e2.cx, y - e2.cy
    p, q = du * c2 + dv * s2, -du * s2 + dv * c2
    f = (p / e2.a) ** 2 + (q / e2.b) ** 2 - 1.0
    return int(np.sum(f * np.roll(f, -1) < 0))


def scale_of(*es):
    return max(max(e.a, e.b, abs(e.cx), abs(e.cy)) for e in es) or 1.0


def outward_point(e, th):
    """(point on e at parametric angle th, unit outward normal)."""
    px, py = e.point_at(th)
    c, s = math.cos(e.rotation), math.sin(e.rotation)
    nu, nv = math.cos(th) / e.a, math.sin(th) / e.b
    nx, ny = nu * c - nv * s, nu * s + nv * c
    n = math.hypot(nx, ny)
    return px, py, nx / n, ny / n


def random_ellipse(rng, tilted=True):
    return E(
        rng.uniform(-2, 2), rng.uniform(-2, 2), rng.uniform(1, 6), rng.uniform(0.4, 3),
        rng.uniform(0, 180) if tilted else 0.0,
    )


# --- designed cases -----------------------------------------------------------

A = E(0.3, -0.2, 4, 2, 20)
TIP = A.point_at(0.0)
NORMAL = (math.cos(A.rotation), math.sin(A.rotation))


def _leading_coefficient(e1, e2):
    from geometry_diagrams.ir.conic_kernel import _quartic

    poly = _quartic(e1, e2)
    return abs(poly[0]) / np.abs(poly).max()


def test_circle_operand_with_a_leading_zero_quartic_works():
    # e2 passes through e1's theta = pi point, so the quartic's leading coefficient
    # (e2's implicit value there) is zero: the roots at other angles must survive.
    e1, e2 = E(0, 0, 1, 1), E(0, 1, math.sqrt(2), math.sqrt(2))
    assert _leading_coefficient(e1, e2) < 1e-14  # the setup really is the leading-zero case
    for a_, b_ in ((e1, e2), (e2, e1)):
        pts = isect(a_, b_)
        assert sorted(round(x, 9) for x, _ in pts) == [-1.0, 1.0]
        for x, y in pts:
            assert y == pytest.approx(0.0, abs=1e-9)


def test_a_pair_crossing_at_four_points_gives_all_four():
    pts = isect(E(0, 0, 5, 2), E(0.2, 0.1, 2.1, 4.7))
    assert len(pts) == 4


def test_coincident_conics_raise_a_typed_error_naming_both_ids():
    with pytest.raises(CoincidentConicsError) as exc:
        isect(A, E(A.cx, A.cy, A.a, A.b, 20 + 180), ids=("ell_a", "ell_b"))
    assert "ell_a" in str(exc.value) and "ell_b" in str(exc.value)


def test_a_circle_is_coincident_with_itself_whatever_its_tilt():
    with pytest.raises(CoincidentConicsError):
        isect(E(1, 1, 2, 2, 0), E(1, 1, 2, 2, 33))


@pytest.mark.parametrize("off, expected", [
    (0.0, 1), (1e-9, 1), (-1e-9, 1), (3e-9, 1), (-3e-9, 1), (1e-7, 0), (-1e-7, 2), (1e-6, 0), (-1e-6, 2),
])
def test_circle_touching_a_tilted_tip_from_outside(off, expected):
    r = 3
    c = E(TIP[0] + NORMAL[0] * (r + off), TIP[1] + NORMAL[1] * (r + off), r, r)
    assert len(isect(A, c)) == expected
    assert len(isect(c, A)) == expected


def test_osculating_circle_at_a_tip_touches_once_in_both_orders():
    rc = A.b ** 2 / A.a
    c = E(TIP[0] - NORMAL[0] * rc, TIP[1] - NORMAL[1] * rc, rc, rc)
    assert len(isect(A, c)) == 1
    assert len(isect(c, A)) == 1


def test_thin_ellipse_against_a_circle_in_both_orders():
    thin, circle = E(0, 0, 5, 0.005, 25), E(0, 0, 2, 2)
    assert len(isect(circle, thin)) == 4
    assert len(isect(thin, circle)) == 4
    assert isect(thin, E(0, 0, 6, 6)) == []


def test_a_1e5_scale_ratio_pair_crosses_at_two_points():
    big = E(0, 0, 1000, 600, 33)
    tip = big.point_at(0.0)
    small = E(tip[0], tip[1], 0.01, 0.005, 70)
    assert len(isect(big, small)) == 2
    assert len(isect(small, big)) == 2


@pytest.mark.parametrize("deg", [0, 90, 180, 360, -90])
def test_tilt_exactly_a_quarter_or_half_turn(deg):
    e2 = E(1.0, 0.5, 3, 2, deg)
    assert len(isect(A, e2)) == oracle_count(A, e2)


@pytest.mark.parametrize("eps, expected", [(1e-2, 4), (1e-6, 4), (1e-8, 4), (1e-10, 2)])
def test_concentric_circle_just_above_the_minor_axis(eps, expected):
    assert len(isect(A, E(A.cx, A.cy, A.b + eps, A.b + eps))) == expected


def test_concentric_ellipses():
    assert isect(A, E(A.cx, A.cy, 3, 1, 20)) == []
    assert len(isect(A, E(A.cx, A.cy, 2, 4, 20))) == 4
    assert len(isect(A, E(A.cx, A.cy, 4, 2, 0))) == 4


def test_intersection_points_lie_on_both_curves():
    rng = random.Random(1)
    for _ in range(50):
        e1, e2 = random_ellipse(rng), random_ellipse(rng)
        for x, y in isect(e1, e2):
            assert abs(e1.boundary_gap(x, y)) < 1e-9 * scale_of(e1, e2)
            assert abs(e2.boundary_gap(x, y)) < 1e-9 * scale_of(e1, e2)


# --- contacts exactly at the first curve's theta = pi (the substitution's blind spot) ---

def _through(e, th, center):
    """Circle about ``center`` through e's point at parametric angle th."""
    x, y = e.point_at(th)
    r = math.hypot(x - center[0], y - center[1])
    return E(center[0], center[1], r, r)


def test_ellipse_and_circle_meeting_at_theta_pi_keep_every_crossing():
    e1, c = E(0, 0, 2, 1), E(0, 1, math.sqrt(5), math.sqrt(5))
    assert _leading_coefficient(e1, c) < 1e-14
    assert len(isect(e1, c)) == len(isect(c, e1)) == oracle_count(e1, c) == 4


def test_tilted_ellipse_and_circle_through_two_of_its_points_one_at_theta_pi():
    e1 = E(1, 2, 3, 1, 30)
    for th2 in (1.0, 2.2, 4.1):
        (x1, y1), (x2, y2) = e1.point_at(math.pi), e1.point_at(th2)
        mx, my, dx, dy = (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1
        c = _through(e1, math.pi, (mx - dy * 0.8, my + dx * 0.8))  # center on the chord's bisector
        assert _leading_coefficient(e1, c) < 1e-14
        expected = oracle_count(e1, c)
        assert expected >= 2
        assert len(isect(e1, c)) == len(isect(c, e1)) == expected


def test_concentric_circle_touching_both_tips_of_a_tilted_ellipse():
    e1 = E(1, 2, 3, 1, 30)
    c = E(1, 2, 3, 3)  # touches the tilted ellipse at theta = 0 and theta = pi
    assert _leading_coefficient(e1, c) < 1e-14
    assert len(isect(e1, c)) == len(isect(c, e1)) == 2


def test_circle_touching_at_theta_pi_gives_one_point_in_both_orders():
    e1 = E(0.3, -0.2, 4, 2, 20)
    tx, ty = e1.point_at(math.pi)
    r = 1.5
    c = E(tx - math.cos(e1.rotation) * r, ty - math.sin(e1.rotation) * r, r, r)  # outside, tangent at the -a tip
    assert len(isect(e1, c)) == len(isect(c, e1)) == 1


@pytest.mark.parametrize("th", [0.0, math.pi / 2, math.pi, 3 * math.pi / 2])
@pytest.mark.parametrize("tilted", [False, True])
def test_random_circles_through_a_fixed_parametric_point_match_the_oracle(th, tilted):
    rng = random.Random(int(th * 10) + (100 if tilted else 0))
    wrong = []
    for _ in range(100):
        e1 = random_ellipse(rng, tilted)
        c = _through(e1, th, (rng.uniform(-3, 3), rng.uniform(-3, 3)))
        if c.a < 1e-3:
            continue
        expected = oracle_count(e1, c)
        for a_, b_ in ((e1, c), (c, e1)):
            if len(isect(a_, b_)) != expected:
                wrong.append((e1, c, expected))
    assert wrong == []


@pytest.mark.parametrize("th", [0.0, math.pi / 2, math.pi, 3 * math.pi / 2])
def test_random_axis_aligned_ellipses_sharing_a_point_at_a_fixed_angle(th):
    # e2 is scaled so e1's point at th lies exactly on its curve.
    rng = random.Random(int(th * 10) + 7)
    wrong = []
    for _ in range(100):
        e1 = random_ellipse(rng, False)
        px, py = e1.point_at(th)
        cx, cy = rng.uniform(-3, 3), rng.uniform(-3, 3)
        a2 = rng.uniform(1, 6)
        k = ((px - cx) / a2) ** 2
        if k >= 0.95:
            continue
        b2 = abs(py - cy) / math.sqrt(1 - k)
        if b2 < 0.3:
            continue
        e2 = E(cx, cy, a2, b2)
        expected = oracle_count(e1, e2)
        for a_, b_ in ((e1, e2), (e2, e1)):
            if len(isect(a_, b_)) != expected:
                wrong.append((e1, e2, expected))
    assert wrong == []


# --- batteries vs the brute-force oracle ---------------------------------------

def _near_tangent_cases(seed, n, internal):
    rng = random.Random(seed)
    cases = []
    while len(cases) < n:
        e1 = random_ellipse(rng)
        th = rng.uniform(0, 2 * math.pi)
        px, py, nx, ny = outward_point(e1, th)
        if internal:
            u, v = e1.to_local(px, py)
            roc = (e1.a ** 2 * e1.b ** 2) * (u * u / e1.a ** 4 + v * v / e1.b ** 4) ** 1.5
            r = rng.uniform(0.2, 0.8) * min(roc, min(e1.a, e1.b))
            sgn = -1
            probe = E(px - nx * (r + 1e-3), py - ny * (r + 1e-3), r, r)
            if oracle_count(e1, probe, 100_000) != 0:
                continue
        else:
            r = rng.uniform(0.2, 2)
            sgn = 1
            probe = E(px + nx * (r - 1e-3), py + ny * (r - 1e-3), r, r)
            if oracle_count(e1, probe, 100_000) != 2:
                continue
        cases.append((e1, px, py, nx, ny, r, sgn))
    return cases


@pytest.mark.parametrize("internal", [False, True])
def test_near_tangent_offsets_follow_the_tolerance_policy(internal):
    n = 150
    offsets = (0.0, 5e-10, -5e-10, 1e-7, -1e-7, 1e-5, -1e-5)
    wrong = []
    for e1, px, py, nx, ny, r, sgn in _near_tangent_cases(13 if internal else 11, n, internal):
        for off in offsets:
            c = E(px + sgn * nx * (r + off), py + sgn * ny * (r + off), r, r)
            scale = scale_of(e1, c)
            if abs(off) <= INTERSECT_TANGENT_TOL * scale:
                expected = 1
            else:  # off > 0 pushes the circle away (outside) or deeper in (inside): no contact
                expected = 0 if off > 0 else 2
            for a_, b_ in ((e1, c), (c, e1)):
                got = len(isect(a_, b_))
                if got != expected:
                    wrong.append((off, expected, got))
    assert wrong == []


@pytest.mark.parametrize("name, seed, tilted", [("tilted", 3, True), ("float axis-aligned", 5, False)])
def test_random_pairs_match_the_oracle(name, seed, tilted):
    rng = random.Random(seed)
    n = 300
    wrong = []
    for _ in range(n):
        e1, e2 = random_ellipse(rng, tilted), random_ellipse(rng, tilted)
        got = len(isect(e1, e2))
        if got != oracle_count(e1, e2):
            wrong.append((e1, e2, got))
    assert wrong == []


def test_random_circle_against_a_tilted_ellipse_in_both_operand_orders():
    rng = random.Random(7)
    n = 300
    wrong = []
    for _ in range(n):
        e = random_ellipse(rng)
        r = rng.uniform(0.3, 5)
        c = E(rng.uniform(-3, 3), rng.uniform(-3, 3), r, r)
        expected = oracle_count(e, c)
        for a_, b_ in ((e, c), (c, e)):
            if len(isect(a_, b_)) != expected:
                wrong.append((e, c))
    assert wrong == []


# --- line / segment / ray x ellipse (closed form) --------------------------------

def test_line_through_a_tilted_ellipse_crosses_twice():
    e = E(1, -2, 5, 2, 37)
    x, y = e.point_at(0.7)
    pts = line_ellipse_crossings(e, (x - 3, y - 2), (x + 3, y + 2), kind="line", slack=0.0)
    assert len(pts) == 2
    for px, py in pts:
        assert abs(e.boundary_gap(px, py)) < 1e-12
    assert any(math.hypot(px - x, py - y) < 1e-9 for px, py in pts)


def test_ray_and_segment_ranges_are_honoured():
    e = E(0, 0, 3, 1, 90)  # the long axis is vertical
    assert len(line_ellipse_crossings(e, (0, -5), (0, 5), kind="line", slack=0.0)) == 2
    assert len(line_ellipse_crossings(e, (0, -5), (0, 5), kind="segment", slack=0.0)) == 2
    assert len(line_ellipse_crossings(e, (0, -5), (0, -4), kind="segment", slack=0.0)) == 0
    assert len(line_ellipse_crossings(e, (0, -5), (0, -4), kind="ray", slack=0.0)) == 2
    assert len(line_ellipse_crossings(e, (0, 5), (0, 6), kind="ray", slack=0.0)) == 0
    assert line_ellipse_crossings(e, (9, 9), (9, 10), kind="line", slack=0.0) == []


# --- tangents from a point ---------------------------------------------------------

def test_two_tangents_from_an_external_point_touch_the_curve_and_pass_through_it():
    e = E(1, -2, 5, 2, 37)
    px, py = 8.0, 3.0
    touches = tangent_touch_points(e, px, py, tol=1e-9)
    assert len(touches) == 2
    for tx, ty in touches:
        assert abs(e.boundary_gap(tx, ty)) < 1e-12
        # the line P-T is perpendicular to the curve's normal at T
        u, v = e.to_local(tx, ty)
        nu, nv = u / e.a ** 2, v / e.b ** 2
        du, dv = e.to_local(px, py)[0] - u, e.to_local(px, py)[1] - v
        assert abs(nu * du + nv * dv) < 1e-12 * max(1.0, math.hypot(du, dv))


def test_a_point_inside_has_no_tangent_and_a_point_on_the_curve_has_one():
    e = E(1, -2, 5, 2, 37)
    assert tangent_touch_points(e, 1.0, -2.0, tol=1e-9) == []
    assert tangent_touch_points(e, *e.point_at(0.0), tol=1e-9) != []
    on = e.point_at(0.7)
    touches = tangent_touch_points(e, *on, tol=1e-9)
    assert len(touches) == 1
    assert touches[0] == pytest.approx(on, abs=1e-9)


def test_touch_point_of_a_line_is_the_extreme_point_on_the_near_side():
    e = E(0, 0, 3, 1, 90)  # long axis vertical: the curve spans x in [-1, 1], y in [-3, 3]
    assert touch_point_for_line(e, 1.0, 0.0, -1.0) == pytest.approx((1.0, 0.0), abs=1e-12)  # x = 1
    assert touch_point_for_line(e, 1.0, 0.0, 1.0) == pytest.approx((-1.0, 0.0), abs=1e-12)  # x = -1
    assert touch_point_for_line(e, 0.0, 1.0, -3.0) == pytest.approx((0.0, 3.0), abs=1e-12)  # y = 3


# --- the frame ---------------------------------------------------------------------

def test_frame_round_trips_and_matches_hand_computed_axis_ends():
    e = E(1, 2, 3, 1, 30)
    assert e.point_at(0.0) == pytest.approx((1 + 3 * math.cos(math.radians(30)), 2 + 3 * math.sin(math.radians(30))))
    assert e.point_at(math.pi / 2) == pytest.approx((1 - math.sin(math.radians(30)), 2 + math.cos(math.radians(30))))
    for t in (0.3, 1.7, -2.0):
        assert e.param_of(*e.point_at(t)) == pytest.approx(t)
    assert e.to_world(*e.to_local(4.0, -1.0)) == pytest.approx((4.0, -1.0))
    assert e.half_widths() == pytest.approx((math.sqrt(7), math.sqrt(3)))


def test_a_1000_by_0_01_ellipse_gap_is_a_length():
    e = E(0, 0, 1000, 0.01, 35)
    on = e.point_at(1.1)
    assert abs(e.boundary_gap(*on)) < 1e-9
    nx = outward_point(e, 1.1)
    off = (on[0] + nx[2] * 1e-5, on[1] + nx[3] * 1e-5)
    assert e.boundary_gap(*off) == pytest.approx(1e-5, rel=0.05)  # a length, whatever the aspect
