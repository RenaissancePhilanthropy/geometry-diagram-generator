from __future__ import annotations

import math
from typing import Any

import sympy.geometry as spg
from pydantic import BaseModel

import ir.ir as ir
from ir.to_sympy import SymTable


class CheckResult(BaseModel):
    check: ir.CheckBase
    passed: bool
    message: str  # empty string on pass; human-readable explanation on failure


def run_checks(
    checks: list[ir.Check],
    sym: SymTable,
    tol: float = 1e-9,
) -> list[CheckResult]:
    """Evaluate each Check against the compiled symbol table."""
    return [_check_one(c, sym, tol) for c in checks]


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
                ok = _to_bool(sym[obj].contains(sym[p]))
                msg = "" if ok else f"Object {obj!r} does not contain point {p!r}"

            case ir.NotContains(p=p, obj=obj):
                ok = not _to_bool(sym[obj].contains(sym[p]))
                msg = "" if ok else f"Object {obj!r} unexpectedly contains point {p!r}"

            case ir.Parallel(l1=l1, l2=l2):
                ok = _to_bool(_as_linear(sym[l1]).is_parallel(_as_linear(sym[l2])))
                msg = "" if ok else f"Objects {l1!r} and {l2!r} are not parallel"

            case ir.NotParallel(l1=l1, l2=l2):
                ok = not _to_bool(_as_linear(sym[l1]).is_parallel(_as_linear(sym[l2])))
                msg = "" if ok else f"Objects {l1!r} and {l2!r} are unexpectedly parallel"

            case ir.Perpendicular(l1=l1, l2=l2):
                ok = _to_bool(_as_linear(sym[l1]).is_perpendicular(_as_linear(sym[l2])))
                msg = "" if ok else f"Objects {l1!r} and {l2!r} are not perpendicular"

            case ir.RightAngle(angle=angle):
                av = _angle_at(sym[angle.a], sym[angle.o], sym[angle.b])
                ok = abs(av - math.pi / 2) < t
                msg = "" if ok else (
                    f"Angle {angle.a}-{angle.o}-{angle.b} is {math.degrees(av):.3f}°, not 90°"
                )

            case ir.AngleEqual(a1=a1, a2=a2):
                v1 = _angle_at(sym[a1.a], sym[a1.o], sym[a1.b])
                v2 = _angle_at(sym[a2.a], sym[a2.o], sym[a2.b])
                ok = abs(v1 - v2) < t
                msg = "" if ok else (
                    f"Angles differ: {math.degrees(v1):.3f}° vs {math.degrees(v2):.3f}°"
                )

            case ir.EqualLength(segs=segs):
                lengths = [float(_seg_length(sym[s]).evalf()) for s in segs]
                ok = all(abs(l - lengths[0]) < t for l in lengths[1:])
                msg = "" if ok else f"Segment lengths not equal: {lengths}"

            case ir.RatioEqual(s1=s1, s2=s2, s3=s3, s4=s4):
                l1 = float(_seg_length(sym[s1]).evalf())
                l2 = float(_seg_length(sym[s2]).evalf())
                l3 = float(_seg_length(sym[s3]).evalf())
                l4 = float(_seg_length(sym[s4]).evalf())
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
                circ = sym[circle]
                lin = _as_line(sym[line])
                d = float(lin.distance(circ.center).evalf())
                r = float(circ.radius.evalf())
                ok = abs(d - r) < t
                msg = "" if ok else (
                    f"Line {line!r} not tangent to {circle!r}: dist={d:.4f}, r={r:.4f}"
                )

            case _:
                # Unknown check kind — pass through (forward-compatible)
                ok = True
                msg = f"(unrecognized check kind {check.kind!r}, skipped)"

        return CheckResult(check=check, passed=ok, message=msg)

    except Exception as exc:
        return CheckResult(check=check, passed=False, message=f"Error in {check.kind!r}: {exc}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_bool(expr: Any) -> bool:
    if isinstance(expr, bool):
        return expr
    try:
        return bool(expr)
    except Exception:
        return False


def _as_linear(obj: Any) -> spg.LinearEntity:
    """Return obj as a LinearEntity, raising TypeError if it isn't one."""
    if isinstance(obj, spg.LinearEntity):
        return obj
    raise TypeError(f"Expected a linear object, got {type(obj).__name__}")


def _as_line(obj: Any) -> spg.Line:
    """Convert a LinearEntity to an infinite Line (for distance computation)."""
    if isinstance(obj, spg.Line):
        return obj
    if isinstance(obj, (spg.Segment, spg.Ray)):
        return spg.Line(obj.p1, obj.p2)
    raise TypeError(f"Cannot convert {type(obj).__name__} to Line")


def _seg_length(obj: Any):
    """Return the length of a Segment-like object as a SymPy expression."""
    if isinstance(obj, spg.Segment):
        return obj.length
    # For other LinearEntity subclasses, compute distance between p1 and p2
    if isinstance(obj, spg.LinearEntity):
        return obj.p1.distance(obj.p2)
    raise TypeError(f"Cannot compute length of {type(obj).__name__}")


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
