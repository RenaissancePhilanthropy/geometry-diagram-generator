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
    tol: float = 5e-3,
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
                msg = "" if ok else (
                    f"Angle {angle.a}-{angle.o}-{angle.b} is {math.degrees(av):.3f}°, not 90°"
                )

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
                lengths = [float(_seg_length(sym[s]).evalf()) for s in segs]
                ok = all(abs(l - lengths[0]) < t for l in lengths[1:])
                if ok:
                    msg = ""
                else:
                    pairs = ", ".join(f"{s}={l:.4f}" for s, l in zip(segs, lengths))
                    msg = f"Segment lengths not equal: {pairs}"

            case ir.DistanceEquals(seg=seg, expected=expected):
                length = float(_seg_length(sym[seg]).evalf())
                ok = abs(length - expected) < t * max(expected, 1.0)
                msg = "" if ok else f"Segment {seg!r} length {length:.4f} ≠ expected {expected:.4f}"

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

            case _:
                # Unknown check kind — pass through (forward-compatible)
                ok = True
                msg = f"(unrecognized check kind {check.kind!r}, skipped)"

        if not ok and check.source:
            msg = f"[{check.source}] {msg}"
        return CheckResult(check=check, passed=ok, message=msg)

    except Exception as exc:
        return CheckResult(check=check, passed=False, message=f"Error in {check.kind!r}: {exc}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _seg_length(obj: Any):
    """Return the length of a Segment-like object as a SymPy expression."""
    if isinstance(obj, spg.Segment):
        return obj.length
    if isinstance(obj, _LINEAR_TYPES):
        return obj.p1.distance(obj.p2)
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
    """Return the set of {p, q} pairs that share a linear object in the diagram."""
    pts_on: dict[str, set[str]] = {}  # obj_id -> set of point ids on that obj

    for stmt in diagram.define:
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
        linear_obj_ids = [
            oid for oid, obj in sym.items()
            if isinstance(obj, (spg.Line, spg.Segment, spg.Ray))
        ]
        point_ids = [
            pid for pid, obj in sym.items()
            if isinstance(obj, spg.Point2D) and not pid.startswith("__")
        ]
        for oid in linear_obj_ids:
            line_obj = sym[oid]
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
    if frozenset([a, o]) not in pairs:
        errors.append(
            f"{kind}: point {a!r} does not lie on any line/segment/ray through vertex {o!r}"
        )
    if frozenset([b, o]) not in pairs:
        errors.append(
            f"{kind}: point {b!r} does not lie on any line/segment/ray through vertex {o!r}"
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
