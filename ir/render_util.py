"""Shared rendering utilities used by both TikZ and SVG backends.

Contains geometry helpers, IR navigation helpers, bounds computation,
coordinate extraction, helper-point synthesis, and numeric formatting.
Neither module has any backend-specific logic — both to_tikz.py and
to_svg.py import from here.
"""
from __future__ import annotations

import math
from typing import Any

import sympy.geometry as spg

import ir.ir as ir
from ir.to_sympy import Arc, SymTable


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BOUNDS_PADDING = 0.8
_TICK_HALF_LENGTH = 0.05


# ---------------------------------------------------------------------------
# Coordinate extraction and helper-point synthesis
# ---------------------------------------------------------------------------

def extract_coords(sym: SymTable) -> dict[str, tuple[float, float]]:
    """Return {id: (x, y)} for every Point in the symbol table."""
    coords: dict[str, tuple[float, float]] = {}
    for def_id, obj in sym.items():
        if isinstance(obj, spg.Point):
            coords[def_id] = (sympy_to_float(obj.x), sympy_to_float(obj.y))
    return coords


def synthesize_helpers(
    diagram: ir.DiagramIR,
    sym: SymTable,
    coords: dict[str, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    """Create auxiliary points not in the IR but needed for drawing.

    Returns a dict of helper-name → (x, y).  Helpers are:
    - ``_lp_{id}`` — second anchor for non-LineThrough line types
    - ``_rt_{id}`` — through-point for CircleCenterRadius
    - ``_cc_{id}`` — center for CircleThrough3
    """
    helpers: dict[str, tuple[float, float]] = {}
    for stmt in diagram.define:
        line_obj = sym.get(stmt.id)
        if isinstance(stmt, ir.LineParallelThrough):
            helpers[f"_lp_{stmt.id}"] = second_line_point(line_obj, sym[stmt.through])
        elif isinstance(stmt, ir.LinePerpendicularThrough):
            helpers[f"_lp_{stmt.id}"] = second_line_point(line_obj, sym[stmt.through])
        elif isinstance(stmt, ir.LineAngleBisector):
            helpers[f"_lp_{stmt.id}"] = second_line_point(line_obj, sym[stmt.vertex])
        elif isinstance(stmt, ir.LineTangent):
            helpers[f"_lp_{stmt.id}"] = second_line_point(line_obj, sym[stmt.point])
        elif isinstance(stmt, ir.CircleCenterRadius):
            circ = sym[stmt.id]
            cx, cy = coords[stmt.center]
            r = sympy_to_float(circ.radius)
            helpers[f"_rt_{stmt.id}"] = (cx + r, cy)
        elif isinstance(stmt, ir.CircleThrough3):
            circ = sym[stmt.id]
            helpers[f"_cc_{stmt.id}"] = (
                sympy_to_float(circ.center.x),
                sympy_to_float(circ.center.y),
            )
        elif isinstance(stmt, (ir.EllipseCenterAxes, ir.EllipseBBox, ir.EllipseFoci, ir.EllipseCenterEccentricity)):
            ell = sym[stmt.id]
            helpers[f"_ec_{stmt.id}"] = (
                sympy_to_float(ell.center.x),
                sympy_to_float(ell.center.y),
            )
    return helpers


# ---------------------------------------------------------------------------
# IR object navigation helpers
# ---------------------------------------------------------------------------

def poly_verts(obj_id: str, stmt_by_id: dict) -> list[str]:
    """Return the ordered vertex point-IDs for a Triangle or Polygon DefStmt."""
    stmt = stmt_by_id[obj_id]
    match stmt:
        case ir.Triangle(a=a, b=b, c=c):
            return [a, b, c]
        case ir.Polygon(points=pts):
            return list(pts)
        case ir.PolygonExterior(a=a, b=b, sides=sides):
            verts = [a, b]
            for i in range(2, sides):
                verts.append(f"{obj_id}_v{i}")
            return verts
        case _:
            raise ValueError(f"Cannot get polygon vertices for {stmt.kind!r}")


def seg_endpoints(seg_id: str, stmt_by_id: dict) -> tuple[str, str]:
    """Return (a, b) endpoint IDs for a Segment DefStmt."""
    stmt = stmt_by_id[seg_id]
    if not isinstance(stmt, ir.Segment):
        raise ValueError(f"Expected Segment def for {seg_id!r}, got {stmt.kind!r}")
    return stmt.a, stmt.b


def line_endpoints(
    line_id: str,
    stmt_by_id: dict,
    helpers: dict[str, tuple[float, float]],
) -> tuple[str, str]:
    """Return two point names to use when drawing a Line."""
    stmt = stmt_by_id[line_id]
    match stmt:
        case ir.LineThrough(p=p, q=q):
            return p, q
        case ir.LineParallelThrough(through=t):
            return t, f"_lp_{line_id}"
        case ir.LinePerpendicularThrough(through=t):
            return t, f"_lp_{line_id}"
        case ir.LineAngleBisector(vertex=v):
            return v, f"_lp_{line_id}"
        case ir.LineTangent(point=p):
            return p, f"_lp_{line_id}"
        case _:
            raise ValueError(f"Unknown line def kind {stmt.kind!r}")


def circle_center_through(
    circle_id: str,
    stmt_by_id: dict,
    helpers: dict[str, tuple[float, float]],
) -> tuple[str, str]:
    """Return (center_name, through_name) for drawing a Circle."""
    stmt = stmt_by_id[circle_id]
    match stmt:
        case ir.CircleCenterPoint(center=c, through=t):
            return c, t
        case ir.CircleCenterRadius(center=c):
            return c, f"_rt_{circle_id}"
        case ir.CircleThrough3(a=a):
            return f"_cc_{circle_id}", a
        case _:
            raise ValueError(f"Unknown circle def kind {stmt.kind!r}")


def ellipse_params(
    ellipse_id: str,
    sym: "SymTable",
) -> tuple[float, float, float, float]:
    """Return (cx, cy, hradius, vradius) for the given ellipse id."""
    ell = sym[ellipse_id]
    return (
        sympy_to_float(ell.center.x),
        sympy_to_float(ell.center.y),
        sympy_to_float(ell.hradius),
        sympy_to_float(ell.vradius),
    )


def arc_params(
    arc_id: str,
    sym: "SymTable",
) -> tuple[float, float, float, float, float, float, float]:
    """Return (cx, cy, r, start_deg, end_deg, sx, sy) for the given arc id.

    - ``start_deg`` / ``end_deg`` delimit a math-CCW sweep (end_deg > start_deg).
    - The magnitude ``end_deg - start_deg`` is ≤180° when ``reflex=False``
      (minor arc, the default) and >180° when ``reflex=True``.
    - ``sx``, ``sy`` are the Cartesian coordinates of the returned start point
      (may be swapped relative to the IR's ``start`` to satisfy the above).
    """
    arc = sym[arc_id]
    cx = sympy_to_float(arc.center.x)
    cy = sympy_to_float(arc.center.y)
    sx = sympy_to_float(arc.start.x)
    sy = sympy_to_float(arc.start.y)
    ex = sympy_to_float(arc.end.x)
    ey = sympy_to_float(arc.end.y)
    r = sympy_to_float(arc.radius)
    s_deg = math.degrees(math.atan2(sy - cy, sx - cx)) % 360.0
    e_deg = math.degrees(math.atan2(ey - cy, ex - cx)) % 360.0
    ccw = (e_deg - s_deg) % 360.0
    if ccw == 0:
        ccw = 360.0
    is_ccw_minor = ccw <= 180.0
    want_reflex = bool(getattr(arc, "reflex", False))
    # Swap endpoints iff the math-CCW traversal does NOT match the requested arc
    if is_ccw_minor == want_reflex:
        sx, sy, ex, ey = ex, ey, sx, sy
        s_deg, e_deg = e_deg, s_deg
    if e_deg <= s_deg:
        e_deg += 360.0
    return (cx, cy, r, s_deg, e_deg, sx, sy)


# ---------------------------------------------------------------------------
# Bounds computation
# ---------------------------------------------------------------------------

def expand_bounds_for_geometry(
    xmin: float, xmax: float, ymin: float, ymax: float,
    sym: SymTable,
) -> tuple[float, float, float, float]:
    """Expand (xmin, xmax, ymin, ymax) to include circles, ellipses, and arcs.

    Used when a Canvas is already established and we need to ensure geometry
    that extends outside the point-based bounds (e.g. a large circle) is not
    clipped.
    """
    for obj in sym.values():
        if isinstance(obj, spg.Ellipse):  # covers Circle
            cx, cy = sympy_to_float(obj.center.x), sympy_to_float(obj.center.y)
            a = sympy_to_float(obj.hradius)
            b = sympy_to_float(obj.vradius)
            if cx - a < xmin:
                xmin = cx - a - BOUNDS_PADDING
            if cx + a > xmax:
                xmax = cx + a + BOUNDS_PADDING
            if cy - b < ymin:
                ymin = cy - b - BOUNDS_PADDING
            if cy + b > ymax:
                ymax = cy + b + BOUNDS_PADDING
        elif isinstance(obj, Arc):
            cx, cy = sympy_to_float(obj.center.x), sympy_to_float(obj.center.y)
            r = sympy_to_float(obj.radius)
            # Conservatively use full enclosing circle.
            if cx - r < xmin:
                xmin = cx - r - BOUNDS_PADDING
            if cx + r > xmax:
                xmax = cx + r + BOUNDS_PADDING
            if cy - r < ymin:
                ymin = cy - r - BOUNDS_PADDING
            if cy + r > ymax:
                ymax = cy + r + BOUNDS_PADDING
    return xmin, xmax, ymin, ymax


def compute_bounds(
    coords: dict[str, tuple[float, float]],
    helpers: dict[str, tuple[float, float]],
    sym: SymTable,
) -> tuple[float, float, float, float]:
    """Compute tight (xmin, xmax, ymin, ymax) from geometry, with padding."""
    all_pts = list(coords.values()) + list(helpers.values())
    if not all_pts:
        return expand_bounds_for_geometry(-5.0, 5.0, -5.0, 5.0, sym)
    xs, ys = zip(*all_pts)
    xmin = min(xs) - BOUNDS_PADDING
    xmax = max(xs) + BOUNDS_PADDING
    ymin = min(ys) - BOUNDS_PADDING
    ymax = max(ys) + BOUNDS_PADDING
    return expand_bounds_for_geometry(xmin, xmax, ymin, ymax, sym)


def effective_canvas_bounds(canvas: ir.Canvas) -> tuple[float, float, float, float]:
    """Return canvas bounds, expanding to include the origin when axes are requested."""
    xmin, xmax, ymin, ymax = canvas.xmin, canvas.xmax, canvas.ymin, canvas.ymax
    if canvas.axes:
        xmin = min(xmin, 0.0)
        xmax = max(xmax, 0.0)
        ymin = min(ymin, 0.0)
        ymax = max(ymax, 0.0)
    return xmin, xmax, ymin, ymax


# ---------------------------------------------------------------------------
# Geometric helpers
# ---------------------------------------------------------------------------

def orient_angle(
    a: str,
    o: str,
    b: str,
    sym: SymTable,
    which: str,
) -> tuple[str, str, str]:
    """Return (a, o, b) or (b, o, a) so angle marks trace the correct arc.

    The 2D cross product (A-O) x (B-O) tells us which arc is CCW:
      cross > 0 → CCW sweep is the small (interior) arc
      cross < 0 → CCW sweep is the large (exterior/reflex) arc
    """
    oa = sym[a] - sym[o]
    ob = sym[b] - sym[o]
    cross = float((oa.x * ob.y - oa.y * ob.x).evalf())
    want_small = (which == "interior")
    if (want_small and cross < 0) or (not want_small and cross > 0):
        return b, o, a
    return a, o, b


def second_line_point(
    line: spg.Line,
    anchor: spg.Point,
) -> tuple[float, float]:
    """Return coordinates of a second distinct point on ``line``, offset from ``anchor``.

    Uses the line's direction vector to step by 1 unit from anchor.
    """
    p1, p2 = line.p1, line.p2
    dx = sympy_to_float(p2.x) - sympy_to_float(p1.x)
    dy = sympy_to_float(p2.y) - sympy_to_float(p1.y)
    mag = (dx ** 2 + dy ** 2) ** 0.5
    if mag < 1e-12:
        return (sympy_to_float(p2.x), sympy_to_float(p2.y))
    ax, ay = sympy_to_float(anchor.x), sympy_to_float(anchor.y)
    return (ax + dx / mag, ay + dy / mag)


# ---------------------------------------------------------------------------
# Numeric formatting
# ---------------------------------------------------------------------------

def sympy_to_float(expr: Any) -> float:
    """Convert a SymPy expression to a Python float."""
    try:
        return float(expr.evalf())
    except Exception:
        return float(expr)


def fmt_num(value: float) -> str:
    """Format a float for use in numeric output (TikZ coords, SVG attributes)."""
    if abs(value) <= 1e-9:
        value = 0.0
    return f"{value:g}"


def fmt_label_num(value: float) -> str:
    """Format a float as a human-readable label (integer when whole)."""
    rounded = round(value)
    if abs(value - rounded) <= 1e-9:
        return str(int(rounded))
    return fmt_num(value)


# ---------------------------------------------------------------------------
# Grid / axis tick math
# ---------------------------------------------------------------------------

def tick_values(lo: float, hi: float, step: float) -> list[float]:
    """Return tick positions between lo and hi at the given step, excluding 0."""
    if step <= 0:
        return []
    start = math.ceil(lo / step)
    end = math.floor(hi / step)
    values: list[float] = []
    for multiple in range(start, end + 1):
        value = multiple * step
        if abs(value) <= 1e-9:
            continue
        values.append(value)
    return values


def round_down_to_step(value: float, step: float) -> float:
    return math.floor(value / step) * step


def round_up_to_step(value: float, step: float) -> float:
    return math.ceil(value / step) * step
