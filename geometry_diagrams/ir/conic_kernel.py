"""Numeric conic kernel: circle/ellipse pairs, tilted or not, plus the closed
forms for line x ellipse and tangents from a point.

numpy only, no SymPy and no imports from the rest of the package (the
tolerances come in as arguments, so ``to_sympy`` stays their one home). It
works on ``EllipseFrame``, the float description of an ellipse: center, the
two semi-axes (``a`` along the rotation, ``b`` across it) and the rotation in
radians. The frame is the one place the rotation math lives: ``to_local`` /
``to_world`` / ``point_at`` / ``param_of`` are used by the compiled tilted
marker, by arcs (rotation 0) and by the renderers, never recomputed.

Ellipse x ellipse (a circle is an ellipse with a == b) substitutes
t = tan(theta/2) into the second conic's implicit equation along the first
ellipse's parametric curve, which gives a quartic in t. Roots are never
trusted for their imaginary part (``np.roots`` is only accurate to about 1e-8
near a double root); every plausible root is Newton-polished and classified by
the measured gap, ``f / |grad f|``, a length on the second conic. See
docs/specs/2026-10-25-rotated-ellipses-design.md.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

_TWO_PI = 2.0 * math.pi
_ROOT_GAP = 1e-12        # a polished root with a gap this small (times the scale) is a crossing
_IMAG_SLACK = 1e-2       # np.roots candidates: |imag| <= this * (1 + |re|)
_CLUSTER_RAD = 0.05      # real roots closer than this (radians) may be one touching pair
_COINCIDENT_REL = 1e-9   # normalized implicit coefficients closer than this: the same curve

Point = tuple[float, float]


class CoincidentConicsError(ValueError):
    """Two conics are the same curve: they share infinitely many points."""


@dataclass(frozen=True)
class EllipseFrame:
    """An ellipse as floats. ``rotation`` is radians counter-clockwise from +x
    to the ``a`` axis; the parametric angle t is measured in the ellipse's own
    frame from that axis, ``point_at(t) = center + R(rotation) (a cos t, b sin t)``."""

    cx: float
    cy: float
    a: float
    b: float
    rotation: float = 0.0
    _cos: float = field(init=False, repr=False, compare=False)
    _sin: float = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_cos", math.cos(self.rotation))
        object.__setattr__(self, "_sin", math.sin(self.rotation))

    def to_local(self, x: float, y: float) -> Point:
        dx, dy = x - self.cx, y - self.cy
        return dx * self._cos + dy * self._sin, -dx * self._sin + dy * self._cos

    def to_world(self, u: float, v: float) -> Point:
        return self.cx + u * self._cos - v * self._sin, self.cy + u * self._sin + v * self._cos

    def point_at(self, t: float) -> Point:
        return self.to_world(self.a * math.cos(t), self.b * math.sin(t))

    def param_of(self, x: float, y: float) -> float:
        """Parametric angle of a world point (the inverse of ``point_at`` on the curve)."""
        u, v = self.to_local(x, y)
        return math.atan2(v / self.b, u / self.a)

    def implicit(self, x: float, y: float) -> float:
        """(u/a)^2 + (v/b)^2 - 1: negative inside, zero on the curve, positive outside."""
        u, v = self.to_local(x, y)
        return u * u / (self.a * self.a) + v * v / (self.b * self.b) - 1.0

    def boundary_gap(self, x: float, y: float) -> float:
        """Signed distance-like gap of a world point from the curve, ``f / |grad f|``
        (positive outside). A length, so one tolerance means the same for a long thin
        ellipse as for a round one; inf at the center, where the gradient vanishes."""
        u, v = self.to_local(x, y)
        a2, b2 = self.a * self.a, self.b * self.b
        f = u * u / a2 + v * v / b2 - 1.0
        grad = 2.0 * math.hypot(u / a2, v / b2)
        return f / grad if grad else math.inf

    def half_widths(self) -> Point:
        """Half-width and half-height of the axis-aligned box around the curve."""
        return math.hypot(self.a * self._cos, self.b * self._sin), math.hypot(self.a * self._sin, self.b * self._cos)

    def line_to_local(self, a: float, b: float, c: float) -> tuple[float, float, float]:
        """Coefficients of ``a x + b y + c = 0`` in the ellipse's frame (origin at the center)."""
        return (
            a * self._cos + b * self._sin,
            -a * self._sin + b * self._cos,
            c + a * self.cx + b * self.cy,
        )


# ---------------------------------------------------------------------------
# Ellipse x ellipse (circle x ellipse in either operand order)
# ---------------------------------------------------------------------------

def _coefficients(e: EllipseFrame) -> np.ndarray:
    """Implicit A x^2 + B xy + C y^2 + D x + E y + F = 0, normalized so the form
    equals (u/a)^2 + (v/b)^2 - 1."""
    c, s, a2, b2 = e._cos, e._sin, e.a * e.a, e.b * e.b
    A = c * c / a2 + s * s / b2
    B = 2 * c * s * (1 / a2 - 1 / b2)
    C = s * s / a2 + c * c / b2
    D = -2 * A * e.cx - B * e.cy
    E_ = -B * e.cx - 2 * C * e.cy
    F = A * e.cx * e.cx + B * e.cx * e.cy + C * e.cy * e.cy - 1.0
    return np.array([A, B, C, D, E_, F])


def _coincident(e1: EllipseFrame, e2: EllipseFrame) -> bool:
    q1, q2 = _coefficients(e1), _coefficients(e2)
    q1, q2 = q1 / np.linalg.norm(q1), q2 / np.linalg.norm(q2)
    return bool(
        np.linalg.norm(q1 - q2) <= _COINCIDENT_REL or np.linalg.norm(q1 + q2) <= _COINCIDENT_REL
    )


def _quartic(e1: EllipseFrame, e2: EllipseFrame) -> np.ndarray:
    """e2's implicit form along e1's curve in t = tan(theta/2), times (1 + t^2)^2.
    ``np.convolve``, never ``np.polymul``: polymul strips leading zeros, which
    breaks a circle operand."""
    A, B, C, D, E_, F = _coefficients(e2)
    one = np.array([1.0, 0.0, 1.0])     # 1 + t^2        (highest degree first)
    cosq = np.array([-1.0, 0.0, 1.0])   # 1 - t^2
    sinq = np.array([0.0, 2.0, 0.0])    # 2 t
    c, s = e1._cos, e1._sin
    X = e1.cx * one + e1.a * c * cosq - e1.b * s * sinq
    Y = e1.cy * one + e1.a * s * cosq + e1.b * c * sinq
    cv = np.convolve
    return A * cv(X, X) + B * cv(X, Y) + C * cv(Y, Y) + D * cv(X, one) + E_ * cv(Y, one) + F * cv(one, one)


def intersect_conics(
    e1: EllipseFrame,
    e2: EllipseFrame,
    *,
    tangent_tol: float,
    merge_tol: float,
    ids: tuple[str, str] = ("first", "second"),
) -> list[Point]:
    """World points where two ellipses (circles included) meet, ordered by e1's
    parametric angle. A pair whose measured gap is at most ``tangent_tol`` times
    the scale touches (one point, whichever side it falls on); candidates closer
    than ``merge_tol`` times the scale are one point. Raises
    ``CoincidentConicsError`` naming both ids for two copies of one curve."""
    if _coincident(e1, e2):
        raise CoincidentConicsError(
            f"{ids[0]!r} and {ids[1]!r} are the same curve, so they share infinitely many points"
        )
    scale = max(e1.a, e1.b, e2.a, e2.b, abs(e1.cx), abs(e1.cy), abs(e2.cx), abs(e2.cy)) or 1.0
    tol = tangent_tol * scale

    def f(th: float) -> float:
        return e2.implicit(*e1.point_at(th))

    def gap(th: float) -> float:
        return e2.boundary_gap(*e1.point_at(th))

    def newton_root(th: float) -> float:
        for _ in range(60):
            fv, h = f(th), 1e-7
            dv = (f(th + h) - f(th - h)) / (2 * h)
            if dv == 0:
                break
            step = max(-0.3, min(0.3, fv / dv))
            th -= step
            if abs(step) < 1e-15:
                break
        return th

    def extremum(th: float) -> float:
        for _ in range(80):
            h = 1e-5
            d1 = (f(th + h) - f(th - h)) / (2 * h)
            d2 = (f(th + h) - 2 * f(th) + f(th - h)) / (h * h)
            if d2 == 0:
                break
            step = max(-0.3, min(0.3, d1 / d2))
            th -= step
            if abs(step) < 1e-13:
                break
        return th

    # theta = pi (t = infinity) is unreachable by the substitution: always probe it.
    candidates = [math.pi]
    poly = _quartic(e1, e2)
    if abs(poly[0]) / (np.abs(poly).max() or 1.0) > 1e-14:
        candidates += [
            2 * math.atan(float(r.real)) for r in np.roots(poly) if abs(r.imag) <= _IMAG_SLACK * (1 + abs(r.real))
        ]
    roots: list[float] = []
    touches: list[float] = []
    for th in candidates:
        tr = newton_root(th)
        if abs(gap(tr)) <= _ROOT_GAP * scale:
            roots.append(tr % _TWO_PI)
        else:
            te = extremum(th)
            if abs(gap(te)) <= tol:
                touches.append(te % _TWO_PI)
    roots = sorted({round(r, 11) for r in roots})
    # Merge clusters: two real roots a hair apart whose in-between extremum is within
    # tolerance are one touching pair (their separation is rounding, not geometry).
    changed = True
    while changed and len(roots) >= 2:
        changed = False
        for i in range(len(roots)):
            j = (i + 1) % len(roots)
            d = math.remainder(roots[j] - roots[i], _TWO_PI)
            if abs(d) < _CLUSTER_RAD:
                tm = extremum(roots[i] + d / 2)
                if abs(gap(tm)) <= tol:
                    roots = sorted([r for k, r in enumerate(roots) if k not in (i, j)] + [tm % _TWO_PI])
                    changed = True
                    break
    thetas = roots + [
        t for t in touches if all(abs(math.remainder(t - r, _TWO_PI)) > 1e-6 for r in roots)
    ]
    points: list[Point] = []
    for th in sorted(thetas):
        p = e1.point_at(th)
        if not any(math.dist(p, q) <= merge_tol * scale for q in points):
            points.append(p)
    return points


# ---------------------------------------------------------------------------
# Line / segment / ray x ellipse, tangents from a point
# ---------------------------------------------------------------------------

def line_ellipse_crossings(
    e: EllipseFrame, p: Point, q: Point, *, kind: str, slack: float,
) -> list[Point]:
    """World points where the line through p and q (``kind`` "line", "segment"
    or "ray" from p toward q) crosses the ellipse: the quadratic in the line's
    parameter, solved in the ellipse's frame. ``slack`` is a length by which a
    segment/ray end may miss the curve and still count. A tangent line that
    the discriminant sees as just missing is the caller's snap to catch."""
    (u0, v0), (u1, v1) = e.to_local(*p), e.to_local(*q)
    du, dv = u1 - u0, v1 - v0
    qa = (du / e.a) ** 2 + (dv / e.b) ** 2
    qb = 2 * (u0 * du / (e.a * e.a) + v0 * dv / (e.b * e.b))
    qc = (u0 / e.a) ** 2 + (v0 / e.b) ** 2 - 1.0
    disc = qb * qb - 4 * qa * qc
    length = math.hypot(du, dv)
    if qa == 0 or disc < 0 or length == 0:
        return []
    root = math.sqrt(disc)
    lo = -slack / length
    out: list[Point] = []
    for s in sorted({(-qb - root) / (2 * qa), (-qb + root) / (2 * qa)}):
        if kind == "segment" and not (lo <= s <= 1 - lo):
            continue
        if kind == "ray" and s < lo:
            continue
        out.append(e.to_world(u0 + s * du, v0 + s * dv))
    return out


def tangent_touch_points(e: EllipseFrame, x: float, y: float, *, tol: float) -> list[Point]:
    """Touch points of the tangents from (x, y): two for an external point, the
    point itself for one within ``tol`` (a length) of the curve, none inside.
    Solves (u/a) cos t + (v/b) sin t = 1 in the ellipse's frame."""
    u, v = e.to_local(x, y)
    ru, rv = u / e.a, v / e.b
    r = math.hypot(ru, rv)
    if abs(e.boundary_gap(x, y)) <= tol:
        return [e.point_at(math.atan2(rv, ru))]
    if r < 1.0:
        return []
    d, w = math.atan2(rv, ru), math.acos(1.0 / r)
    return [e.point_at(d + w), e.point_at(d - w)]


def touch_point_for_line(e: EllipseFrame, a: float, b: float, c: float) -> Point:
    """Where the tangent line ``a x + b y + c = 0`` touches the ellipse: of the
    two points whose tangent has the line's direction, the one nearer the line."""
    al, bl, cl = e.line_to_local(a, b, c)
    theta0 = math.atan2(e.b * bl, e.a * al)
    best = None
    for theta in (theta0, theta0 + math.pi):
        u, v = e.a * math.cos(theta), e.b * math.sin(theta)
        miss = abs(al * u + bl * v + cl)
        if best is None or miss < best[0]:
            best = (miss, u, v)
    return e.to_world(best[1], best[2])
