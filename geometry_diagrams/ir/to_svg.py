"""Direct SVG renderer for DiagramIR.

Converts a compiled DiagramIR + SymTable directly to an SVG string,
bypassing TikZ/LaTeX entirely.  All geometric coordinates come from the
SymPy symbol table; no Docker container is required.

Y-axis convention
-----------------
SymPy uses a math-style coordinate system (y increases upward).
SVG uses a screen coordinate system (y increases downward).
We handle this by placing all geometry inside a ``<g transform="scale(1,-1)">``
group and then placing text elements outside that group (or applying a
counter-flip transform to each text element) so labels appear upright.
"""
from __future__ import annotations

import logging
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import sympy.geometry as spg

from . import ir
from .font import FontConfig, FONT_VARIANTS, default_font_config
from .mathtext_svg import MathGlyph, label_needs_mathtext, render_math_to_svg
from .to_sympy import Arc, Sector, SymTable
from .render_util import (
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

# SVG canvas dimensions in pixels (geometry is mapped into this space)
_SVG_SIZE = 500
_POINT_RADIUS = 2.5        # px — radius of drawn points
_TICK_LEN = 6              # px — half-length of segment tick marks
_CHEVRON_TIP = 5           # px — tip length of chevron marks
_CHEVRON_BACK = 6          # px — back-step distance for chevron wings
_CHEVRON_WING = 4          # px — wing half-width for chevron marks
_RA_SIZE = 8               # px — size of right-angle square leg
_ANGLE_ARC_R = 20          # px — radius of angle arc marks
_FONT_SIZE = 14            # px
_LABEL_OFFSET = 12         # px — label distance from geometry
_ANGLE_LABEL_R = _ANGLE_ARC_R + _LABEL_OFFSET  # px — angle label beyond arc
_TICK_PX = 5               # px — tick mark half-length
_TICK_LABEL_FONT_SIZE = 11 # px — matches the font-size used for tick labels in _append_axes


# ---------------------------------------------------------------------------
# Deferred label placement
# ---------------------------------------------------------------------------

@dataclass
class _LabelPlacement:
    x: float
    y: float
    text: str
    color: str
    anchor: str
    attrs: dict[str, str] = field(default_factory=dict)
    width_est: float = 0.0
    height_est: float = float(_FONT_SIZE)
    # When non-None, this label should be emitted as an SVG <path> (mathtext
    # vector glyph) rather than as a <text>/<tspan> element.
    math_glyph: MathGlyph | None = None


# ---------------------------------------------------------------------------
# Coordinate formatting helper
# ---------------------------------------------------------------------------

def _fmt_coord_val(v: float) -> str:
    """Format a coordinate value: 1 decimal place when close to .0 or .5, else 2."""
    rounded1 = round(v, 1)
    if abs(v - rounded1) < 1e-9:
        return f"{rounded1:g}"
    return f"{round(v, 2):g}"


def _fmt_coord_pair(x: float, y: float) -> str:
    """Return a '(x, y)' string with appropriate precision."""
    return f"({_fmt_coord_val(x)}, {_fmt_coord_val(y)})"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def ir_to_svg(
    diagram: ir.DiagramIR,
    sym: SymTable,
    warnings: list[str] | None = None,
    font_config: FontConfig | None = None,
    embed_fonts: bool = False,
) -> str:
    """Compile a DiagramIR + resolved SymTable to an SVG string."""
    if font_config is None:
        font_config = default_font_config()

    # --- Extract coordinates and helper points ---
    coords = extract_coords(sym)
    stmt_by_id: dict[str, Any] = {stmt.id: stmt for stmt in diagram.define}
    helpers = synthesize_helpers(diagram, sym, coords)

    # --- Compute viewport bounds (in geometry/SymPy space) ---
    canvas = diagram.canvas
    if canvas is not None:
        xmin, xmax, ymin, ymax = effective_canvas_bounds(canvas)
        for px, py in list(coords.values()) + list(helpers.values()):
            if px < xmin:
                xmin = px - BOUNDS_PADDING
            if px > xmax:
                xmax = px + BOUNDS_PADDING
            if py < ymin:
                ymin = py - BOUNDS_PADDING
            if py > ymax:
                ymax = py + BOUNDS_PADDING
        xmin, xmax, ymin, ymax = expand_bounds_for_geometry(xmin, xmax, ymin, ymax, sym)
    else:
        xmin, xmax, ymin, ymax = compute_bounds(coords, helpers, sym)

    geo_w = xmin if xmin == xmax else xmax - xmin
    geo_h = ymin if ymin == ymax else ymax - ymin
    if geo_w == 0:
        geo_w = 1.0
    if geo_h == 0:
        geo_h = 1.0

    # Scale: map geometry units → SVG pixels
    # Keep aspect ratio; add a small pixel margin
    _MARGIN = 20  # px
    usable = _SVG_SIZE - 2 * _MARGIN
    scale = usable / max(geo_w, geo_h)

    # Wide y-axis tick labels (e.g. multi-digit numbers on a large canvas) can
    # be wider than the default margin reserves, clipping off the left edge —
    # widen the left margin to fit the widest one actually being drawn,
    # rather than assuming a fixed margin covers every tick label.
    extra_left = 0.0
    if canvas is not None and canvas.axes and canvas.show_tick_labels and xmin <= 0 <= xmax:
        tick_step = canvas.tick_step if canvas.tick_step > 0 else 1.0
        widths = [
            max(len(fmt_label_num(y)), 1) * _TICK_LABEL_FONT_SIZE * 0.65
            for y in tick_values(ymin, ymax, tick_step)
        ]
        if widths:
            extra_left = max(widths) - _MARGIN + _TICK_PX + 3
            extra_left = max(extra_left, 0.0)

    svg_w = geo_w * scale + 2 * _MARGIN + extra_left
    svg_h = geo_h * scale + 2 * _MARGIN

    def gx(x: float) -> float:
        """Geometry x → SVG x."""
        return (x - xmin) * scale + _MARGIN + extra_left

    def gy(y: float) -> float:
        """Geometry y → SVG y (flipped: high y = low pixel row)."""
        return svg_h - ((y - ymin) * scale + _MARGIN)

    def gxy(x: float, y: float) -> tuple[float, float]:
        return gx(x), gy(y)

    def pt(pid: str) -> tuple[float, float]:
        """Look up a point by id in coords+helpers, return SVG (px, py)."""
        if pid in coords:
            return gxy(*coords[pid])
        if pid in helpers:
            return gxy(*helpers[pid])
        raise KeyError(f"Point {pid!r} not found in coords or helpers")

    # --- Build SVG root ---
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    svg = ET.Element("svg", {
        "xmlns": "http://www.w3.org/2000/svg",
        "width": fmt_num(svg_w),
        "height": fmt_num(svg_h),
        "viewBox": f"0 0 {fmt_num(svg_w)} {fmt_num(svg_h)}",
    })

    # Arrow marker definitions (referenced by stroke attrs when "->" or "<->" style is used)
    defs = ET.SubElement(svg, "defs")
    marker = ET.SubElement(defs, "marker", {
        "id": "arrowhead",
        "markerWidth": "8", "markerHeight": "6",
        "refX": "8", "refY": "3",
        "orient": "auto",
    })
    ET.SubElement(marker, "path", {
        "d": "M 0 0 L 8 3 L 0 6 Z",
        "fill": "black",
    })
    marker_start = ET.SubElement(defs, "marker", {
        "id": "arrowhead-start",
        "markerWidth": "8", "markerHeight": "6",
        "refX": "0", "refY": "3",
        "orient": "auto-start-reverse",
    })
    ET.SubElement(marker_start, "path", {
        "d": "M 0 0 L 8 3 L 0 6 Z",
        "fill": "black",
    })

    # Font @font-face declarations
    _FONT_WEIGHTS = {
        "Regular":    ("normal", "normal"),
        "Bold":       ("bold",   "normal"),
        "Italic":     ("normal", "italic"),
        "BoldItalic": ("bold",   "italic"),
    }
    font_rules = []
    for variant in FONT_VARIANTS:
        weight, style = _FONT_WEIGHTS[variant]
        src = font_config.data_uri(variant) if embed_fonts else font_config.url(variant)
        font_rules.append(
            f"@font-face {{ font-family: '{font_config.family}'; "
            f"font-weight: {weight}; font-style: {style}; "
            f"src: url('{src}'); }}"
        )
    style_el = ET.SubElement(defs, "style")
    style_el.text = "\n    " + "\n    ".join(font_rules) + "\n"

    # White background
    ET.SubElement(svg, "rect", {
        "x": "0", "y": "0",
        "width": fmt_num(svg_w), "height": fmt_num(svg_h),
        "fill": "white",
    })

    # Collect drawn line segments (SVG pixel coords) for label-vs-geometry checks.
    # Populated by the grid/axes below (if enabled) and by geometry ops during
    # the main render loop.
    drawn_segments: list[tuple[float, float, float, float]] = []
    # Axis tick label bounding boxes — fixed obstacles other labels must avoid
    # (tick labels are drawn immediately below, not through pending_labels).
    tick_label_boxes: list[tuple[float, float, float, float]] = []

    # Optional grid
    if canvas is not None and canvas.grid:
        _append_grid(svg, canvas, xmin, xmax, ymin, ymax, gxy)

    # Optional axes
    if canvas is not None and canvas.axes:
        _append_axes(svg, canvas, xmin, xmax, ymin, ymax, gxy, scale,
                     font_family=font_config.family,
                     drawn_segments=drawn_segments,
                     tick_label_boxes=tick_label_boxes)

    # --- Render ops (z-sorted) ---
    _Z_ORDER = {
        "fill": 0,
        "draw": 1, "mark_angles": 1, "mark_right_angles": 1, "mark_segments": 1,
        "draw_points": 2,
        "label_point": 3, "label_angle": 3, "label_segment": 3, "label_free_text": 3,
    }
    sorted_ops = sorted(diagram.render, key=lambda op: _Z_ORDER.get(op.kind, 1))

    # Pre-compute group → mark symbol / chevron-count for MarkSegments.
    # Equal-length groups cycle through _MARK_SYMBOLS (matching TikZ's tkz-euclide).
    # Parallel groups cycle through chevron counts.
    _MARK_SYMBOLS = ["|", "||", "|||", "s", "s|", "s||"]
    _styles = diagram.styles or {}
    seg_groups: list[str] = []
    for op in sorted_ops:
        if isinstance(op, ir.MarkSegments) and op.group and (op.style or op.group) not in _styles:
            if op.group not in seg_groups:
                seg_groups.append(op.group)
    group_mark_symbols: dict[str, str] = {}   # equal-length: symbol like "|", "s|", …
    group_chevron_counts: dict[str, int] = {}  # parallel: 1/2/3 chevrons
    equal_idx = 0
    parallel_idx = 0
    for g in seg_groups:
        if g.startswith("parallel"):
            group_chevron_counts[g] = (parallel_idx % 3) + 1
            parallel_idx += 1
        else:
            group_mark_symbols[g] = _MARK_SYMBOLS[equal_idx % len(_MARK_SYMBOLS)]
            equal_idx += 1

    # Pre-compute incident angles for smart auto label placement
    incident_angles = _build_incident_angles(diagram, sym, stmt_by_id, coords, helpers)
    angle_mark_wedges = _build_angle_mark_wedges(diagram, sym, coords, helpers)

    # Deduplicate angle marks globally to avoid duplicate paths
    _seen_ra_triples: set[tuple[str, str, str]] = set()
    _seen_angle_triples: set[tuple[str, str, str, str | None]] = set()

    # Deferred label list: labels are collected here, collision-resolved, then emitted
    pending_labels: list[_LabelPlacement] = []

    for op in sorted_ops:
        _emit_svg_op(
            op, svg, sym, stmt_by_id, coords, helpers, _styles,
            group_mark_symbols, pt, gxy, scale, xmin, xmax, ymin, ymax,
            group_chevron_counts=group_chevron_counts,
            incident_angles=incident_angles,
            angle_mark_wedges=angle_mark_wedges,
            warnings=warnings,
            pending_labels=pending_labels,
            seen_ra_triples=_seen_ra_triples,
            seen_angle_triples=_seen_angle_triples,
            drawn_segments=drawn_segments,
            font_family=font_config.family,
        )

    # Deduplicate coincident point labels (keep first occurrence at each position)
    _dedup_coincident_labels(pending_labels)

    # Nudge labels away from drawn lines/segments and fixed tick-label boxes,
    # then resolve label-label collisions, then nudge again — collision
    # resolution can push labels back into segments/tick labels, so the
    # second pass re-establishes clearance.
    _nudge_labels_from_lines(pending_labels, drawn_segments)
    _nudge_labels_from_fixed_boxes(pending_labels, tick_label_boxes)
    _resolve_label_collisions(pending_labels, svg_w, svg_h)
    _nudge_labels_from_lines(pending_labels, drawn_segments)
    _nudge_labels_from_fixed_boxes(pending_labels, tick_label_boxes)
    for lp in pending_labels:
        _append_label(
            svg, lp.x, lp.y, lp.text, lp.color,
            anchor=lp.anchor, extra_attrs=lp.attrs,
            font_family=font_config.family,
            math_glyph=lp.math_glyph,
        )

    # --- Serialise ---
    return ET.tostring(svg, encoding="unicode", xml_declaration=False)


# ---------------------------------------------------------------------------
# Per-op SVG emitters
# ---------------------------------------------------------------------------

def _emit_svg_op(
    op: Any,
    svg: ET.Element,
    sym: SymTable,
    stmt_by_id: dict,
    coords: dict,
    helpers: dict,
    styles: dict,
    group_mark_symbols: dict[str, str],
    pt,
    gxy,
    scale: float,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    group_chevron_counts: dict[str, int] = None,
    incident_angles: dict[str, list[float]] | None = None,
    angle_mark_wedges: dict[str, list[tuple[float, float]]] | None = None,
    warnings: list[str] | None = None,
    pending_labels: list[_LabelPlacement] | None = None,
    seen_ra_triples: set[tuple[str, str, str]] | None = None,
    seen_angle_triples: set[tuple[str, str, str, str | None]] | None = None,
    drawn_segments: list[tuple[float, float, float, float]] | None = None,
    font_family: str = "serif",
) -> None:
    match op:
        case ir.Draw(obj=obj_id, add=add, style=style):
            if obj_id not in sym:
                _warn(warnings, f"Skipping Draw for undefined object '{obj_id}'")
                return
            sym_obj = sym[obj_id]
            attrs = _stroke_attrs(style, styles, svg)

            if isinstance(sym_obj, (spg.Triangle, spg.Polygon)):
                verts = poly_verts(obj_id, stmt_by_id)
                pts_str = " ".join(f"{pt(v)[0]:.2f},{pt(v)[1]:.2f}" for v in verts)
                geo_type = "triangle" if len(verts) == 3 else "polygon"
                ET.SubElement(svg, "polygon", {
                    "data-ir-id": obj_id,
                    "data-type": geo_type,
                    "data-vertices": ",".join(verts),
                    "points": pts_str,
                    "fill": "none",
                    **attrs,
                })
                if drawn_segments is not None:
                    sv = [pt(v) for v in verts]
                    for i in range(len(sv)):
                        ax, ay = sv[i]
                        bx, by = sv[(i + 1) % len(sv)]
                        drawn_segments.append((ax, ay, bx, by))

            elif isinstance(sym_obj, spg.Segment):
                a, b = seg_endpoints(obj_id, stmt_by_id)
                x1, y1 = pt(a)
                x2, y2 = pt(b)
                ET.SubElement(svg, "line", {
                    "data-ir-id": obj_id,
                    "data-type": "segment",
                    "data-endpoints": f"{a},{b}",
                    "x1": f"{x1:.2f}", "y1": f"{y1:.2f}",
                    "x2": f"{x2:.2f}", "y2": f"{y2:.2f}",
                    **attrs,
                })
                if drawn_segments is not None:
                    drawn_segments.append((x1, y1, x2, y2))

            elif isinstance(sym_obj, spg.Line):
                p1_id, p2_id = line_endpoints(obj_id, stmt_by_id, helpers)
                x1, y1 = _geo_coord(p1_id, coords, helpers)
                x2, y2 = _geo_coord(p2_id, coords, helpers)
                sx1, sy1, sx2, sy2 = _clip_line_to_bounds(
                    x1, y1, x2, y2, xmin, xmax, ymin, ymax
                )
                if sx1 is not None:
                    px1, py1 = gxy(sx1, sy1)
                    px2, py2 = gxy(sx2, sy2)
                    ET.SubElement(svg, "line", {
                        "data-ir-id": obj_id,
                        "data-type": "line",
                        "data-endpoints": f"{p1_id},{p2_id}",
                        "x1": f"{px1:.2f}", "y1": f"{py1:.2f}",
                        "x2": f"{px2:.2f}", "y2": f"{py2:.2f}",
                        **attrs,
                    })
                    if drawn_segments is not None:
                        drawn_segments.append((px1, py1, px2, py2))

            elif isinstance(sym_obj, spg.Ray):
                stmt = stmt_by_id[obj_id]
                ax, ay = _geo_coord(stmt.a, coords, helpers)
                bx, by = _geo_coord(stmt.b, coords, helpers)
                # Extend ray to canvas edge
                sx1, sy1, sx2, sy2 = _clip_ray_to_bounds(
                    ax, ay, bx, by, xmin, xmax, ymin, ymax
                )
                if sx1 is not None:
                    px1, py1 = gxy(sx1, sy1)
                    px2, py2 = gxy(sx2, sy2)
                    ET.SubElement(svg, "line", {
                        "data-ir-id": obj_id,
                        "data-type": "ray",
                        "data-endpoints": f"{stmt.a},{stmt.b}",
                        "x1": f"{px1:.2f}", "y1": f"{py1:.2f}",
                        "x2": f"{px2:.2f}", "y2": f"{py2:.2f}",
                        **attrs,
                    })
                    if drawn_segments is not None:
                        drawn_segments.append((px1, py1, px2, py2))

            elif isinstance(sym_obj, spg.Circle):
                cx_g = sympy_to_float(sym_obj.center.x)
                cy_g = sympy_to_float(sym_obj.center.y)
                r_g = sympy_to_float(sym_obj.radius)
                cx_s, cy_s = gxy(cx_g, cy_g)
                r_s = r_g * scale
                # Recover center point id from the DefStmt
                center_id = _circle_center_id(obj_id, stmt_by_id)
                ET.SubElement(svg, "circle", {
                    "data-ir-id": obj_id,
                    "data-type": "circle",
                    **({"data-center": center_id} if center_id else {}),
                    "cx": f"{cx_s:.2f}", "cy": f"{cy_s:.2f}", "r": f"{r_s:.2f}",
                    "fill": "none",
                    **attrs,
                })

            elif isinstance(sym_obj, spg.Ellipse):
                cx_g, cy_g, a_g, b_g = ellipse_params(obj_id, sym)
                cx_s, cy_s = gxy(cx_g, cy_g)
                rx_s = a_g * scale
                ry_s = b_g * scale
                ET.SubElement(svg, "ellipse", {
                    "data-ir-id": obj_id,
                    "data-type": "ellipse",
                    "cx": f"{cx_s:.2f}", "cy": f"{cy_s:.2f}",
                    "rx": f"{rx_s:.2f}", "ry": f"{ry_s:.2f}",
                    "fill": "none",
                    **attrs,
                })

            elif isinstance(sym_obj, Arc):
                cx_g, cy_g, r_g, start_deg, end_deg, sx_g, sy_g = arc_params(obj_id, sym)
                r_s = r_g * scale
                # Compute arc endpoint on the circle in geometry space, then map
                # to pixel space.  The SymPy-space sweep is CCW from start_deg
                # to end_deg.
                end_rad = math.radians(end_deg)
                ex_g = cx_g + r_g * math.cos(end_rad)
                ey_g = cy_g + r_g * math.sin(end_rad)
                sx_s, sy_s = gxy(sx_g, sy_g)
                ex_s, ey_s = gxy(ex_g, ey_g)
                sweep_deg = end_deg - start_deg  # always > 0 per arc_params
                large_arc = 1 if sweep_deg > 180.0 else 0
                # math-CCW = visually-CCW in SVG = sweep_flag=0
                sweep_flag = 0
                d = (
                    f"M {sx_s:.2f} {sy_s:.2f} "
                    f"A {r_s:.2f} {r_s:.2f} 0 {large_arc} {sweep_flag} "
                    f"{ex_s:.2f} {ey_s:.2f}"
                )
                ET.SubElement(svg, "path", {
                    "data-ir-id": obj_id,
                    "data-type": "arc",
                    "d": d,
                    "fill": "none",
                    **attrs,
                })

            elif isinstance(sym_obj, Sector):
                cx_g, cy_g, r_g, start_deg, end_deg, sx_g, sy_g = arc_params(obj_id, sym)
                r_s = r_g * scale
                end_rad = math.radians(end_deg)
                ex_g = cx_g + r_g * math.cos(end_rad)
                ey_g = cy_g + r_g * math.sin(end_rad)
                cx_s, cy_s = gxy(cx_g, cy_g)
                sx_s, sy_s = gxy(sx_g, sy_g)
                ex_s, ey_s = gxy(ex_g, ey_g)
                sweep_deg = end_deg - start_deg
                large_arc = 1 if sweep_deg > 180.0 else 0
                d = (
                    f"M {cx_s:.2f} {cy_s:.2f} "
                    f"L {sx_s:.2f} {sy_s:.2f} "
                    f"A {r_s:.2f} {r_s:.2f} 0 {large_arc} 0 {ex_s:.2f} {ey_s:.2f} "
                    f"L {cx_s:.2f} {cy_s:.2f}"
                )
                ET.SubElement(svg, "path", {
                    "data-ir-id": obj_id,
                    "data-type": "sector",
                    "d": d,
                    "fill": "none",
                    **attrs,
                })

        case ir.DrawPoints(points=points, style=style):
            fill = _color_from_style(style, styles) or "black"
            for pid in points:
                if pid not in coords and pid not in helpers:
                    _warn(warnings, f"Skipping DrawPoints for undefined point '{pid}'")
                    continue
                px, py = pt(pid)
                ET.SubElement(svg, "circle", {
                    "data-ir-id": pid,
                    "data-type": "point",
                    "cx": f"{px:.2f}", "cy": f"{py:.2f}",
                    "r": str(_POINT_RADIUS),
                    "fill": fill,
                })

        case ir.Fill(obj=obj_id, holes=holes, opacity=opacity, style=style):
            if obj_id not in sym:
                _warn(warnings, f"Skipping Fill for undefined object '{obj_id}'")
                return
            sym_obj = sym[obj_id]
            fill_color, fill_opacity = _fill_attrs(style, styles, opacity)

            if holes:
                # Even-odd compound fill: outer shape minus hole shapes.
                outer_path = _obj_to_svg_subpath(
                    obj_id, sym, stmt_by_id, gxy, scale, poly_verts, ellipse_params
                )
                if outer_path is None:
                    _warn(warnings, f"Fill with holes: unsupported outer shape type for '{obj_id}'")
                    return
                subpaths = [outer_path]
                for hole_id in holes:
                    if hole_id not in sym:
                        _warn(warnings, f"Fill hole '{hole_id}' is undefined; skipping hole")
                        continue
                    hole_path = _obj_to_svg_subpath(
                        hole_id, sym, stmt_by_id, gxy, scale, poly_verts, ellipse_params
                    )
                    if hole_path is None:
                        _warn(warnings, f"Fill hole '{hole_id}' has unsupported shape type; skipping hole")
                        continue
                    subpaths.append(hole_path)
                ET.SubElement(svg, "path", {
                    "data-ir-id": obj_id,
                    "data-role": "fill",
                    "d": " ".join(subpaths),
                    "fill": fill_color,
                    "fill-opacity": str(fill_opacity),
                    "fill-rule": "evenodd",
                    "stroke": "none",
                })

            elif isinstance(sym_obj, (spg.Triangle, spg.Polygon)):
                verts = poly_verts(obj_id, stmt_by_id)
                pts_str = " ".join(f"{pt(v)[0]:.2f},{pt(v)[1]:.2f}" for v in verts)
                ET.SubElement(svg, "polygon", {
                    "data-ir-id": obj_id,
                    "data-role": "fill",
                    "points": pts_str,
                    "fill": fill_color,
                    "fill-opacity": str(fill_opacity),
                    "stroke": "none",
                })

            elif isinstance(sym_obj, spg.Circle):
                cx_g = sympy_to_float(sym_obj.center.x)
                cy_g = sympy_to_float(sym_obj.center.y)
                r_g = sympy_to_float(sym_obj.radius)
                cx_s, cy_s = gxy(cx_g, cy_g)
                r_s = r_g * scale
                ET.SubElement(svg, "circle", {
                    "data-ir-id": obj_id,
                    "data-role": "fill",
                    "cx": f"{cx_s:.2f}", "cy": f"{cy_s:.2f}", "r": f"{r_s:.2f}",
                    "fill": fill_color,
                    "fill-opacity": str(fill_opacity),
                    "stroke": "none",
                })

            elif isinstance(sym_obj, spg.Ellipse):
                cx_g, cy_g, a_g, b_g = ellipse_params(obj_id, sym)
                cx_s, cy_s = gxy(cx_g, cy_g)
                rx_s = a_g * scale
                ry_s = b_g * scale
                ET.SubElement(svg, "ellipse", {
                    "data-ir-id": obj_id,
                    "data-role": "fill",
                    "cx": f"{cx_s:.2f}", "cy": f"{cy_s:.2f}",
                    "rx": f"{rx_s:.2f}", "ry": f"{ry_s:.2f}",
                    "fill": fill_color,
                    "fill-opacity": str(fill_opacity),
                    "stroke": "none",
                })

            elif isinstance(sym_obj, Sector):
                cx_g, cy_g, r_g, start_deg, end_deg, sx_g, sy_g = arc_params(obj_id, sym)
                r_s = r_g * scale
                end_rad = math.radians(end_deg)
                ex_g = cx_g + r_g * math.cos(end_rad)
                ey_g = cy_g + r_g * math.sin(end_rad)
                cx_s, cy_s = gxy(cx_g, cy_g)
                sx_s, sy_s = gxy(sx_g, sy_g)
                ex_s, ey_s = gxy(ex_g, ey_g)
                sweep_deg = end_deg - start_deg
                large_arc = 1 if sweep_deg > 180.0 else 0
                d = (
                    f"M {cx_s:.2f} {cy_s:.2f} "
                    f"L {sx_s:.2f} {sy_s:.2f} "
                    f"A {r_s:.2f} {r_s:.2f} 0 {large_arc} 0 {ex_s:.2f} {ey_s:.2f} Z"
                )
                ET.SubElement(svg, "path", {
                    "data-ir-id": obj_id,
                    "data-role": "fill",
                    "d": d,
                    "fill": fill_color,
                    "fill-opacity": str(fill_opacity),
                    "stroke": "none",
                })

        case ir.MarkRightAngles(angles=angles, style=style):
            stroke = _color_from_style(style, styles) or "black"
            for angle in angles:
                missing = [pid for pid in (angle.a, angle.o, angle.b) if pid not in sym]
                if missing:
                    _warn(warnings, f"Skipping MarkRightAngles for undefined {missing!r}")
                    continue
                # Deduplicate: canonical key ignores a/b order
                ra_key = (min(angle.a, angle.b), angle.o, max(angle.a, angle.b))
                if seen_ra_triples is not None:
                    if ra_key in seen_ra_triples:
                        continue
                    seen_ra_triples.add(ra_key)
                _append_right_angle_mark(
                    svg, angle.a, angle.o, angle.b, pt, stroke,
                    extra_attrs={
                        "data-role": "mark-right-angle",
                        "data-angle": f"{angle.a},{angle.o},{angle.b}",
                    },
                )

        case ir.MarkAngles(angles=angles, group=group, which=which, style=style):
            stroke = _color_from_style(style or group, styles)
            if stroke is None:
                _COLOR_CYCLE = ["black", "blue", "red", "teal", "purple", "orange"]
                try:
                    idx = (int(str(group)) - 1) % len(_COLOR_CYCLE) if group else 0
                    stroke = _COLOR_CYCLE[idx]
                except (ValueError, TypeError):
                    stroke = "black"
            n_arcs = 1
            if group:
                try:
                    n_arcs = min(int(str(group)), 3)
                except (ValueError, TypeError):
                    pass
            for angle in angles:
                missing = [pid for pid in (angle.a, angle.o, angle.b) if pid not in sym]
                if missing:
                    _warn(warnings, f"Skipping MarkAngles for undefined {missing!r}")
                    continue
                # Deduplicate: canonical key ignores a/b order within a group
                angle_key = (min(angle.a, angle.b), angle.o, max(angle.a, angle.b), group)
                if seen_angle_triples is not None:
                    if angle_key in seen_angle_triples:
                        continue
                    seen_angle_triples.add(angle_key)
                a, o, b = orient_angle(angle.a, angle.o, angle.b, sym, which)
                arc_attrs: dict[str, str] = {
                    "data-role": "mark-angle",
                    "data-angle": f"{angle.a},{angle.o},{angle.b}",
                }
                if group:
                    arc_attrs["data-group"] = str(group)
                _append_angle_arc(svg, a, o, b, pt, stroke, n_arcs, extra_attrs=arc_attrs)

        case ir.MarkSegments(segs=segs, group=group, style=style):
            stroke = _color_from_style(style or group, styles) or "black"
            for seg_id in segs:
                if seg_id not in stmt_by_id:
                    _warn(warnings, f"Skipping MarkSegments for undefined '{seg_id}'")
                    continue
                a, b = seg_endpoints(seg_id, stmt_by_id)
                mark_attrs: dict[str, str] = {
                    "data-role": "mark-segment",
                    "data-segment": seg_id,
                }
                if group:
                    mark_attrs["data-group"] = str(group)
                if group and group.startswith("parallel"):
                    # Parallel segments: use chevron marks (incrementing count per group)
                    n_chevrons = group_chevron_counts.get(group, 1)
                    _append_seg_chevrons(svg, a, b, pt, stroke, n_chevrons, extra_attrs=mark_attrs)
                else:
                    # Equal-length segments: dispatch on mark symbol
                    mark_sym = group_mark_symbols.get(group, "|") if group else "|"
                    n_slashes = mark_sym.count("s")
                    n_ticks = mark_sym.count("|")
                    if n_slashes:
                        _append_seg_slash(svg, a, b, pt, stroke, extra_attrs=mark_attrs)
                    if n_ticks:
                        _append_seg_ticks(svg, a, b, pt, stroke, n_ticks, extra_attrs=mark_attrs)

        case ir.LabelPoint(p=p, text=text, pos=pos, style=style, show_coords=show_coords):
            if p not in sym:
                _warn(warnings, f"Skipping LabelPoint for undefined '{p}'")
                return
            label = text if text is not None else p
            if show_coords and p in coords:
                gx_val, gy_val = coords[p]
                label = label + _fmt_coord_pair(gx_val, gy_val)
            px, py = pt(p)
            if not pos or pos == "auto":
                angles = (incident_angles or {}).get(p, [])
                wedges = (angle_mark_wedges or {}).get(p, [])
                direction = _auto_label_direction(angles, wedges)
                ox, oy = _angle_to_offset(direction, _LABEL_OFFSET)
                anchor = _angle_to_anchor(direction)
            else:
                ox, oy = _label_offset(pos, _LABEL_OFFSET)
                anchor = _pos_to_anchor(pos)
            color = _color_from_style(style, styles) or "black"
            lp = _make_label_placement(
                x=px + ox, y=py + oy, text=label, color=color, anchor=anchor,
                attrs={"data-role": "label-point", "data-for": p},
            )
            if pending_labels is not None:
                pending_labels.append(lp)
            else:
                _append_label(svg, lp.x, lp.y, lp.text, lp.color, anchor=lp.anchor, extra_attrs=lp.attrs,
                      font_family=font_family, math_glyph=lp.math_glyph)

        case ir.LabelAngle(angle=angle, text=text, pos=pos, style=style):
            missing = [pid for pid in (angle.a, angle.o, angle.b) if pid not in sym]
            if missing:
                _warn(warnings, f"Skipping LabelAngle for undefined {missing!r}")
                return
            a_id, o_id, b_id = orient_angle(angle.a, angle.o, angle.b, sym, "interior")
            ox_g, oy_g = coords.get(o_id, helpers.get(o_id, (0, 0)))
            ax_g, ay_g = coords.get(a_id, helpers.get(a_id, (0, 0)))
            bx_g, by_g = coords.get(b_id, helpers.get(b_id, (0, 0)))
            # Place label along bisector direction, beyond the arc marker
            da = math.atan2(ay_g - oy_g, ax_g - ox_g)
            db = math.atan2(by_g - oy_g, bx_g - ox_g)
            bisector = _bisector_angle(da, db)
            lx, ly = gxy(ox_g, oy_g)
            lx += math.cos(bisector) * _ANGLE_LABEL_R
            # In SVG space y is flipped, so negate sin component
            ly -= math.sin(bisector) * _ANGLE_LABEL_R
            label_text = text or ""
            color = _color_from_style(style, styles) or "black"
            lp = _make_label_placement(
                x=lx, y=ly, text=label_text, color=color, anchor="middle",
                attrs={"data-role": "label-angle", "data-for": f"{angle.a},{angle.o},{angle.b}"},
            )
            if pending_labels is not None:
                pending_labels.append(lp)
            else:
                _append_label(svg, lp.x, lp.y, lp.text, lp.color, anchor=lp.anchor, extra_attrs=lp.attrs,
                      font_family=font_family, math_glyph=lp.math_glyph)

        case ir.LabelSegment(seg=seg_id, text=text, pos=pos, style=style):
            if seg_id not in stmt_by_id:
                _warn(warnings, f"Skipping LabelSegment for undefined '{seg_id}'")
                return
            a, b = seg_endpoints(seg_id, stmt_by_id)
            ax, ay = pt(a)
            bx, by = pt(b)
            # Midpoint, offset perpendicular
            mx, my = (ax + bx) / 2, (ay + by) / 2
            dx, dy = bx - ax, by - ay
            mag = math.hypot(dx, dy) or 1
            # Perpendicular (rotated 90° CCW in screen coords)
            nx, ny = -dy / mag, dx / mag
            # Choose the side with fewer surrounding points
            other_pts = [
                pt(pid)
                for pid in list(coords.keys()) + list(helpers.keys())
                if pid not in (a, b)
            ]
            side = _segment_label_side(mx, my, nx, ny, other_pts)
            label_text = text or ""
            lx = mx + nx * _LABEL_OFFSET * side
            ly = my + ny * _LABEL_OFFSET * side
            color = _color_from_style(style, styles) or "black"
            lp = _make_label_placement(
                x=lx, y=ly, text=label_text, color=color, anchor="middle",
                attrs={"data-role": "label-segment", "data-for": seg_id},
            )
            if pending_labels is not None:
                pending_labels.append(lp)
            else:
                _append_label(svg, lp.x, lp.y, lp.text, lp.color, anchor=lp.anchor, extra_attrs=lp.attrs,
                      font_family=font_family, math_glyph=lp.math_glyph)

        case ir.LabelFreeText(text=text, at=at, centroid_of=cof, style=style):
            if at is not None:
                lx, ly = gxy(float(at[0]), float(at[1]))
            else:
                obj = sym.get(cof)
                if obj is None:
                    _warn(warnings, f"Skipping LabelFreeText: centroid_of '{cof}' not in sym")
                    return
                verts = list(obj.vertices)
                cx = sum(float(v.x) for v in verts) / len(verts)
                cy = sum(float(v.y) for v in verts) / len(verts)
                lx, ly = gxy(cx, cy)
            label_text = text or ""
            color = _color_from_style(style, styles) or "black"
            lp = _make_label_placement(
                x=lx, y=ly, text=label_text, color=color, anchor="middle",
                attrs={"data-role": "label-free-text"},
            )
            if pending_labels is not None:
                pending_labels.append(lp)
            else:
                _append_label(svg, lp.x, lp.y, lp.text, lp.color, anchor=lp.anchor, extra_attrs=lp.attrs,
                      font_family=font_family, math_glyph=lp.math_glyph)


# ---------------------------------------------------------------------------
# Mark helpers
# ---------------------------------------------------------------------------

def _append_right_angle_mark(
    svg: ET.Element,
    a_id: str,
    o_id: str,
    b_id: str,
    pt,
    stroke: str,
    extra_attrs: dict[str, str] | None = None,
) -> None:
    """Draw a small square at vertex o between rays oa and ob."""
    ox, oy = pt(o_id)
    ax, ay = pt(a_id)
    bx, by = pt(b_id)

    def unit(dx: float, dy: float) -> tuple[float, float]:
        m = math.hypot(dx, dy) or 1
        return dx / m, dy / m

    ux, uy = unit(ax - ox, ay - oy)
    vx, vy = unit(bx - ox, by - oy)
    s = _RA_SIZE
    # Four corners of the square
    p1 = (ox + ux * s, oy + uy * s)
    p2 = (ox + ux * s + vx * s, oy + uy * s + vy * s)
    p3 = (ox + vx * s, oy + vy * s)
    d = (
        f"M {p1[0]:.2f} {p1[1]:.2f} "
        f"L {p2[0]:.2f} {p2[1]:.2f} "
        f"L {p3[0]:.2f} {p3[1]:.2f}"
    )
    ET.SubElement(svg, "path", {
        **(extra_attrs or {}),
        "d": d,
        "stroke": stroke,
        "stroke-width": "1.5",
        "fill": "none",
    })


def _append_angle_arc(
    svg: ET.Element,
    a_id: str,
    o_id: str,
    b_id: str,
    pt,
    stroke: str,
    n_arcs: int,
    extra_attrs: dict[str, str] | None = None,
) -> None:
    """Draw n_arcs concentric arcs at vertex o from ray oa to ray ob.

    orient_angle() has already ensured that the CCW sweep from a→b in SymPy
    (y-up) math coords traces the requested arc (interior/exterior).  In SVG
    pixel coords (y-down) that same CCW sweep becomes CW, so:
      - angles computed from pixel coords are negated relative to math angles
      - diff_svg = 2π − diff_math, flipping large/small
      - the correct draw direction is sweep=0 (CCW in SVG = CW visually = CCW in math)
      - large_arc must be flipped: 0 when diff_svg > π (i.e. the complement ≤ π)
    """
    ox, oy = pt(o_id)
    ax, ay = pt(a_id)
    bx, by = pt(b_id)

    # Angles in SVG pixel space (y-down), so negated vs. math space
    angle_a = math.atan2(ay - oy, ax - ox)
    angle_b = math.atan2(by - oy, bx - ox)

    # diff_svg = 2π − diff_math, so large when the math interior arc is small
    diff = (angle_b - angle_a) % (2 * math.pi)
    # We want large_arc=0 when the intended arc ≤ 180° (diff_svg > π → complement ≤ π)
    large_arc = 0 if diff > math.pi else 1

    for i in range(n_arcs):
        r = _ANGLE_ARC_R + i * 5
        sx = ox + r * math.cos(angle_a)
        sy = oy + r * math.sin(angle_a)
        ex = ox + r * math.cos(angle_b)
        ey = oy + r * math.sin(angle_b)
        # sweep=0 (CCW in SVG pixel space) corresponds to CCW in math space = interior
        d = f"M {sx:.2f} {sy:.2f} A {r:.2f} {r:.2f} 0 {large_arc} 0 {ex:.2f} {ey:.2f}"
        ET.SubElement(svg, "path", {
            **(extra_attrs or {}),
            "d": d,
            "stroke": stroke,
            "stroke-width": "1.5",
            "fill": "none",
        })


def _append_seg_slash(
    svg: ET.Element,
    a_id: str,
    b_id: str,
    pt,
    stroke: str,
    extra_attrs: dict[str, str] | None = None,
) -> None:
    """Draw a diagonal slash mark at the midpoint of segment AB.

    The slash is a short line drawn at 45° from the segment direction — visually
    distinct from the perpendicular tick mark.  This corresponds to the ``s``
    mark symbol in tkz-euclide's set ``["|", "||", "|||", "s", "s|", "s||"]``.
    """
    ax, ay = pt(a_id)
    bx, by = pt(b_id)
    mx, my = (ax + bx) / 2, (ay + by) / 2
    dx, dy = bx - ax, by - ay
    mag = math.hypot(dx, dy) or 1
    # Unit vector along the segment
    along_x, along_y = dx / mag, dy / mag
    # Perpendicular unit vector
    perp_x, perp_y = -dy / mag, dx / mag
    # Slash direction: bisect between along and perp (45° from segment)
    slash_x = (along_x + perp_x) / math.sqrt(2)
    slash_y = (along_y + perp_y) / math.sqrt(2)
    # Half-length of slash line
    half = _TICK_LEN
    ET.SubElement(svg, "line", {
        **(extra_attrs or {}),
        "x1": f"{mx - slash_x * half:.2f}",
        "y1": f"{my - slash_y * half:.2f}",
        "x2": f"{mx + slash_x * half:.2f}",
        "y2": f"{my + slash_y * half:.2f}",
        "stroke": stroke,
        "stroke-width": "1.5",
    })


def _append_seg_ticks(
    svg: ET.Element,
    a_id: str,
    b_id: str,
    pt,
    stroke: str,
    n_ticks: int,
    extra_attrs: dict[str, str] | None = None,
) -> None:
    """Draw n_ticks perpendicular tick marks at the midpoint of segment AB."""
    ax, ay = pt(a_id)
    bx, by = pt(b_id)
    mx, my = (ax + bx) / 2, (ay + by) / 2
    dx, dy = bx - ax, by - ay
    mag = math.hypot(dx, dy) or 1
    # Perpendicular direction
    nx, ny = -dy / mag, dx / mag
    # Tick spacing along the segment direction
    spacing = 4  # px between multiple ticks
    along_x, along_y = dx / mag, dy / mag

    for i in range(n_ticks):
        offset = (i - (n_ticks - 1) / 2) * spacing
        tx = mx + along_x * offset
        ty = my + along_y * offset
        ET.SubElement(svg, "line", {
            **(extra_attrs or {}),
            "x1": f"{tx - nx * _TICK_LEN:.2f}",
            "y1": f"{ty - ny * _TICK_LEN:.2f}",
            "x2": f"{tx + nx * _TICK_LEN:.2f}",
            "y2": f"{ty + ny * _TICK_LEN:.2f}",
            "stroke": stroke,
            "stroke-width": "1.5",
        })


def _append_seg_chevrons(
    svg: ET.Element,
    a_id: str,
    b_id: str,
    pt,
    stroke: str,
    n_chevrons: int,
    extra_attrs: dict[str, str] | None = None,
) -> None:
    """Draw n_chevrons directional chevron marks at the midpoint of segment AB."""
    ax, ay = pt(a_id)
    bx, by = pt(b_id)
    mx, my = (ax + bx) / 2, (ay + by) / 2
    dx, dy = bx - ax, by - ay
    mag = math.hypot(dx, dy) or 1
    # Direction (A→B) and perpendicular
    along_x, along_y = dx / mag, dy / mag
    perp_x, perp_y = -dy / mag, dx / mag
    spacing = 4  # px between multiple chevrons

    for i in range(n_chevrons):
        offset = (i - (n_chevrons - 1) / 2) * spacing
        cx = mx + along_x * offset
        cy = my + along_y * offset
        # Tip point ahead in the segment direction
        tip_x = cx + along_x * _CHEVRON_TIP
        tip_y = cy + along_y * _CHEVRON_TIP
        # Wing base points: back from tip, offset perpendicular
        wing1_x = tip_x - along_x * _CHEVRON_BACK + perp_x * _CHEVRON_WING
        wing1_y = tip_y - along_y * _CHEVRON_BACK + perp_y * _CHEVRON_WING
        wing2_x = tip_x - along_x * _CHEVRON_BACK - perp_x * _CHEVRON_WING
        wing2_y = tip_y - along_y * _CHEVRON_BACK - perp_y * _CHEVRON_WING
        # Two arms of the chevron
        for wx, wy in [(wing1_x, wing1_y), (wing2_x, wing2_y)]:
            ET.SubElement(svg, "line", {
                **(extra_attrs or {}),
                "x1": f"{wx:.2f}",
                "y1": f"{wy:.2f}",
                "x2": f"{tip_x:.2f}",
                "y2": f"{tip_y:.2f}",
                "stroke": stroke,
                "stroke-width": "1.5",
            })


# ---------------------------------------------------------------------------
# Label helpers
# ---------------------------------------------------------------------------

def _append_label(
    svg: ET.Element,
    x: float,
    y: float,
    text: str,
    color: str,
    anchor: str = "middle",
    extra_attrs: dict[str, str] | None = None,
    font_family: str = "serif",
    math_glyph: MathGlyph | None = None,
) -> None:
    """Append a label element to *svg*.

    If *math_glyph* is provided (a pre-rendered mathtext path), emit a ``<g>``
    containing a ``<path>`` using the glyph's ``d`` string, positioned so that
    the label is horizontally anchored per *anchor* and vertically centred on *y*.
    Otherwise, fall back to a ``<text>`` element with tspan LaTeX substitutions.
    """
    if math_glyph is not None:
        _append_math_label(svg, x, y, color, anchor, extra_attrs or {}, math_glyph)
    else:
        el = ET.SubElement(svg, "text", {
            **(extra_attrs or {}),
            "x": f"{x:.2f}",
            "y": f"{y:.2f}",
            "font-family": font_family,
            "font-size": str(_FONT_SIZE),
            "fill": color,
            "text-anchor": anchor,
            "dominant-baseline": "central",
        })
        _build_tspans(el, text)


def _append_math_label(
    svg: ET.Element,
    x: float,
    y: float,
    color: str,
    anchor: str,
    extra_attrs: dict[str, str],
    glyph: MathGlyph,
) -> None:
    """Emit a mathtext glyph as a ``<g><path /></g>`` at the requested position.

    The path's local coordinate system has its origin at the left edge of the
    glyph bounding box, at the SVG pixel row corresponding to the top of the
    bounding box.  We apply a ``translate`` transform to position it correctly:

    * Horizontally: honour *anchor* (start/middle/end) relative to *x*.
    * Vertically: centre the glyph on *y* (matching ``dominant-baseline:central``
      used by the ``<text>`` path).
    """
    # Horizontal offset based on anchor
    if anchor == "middle":
        tx = x - glyph.x_min - glyph.width / 2
    elif anchor == "end":
        tx = x - glyph.x_min - glyph.width
    else:  # "start"
        tx = x - glyph.x_min

    # Vertical: centre glyph height on y
    ty = y - glyph.y_min - glyph.height / 2

    g = ET.SubElement(svg, "g", {
        **extra_attrs,
        "transform": f"translate({tx:.3f},{ty:.3f})",
    })
    ET.SubElement(g, "path", {
        "d": glyph.d,
        "fill": color,
    })


def _build_tspans(parent: ET.Element, text: str) -> None:
    """Parse LaTeX math markup and populate parent with text/tspan children."""
    # Strip outer $...$ delimiters
    stripped = text.strip()
    if stripped.startswith("$") and stripped.endswith("$") and len(stripped) > 1:
        stripped = stripped[1:-1]

    # Apply command substitutions (Greek letters, symbols)
    segments = _parse_latex(stripped)
    for seg in segments:
        kind = seg["kind"]
        content = seg["content"]
        if kind == "text":
            _append_text_run(parent, content)
        elif kind == "sub":
            _append_tspan(parent, content, baseline_shift="sub", font_size="70%")
        elif kind == "sup":
            _append_tspan(parent, content, baseline_shift="super", font_size="70%")
        elif kind == "overline":
            _append_tspan(parent, content, text_decoration="overline")
        elif kind == "bold":
            _append_tspan(parent, content, font_weight="bold")
        elif kind == "italic":
            _append_tspan(parent, content, font_style="italic")


def _append_text_run(parent: ET.Element, text: str) -> None:
    """Append characters from a plain-text run, italicising lone letters."""
    # Split into italic (single letter) and upright (everything else) runs
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isalpha() and (i == 0 or not text[i - 1].isalpha()) and (i + 1 >= len(text) or not text[i + 1].isalpha()):
            # Single isolated letter → italic
            span = ET.SubElement(parent, "tspan", {"font-style": "italic"})
            span.text = ch
        else:
            # Append to parent directly
            if len(parent) == 0:
                parent.text = (parent.text or "") + ch
            else:
                last = parent[-1]
                last.tail = (last.tail or "") + ch
        i += 1


def _append_tspan(
    parent: ET.Element,
    content: str,
    baseline_shift: str | None = None,
    font_size: str | None = None,
    text_decoration: str | None = None,
    font_weight: str | None = None,
    font_style: str | None = None,
) -> None:
    attrs: dict[str, str] = {}
    if baseline_shift:
        attrs["baseline-shift"] = baseline_shift
    if font_size:
        attrs["font-size"] = font_size
    if text_decoration:
        attrs["text-decoration"] = text_decoration
    if font_weight:
        attrs["font-weight"] = font_weight
    if font_style:
        attrs["font-style"] = font_style
    span = ET.SubElement(parent, "tspan", attrs)
    span.text = content


# ---------------------------------------------------------------------------
# LaTeX parser
# ---------------------------------------------------------------------------

# Greek letters and common symbols → Unicode
_LATEX_UNICODE: dict[str, str] = {
    # Lowercase Greek
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ",
    "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ", "eta": "η",
    "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
    "pi": "π", "varpi": "ϖ", "rho": "ρ", "varrho": "ϱ",
    "sigma": "σ", "varsigma": "ς", "tau": "τ", "upsilon": "υ",
    "phi": "φ", "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    # Uppercase Greek
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ",
    "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ",
    "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    # Geometry symbols
    "triangle": "△", "angle": "∠", "perp": "⊥", "parallel": "∥",
    "sim": "∼", "cong": "≅",
    # Math symbols
    "degree": "°", "circ": "°", "infty": "∞", "cdot": "·", "times": "×",
    "leq": "≤", "geq": "≥", "neq": "≠", "approx": "≈",
    "pm": "±", "sqrt": "√",
    # Arrows
    "rightarrow": "→", "to": "→", "Rightarrow": "⇒",
    "leftarrow": "←", "Leftarrow": "⇐",
    "leftrightarrow": "↔", "Leftrightarrow": "⟺",
    "longrightarrow": "⟶", "longleftarrow": "⟵",
    # Formatting that becomes invisible/plain
    "left": "", "right": "", ",": " ", ";": " ", "!": "",
    "text": "",  # \text{...} handled below
}


def _parse_latex(s: str) -> list[dict]:
    """Parse a LaTeX string (without outer $) into a list of segments.

    Each segment is a dict with keys:
      - ``kind``: "text" | "sub" | "sup" | "overline"
      - ``content``: the (already-converted) string content
    """
    segments: list[dict] = []
    i = 0
    current_text = ""

    def flush():
        nonlocal current_text
        if current_text:
            segments.append({"kind": "text", "content": current_text})
            current_text = ""

    while i < len(s):
        ch = s[i]

        if ch == "\\":
            # LaTeX command
            i += 1
            # Read command name (letters only, or a single non-letter)
            if i < len(s) and s[i].isalpha():
                j = i
                while j < len(s) and s[j].isalpha():
                    j += 1
                cmd = s[i:j]
                i = j
                # Check for \overline{...} and arc/hat commands
                if cmd in ("overline", "widehat", "widetilde", "hat", "bar", "vec") and i < len(s) and s[i] == "{":
                    inner, i = _read_braced(s, i)
                    flush()
                    segments.append({"kind": "overline", "content": _apply_substitutions(inner)})
                elif cmd in ("textbf", "mathbf", "boldsymbol") and i < len(s) and s[i] == "{":
                    inner, i = _read_braced(s, i)
                    flush()
                    segments.append({"kind": "bold", "content": _apply_substitutions(inner)})
                elif cmd in ("textit", "mathit", "emph") and i < len(s) and s[i] == "{":
                    inner, i = _read_braced(s, i)
                    flush()
                    segments.append({"kind": "italic", "content": _apply_substitutions(inner)})
                elif cmd == "text" and i < len(s) and s[i] == "{":
                    # \text{...} → plain text (upright)
                    inner, i = _read_braced(s, i)
                    current_text += inner
                elif cmd == "frac" and i < len(s) and s[i] == "{":
                    # \frac{num}{den} → Unicode fraction if common, else num/den
                    num, i = _read_braced(s, i)
                    if i < len(s) and s[i] == "{":
                        den, i = _read_braced(s, i)
                    else:
                        den = ""
                    num = _apply_substitutions(num.strip())
                    den = _apply_substitutions(den.strip())
                    frac_unicode = {
                        ("1", "2"): "½", ("1", "3"): "⅓", ("2", "3"): "⅔",
                        ("1", "4"): "¼", ("3", "4"): "¾", ("1", "5"): "⅕",
                        ("2", "5"): "⅖", ("3", "5"): "⅗", ("4", "5"): "⅘",
                        ("1", "6"): "⅙", ("5", "6"): "⅚", ("1", "8"): "⅛",
                        ("3", "8"): "⅜", ("5", "8"): "⅝", ("7", "8"): "⅞",
                    }
                    current_text += frac_unicode.get((num, den), f"{num}/{den}")
                else:
                    current_text += _LATEX_UNICODE.get(cmd, cmd)
            else:
                if i < len(s):
                    current_text += _LATEX_UNICODE.get(s[i], s[i])
                    i += 1

        elif ch == "_":
            flush()
            i += 1
            if i < len(s) and s[i] == "{":
                inner, i = _read_braced(s, i)
            elif i < len(s) and s[i] == "\\":
                inner, i = _read_latex_cmd(s, i)
            elif i < len(s) and (s[i].isalnum() or s[i] == "_"):
                j = i
                while j < len(s) and (s[j].isalnum() or s[j] == "_"):
                    j += 1
                inner = s[i:j]
                i = j
            elif i < len(s):
                inner = s[i]
                i += 1
            else:
                inner = ""
            segments.append({"kind": "sub", "content": _apply_substitutions(inner)})

        elif ch == "^":
            flush()
            i += 1
            if i < len(s) and s[i] == "{":
                inner, i = _read_braced(s, i)
            elif i < len(s) and s[i] == "\\":
                inner, i = _read_latex_cmd(s, i)
            elif i < len(s) and (s[i].isalnum() or s[i] == "_"):
                j = i
                while j < len(s) and (s[j].isalnum() or s[j] == "_"):
                    j += 1
                inner = s[i:j]
                i = j
            elif i < len(s):
                inner = s[i]
                i += 1
            else:
                inner = ""
            segments.append({"kind": "sup", "content": _apply_substitutions(inner)})

        elif ch in "${}":
            i += 1  # skip dollar signs and bare braces

        else:
            current_text += ch
            i += 1

    flush()
    return segments


def _read_latex_cmd(s: str, i: int) -> tuple[str, int]:
    """Read a \\cmd (and optional {arg}) starting at s[i] where s[i]=='\\'.
    Returns (reconstructed_string, new_i) for use with _apply_substitutions."""
    assert s[i] == "\\"
    i += 1
    j = i
    while j < len(s) and s[j].isalpha():
        j += 1
    cmd = s[i:j]
    i = j
    if i < len(s) and s[i] == "{":
        arg, i = _read_braced(s, i)
        return f"\\{cmd}{{{arg}}}", i
    return f"\\{cmd}", i


def _read_braced(s: str, i: int) -> tuple[str, int]:
    """Read {content} starting at s[i] (where s[i]=='{'). Return (content, new_i)."""
    assert s[i] == "{"
    depth = 0
    j = i
    start = i + 1
    while j < len(s):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[start:j], j + 1
        j += 1
    return s[start:], len(s)


def _apply_substitutions(s: str) -> str:
    """Apply Unicode substitutions to a short string (e.g. inside sub/sup)."""
    result = ""
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            i += 1
            j = i
            while j < len(s) and s[j].isalpha():
                j += 1
            cmd = s[i:j]
            result += _LATEX_UNICODE.get(cmd, cmd)
            i = j
        else:
            result += s[i]
            i += 1
    return result


# ---------------------------------------------------------------------------
# Grid and axes
# ---------------------------------------------------------------------------

def _append_grid(
    svg: ET.Element,
    canvas: ir.Canvas,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    gxy,
) -> None:
    step = canvas.grid_step if canvas.grid_step > 0 else 1.0
    gxmin = round_down_to_step(xmin, step)
    gxmax = round_up_to_step(xmax, step)
    gymin = round_down_to_step(ymin, step)
    gymax = round_up_to_step(ymax, step)

    x = gxmin
    while x <= gxmax + 1e-9:
        px1, py1 = gxy(x, gymin)
        px2, py2 = gxy(x, gymax)
        ET.SubElement(svg, "line", {
            "x1": f"{px1:.2f}", "y1": f"{py1:.2f}",
            "x2": f"{px2:.2f}", "y2": f"{py2:.2f}",
            "stroke": "#ccc", "stroke-width": "0.5",
        })
        x += step

    y = gymin
    while y <= gymax + 1e-9:
        px1, py1 = gxy(gxmin, y)
        px2, py2 = gxy(gxmax, y)
        ET.SubElement(svg, "line", {
            "x1": f"{px1:.2f}", "y1": f"{py1:.2f}",
            "x2": f"{px2:.2f}", "y2": f"{py2:.2f}",
            "stroke": "#ccc", "stroke-width": "0.5",
        })
        y += step


def _append_axes(
    svg: ET.Element,
    canvas: ir.Canvas,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    gxy,
    scale: float,
    font_family: str = "serif",
    drawn_segments: list[tuple[float, float, float, float]] | None = None,
    tick_label_boxes: list[tuple[float, float, float, float]] | None = None,
) -> None:
    has_x = ymin <= 0 <= ymax
    has_y = xmin <= 0 <= xmax

    def arrow_line(x1, y1, x2, y2):
        ET.SubElement(svg, "line", {
            "x1": f"{x1:.2f}", "y1": f"{y1:.2f}",
            "x2": f"{x2:.2f}", "y2": f"{y2:.2f}",
            "stroke": "black", "stroke-width": "1.5",
            "marker-end": "url(#arrow)",
        })
        if drawn_segments is not None:
            drawn_segments.append((x1, y1, x2, y2))

    # Ensure arrow marker is defined
    _ensure_arrow_marker(svg)

    if has_x:
        px1, py1 = gxy(xmin, 0)
        px2, py2 = gxy(xmax, 0)
        arrow_line(px1, py1, px2, py2)
        if canvas.show_axis_labels:
            ET.SubElement(svg, "text", {
                "x": f"{px2 + 8:.2f}", "y": f"{py2:.2f}",
                "font-family": font_family, "font-size": str(_FONT_SIZE),
                "font-style": "italic", "dominant-baseline": "central",
            }).text = "x"

    if has_y:
        px1, py1 = gxy(0, ymin)
        px2, py2 = gxy(0, ymax)
        arrow_line(px1, py1, px2, py2)
        if canvas.show_axis_labels:
            ET.SubElement(svg, "text", {
                "x": f"{px2:.2f}", "y": f"{py2 - 8:.2f}",
                "font-family": font_family, "font-size": str(_FONT_SIZE),
                "font-style": "italic", "text-anchor": "middle",
            }).text = "y"

    tick_step = canvas.tick_step if canvas.tick_step > 0 else 1.0
    TICK_PX = _TICK_PX

    if (canvas.show_ticks or canvas.show_tick_labels) and has_x:
        for x in tick_values(xmin, xmax, tick_step):
            px, py = gxy(x, 0)
            if canvas.show_ticks:
                ET.SubElement(svg, "line", {
                    "x1": f"{px:.2f}", "y1": f"{py - TICK_PX:.2f}",
                    "x2": f"{px:.2f}", "y2": f"{py + TICK_PX:.2f}",
                    "stroke": "black", "stroke-width": "1",
                })
            if canvas.show_tick_labels:
                label_text = fmt_label_num(x)
                tx, ty = px, py + TICK_PX + 4
                ET.SubElement(svg, "text", {
                    "x": f"{tx:.2f}", "y": f"{ty:.2f}",
                    "font-family": font_family, "font-size": str(_TICK_LABEL_FONT_SIZE),
                    "text-anchor": "middle", "dominant-baseline": "hanging",
                }).text = label_text
                if tick_label_boxes is not None:
                    w = max(len(label_text), 1) * _TICK_LABEL_FONT_SIZE * 0.65
                    tick_label_boxes.append((tx - w / 2, ty, tx + w / 2, ty + _TICK_LABEL_FONT_SIZE))

    if (canvas.show_ticks or canvas.show_tick_labels) and has_y:
        for y in tick_values(ymin, ymax, tick_step):
            px, py = gxy(0, y)
            if canvas.show_ticks:
                ET.SubElement(svg, "line", {
                    "x1": f"{px - TICK_PX:.2f}", "y1": f"{py:.2f}",
                    "x2": f"{px + TICK_PX:.2f}", "y2": f"{py:.2f}",
                    "stroke": "black", "stroke-width": "1",
                })
            if canvas.show_tick_labels:
                label_text = fmt_label_num(y)
                tx, ty = px - TICK_PX - 3, py
                ET.SubElement(svg, "text", {
                    "x": f"{tx:.2f}", "y": f"{ty:.2f}",
                    "font-family": font_family, "font-size": str(_TICK_LABEL_FONT_SIZE),
                    "text-anchor": "end", "dominant-baseline": "central",
                }).text = label_text
                if tick_label_boxes is not None:
                    w = max(len(label_text), 1) * _TICK_LABEL_FONT_SIZE * 0.65
                    tick_label_boxes.append((tx - w, ty - _TICK_LABEL_FONT_SIZE / 2, tx, ty + _TICK_LABEL_FONT_SIZE / 2))


def _ensure_arrow_marker(svg: ET.Element) -> None:
    """Add an arrowhead marker to <defs> if not already present."""
    defs = svg.find("{http://www.w3.org/2000/svg}defs")
    if defs is None:
        defs = svg.find("defs")
    if defs is None:
        defs = ET.SubElement(svg, "defs")
        # Insert defs before other elements
        svg.remove(defs)
        svg.insert(0, defs)
    # Check if arrow marker already exists
    for child in defs:
        if child.get("id") == "arrow":
            return
    marker = ET.SubElement(defs, "marker", {
        "id": "arrow",
        "markerWidth": "8", "markerHeight": "8",
        "refX": "6", "refY": "3",
        "orient": "auto",
    })
    ET.SubElement(marker, "path", {
        "d": "M0,0 L0,6 L8,3 z",
        "fill": "black",
    })


# ---------------------------------------------------------------------------
# Line / ray clipping
# ---------------------------------------------------------------------------

def _clip_line_to_bounds(
    x1: float, y1: float, x2: float, y2: float,
    xmin: float, xmax: float, ymin: float, ymax: float,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Clip an infinite line (defined by two points) to the bounding box.

    Returns (cx1, cy1, cx2, cy2) or (None, None, None, None) if no intersection.
    Uses parametric line-clipping (Cohen-Sutherland-like parameter approach).
    """
    dx = x2 - x1
    dy = y2 - y1
    t_vals: list[float] = []

    # Collect all t values where the line crosses a box edge
    for edge_val, is_x, sign in [
        (xmin, True, 1), (xmax, True, -1),
        (ymin, False, 1), (ymax, False, -1),
    ]:
        denom = dx if is_x else dy
        if abs(denom) > 1e-12:
            t = ((edge_val - (x1 if is_x else y1)) / denom)
            t_vals.append(t)

    if len(t_vals) < 2:
        return None, None, None, None

    t_vals.sort()
    # Take the two widest t values that stay within the box
    candidates = []
    for t in t_vals:
        px = x1 + t * dx
        py = y1 + t * dy
        if xmin - 1e-9 <= px <= xmax + 1e-9 and ymin - 1e-9 <= py <= ymax + 1e-9:
            candidates.append((t, px, py))

    if len(candidates) < 2:
        return None, None, None, None

    (_, ax, ay), (_, bx, by) = candidates[0], candidates[-1]
    return ax, ay, bx, by


def _clip_ray_to_bounds(
    ox: float, oy: float, dx_: float, dy_: float,
    xmin: float, xmax: float, ymin: float, ymax: float,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Clip a ray (from origin in direction (dx_, dy_)) to the bounding box.

    Returns (ox, oy, ex, ey) — the ray starts at its origin and ends at
    the first box edge it hits (or None if the origin is outside).
    """
    dx = dx_ - ox
    dy = dy_ - oy
    t_max = float("inf")

    for edge_val, is_x in [
        (xmin, True), (xmax, True),
        (ymin, False), (ymax, False),
    ]:
        denom = dx if is_x else dy
        if abs(denom) > 1e-12:
            t = (edge_val - (ox if is_x else oy)) / denom
            if t > 0:
                t_max = min(t_max, t)

    if t_max == float("inf"):
        return None, None, None, None

    ex = ox + t_max * dx
    ey = oy + t_max * dy
    return ox, oy, ex, ey


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------

_CSS_COLOR_NAMES = {
    "red", "blue", "green", "orange", "purple", "cyan", "magenta",
    "yellow", "black", "white", "brown", "gray", "grey",
    "darkgray", "darkgrey", "lightgray", "lightgrey", "olive", "teal", "violet",
}

# Map TikZ thickness keywords to stroke-width values
_STROKE_WIDTHS = {"thin": "0.75", "thick": "2.5", "very thick": "3.5", "ultra thick": "5"}


def _color_from_style(style_key: str | None, styles: dict) -> str | None:
    """Extract a CSS color string from a style key, or None if not found."""
    if not style_key:
        return None
    if style_key in styles:
        d = styles[style_key]
        return d.get("color") or d.get("fill") or None
    if style_key in _CSS_COLOR_NAMES:
        return style_key
    return None


def _slugify_color(color: str) -> str:
    """Turn a CSS color string into a safe SVG id fragment."""
    return re.sub(r"[^a-zA-Z0-9]+", "-", color.strip()).strip("-").lower() or "black"


def _ensure_colored_arrow_marker(svg: ET.Element | None, color: str, *, start: bool) -> str:
    """Ensure a marker whose arrowhead fill matches ``color`` exists in <defs>; return its id.

    Arrowheads must match the line's stroke color — a black arrowhead on a
    colored line reads as a rendering glitch and defeats color-based
    differentiation for colorblind viewers who rely on line color as the
    distinguishing cue rather than position alone.
    """
    base = "arrowhead-start" if start else "arrowhead"
    if color == "black":
        return base
    marker_id = f"{base}-{_slugify_color(color)}"
    if svg is None:
        return marker_id

    defs = svg.find("{http://www.w3.org/2000/svg}defs")
    if defs is None:
        defs = svg.find("defs")
    if defs is None:
        defs = ET.SubElement(svg, "defs")
        svg.remove(defs)
        svg.insert(0, defs)

    for child in defs:
        if child.get("id") == marker_id:
            return marker_id

    if start:
        marker = ET.SubElement(defs, "marker", {
            "id": marker_id,
            "markerWidth": "8", "markerHeight": "6",
            "refX": "0", "refY": "3",
            "orient": "auto-start-reverse",
        })
    else:
        marker = ET.SubElement(defs, "marker", {
            "id": marker_id,
            "markerWidth": "8", "markerHeight": "6",
            "refX": "8", "refY": "3",
            "orient": "auto",
        })
    ET.SubElement(marker, "path", {
        "d": "M 0 0 L 8 3 L 0 6 Z",
        "fill": color,
    })
    return marker_id


def _stroke_attrs(style_key: str | None, styles: dict, svg: ET.Element | None = None) -> dict[str, str]:
    """Return SVG attribute dict for stroke styling."""
    attrs: dict[str, str] = {"stroke": "black", "stroke-width": "1.5"}
    if not style_key:
        return attrs
    if style_key in styles:
        d = styles[style_key]
        if "color" in d:
            attrs["stroke"] = str(d["color"])
        if "thick" in d and d["thick"] is True:
            attrs["stroke-width"] = "2.5"
        if "thin" in d and d["thin"] is True:
            attrs["stroke-width"] = "0.75"
        if "line_width" in d:
            attrs["stroke-width"] = str(d["line_width"])
        if "dashed" in d and d["dashed"] is True:
            attrs["stroke-dasharray"] = "6,3"
        if "dotted" in d and d["dotted"] is True:
            attrs["stroke-dasharray"] = "2,3"
        if d.get("->") is True or d.get("<->") is True:
            end_id = _ensure_colored_arrow_marker(svg, attrs["stroke"], start=False)
            attrs["marker-end"] = f"url(#{end_id})"
        if d.get("<-") is True or d.get("<->") is True:
            start_id = _ensure_colored_arrow_marker(svg, attrs["stroke"], start=True)
            attrs["marker-start"] = f"url(#{start_id})"
        return attrs
    if style_key in _CSS_COLOR_NAMES:
        attrs["stroke"] = style_key
    return attrs


def _fill_attrs(
    style_key: str | None,
    styles: dict,
    opacity: float,
) -> tuple[str, float]:
    """Return (fill_color, fill_opacity) for a Fill op."""
    if style_key and style_key in styles:
        d = styles[style_key]
        color = d.get("fill") or d.get("color") or "blue"
        op = d.get("opacity", opacity)
        return str(color), float(op)
    return "blue", opacity


def _obj_to_svg_subpath(
    obj_id: str,
    sym: dict,
    stmt_by_id: dict,
    gxy,
    scale: float,
    poly_verts_fn,
    ellipse_params_fn,
) -> str | None:
    """Return an SVG path subpath string (closed with Z) for a single shape.

    Supports Polygon/Triangle, Circle, and Ellipse. Returns None for unsupported types.
    """
    sym_obj = sym.get(obj_id)
    if sym_obj is None:
        return None

    if isinstance(sym_obj, (spg.Triangle, spg.Polygon)):
        verts = poly_verts_fn(obj_id, stmt_by_id)
        first = verts[0]
        fx, fy = gxy(sympy_to_float(sym[first].x), sympy_to_float(sym[first].y))
        parts = [f"M {fx:.2f} {fy:.2f}"]
        for v in verts[1:]:
            vx, vy = gxy(sympy_to_float(sym[v].x), sympy_to_float(sym[v].y))
            parts.append(f"L {vx:.2f} {vy:.2f}")
        parts.append("Z")
        return " ".join(parts)

    if isinstance(sym_obj, spg.Circle):
        cx_g = sympy_to_float(sym_obj.center.x)
        cy_g = sympy_to_float(sym_obj.center.y)
        r_g = sympy_to_float(sym_obj.radius)
        cx_s, cy_s = gxy(cx_g, cy_g)
        r_s = r_g * scale
        # Circle as two semicircular arcs (SVG arc cannot do a full 360° in one command)
        return (
            f"M {cx_s - r_s:.2f} {cy_s:.2f} "
            f"A {r_s:.2f} {r_s:.2f} 0 1 0 {cx_s + r_s:.2f} {cy_s:.2f} "
            f"A {r_s:.2f} {r_s:.2f} 0 1 0 {cx_s - r_s:.2f} {cy_s:.2f} Z"
        )

    if isinstance(sym_obj, spg.Ellipse):
        cx_g, cy_g, a_g, b_g = ellipse_params_fn(obj_id, sym)
        cx_s, cy_s = gxy(cx_g, cy_g)
        rx_s = a_g * scale
        ry_s = b_g * scale
        return (
            f"M {cx_s - rx_s:.2f} {cy_s:.2f} "
            f"A {rx_s:.2f} {ry_s:.2f} 0 1 0 {cx_s + rx_s:.2f} {cy_s:.2f} "
            f"A {rx_s:.2f} {ry_s:.2f} 0 1 0 {cx_s - rx_s:.2f} {cy_s:.2f} Z"
        )

    if isinstance(sym_obj, Sector):
        cx_g, cy_g, r_g, start_deg, end_deg, sx_g, sy_g = arc_params(obj_id, sym)
        r_s = r_g * scale
        end_rad = math.radians(end_deg)
        ex_g = cx_g + r_g * math.cos(end_rad)
        ey_g = cy_g + r_g * math.sin(end_rad)
        cx_s, cy_s = gxy(cx_g, cy_g)
        sx_s, sy_s = gxy(sx_g, sy_g)
        ex_s, ey_s = gxy(ex_g, ey_g)
        sweep_deg = end_deg - start_deg
        large_arc = 1 if sweep_deg > 180.0 else 0
        return (
            f"M {cx_s:.2f} {cy_s:.2f} "
            f"L {sx_s:.2f} {sy_s:.2f} "
            f"A {r_s:.2f} {r_s:.2f} 0 {large_arc} 0 {ex_s:.2f} {ey_s:.2f} Z"
        )

    return None


# ---------------------------------------------------------------------------
# Label positioning
# ---------------------------------------------------------------------------

def _label_offset(pos: str | None, dist: float) -> tuple[float, float]:
    """Return (dx, dy) pixel offset for a given position keyword."""
    if not pos or pos == "auto":
        return 0.0, -dist
    pos_l = pos.lower()
    dx, dy = 0.0, 0.0
    if "above" in pos_l:
        dy = -dist
    if "below" in pos_l:
        dy = dist
    if "left" in pos_l:
        dx = -dist
    if "right" in pos_l:
        dx = dist
    if dx == 0 and dy == 0:
        dy = -dist  # default: above
    return dx, dy


def _pos_to_anchor(pos: str | None) -> str:
    """Map TikZ position keyword to SVG text-anchor."""
    if not pos or pos == "auto":
        return "middle"
    pos_l = pos.lower()
    if "left" in pos_l and "right" not in pos_l:
        return "end"
    if "right" in pos_l and "left" not in pos_l:
        return "start"
    return "middle"


# ---------------------------------------------------------------------------
# Incident-angle-based auto label placement
# ---------------------------------------------------------------------------

def _build_incident_angles(
    diagram: ir.DiagramIR,
    sym: SymTable,
    stmt_by_id: dict,
    coords: dict,
    helpers: dict,
) -> dict[str, list[float]]:
    """Return a map of point_id → list of edge angles (in geometry space, y-up).

    Only considers objects that are actually drawn (present as Draw ops in
    diagram.render).  Angles are in radians, computed with math.atan2 in the
    math/SymPy coordinate system (y increases upward).
    """
    result: dict[str, list[float]] = {}

    def _add(pid: str, angle: float) -> None:
        result.setdefault(pid, []).append(angle)

    def _geo(pid: str) -> tuple[float, float] | None:
        if pid in coords:
            return coords[pid]
        if pid in helpers:
            return helpers[pid]
        return None

    def _edge_angles(a_id: str, b_id: str) -> None:
        """Record the angles of edge a→b at both endpoints."""
        pa = _geo(a_id)
        pb = _geo(b_id)
        if pa is None or pb is None:
            return
        ax, ay = pa
        bx, by = pb
        if ax == bx and ay == by:
            return
        angle_ab = math.atan2(by - ay, bx - ax)
        _add(a_id, angle_ab)
        _add(b_id, angle_ab + math.pi)  # opposite direction at the other end

    for op in diagram.render:
        if not isinstance(op, ir.Draw):
            continue
        obj_id = op.obj
        if obj_id not in sym:
            continue
        sym_obj = sym[obj_id]

        if isinstance(sym_obj, spg.Segment):
            a, b = seg_endpoints(obj_id, stmt_by_id)
            _edge_angles(a, b)

        elif isinstance(sym_obj, spg.Line):
            # Infinite line: both directions occupied at each defining point.
            p1_id, p2_id = line_endpoints(obj_id, stmt_by_id, helpers)
            pa, pb = _geo(p1_id), _geo(p2_id)
            if pa is not None and pb is not None:
                ax, ay = pa
                bx, by = pb
                if not (ax == bx and ay == by):
                    angle_ab = math.atan2(by - ay, bx - ax)
                    _add(p1_id, angle_ab)
                    _add(p1_id, angle_ab + math.pi)
                    _add(p2_id, angle_ab)
                    _add(p2_id, angle_ab + math.pi)

        elif isinstance(sym_obj, spg.Ray):
            stmt = stmt_by_id.get(obj_id)
            if stmt is None:
                continue
            # Ray: source has one direction; direction-point has both
            if hasattr(stmt, "a") and hasattr(stmt, "b"):
                _edge_angles(stmt.a, stmt.b)
            else:
                p1_id, p2_id = line_endpoints(obj_id, stmt_by_id, helpers)
                _edge_angles(p1_id, p2_id)

        elif isinstance(sym_obj, (spg.Triangle, spg.Polygon)):
            verts = poly_verts(obj_id, stmt_by_id)
            for i in range(len(verts)):
                _edge_angles(verts[i], verts[(i + 1) % len(verts)])

        elif isinstance(sym_obj, spg.Circle):
            # For each labeled point that lies on this circle, add both tangent
            # directions at that point (perpendicular to the radius).
            cx_g = sympy_to_float(sym_obj.center.x)
            cy_g = sympy_to_float(sym_obj.center.y)
            for lop in diagram.render:
                if not isinstance(lop, ir.LabelPoint) or lop.pos != "auto":
                    continue
                pc = _geo(lop.p)
                if pc is None:
                    continue
                px, py = pc
                # Check if point lies on circle (within tolerance)
                r_g = sympy_to_float(sym_obj.radius)
                if abs(math.hypot(px - cx_g, py - cy_g) - r_g) > 1e-6 * max(r_g, 1):
                    continue
                # Tangent is perpendicular to radius direction
                radius_angle = math.atan2(py - cy_g, px - cx_g)
                tangent = radius_angle + math.pi / 2
                _add(lop.p, tangent)
                _add(lop.p, tangent + math.pi)

    # Second pass: for each auto-labeled point, check if it lies on any drawn
    # line/segment/ray without being a defining endpoint.  If so, add that
    # object's direction as an incident angle.  This catches intersection
    # points and points that lie on lines defined through other points.
    auto_label_pids = [
        lop.p for lop in diagram.render
        if isinstance(lop, ir.LabelPoint) and (not lop.pos or lop.pos == "auto")
    ]
    drawn_objs = [
        (op.obj, sym[op.obj]) for op in diagram.render
        if isinstance(op, ir.Draw) and op.obj in sym
    ]
    for pid in auto_label_pids:
        pc = _geo(pid)
        if pc is None:
            continue
        px, py = pc
        for obj_id, sym_obj in drawn_objs:
            if isinstance(sym_obj, (spg.Segment, spg.Line, spg.Ray)):
                # Skip if this point is already a defining endpoint
                stmt = stmt_by_id.get(obj_id)
                if stmt is not None:
                    defining_pts = set()
                    for attr in ("a", "b", "p", "q", "through"):
                        v = getattr(stmt, attr, None)
                        if isinstance(v, str):
                            defining_pts.add(v)
                    if pid in defining_pts:
                        continue
                # Check if the point lies on this object
                p1 = sym_obj.p1
                p2 = sym_obj.p2
                x1, y1 = sympy_to_float(p1.x), sympy_to_float(p1.y)
                x2, y2 = sympy_to_float(p2.x), sympy_to_float(p2.y)
                dx, dy = x2 - x1, y2 - y1
                length = math.hypot(dx, dy)
                if length < 1e-12:
                    continue
                # Distance from point to the infinite line through p1-p2
                dist = abs(dy * (px - x1) - dx * (py - y1)) / length
                tol = 1e-6 * max(length, 1)
                if dist > tol:
                    continue
                # For Segment, also check that the point is between endpoints
                if isinstance(sym_obj, spg.Segment):
                    t = ((px - x1) * dx + (py - y1) * dy) / (length * length)
                    if t < -1e-6 or t > 1 + 1e-6:
                        continue
                line_angle = math.atan2(dy, dx)
                _add(pid, line_angle)
                _add(pid, line_angle + math.pi)

            elif isinstance(sym_obj, (spg.Triangle, spg.Polygon)):
                # Check if the point lies on any edge of the polygon
                verts = poly_verts(obj_id, stmt_by_id)
                if pid in verts:
                    continue  # already handled as a vertex in the first pass
                for i in range(len(verts)):
                    v1_id = verts[i]
                    v2_id = verts[(i + 1) % len(verts)]
                    pv1 = _geo(v1_id)
                    pv2 = _geo(v2_id)
                    if pv1 is None or pv2 is None:
                        continue
                    x1, y1 = pv1
                    x2, y2 = pv2
                    dx, dy = x2 - x1, y2 - y1
                    edge_len = math.hypot(dx, dy)
                    if edge_len < 1e-12:
                        continue
                    dist = abs(dy * (px - x1) - dx * (py - y1)) / edge_len
                    tol = 1e-6 * max(edge_len, 1)
                    if dist > tol:
                        continue
                    # Check point is between endpoints
                    t = ((px - x1) * dx + (py - y1) * dy) / (edge_len * edge_len)
                    if t < -1e-6 or t > 1 + 1e-6:
                        continue
                    edge_angle = math.atan2(dy, dx)
                    _add(pid, edge_angle)
                    _add(pid, edge_angle + math.pi)

    # Resolve aliases: if point X is an alias for point Y, copy Y's angles to X.
    for stmt in diagram.define:
        if isinstance(stmt, ir.PointAlias):
            ref_angles = result.get(stmt.ref, [])
            if ref_angles:
                result.setdefault(stmt.id, []).extend(ref_angles)

    return result


def _build_angle_mark_wedges(
    diagram: ir.DiagramIR,
    sym: SymTable,
    coords: dict,
    helpers: dict,
) -> dict[str, list[tuple[float, float]]]:
    """Return point_id → list of (start, start+size) angular spans (radians,
    geometry space, y-up) occupied by a mark_angles/mark_right_angles arc at
    that point's vertex.  ``start`` is normalised to [0, 2π); size is in
    (0, 2π).  Used so auto label placement avoids bisecting a gap that an
    angle arc is drawn in.
    """
    TWO_PI = 2 * math.pi

    def _geo(pid: str) -> tuple[float, float] | None:
        if pid in coords:
            return coords[pid]
        if pid in helpers:
            return helpers[pid]
        return None

    result: dict[str, list[tuple[float, float]]] = {}
    for op in diagram.render:
        if not isinstance(op, (ir.MarkAngles, ir.MarkRightAngles)):
            continue
        which = getattr(op, "which", "interior")
        for angle in op.angles:
            po = _geo(angle.o)
            pa = _geo(angle.a)
            pb = _geo(angle.b)
            if po is None or pa is None or pb is None:
                continue
            ox, oy = po
            d_a = math.atan2(pa[1] - oy, pa[0] - ox)
            d_b = math.atan2(pb[1] - oy, pb[0] - ox)
            d_a %= TWO_PI
            d_b %= TWO_PI
            s1 = (d_b - d_a) % TWO_PI  # CCW span a -> b
            if s1 <= math.pi:
                interior = (d_a, d_a + s1)
                exterior = (d_b, d_b + (TWO_PI - s1))
            else:
                interior = (d_b, d_b + (TWO_PI - s1))
                exterior = (d_a, d_a + s1)
            span = interior if which == "interior" else exterior
            result.setdefault(angle.o, []).append(span)
    return result


def _angle_in_wedges(angle: float, wedges: list[tuple[float, float]]) -> bool:
    TWO_PI = 2 * math.pi
    a = angle % TWO_PI
    for start, end in wedges:
        if (a - start) % TWO_PI < (end - start):
            return True
    return False


def _auto_label_direction(
    angles: list[float],
    wedges: list[tuple[float, float]] | None = None,
) -> float:
    """Return the angle (geometry space, y-up) of the largest gap between edges.

    - No edges → default to straight up (π/2).
    - One edge angle → place label on the opposite side.
    - Multiple → find the largest angular gap and bisect it, skipping gaps
      whose bisector falls inside a drawn angle-mark wedge (``wedges``).
    """
    if not angles:
        return math.pi / 2  # above

    # Normalise all angles to [0, 2π)
    TWO_PI = 2 * math.pi
    normed = sorted(a % TWO_PI for a in angles)

    if len(normed) == 1:
        return (normed[0] + math.pi) % TWO_PI

    # Compute gaps between consecutive sorted angles (wrapping around),
    # largest first, and pick the first one whose bisector clears any
    # angle-mark wedge at this point.
    n = len(normed)
    gaps = []
    for i in range(n):
        a1 = normed[i]
        a2 = normed[(i + 1) % n]
        gap = (a2 - a1) % TWO_PI
        bisector = (a1 + gap / 2) % TWO_PI
        gaps.append((gap, bisector))
    gaps.sort(key=lambda g: g[0], reverse=True)

    if wedges:
        for gap, bisector in gaps:
            if not _angle_in_wedges(bisector, wedges):
                return bisector

    return gaps[0][1]


def _angle_to_offset(angle: float, dist: float) -> tuple[float, float]:
    """Convert a geometry-space angle to an SVG pixel offset (dx, dy).

    SVG y-axis is flipped relative to geometry space, so we negate the sin
    component.
    """
    return math.cos(angle) * dist, -math.sin(angle) * dist


def _angle_to_anchor(angle: float) -> str:
    """Map a geometry-space label angle to an SVG text-anchor value."""
    # Normalise to (-π, π]
    a = (angle + math.pi) % (2 * math.pi) - math.pi
    # Roughly above/below (within ±45° of vertical) → "middle"
    if math.pi / 4 < a <= 3 * math.pi / 4:
        return "middle"   # above
    if -3 * math.pi / 4 <= a < -math.pi / 4:
        return "middle"   # below
    # Left half-plane → "end" (text ends at the point)
    if abs(a) > math.pi / 2:
        return "end"
    # Right half-plane → "start"
    return "start"


def _point_to_segment_distance(
    px: float, py: float,
    x1: float, y1: float,
    x2: float, y2: float,
) -> tuple[float, float, float]:
    """Return (distance, nearest_x, nearest_y) from point to line segment."""
    dx, dy = x2 - x1, y2 - y1
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-12:
        return math.hypot(px - x1, py - y1), x1, y1
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / len_sq))
    nx, ny = x1 + t * dx, y1 + t * dy
    return math.hypot(px - nx, py - ny), nx, ny


def _nudge_labels_from_lines(
    labels: list[_LabelPlacement],
    drawn_segments: list[tuple[float, float, float, float]],
) -> None:
    """Nudge labels whose bbox overlaps or is too close to a drawn line or segment.

    Uses up to 4 iterations so a label nudged away from one line doesn't land
    on another.  The required clearance uses the support function of the label
    bbox in the nudge direction: half_extent = |W/2·|dx|| + |H/2·|dy||.
    This correctly handles wide math labels on diagonal/vertical segments where
    a height-only threshold would leave the bbox corners crossing the segment.
    """
    _MARGIN = _FONT_SIZE * 0.35
    _EPS = 0.5  # small overshoot so the re-check passes without float jitter
    for _ in range(4):
        moved = False
        for lp in labels:
            # The anchor point (lp.x, lp.y) is NOT the bbox centre for
            # start/end-anchored labels — _label_bbox is anchor-aware.  Measure
            # clearance from the true bbox centre so a start-anchored label
            # sitting just right of a vertical line isn't spuriously pushed
            # w/2 further away (the origin-label bug).  The centre offset is
            # constant per label, so nudging lp moves the bbox identically.
            bx0, by0, bx1, by1 = _label_bbox(lp)
            off_x = (bx0 + bx1) / 2 - lp.x
            off_y = (by0 + by1) / 2 - lp.y
            for x1, y1, x2, y2 in drawn_segments:
                cx, cy = lp.x + off_x, lp.y + off_y
                dist, near_x, near_y = _point_to_segment_distance(cx, cy, x1, y1, x2, y2)

                # Compute the nudge direction first — needed for the support function.
                if dist < 1e-6:
                    # Label center is on the segment; push 90° CCW from it.
                    sdx, sdy = x2 - x1, y2 - y1
                    smag = math.hypot(sdx, sdy) or 1.0
                    dx, dy = -sdy / smag, sdx / smag
                else:
                    # Push away from the nearest point on the segment.
                    dx = (cx - near_x) / dist
                    dy = (cy - near_y) / dist

                # Support function: extent of the label bbox in the nudge direction.
                # This is the minimum center-to-segment distance for the bbox to clear.
                half_extent = abs(lp.width_est / 2 * dx) + abs(lp.height_est / 2 * dy)
                min_dist = half_extent + _MARGIN

                if dist >= min_dist:
                    continue

                nudge = min_dist - dist + _EPS
                lp.x += dx * nudge
                lp.y += dy * nudge
                moved = True
        if not moved:
            break


def _nudge_labels_from_fixed_boxes(
    labels: list[_LabelPlacement],
    boxes: list[tuple[float, float, float, float]],
) -> None:
    """Push movable labels (point/segment/angle/free-text) clear of fixed
    obstacle boxes — axis tick labels — that never move themselves.

    Tick labels are drawn immediately in _append_axes rather than through
    this module's deferred pending_labels pipeline, so without this pass
    other labels have no way to even detect them, let alone avoid them: a
    segment's length label sits at its midpoint, and that midpoint commonly
    lands exactly on a tick position (e.g. a segment from 0 to 400 with
    grid_step=50 has its midpoint, 200, fall exactly on the "200" tick).
    """
    padding = 2.0
    for _ in range(4):
        moved = False
        for lp in labels:
            bb = _label_bbox(lp)
            for bx0, by0, bx1, by1 in boxes:
                box_pad = (bx0 - padding, by0 - padding, bx1 + padding, by1 + padding)
                if not _bboxes_overlap(bb, box_pad):
                    continue
                bcx, bcy = (bx0 + bx1) / 2, (by0 + by1) / 2
                dx, dy = lp.x - bcx, lp.y - bcy
                dist = math.hypot(dx, dy)
                if dist < 1e-6:
                    dx, dy, dist = 0.0, -1.0, 1.0
                else:
                    dx, dy = dx / dist, dy / dist
                label_extent = abs(lp.width_est / 2 * dx) + abs(lp.height_est / 2 * dy)
                box_extent = abs((bx1 - bx0) / 2 * dx) + abs((by1 - by0) / 2 * dy)
                min_dist = label_extent + box_extent + padding
                if dist >= min_dist:
                    continue
                nudge = min_dist - dist + 0.5
                lp.x += dx * nudge
                lp.y += dy * nudge
                bb = _label_bbox(lp)
                moved = True
        if not moved:
            break


def _bisector_angle(da: float, db: float) -> float:
    """Return the bisector angle of two rays at angles da and db (geometry space, y-up).

    Uses CCW angular difference from da to db so the result correctly bisects
    the interior arc even when the angles straddle the ±π discontinuity.
    """
    diff = (db - da) % (2 * math.pi)
    return da + diff / 2


def _segment_label_side(
    mx: float, my: float,
    nx: float, ny: float,
    other_points: list[tuple[float, float]],
) -> float:
    """Return +1 or -1 for the perpendicular side that has less nearby weight.

    (mx, my) is the midpoint of the segment in SVG pixel space.
    (nx, ny) is the unit CCW perpendicular vector in SVG pixel space.
    Positive side = direction of (nx, ny).

    Each point's vote is weighted by 1/(distance+1) so a close point
    (e.g. the opposite triangle vertex) outweighs many distant ones.
    """
    pos_weight = 0.0
    neg_weight = 0.0
    for px, py in other_points:
        proj = (px - mx) * nx + (py - my) * ny
        dist = math.hypot(px - mx, py - my) + 1.0
        w = 1.0 / dist
        if proj > 0:
            pos_weight += w
        else:
            neg_weight += w
    # Place label on the side with lower weighted presence
    return -1.0 if pos_weight > neg_weight else 1.0


def _estimate_text_width(text: str) -> float:
    """Approximate rendered text width in SVG pixels for collision detection."""
    # Strip dollar signs and LaTeX commands (each becomes ~1 char wide)
    t = text.strip()
    if t.startswith("$") and t.endswith("$"):
        t = t[1:-1]
    # Replace command sequences like \alpha, \theta with a single character
    t = re.sub(r"\\[a-zA-Z]+", "X", t)
    # Drop grouping chars
    t = re.sub(r"[{}_^]", "", t)
    return max(len(t), 1) * _FONT_SIZE * 0.65


def _make_label_placement(
    x: float,
    y: float,
    text: str,
    color: str,
    anchor: str,
    attrs: dict[str, str],
) -> _LabelPlacement:
    """Build a ``_LabelPlacement``, using mathtext metrics when appropriate.

    If *text* is a math expression (as classified by :func:`label_needs_mathtext`),
    we render it via the mathtext engine to obtain an accurate bounding box and
    store the :class:`MathGlyph` for later emission.  Otherwise we fall back to
    the approximate char-count estimator and a plain ``<text>`` path.
    """
    if label_needs_mathtext(text):
        glyph = render_math_to_svg(text, font_size=float(_FONT_SIZE))
        if glyph is not None:
            return _LabelPlacement(
                x=x, y=y, text=text, color=color, anchor=anchor, attrs=attrs,
                width_est=glyph.width,
                height_est=glyph.height,
                math_glyph=glyph,
            )
    # Fallback: plain text path with approximate sizing
    return _LabelPlacement(
        x=x, y=y, text=text, color=color, anchor=anchor, attrs=attrs,
        width_est=_estimate_text_width(text),
    )


def _label_bbox(lp: _LabelPlacement) -> tuple[float, float, float, float]:
    """Return (x_min, y_min, x_max, y_max) for a label's approximate bounding box."""
    w = lp.width_est
    h = lp.height_est
    if lp.anchor == "middle":
        x0 = lp.x - w / 2
    elif lp.anchor == "end":
        x0 = lp.x - w
    else:
        x0 = lp.x
    y0 = lp.y - h / 2  # dominant-baseline: central
    return x0, y0, x0 + w, y0 + h


def _bboxes_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    """Return True if two AABBs intersect."""
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _dedup_coincident_labels(labels: list[_LabelPlacement]) -> None:
    """Remove later point labels whose position is within 2px of an earlier one."""
    seen_positions: list[tuple[float, float]] = []
    to_remove: list[int] = []
    for i, lp in enumerate(labels):
        if lp.attrs.get("data-role") != "label-point":
            continue
        pos = (lp.x, lp.y)
        for sp in seen_positions:
            if math.hypot(pos[0] - sp[0], pos[1] - sp[1]) < 2.0:
                to_remove.append(i)
                break
        else:
            seen_positions.append(pos)
    for i in reversed(to_remove):
        del labels[i]


def _resolve_label_collisions(labels: list[_LabelPlacement], svg_w: float, svg_h: float) -> None:
    """Nudge overlapping labels apart in-place. O(n²) per pass, up to 6 passes.

    Both colliding labels are displaced symmetrically so no label is
    permanently anchored (the previous code only moved label i, leaving j fixed).
    """
    padding = 2.0
    margin = _FONT_SIZE
    for _ in range(6):
        moved = False
        for i in range(len(labels)):
            for j in range(i):
                bb_i = _label_bbox(labels[i])
                bb_j = _label_bbox(labels[j])
                bb_j_pad = (bb_j[0] - padding, bb_j[1] - padding,
                            bb_j[2] + padding, bb_j[3] + padding)
                if not _bboxes_overlap(bb_i, bb_j_pad):
                    continue
                dx = labels[i].x - labels[j].x
                dy = labels[i].y - labels[j].y
                dist = math.hypot(dx, dy)
                if dist < 1e-6:
                    dx, dy, dist = 0.0, -1.0, 1.0
                # Push both labels apart by half the nudge each
                half = _FONT_SIZE * 0.8
                nx_step = (dx / dist) * half
                ny_step = (dy / dist) * half
                labels[i].x += nx_step
                labels[i].y += ny_step
                labels[j].x -= nx_step
                labels[j].y -= ny_step
                for lp in (labels[i], labels[j]):
                    lp.x = max(margin, min(svg_w - margin, lp.x))
                    lp.y = max(margin, min(svg_h - margin, lp.y))
                moved = True
                break  # recompute bboxes after each move
        if not moved:
            break


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------

def _circle_center_id(circle_id: str, stmt_by_id: dict) -> str | None:
    """Return the named center point ID for a circle DefStmt, if available."""
    stmt = stmt_by_id.get(circle_id)
    if stmt is None:
        return None
    if isinstance(stmt, ir.CircleCenterPoint):
        return stmt.center
    if isinstance(stmt, ir.CircleCenterRadius):
        return stmt.center
    # CircleThrough3 has no named center point
    return None


def _geo_coord(
    pid: str,
    coords: dict[str, tuple[float, float]],
    helpers: dict[str, tuple[float, float]],
) -> tuple[float, float]:
    if pid in coords:
        return coords[pid]
    if pid in helpers:
        return helpers[pid]
    raise KeyError(f"Point {pid!r} not in coords or helpers")


def _warn(warnings: list[str] | None, msg: str) -> None:
    logger.warning(msg)
    if warnings is not None:
        warnings.append(msg)
