from __future__ import annotations

import logging
import math
from typing import Any

import sympy as sp
import sympy.geometry as spg

import ir.ir as ir
from ir.to_sympy import SymTable

logger = logging.getLogger(__name__)


def ir_to_tikz(diagram: ir.DiagramIR, sym: SymTable, warnings: list[str] | None = None) -> str:
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
        # Circumcenter helper for CircleThrough3 (center is computed, not a named point)
        elif isinstance(stmt, ir.CircleThrough3):
            circ = sym[stmt.id]
            helpers[f"_cc_{stmt.id}"] = (_f(circ.center.x), _f(circ.center.y))
        # Two points for Ray (anchor already named, need direction point)
        elif isinstance(stmt, ir.Ray):
            # sym object is spg.Ray; p2 is the direction point (= sym[stmt.b])
            # stmt.b is already a named point, so nothing extra needed
            pass

    # --- Phase 4: canvas / init ---
    lines: list[str] = []
    canvas = diagram.canvas  # may be None
    if canvas is not None:
        xmin, xmax, ymin, ymax = _effective_canvas_bounds(canvas)
        # Expand only when computed points fall outside the LLM's canvas bounds,
        # so derived geometry (e.g. polygon_exterior vertices) isn't clipped.
        for px, py in list(coords.values()) + list(helpers.values()):
            if px < xmin:
                xmin = px - _BOUNDS_PADDING
            if px > xmax:
                xmax = px + _BOUNDS_PADDING
            if py < ymin:
                ymin = py - _BOUNDS_PADDING
            if py > ymax:
                ymax = py + _BOUNDS_PADDING
    else:
        xmin, xmax, ymin, ymax = _compute_bounds(coords, helpers, sym)
    lines.append(
        f"\\tkzInit[xmin={_fmt_num(xmin)},xmax={_fmt_num(xmax)},"
        f"ymin={_fmt_num(ymin)},ymax={_fmt_num(ymax)}]"
    )
    if canvas is None or canvas.clip:
        lines.append("\\tkzClip")
    if canvas is not None and canvas.grid:
        lines.extend(_emit_grid(canvas, xmin, xmax, ymin, ymax))
    if canvas is not None and canvas.axes:
        lines.extend(_emit_axes(canvas, xmin, xmax, ymin, ymax))
    lines.append("")

    # --- Phase 5: emit \tkzDefPoint for all named points and helpers ---
    for pid, (x, y) in coords.items():
        lines.append(f"\\tkzDefPoint({x:.6g},{y:.6g}){{{pid}}}")
    for hid, (x, y) in helpers.items():
        lines.append(f"\\tkzDefPoint({x:.6g},{y:.6g}){{{hid}}}")
    lines.append("")

    # --- Phase 6: emit render ops ---
    # Pre-compute group -> mark symbol for MarkSegments ops that lack an explicit style.
    _MARK_SYMBOLS = ["|", "||", "|||", "s", "s|", "s||"]
    _styles = diagram.styles or {}
    seg_groups: list[str] = []
    for op in diagram.render:
        if isinstance(op, ir.MarkSegments) and op.group and (op.style or op.group) not in _styles:
            if op.group not in seg_groups:
                seg_groups.append(op.group)
    group_marks = {g: _MARK_SYMBOLS[i % len(_MARK_SYMBOLS)] for i, g in enumerate(seg_groups)}

    for op in diagram.render:
        chunk = _emit_op(op, sym, stmt_by_id, helpers, diagram.styles, group_marks, warnings=warnings)
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
    group_marks: dict[str, str] | None = None,
    warnings: list[str] | None = None,
) -> list[str]:
    out: list[str] = []
    match op:
        case ir.Draw(obj=obj_id, add=add, style=style):
            if obj_id not in sym:
                msg = f"Skipping render op Draw for undefined object '{obj_id}'"
                logger.warning(msg)
                if warnings is not None:
                    warnings.append(msg)
                return out
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
                add_opt = f"add={add[0]} and {add[1]}" if add else "add=20 and 20"
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
            if obj_id not in sym:
                msg = f"Skipping render op Fill for undefined object '{obj_id}'"
                logger.warning(msg)
                if warnings is not None:
                    warnings.append(msg)
                return out
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
                if any(pid not in sym for pid in (angle.a, angle.o, angle.b)):
                    missing = [pid for pid in (angle.a, angle.o, angle.b) if pid not in sym]
                    msg = f"Skipping render op MarkRightAngles for undefined object(s) {missing!r}"
                    logger.warning(msg)
                    if warnings is not None:
                        warnings.append(msg)
                    continue
                out.append(f"\\tkzMarkRightAngle{sopts}({angle.a},{angle.o},{angle.b})")

        case ir.MarkAngles(angles=angles, group=group, which=which, style=style):
            sopts = _style_str(style or group, styles)
            # Map numeric groups to tkz-euclide arc options for visual differentiation.
            # group "1" → 1 arc (default), "2" → arc=ll, "3" → arc=lll
            # group "4"+ → color cycle for further differentiation
            _ARC_OPTS = {"2": "arc=ll", "3": "arc=lll"}
            _COLOR_CYCLE = ["blue", "red", "teal", "purple", "orange"]
            if not sopts and group:
                g = str(group)
                if g in _ARC_OPTS:
                    sopts = f"[{_ARC_OPTS[g]}]"
                else:
                    try:
                        idx = (int(g) - 4) % len(_COLOR_CYCLE)
                        sopts = f"[color={_COLOR_CYCLE[idx]}]"
                    except (ValueError, TypeError):
                        pass
            for angle in angles:
                if any(pid not in sym for pid in (angle.a, angle.o, angle.b)):
                    missing = [pid for pid in (angle.a, angle.o, angle.b) if pid not in sym]
                    msg = f"Skipping render op MarkAngles for undefined object(s) {missing!r}"
                    logger.warning(msg)
                    if warnings is not None:
                        warnings.append(msg)
                    continue
                a, o, b = _orient_angle(angle.a, angle.o, angle.b, sym, which)
                merged = _merge_opts("size=0.5", sopts)
                out.append(f"\\tkzMarkAngle[{merged}]({a},{o},{b})")

        case ir.MarkSegments(segs=segs, group=group, style=style):
            mark_key = style or group
            if mark_key and mark_key in styles:
                sopts = _style_str(mark_key, styles)
            elif group and group_marks and group in group_marks:
                sopts = f"[mark={group_marks[group]}]"
            else:
                sopts = "[mark=|]"
            for seg_id in segs:
                if seg_id not in stmt_by_id:
                    msg = f"Skipping render op MarkSegments for undefined object '{seg_id}'"
                    logger.warning(msg)
                    if warnings is not None:
                        warnings.append(msg)
                    continue
                a, b = _seg_pts(seg_id, stmt_by_id)
                out.append(f"\\tkzMarkSegment{sopts}({a},{b})")

        case ir.LabelPoint(p=p, text=text, pos=pos, style=style):
            if p not in sym:
                msg = f"Skipping render op LabelPoint for undefined object '{p}'"
                logger.warning(msg)
                if warnings is not None:
                    warnings.append(msg)
                return out
            label = text if text is not None else p
            pos_str = f"[{pos}]" if pos and pos != "auto" else ""
            out.append(f"\\tkzLabelPoint{pos_str}({p}){{${label}$}}")

        case ir.LabelAngle(angle=angle, text=text, pos=pos, style=style):
            if any(pid not in sym for pid in (angle.a, angle.o, angle.b)):
                missing = [pid for pid in (angle.a, angle.o, angle.b) if pid not in sym]
                msg = f"Skipping render op LabelAngle for undefined object(s) {missing!r}"
                logger.warning(msg)
                if warnings is not None:
                    warnings.append(msg)
                return out
            opts_parts = []
            if pos is not None:
                opts_parts.append(f"pos={pos}")
            color_opts = _style_str(style, styles)
            if color_opts:
                opts_parts.append(color_opts.strip("[]"))
            sopts = f"[{','.join(opts_parts)}]" if opts_parts else ""
            a, o, b = _orient_angle(angle.a, angle.o, angle.b, sym, "interior")
            out.append(f"\\tkzLabelAngle{sopts}({a},{o},{b}){{${text}$}}")

        case ir.LabelSegment(seg=seg_id, text=text, pos=pos, style=style):
            if seg_id not in stmt_by_id:
                msg = f"Skipping render op LabelSegment for undefined object '{seg_id}'"
                logger.warning(msg)
                if warnings is not None:
                    warnings.append(msg)
                return out
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
        case ir.PolygonExterior(a=a, b=b, sides=sides):
            verts = [a, b]
            for i in range(2, sides):
                verts.append(f"{obj_id}_v{i}")
            return verts
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
        case ir.CircleThrough3(a=a):
            return f"_cc_{circle_id}", a  # circumcenter helper + first defining point
        case _:
            raise ValueError(f"Unknown circle def kind {stmt.kind!r}")


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------

_TIKZ_COLOR_NAMES = {
    "red", "blue", "green", "orange", "purple", "cyan", "magenta",
    "yellow", "black", "white", "brown", "gray", "grey",
    "darkgray", "darkgrey", "lightgray", "lightgrey", "olive", "teal", "violet",
}


def _style_str(style_key: str | None, styles: dict) -> str:
    """Return a TikZ option string like '[color=red,thick]' or '' if no style.

    If style_key is found in the styles dict, format its entries as TikZ options.
    If not found but the key is a recognized TikZ color name, return '[color=<name>]'
    so that LLM-generated style values like "red" work without a populated styles dict.
    """
    if not style_key:
        return ""
    if style_key in styles:
        opts = ",".join(
            (k if v is True else f"{k}={v}")
            for k, v in styles[style_key].items()
            if v is not False
        )
        return f"[{opts}]" if opts else ""
    if style_key in _TIKZ_COLOR_NAMES:
        return f"[color={style_key}]"
    return ""


def _merge_opts(base: str, extra_bracket: str) -> str:
    """Merge base option string with the content of an extra [opts] bracket."""
    if not extra_bracket:
        return base
    inner = extra_bracket.strip("[]")
    return f"{base},{inner}" if inner else base


# ---------------------------------------------------------------------------
# Geometric helpers
# ---------------------------------------------------------------------------

def _orient_angle(
    a: str, o: str, b: str,
    sym: SymTable,
    which: str,
) -> tuple[str, str, str]:
    """Return (a, o, b) or (b, o, a) so \\tkzMarkAngle / \\tkzLabelAngle traces the correct arc.

    \\tkzMarkAngle(A,O,B) draws counterclockwise from ray OA to ray OB.
    The 2D cross product (A-O) x (B-O) tells us which arc that is:
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


_BOUNDS_PADDING = 0.8
_TICK_HALF_LENGTH = 0.05


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


def _effective_canvas_bounds(canvas: ir.Canvas) -> tuple[float, float, float, float]:
    """Return canvas bounds, expanding to include the origin when axes are requested."""
    xmin, xmax, ymin, ymax = canvas.xmin, canvas.xmax, canvas.ymin, canvas.ymax
    if canvas.axes:
        xmin = min(xmin, 0.0)
        xmax = max(xmax, 0.0)
        ymin = min(ymin, 0.0)
        ymax = max(ymax, 0.0)
    return xmin, xmax, ymin, ymax


def _emit_grid(
    canvas: ir.Canvas,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
) -> list[str]:
    step = canvas.grid_step if canvas.grid_step > 0 else 1.0
    grid_xmin = _round_down_to_step(xmin, step)
    grid_xmax = _round_up_to_step(xmax, step)
    grid_ymin = _round_down_to_step(ymin, step)
    grid_ymax = _round_up_to_step(ymax, step)
    return [
        (
            f"\\draw[gray!35,thin,step={_fmt_num(step)}] "
            f"({_fmt_num(grid_xmin)},{_fmt_num(grid_ymin)}) grid "
            f"({_fmt_num(grid_xmax)},{_fmt_num(grid_ymax)});"
        )
    ]


def _emit_axes(
    canvas: ir.Canvas,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
) -> list[str]:
    lines: list[str] = []
    has_x_axis = ymin <= 0 <= ymax
    has_y_axis = xmin <= 0 <= xmax

    if has_x_axis:
        x_axis = f"\\draw[->,thick] ({_fmt_num(xmin)},0) -- ({_fmt_num(xmax)},0)"
        if canvas.show_axis_labels:
            x_axis += " node[right] {$x$}"
        lines.append(x_axis + ";")

    if has_y_axis:
        y_axis = f"\\draw[->,thick] (0,{_fmt_num(ymin)}) -- (0,{_fmt_num(ymax)})"
        if canvas.show_axis_labels:
            y_axis += " node[above] {$y$}"
        lines.append(y_axis + ";")

    if canvas.show_ticks or canvas.show_tick_labels:
        tick_step = canvas.tick_step if canvas.tick_step > 0 else 1.0
        if has_x_axis:
            for x in _tick_values(xmin, xmax, tick_step):
                if canvas.show_ticks:
                    lines.append(
                        f"\\draw ({_fmt_num(x)},{_fmt_num(_TICK_HALF_LENGTH)}) -- "
                        f"({_fmt_num(x)},{_fmt_num(-_TICK_HALF_LENGTH)});"
                    )
                if canvas.show_tick_labels:
                    lines.append(
                        f"\\node[below, font=\\small] at ({_fmt_num(x)},0) "
                        f"{{{_fmt_label_num(x)}}};"
                    )
        if has_y_axis:
            for y in _tick_values(ymin, ymax, tick_step):
                if canvas.show_ticks:
                    lines.append(
                        f"\\draw ({_fmt_num(_TICK_HALF_LENGTH)},{_fmt_num(y)}) -- "
                        f"({_fmt_num(-_TICK_HALF_LENGTH)},{_fmt_num(y)});"
                    )
                if canvas.show_tick_labels:
                    lines.append(
                        f"\\node[left, font=\\small] at (0,{_fmt_num(y)}) "
                        f"{{{_fmt_label_num(y)}}};"
                    )

    return lines


def _tick_values(lo: float, hi: float, step: float) -> list[float]:
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


def _round_down_to_step(value: float, step: float) -> float:
    return math.floor(value / step) * step


def _round_up_to_step(value: float, step: float) -> float:
    return math.ceil(value / step) * step


def _fmt_num(value: float) -> str:
    if abs(value) <= 1e-9:
        value = 0.0
    return f"{value:g}"


def _fmt_label_num(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) <= 1e-9:
        return str(int(rounded))
    return _fmt_num(value)


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
