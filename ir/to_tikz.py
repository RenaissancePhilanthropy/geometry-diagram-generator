from __future__ import annotations

import logging
import math
import re
from typing import Any

import sympy as sp
import sympy.geometry as spg

import ir.ir as ir
from ir.to_sympy import Arc, Sector, SymTable
from ir.render_util import (
    BOUNDS_PADDING,
    arc_params,
    circle_center_through,
    compute_bounds,
    effective_canvas_bounds,
    expand_bounds_for_geometry,
    ellipse_params,
    extract_coords,
    fmt_label_num,
    fmt_num,
    line_endpoints,
    orient_angle,
    poly_verts,
    round_down_to_step,
    round_up_to_step,
    second_line_point,
    seg_endpoints,
    synthesize_helpers,
    sympy_to_float,
    tick_values,
)

logger = logging.getLogger(__name__)

# Private aliases so internal callers keep working unchanged
_f = sympy_to_float
_fmt_num = fmt_num
_fmt_label_num = fmt_label_num
_compute_bounds = compute_bounds
_effective_canvas_bounds = effective_canvas_bounds
_expand_bounds_for_geometry = expand_bounds_for_geometry
_orient_angle = orient_angle
_second_line_point = second_line_point
_poly_verts = poly_verts
_seg_pts = seg_endpoints
_line_pts = line_endpoints
_circle_pts = circle_center_through
_tick_values = tick_values
_round_down_to_step = round_down_to_step
_round_up_to_step = round_up_to_step

_BOUNDS_PADDING = BOUNDS_PADDING
_TICK_HALF_LENGTH = 0.05


def ir_to_tikz(diagram: ir.DiagramIR, sym: SymTable, warnings: list[str] | None = None) -> str:
    """
    Compile a DiagramIR + resolved SymTable to a tkz-euclide TikZ body string.
    The returned string is intended to be placed inside a tikzpicture environment
    (the renderer wraps it automatically).
    """
    # --- Phase 1: extract float coordinates for every Point in the symbol table ---
    coords = extract_coords(sym)

    # --- Phase 2: index DefStmts by id ---
    stmt_by_id: dict[str, Any] = {stmt.id: stmt for stmt in diagram.define}

    # --- Phase 3: synthesize helper points ---
    helpers = synthesize_helpers(diagram, sym, coords)

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
        xmin, xmax, ymin, ymax = _expand_bounds_for_geometry(xmin, xmax, ymin, ymax, sym)
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
    # Sort by z-layer so fills are always behind outlines/marks, and labels always on top.
    _Z_ORDER = {
        "fill": 0,
        "draw": 1, "mark_angles": 1, "mark_right_angles": 1, "mark_segments": 1,
        "draw_points": 2,
        "label_point": 3, "label_angle": 3, "label_segment": 3, "label_free_text": 3,
    }
    sorted_ops = sorted(diagram.render, key=lambda op: _Z_ORDER.get(op.kind, 1))

    # Pre-compute group -> mark symbol for MarkSegments ops that lack an explicit style.
    _MARK_SYMBOLS = ["|", "||", "|||", "s", "s|", "s||"]
    _PARALLEL_MARKS = [">", ">>", ">>>"]
    _styles = diagram.styles or {}
    seg_groups: list[str] = []
    for op in sorted_ops:
        if isinstance(op, ir.MarkSegments) and op.group and (op.style or op.group) not in _styles:
            if op.group not in seg_groups:
                seg_groups.append(op.group)
    group_marks: dict[str, str] = {}
    equal_idx = 0
    parallel_idx = 0
    for g in seg_groups:
        if g.startswith("parallel"):
            group_marks[g] = _PARALLEL_MARKS[parallel_idx % len(_PARALLEL_MARKS)]
            parallel_idx += 1
        else:
            group_marks[g] = _MARK_SYMBOLS[equal_idx % len(_MARK_SYMBOLS)]
            equal_idx += 1

    for op in sorted_ops:
        chunk = _emit_op(op, sym, stmt_by_id, helpers, diagram.styles, group_marks, warnings=warnings)
        lines.extend(chunk)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Render op emitters
# ---------------------------------------------------------------------------

def _obj_to_tikz_path(
    obj_id: str,
    sym: SymTable,
    stmt_by_id: dict,
    helpers: dict,
) -> str | None:
    """Return a TikZ path fragment for a shape, for use in even-odd compound fills.

    Returns None for unsupported shape types (e.g. lines).
    """
    sym_obj = sym.get(obj_id)
    if sym_obj is None:
        return None
    if isinstance(sym_obj, (spg.Triangle, spg.Polygon)):
        verts = _poly_verts(obj_id, stmt_by_id)
        pts = " -- ".join(
            f"({fmt_num(_f(sym[v].x))},{fmt_num(_f(sym[v].y))})" for v in verts
        )
        return f"{pts} -- cycle"
    if isinstance(sym_obj, spg.Circle):
        cx = fmt_num(_f(sym_obj.center.x))
        cy = fmt_num(_f(sym_obj.center.y))
        r = fmt_num(_f(sym_obj.radius))
        return f"({cx},{cy}) circle[radius={r}]"
    if isinstance(sym_obj, spg.Ellipse):
        cx, cy, a, b = ellipse_params(obj_id, sym)
        return (
            f"({fmt_num(cx)},{fmt_num(cy)}) "
            f"ellipse[x radius={fmt_num(a)},y radius={fmt_num(b)}]"
        )
    if isinstance(sym_obj, Sector):
        cx, cy, r, start_deg, end_deg, sx, sy = arc_params(obj_id, sym)
        return (
            f"({fmt_num(cx)},{fmt_num(cy)}) -- "
            f"({fmt_num(sx)},{fmt_num(sy)}) "
            f"arc[start angle={fmt_num(start_deg)},"
            f"end angle={fmt_num(end_deg)},radius={fmt_num(r)}] -- cycle"
        )
    return None


def _to_latex(text: str) -> str:
    """Convert Unicode math symbols to LaTeX equivalents for use inside $...$."""
    text = re.sub(r'√([^√\s]*)', lambda m: f'\\sqrt{{{m.group(1)}}}' if m.group(1) else '\\sqrt{}', text)
    text = text.replace('°', r'^\circ')
    return text


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
            elif isinstance(sym_obj, spg.Ellipse):
                cx, cy, a, b = ellipse_params(obj_id, sym)
                style_inner = sopts[1:-1] if sopts else ""  # strip surrounding []
                style_str = f"[{style_inner}]" if style_inner else ""
                out.append(
                    f"\\draw{style_str} ({fmt_num(cx)},{fmt_num(cy)}) ellipse "
                    f"({fmt_num(a)} and {fmt_num(b)});"
                )
            elif isinstance(sym_obj, Arc):
                cx, cy, r, start_deg, end_deg, sx, sy = arc_params(obj_id, sym)
                style_inner = sopts[1:-1] if sopts else ""  # strip surrounding []
                style_str = f"[{style_inner}]" if style_inner else ""
                out.append(
                    f"\\draw{style_str} ({fmt_num(sx)},{fmt_num(sy)}) "
                    f"arc[start angle={fmt_num(start_deg)},"
                    f"end angle={fmt_num(end_deg)},radius={fmt_num(r)}];"
                )
            elif isinstance(sym_obj, Sector):
                cx, cy, r, start_deg, end_deg, sx, sy = arc_params(obj_id, sym)
                style_inner = sopts[1:-1] if sopts else ""  # strip surrounding []
                style_str = f"[{style_inner}]" if style_inner else ""
                out.append(
                    f"\\draw{style_str} "
                    f"({fmt_num(cx)},{fmt_num(cy)}) -- "
                    f"({fmt_num(sx)},{fmt_num(sy)}) "
                    f"arc[start angle={fmt_num(start_deg)},"
                    f"end angle={fmt_num(end_deg)},radius={fmt_num(r)}] -- cycle;"
                )
            else:
                out.append(f"% Draw: unhandled type {type(sym_obj).__name__} for {obj_id!r}")

        case ir.DrawPoints(points=points, style=style):
            sopts = _style_str(style, styles)
            out.append(f"\\tkzDrawPoints{sopts}({','.join(points)})")

        case ir.Fill(obj=obj_id, holes=holes, opacity=opacity, style=style):
            if obj_id not in sym:
                msg = f"Skipping render op Fill for undefined object '{obj_id}'"
                logger.warning(msg)
                if warnings is not None:
                    warnings.append(msg)
                return out
            sym_obj = sym[obj_id]
            if style and style in styles:
                fill_opts = _style_str(style, styles)
                style_inner = fill_opts[1:-1] if fill_opts else f"fill=blue!20,opacity={opacity}"
            else:
                style_inner = f"fill=blue!20,opacity={opacity}"
                fill_opts = f"[{style_inner}]"

            if holes:
                # Even-odd compound fill using raw \fill[even odd rule].
                outer_path = _obj_to_tikz_path(obj_id, sym, stmt_by_id, helpers)
                if outer_path is None:
                    msg = f"Fill with holes: unsupported outer shape type for '{obj_id}'"
                    logger.warning(msg)
                    if warnings is not None:
                        warnings.append(msg)
                    return out
                path_parts = [outer_path]
                for hole_id in holes:
                    if hole_id not in sym:
                        msg = f"Fill hole '{hole_id}' is undefined; skipping hole"
                        logger.warning(msg)
                        if warnings is not None:
                            warnings.append(msg)
                        continue
                    hole_path = _obj_to_tikz_path(hole_id, sym, stmt_by_id, helpers)
                    if hole_path is None:
                        msg = f"Fill hole '{hole_id}' has unsupported shape type; skipping"
                        logger.warning(msg)
                        if warnings is not None:
                            warnings.append(msg)
                        continue
                    path_parts.append(hole_path)
                out.append(f"\\fill[{style_inner},even odd rule] {' '.join(path_parts)};")
            elif isinstance(sym_obj, (spg.Triangle, spg.Polygon)):
                verts = _poly_verts(obj_id, stmt_by_id)
                out.append(f"\\tkzFillPolygon{fill_opts}({','.join(verts)})")
            elif isinstance(sym_obj, spg.Circle):
                center, through = _circle_pts(obj_id, stmt_by_id, helpers)
                out.append(f"\\tkzFillCircle{fill_opts}({center},{through})")
            elif isinstance(sym_obj, spg.Ellipse):
                cx, cy, a, b = ellipse_params(obj_id, sym)
                out.append(
                    f"\\fill[{style_inner}] ({fmt_num(cx)},{fmt_num(cy)}) ellipse "
                    f"({fmt_num(a)} and {fmt_num(b)});"
                )
            elif isinstance(sym_obj, Sector):
                cx, cy, r, start_deg, end_deg, sx, sy = arc_params(obj_id, sym)
                out.append(
                    f"\\fill[{style_inner}] "
                    f"({fmt_num(cx)},{fmt_num(cy)}) -- "
                    f"({fmt_num(sx)},{fmt_num(sy)}) "
                    f"arc[start angle={fmt_num(start_deg)},"
                    f"end angle={fmt_num(end_deg)},radius={fmt_num(r)}] -- cycle;"
                )

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

        case ir.LabelPoint(p=p, text=text, pos=pos, style=style, show_coords=show_coords):
            if p not in sym:
                msg = f"Skipping render op LabelPoint for undefined object '{p}'"
                logger.warning(msg)
                if warnings is not None:
                    warnings.append(msg)
                return out
            label = text if text is not None else p
            if show_coords and isinstance(sym.get(p), spg.Point):
                pt_obj = sym[p]
                _cx: Any = pt_obj.x
                _cy: Any = pt_obj.y
                label = label + _tikz_fmt_coord_pair(float(_cx.evalf()), float(_cy.evalf()))
            pos_str = f"[{pos}]" if pos and pos != "auto" else ""
            out.append(f"\\tkzLabelPoint{pos_str}({p}){{${_to_latex(label)}$}}")

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
            out.append(f"\\tkzLabelAngle{sopts}({a},{o},{b}){{${_to_latex(text)}$}}")

        case ir.LabelSegment(seg=seg_id, text=text, pos=pos, style=style):
            if seg_id not in stmt_by_id:
                msg = f"Skipping render op LabelSegment for undefined object '{seg_id}'"
                logger.warning(msg)
                if warnings is not None:
                    warnings.append(msg)
                return out
            a, b = _seg_pts(seg_id, stmt_by_id)
            sopts = f"[pos={pos}]" if pos is not None else ""
            out.append(f"\\tkzLabelSegment{sopts}({a},{b}){{${_to_latex(text)}$}}")

        case ir.LabelFreeText(text=text, at=at, centroid_of=cof):
            if at is not None:
                x, y = float(at[0]), float(at[1])
            else:
                obj = sym.get(cof)
                if obj is None:
                    msg = f"Skipping LabelFreeText: centroid_of '{cof}' not in sym"
                    logger.warning(msg)
                    if warnings is not None:
                        warnings.append(msg)
                    return out
                verts = list(obj.vertices)
                x = sum(_f(v.x) for v in verts) / len(verts)
                y = sum(_f(v.y) for v in verts) / len(verts)
            out.append(f"\\node at ({fmt_num(x)},{fmt_num(y)}) {{${text}$}};")

    return out


# ---------------------------------------------------------------------------
# Style helpers (TikZ-specific)
# ---------------------------------------------------------------------------

_TIKZ_COLOR_NAMES = {
    "red", "blue", "green", "orange", "purple", "cyan", "magenta",
    "yellow", "black", "white", "brown", "gray", "grey",
    "darkgray", "darkgrey", "lightgray", "lightgrey", "olive", "teal", "violet",
}


def _tikz_fmt_coord_val(v: float) -> str:
    """Format a coordinate value: 1 decimal place when close to .0 or .5, else 2."""
    rounded1 = round(v, 1)
    if abs(v - rounded1) < 1e-9:
        return f"{rounded1:g}"
    return f"{round(v, 2):g}"


def _tikz_fmt_coord_pair(x: float, y: float) -> str:
    """Return a '(x, y)' string with appropriate precision."""
    return f"({_tikz_fmt_coord_val(x)}, {_tikz_fmt_coord_val(y)})"


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
# Grid / axis emitters (TikZ-specific)
# ---------------------------------------------------------------------------

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
