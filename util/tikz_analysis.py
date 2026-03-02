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


def extract_defined_points(tikz: str) -> dict[str, tuple[float, float]]:
    """Extract explicitly defined points from \\tkzDefPoint(x,y){Name} commands."""
    points: dict[str, tuple[float, float]] = {}
    for m in _DEF_POINT_RE.finditer(tikz):
        x, y, name = float(m.group(1)), float(m.group(2)), m.group(3)
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
        r"(\\tkzDefMidPoint|\\tkzCircumCenter|\\tkzInterLL|\\tkzGetPoint)\b",
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
# Coordinate resolution
# ---------------------------------------------------------------------------

def _midpoint(p1: tuple[float, float], p2: tuple[float, float]) -> tuple[float, float]:
    return ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)


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


def _vec(p_from: tuple[float, float], p_to: tuple[float, float]) -> tuple[float, float]:
    return (p_to[0] - p_from[0], p_to[1] - p_from[1])


def _dist(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2)


def validate_geometric_property(
    coords: dict[str, tuple[float, float]],
    property_type: str,
    args: list,
    tolerance: float = 1e-4,
) -> bool | None:
    """
    Validate a geometric property given a resolved coordinate map.

    property_type values:
      - "right_angle": args = [A, vertex, C] — angle at vertex is 90°
      - "midpoint": args = [M, A, B] — M is the midpoint of AB
      - "collinear": args = [A, B, C] — three points are collinear
      - "equal_lengths": args = [[P1,P2], [P3,P4], ...] — all segments equal
      - "parallel": args = [[A,B], [C,D]] — lines AB and CD are parallel
      - "perpendicular": args = [[A,B], [C,D]] — lines AB and CD are perpendicular

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

    except KeyError:
        return None  # A required coordinate is not in the map

    return None
