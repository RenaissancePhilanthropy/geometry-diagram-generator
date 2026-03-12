"""
Static analysis of TikZ/tkz-euclide code.

Extracts geometric information from TikZ source code using regex patterns,
computes derived coordinates where possible, and validates geometric properties.
No rendering or external tools required.
"""
from __future__ import annotations

import math
import re
from typing import Any

# ---------------------------------------------------------------------------
# Point extraction
# ---------------------------------------------------------------------------

_DEF_POINT_RE = re.compile(
    r"\\tkzDefPoint\s*\(\s*([+-]?\d*\.?\d+)\s*,\s*([+-]?\d*\.?\d+)\s*\)\s*\{(\w+)\}"
)
_COORDINATE_RE = re.compile(
    r"\\coordinate\s*\((\w+)\)\s*at\s*\(\s*([+-]?\d*\.?\d+)\s*,\s*([+-]?\d*\.?\d+)\s*\)"
)


def extract_defined_points(tikz: str) -> dict[str, tuple[float, float]]:
    """Extract explicitly defined points from \\tkzDefPoint(x,y){Name} and \\coordinate(name) at (x,y) commands."""
    points: dict[str, tuple[float, float]] = {}
    for m in _DEF_POINT_RE.finditer(tikz):
        x, y, name = float(m.group(1)), float(m.group(2)), m.group(3)
        points[name] = (x, y)
    for m in _COORDINATE_RE.finditer(tikz):
        name, x, y = m.group(1), float(m.group(2)), float(m.group(3))
        points[name] = (x, y)
    return points


# ---------------------------------------------------------------------------
# Computed / derived point extraction
# ---------------------------------------------------------------------------

_GET_POINT_RE = re.compile(r"\\tkzGetPoint\s*\{(\w+)\}")
_MID_POINT_RE = re.compile(r"\\tkzDefMidPoint\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)")
_CIRCUM_CENTER_RE = re.compile(
    r"\\tkzCircumCenter\s*\(\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*\)"
)
_INTER_LL_RE = re.compile(
    r"\\tkzInterLL\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)"
)
_ORTHO_CENTER_RE = re.compile(
    r"\\tkzOrthoCenter\s*\(\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*\)"
)
_CENTROID_RE = re.compile(
    r"\\tkzCentroid\s*\(\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*\)"
)
# \tkzDefTriangleCenter[in](A,B,C) or [circum] or [ortho] etc.
_TRIANGLE_CENTER_RE = re.compile(
    r"\\tkzDefTriangleCenter\s*\[(\w+)\]\s*\(\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*\)"
)
# \tkzDefPointBy[projection=onto A--B](C) — projection of last arg onto the line
_PROJECTION_RE = re.compile(
    r"\\tkzDefPointBy\s*\[projection=onto\s+(\w+)--(\w+)\]\s*\((\w+)\)"
)
# \tkzDefPointBy[symmetry=center A](B) — reflection of B across A
_SYMMETRY_CENTER_RE = re.compile(
    r"\\tkzDefPointBy\s*\[symmetry=center\s+(\w+)\]\s*\((\w+)\)"
)


def extract_computed_points(tikz: str) -> dict[str, dict[str, Any]]:
    """
    Extract derived points defined via computation commands.
    Returns a dict mapping point name -> {'type': ..., 'args': [...]}.
    These require known coordinates of their inputs to resolve to (x,y).
    """
    computed: dict[str, dict[str, Any]] = {}

    # Pair each computation command with the following \\tkzGetPoint
    # by scanning positionally through the source.
    tokens = list(re.finditer(
        r"(\\tkzDefMidPoint|\\tkzCircumCenter|\\tkzInterLL|\\tkzGetPoint"
        r"|\\tkzOrthoCenter|\\tkzCentroid|\\tkzDefTriangleCenter|\\tkzDefPointBy)\b",
        tikz,
    ))

    pending: dict[str, Any] | None = None
    for tok in tokens:
        cmd = tok.group(1)
        # Find the full command text starting at this token
        rest = tikz[tok.start():]

        if cmd == "\\tkzDefMidPoint":
            m = _MID_POINT_RE.match(rest)
            if m:
                pending = {"type": "midpoint", "args": [m.group(1), m.group(2)]}

        elif cmd == "\\tkzCircumCenter":
            m = _CIRCUM_CENTER_RE.match(rest)
            if m:
                pending = {
                    "type": "circumcenter",
                    "args": [m.group(1), m.group(2), m.group(3)],
                }

        elif cmd == "\\tkzInterLL":
            m = _INTER_LL_RE.match(rest)
            if m:
                pending = {
                    "type": "inter_ll",
                    "args": [m.group(1), m.group(2), m.group(3), m.group(4)],
                }

        elif cmd == "\\tkzOrthoCenter":
            m = _ORTHO_CENTER_RE.match(rest)
            if m:
                pending = {
                    "type": "orthocenter",
                    "args": [m.group(1), m.group(2), m.group(3)],
                }

        elif cmd == "\\tkzCentroid":
            m = _CENTROID_RE.match(rest)
            if m:
                pending = {
                    "type": "centroid",
                    "args": [m.group(1), m.group(2), m.group(3)],
                }

        elif cmd == "\\tkzDefTriangleCenter":
            m = _TRIANGLE_CENTER_RE.match(rest)
            if m:
                kind = m.group(1).lower()
                if kind in ("in", "circum", "ortho"):
                    type_map = {"in": "incenter", "circum": "circumcenter", "ortho": "orthocenter"}
                    pending = {
                        "type": type_map[kind],
                        "args": [m.group(2), m.group(3), m.group(4)],
                    }
                elif kind == "centroid":
                    pending = {
                        "type": "centroid",
                        "args": [m.group(2), m.group(3), m.group(4)],
                    }

        elif cmd == "\\tkzDefPointBy":
            m = _PROJECTION_RE.match(rest)
            if m:
                pending = {
                    "type": "projection",
                    "args": [m.group(3), m.group(1), m.group(2)],  # project point, line_a, line_b
                }
            else:
                m = _SYMMETRY_CENTER_RE.match(rest)
                if m:
                    pending = {
                        "type": "symmetry",
                        "args": [m.group(2), m.group(1)],  # point to reflect, center
                    }

        elif cmd == "\\tkzGetPoint":
            m = _GET_POINT_RE.match(rest)
            if m and pending is not None:
                computed[m.group(1)] = pending
                pending = None

    return computed


# ---------------------------------------------------------------------------
# Draw command extraction
# ---------------------------------------------------------------------------

_POLYGON_RE = re.compile(r"\\tkzDrawPolygon\s*\(([^)]+)\)")
_SEGMENT_RE = re.compile(r"\\tkzDrawSegment(?:\[[^\]]*\])?\s*\(([^)]+)\)")
_LINE_RE = re.compile(r"\\tkzDrawLine(?:\[[^\]]*\])?\s*\(([^)]+)\)")
_CIRCLE_RE = re.compile(r"\\tkzDrawCircle(?:\[[^\]]*\])?\s*\(([^)]+)\)")


def _split_args(s: str) -> list[str]:
    return [p.strip() for p in s.split(",") if p.strip()]


def extract_draw_commands(tikz: str) -> list[dict[str, Any]]:
    """Extract draw commands: polygon, segment, line, circle."""
    commands: list[dict[str, Any]] = []

    for m in _POLYGON_RE.finditer(tikz):
        pts = _split_args(m.group(1))
        if len(pts) >= 2:
            edges = [(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
            commands.append({"type": "polygon", "points": pts, "edges": edges})

    for m in _SEGMENT_RE.finditer(tikz):
        pts = _split_args(m.group(1))
        if len(pts) == 2:
            commands.append({"type": "segment", "from": pts[0], "to": pts[1]})

    for m in _LINE_RE.finditer(tikz):
        pts = _split_args(m.group(1))
        if len(pts) == 2:
            commands.append({"type": "line", "through": pts})

    for m in _CIRCLE_RE.finditer(tikz):
        pts = _split_args(m.group(1))
        if len(pts) == 2:
            commands.append({"type": "circle", "center": pts[0], "through": pts[1]})

    return commands


# ---------------------------------------------------------------------------
# Mark extraction
# ---------------------------------------------------------------------------

_RIGHT_ANGLE_RE = re.compile(
    r"\\tkzMarkRightAngle(?:\[[^\]]*\])?\s*\(\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*\)"
)
_ANGLE_MARK_RE = re.compile(
    r"\\tkzMarkAngle(?:\[[^\]]*\])?\s*\(\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*\)"
)
_SEGMENT_MARK_RE = re.compile(
    r"\\tkzMarkSegment(?:\[[^\]]*\])?\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)"
)


def extract_marks(tikz: str) -> list[dict[str, Any]]:
    """Extract mark commands: right angles, angles, segment tick marks."""
    marks: list[dict[str, Any]] = []

    for m in _RIGHT_ANGLE_RE.finditer(tikz):
        marks.append({
            "type": "right_angle",
            "from": m.group(1),
            "vertex": m.group(2),
            "to": m.group(3),
        })

    for m in _ANGLE_MARK_RE.finditer(tikz):
        marks.append({
            "type": "angle",
            "from": m.group(1),
            "vertex": m.group(2),
            "to": m.group(3),
        })

    for m in _SEGMENT_MARK_RE.finditer(tikz):
        marks.append({"type": "segment_mark", "from": m.group(1), "to": m.group(2)})

    return marks


# ---------------------------------------------------------------------------
# Label extraction
# ---------------------------------------------------------------------------

_LABEL_POINTS_RE = re.compile(
    r"\\tkzLabelPoints(?:\[[^\]]*\])?\s*\(([^)]+)\)"
)
_LABEL_POINT_RE = re.compile(
    r"\\tkzLabelPoint(?:\[[^\]]*\])?\s*\((\w+)\)\s*\{([^}]+)\}"
)
_TKZ_GRID_RE = re.compile(r"\\tkzGrid\b")
_TKZ_AXES_RE = re.compile(r"\\tkzAxeXY\b")
_RAW_GRID_RE = re.compile(
    r"\\draw(?:\[[^\]]*\])?\s*\([^)]*\)\s*grid\s*\([^)]*\)"
)
_RAW_AXIS_DRAW_RE = re.compile(
    r"\\draw(?:\[[^\]]*->?[^\]]*\])?\s*"
    r"\(\s*([+-]?\d*\.?\d+)\s*,\s*([+-]?\d*\.?\d+)\s*\)\s*--\s*"
    r"\(\s*([+-]?\d*\.?\d+)\s*,\s*([+-]?\d*\.?\d+)\s*\)"
)


def extract_labels(tikz: str) -> list[dict[str, Any]]:
    """Extract label commands."""
    labels: list[dict[str, Any]] = []

    for m in _LABEL_POINTS_RE.finditer(tikz):
        pts = _split_args(m.group(1))
        labels.append({"type": "label_points", "points": pts})

    for m in _LABEL_POINT_RE.finditer(tikz):
        labels.append({"type": "label_point", "point": m.group(1), "text": m.group(2)})

    return labels


# ---------------------------------------------------------------------------
# Canvas extraction
# ---------------------------------------------------------------------------

def _raw_axes_present(tikz: str) -> bool:
    """Return True for common raw TikZ x/y axes through the origin."""
    has_horizontal = False
    has_vertical = False

    for match in _RAW_AXIS_DRAW_RE.finditer(tikz):
        x1, y1, x2, y2 = (float(match.group(i)) for i in range(1, 5))
        if abs(y1 - y2) <= 1e-9 and min(x1, x2) <= 0 <= max(x1, x2) and abs(y1) <= 1e-9:
            has_horizontal = True
        if abs(x1 - x2) <= 1e-9 and min(y1, y2) <= 0 <= max(y1, y2) and abs(x1) <= 1e-9:
            has_vertical = True
        if has_horizontal and has_vertical:
            return True

    return False


def extract_canvas_features(tikz: str) -> dict[str, bool]:
    """
    Extract visible canvas features from TikZ code.

    Currently detects:
      - grid via \\tkzGrid or a common raw-TikZ `grid` draw command
      - axes via \\tkzAxeXY or common raw-TikZ arrowed axes through the origin
    """
    return {
        "grid": bool(_TKZ_GRID_RE.search(tikz) or _RAW_GRID_RE.search(tikz)),
        "axes": bool(_TKZ_AXES_RE.search(tikz) or _raw_axes_present(tikz)),
    }


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
    # Altitude from A perpendicular to BC, altitude from B perpendicular to CA
    # Foot of altitude from A onto BC (any point on altitude from A: A and A + perp-to-BC)
    # Altitude through A in direction perpendicular to BC: direction = (-(cy-by), cx-bx)
    # Parameterize: A + t*(perp_BC) and B + s*(perp_CA)
    # Intersection via _inter_ll using two points on each altitude
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


def resolve_all_coordinates(tikz: str) -> dict[str, tuple[float, float]]:
    """
    Build a full coordinate map combining explicit definitions with
    computable derived points.

    Points that require runtime rendering (e.g. \\tkzInterCC) are omitted
    rather than guessed.
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
        if label["type"] == "label_points" and point_name in label["points"]:
            return True
        if label["type"] == "label_point" and label["point"] == point_name:
            return True
    return False


def _validate_mark_present(tikz: str, mark_type: str, vertex: str) -> bool:
    """Return True if a mark of mark_type exists with the given vertex."""
    for mark in extract_marks(tikz):
        if mark["type"] != mark_type:
            continue
        # Right-angle and angle marks have an explicit "vertex" key
        if mark.get("vertex") == vertex:
            return True
        # Segment marks use "from"/"to"
        if mark.get("from") == vertex or mark.get("to") == vertex:
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


# ---------------------------------------------------------------------------
# Scenario-level checks
# ---------------------------------------------------------------------------

def validate_required_labels(tikz: str, required: list[str]) -> dict[str, Any]:
    """
    Check that all required point labels appear in the TikZ source.
    Returns {"passed": bool, "missing": list[str]}.
    """
    labeled: set[str] = set()
    for label in extract_labels(tikz):
        if label["type"] == "label_points":
            labeled.update(label["points"])
        elif label["type"] == "label_point":
            labeled.add(label["point"])
    missing = [name for name in required if name not in labeled]
    return {"passed": len(missing) == 0, "missing": missing}


def validate_required_canvas(tikz: str, required_canvas: dict[str, bool]) -> dict[str, Any]:
    """
    Check that required visible canvas features are present.

    Returns {"passed": bool, "missing": list[str], "features": dict[str, bool]}.
    """
    features = extract_canvas_features(tikz)
    missing = [
        feature
        for feature, required in required_canvas.items()
        if required and not features.get(feature, False)
    ]
    return {
        "passed": len(missing) == 0,
        "missing": missing,
        "features": features,
    }


def validate_expected_points(
    coords: dict[str, tuple[float, float]],
    expected_points: dict[str, list[float] | tuple[float, float]],
    tolerance: float = 1e-4,
) -> dict[str, Any]:
    """
    Check that named points resolve to the expected coordinates.

    Returns:
      {"passed": bool, "missing": list[str], "mismatches": {name: {...}}}
    """
    missing: list[str] = []
    mismatches: dict[str, dict[str, list[float]]] = {}

    for name, expected in expected_points.items():
        if name not in coords:
            missing.append(name)
            continue
        expected_xy = (float(expected[0]), float(expected[1]))
        actual_xy = coords[name]
        if (
            abs(actual_xy[0] - expected_xy[0]) > tolerance
            or abs(actual_xy[1] - expected_xy[1]) > tolerance
        ):
            mismatches[name] = {
                "expected": [expected_xy[0], expected_xy[1]],
                "actual": [actual_xy[0], actual_xy[1]],
            }

    return {
        "passed": len(missing) == 0 and len(mismatches) == 0,
        "missing": missing,
        "mismatches": mismatches,
    }


def validate_required_entities(tikz: str, required: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Check that all required draw entities appear in the TikZ source.

    Each entry in `required` is a dict with at least "type" (matching
    extract_draw_commands types: polygon, segment, line, circle), and
    optionally "args" — a dict of key-value pairs that must match the
    extracted command dict.

    Returns {"passed": bool, "missing": list[dict]}.
    """
    commands = extract_draw_commands(tikz)
    missing: list[dict[str, Any]] = []
    for entity in required:
        entity_type = entity.get("type")
        entity_args = entity.get("args", {})
        found = any(
            cmd["type"] == entity_type
            and all(cmd.get(k) == v for k, v in entity_args.items())
            for cmd in commands
        )
        if not found:
            missing.append(entity)
    return {"passed": len(missing) == 0, "missing": missing}
