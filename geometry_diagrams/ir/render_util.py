"""Shared rendering utilities used by both TikZ and SVG backends.

Contains geometry helpers, IR navigation helpers, bounds computation,
coordinate extraction, helper-point synthesis, and numeric formatting.
Neither module has any backend-specific logic — both to_tikz.py and
to_svg.py import from here.
"""
from __future__ import annotations

import colorsys
import logging
import math
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

import sympy.geometry as spg
from sympy.geometry.line import LinearEntity

from . import ir
from .derived import REGISTRY as DERIVED_REGISTRY, effective_defs
from .conic_kernel import EllipseFrame
from .to_sympy import Arc, EllipticalArc, Sector, EllipticalSector, RotatedEllipse, SymTable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BOUNDS_PADDING = 0.8
_TICK_HALF_LENGTH = 0.05

# Bare color names a render op's ``style`` may give instead of a key into
# ``DiagramIR.styles``; both renderers recognize exactly this set.
NAMED_STYLE_COLORS = frozenset({
    "red", "blue", "green", "orange", "purple", "cyan", "magenta",
    "yellow", "black", "white", "brown", "gray", "grey",
    "darkgray", "darkgrey", "lightgray", "lightgrey", "olive", "teal", "violet",
})


# ---------------------------------------------------------------------------
# Color translation layer
# ---------------------------------------------------------------------------
#
# A color specification string is parsed ONCE into a backend-neutral value
# (``ParsedColor``) and each renderer emits it natively:
#
#   form                  SVG                 TikZ
#   named / "none"        unchanged           unchanged (xcolor knows them)
#   CSS name xcolor lacks unchanged           \definecolor'd name (e.g. lightblue, gold;
#   (and grey spellings)                      CSS values, from matplotlib's CSS4 table)
#   #rrggbb, #rgb         #rrggbb             \definecolor'd name
#   rgb(r, g, b) 0-255    #rrggbb             \definecolor'd name
#   hsv(h, s, v)          #rrggbb             \definecolor'd name
#   name!pct[!name2]      #rrggbb             unchanged (xcolor mixes natively)
#   anything else         unchanged + warn    unchanged + warn
#
# Mixes are computed from xcolor's own definitions of the named colors (not
# CSS's -- CSS "green" is #008000, xcolor's is #00ff00) so the SVG agrees with
# what TikZ draws for the same mix string.

# The style-dict keys whose string values are colors.
COLOR_STYLE_KEYS = ("color", "fill", "draw", "text")

# xcolor's base definitions (0-1 per channel) of NAMED_STYLE_COLORS; the
# "grey" spellings, which xcolor itself does not define, map to the gray ones.
_XCOLOR_RGB: dict[str, tuple[float, float, float]] = {
    "red": (1, 0, 0), "green": (0, 1, 0), "blue": (0, 0, 1),
    "cyan": (0, 1, 1), "magenta": (1, 0, 1), "yellow": (1, 1, 0),
    "black": (0, 0, 0), "white": (1, 1, 1),
    "gray": (0.5, 0.5, 0.5), "grey": (0.5, 0.5, 0.5),
    "darkgray": (0.25, 0.25, 0.25), "darkgrey": (0.25, 0.25, 0.25),
    "lightgray": (0.75, 0.75, 0.75), "lightgrey": (0.75, 0.75, 0.75),
    "brown": (0.75, 0.5, 0.25), "olive": (0.5, 0.5, 0), "orange": (1, 0.5, 0),
    "purple": (0.75, 0, 0.25), "teal": (0, 0.5, 0.5), "violet": (0.5, 0, 0.5),
}

# Color names xcolor itself defines (its base set, always available). Any other
# CSS4 name, and the "grey" spellings, must be defined for TikZ.
_XCOLOR_BASE_NAMES = frozenset({
    "black", "blue", "brown", "cyan", "darkgray", "gray", "green", "lightgray", "lime",
    "magenta", "olive", "orange", "pink", "purple", "red", "teal", "violet", "white", "yellow",
})


def _css_rgb(name: str) -> tuple[int, int, int] | None:
    """RGB (0-255) of a color name TikZ cannot resolve on its own, else None.

    The "grey" spellings take the gray values (xcolor has no "grey"); any other
    CSS4 name xcolor does not define takes its CSS value."""
    if name in _XCOLOR_BASE_NAMES:
        return None
    if name in _XCOLOR_RGB:
        return _to_255(_XCOLOR_RGB[name])
    from matplotlib.colors import CSS4_COLORS, to_rgb

    if name in CSS4_COLORS:
        return _to_255(to_rgb(CSS4_COLORS[name]))
    return None


_HEX6_RE = re.compile(r"#([0-9a-fA-F]{6})")
_HEX3_RE = re.compile(r"#([0-9a-fA-F]{3})")
_RGB_RE = re.compile(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)")
_NUM = r"(\d+(?:\.\d*)?|\.\d+)"
_HSV_RE = re.compile(rf"hsv\(\s*{_NUM}\s*,\s*{_NUM}\s*,\s*{_NUM}\s*\)")
_MIX_RE = re.compile(r"([a-z]+)!(\d+(?:\.\d+)?)(?:!([a-z]+))?")

# Prefix of the generated TikZ color names (letters and hex digits only, so
# nothing TeX or the TikZ option parser could misread).
_TIKZ_COLOR_PREFIX = "gdrgb"


@dataclass(frozen=True)
class ParsedColor:
    """A color specification parsed once, independent of any backend.

    ``form`` is "named", "css", "hex", "rgb", "hsv", "mix" or "unrecognized";
    ``rgb`` (0-255 integers) is set for every form except "named" and
    "unrecognized", whose ``text`` every backend passes through unchanged.
    A "css" name is passed through by SVG (valid CSS) but defined for TikZ,
    because xcolor lacks it.
    """
    text: str
    form: str
    rgb: tuple[int, int, int] | None = None

    @property
    def recognized(self) -> bool:
        return self.form != "unrecognized"


def _to_255(channels: tuple[float, float, float]) -> tuple[int, int, int]:
    r, g, b = (int(c * 255 + 0.5) for c in channels)
    return r, g, b


def parse_color(text: str) -> ParsedColor:
    """Parse a color specification string (see the table above)."""
    if text in NAMED_STYLE_COLORS or text == "none":
        # Named for SVG; TikZ additionally defines the names xcolor lacks (see
        # ``tikz_color``), so the parsed form says "css" for those.
        rgb = _css_rgb(text) if text != "none" else None
        return ParsedColor(text, "css", rgb) if rgb is not None else ParsedColor(text, "named")
    if (rgb := _css_rgb(text)) is not None:
        return ParsedColor(text, "css", rgb)
    if m := _HEX6_RE.fullmatch(text):
        h = m.group(1)
        return ParsedColor(text, "hex", (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))
    if m := _HEX3_RE.fullmatch(text):
        r, g, b = (int(c * 2, 16) for c in m.group(1))
        return ParsedColor(text, "hex", (r, g, b))
    if m := _RGB_RE.fullmatch(text):
        r, g, b = (int(v) for v in m.groups())
        if max(r, g, b) <= 255:
            return ParsedColor(text, "rgb", (r, g, b))
    elif m := _HSV_RE.fullmatch(text):
        h, s, v = (float(x) for x in m.groups())
        if h <= 360 and s <= 1 and v <= 1:
            return ParsedColor(text, "hsv", _to_255(colorsys.hsv_to_rgb((h % 360) / 360, s, v)))
    elif m := _MIX_RE.fullmatch(text):
        first, pct, second = m.group(1), float(m.group(2)), m.group(3) or "white"
        if first in _XCOLOR_RGB and second in _XCOLOR_RGB and pct <= 100:
            p = pct / 100
            c1, c2 = _XCOLOR_RGB[first], _XCOLOR_RGB[second]
            mixed = tuple(p * a + (1 - p) * b for a, b in zip(c1, c2))
            return ParsedColor(text, "mix", _to_255(mixed))  # type: ignore[arg-type]
    return ParsedColor(text, "unrecognized")


def svg_color(text: str) -> str:
    """The SVG paint for a color spec: ``#rrggbb`` for every converted form,
    the string unchanged for named and unrecognized ones."""
    parsed = parse_color(text)
    if parsed.rgb is None or parsed.form == "css":
        return text
    return "#{:02x}{:02x}{:02x}".format(*parsed.rgb)


def tikz_color(text: str) -> tuple[str, str | None]:
    """The TikZ color for a color spec, as ``(name, definition)``.

    Hex, rgb(...) and hsv(...) forms, and the CSS names xcolor lacks, get a name derived from the RGB value
    (the same value always gets the same name) and the ``\\definecolor`` line
    (xcolor's ``RGB`` model: integers 0-255) that must precede its first use.
    Named colors, xcolor mixes and unrecognized strings are returned
    unchanged with no definition."""
    parsed = parse_color(text)
    if parsed.form not in ("hex", "rgb", "hsv", "css"):
        return text, None
    r, g, b = parsed.rgb  # type: ignore[misc]
    name = f"{_TIKZ_COLOR_PREFIX}{r:02x}{g:02x}{b:02x}"
    return name, f"\\definecolor{{{name}}}{{RGB}}{{{r},{g},{b}}}"


def unrecognized_color_warning(text: str) -> str:
    return (
        f"Unrecognized color {text!r}: passed through unchanged, so the two renderers "
        f"may disagree on it. Use a named color ({', '.join(sorted(NAMED_STYLE_COLORS))}), "
        f"hex '#rrggbb', 'rgb(r, g, b)' (0-255), 'hsv(h, s, v)' (h 0-360, s and v 0-1) "
        f"or an xcolor mix such as 'blue!30' or 'red!40!blue'."
    )


def ordered_polygon_paints(
    op: Any, emit: Callable[[str], str], warnings: list[str] | None
) -> tuple[str, str]:
    """``(fill, stroke)`` of an ``ir.OrderedPolygon`` in the backend's native
    form (``emit`` is ``svg_color`` or the name half of ``tikz_color``). An
    unrecognized string passes through and warns once per distinct message, the
    same message ``translate_style_colors`` uses."""
    for spec in (op.fill, op.stroke):
        if not parse_color(spec).recognized and warnings is not None:
            message = unrecognized_color_warning(spec)
            if message not in warnings:
                warnings.append(message)
    return emit(op.fill), emit(op.stroke)


def bare_color_key(style_key: str | None) -> bool:
    """True if a render op's bare ``style`` (not a key of ``DiagramIR.styles``)
    is itself a recognized color specification. ``none`` is excluded: it is
    accepted only as a value inside a style dict (``fill: none``), never as a
    bare style, which both renderers have always ignored."""
    return (
        style_key is not None and style_key not in ("", "none")
        and parse_color(style_key).recognized
    )


def translate_style_colors(
    styles: dict[str, dict[str, Any]],
    emit: Callable[[str], str],
    warnings: list[str] | None,
) -> dict[str, dict[str, Any]]:
    """A copy of ``styles`` with every string value under a color key
    (``COLOR_STYLE_KEYS``) replaced by ``emit(value)`` -- the backend's
    native form. Each distinct unrecognized string adds one warning."""
    warned: set[str] = set()
    out: dict[str, dict[str, Any]] = {}
    for key, style in styles.items():
        new_style = dict(style)
        for ck in COLOR_STYLE_KEYS:
            value = style.get(ck)
            if not isinstance(value, str):
                continue
            if not parse_color(value).recognized and value not in warned:
                warned.add(value)
                if warnings is not None:
                    warnings.append(unrecognized_color_warning(value))
            new_style[ck] = emit(value)
        out[key] = new_style
    return out


# ---------------------------------------------------------------------------
# Coordinate extraction and helper-point synthesis
# ---------------------------------------------------------------------------

def centroid_of_obj(obj: Any) -> tuple[float, float]:
    """A representative "center" point for label_text(centroid_of=...),
    for any object kind that can be drawn — not just Polygon/Triangle
    (which have .vertices). Circle/Ellipse have no .vertices at all;
    Arc/Sector/EllipticalArc/EllipticalSector are lightweight marker
    types (see to_sympy.py) with no .vertices either — both previously
    crashed uncaught with AttributeError, escaping the retry loop
    entirely instead of giving the model a chance to fix it (confirmed
    2026-08-09 across two unrelated models' eval failures). Line/Segment/Ray
    (from line_through/segment/ray/tangent_line/angle_bisector/etc.) have
    no .vertices either — this one wasn't caught by a crash, since
    build_entity_manifest's except-and-skip swallowed it silently instead:
    a named Line/Segment/Ray variable was simply absent from the "named"
    entity manifest, invisible to check_edit_locality regardless of
    whether it appeared, disappeared, or moved (confirmed 2026-08-18, found
    via evals/eval_locality_retry_judgment.py's fixture bank).

    For a pie-slice sector/arc, the average of center/start/end is not
    the exact area centroid of the region, but it's a reasonable point
    near the middle of the shape for text placement — the same
    standard this function already applies to Polygon (average of
    vertices, not the exact area centroid either). Line/Segment/Ray's
    midpoint of its two defining points (.p1/.p2, shared by the whole
    LinearEntity family) is the equivalent stand-in for an object with no
    natural "center" at all."""
    registered = DERIVED_REGISTRY.position_of(obj)
    if registered is not None:
        return registered
    if isinstance(obj, (Arc, Sector, EllipticalArc, EllipticalSector)):
        pts = [obj.center, obj.start, obj.end]
    elif isinstance(obj, (spg.Circle, spg.Ellipse, RotatedEllipse)):
        pts = [obj.center]
    elif isinstance(obj, LinearEntity):
        pts = [obj.p1, obj.p2]
    elif isinstance(obj, list):
        # A compiled PolylineOpen (to_sympy.py's ir.PolylineOpen case) is a
        # plain list of Points, not an object with .vertices -- this used to
        # raise AttributeError, same failure mode as the other marker types
        # above.
        pts = obj
    else:
        pts = list(obj.vertices)
    cx = sum(sympy_to_float(p.x) for p in pts) / len(pts)
    cy = sum(sympy_to_float(p.y) for p in pts) / len(pts)
    return cx, cy


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
    - ``_rt_{id}`` — through-point for CircleCenterRadius / CircleTangentAt
    - ``_cc_{id}`` — center for CircleThrough3 / CircleTangentAt
    """
    helpers: dict[str, tuple[float, float]] = {}
    for stmt in effective_defs(diagram):
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
        elif isinstance(stmt, ir.CircleTangentAt):
            # Neither the center nor any point at radius distance is named by
            # the statement itself, so synthesize both from the compiled circle.
            circ = sym[stmt.id]
            cx = sympy_to_float(circ.center.x)
            cy = sympy_to_float(circ.center.y)
            helpers[f"_cc_{stmt.id}"] = (cx, cy)
            helpers[f"_rt_{stmt.id}"] = (cx + sympy_to_float(circ.radius), cy)
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
        case ir.PolylineOpen(points=pts):
            return list(pts)
        case _:
            registered = DERIVED_REGISTRY.vertex_ids(stmt)
            if registered is not None:
                return registered
            raise ValueError(f"Cannot get polygon vertices for {stmt.kind!r}")


def seg_endpoints(seg_id: str, stmt_by_id: dict) -> tuple[str, str]:
    """Return (a, b) endpoint IDs for a Segment or Ray DefStmt — a Ray has
    the same a/b point-id fields as a Segment (a, extending through and
    beyond b), so it resolves the same way. Used by both rendering
    backends' MarkSegments handling, which is why a ray marked equal/
    parallel/proportional to a segment must resolve here instead of
    raising."""
    stmt = stmt_by_id[seg_id]
    if not isinstance(stmt, (ir.Segment, ir.Ray)):
        raise ValueError(f"Expected Segment or Ray def for {seg_id!r}, got {stmt.kind!r}")
    return stmt.a, stmt.b


def parallel_chevron_flips(
    ops: list,
    stmt_by_id: dict,
    xy,
) -> set[tuple[str, str]]:
    """Return the ``(group, seg_id)`` pairs whose parallel chevron must point
    B->A instead of A->B so every chevron in a ``parallelN`` group points the
    same way.

    The first marked segment of each group (in op order) fixes the group's
    direction; any later segment whose direction has a negative dot product
    with it is flipped. A perpendicular segment (zero dot) is left as
    authored. ``xy(point_id)`` returns the point's coordinates in any frame
    that preserves the sign of the dot product (both renderers use theirs).
    Only ops that actually draw chevrons count: a ``ticks`` override or a
    non-parallel group is ignored. Undefined segments are skipped here; each
    renderer already warns about them.
    """
    ref: dict[str, tuple[float, float]] = {}
    flips: set[tuple[str, str]] = set()
    for op in ops:
        if not isinstance(op, ir.MarkSegments):
            continue
        if op.ticks is not None or not (op.group and op.group.startswith("parallel")):
            continue
        for seg_id in op.segs:
            if seg_id not in stmt_by_id:
                continue
            a, b = seg_endpoints(seg_id, stmt_by_id)
            (ax, ay), (bx, by) = xy(a), xy(b)
            d = (bx - ax, by - ay)
            if op.group not in ref:
                ref[op.group] = d
            elif d[0] * ref[op.group][0] + d[1] * ref[op.group][1] < 0:
                flips.add((op.group, seg_id))
    return flips


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


def line_label_endpoints(
    obj_id: str,
    stmt_by_id: dict,
    helpers: dict[str, tuple[float, float]],
) -> "tuple[str, str] | None":
    """Return (a, b) point ids to anchor a midpoint+perpendicular-offset
    label for a Segment/Ray/Line-family def, or None for a def kind this
    scheme doesn't apply to (e.g. an arc, which needs radial-offset
    placement instead — see arc_label_point()).

    Reuses whatever the drawing code already resolved for that def kind
    (a Ray's own a/b, or line_endpoints()'s real-or-synthetic pair for a
    Line) so the label sits on the same line the renderer actually draws."""
    stmt = stmt_by_id[obj_id]
    if isinstance(stmt, (ir.Segment, ir.Ray)):
        return stmt.a, stmt.b
    if isinstance(stmt, (
        ir.LineThrough, ir.LineParallelThrough, ir.LinePerpendicularThrough,
        ir.LineAngleBisector, ir.LineTangent,
    )):
        return line_endpoints(obj_id, stmt_by_id, helpers)
    return None


def arc_label_anchor(
    arc_id: str, sym: "SymTable", pos: float = 0.5
) -> tuple[float, float, float, float, float]:
    """Return (cx, cy, px, py, r) in geometry space: the arc's center, the
    point on the arc itself at fractional position ``pos`` along its CCW
    sweep (radius r, no offset yet, ``pos=0.5`` the default midpoint), and
    that radius (so callers can size their offset proportionally to the
    arc — a fixed absolute offset would look right on one diagram's
    coordinate scale and wrong on another's).

    Callers apply their own backend-space offset along the center->point
    direction — geometry-space and screen-space units differ (and screen
    space may flip the y axis), so the offset can't be baked in here.
    Mirrors how LabelAngle places its text beyond the angle-mark arc."""
    cx, cy, r, start_deg, end_deg, _sx, _sy = arc_params(arc_id, sym)
    anchor_rad = math.radians(start_deg + pos * (end_deg - start_deg))
    return cx, cy, cx + r * math.cos(anchor_rad), cy + r * math.sin(anchor_rad), r


def elliptical_arc_label_anchor(
    arc_id: str, sym: "SymTable", pos: float = 0.5
) -> tuple[float, float, float, float, float]:
    """The elliptical-arc analogue of arc_label_anchor(), for a compiled
    EllipticalArc/EllipticalSector. Returns (cx, cy, px, py, r): the arc's
    center, the point on the arc itself at fractional position ``pos`` along
    its CCW sweep, and the center-to-point distance at that position (not a
    true radius -- an ellipse's boundary distance from its center varies by
    angle -- but usable the same way arc_label_anchor()'s r is, to scale a
    caller's offset proportionally to the curve's local size).

    An ellipse's true outward normal at a boundary point generally isn't the
    same as the center-to-point direction (they only coincide at the four
    axis vertices) -- computing the exact normal would need the ellipse's
    gradient at that point. This accepts the same center-to-point
    approximation arc_label_anchor()'s own docstring already accepts for the
    circular case, rather than adding an exact calculation only this one
    caller would need.

    Cannot delegate to arc_label_anchor(): that function's anchor point is
    cx + r*cos/sin(angle) for a single radius r, which is only correct when
    hradius == vradius. This instead evaluates the ellipse's own parametric
    form (hr*cos(t), vr*sin(t)) at the interpolated parametric angle t that
    elliptical_arc_params() recovers."""
    cx, cy, hr, vr, start_deg, end_deg, _sx, _sy = elliptical_arc_params(arc_id, sym)
    t = math.radians(start_deg + pos * (end_deg - start_deg))
    px = cx + hr * math.cos(t)
    py = cy + vr * math.sin(t)
    r = math.hypot(px - cx, py - cy)
    return cx, cy, px, py, r


def label_segment_arc_anchor(
    seg_id: str,
    stmt_by_id: dict,
    sym: "SymTable",
    pos: "float | None",
) -> "tuple[float, float, float, float, float] | None":
    """Return the (cx, cy, px, py, r) label anchor for seg_id if it names a
    circular or elliptical arc/sector def, honoring an explicit
    LabelSegment.pos (None defaults to the midpoint, 0.5) -- the arc-family
    counterpart of line_label_endpoints(). Returns None for any other def
    kind (the caller should fall back to line_label_endpoints() instead).

    Shared by to_svg.py and to_tikz.py so their LabelSegment dispatch agrees
    on exactly which def kinds route to radial-offset placement instead of
    the straight-line midpoint+perpendicular-offset scheme -- previously
    each backend re-implemented (and under-implemented) this check itself,
    each only recognizing ArcCenterStartEnd and silently dropping the label
    for a sector or an elliptical arc/sector."""
    stmt = stmt_by_id[seg_id]
    p = 0.5 if pos is None else pos
    if isinstance(stmt, (ir.ArcCenterStartEnd, ir.SectorCenterStartEnd)):
        return arc_label_anchor(seg_id, sym, pos=p)
    if isinstance(stmt, (ir.EllipticalArcCenterStartEnd, ir.EllipticalSectorCenterStartEnd)):
        return elliptical_arc_label_anchor(seg_id, sym, pos=p)
    return None


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
        case ir.CircleTangentAt():
            return f"_cc_{circle_id}", f"_rt_{circle_id}"
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


def screen_ellipse(
    hr: float, vr: float, rotation: float, sx: float, sy: float,
) -> tuple[float, float, float]:
    """Screen image of a tilted ellipse under unequal axis scales:
    ``(rx, ry, phi_deg)`` with ``rx >= ry`` and ``phi_deg`` the SVG
    ``rotate()`` angle (degrees, y down) of the ``rx`` axis. ``rotation`` is
    radians counterclockwise in construction space (y up).

    The curve is ``M (cos t, sin t)`` for ``M = diag(sx, -sy) . R(rotation) .
    diag(hr, vr)`` (the minus flips y for the page). Its principal axes are
    the singular values and the left singular direction of the 2x2 ``M``,
    taken in closed form from the sum and difference of its entries."""
    cr, sr = math.cos(rotation), math.sin(rotation)
    a, b = sx * hr * cr, -sx * vr * sr
    c, d = -sy * hr * sr, -sy * vr * cr
    e, f, g, h = (a + d) / 2, (a - d) / 2, (c + b) / 2, (c - b) / 2
    q, r = math.hypot(e, h), math.hypot(f, g)
    phi = (math.atan2(h, e) + math.atan2(g, f)) / 2
    # A negative minor singular value only records a reflection (the y flip).
    return q + r, abs(q - r), math.degrees(phi)


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


def elliptical_arc_params(
    arc_id: str,
    sym: "SymTable",
) -> tuple[float, float, float, float, float, float, float, float]:
    """Return (cx, cy, hr, vr, start_deg, end_deg, sx, sy) for the given
    elliptical arc id.

    Mirrors arc_params() exactly, except recovering the parametric angle t
    via atan2((y-cy)/vr, (x-cx)/hr) instead of plain atan2(y-cy, x-cx) --
    the plain formula is only correct when hr == vr (a circle); for a true
    ellipse it recovers the wrong angle, silently corrupting the rendered
    endpoint.

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
    hr = sympy_to_float(arc.hradius)
    vr = sympy_to_float(arc.vradius)
    frame = EllipseFrame(cx, cy, hr, vr)
    s_deg = math.degrees(frame.param_of(sx, sy)) % 360.0
    e_deg = math.degrees(frame.param_of(ex, ey)) % 360.0
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
    return (cx, cy, hr, vr, s_deg, e_deg, sx, sy)


# ---------------------------------------------------------------------------
# Bounds computation
# ---------------------------------------------------------------------------

def drawn_object_ids(diagram: ir.DiagramIR) -> set[str]:
    """Ids of the objects a render op draws, fills or marks."""
    ids: set[str] = set()
    for op in diagram.render:
        if isinstance(op, ir.Draw):
            ids.add(op.obj)
        elif isinstance(op, ir.Fill):
            ids.add(op.obj)
            ids.update(op.holes)
        elif isinstance(op, ir.MarkArcs):
            ids.update(op.arcs)
        elif isinstance(op, ir.LabelAlongArc):
            ids.add(op.arc)
    return ids


def helpers_for_bounds(
    helpers: dict[str, tuple[float, float]], drawn: Optional[set[str]],
) -> dict[str, tuple[float, float]]:
    """Drop a circle's synthesized ``_rt_``/``_cc_`` helper points when nothing
    draws that circle, so an anchor-only circle does not move the canvas."""
    if drawn is None:
        return helpers
    return {
        k: v for k, v in helpers.items()
        if not (k.startswith(("_rt_", "_cc_")) and k[4:] not in drawn)
    }


def _arc_extent(
    cx: float, cy: float, hr: float, vr: float,
    start_deg: float, end_deg: float,
) -> tuple[float, float, float, float]:
    """Bounding box of the CCW sweep start_deg..end_deg (end > start) of an
    axis-aligned ellipse given in parametric angles: both endpoints plus each
    axis extreme (0/90/180/270) inside the sweep."""
    angles = [start_deg, end_deg]
    k = math.ceil(start_deg / 90.0)
    while k * 90.0 <= end_deg:
        angles.append(k * 90.0)
        k += 1
    xs = [cx + hr * math.cos(math.radians(t)) for t in angles]
    ys = [cy + vr * math.sin(math.radians(t)) for t in angles]
    return min(xs), max(xs), min(ys), max(ys)


def expand_bounds_for_geometry(
    xmin: float, xmax: float, ymin: float, ymax: float,
    sym: SymTable,
    drawn: Optional[set[str]] = None,
) -> tuple[float, float, float, float]:
    """Expand (xmin, xmax, ymin, ymax) to include circles, ellipses, and arcs.

    Used when a Canvas is already established and we need to ensure geometry
    that extends outside the point-based bounds (e.g. a large circle) is not
    clipped. An arc or sector contributes only its own swept extent, not its
    full circle. When ``drawn`` (ids a render op references) is given, a circle
    or ellipse nobody draws (e.g. one that only anchors a point) is ignored;
    ``None`` counts every object as drawn.
    """
    def grow(x0: float, x1: float, y0: float, y1: float) -> None:
        nonlocal xmin, xmax, ymin, ymax
        if x0 < xmin:
            xmin = x0 - BOUNDS_PADDING
        if x1 > xmax:
            xmax = x1 + BOUNDS_PADDING
        if y0 < ymin:
            ymin = y0 - BOUNDS_PADDING
        if y1 > ymax:
            ymax = y1 + BOUNDS_PADDING

    for oid, obj in sym.items():
        if drawn is not None and oid not in drawn:
            continue
        if isinstance(obj, spg.Ellipse):  # covers Circle
            cx, cy = sympy_to_float(obj.center.x), sympy_to_float(obj.center.y)
            a = sympy_to_float(obj.hradius)
            b = sympy_to_float(obj.vradius)
            grow(cx - a, cx + a, cy - b, cy + b)
        elif isinstance(obj, RotatedEllipse):
            cx, cy = sympy_to_float(obj.center.x), sympy_to_float(obj.center.y)
            wx, wy = obj.half_widths()
            grow(cx - wx, cx + wx, cy - wy, cy + wy)
        elif isinstance(obj, (Arc, Sector)):
            cx, cy, r, s_deg, e_deg, _, _ = arc_params(oid, sym)
            grow(*_arc_extent(cx, cy, r, r, s_deg, e_deg))
        elif isinstance(obj, (EllipticalArc, EllipticalSector)):
            cx, cy, hr, vr, s_deg, e_deg, _, _ = elliptical_arc_params(oid, sym)
            grow(*_arc_extent(cx, cy, hr, vr, s_deg, e_deg))
    return xmin, xmax, ymin, ymax


def compute_bounds(
    coords: dict[str, tuple[float, float]],
    helpers: dict[str, tuple[float, float]],
    sym: SymTable,
    drawn: Optional[set[str]] = None,
) -> tuple[float, float, float, float]:
    """Compute tight (xmin, xmax, ymin, ymax) from geometry, with padding."""
    all_pts = list(coords.values()) + list(helpers_for_bounds(helpers, drawn).values())
    if not all_pts:
        return expand_bounds_for_geometry(-5.0, 5.0, -5.0, 5.0, sym, drawn)
    xs, ys = zip(*all_pts)
    xmin = min(xs) - BOUNDS_PADDING
    xmax = max(xs) + BOUNDS_PADDING
    ymin = min(ys) - BOUNDS_PADDING
    ymax = max(ys) + BOUNDS_PADDING
    return expand_bounds_for_geometry(xmin, xmax, ymin, ymax, sym, drawn)


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


_TICK_COUNT_RE = re.compile(r"^tick(\d+)$")
_PARALLEL_COUNT_RE = re.compile(r"^parallel(\d+)$")

# Half-length / spacing (construction units) for to_tikz.py's raw-drawn
# segment AND arc tick marks (MarkSegments.ticks / MarkArcs, and any group
# index beyond the mark-symbol palette). Shared between the two so a tick
# on a segment and a tick on an arc marked with the same group are the same
# visual size. Not used by to_svg.py, which works in pixel space
# post-projection (see _TICK_LEN/spacing in to_svg.py).
SEG_TICK_HALF_LENGTH = 0.12
SEG_TICK_SPACING = 0.09
# Parallel chevron (TikZ, construction units); the SVG renderer's _CHEVRON_*
# pixel constants are these x50, like SEG_TICK_HALF_LENGTH vs _TICK_LEN.
SEG_CHEVRON_TIP = 0.10
SEG_CHEVRON_BACK = 0.12
SEG_CHEVRON_WING = 0.08
SEG_CHEVRON_SPACING = 0.08


def resolve_mark_group_indices(seg_groups: list[str], name_re: "re.Pattern[str]") -> dict[str, int]:
    """Assign a 1-based count to each mark group, in first-encounter order.

    A group whose name matches `name_re` (e.g. "tick3", "parallel2") with a
    captured digit gets that digit directly; every other group gets the next
    number in encounter order. Shared by to_svg.py and to_tikz.py so a
    diagram's MarkSegments groups resolve to the same counts on both
    backends — a group named by convention no longer silently falls back to
    encounter order on one backend while honoring its name on the other.
    """
    indices: dict[str, int] = {}
    encounter_idx = 0
    for g in seg_groups:
        m = name_re.match(g)
        if m:
            indices[g] = max(int(m.group(1)), 1)
        else:
            encounter_idx += 1
            indices[g] = encounter_idx
    return indices


def tick_mark_segments(
    a: "tuple[float, float]",
    b: "tuple[float, float]",
    n_ticks: int,
    half_length: float,
    spacing: float,
) -> "list[tuple[tuple[float, float], tuple[float, float]]]":
    """Return n_ticks short perpendicular strokes centered on segment a-b's
    midpoint, evenly spaced along a-b. Each element is the stroke's own
    ((x1, y1), (x2, y2)) endpoints, in whatever coordinate space a/b are
    given in (pixels for to_svg.py, construction units for to_tikz.py).
    Has no upper bound on n_ticks — unlike the fixed-size mark-symbol
    palettes both renderers use for the group-derived (non-explicit) count.
    """
    ax, ay = a
    bx, by = b
    mx, my = (ax + bx) / 2, (ay + by) / 2
    dx, dy = bx - ax, by - ay
    mag = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / mag, dx / mag
    along_x, along_y = dx / mag, dy / mag
    strokes: "list[tuple[tuple[float, float], tuple[float, float]]]" = []
    for i in range(n_ticks):
        offset = (i - (n_ticks - 1) / 2) * spacing
        tx = mx + along_x * offset
        ty = my + along_y * offset
        strokes.append((
            (tx - nx * half_length, ty - ny * half_length),
            (tx + nx * half_length, ty + ny * half_length),
        ))
    return strokes


def chevron_mark_strokes(
    a: "tuple[float, float]",
    b: "tuple[float, float]",
    n_chevrons: int,
    tip: float,
    back: float,
    wing: float,
    spacing: float,
) -> "list[tuple[tuple[float, float], tuple[float, float]]]":
    """Return the strokes of n_chevrons ``>`` marks at segment a-b's midpoint,
    pointing a -> b, as ((wing_x, wing_y), (tip_x, tip_y)) pairs (two per
    chevron), in whatever coordinate space a/b are given in. ``tip`` is how
    far the tip sits ahead of the chevron's center, ``back`` how far the wings
    sit behind the tip, ``wing`` their half-width, ``spacing`` the gap between
    chevrons. Swap a and b to reverse the direction."""
    ax, ay = a
    bx, by = b
    mx, my = (ax + bx) / 2, (ay + by) / 2
    dx, dy = bx - ax, by - ay
    mag = math.hypot(dx, dy) or 1.0
    along_x, along_y = dx / mag, dy / mag
    perp_x, perp_y = -dy / mag, dx / mag
    strokes: "list[tuple[tuple[float, float], tuple[float, float]]]" = []
    for i in range(n_chevrons):
        offset = (i - (n_chevrons - 1) / 2) * spacing
        tip_x = mx + along_x * (offset + tip)
        tip_y = my + along_y * (offset + tip)
        for sign in (1, -1):
            strokes.append((
                (tip_x - along_x * back + sign * perp_x * wing,
                 tip_y - along_y * back + sign * perp_y * wing),
                (tip_x, tip_y),
            ))
    return strokes


def tick_mark_arcs(
    cx: float,
    cy: float,
    r: float,
    start_deg: float,
    end_deg: float,
    n_ticks: int,
    half_length: float,
    spacing: float,
) -> "list[tuple[tuple[float, float], tuple[float, float]]]":
    """Return n_ticks short RADIAL strokes straddling a circular arc,
    centered on the arc's own midpoint angle and evenly spaced along it by
    arc length. Each element is the stroke's own ((x1, y1), (x2, y2))
    endpoints, in whatever coordinate space cx/cy/r/half_length/spacing are
    given in (pixels for to_svg.py, construction units for to_tikz.py).

    The arc-space counterpart of tick_mark_segments(): both backends call
    this in GEOMETRY space and project the result themselves — to_svg.py's
    projection is a uniform scale + y-flip (a similarity transform), so a
    radial stroke stays radial and a pixel-space length is just the
    geometry-space length times scale.

    ``spacing`` is an ARC LENGTH, converted to a central angle via
    ``dtheta = spacing / r``, so two arcs of different radii marked with the
    same count get strokes the same visual distance apart rather than the
    same angle apart.

    Like tick_mark_segments(), this does not clamp overrun past the arc's
    own endpoints — a large n_ticks on a short sweep will place its
    outermost strokes beyond where the arc itself ends. It does clamp the
    inner radius at 0 so a half_length larger than r can't cross the center.
    """
    if n_ticks < 1 or r <= 0:
        return []
    mid_rad = math.radians((start_deg + end_deg) / 2.0)
    dtheta = spacing / r
    r_in = max(r - half_length, 0.0)
    r_out = r + half_length
    strokes: "list[tuple[tuple[float, float], tuple[float, float]]]" = []
    for i in range(n_ticks):
        theta = mid_rad + (i - (n_ticks - 1) / 2) * dtheta
        ux, uy = math.cos(theta), math.sin(theta)
        strokes.append((
            (cx + r_in * ux, cy + r_in * uy),
            (cx + r_out * ux, cy + r_out * uy),
        ))
    return strokes


# Definition kinds MarkArcs / LabelAlongArc accept (circular and elliptical
# arcs and sectors), shared so both backends agree on what is an arc.
ARC_STMT_TYPES = (
    ir.ArcCenterStartEnd,
    ir.SectorCenterStartEnd,
    ir.EllipticalArcCenterStartEnd,
    ir.EllipticalSectorCenterStartEnd,
)


# ---------------------------------------------------------------------------
# Elliptical-arc curve walking (tick marks and text along the curve)
# ---------------------------------------------------------------------------
# An axis-aligned ellipse is (cx + hr cos t, cy + vr sin t) in PARAMETRIC angle
# t. Its outward normal at t is (vr cos t, hr sin t) normalized -- not the
# radial direction, which only matches at the four axis vertices -- and arc
# length is not proportional to t. These helpers walk the curve (or its
# parallel offset curve) by true arc length, so tick spacing and glyph spacing
# stay even however unevenly the curve bends.

def _ellipse_normal(hr: float, vr: float, t: float) -> "tuple[float, float]":
    nx, ny = vr * math.cos(t), hr * math.sin(t)
    mag = math.hypot(nx, ny)
    return nx / mag, ny / mag


def _offset_curve_velocity(hr: float, vr: float, t: float, offset: float) -> "tuple[float, float]":
    """d/dt of P(t) + offset * n(t), where P is the ellipse point and n its
    unit outward normal (offset > 0 outside, < 0 inside)."""
    ux, uy = vr * math.cos(t), hr * math.sin(t)
    dux, duy = -vr * math.sin(t), hr * math.cos(t)
    length = math.hypot(ux, uy)
    dot = ux * dux + uy * duy
    dnx = dux / length - ux * dot / length ** 3
    dny = duy / length - uy * dot / length ** 3
    return (-hr * math.sin(t) + offset * dnx, vr * math.cos(t) + offset * dny)


def _offset_curve_length(hr: float, vr: float, offset: float, t0: float, t1: float) -> float:
    """Signed arc length of the offset curve from parameter t0 to t1
    (composite Simpson; the integrand is smooth and periodic-analytic)."""
    if t0 == t1:
        return 0.0
    n = 2 * (32 + int(abs(t1 - t0) * 48))
    h = (t1 - t0) / n
    total = 0.0
    for i in range(n + 1):
        vx, vy = _offset_curve_velocity(hr, vr, t0 + i * h, offset)
        w = 1 if i in (0, n) else (4 if i % 2 else 2)
        total += w * math.hypot(vx, vy)
    return total * abs(h) / 3.0 * (1.0 if t1 > t0 else -1.0)


def _offset_curve_param_at(hr: float, vr: float, offset: float, t0: float, dist: float) -> float:
    """Parameter t whose offset-curve arc length from t0 equals the signed
    distance `dist` (positive = toward increasing t). Newton iteration on the
    monotone arc-length function."""
    if dist == 0.0:
        return t0
    vx, vy = _offset_curve_velocity(hr, vr, t0, offset)
    t = t0 + dist / (math.hypot(vx, vy) or 1.0)
    for _ in range(60):
        err = _offset_curve_length(hr, vr, offset, t0, t) - dist
        vx, vy = _offset_curve_velocity(hr, vr, t, offset)
        speed = math.hypot(vx, vy) or 1e-12
        t -= err / speed
        if abs(err) < 1e-12 * max(1.0, abs(dist)):
            break
    return t


def tick_mark_elliptical_arcs(
    cx: float,
    cy: float,
    hr: float,
    vr: float,
    start_deg: float,
    end_deg: float,
    n_ticks: int,
    half_length: float,
    spacing: float,
) -> "list[tuple[tuple[float, float], tuple[float, float]]]":
    """The elliptical counterpart of tick_mark_arcs(): n_ticks short strokes
    straddling an axis-aligned elliptical arc, centered on its parametric
    midpoint and evenly spaced along it by ARC LENGTH (``spacing``, as for a
    circular arc), each oriented along the ellipse's own normal at its
    placement point. ``start_deg``/``end_deg`` are parametric angles as
    returned by elliptical_arc_params(). Same coordinate-space contract as
    tick_mark_arcs()."""
    if n_ticks < 1 or hr <= 0 or vr <= 0:
        return []
    mid = math.radians((start_deg + end_deg) / 2.0)
    strokes: "list[tuple[tuple[float, float], tuple[float, float]]]" = []
    for i in range(n_ticks):
        t = _offset_curve_param_at(hr, vr, 0.0, mid, (i - (n_ticks - 1) / 2) * spacing)
        nx, ny = _ellipse_normal(hr, vr, t)
        px, py = cx + hr * math.cos(t), cy + vr * math.sin(t)
        strokes.append((
            (px - nx * half_length, py - ny * half_length),
            (px + nx * half_length, py + ny * half_length),
        ))
    return strokes


# Uniform per-character text-advance fraction of the em size, used by
# arc_text_glyphs() below. It is the flat rule to_svg.py's
# _estimate_text_width() falls back to when the bundled font cannot be
# loaded; the SVG estimate is otherwise measured from the font, while arc
# text keeps this uniform advance (TikZ shares it and has no font metrics),
# and its per-glyph boxes are built from these same advances.
TEXT_ADVANCE_EM = 0.65

# Nominal em size in construction units for to_tikz.py's arc text. TikZ has
# no font metrics available at IR-emission time. \tkzInit maps one
# construction unit to 1cm and the default document font is ~10pt (~0.35cm),
# so one em is about 0.35 construction units regardless of the diagram's own
# xmin/xmax range (a wider range makes the picture physically bigger, not
# the font smaller).
TIKZ_TEXT_EM = 0.35


def arc_text_glyphs(text: str, em: float) -> "list[tuple[str, float]]":
    """Split *text* into per-glyph (character, advance) pairs, advances in
    whatever length unit *em* is given in (SVG px, or construction units).

    Uses a uniform TEXT_ADVANCE_EM advance per character after the same
    normalization as to_svg.py's _estimate_text_width() (strip an outer
    $...$, collapse a \\command to one glyph, drop {}_^). The SVG label
    estimate is measured from the bundled font, so the sum here equals it
    only on the estimator's flat fallback path.

    The \\command rule is defensive only: arc_text_is_layoutable() already
    routes every string containing one to the single-label fallback, so this
    function should never actually see a backslash in practice.

    Whitespace characters are kept (with their advance) so the cursor still
    moves correctly across a run with spaces — callers should skip emitting
    a visible glyph for them, not skip them here.
    """
    t = text.strip()
    if t.startswith("$") and t.endswith("$"):
        t = t[1:-1]
    t = re.sub(r"\\[a-zA-Z]+", "X", t)
    t = re.sub(r"[{}_^]", "", t)
    advance = em * TEXT_ADVANCE_EM
    return [(ch, advance) for ch in t]


def arc_text_is_layoutable(text: str) -> bool:
    """True if *text* can be laid out glyph-by-glyph along an arc; False if
    the caller should fall back to a single unrotated label at the arc
    anchor instead.

    False for two classes of string:
      * anything label_needs_mathtext() routes to the monolithic mathtext
        vector path — mathtext_svg.MathGlyph carries one ``d`` path string
        and whole-string metrics, so there are no per-glyph advances to lay
        out at all, and a fraction/radical is a 2-D box that rotating it
        per sub-glyph would mangle anyway; and
      * anything carrying a sub/superscript, which arc_text_glyphs() would
        otherwise flatten ("P_1" -> "P1"). Silently dropping a subscript is
        worse than falling back to a straight label.

    Shared by both backends so they agree on exactly which strings curve —
    a per-backend gate would make the same IR render differently in SVG and
    TikZ, which is the one failure mode this op cannot afford.
    """
    # Function-local: mathtext_svg imports matplotlib at module scope, and
    # to_tikz.py's import path is otherwise matplotlib-free.
    from .mathtext_svg import label_needs_mathtext

    if "_" in text or "^" in text:
        return False
    return not label_needs_mathtext(text)


def arc_text_glyph_layout(
    cx: float,
    cy: float,
    r: float,
    start_deg: float,
    end_deg: float,
    advances: "list[float]",
    pos: float = 0.5,
    offset: float = 0.0,
    side: str = "outside",
    flip: "bool | None" = None,
) -> "list[tuple[float, float, float]]":
    """Lay a string out along a circular arc, one glyph at a time.

    Returns one (x, y, rotation_deg) per entry in *advances*, all in
    GEOMETRY space: (x, y) is the glyph's own center (callers anchor
    middle/central on it and rotate about it), and rotation_deg is a
    math-CCW angle. to_svg.py must NEGATE it before use — its gy() is
    y-flipped, so a screen-CCW rotation is an SVG rotate() of the opposite
    sign. to_tikz.py uses it as-is (TikZ's y axis is not flipped).

    - ``pos`` in [0, 1] picks the anchor angle along the arc's CCW sweep
      that the string is CENTERED on (0.5 = the midpoint arc_label_anchor()
      uses). Not clamped away from the endpoints: pos=0 centers the string
      on the arc's start point, so half of it overhangs before the arc
      begins.
    - ``side`` = "outside" puts the baseline at radius r + offset, "inside"
      at r - offset (clamped above 0).
    - ``flip`` = None auto-derives: glyph tops point away from the center on
      the upper half of the circle and toward it on the lower half, so text
      at the bottom of a circle reads right-side up instead of upside down.
      One decision for the whole string, taken at the anchor angle — a
      per-glyph decision would invert a word mid-way. True/False force tops
      inward/outward regardless of position (e.g. for a sweep crossing the
      horizontal, where no single auto choice is right everywhere, or for
      deliberate seal-style text).
    """
    if not advances:
        return []
    baseline_r = (r + offset) if side == "outside" else max(r - offset, 1e-9)
    anchor = math.radians(start_deg + pos * (end_deg - start_deg))
    if flip is None:
        # Upper half -> glyph tops point outward; lower half -> inward
        # (upright either way).
        up_sign = 1.0 if math.sin(anchor) >= 0.0 else -1.0
    else:
        up_sign = -1.0 if flip else 1.0
    # Reading direction is opposite the "up" direction: with tops pointing
    # outward, text reads clockwise (decreasing theta).
    step = -up_sign
    # Angular width is computed AT THE BASELINE radius, not at r — a large
    # offset would otherwise over-space the glyphs relative to how far apart
    # they actually render.
    total_rad = sum(advances) / baseline_r
    cursor = anchor - step * total_rad / 2.0
    out: "list[tuple[float, float, float]]" = []
    for adv in advances:
        dt = adv / baseline_r
        theta = cursor + step * dt / 2.0
        rot = math.degrees(theta) + (-90.0 if up_sign > 0 else 90.0)
        rot = (rot + 180.0) % 360.0 - 180.0  # normalize to (-180, 180]
        out.append((
            cx + baseline_r * math.cos(theta),
            cy + baseline_r * math.sin(theta),
            rot,
        ))
        cursor += step * dt
    return out


# An inside text baseline may sit at most this fraction of the tightest radius
# of curvature from the ellipse, keeping the offset curve strictly regular.
_INSIDE_OFFSET_FRACTION = 0.8


def _min_curvature_radius(hr: float, vr: float, anchor: float, text_length: float) -> float:
    """Smallest radius of curvature, speed**3 / (hr * vr), over the parameters
    a string of ``text_length`` centered at ``anchor`` can touch. The window is
    found by walking the ellipse itself that far either side of the anchor,
    with 25% slack because an inside baseline is shorter than the ellipse
    (so the same string reaches further along it). The four axis vertices,
    where the extremes sit, are included exactly rather than by sampling."""
    reach = 0.625 * text_length
    lo = _offset_curve_param_at(hr, vr, 0.0, anchor, -reach)
    hi = _offset_curve_param_at(hr, vr, 0.0, anchor, reach)
    ts = [lo + (hi - lo) * i / 256 for i in range(257)]
    ts += [k * math.pi / 2 for k in range(math.ceil(lo / (math.pi / 2)), math.floor(hi / (math.pi / 2)) + 1)]
    return min(math.hypot(-hr * math.sin(t), vr * math.cos(t)) ** 3 / (hr * vr) for t in ts)


def elliptical_arc_text_glyph_layout(
    cx: float,
    cy: float,
    hr: float,
    vr: float,
    start_deg: float,
    end_deg: float,
    advances: "list[float]",
    pos: float = 0.5,
    offset: float = 0.0,
    side: str = "outside",
    flip: "bool | None" = None,
) -> "list[tuple[float, float, float]]":
    """arc_text_glyph_layout() for an axis-aligned elliptical arc.

    Same contract and conventions (returned (x, y, rotation_deg) per advance in
    geometry space, ``pos``, ``side``, ``flip`` and the upright rule), with
    ``start_deg``/``end_deg`` parametric angles. The glyph centers lie on the
    parallel curve ``offset`` away from the ellipse along its own normal, and
    each advance is measured as arc length along THAT curve, so uneven
    curvature never squeezes or stretches the glyph spacing. Rotation is the
    reading direction of the curve's local tangent. An inside offset is
    capped at a fraction of the smallest radius of curvature over the span the
    text covers (see _min_curvature_radius), so the inside offset curve never
    reaches a cusp and reverses its tangent mid-word -- the analogue of the
    circular clamp at the center.
    """
    if not advances:
        return []
    anchor = math.radians(start_deg + pos * (end_deg - start_deg))
    total = sum(advances)
    if side == "outside":
        signed = offset
    else:
        signed = -min(offset, _INSIDE_OFFSET_FRACTION * _min_curvature_radius(
            hr, vr, anchor, total))
    if flip is None:
        up_sign = 1.0 if _ellipse_normal(hr, vr, anchor)[1] >= 0.0 else -1.0
    else:
        up_sign = -1.0 if flip else 1.0
    step = -up_sign
    cursor = -total / 2.0
    out: "list[tuple[float, float, float]]" = []
    for adv in advances:
        dist = step * (cursor + adv / 2.0)
        t = _offset_curve_param_at(hr, vr, signed, anchor, dist)
        nx, ny = _ellipse_normal(hr, vr, t)
        vx, vy = _offset_curve_velocity(hr, vr, t, signed)
        rot = math.degrees(math.atan2(step * vy, step * vx))
        out.append((
            cx + hr * math.cos(t) + signed * nx,
            cy + vr * math.sin(t) + signed * ny,
            rot,
        ))
        cursor += adv
    return out


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
# DrawBrace geometry (shared by to_svg.py and to_tikz.py)
# ---------------------------------------------------------------------------

BRACE_WIDTH = 0.3       # perpendicular distance from the p1-p2 line to the brace's tip
_BRACE_CURVATURE = 0.6  # 0-1 shape parameter; see brace_quadratic_points docstring

_BRACE_DIRECTION_VECTORS: dict[str, tuple[float, float]] = {
    "up": (0.0, 1.0), "down": (0.0, -1.0), "left": (-1.0, 0.0), "right": (1.0, 0.0),
}


def brace_quadratic_points(
    p1: "tuple[float, float]",
    p2: "tuple[float, float]",
    direction: str,
    width: float = BRACE_WIDTH,
    curvature: float = _BRACE_CURVATURE,
) -> "dict[str, tuple[float, float]]":
    """The key points of a standard two-hump curly-brace curve from p1 to p2.

    Returns a dict with:
      - "start"/"end": p1/p2 unchanged.
      - "tip": the brace's pointed center, offset `width` from the p1-p2
        line toward `direction`.
      - "near1"/"near2": the brace's two shoulder points, at the 1/4 and 3/4
        marks along p1-p2, offset partway toward the tip.
      - "far1"/"far2": quadratic-Bezier control points near p1/p2 — only
        needed by to_svg.py's exact cubic-Bezier conversion; to_tikz.py
        ignores them and lets `plot[smooth]` interpolate the anchor points
        directly.

    Adapted from the well-known SVG curly-brace construction (e.g.
    alexhornbake's "svg-curly-brace" gist): two mirror-image quadratic
    curves, p1 -> near1 -> tip and p2 -> near2 -> tip, each with its control
    point reflected at the shoulder so the curve stays smooth (C1-continuous)
    there.

    `direction` selects which side of the p1-p2 line the brace bulges
    toward, as an absolute canvas direction (independent of p1-p2's own
    orientation) — matching `DrawBrace.direction`'s Literal["left", "right",
    "up", "down"]. The offset actually used is p1-p2's own perpendicular,
    picked to have a positive component along `direction`; if p1-p2 runs
    parallel to `direction` (so neither perpendicular candidate has any
    component along it — e.g. a vertical segment with direction="up"), the
    bulge falls back to `direction` itself rather than leaving the brace
    flat.
    """
    if direction not in _BRACE_DIRECTION_VECTORS:
        raise ValueError(
            f"Unknown brace direction {direction!r}; expected one of "
            f"{sorted(_BRACE_DIRECTION_VECTORS)}"
        )

    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    seg_len = math.hypot(dx, dy)
    if seg_len < 1e-9:
        ux, uy = 1.0, 0.0
    else:
        ux, uy = dx / seg_len, dy / seg_len

    dirx, diry = _BRACE_DIRECTION_VECTORS[direction]
    n1 = (-uy, ux)
    n2 = (uy, -ux)
    nx, ny = n1 if (n1[0] * dirx + n1[1] * diry) >= (n2[0] * dirx + n2[1] * diry) else n2
    if abs(nx * dirx + ny * diry) < 1e-9:
        nx, ny = dirx, diry

    def along(t: float) -> "tuple[float, float]":
        return (x1 + t * dx, y1 + t * dy)

    def offset(point: "tuple[float, float]", amt: float) -> "tuple[float, float]":
        return (point[0] + nx * amt, point[1] + ny * amt)

    q = curvature
    return {
        "start": (x1, y1),
        "far1": offset(along(0.0), q * width),
        "near1": offset(along(0.25), (1 - q) * width),
        "tip": offset(along(0.5), width),
        "near2": offset(along(0.75), (1 - q) * width),
        "far2": offset(along(1.0), q * width),
        "end": (x2, y2),
    }


# ---------------------------------------------------------------------------
# Grid / axis tick math
# ---------------------------------------------------------------------------

def tick_values(lo: float, hi: float, step: float) -> list[float]:
    """Return tick positions between lo and hi at the given step, excluding 0
    and the endpoints themselves — axis arrowheads are drawn exactly at
    (lo, hi), so a tick there would overlap the arrowhead."""
    if step <= 0:
        return []
    start = math.ceil(lo / step)
    end = math.floor(hi / step)
    eps = max(abs(step) * 1e-9, 1e-9)
    values: list[float] = []
    for multiple in range(start, end + 1):
        value = multiple * step
        if abs(value) <= 1e-9:
            continue
        if abs(value - lo) <= eps or abs(value - hi) <= eps:
            continue
        values.append(value)
    return values


def round_down_to_step(value: float, step: float) -> float:
    return math.floor(value / step) * step


def round_up_to_step(value: float, step: float) -> float:
    return math.ceil(value / step) * step


# ---------------------------------------------------------------------------
# Entity manifest building
# ---------------------------------------------------------------------------

def _anonymous_render_op_position(
    op: Any, sym: "SymTable", stmt_by_id: dict[str, Any],
) -> "tuple[float, float] | None":
    """Best-effort canvas position for a manifest entry describing an
    anonymous (never variable-bound) render op — labels, fills, marks.
    Returns None for op kinds not yet handled here; such ops are simply
    omitted from the manifest rather than grounded incorrectly."""
    if isinstance(op, ir.LabelPoint):
        obj = sym.get(op.p)
        return (float(obj.x), float(obj.y)) if obj is not None else None
    if isinstance(op, ir.LabelFreeText):
        if op.at is not None:
            return (float(op.at[0]), float(op.at[1]))
        obj = sym.get(op.centroid_of)
        return centroid_of_obj(obj) if obj is not None else None
    if isinstance(op, ir.Fill):
        obj = sym.get(op.obj)
        return centroid_of_obj(obj) if obj is not None else None
    if isinstance(op, ir.LabelSegment):
        seg_stmt = stmt_by_id.get(op.seg)
        if isinstance(seg_stmt, (ir.Segment, ir.Ray)):
            a, b = sym.get(seg_stmt.a), sym.get(seg_stmt.b)
            if a is not None and b is not None:
                return (float((a.x + b.x) / 2), float((a.y + b.y) / 2))
            return None
        if seg_stmt is not None and seg_stmt.kind in (
            "arc_center_start_end", "sector_center_start_end",
        ):
            _, _, px, py, _ = arc_label_anchor(op.seg, sym)
            return (px, py)
        return None
    return None


def build_entity_manifest(
    diagram_ir: "ir.DiagramIR", sym: "SymTable", variable_ids: dict,
) -> dict:
    """Grounding manifest for edit requests: named entities (script variable
    name -> type + approx position) plus anonymous render ops (labels,
    marks, fills — which never bind to a variable) with a synthetic id.
    Named entities are grounded by name; anonymous ones only by
    type/position/text (see design doc, Component 2)."""
    # Effective view: a script variable may be bound to a synthesized id
    # (e.g. a solid's face), and a fill may target one.
    stmts_by_id = {stmt.id: stmt for stmt in effective_defs(diagram_ir)}

    named = []
    for name, obj_id in variable_ids.items():
        stmt = stmts_by_id.get(obj_id)
        obj = sym.get(obj_id)
        if stmt is None or obj is None:
            continue
        try:
            if isinstance(obj, spg.Point):
                position = (sympy_to_float(obj.x), sympy_to_float(obj.y))
            else:
                position = centroid_of_obj(obj)
        except Exception:
            # A silent `continue` here is exactly how Line/Segment/Ray went
            # unnoticed for as long as they did (see centroid_of_obj's
            # docstring, 2026-08-18): a swallowed type just vanishes from
            # "named" with zero signal that anything was skipped. Logging
            # doesn't fix the swallow — this entity is still excluded from
            # the manifest and thus invisible to check_edit_locality for
            # this call — but it means the NEXT unhandled type surfaces via
            # a log line instead of another multi-hour live debugging
            # session finding it by accident.
            logger.warning(
                "build_entity_manifest: could not compute a position for "
                "%r (variable %r, sympy type %s) — excluded from the "
                "entity manifest, invisible to check_edit_locality",
                obj_id, name, type(obj).__name__,
            )
            continue
        named.append({
            "name": name,
            "id": obj_id,
            "type": stmt.kind,
            "approx_position": [float(position[0]), float(position[1])],
        })

    anonymous = []
    for index, op in enumerate(diagram_ir.render):
        position = _anonymous_render_op_position(op, sym, stmts_by_id)
        if position is None:
            continue
        entry = {
            "synthetic_id": f"render_op_{index}",
            "type": op.kind,
            "approx_position": [float(position[0]), float(position[1])],
        }
        text = getattr(op, "text", None)
        if text is not None:
            entry["text"] = text
        anonymous.append(entry)

    return {"named": named, "anonymous": anonymous}


# ---------------------------------------------------------------------------
# Segment labels placed away from a point (registry ``label_away_from`` hook)
# ---------------------------------------------------------------------------

def away_normal(
    a: tuple[float, float], b: tuple[float, float], center: tuple[float, float],
) -> tuple[float, float] | None:
    """Unit normal of segment a-b pointing to the side AWAY from ``center``
    (all three in one coordinate frame). None when ``center`` lies on the
    segment's line (to within 1e-6 of the segment's length), e.g. a prism's
    space diagonal, which passes through the box center: there is no away side.

    The placement rule both renderers apply to a segment label when a
    registered kind's ``label_away_from`` hook names a point for the segment
    (a prism's center for a segment joining two of its corners: on a
    silhouette edge the away side is outside the drawn silhouette)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return None
    nx, ny = -dy / length, dx / length
    side = (center[0] - a[0]) * nx + (center[1] - a[1]) * ny
    if abs(side) <= 1e-6 * length:
        return None
    return (-nx, -ny) if side > 0 else (nx, ny)


# An away-placed label on an edge whose away normal has |ux| strictly between
# these bounds (the edge is neither near-horizontal nor near-vertical on the
# page) slides along the edge, see ``away_label_center``. Outside the bounds
# the box centered on the normal through the midpoint already touches the
# line near the midpoint, so the placement is left as it was.
AWAY_SLIDE_MIN_NORMAL_X = 0.3
AWAY_SLIDE_MAX_NORMAL_X = 0.95


def away_label_center(
    a: tuple[float, float], b: tuple[float, float], away: tuple[float, float],
    w: float, h: float, gap: float,
) -> tuple[float, float]:
    """Center of a ``w`` x ``h`` label box placed on the ``away`` side of the
    segment a-b (page coordinates, y down; ``away`` is ``away_normal``'s unit
    normal) with perpendicular clearance ``gap`` between box and line.

    Base placement: the center sits on the normal through the edge midpoint m,
    at ``clear = |ux|*w/2 + |uy|*h/2 + gap``. For a slanted edge (``AWAY_SLIDE_*``
    bounds on ``|ux|``) that leaves the box's nearest corner off the midpoint
    (a diagonal normal hangs a short steep edge's label past its lower end), so
    the center also slides along the edge, toward its upper endpoint (smaller
    y) d, by ``t = sgn(ux)*(w/2)*dx + sgn(uy)*(h/2)*dy`` (sgn(0) = +1). The
    nearest corner, center - (sgn(ux)*w/2, sgn(uy)*h/2), then lies on the line
    at m (n.d = 0, so the perpendicular clearance is unchanged)."""
    ux, uy = away
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    clear = abs(ux) * w / 2 + abs(uy) * h / 2 + gap
    cx, cy = mx + ux * clear, my + uy * clear
    if not AWAY_SLIDE_MIN_NORMAL_X < abs(ux) < AWAY_SLIDE_MAX_NORMAL_X:
        return cx, cy
    top, low = (a, b) if a[1] < b[1] else (b, a)
    length = math.hypot(top[0] - low[0], top[1] - low[1])
    if length == 0:
        return cx, cy
    dx, dy = (top[0] - low[0]) / length, (top[1] - low[1]) / length
    sgn_x = 1.0 if ux >= 0 else -1.0
    sgn_y = 1.0 if uy >= 0 else -1.0
    t = sgn_x * w / 2 * dx + sgn_y * h / 2 * dy
    return cx + dx * t, cy + dy * t
