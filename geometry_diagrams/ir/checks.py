from __future__ import annotations

import math
from typing import Any

import sympy.geometry as spg
from pydantic import BaseModel

from . import ir
from .curve_measures import curve_length
from .derived import REGISTRY as DERIVED_REGISTRY, effective_defs
from .to_sympy import (
    Arc,
    EllipticalArc,
    EllipticalSector,
    Sector,
    SymTable,
    _arc_param_frame,
    _point_in_arc_sweep,
    _tangent_touch_point,
    _underlying_conic,
    arc_sweep_degrees,
    point_on_arc,
)


DEFAULT_TOL = 5e-3
# Default relative tolerance of the solid measure checks (prism volume_equals
# and true_length_equals, evaluated by the prism's registry hooks through
# _near_exact). Prism dimensions are exact, so an off-by-one answer must fail
# (DEFAULT_TOL would pass 299 against 300). A check's own ``tol`` overrides
# it; the run-wide default passed to run_checks does not apply to these two
# kinds, and every other kind keeps DEFAULT_TOL.
EXACT_MEASURE_TOL = 1e-9


class UnsupportedOperand(TypeError):
    """An operand a check deliberately does not support (e.g. an elliptical
    arc/sector where only circular ones work).

    A `TypeError` subclass so any caller already catching `TypeError` keeps
    working. `_check_one` reports it as a clean, direct failure message —
    the same shape `_check_congruent_arcs` returns for the same kind of
    rejection — rather than wrapping it in the generic ``Error in <kind>:``
    prefix reserved for unexpected exceptions.
    """


class CheckResult(BaseModel):
    check: ir.CheckBase
    passed: bool
    message: str  # empty string on pass; human-readable explanation on failure


def run_checks(
    checks: list[ir.Check],
    sym: SymTable,
    tol: float = DEFAULT_TOL,
    warnings: list[str] | None = None,
) -> list[CheckResult]:
    """Evaluate each Check against the compiled symbol table.

    ``warnings``: optional collector (the pipeline passes its warnings list).
    Check-stage warnings are appended to it; they never change a result. They
    come from the registered kinds' ``check_warnings`` hooks (today the
    prism's projection warning: a generic 2D length check measured a prism
    segment's drawn projection, not its true length).
    """
    results = [_check_one(c, sym, tol) for c in checks]
    if warnings is not None:
        for check in checks:
            warnings.extend(DERIVED_REGISTRY.check_warnings(check, sym))
    return results


# ---------------------------------------------------------------------------
# Internal dispatcher
# ---------------------------------------------------------------------------

def _check_one(check: Any, sym: SymTable, default_tol: float) -> CheckResult:
    t = check.tol if check.tol is not None else default_tol
    try:
        match check:
            case ir.DistinctPoints(a=a, b=b):
                d = float(sym[a].distance(sym[b]).evalf())
                ok = d > t
                msg = "" if ok else f"Points {a!r} and {b!r} coincide (distance={d:.2e})"

            case ir.DistinctObjects(a=a, b=b):
                ok = not _to_bool(sym[a] == sym[b])
                msg = "" if ok else f"Objects {a!r} and {b!r} are geometrically identical"

            case ir.NonCollinear(a=a, b=b, c=c):
                ok = not _to_bool(spg.Point.is_collinear(sym[a], sym[b], sym[c]))
                msg = "" if ok else f"Points {a!r}, {b!r}, {c!r} are collinear"

            case ir.Collinear(points=points):
                pts = [sym[p] for p in points]
                ok = _to_bool(spg.Point.is_collinear(*pts))
                ids = ", ".join(repr(p) for p in points)
                msg = "" if ok else f"Points {ids} are not collinear"

            case ir.Contains(p=p, obj=obj):
                ok = _contains(sym[obj], sym[p], t)
                msg = "" if ok else f"Object {obj!r} does not contain point {p!r}"

            case ir.NotContains(p=p, obj=obj):
                ok = not _contains(sym[obj], sym[p], t)
                msg = "" if ok else f"Object {obj!r} unexpectedly contains point {p!r}"

            case ir.Parallel(l1=l1, l2=l2):
                ok = _is_parallel(_as_linear(sym[l1]), _as_linear(sym[l2]))
                msg = "" if ok else f"Objects {l1!r} and {l2!r} are not parallel"

            case ir.NotParallel(l1=l1, l2=l2):
                ok = not _is_parallel(_as_linear(sym[l1]), _as_linear(sym[l2]))
                msg = "" if ok else f"Objects {l1!r} and {l2!r} are unexpectedly parallel"

            case ir.Perpendicular(l1=l1, l2=l2):
                ok = _to_bool(_as_linear(sym[l1]).is_perpendicular(_as_linear(sym[l2])))
                msg = "" if ok else f"Objects {l1!r} and {l2!r} are not perpendicular"

            case ir.RightAngle(angle=angle):
                av = _angle_at(sym[angle.a], sym[angle.o], sym[angle.b])
                ok = abs(av - math.pi / 2) < t
                if ok:
                    msg = ""
                else:
                    msg = f"Angle {angle.a}-{angle.o}-{angle.b} is {math.degrees(av):.3f}°, not 90°"
                    cands = _candidate_angles_at(angle.o, sym, 90.0, t)
                    if cands:
                        msg += f" | right angles at {angle.o}: {', '.join(cands)}"

            case ir.AngleEqual(a1=a1, a2=a2):
                v1 = _angle_at(sym[a1.a], sym[a1.o], sym[a1.b])
                v2 = _angle_at(sym[a2.a], sym[a2.o], sym[a2.b])
                ok = abs(v1 - v2) < t
                if ok:
                    msg = ""
                else:
                    d1, d2 = math.degrees(v1), math.degrees(v2)
                    msg = (
                        f"Angle {a1.a}-{a1.o}-{a1.b} = {d1:.1f}° "
                        f"but {a2.a}-{a2.o}-{a2.b} = {d2:.1f}°"
                    )
                    # Suggest matching alternatives at each vertex
                    hints = []
                    cands1 = _candidate_angles_at(a1.o, sym, d2, t)
                    if cands1:
                        hints.append(f"at {a1.o} try: {', '.join(cands1)}")
                    cands2 = _candidate_angles_at(a2.o, sym, d1, t)
                    if cands2:
                        hints.append(f"at {a2.o} try: {', '.join(cands2)}")
                    if hints:
                        msg += " | " + "; ".join(hints)

            case ir.EqualLength(segs=segs):
                lengths = [_length_of(sym[s], s) for s in segs]
                ok = all(abs(l - lengths[0]) < t for l in lengths[1:])
                if ok:
                    msg = ""
                else:
                    pairs = ", ".join(f"{s}={l:.4f}" for s, l in zip(segs, lengths))
                    msg = f"Lengths not equal: {pairs}"

            case ir.DistanceEquals(seg=seg, expected=expected):
                length = _length_of(sym[seg], seg)
                ok = abs(length - expected) < t * max(expected, 1.0)
                msg = "" if ok else f"{seg!r} length {length:.4f} ≠ expected {expected:.4f}"

            case ir.RatioEqual(s1=s1, s2=s2, s3=s3, s4=s4):
                l1 = _length_of(sym[s1], s1)
                l2 = _length_of(sym[s2], s2)
                l3 = _length_of(sym[s3], s3)
                l4 = _length_of(sym[s4], s4)
                # Cross-multiply to avoid division: l1*l4 == l2*l3
                lhs, rhs = l1 * l4, l2 * l3
                ok = abs(lhs - rhs) < t * max(abs(lhs), abs(rhs), 1.0)
                msg = "" if ok else (
                    f"Ratios not equal: {l1:.4f}/{l2:.4f}≠{l3:.4f}/{l4:.4f}"
                )

            case ir.SimilarTriangles(t1=t1, t2=t2):
                tri1, tri2 = sym[t1], sym[t2]
                angles1 = sorted(float(a.evalf()) for a in tri1.angles.values())
                angles2 = sorted(float(a.evalf()) for a in tri2.angles.values())
                ok = all(abs(a - b) < t for a, b in zip(angles1, angles2))
                deg1 = [f"{math.degrees(a):.1f}°" for a in angles1]
                deg2 = [f"{math.degrees(a):.1f}°" for a in angles2]
                msg = "" if ok else f"Triangles not similar: {deg1} vs {deg2}"

            case ir.Tangent(line=line, circle=circle):
                obj = sym[circle]
                lin = _as_line(sym[line])
                cx, cy, hr, vr = _conic_frame(obj, "tangent", circle)
                a, b, c0 = (float(v.evalf()) for v in lin.coefficients)
                norm = math.hypot(a, b)
                # Distance from the center at which a line of this direction is
                # tangent: the conic's support function along the line's normal
                # (the radius, for a circle).
                d = abs(a * cx + b * cy + c0) / norm
                r = math.hypot(hr * a, vr * b) / norm
                ok = abs(d - r) < t
                msg = "" if ok else (
                    f"Line {line!r} not tangent to {circle!r}: dist={d:.4f}, r={r:.4f}"
                )
                if ok and isinstance(obj, _ARC_LIKE):
                    # Tangent to the full curve is not enough: the touch point
                    # must be on the drawn sweep.
                    touch = _tangent_touch_point(lin, _underlying_conic(obj))
                    if touch is None or not _point_in_arc_sweep(touch, obj):
                        ok = False
                        msg = (
                            f"Line {line!r} is tangent to the full curve of {circle!r} but "
                            "touches it outside the arc's sweep"
                        )

            case ir.OppositeSide(p=p, q=q, line_a=line_a, line_b=line_b):
                pa = sym[p]
                qa = sym[q]
                la = sym[line_a]
                lb = sym[line_b]
                # cross product sign: (lb - la) x (pt - la)
                dx = float((lb.x - la.x).evalf())
                dy = float((lb.y - la.y).evalf())
                cross_p = dx * float((pa.y - la.y).evalf()) - dy * float((pa.x - la.x).evalf())
                cross_q = dx * float((qa.y - la.y).evalf()) - dy * float((qa.x - la.x).evalf())
                ok = cross_p * cross_q < -t
                msg = "" if ok else (
                    f"Points {p!r} and {q!r} are not on opposite sides of line {line_a!r}-{line_b!r}"
                )

            case ir.SameSide(p=p, q=q, line_a=line_a, line_b=line_b):
                pa = sym[p]
                qa = sym[q]
                la = sym[line_a]
                lb = sym[line_b]
                dx = float((lb.x - la.x).evalf())
                dy = float((lb.y - la.y).evalf())
                cross_p = dx * float((pa.y - la.y).evalf()) - dy * float((pa.x - la.x).evalf())
                cross_q = dx * float((qa.y - la.y).evalf()) - dy * float((qa.x - la.x).evalf())
                ok = cross_p * cross_q > t
                msg = "" if ok else (
                    f"Points {p!r} and {q!r} are not on the same side of line {line_a!r}-{line_b!r}"
                )

            case ir.Centroid(g=g, a=a, b=b, c=c):
                ga = sym[g]
                aa = sym[a]
                ba = sym[b]
                ca = sym[c]
                cx = (float(aa.x.evalf()) + float(ba.x.evalf()) + float(ca.x.evalf())) / 3.0
                cy = (float(aa.y.evalf()) + float(ba.y.evalf()) + float(ca.y.evalf())) / 3.0
                dx = float(ga.x.evalf()) - cx
                dy = float(ga.y.evalf()) - cy
                ok = max(abs(dx), abs(dy)) <= t
                msg = "" if ok else (
                    f"Point {g!r} is not the centroid of triangle "
                    f"{a!r}{b!r}{c!r}: expected ({cx:.4f}, {cy:.4f}), "
                    f"got ({float(ga.x.evalf()):.4f}, {float(ga.y.evalf()):.4f})"
                )

            case ir.Convex(polygon=polygon):
                poly = sym[polygon]
                ok = _to_bool(poly.is_convex())
                msg = "" if ok else f"Polygon {polygon!r} is not convex"

            case ir.CCW(polygon=polygon):
                poly = sym[polygon]
                area = float(poly.area.evalf())
                ok = area > 0
                msg = "" if ok else (
                    f"Polygon {polygon!r} is not wound counter-clockwise "
                    f"(signed area={area:.4f})"
                )

            case ir.MinDistance(a=a, b=b, min_dist=min_dist):
                d = float(sym[a].distance(sym[b]).evalf())
                ok = d >= min_dist
                msg = "" if ok else (
                    f"Points {a!r} and {b!r} are too close: distance={d:.4f}, "
                    f"expected at least {min_dist:.4f}"
                )

            case ir.CongruentTriangles(t1=t1, t2=t2):
                tri1, tri2 = sym[t1], sym[t2]
                lengths1 = sorted(float(s.length.evalf()) for s in tri1.sides)
                lengths2 = sorted(float(s.length.evalf()) for s in tri2.sides)
                ok = all(abs(a - b) < t for a, b in zip(lengths1, lengths2))
                len1 = [f"{l:.4f}" for l in lengths1]
                len2 = [f"{l:.4f}" for l in lengths2]
                msg = "" if ok else f"Triangles not congruent: {len1} vs {len2}"

            case ir.EqualRadius(circles=circles):
                # A circle's radius, or an ellipse's (hradius, vradius) pair; a
                # circle and a genuine ellipse are simply unequal.
                radii = [_conic_frame(sym[c], "equal_radius", c)[2:] for c in circles]
                ok = all(
                    abs(hr - radii[0][0]) < t and abs(vr - radii[0][1]) < t
                    for hr, vr in radii[1:]
                )
                if ok:
                    msg = ""
                else:
                    pairs = ", ".join(
                        f"{c}={hr:.4f}" if abs(hr - vr) < 1e-12 else f"{c}={hr:.4f}x{vr:.4f}"
                        for c, (hr, vr) in zip(circles, radii)
                    )
                    msg = f"Circle radii not equal: {pairs}"

            case ir.RadiusEquals(circle=circle, expected=expected):
                radius = _circular_radius(sym[circle], "radius_equals", circle)
                ok = abs(radius - expected) < t * max(expected, 1.0)
                msg = "" if ok else (
                    f"Circle {circle!r} radius {radius:.4f} ≠ expected {expected:.4f}"
                )

            case ir.CongruentArcs(arcs=arcs):
                ok, msg = _check_congruent_arcs(arcs, sym, t)

            case ir.AngleValue(angle=angle, expected_deg=expected_deg):
                av = _angle_at(sym[angle.a], sym[angle.o], sym[angle.b])
                expected_rad = math.radians(expected_deg)
                ok = abs(av - expected_rad) < t
                if ok:
                    msg = ""
                else:
                    msg = (
                        f"Angle {angle.a}-{angle.o}-{angle.b} is "
                        f"{math.degrees(av):.3f}°, not {expected_deg:.3f}°"
                    )
                    cands = _candidate_angles_at(angle.o, sym, expected_deg, t)
                    if cands:
                        msg += f" | angles={expected_deg:.1f}° at {angle.o}: {', '.join(cands)}"

            case ir.CirclesTangent(c1=c1, c2=c2):
                circ1, circ2 = sym[c1], sym[c2]
                d = float(circ1.center.distance(circ2.center).evalf())
                r1 = _circular_radius(circ1, "circles_tangent", c1)
                r2 = _circular_radius(circ2, "circles_tangent", c2)
                identical = d < t and abs(r1 - r2) < t
                externally_tangent = abs(d - (r1 + r2)) < t
                internally_tangent = abs(d - abs(r1 - r2)) < t
                ok = (externally_tangent or internally_tangent) and not identical
                msg = "" if ok else (
                    f"Circles {c1!r} and {c2!r} are not tangent: "
                    f"center distance={d:.4f}, r1={r1:.4f}, r2={r2:.4f}"
                )

            case _ if (evaluate := DERIVED_REGISTRY.check_evaluator(check.kind)) is not None:
                # A check kind owned by a registered kind (volume_equals,
                # true_length_equals, cube_count_equals: see the registry's
                # ``evaluate_checks`` hook).
                ok, msg = evaluate(check, sym, default_tol)

            case _:
                # Unknown check kind — pass through (forward-compatible)
                ok = True
                msg = f"(unrecognized check kind {check.kind!r}, skipped)"

        if not ok and check.source:
            msg = f"[{check.source}] {msg}"
        return CheckResult(check=check, passed=ok, message=msg)

    except UnsupportedOperand as exc:
        # A deliberate rejection, not a surprise — report it as directly as a
        # check that returns its own failure message would.
        msg = str(exc)
        if check.source:
            msg = f"[{check.source}] {msg}"
        return CheckResult(check=check, passed=False, message=msg)

    except Exception as exc:
        return CheckResult(check=check, passed=False, message=f"Error in {check.kind!r}: {exc}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _near_exact(actual: float, expected: float, tol: float | None) -> bool:
    """Relative comparison for the prism measure checks: ``tol`` (the check's
    own) or EXACT_MEASURE_TOL, scaled by max(|expected|, 1)."""
    t = EXACT_MEASURE_TOL if tol is None else tol
    return abs(actual - expected) <= t * max(abs(expected), 1.0)


def _is_parallel(obj1, obj2, tol: float = 1e-9) -> bool:
    """Check parallelism symbolically, falling back to numerical cross-product for float coords."""
    try:
        result = _to_bool(obj1.is_parallel(obj2))
        if result:
            return True
    except Exception:
        pass
    # Numerical fallback: cross product of direction vectors
    try:
        d1 = obj1.direction
        d2 = obj2.direction
        cross = float(d1.x * d2.y - d1.y * d2.x)
        norm = (float(abs(d1.x) + abs(d1.y))) * (float(abs(d2.x) + abs(d2.y)))
        return abs(cross) < tol * norm if norm > 0 else True
    except Exception:
        return False


def _to_bool(expr: Any) -> bool:
    if isinstance(expr, bool):
        return expr
    try:
        return bool(expr)
    except Exception:
        return False


def _contains(obj: Any, point: spg.Point, tol: float) -> bool:
    """Check whether obj contains point, using distance-based tolerance for circles/ellipses."""
    if isinstance(obj, _ARC_LIKE):
        # On the curved edge only — see point_on_arc(), which the pick_on_object
        # rule in to_sympy.py shares, so the two can't drift apart.
        return point_on_arc(point, obj, tol)
    if isinstance(obj, spg.Circle):
        d = float(point.distance(obj.center).evalf())
        r = float(obj.radius.evalf())
        return abs(d - r) < tol
    if isinstance(obj, spg.Ellipse):
        cx = float(obj.center.x.evalf())
        cy = float(obj.center.y.evalf())
        a = float(obj.hradius.evalf())
        b = float(obj.vradius.evalf())
        px, py = float(point.x.evalf()), float(point.y.evalf())
        val = ((px - cx) / a) ** 2 + ((py - cy) / b) ** 2
        return abs(val - 1.0) < tol
    return _to_bool(obj.contains(point))


_LINEAR_TYPES = (spg.Line, spg.Segment, spg.Ray)


def _as_linear(obj: Any):
    """Return obj if it is a linear geometry object, raising TypeError otherwise."""
    if isinstance(obj, _LINEAR_TYPES):
        return obj
    raise TypeError(f"Expected a linear object, got {type(obj).__name__}")


def _as_line(obj: Any) -> spg.Line:
    """Convert a LinearEntity to an infinite Line (for distance computation)."""
    if isinstance(obj, spg.Line):
        return obj
    if isinstance(obj, (spg.Segment, spg.Ray)):
        return spg.Line(obj.p1, obj.p2)
    raise TypeError(f"Cannot convert {type(obj).__name__} to Line")


_ARC_LIKE = (Arc, Sector, EllipticalArc, EllipticalSector)


def _conic_frame(obj: Any, kind: str, obj_id: str) -> tuple[float, float, float, float]:
    """(cx, cy, hradius, vradius) of a circle, ellipse, arc, sector, elliptical
    arc or elliptical sector; a circular object has hradius == vradius.
    Anything else is an UnsupportedOperand naming `kind` and `obj_id`."""
    if isinstance(obj, (Arc, Sector)):
        r = float(obj.radius.evalf())
        hr = vr = r
    elif isinstance(obj, (EllipticalArc, EllipticalSector, spg.Ellipse)):
        hr, vr = float(obj.hradius.evalf()), float(obj.vradius.evalf())
    else:
        raise UnsupportedOperand(
            f"{kind}: {obj_id!r} must be a circle, ellipse, arc or sector, got {type(obj).__name__}"
        )
    return float(obj.center.x.evalf()), float(obj.center.y.evalf()), hr, vr


def _circular_radius(obj: Any, kind: str, obj_id: str) -> float:
    """The single radius of a circular object. An ellipse has two radii, so a
    check that compares one radius cannot evaluate it: UnsupportedOperand."""
    _cx, _cy, hr, vr = _conic_frame(obj, kind, obj_id)
    if abs(hr - vr) > 1e-9 * max(hr, vr, 1.0):
        raise UnsupportedOperand(
            f"{kind}: {obj_id!r} is an ellipse with two radii (hradius={hr:.4f}, "
            f"vradius={vr:.4f}), not a circle"
        )
    return hr


def _wrap_pi(x: float) -> float:
    """`x` (radians) wrapped to [-pi, pi)."""
    return (x + math.pi) % (2 * math.pi) - math.pi


def _ellipse_arcs_congruent(a: tuple, b: tuple, tol: float) -> bool:
    """Are two elliptical arcs congruent, i.e. is one a rigid motion of the
    other? Each is (hradius, vradius, start, end) in parametric angle, CCW.

    An ellipse's curvature varies along it, so equal span is not enough: the
    arcs must have equal axes (or axes swapped, a 90-degree turn) and their
    positions must be related by a symmetry of the ellipse. For an
    axis-aligned ellipse those are the reflections across either axis, the
    half turn and arc reversal: parametric angle t -> t + k*pi (k = 0, 1) or
    t -> -t + k*pi, the arc reversing under the reflections so it stays CCW.
    With swapped axes the same set is shifted by a quarter turn (pi/2).
    """
    a_hr, a_vr, a_s, a_e = a
    b_hr, b_vr, b_s, b_e = b
    same = abs(a_hr - b_hr) < tol and abs(a_vr - b_vr) < tol
    swapped = abs(a_hr - b_vr) < tol and abs(a_vr - b_hr) < tol
    if not (same or swapped) or abs((a_e - a_s) - (b_e - b_s)) >= tol:
        return False
    base = 0.0 if same else math.pi / 2
    for k in (0, 1):
        shift = base + k * math.pi
        for image_start in (a_s + shift, -a_e + shift):
            if abs(_wrap_pi(b_s - image_start)) < tol:
                return True
    return False


def _check_congruent_arcs(arcs: list[str], sym: SymTable, tol: float) -> tuple[bool, str]:
    """Compare a list of arcs/sectors for congruence.

    Circular ones are congruent when they have equal radius and equal
    (reflex-aware) central-angle sweep. Elliptical ones need the symmetry
    condition in `_ellipse_arcs_congruent`; a circle and a genuine ellipse are
    never congruent, and an elliptical arc whose two radii are equal is just a
    circular arc.

    Sweep math comes from `to_sympy._arc_param_frame()` (parametric angle,
    which is the polar angle for a circular arc) — not from `render_util`,
    which owns arc math for *rendering* only.
    """
    frames: list[tuple[float, float, float, float]] = []
    for arc_id in arcs:
        obj = sym[arc_id]
        if not isinstance(obj, _ARC_LIKE):
            return False, f"Object {arc_id!r} is not an arc or sector (got {type(obj).__name__})"
        _cx, _cy, hr, vr, start, end = _arc_param_frame(obj)
        frames.append((hr, vr, start, end))

    def circular(f: tuple[float, float, float, float]) -> bool:
        return abs(f[0] - f[1]) <= 1e-9 * max(f[0], f[1], 1.0)

    def congruent(f: tuple[float, float, float, float], g: tuple[float, float, float, float]) -> bool:
        if circular(f) != circular(g):
            return False
        if circular(f):
            return abs(f[0] - g[0]) < tol and abs((f[3] - f[2]) - (g[3] - g[2])) < tol
        return _ellipse_arcs_congruent(f, g, tol)

    if all(congruent(frames[0], f) for f in frames[1:]):
        return True, ""

    def describe(arc_id: str, f: tuple[float, float, float, float]) -> str:
        if circular(f):
            return f"{arc_id}=(r={f[0]:.4f}, sweep={math.degrees(f[3] - f[2]):.2f}°)"
        return (
            f"{arc_id}=(hradius={f[0]:.4f}, vradius={f[1]:.4f}, "
            f"t={math.degrees(f[2]):.1f}°→{math.degrees(f[3]):.1f}°)"
        )

    msg = "Arcs not congruent: " + ", ".join(describe(i, f) for i, f in zip(arcs, frames))
    if len({circular(f) for f in frames}) > 1:
        msg += " (a circle and an ellipse are never congruent)"
    return False, msg


def _length_of(obj: Any, obj_id: str) -> float:
    """Length of a segment-like object or of an arc/sector's curved edge.

    A sector counts its curved edge only. A full circle or ellipse has no
    single "length" for these checks: UnsupportedOperand pointing at the
    radius checks."""
    if isinstance(obj, spg.Segment):
        return float(obj.length.evalf())
    if isinstance(obj, _LINEAR_TYPES):
        return float(obj.p1.distance(obj.p2).evalf())
    if isinstance(obj, _ARC_LIKE):
        return curve_length(obj)
    if isinstance(obj, spg.Ellipse):  # Circle subclasses Ellipse
        raise UnsupportedOperand(
            f"length: {obj_id!r} is a full {type(obj).__name__.lower()}, which has no "
            f"single length here; use a radius check (radius_equals / equal_radius)"
        )
    raise TypeError(f"Cannot compute length of {type(obj).__name__}")


# ---------------------------------------------------------------------------
# Render-op angle validation
# ---------------------------------------------------------------------------

def check_render_angles(
    diagram: ir.DiagramIR,
    sym: SymTable | None = None,
) -> list[str]:
    """Validate that angle triples in render ops use points connected through
    the diagram's linear definitions.

    For mark_angles / mark_right_angles / label_angle, the triple {a, o, b}
    must have both `a` and `b` on a line/segment/ray that passes through `o`.
    Returns a list of error strings (empty = all valid).

    When *sym* is provided, also accepts pairs where a point geometrically lies
    on a drawn line/segment/ray (e.g. a point placed on a parallel line without
    being a structural defining point).
    """
    if not any(isinstance(op, (ir.MarkAngles, ir.MarkRightAngles, ir.LabelAngle)) for op in diagram.render):
        # Nothing to validate. Building the pairs tests every point against
        # every linear object (exact SymPy containment), which is costly for
        # diagrams with many polygons (a block stack's column top faces).
        return []
    pairs = _build_linear_pairs(diagram, sym)
    errors: list[str] = []
    for op in diagram.render:
        match op:
            case ir.MarkAngles(angles=angles) | ir.MarkRightAngles(angles=angles):
                for angle in angles:
                    _validate_triple(angle, op.kind, pairs, errors)
            case ir.LabelAngle(angle=angle):
                _validate_triple(angle, "label_angle", pairs, errors)
    return errors


def _build_linear_pairs(
    diagram: ir.DiagramIR,
    sym: SymTable | None = None,
) -> set[frozenset]:
    """Return the set of {p, q} pairs that share a linear object in the diagram
    (effective view: synthesized segments/polygons count, see derived.py)."""
    defs = effective_defs(diagram)
    pts_on: dict[str, set[str]] = {}  # obj_id -> set of point ids on that obj

    for stmt in defs:
        match stmt:
            case ir.LineThrough(id=oid, p=p, q=q):
                pts_on.setdefault(oid, set()).update([p, q])
            case ir.Segment(id=oid, a=a, b=b):
                pts_on.setdefault(oid, set()).update([a, b])
            case ir.Ray(id=oid, a=a, b=b):
                pts_on.setdefault(oid, set()).update([a, b])
            case ir.PointIntersection(id=pid, obj1=o1, obj2=o2):
                pts_on.setdefault(o1, set()).add(pid)
                pts_on.setdefault(o2, set()).add(pid)
            case ir.PointOn(id=pid, on=obj):
                pts_on.setdefault(obj, set()).add(pid)
            case ir.PointMidpoint(id=pid, p=p, q=q):
                pts_on.setdefault(f"__mid_{pid}", set()).update([pid, p, q])
            case ir.PointFoot(id=pid, onto=obj):
                pts_on.setdefault(obj, set()).add(pid)
            case ir.PointBetween(id=pid, a=a, b=b):
                # PointBetween lies on the virtual segment a-b
                pts_on.setdefault(f"__between_{pid}", set()).update([pid, a, b])
            case ir.Triangle(id=oid, a=a, b=b, c=c):
                pts_on[f"{oid}__ab"] = {a, b}
                pts_on[f"{oid}__bc"] = {b, c}
                pts_on[f"{oid}__ac"] = {a, c}
            case ir.Polygon(id=oid, points=pts):
                for i, pt in enumerate(pts):
                    nxt = pts[(i + 1) % len(pts)]
                    pts_on[f"{oid}__{i}"] = {pt, nxt}
            case ir.LinePerpendicularThrough(id=oid, through=p):
                pts_on.setdefault(oid, set()).add(p)
            case ir.LineParallelThrough(id=oid, through=p):
                pts_on.setdefault(oid, set()).add(p)
            case ir.LineAngleBisector(id=oid, vertex=v):
                pts_on.setdefault(oid, set()).add(v)
            case ir.LineTangent(id=oid, point=p):
                pts_on.setdefault(oid, set()).add(p)

    # When sym is available, check if any point geometrically lies on a
    # line/segment/ray it isn't structurally connected to.
    if sym is not None:
        linear_objs: dict[str, Any] = {
            oid: obj for oid, obj in sym.items()
            if isinstance(obj, (spg.Line, spg.Segment, spg.Ray))
        }
        # Polygon/Triangle sides are also valid places for a point to lie for
        # angle-mark purposes (e.g. a point_on() point placed on a polygon's
        # side without being one of its named vertices) — sympy exposes
        # these as .sides (a list of Segment objects) on both Polygon and
        # its Triangle subclass. The structural pass above already handles a
        # polygon's own named vertices via its own pts_on entries; this
        # geometric fallback is specifically for points NOT already known to
        # be on that side structurally, so it needs its own synthetic ids —
        # reusing the polygon's oid would silently merge into (and be
        # shadowed by) the structural entry already keyed on that oid.
        # The faces of a ``trusted_faces`` kind (derived registry) are
        # skipped: a block stack's up to 400 column top faces, each side an
        # exact radical segment, would make this pass test every point
        # against 1600 segments (about a minute); they are faces of a drawn
        # solid, not lines a point is placed on.
        solid_faces = {stmt.id for stmt in defs if DERIVED_REGISTRY.is_trusted_face(stmt, sym)}
        for oid, obj in sym.items():
            if isinstance(obj, spg.Polygon) and oid not in solid_faces:
                for i, side in enumerate(obj.sides):
                    linear_objs[f"{oid}__contains_side{i}"] = side
        # A Sector/EllipticalSector's two straight radii (center-start and
        # center-end) are also valid angle-mark legs — e.g. marking the
        # sector's own subtended angle at its center. Sector/EllipticalSector
        # are lightweight marker types (to_sympy.py), not sympy geometry
        # objects, so their radii must be synthesized as Segments here rather
        # than read off an existing .sides-style attribute.
        for oid, obj in sym.items():
            if isinstance(obj, (Sector, EllipticalSector)):
                linear_objs[f"{oid}__radius_start"] = spg.Segment(obj.center, obj.start)
                linear_objs[f"{oid}__radius_end"] = spg.Segment(obj.center, obj.end)
        # point_reflect (point-symmetry mode) and point_dilate are always
        # collinear with their own defining points by construction — source,
        # across/center, and the result all lie on one line — but that fact
        # is only visible here, not to whichever strategy produced the IR
        # (the recipe DSL's ReflectionOp, or structured/pydsl building
        # PointReflect/PointDilate directly, none of which carry a distinct
        # "this result is collinear with X, Y" marker once lowered), so
        # fixing this once here — shared by every strategy — is more direct
        # than teaching each producing pathway to separately emit a
        # synthetic linear def. Mirror-mode point_reflect (across a line/
        # segment/ray) is NOT collinear with source in general, so it's
        # deliberately excluded — only checked when `across` resolves to a
        # point. Guarded against degenerate (coincident) inputs, which would
        # otherwise raise constructing spg.Line — lower.py already rejects
        # these for the recipe DSL's own ops, but this path is shared with
        # strategies that build the IR directly and may not pre-validate it.
        for stmt in defs:
            match stmt:
                case ir.PointReflect(id=oid, source=source_id, across=across_id):
                    across_obj = sym.get(across_id)
                    source_obj = sym.get(source_id)
                    if (
                        isinstance(across_obj, spg.Point2D)
                        and isinstance(source_obj, spg.Point2D)
                        and across_obj != source_obj
                    ):
                        linear_objs[f"{oid}__reflect_axis"] = spg.Line(source_obj, across_obj)
                case ir.PointDilate(id=oid, center=center_id, source=source_id):
                    center_obj = sym.get(center_id)
                    source_obj = sym.get(source_id)
                    if (
                        isinstance(center_obj, spg.Point2D)
                        and isinstance(source_obj, spg.Point2D)
                        and center_obj != source_obj
                    ):
                        linear_objs[f"{oid}__dilate_line"] = spg.Line(center_obj, source_obj)
        # Points referenced by angle triples in render ops must be eligible for
        # geometric validation even when implicit (__-prefixed) — the resolver
        # in angle_pairs.py synthesizes such points on real lines by construction.
        referenced_by_angle_ops: set[str] = set()
        for op in diagram.render:
            match op:
                case ir.MarkAngles(angles=angles) | ir.MarkRightAngles(angles=angles):
                    for ang in angles:
                        referenced_by_angle_ops.update((ang.a, ang.o, ang.b))
                case ir.LabelAngle(angle=ang):
                    referenced_by_angle_ops.update((ang.a, ang.o, ang.b))
        point_ids = [
            pid for pid, obj in sym.items()
            if isinstance(obj, spg.Point2D)
            and (not pid.startswith("__") or pid in referenced_by_angle_ops)
        ]
        for oid, line_obj in linear_objs.items():
            existing = pts_on.get(oid, set())
            for pid in point_ids:
                if pid in existing:
                    continue
                pt_obj = sym[pid]
                try:
                    if line_obj.contains(pt_obj):
                        pts_on.setdefault(oid, set()).add(pid)
                except (TypeError, ValueError):
                    continue

    pairs: set[frozenset] = set()
    for obj_pts in pts_on.values():
        pts_list = list(obj_pts)
        for i in range(len(pts_list)):
            for j in range(i + 1, len(pts_list)):
                pairs.add(frozenset([pts_list[i], pts_list[j]]))
    return pairs


def _validate_triple(
    angle: ir.AnglePoints,
    kind: str,
    pairs: set[frozenset],
    errors: list[str],
) -> None:
    a, o, b = angle.a, angle.o, angle.b
    hint = f" (to mark an angle at {o}, draw a segment from {o} to each leg point)"
    if frozenset([a, o]) not in pairs:
        errors.append(
            f"{kind}: point {a!r} does not lie on any line/segment/ray through vertex {o!r}{hint}"
        )
    if frozenset([b, o]) not in pairs:
        errors.append(
            f"{kind}: point {b!r} does not lie on any line/segment/ray through vertex {o!r}{hint}"
        )


def _angle_at(a: spg.Point2D, vertex: spg.Point2D, b: spg.Point2D) -> float:
    """Unsigned angle at vertex in configuration a-vertex-b (radians, [0, π])."""
    vax = float((a.x - vertex.x).evalf())
    vay = float((a.y - vertex.y).evalf())
    vbx = float((b.x - vertex.x).evalf())
    vby = float((b.y - vertex.y).evalf())
    dot = vax * vbx + vay * vby
    mag_a = math.sqrt(vax ** 2 + vay ** 2)
    mag_b = math.sqrt(vbx ** 2 + vby ** 2)
    if mag_a < 1e-15 or mag_b < 1e-15:
        raise ValueError("Degenerate angle: vertex coincides with a leg point")
    cos_val = max(-1.0, min(1.0, dot / (mag_a * mag_b)))
    return math.acos(cos_val)


def _candidate_angles_at(
    vertex_id: str,
    sym: "SymTable",
    target_deg: float,
    tol: float,
) -> list[str]:
    """Find all non-implicit point pairs at vertex whose angle matches target_deg."""
    if vertex_id not in sym or not isinstance(sym[vertex_id], spg.Point2D):
        return []
    vertex = sym[vertex_id]
    pts = [
        (k, v) for k, v in sym.items()
        if isinstance(v, spg.Point2D) and k != vertex_id and not k.startswith("__")
    ]
    matches = []
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            a_id, a_pt = pts[i]
            b_id, b_pt = pts[j]
            try:
                deg = math.degrees(_angle_at(a_pt, vertex, b_pt))
                if abs(deg - target_deg) < tol:
                    matches.append(f"{a_id}-{vertex_id}-{b_id}={deg:.1f}°")
            except (ValueError, ZeroDivisionError):
                continue
    return matches
