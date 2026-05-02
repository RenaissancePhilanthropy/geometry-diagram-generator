"""
Coordinate resolution and geometric property validation for TikZ diagrams.

Resolves derived point coordinates from extracted TikZ commands and validates
geometric properties (right angles, midpoints, parallelism, etc.) against a
resolved coordinate map.
"""
from __future__ import annotations

import math
from typing import Any

from .tikz_extraction import (
    extract_defined_points,
    extract_computed_points,
    extract_labels,
    extract_marks,
    point_names_match,
)

# ---------------------------------------------------------------------------
# Coordinate resolution
# ---------------------------------------------------------------------------

def _dist(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2)


def _midpoint(p1: tuple[float, float], p2: tuple[float, float]) -> tuple[float, float]:
    return ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)


def _centroid(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
) -> tuple[float, float]:
    """Centroid of triangle ABC = average of the three vertices."""
    return ((a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3)


def _projection(
    p: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
) -> tuple[float, float] | None:
    """Orthogonal projection of P onto line AB (foot of perpendicular)."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom < 1e-12:
        return None
    t = ((p[0] - ax) * dx + (p[1] - ay) * dy) / denom
    return (ax + t * dx, ay + t * dy)


def _orthocenter(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
) -> tuple[float, float] | None:
    """Orthocenter of triangle ABC = intersection of altitudes."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    # Direction perpendicular to BC
    perp_bc = (-(cy - by), cx - bx)
    # Direction perpendicular to CA
    perp_ca = (-(ay - cy), ax - cx)
    a2 = (ax + perp_bc[0], ay + perp_bc[1])
    b2 = (bx + perp_ca[0], by + perp_ca[1])
    return _inter_ll(a, a2, b, b2)


def _incenter(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
) -> tuple[float, float]:
    """Incenter of triangle ABC = weighted average of vertices by opposite side lengths."""
    la = _dist(b, c)  # side opposite A
    lb = _dist(a, c)  # side opposite B
    lc = _dist(a, b)  # side opposite C
    total = la + lb + lc
    if total < 1e-12:
        return a
    return (
        (la * a[0] + lb * b[0] + lc * c[0]) / total,
        (la * a[1] + lb * b[1] + lc * c[1]) / total,
    )


def _symmetry(
    p: tuple[float, float],
    center: tuple[float, float],
) -> tuple[float, float]:
    """Reflection of P across center point: 2*center - P."""
    return (2 * center[0] - p[0], 2 * center[1] - p[1])


def _circumcenter(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
) -> tuple[float, float] | None:
    """Compute circumcenter of triangle ABC."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None  # Degenerate / collinear
    ux = ((ax**2 + ay**2) * (by - cy) + (bx**2 + by**2) * (cy - ay) + (cx**2 + cy**2) * (ay - by)) / d
    uy = ((ax**2 + ay**2) * (cx - bx) + (bx**2 + by**2) * (ax - cx) + (cx**2 + cy**2) * (bx - ax)) / d
    return (ux, uy)


def _inter_ll(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> tuple[float, float] | None:
    """Compute intersection of line AB and line CD."""
    x1, y1 = a
    x2, y2 = b
    x3, y3 = c
    x4, y4 = d
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-12:
        return None  # Parallel lines
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    x = x1 + t * (x2 - x1)
    y = y1 + t * (y2 - y1)
    return (x, y)


def _inter_cc(
    o1: tuple[float, float],
    p1: tuple[float, float],
    o2: tuple[float, float],
    p2: tuple[float, float],
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Intersection of circle 1 (center o1, through p1) with circle 2 (center
    o2, through p2). Returns the two intersection points sorted by (y, x)
    ascending so the assignment to which=0/which=1 is deterministic. Returns
    None if the circles are coincident, fully separate, or one contains the
    other (no real intersection).
    """
    r1 = _dist(o1, p1)
    r2 = _dist(o2, p2)
    dx = o2[0] - o1[0]
    dy = o2[1] - o1[1]
    d = math.sqrt(dx * dx + dy * dy)
    # No intersection: too far apart, or one inside the other, or coincident
    if d < 1e-12:
        return None
    if d > r1 + r2 + 1e-9:
        return None
    if d < abs(r1 - r2) - 1e-9:
        return None
    # a = distance from o1 to the chord midpoint along the line o1->o2
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h_sq = r1 * r1 - a * a
    h = math.sqrt(max(0.0, h_sq))
    mx = o1[0] + a * dx / d
    my = o1[1] + a * dy / d
    rx = -dy * (h / d)
    ry = dx * (h / d)
    p_a = (mx + rx, my + ry)
    p_b = (mx - rx, my - ry)
    # Sort for deterministic which=0 / which=1 assignment.
    return tuple(sorted([p_a, p_b], key=lambda p: (p[1], p[0])))  # type: ignore[return-value]


def _inter_lc(
    a: tuple[float, float],
    b: tuple[float, float],
    o: tuple[float, float],
    t: tuple[float, float],
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Intersection of line AB with circle (center o, through t). Returns the
    pair of intersection points (which may coincide if the line is tangent).
    Returns None if the line misses the circle entirely.
    """
    r = _dist(o, t)
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    fx = a[0] - o[0]
    fy = a[1] - o[1]
    A = dx * dx + dy * dy
    if A < 1e-12:
        return None
    B = 2 * (fx * dx + fy * dy)
    C = fx * fx + fy * fy - r * r
    disc = B * B - 4 * A * C
    if disc < -1e-9:
        return None
    disc = max(0.0, disc)
    sqrt_disc = math.sqrt(disc)
    t1 = (-B - sqrt_disc) / (2 * A)
    t2 = (-B + sqrt_disc) / (2 * A)
    p_a = (a[0] + t1 * dx, a[1] + t1 * dy)
    p_b = (a[0] + t2 * dx, a[1] + t2 * dy)
    return tuple(sorted([p_a, p_b], key=lambda p: (p[1], p[0])))  # type: ignore[return-value]


def resolve_all_coordinates(tikz: str) -> dict[str, tuple[float, float]]:
    """
    Build a full coordinate map combining explicit definitions with
    computable derived points.

    Two-solution constructions like ``\\tkzInterCC`` and ``\\tkzInterLC`` are
    resolved by computing both candidates and assigning them to the names
    paired by ``\\tkzGetPoints`` using a deterministic (y, x)-ascending sort.
    Constructions whose inputs cannot be resolved are silently omitted rather
    than guessed.
    """
    coords = extract_defined_points(tikz)
    computed = extract_computed_points(tikz)

    # Iteratively resolve computed points (some may depend on others)
    max_passes = 5
    for _ in range(max_passes):
        resolved_any = False
        for name, info in computed.items():
            if name in coords:
                continue
            t = info["type"]
            args = info["args"]
            try:
                if t == "midpoint" and len(args) == 2:
                    p1, p2 = coords[args[0]], coords[args[1]]
                    coords[name] = _midpoint(p1, p2)
                    resolved_any = True
                elif t == "circumcenter" and len(args) == 3:
                    pts = [coords[a] for a in args]
                    result = _circumcenter(*pts)
                    if result is not None:
                        coords[name] = result
                        resolved_any = True
                elif t == "inter_ll" and len(args) == 4:
                    pts = [coords[a] for a in args]
                    result = _inter_ll(*pts)
                    if result is not None:
                        coords[name] = result
                        resolved_any = True
                elif t == "inter_cc" and len(args) == 4:
                    pts = [coords[a] for a in args]
                    pair = _inter_cc(*pts)
                    if pair is not None:
                        coords[name] = pair[info.get("which", 0)]
                        resolved_any = True
                elif t == "inter_lc" and len(args) == 4:
                    pts = [coords[a] for a in args]
                    pair = _inter_lc(*pts)
                    if pair is not None:
                        coords[name] = pair[info.get("which", 0)]
                        resolved_any = True
                elif t == "centroid" and len(args) == 3:
                    pts = [coords[a] for a in args]
                    coords[name] = _centroid(*pts)
                    resolved_any = True
                elif t == "orthocenter" and len(args) == 3:
                    pts = [coords[a] for a in args]
                    result = _orthocenter(*pts)
                    if result is not None:
                        coords[name] = result
                        resolved_any = True
                elif t == "incenter" and len(args) == 3:
                    pts = [coords[a] for a in args]
                    coords[name] = _incenter(*pts)
                    resolved_any = True
                elif t == "projection" and len(args) == 3:
                    # args = [point_to_project, line_a, line_b]
                    p = coords[args[0]]
                    a, b = coords[args[1]], coords[args[2]]
                    result = _projection(p, a, b)
                    if result is not None:
                        coords[name] = result
                        resolved_any = True
                elif t == "symmetry" and len(args) == 2:
                    # args = [point, center]
                    p = coords[args[0]]
                    c = coords[args[1]]
                    coords[name] = _symmetry(p, c)
                    resolved_any = True
            except KeyError:
                pass  # Dependency not yet resolved — try next pass
        if not resolved_any:
            break

    return coords


# ---------------------------------------------------------------------------
# Geometric property validation
# ---------------------------------------------------------------------------

def _dot(v1: tuple[float, float], v2: tuple[float, float]) -> float:
    return v1[0] * v2[0] + v1[1] * v2[1]


def _point_to_line_distance(
    p: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
) -> float:
    """Perpendicular distance from point P to line through A and B."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    denom = math.sqrt(dx * dx + dy * dy)
    if denom < 1e-12:
        return _dist(p, a)
    return abs((p[0] - ax) * dy - (p[1] - ay) * dx) / denom


def _vec(p_from: tuple[float, float], p_to: tuple[float, float]) -> tuple[float, float]:
    return (p_to[0] - p_from[0], p_to[1] - p_from[1])


def _angle_at_vertex(
    a: tuple[float, float],
    vertex: tuple[float, float],
    c: tuple[float, float],
) -> float:
    """Unsigned angle ∠AVC at vertex, in radians [0, π]."""
    va = _vec(vertex, a)
    vc = _vec(vertex, c)
    mag_a = math.sqrt(va[0] ** 2 + va[1] ** 2)
    mag_c = math.sqrt(vc[0] ** 2 + vc[1] ** 2)
    if mag_a < 1e-12 or mag_c < 1e-12:
        return 0.0
    cos_angle = _dot(va, vc) / (mag_a * mag_c)
    return math.acos(max(-1.0, min(1.0, cos_angle)))


def _validate_label_present(tikz: str, point_name: str) -> bool:
    """Return True if a label for point_name exists in the TikZ source."""
    for label in extract_labels(tikz):
        if label["type"] == "label_points":
            if any(point_names_match(point_name, p) for p in label["points"]):
                return True
        if label["type"] == "label_point":
            if point_names_match(point_name, label["point"]):
                return True
    return False


def _validate_mark_present(tikz: str, mark_type: str, vertex: str) -> bool:
    """Return True if a mark of mark_type exists with the given vertex."""
    for mark in extract_marks(tikz):
        if mark["type"] != mark_type:
            continue
        if point_names_match(vertex, mark.get("vertex", "")):
            return True
        if point_names_match(vertex, mark.get("from", "")):
            return True
        if point_names_match(vertex, mark.get("to", "")):
            return True
    return False


def validate_geometric_property(
    coords: dict[str, tuple[float, float]],
    property_type: str,
    args: list,
    tolerance: float = 1e-4,
    tikz: str | None = None,
) -> bool | None:
    """
    Validate a geometric property given a resolved coordinate map.

    property_type values:
      - "right_angle":     args = [A, vertex, C] — angle at vertex is 90°
      - "midpoint":        args = [M, A, B] — M is the midpoint of AB
      - "centroid":        args = [G, A, B, C] — G = (A + B + C) / 3
      - "collinear":       args = [A, B, C] — three points are collinear
      - "equal_lengths":   args = [[P1,P2], [P3,P4], ...] — all segments equal
      - "parallel":        args = [[A,B], [C,D]] — lines AB and CD are parallel
      - "perpendicular":   args = [[A,B], [C,D]] — lines AB and CD are perpendicular
      - "point_on_line":   args = [P, A, B] — P lies on line through A,B
      - "point_on_segment": args = [P, A, B] — P lies on segment AB (between A and B)
      - "point_on_circle": args = [P, O, R] — P lies on circle centered at O through R
      - "tangent":         args = [[L1,L2], O, T] — line tangent to circle(center=O) at T
      - "angle_equal":     args = [[A,B,C], [D,E,F]] — ∠ABC == ∠DEF
      - "angle_bisector":  args = [D, A, B, C] — AD bisects ∠BAC
      - "intersects":      args = [[A,B], [C,D], P] — lines AB and CD intersect at P
      - "label_present":   args = ["A"] — label for point A exists (requires tikz=)
      - "mark_present":    args = ["right_angle", "B"] — mark at vertex B (requires tikz=)

    Returns True/False if the property can be checked, None if any required
    coordinates are missing.
    """
    try:
        if property_type == "right_angle":
            a_name, vertex_name, c_name = args
            vertex = coords[vertex_name]
            a = coords[a_name]
            c = coords[c_name]
            va = _vec(vertex, a)
            vc = _vec(vertex, c)
            return abs(_dot(va, vc)) <= tolerance

        elif property_type == "midpoint":
            m_name, a_name, b_name = args
            m = coords[m_name]
            a = coords[a_name]
            b = coords[b_name]
            expected = _midpoint(a, b)
            return (
                abs(m[0] - expected[0]) <= tolerance
                and abs(m[1] - expected[1]) <= tolerance
            )

        elif property_type == "centroid":
            # Componentwise check on (A + B + C) / 3, parallel to the midpoint
            # decision rule. The equivalent "G lies on each median" form would
            # be a numerically equivalent but more expensive consequence.
            g_name, a_name, b_name, c_name = args
            g = coords[g_name]
            expected = _centroid(coords[a_name], coords[b_name], coords[c_name])
            return (
                abs(g[0] - expected[0]) <= tolerance
                and abs(g[1] - expected[1]) <= tolerance
            )

        elif property_type == "collinear":
            a_name, b_name, c_name = args
            a = coords[a_name]
            b = coords[b_name]
            c = coords[c_name]
            # Area of triangle = 0 iff collinear
            area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            return abs(area) <= tolerance

        elif property_type == "equal_lengths":
            if not args:
                return None
            distances = []
            for pair in args:
                p1_name, p2_name = pair
                distances.append(_dist(coords[p1_name], coords[p2_name]))
            if not distances:
                return None
            ref = distances[0]
            return all(abs(d - ref) <= tolerance for d in distances[1:])

        elif property_type == "parallel":
            (a_name, b_name), (c_name, d_name) = args
            a, b = coords[a_name], coords[b_name]
            c, d = coords[c_name], coords[d_name]
            v1 = _vec(a, b)
            v2 = _vec(c, d)
            # Cross product = 0 iff parallel
            cross = v1[0] * v2[1] - v1[1] * v2[0]
            return abs(cross) <= tolerance

        elif property_type == "perpendicular":
            (a_name, b_name), (c_name, d_name) = args
            a, b = coords[a_name], coords[b_name]
            c, d = coords[c_name], coords[d_name]
            v1 = _vec(a, b)
            v2 = _vec(c, d)
            return abs(_dot(v1, v2)) <= tolerance

        elif property_type == "point_on_line":
            p_name, a_name, b_name = args
            p = coords[p_name]
            a = coords[a_name]
            b = coords[b_name]
            area = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
            return abs(area) <= tolerance

        elif property_type == "point_on_segment":
            p_name, a_name, b_name = args
            p = coords[p_name]
            a = coords[a_name]
            b = coords[b_name]
            # Collinear check
            area = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
            if abs(area) > tolerance:
                return False
            # Between check: dist(A,P) + dist(P,B) ≈ dist(A,B)
            return abs(_dist(a, p) + _dist(p, b) - _dist(a, b)) <= tolerance

        elif property_type == "point_on_circle":
            p_name, o_name, r_name = args
            p = coords[p_name]
            o = coords[o_name]
            r = coords[r_name]
            return abs(_dist(o, p) - _dist(o, r)) <= tolerance

        elif property_type == "tangent":
            # args = [[L1, L2], O, T]
            (l1_name, l2_name), o_name, t_name = args
            l1 = coords[l1_name]
            l2 = coords[l2_name]
            o = coords[o_name]
            t = coords[t_name]
            # T must lie on line L1L2
            area = (l2[0] - l1[0]) * (t[1] - l1[1]) - (l2[1] - l1[1]) * (t[0] - l1[0])
            if abs(area) > tolerance:
                return False
            # OT must be perpendicular to line L1L2
            v_line = _vec(l1, l2)
            v_ot = _vec(o, t)
            return abs(_dot(v_line, v_ot)) <= tolerance

        elif property_type == "angle_equal":
            # args = [[A, B, C], [D, E, F]]
            (a_name, b_name, c_name), (d_name, e_name, f_name) = args
            a1 = _angle_at_vertex(coords[a_name], coords[b_name], coords[c_name])
            a2 = _angle_at_vertex(coords[d_name], coords[e_name], coords[f_name])
            return abs(a1 - a2) <= tolerance

        elif property_type == "angle_bisector":
            # args = [D, A, B, C] — AD bisects ∠BAC
            d_name, a_name, b_name, c_name = args
            a = coords[a_name]
            b = coords[b_name]
            c = coords[c_name]
            d = coords[d_name]
            angle_bad = _angle_at_vertex(b, a, d)
            angle_dac = _angle_at_vertex(d, a, c)
            return abs(angle_bad - angle_dac) <= tolerance

        elif property_type == "intersects":
            # args = [[A, B], [C, D], P]
            (a_name, b_name), (c_name, d_name), p_name = args
            result = _inter_ll(
                coords[a_name], coords[b_name],
                coords[c_name], coords[d_name],
            )
            if result is None:
                return False  # Lines are parallel — no intersection
            p = coords[p_name]
            return abs(result[0] - p[0]) <= tolerance and abs(result[1] - p[1]) <= tolerance

        elif property_type == "label_present":
            if tikz is None:
                return None
            point_name = args[0]
            return _validate_label_present(tikz, point_name)

        elif property_type == "mark_present":
            if tikz is None:
                return None
            mark_type, vertex = args[0], args[1]
            return _validate_mark_present(tikz, mark_type, vertex)

        elif property_type == "equidistant_from_sides":
            # args = [P, A, B, C] — P is equidistant from lines AB, BC, CA
            p = coords[args[0]]
            a = coords[args[1]]
            b = coords[args[2]]
            c = coords[args[3]]
            d1 = _point_to_line_distance(p, a, b)
            d2 = _point_to_line_distance(p, b, c)
            d3 = _point_to_line_distance(p, c, a)
            return abs(d1 - d2) <= tolerance and abs(d2 - d3) <= tolerance

    except KeyError:
        return None  # A required coordinate is not in the map

    return None
