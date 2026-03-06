from __future__ import annotations

from typing import Any

import sympy as sp
import sympy.geometry as spg

import ir.ir as ir
from ir.to_sympy import SymTable


def ir_to_tikz(diagram: ir.DiagramIR, sym: SymTable) -> str:
    """
    Compile a DiagramIR + resolved SymTable to a tkz-euclide TikZ body string.
    The returned string is intended to be placed inside a tikzpicture environment
    (the renderer wraps it automatically).
    """
    # --- Phase 1: extract float coordinates for every Point in the symbol table ---
    coords: dict[str, tuple[float, float]] = {}
    for def_id, obj in sym.items():
        if isinstance(obj, spg.Point):
            coords[def_id] = (_f(obj.x), _f(obj.y))

    # --- Phase 2: index DefStmts by id ---
    stmt_by_id: dict[str, Any] = {stmt.id: stmt for stmt in diagram.define}

    # --- Phase 3: synthesize helper points ---
    # helpers: name -> (x, y) for points that don't have IR ids but are needed for drawing
    helpers: dict[str, tuple[float, float]] = {}

    for stmt in diagram.define:
        line_obj = sym.get(stmt.id)
        # Second anchor point for non-LineThrough line types
        if isinstance(stmt, ir.LineParallelThrough):
            helpers[f"_lp_{stmt.id}"] = _second_line_point(line_obj, sym[stmt.through])
        elif isinstance(stmt, ir.LinePerpendicularThrough):
            helpers[f"_lp_{stmt.id}"] = _second_line_point(line_obj, sym[stmt.through])
        elif isinstance(stmt, ir.LineAngleBisector):
            helpers[f"_lp_{stmt.id}"] = _second_line_point(line_obj, sym[stmt.vertex])
        elif isinstance(stmt, ir.LineTangent):
            helpers[f"_lp_{stmt.id}"] = _second_line_point(line_obj, sym[stmt.point])
        # Through-point for CircleCenterRadius (no explicit through-point in IR)
        elif isinstance(stmt, ir.CircleCenterRadius):
            circ = sym[stmt.id]
            cx, cy = coords[stmt.center]
            r = _f(circ.radius)
            helpers[f"_rt_{stmt.id}"] = (cx + r, cy)
        # Two points for Ray (anchor already named, need direction point)
        elif isinstance(stmt, ir.Ray):
            # sym object is spg.Ray; p2 is the direction point (= sym[stmt.b])
            # stmt.b is already a named point, so nothing extra needed
            pass

    # --- Phase 4: canvas / init ---
    lines: list[str] = []
    canvas = diagram.canvas  # may be None
    if canvas is not None:
        xmin, xmax, ymin, ymax = canvas.xmin, canvas.xmax, canvas.ymin, canvas.ymax
    else:
        xmin, xmax, ymin, ymax = _compute_bounds(coords, helpers, sym)
    lines.append(
        f"\\tkzInit[xmin={xmin:.4g},xmax={xmax:.4g},"
        f"ymin={ymin:.4g},ymax={ymax:.4g}]"
    )
    if canvas is None or canvas.clip:
        lines.append("\\tkzClip")
    if canvas is not None and canvas.grid:
        lines.append("\\tkzGrid")
    if canvas is not None and canvas.axes:
        lines.append("\\tkzAxeXY")
    lines.append("")

    # --- Phase 5: emit \tkzDefPoint for all named points and helpers ---
    for pid, (x, y) in coords.items():
        lines.append(f"\\tkzDefPoint({x:.6g},{y:.6g}){{{pid}}}")
    for hid, (x, y) in helpers.items():
        lines.append(f"\\tkzDefPoint({x:.6g},{y:.6g}){{{hid}}}")
    lines.append("")

    # --- Phase 6: emit render ops ---
    for op in diagram.render:
        chunk = _emit_op(op, sym, stmt_by_id, helpers, diagram.styles)
        lines.extend(chunk)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Render op emitters
# ---------------------------------------------------------------------------

def _emit_op(
    op: Any,
    sym: SymTable,
    stmt_by_id: dict[str, Any],
    helpers: dict[str, tuple[float, float]],
    styles: dict[str, dict],
) -> list[str]:
    out: list[str] = []
    match op:
        case ir.Draw(obj=obj_id, add=add, style=style):
            sym_obj = sym[obj_id]
            sopts = _style_str(style, styles)
            if isinstance(sym_obj, (spg.Triangle, spg.Polygon)):
                verts = _poly_verts(obj_id, stmt_by_id)
                out.append(f"\\tkzDrawPolygon{sopts}({','.join(verts)})")
            elif isinstance(sym_obj, spg.Segment):
                a, b = _seg_pts(obj_id, stmt_by_id)
                out.append(f"\\tkzDrawSegment{sopts}({a},{b})")
            elif isinstance(sym_obj, spg.Line):
                p1, p2 = _line_pts(obj_id, stmt_by_id, helpers)
                add_opt = f"add={add[0]} and {add[1]}" if add else "add=1 and 1"
                opts = _merge_opts(add_opt, sopts)
                out.append(f"\\tkzDrawLine[{opts}]({p1},{p2})")
            elif isinstance(sym_obj, spg.Ray):
                stmt = stmt_by_id[obj_id]
                out.append(f"\\tkzDrawLine[add=0 and 1{sopts}]({stmt.a},{stmt.b})")
            elif isinstance(sym_obj, spg.Circle):
                center, through = _circle_pts(obj_id, stmt_by_id, helpers)
                out.append(f"\\tkzDrawCircle{sopts}({center},{through})")
            else:
                out.append(f"% Draw: unhandled type {type(sym_obj).__name__} for {obj_id!r}")

        case ir.DrawPoints(points=points, style=style):
            sopts = _style_str(style, styles)
            out.append(f"\\tkzDrawPoints{sopts}({','.join(points)})")

        case ir.Fill(obj=obj_id, opacity=opacity, style=style):
            sym_obj = sym[obj_id]
            fill_opts = f"[fill=blue!20,opacity={opacity}]"
            if isinstance(sym_obj, (spg.Triangle, spg.Polygon)):
                verts = _poly_verts(obj_id, stmt_by_id)
                out.append(f"\\tkzFillPolygon{fill_opts}({','.join(verts)})")
            elif isinstance(sym_obj, spg.Circle):
                center, through = _circle_pts(obj_id, stmt_by_id, helpers)
                out.append(f"\\tkzFillCircle{fill_opts}({center},{through})")

        case ir.MarkRightAngles(angles=angles, style=style):
            sopts = _style_str(style, styles)
            for angle in angles:
                out.append(f"\\tkzMarkRightAngle{sopts}({angle.a},{angle.o},{angle.b})")

        case ir.MarkAngles(angles=angles, group=group, which=which, style=style):
            sopts = _style_str(style or group, styles)
            for angle in angles:
                a, o, b = angle.a, angle.o, angle.b
                if which == "exterior":
                    a, b = b, a
                out.append(f"\\tkzMarkAngle[size=0.5]{sopts}({a},{o},{b})")

        case ir.MarkSegments(segs=segs, group=group, style=style):
            mark_key = style or group
            if mark_key and mark_key in styles:
                sopts = _style_str(mark_key, styles)
            else:
                sopts = "[mark=|]"
            for seg_id in segs:
                a, b = _seg_pts(seg_id, stmt_by_id)
                out.append(f"\\tkzMarkSegment{sopts}({a},{b})")

        case ir.LabelPoint(p=p, text=text, pos=pos, style=style):
            label = text if text is not None else p
            pos_str = f"[{pos}]" if pos and pos != "auto" else ""
            out.append(f"\\tkzLabelPoint{pos_str}({p}){{${label}$}}")

        case ir.LabelAngle(angle=angle, text=text, pos=pos, style=style):
            sopts = f"[pos={pos}]" if pos is not None else ""
            out.append(f"\\tkzLabelAngle{sopts}({angle.a},{angle.o},{angle.b}){{${text}$}}")

        case ir.LabelSegment(seg=seg_id, text=text, pos=pos, style=style):
            a, b = _seg_pts(seg_id, stmt_by_id)
            sopts = f"[pos={pos}]" if pos is not None else ""
            out.append(f"\\tkzLabelSegment{sopts}({a},{b}){{${text}$}}")

    return out


# ---------------------------------------------------------------------------
# Object vertex / endpoint helpers
# ---------------------------------------------------------------------------

def _poly_verts(obj_id: str, stmt_by_id: dict) -> list[str]:
    """Return the ordered vertex point-IDs for a Triangle or Polygon DefStmt."""
    stmt = stmt_by_id[obj_id]
    match stmt:
        case ir.Triangle(a=a, b=b, c=c):
            return [a, b, c]
        case ir.Polygon(points=pts):
            return list(pts)
        case _:
            raise ValueError(f"Cannot get polygon vertices for {stmt.kind!r}")


def _seg_pts(seg_id: str, stmt_by_id: dict) -> tuple[str, str]:
    """Return (a, b) endpoint IDs for a Segment DefStmt."""
    stmt = stmt_by_id[seg_id]
    if not isinstance(stmt, ir.Segment):
        raise ValueError(f"Expected Segment def for {seg_id!r}, got {stmt.kind!r}")
    return stmt.a, stmt.b


def _line_pts(line_id: str, stmt_by_id: dict, helpers: dict) -> tuple[str, str]:
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


def _circle_pts(circle_id: str, stmt_by_id: dict, helpers: dict) -> tuple[str, str]:
    """Return (center_name, through_name) for drawing a Circle."""
    stmt = stmt_by_id[circle_id]
    match stmt:
        case ir.CircleCenterPoint(center=c, through=t):
            return c, t
        case ir.CircleCenterRadius(center=c):
            return c, f"_rt_{circle_id}"
        case ir.CircleThrough3(a=a, b=b, c=c):
            return a, b  # use first two defining points (center is circumcenter)
        case _:
            raise ValueError(f"Unknown circle def kind {stmt.kind!r}")


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------

def _style_str(style_key: str | None, styles: dict) -> str:
    """Return a TikZ option string like '[color=red,thick]' or '' if no style."""
    if not style_key or style_key not in styles:
        return ""
    opts = ",".join(
        (k if v is True else f"{k}={v}")
        for k, v in styles[style_key].items()
        if v is not False
    )
    return f"[{opts}]" if opts else ""


def _merge_opts(base: str, extra_bracket: str) -> str:
    """Merge base option string with the content of an extra [opts] bracket."""
    if not extra_bracket:
        return base
    inner = extra_bracket.strip("[]")
    return f"{base},{inner}" if inner else base


# ---------------------------------------------------------------------------
# Geometric helpers
# ---------------------------------------------------------------------------

_BOUNDS_PADDING = 0.8


def _compute_bounds(
    coords: dict[str, tuple[float, float]],
    helpers: dict[str, tuple[float, float]],
    sym: SymTable,
) -> tuple[float, float, float, float]:
    """Compute tight (xmin, xmax, ymin, ymax) from geometry, with padding."""
    all_pts = list(coords.values()) + list(helpers.values())
    for obj in sym.values():
        if isinstance(obj, spg.Circle):
            cx, cy = _f(obj.center.x), _f(obj.center.y)
            r = _f(obj.radius)
            all_pts.extend([(cx - r, cy - r), (cx + r, cy + r)])
    if not all_pts:
        return (-5.0, 5.0, -5.0, 5.0)
    xs, ys = zip(*all_pts)
    return (
        min(xs) - _BOUNDS_PADDING,
        max(xs) + _BOUNDS_PADDING,
        min(ys) - _BOUNDS_PADDING,
        max(ys) + _BOUNDS_PADDING,
    )


def _f(expr) -> float:
    """Convert a SymPy expression to float."""
    try:
        return float(expr.evalf())
    except Exception:
        return float(expr)


def _second_line_point(
    line: spg.Line,
    anchor: spg.Point,
) -> tuple[float, float]:
    """
    Return coordinates of a second distinct point on `line`, offset from `anchor`.
    Uses the line's direction vector to step by 1 unit from anchor.
    """
    # Direction vector from line's two defining points
    p1, p2 = line.p1, line.p2
    dx = _f(p2.x) - _f(p1.x)
    dy = _f(p2.y) - _f(p1.y)
    mag = (dx ** 2 + dy ** 2) ** 0.5
    if mag < 1e-12:
        # Degenerate direction; fall back to p2
        return (_f(p2.x), _f(p2.y))
    ax, ay = _f(anchor.x), _f(anchor.y)
    return (ax + dx / mag, ay + dy / mag)
