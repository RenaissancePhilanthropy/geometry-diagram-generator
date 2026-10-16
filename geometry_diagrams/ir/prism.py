"""
Rectangular prisms: the projection, the compiled ``Prism`` object and the
prism definition's validation.

A projection is a linear map of the three prism axes to 2D vectors. Axis
order everywhere is (length, height, width), which is also the bit order of a
corner: corner (a, b, c) sits at ``origin + a*L*e_length + b*H*e_height +
c*W*e_width``. The viewer direction is the kernel of that map, signed so the
top face is visible; which faces are visible and which corner is hidden are
derived from it, never hard-coded per view.

All map constants are exact SymPy values (radicals, rationals), never floats:
corner coordinates feed later SymPy constructions, and floats would be turned
into huge rationals there.
"""
from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

import sympy as sp
import sympy.geometry as spg

from . import ir
from .errors import IRCompileError

AXES = ("length", "height", "width")
CORNER_BITS: tuple[tuple[int, int, int], ...] = tuple(itertools.product((0, 1), repeat=3))

# Oblique defaults, measured on the reference art (solids ticket 08): the
# receding depth edge runs at 45 degrees (fitted 44.2-45.1 across the four
# oblique figures) at half scale (0.50 on the one oblique figure with a stated
# depth, which the art draws proportionally), i.e. cabinet projection. Both
# are exact: cos 45 = sin 45 = sqrt(2)/2. The single place they are defined.
OBLIQUE_DEFAULT_ANGLE_DEG = 45
OBLIQUE_DEFAULT_SCALE = sp.Rational(1, 2)

_COS30 = sp.sqrt(3) / 2
_SIN30 = sp.Rational(1, 2)

Vec2 = tuple[sp.Expr, sp.Expr]


def _sign(value: sp.Expr) -> int:
    """Sign of an exact constant, robust to SymPy not deciding it symbolically."""
    v = float(sp.N(value, 30))
    if abs(v) < 1e-12:
        return 0
    return 1 if v > 0 else -1


@dataclass(frozen=True)
class Projection:
    """Images of the length, height and width axes (in that order)."""

    length: Vec2
    height: Vec2
    width: Vec2

    @property
    def axes(self) -> tuple[Vec2, Vec2, Vec2]:
        return (self.length, self.height, self.width)

    @property
    def viewer(self) -> tuple[sp.Expr, sp.Expr, sp.Expr]:
        """Direction toward the viewer in prism axes (length, height, width):
        the kernel of the map (cross product of its two rows), signed so the
        top face (height max) faces the viewer."""
        row_x = [v[0] for v in self.axes]
        row_y = [v[1] for v in self.axes]
        k = sp.Matrix(row_x).cross(sp.Matrix(row_y))
        if _sign(k[1]) == 0:
            raise ValueError("degenerate projection: the top face is seen edge-on")
        if _sign(k[1]) < 0:
            k = -k
        return (sp.simplify(k[0]), sp.simplify(k[1]), sp.simplify(k[2]))

    @property
    def visible_planes(self) -> frozenset[tuple[str, str]]:
        """Visible faces as (axis, "min" | "max"): a face is visible when its
        outward normal points toward the viewer. An axis whose faces are both
        seen edge-on contributes nothing."""
        planes = set()
        for axis, k in zip(AXES, self.viewer):
            s = _sign(k)
            if s:
                planes.add((axis, "max" if s > 0 else "min"))
        return frozenset(planes)

    @property
    def hidden_corner(self) -> tuple[int, int, int]:
        """Corner bits (length, height, width) of the corner farthest from the
        viewer: on each axis, the side whose face is hidden."""
        return tuple(1 if _sign(k) < 0 else 0 for k in self.viewer)  # type: ignore[return-value]

    def offset(self, length: Any, height: Any, width: Any) -> Vec2:
        x = length * self.length[0] + height * self.height[0] + width * self.width[0]
        y = length * self.length[1] + height * self.height[1] + width * self.width[1]
        return (x, y)


def projection_for(
    view: str = "oblique",
    side: str = "right",
    depth_angle: float | None = None,
    depth_scale: float | None = None,
) -> Projection:
    """The projection a prism's flat view fields select. Raises ValueError for
    an invalid combination (overrides with isometric, out-of-range values).

    oblique: length -> (1, 0), height -> (0, 1), width -> s*(cos a, sin a);
        side=left negates the x component of the width (depth) vector.
    isometric: right: length -> (cos30, -sin30), height -> (0, 1),
        width -> (cos30, sin30). left: length -> (cos30, sin30),
        width -> (-cos30, sin30); the left mapping is the only one with
        isometric axes, a vertical height, length running rightward along the
        front bottom edge, and a kernel that shows the front, left and top
        faces (negating only the depth x component, as oblique does, would
        make width the exact opposite of length: a degenerate map).
    """
    if side not in ("right", "left"):
        raise ValueError(f"side must be 'right' or 'left', got {side!r}")
    if view == "isometric":
        if depth_angle is not None or depth_scale is not None:
            raise ValueError(
                "depth_angle and depth_scale apply only to the oblique view; "
                "remove them for view='isometric' or use view='oblique'"
            )
        if side == "right":
            return Projection((_COS30, -_SIN30), (sp.S(0), sp.S(1)), (_COS30, _SIN30))
        return Projection((_COS30, _SIN30), (sp.S(0), sp.S(1)), (-_COS30, _SIN30))
    if view != "oblique":
        raise ValueError(f"view must be 'oblique' or 'isometric', got {view!r}")
    for name, value in (("depth_angle", depth_angle), ("depth_scale", depth_scale)):
        if value is not None and not math.isfinite(float(value)):
            raise ValueError(f"{name} must be a finite number, got {value}")
    angle = sp.Rational(str(OBLIQUE_DEFAULT_ANGLE_DEG if depth_angle is None else depth_angle))
    scale = OBLIQUE_DEFAULT_SCALE if depth_scale is None else sp.Rational(str(depth_scale))
    if not 0 < angle < 90:
        raise ValueError(f"depth_angle must be between 0 and 90 degrees (exclusive), got {depth_angle}")
    if not scale > 0:
        raise ValueError(f"depth_scale must be positive, got {depth_scale}")
    rad = sp.pi * angle / 180
    dx, dy = scale * sp.cos(rad), scale * sp.sin(rad)
    if side == "left":
        dx = -dx
    projection = Projection((sp.S(1), sp.S(0)), (sp.S(0), sp.S(1)), (dx, dy))
    try:
        projection.viewer  # evaluate eagerly: a degenerate view fails here, at compile
    except ValueError as e:
        raise ValueError(
            f"{e} (depth_scale={depth_scale}, depth_angle={depth_angle} make the depth axis "
            "vanish on screen); use a depth_scale of at least about 0.01 and a depth_angle "
            "of at least about 1 degree, or omit both for the defaults"
        ) from e
    return projection


Bits = tuple[int, int, int]
CornerPair = tuple[Bits, Bits]


class Prism:
    """Marker type for a rectangular prism in the symbol table (not a SymPy
    shape, like Arc/Sector). Holds the true dimensions, the projection and the
    eight projected corners keyed by (length, height, width) bits.

    It also holds the corner-segment index: every segment DEFINITION whose
    endpoints are two of this prism's corners, keyed by corner pair (low bits
    first), whoever created it (an authored segment with any id, the prism's
    own derived edges, a builder's helper segment). It is filled at compile
    from the definitions' endpoint ids (see ``index_corner_segment``), never by
    matching coordinates: two corners can project to the same 2D point. Queries
    and checks receive only the symbol table, so the index lives here."""

    __slots__ = (
        "length", "width", "height", "projection", "corners", "corner_ids",
        "corner_segments", "_segment_pairs", "_bits_by_name",
    )

    def __init__(
        self,
        length: sp.Expr,
        width: sp.Expr,
        height: sp.Expr,
        projection: Projection,
        corners: dict[tuple[int, int, int], spg.Point],
        corner_ids: dict[tuple[int, int, int], str],
    ) -> None:
        self.length = length
        self.width = width
        self.height = height
        self.projection = projection
        self.corners = corners
        self.corner_ids = corner_ids
        # corner pair (low bits first) -> ids of the segments joining them
        self.corner_segments: dict[CornerPair, list[str]] = {}
        self._segment_pairs: dict[str, CornerPair] = {}
        self._bits_by_name = {name: bits for bits, name in corner_ids.items()}

    def corner_bits(self, point_id: str) -> Bits | None:
        """Bits of the corner named ``point_id``; None when it is not one."""
        return self._bits_by_name.get(point_id)

    def record_segment(self, segment_id: str, p: Bits, q: Bits) -> None:
        pair = (p, q) if p <= q else (q, p)
        self.corner_segments.setdefault(pair, []).append(segment_id)
        self._segment_pairs[segment_id] = pair

    def segment_pair(self, segment_id: str) -> CornerPair | None:
        """Corner pair the indexed segment joins; None when not indexed."""
        return self._segment_pairs.get(segment_id)

    def true_distance(self, p: Bits, q: Bits) -> sp.Expr:
        """Exact 3D distance between two corners: an edge gives one
        dimension, a face diagonal or the space diagonal the Euclidean
        combination."""
        steps = [abs(a - b) for a, b in zip(p, q)]  # (length, height, width)
        dims = (self.length, self.height, self.width)
        return sp.sqrt(sum((s * d) ** 2 for s, d in zip(steps, dims)))

    @property
    def volume(self) -> sp.Expr:
        return self.length * self.width * self.height

    @property
    def base_area(self) -> sp.Expr:
        """Area of the bottom face (the base): length x width."""
        return self.length * self.width

    @property
    def surface_area(self) -> sp.Expr:
        l, w, h = self.length, self.width, self.height
        return 2 * (l * w + l * h + w * h)

    @property
    def center(self) -> spg.Point:
        """Projected center of the box (mean of the eight corners), which is
        the center of symmetry of the drawn silhouette."""
        xs = sum(p.x for p in self.corners.values())
        ys = sum(p.y for p in self.corners.values())
        return spg.Point(xs / 8, ys / 8)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Prism(L={self.length}, W={self.width}, H={self.height})"


def corner_names(stmt: ir.RectangularPrism) -> dict[tuple[int, int, int], str]:
    """Corner bits -> corner point id, in product order. Default ids are
    ``{id}_v{a}{b}{c}``; ``vertex_names`` replaces them in the same order (a
    list of the wrong length is reported by ``validate``, not here)."""
    if stmt.vertex_names is not None:
        return dict(zip(CORNER_BITS, stmt.vertex_names))
    return {bits: f"{stmt.id}_v{''.join(map(str, bits))}" for bits in CORNER_BITS}


# Per-dimension limit of unit_cubes mode: gridline definitions grow linearly
# (about 4 * (L + W + H)), so this bounds the synthesized view.
UNIT_CUBE_MAX_DIM = 100


def _unit_cube_dim(stmt: ir.RectangularPrism, field: str) -> sp.Integer:
    raw = getattr(stmt, field)
    literal = isinstance(raw, (int, float)) and not isinstance(raw, bool)
    if not literal or not math.isfinite(raw) or float(raw) != int(raw):
        raise IRCompileError(
            stmt.id,
            f"rectangular_prism with unit_cubes needs literal positive integer "
            f"dimensions; {field} is {raw!r}",
        )
    if int(raw) > UNIT_CUBE_MAX_DIM:
        raise IRCompileError(
            stmt.id,
            f"rectangular_prism with unit_cubes allows at most {UNIT_CUBE_MAX_DIM} unit cubes "
            f"per dimension; {field} is {raw!r}. Use wireframe mode (unit_cubes=false) "
            f"for larger prisms",
        )
    return sp.Integer(int(raw))


def compile_prism(
    stmt: ir.RectangularPrism,
    origin: Any,
    ev: Callable[[Any], sp.Expr],
) -> Prism:
    """Validate ``stmt`` and build its Prism from the resolved origin point.
    ``ev`` evaluates a dimension (number or expression). Raises IRCompileError."""
    did = stmt.id
    if stmt.vertex_names is not None:
        if len(stmt.vertex_names) != 8:
            raise IRCompileError(
                did,
                f"rectangular_prism vertex_names must list exactly eight corner names "
                f"(in itertools.product((0, 1), repeat=3) order), got {len(stmt.vertex_names)}",
            )
        seen: set[str] = set()
        for name in stmt.vertex_names:
            if name == did:
                raise IRCompileError(did, f"corner name {name!r} is the prism's own id; rename the corner")
            if name in seen:
                raise IRCompileError(did, f"corner name {name!r} is used twice; corner names must be distinct")
            seen.add(name)
    try:
        projection = projection_for(stmt.view, stmt.side, stmt.depth_angle, stmt.depth_scale)
    except ValueError as e:
        raise IRCompileError(did, f"rectangular_prism: {e}") from e
    if not isinstance(origin, spg.Point):
        raise IRCompileError(
            did, f"rectangular_prism origin {stmt.origin!r} must be a point, got {type(origin).__name__}"
        )

    dims: dict[str, sp.Expr] = {}
    for field in ("length", "width", "height"):
        value = _unit_cube_dim(stmt, field) if stmt.unit_cubes else ev(getattr(stmt, field))
        if not (getattr(value, "is_number", False) and value.is_real is not False):
            raise IRCompileError(did, f"rectangular_prism {field} must be a number, got {value}")
        if not math.isfinite(float(sp.N(value))):
            raise IRCompileError(did, f"rectangular_prism {field} must be a finite number, got {value}")
        if float(sp.N(value)) <= 0:
            raise IRCompileError(did, f"rectangular_prism {field} must be positive, got {value}")
        dims[field] = value

    L, W, H = dims["length"], dims["width"], dims["height"]
    corners = {}
    for bits in CORNER_BITS:
        a, b, c = bits
        dx, dy = projection.offset(a * L, b * H, c * W)
        corners[bits] = spg.Point(origin.x + dx, origin.y + dy)
    return Prism(L, W, H, projection, corners, corner_names(stmt))


def register_corners(stmt: ir.RectangularPrism, obj: Any, sym: dict[str, Any]) -> None:
    """Add the eight corners to ``sym``. A corner name already present is a
    collision (compile_defs reports those up front; this guards incremental
    compiles), never silently skipped or overwritten."""
    if not isinstance(obj, Prism):
        return
    for bits, name in obj.corner_ids.items():
        if name in sym:
            raise IRCompileError(
                stmt.id, f"corner name {name!r} collides with an existing definition; rename the corner"
            )
        sym[name] = obj.corners[bits]


def index_corner_segment(stmt: Any, obj: Any, sym: dict[str, Any]) -> None:
    """Registry ``index`` hook, run after EVERY statement compiles: a segment
    definition whose endpoint ids are two distinct corners of the same prism
    is recorded in that prism's corner-segment index. Type-exact on
    ``ir.Segment``; endpoint ids only, never coordinates."""
    if type(stmt) is not ir.Segment:
        return
    for prism in sym.values():
        if type(prism) is not Prism:
            continue
        p, q = prism.corner_bits(stmt.a), prism.corner_bits(stmt.b)
        if p is not None and q is not None and p != q:
            prism.record_segment(stmt.id, p, q)
            return


def corner_segment(sym: dict[str, Any], segment_id: str) -> tuple[Prism, Bits, Bits] | None:
    """(prism, corner bits, corner bits) for a segment joining two corners of
    one prism, from the compile-time index; None for any other id."""
    for prism in sym.values():
        if type(prism) is Prism:
            pair = prism.segment_pair(segment_id)
            if pair is not None:
                return prism, pair[0], pair[1]
    return None


def true_length(sym: dict[str, Any], segment_id: str) -> sp.Expr | None:
    """Exact true 3D length of a segment joining two corners of one prism;
    None for any other segment."""
    hit = corner_segment(sym, segment_id)
    if hit is None:
        return None
    prism, p, q = hit
    return prism.true_distance(p, q)


def prism_position(obj: Any) -> tuple[float, float] | None:
    if not isinstance(obj, Prism):
        return None
    c = obj.center
    return (float(c.x), float(c.y))


# --- labels on corner segments ---------------------------------------------------

def corner_segment_center(sym: dict[str, Any], segment_id: str) -> tuple[float, float] | None:
    """Registry ``label_away_from`` hook: the projected center of the prism
    whose two corners ``segment_id`` joins (from the compile-time
    corner-segment index); None for any other id. Both renderers place the
    segment's label on the side of its line away from this point (see
    ``render_util.away_normal``): a dimension label outside the silhouette."""
    hit = corner_segment(sym, segment_id)
    if hit is None:
        return None
    return prism_position(hit[0])


# --- render operations on the prism id ------------------------------------------
#
# Slots are the render-operation fields that name an object (see
# derived.render_refs). Only ``draw`` (lowered to the visible faces and hidden
# edges) and ``centroid`` (a free-text label at the projected center) accept
# the prism id; every other slot would silently do nothing, warn and skip, or
# crash on the non-SymPy Prism object, so it is a typed error naming the
# derived ids to use instead.

_VALID_SLOTS = frozenset({"draw", "centroid"})


def render_ref_error(stmt: ir.RectangularPrism, op_kind: str, slot: str) -> str | None:
    """Registry ``render_ref_error`` hook: the error message for the prism
    id used in ``slot`` of a ``op_kind`` render operation; None when valid."""
    if slot in _VALID_SLOTS:
        return None
    pid = stmt.id
    corners = list(corner_names(stmt).values())
    faces = ", ".join(repr(face_id(pid, f)) for f in FACE_NAMES)
    edge = edge_id(pid, (0, 0, 0), (1, 0, 0))
    if slot in ("fill", "fill_hole"):
        why = "a prism has no single outline to fill"
        alt = f"fill a face id such as {face_id(pid, 'bottom')!r} (faces: {faces})"
    elif slot == "point":
        why = "a prism is not a point"
        alt = f"use a corner id such as {corners[0]!r} (corners: {', '.join(map(repr, corners))})"
    elif slot == "segment":
        why = "a prism is not a segment"
        alt = (
            f"use an edge id such as {edge!r} (edges are named {pid}_e_<bits>_<bits> "
            f"by their corner bits, smaller first)"
        )
    else:  # arc
        why = "a prism has no arcs"
        alt = (
            f"to mark an edge use mark_segments on an edge id such as {edge!r}; to place "
            f"text use label_free_text with centroid_of={pid!r} or a face id"
        )
    return f"{op_kind} cannot use the rectangular_prism {pid!r}: {why}; {alt}"


def render_warnings(stmt: ir.RectangularPrism, diagram: Any) -> list[str]:
    """Registry ``render_warnings`` hook: a prism on a canvas with unequal
    axis scales is drawn skewed (the projection assumes equal units), and a
    ``unit_cubes`` prism whose id no draw targets shows no cube gridlines
    (they come only from the prism-id draw lowering, never from its faces)."""
    out: list[str] = []
    canvas = diagram.canvas
    aspect = canvas.aspect if canvas is not None else None
    if aspect is not None and aspect != 1:
        out.append(
            f"rectangular_prism {stmt.id!r} is on a canvas with unequal axis scales "
            f"(canvas.aspect={aspect}): the projection is skewed (the depth angle and face "
            f"shapes are distorted); remove canvas.aspect for an undistorted prism"
        )
    if stmt.unit_cubes and not any(
        isinstance(op, ir.Draw) and op.obj == stmt.id for op in diagram.render
    ):
        out.append(
            f"prism {stmt.id!r} has unit_cubes=true but is never drawn: its cube gridlines "
            f"appear only when you draw the prism id (draw {stmt.id}); drawing its faces "
            f"separately shows no gridlines"
        )
    return out


_LABEL_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?|\.\d+")
_EDGE_AXIS_NAMES = ("length", "height", "width")


def label_dimension_warnings(diagram: Any, sym: dict[str, Any]) -> list[str]:
    """Registry ``pipeline_warnings`` hook.

    Warnings for numeric ``label_segment`` texts on a segment joining two
    corners of one prism whose first number differs from the segment's true
    3D length. A label with no number is schematic and never warns. For an
    edge the message names the dimension (first differing corner bit = length,
    second = height, third = width)."""
    out: list[str] = []
    for op in diagram.render:
        if not isinstance(op, ir.LabelSegment):
            continue
        m = _LABEL_NUMBER_RE.search(op.text)
        hit = corner_segment(sym, op.seg)
        if m is None or hit is None:
            continue
        prism, p, q = hit
        true = float(prism.true_distance(p, q).evalf())
        if math.isclose(float(m.group()), true, rel_tol=1e-6, abs_tol=1e-9):
            continue
        differing = [i for i in range(3) if p[i] != q[i]]
        axis = f" ({_EDGE_AXIS_NAMES[differing[0]]} edge)" if len(differing) == 1 else ""
        out.append(
            f"Label {op.text!r} on prism segment {op.seg!r}{axis} does not match its true "
            f"length {true:.10g}: a prism edge's true length is its length edge "
            f"(first corner bit differs), height edge (second) or width edge (third); "
            f"check the label is on the edge of that dimension."
        )
    return out


# --- registry hooks: compile, query, checks, canvas extent ---------------------

def compile_statement(stmt: ir.RectangularPrism, ref: Callable[[str], Any], ev: Callable[[Any], sp.Expr]) -> Prism:
    """Registry ``compile`` hook."""
    return compile_prism(stmt, ref(stmt.origin), ev)


def query(obj: Prism) -> dict:
    """Registry ``query`` hook (query type ``prism``): true dimensions and
    derived measures of a rectangular prism, plus its corner ids keyed by
    corner bits (length, height, width), e.g. "100" is the corner one length
    along from the origin."""
    def num(v: Any) -> float:
        return float(v.evalf())

    return {
        "length": num(obj.length),
        "width": num(obj.width),
        "height": num(obj.height),
        "volume": num(obj.volume),
        "base_area": num(obj.base_area),
        "surface_area": num(obj.surface_area),
        "corner_ids": {"".join(map(str, bits)): cid for bits, cid in obj.corner_ids.items()},
    }


def _evaluate_volume(check: ir.VolumeEquals, sym: dict[str, Any], default_tol: float) -> tuple[bool, str]:
    """Registry ``evaluate_checks`` hook for ``volume_equals`` (near-exact by
    default: the run-wide default tolerance does not apply)."""
    from .checks import UnsupportedOperand, _near_exact

    prism_id, expected = check.prism, check.expected
    obj = sym[prism_id]
    if type(obj) is not Prism:
        raise UnsupportedOperand(
            f"volume_equals: {prism_id!r} is not a prism "
            f"(got {type(obj).__name__})"
        )
    volume = float(obj.volume.evalf())
    ok = _near_exact(volume, expected, check.tol)
    msg = "" if ok else (
        f"Prism {prism_id!r} volume {volume:.10g} != expected {expected:.10g}"
    )
    return ok, msg


def _evaluate_true_length(check: ir.TrueLengthEquals, sym: dict[str, Any], default_tol: float) -> tuple[bool, str]:
    """Registry ``evaluate_checks`` hook for ``true_length_equals``."""
    from .checks import UnsupportedOperand, _near_exact

    seg, expected = check.seg, check.expected
    sym[seg]  # unknown id: the usual KeyError failure
    true = true_length(sym, seg)
    if true is None:
        raise UnsupportedOperand(
            f"true_length_equals: segment {seg!r} does not join two corners "
            f"of one prism; true length is defined only for those (use "
            f"distance_equals for a 2D length)"
        )
    length = float(true.evalf())
    ok = _near_exact(length, expected, check.tol)
    msg = "" if ok else (
        f"Segment {seg!r} true length {length:.10g} != expected {expected:.10g}"
    )
    return ok, msg


EVALUATE_CHECKS = {"volume_equals": _evaluate_volume, "true_length_equals": _evaluate_true_length}


# Generic 2D checks that measure segment lengths, and the segment fields they
# measure. On a segment joining two prism corners they measure the drawn
# projection, so they warn (their result is unchanged).
def _length_check_segments(check: Any) -> list[str]:
    match check:
        case ir.DistanceEquals(seg=seg):
            return [seg]
        case ir.EqualLength(segs=segs):
            return list(segs)
        case ir.RatioEqual(s1=s1, s2=s2, s3=s3, s4=s4):
            return [s1, s2, s3, s4]
    return []


def projection_check_warnings(check: Any, sym: dict[str, Any]) -> list[str]:
    """Registry ``check_warnings`` hook: a warning when a generic 2D length
    check measures a segment joining two corners of one prism (it measured
    the projection, not the true length)."""
    parts = []
    for seg in dict.fromkeys(_length_check_segments(check)):
        true = true_length(sym, seg)
        obj = sym.get(seg)
        if true is None or not isinstance(obj, spg.Segment):
            continue
        parts.append(
            f"{seg!r} (drawn {float(obj.length.evalf()):.4g}, true {float(true.evalf()):.10g})"
        )
    if not parts:
        return []
    return [
        f"Check {check.kind!r} measured the projected 2D length of prism segment(s) "
        f"{', '.join(parts)}, not the true 3D length; use true_length_equals to check "
        f"a prism's true length."
    ]


def box_extent(stmt: Any, point_xy: Callable[[str], Any], dims: Any) -> list[tuple[float, float]]:
    """The projected corners of a box of (length, height, width) ``dims`` at
    ``stmt.origin`` under ``stmt``'s view fields (a prism's or a block
    stack's), for the recipe lowerer's canvas fit. Empty when the origin has
    no lowering-time coordinates or the view is invalid (reported elsewhere)."""
    try:
        proj = projection_for(stmt.view, stmt.side, stmt.depth_angle, stmt.depth_scale)
    except ValueError:
        return []
    origin = point_xy(stmt.origin)
    if origin is None:
        return []
    out: list[tuple[float, float]] = []
    for bits in CORNER_BITS:
        dx, dy = proj.offset(*(b * d for b, d in zip(bits, dims)))
        out.append((origin[0] + float(dx), origin[1] + float(dy)))
    return out


def canvas_extent(stmt: ir.RectangularPrism, point_xy: Callable[[str], Any]) -> list[tuple[float, float]]:
    """Registry ``canvas_extent`` hook: the eight projected corners, when all
    three dimensions are literal numbers (expression dimensions: unknown
    extent, the canvas falls back to the other points)."""
    try:
        dims = [float(v) for v in (stmt.length, stmt.height, stmt.width)]
    except (TypeError, ValueError):
        return []
    return box_extent(stmt, point_xy, dims)


# --- derived edges and faces (public ids) --------------------------------------
#
# Faces: ``{id}_front``, ``{id}_back``, ``{id}_left``, ``{id}_right``,
# ``{id}_top`` and ``{id}_bottom`` (the bottom face is also called the base;
# there is no separate base id). Edges: ``{id}_e_{abc}_{abc}``, the two corner
# bit strings of its endpoints with the smaller one first (e.g. ``P_e_000_100``
# is the front bottom edge, along the length). Edge and face ids are always
# built from the prism id and corner bits, also when ``vertex_names`` renames
# the corners (their endpoints are then the renamed corners).

# Face name -> the plane it lies in, as (axis, "min" | "max"), matching
# Projection.visible_planes.
FACE_PLANES: dict[str, tuple[str, str]] = {
    "front": ("width", "min"),
    "back": ("width", "max"),
    "left": ("length", "min"),
    "right": ("length", "max"),
    "bottom": ("height", "min"),
    "top": ("height", "max"),
}
FACE_NAMES: tuple[str, ...] = ("front", "back", "left", "right", "top", "bottom")


def _bits_str(bits: tuple[int, int, int]) -> str:
    return "".join(map(str, bits))


def face_id(prism_id: str, face: str) -> str:
    return f"{prism_id}_{face}"


def edge_id(prism_id: str, p: tuple[int, int, int], q: tuple[int, int, int]) -> str:
    lo, hi = sorted((_bits_str(p), _bits_str(q)))
    return f"{prism_id}_e_{lo}_{hi}"


def face_corners(face: str) -> list[tuple[int, int, int]]:
    """The face's four corner bits in boundary order."""
    axis, side = FACE_PLANES[face]
    fixed = AXES.index(axis)
    j, k = [i for i in range(3) if i != fixed]
    out = []
    for u, v in ((0, 0), (1, 0), (1, 1), (0, 1)):
        bits = [0, 0, 0]
        bits[fixed] = 1 if side == "max" else 0
        bits[j], bits[k] = u, v
        out.append(tuple(bits))
    return out  # type: ignore[return-value]


def edges() -> list[tuple[tuple[int, int, int], tuple[int, int, int]]]:
    """The twelve edges as corner-bit pairs (low end first), in a fixed order."""
    out = []
    for bits in CORNER_BITS:
        for axis in range(3):
            if bits[axis] == 0:
                other = list(bits)
                other[axis] = 1
                out.append((bits, tuple(other)))
    return out  # type: ignore[return-value]


def edge_between(
    prism_id: str, corners: Mapping[tuple[int, int, int], str], p: str, q: str,
) -> str | None:
    """The prism's own edge id when corner ids ``p`` and ``q`` (either order)
    are the two ends of one of its edges (their corner bits differ on exactly
    one axis); None for a diagonal, the same corner twice or a non-corner.
    ``corners`` is the prism's bits -> corner id map (``corner_names``)."""
    bits = {name: b for b, name in corners.items()}
    a, b = bits.get(p), bits.get(q)
    if a is None or b is None or sum(x != y for x, y in zip(a, b)) != 1:
        return None
    return edge_id(prism_id, a, b)


def gridline_point_id(prism_id: str, n: int) -> str:
    return f"__{prism_id}_gp{n}"


def gridline_id(prism_id: str, n: int) -> str:
    return f"__{prism_id}_g{n}"


def _unit_cube_dims(stmt: ir.RectangularPrism) -> dict[str, int] | None:
    """The literal integer dimensions of a unit-cubes prism, or None when they
    are not (compile reports that; nothing is synthesized meanwhile)."""
    dims = {}
    for field in ("length", "width", "height"):
        try:
            dims[field] = int(_unit_cube_dim(stmt, field))
        except IRCompileError:
            return None
        if dims[field] <= 0:
            return None
    return dims


def gridline_defs(stmt: ir.RectangularPrism) -> tuple[list[Any], list[Any]]:
    """Derived (points, segments) for the unit-cube gridlines, with hidden ids
    ``__{id}_gp{n}`` (points) and ``__{id}_g{n}`` (segments).

    Each visible face (the planes of the projection's viewer direction, never a
    per-view table) with axes (u, v) of sizes (nu, nv) gets, for every integer
    cut k in 1..nu-1, a line parallel to v spanning the face, and for every cut
    j in 1..nv-1 a line parallel to u. A line's ends are PointBetween points on
    the face's boundary edges; a boundary point shared by two faces (a visible
    edge) is made once. Pure function of the statement. Empty unless
    ``unit_cubes`` with valid dimensions and view."""
    if not stmt.unit_cubes:
        return [], []
    names = corner_names(stmt)
    dims = _unit_cube_dims(stmt)
    if len(names) != 8 or dims is None:
        return [], []
    try:
        visible = projection_for(stmt.view, stmt.side, stmt.depth_angle, stmt.depth_scale).visible_planes
    except ValueError:
        return [], []
    size = (dims["length"], dims["height"], dims["width"])
    points: list[Any] = []
    segments: list[Any] = []
    made: dict[tuple[Bits, Bits, int], str] = {}

    def cut_point(lo: Bits, hi: Bits, k: int) -> str:
        """The point k/n of the way from corner ``lo`` to its edge neighbour ``hi``."""
        key = (lo, hi, k)
        if key not in made:
            axis = next(i for i in range(3) if lo[i] != hi[i])
            pid = gridline_point_id(stmt.id, len(made))
            made[key] = pid
            points.append(ir.PointBetween(
                id=pid, a=names[lo], b=names[hi], ratio=f"{k}:{size[axis] - k}"
            ))
        return made[key]

    for face in FACE_NAMES:
        if FACE_PLANES[face] not in visible:
            continue
        axis, side = FACE_PLANES[face]
        fixed = AXES.index(axis)
        u, v = [i for i in range(3) if i != fixed]

        def corner(a: int, b: int) -> Bits:
            bits = [0, 0, 0]
            bits[fixed] = 1 if side == "max" else 0
            bits[u], bits[v] = a, b
            return tuple(bits)  # type: ignore[return-value]

        # lines parallel to v at u = k (ends on the v=0 and v=1 boundary edges)
        for k in range(1, size[u]):
            p, q = (cut_point(corner(0, e), corner(1, e), k) for e in (0, 1))
            segments.append(ir.Segment(id=gridline_id(stmt.id, len(segments)), a=p, b=q))
        # lines parallel to u at v = j (ends on the u=0 and u=1 boundary edges)
        for j in range(1, size[v]):
            p, q = (cut_point(corner(e, 0), corner(e, 1), j) for e in (0, 1))
            segments.append(ir.Segment(id=gridline_id(stmt.id, len(segments)), a=p, b=q))
    return points, segments


def synthesize_edges_and_faces(stmt: ir.RectangularPrism) -> list[Any]:
    """The twelve edge segments and six face polygons over the corner ids,
    plus (``unit_cubes``) the gridline points and segments (registry
    ``synthesize`` hook; never written into the authored IR). A
    wrong-length ``vertex_names`` synthesizes nothing (compile reports it)."""
    names = corner_names(stmt)
    if len(names) != 8:
        return []
    out: list[Any] = [
        ir.Segment(id=edge_id(stmt.id, p, q), a=names[p], b=names[q]) for p, q in edges()
    ]
    out += [
        ir.Polygon(id=face_id(stmt.id, face), points=[names[b] for b in face_corners(face)])
        for face in FACE_NAMES
    ]
    points, segments = gridline_defs(stmt)
    return out + points + segments


# Gridlines are thin gray whatever the author's style: the author's style
# stays on the face outlines. ``gray`` is a named color both renderers know.
GRIDLINE_STYLE: dict[str, Any] = {"color": "gray", "thin": True}


def _hidden_style(style_key: str | None, styles: dict[str, Any]) -> dict[str, Any]:
    """The author's draw style with ``dashed`` merged in (a dotted pattern is
    dropped: hidden edges are always dashed)."""
    from .render_util import bare_color_key

    if style_key is not None and style_key in styles:
        merged = dict(styles[style_key])
    elif bare_color_key(style_key):
        merged = {"color": style_key}
    else:
        merged = {}
    merged.pop("dotted", None)
    merged["dashed"] = True
    return merged


def lower_draw(stmt: ir.RectangularPrism, op: Any, styles: dict[str, Any]) -> Any:
    """Registry ``lower_draw`` hook: a draw of the prism becomes draws of its
    visible face outlines (author's style) and, unless ``unit_cubes``, of the
    three edges meeting at the hidden corner (author's style plus dashed); with
    ``unit_cubes`` instead of the gridline segments (thin gray).
    Visible faces and the hidden corner come from the projection's viewer
    direction, never from a per-view table."""
    from .derived import Lowering

    try:
        projection = projection_for(stmt.view, stmt.side, stmt.depth_angle, stmt.depth_scale)
    except ValueError as e:
        raise IRCompileError(stmt.id, f"rectangular_prism: {e}") from e
    visible = projection.visible_planes
    ops: list[Any] = [
        ir.Draw(obj=face_id(stmt.id, face), style=op.style)
        for face in FACE_NAMES
        if FACE_PLANES[face] in visible
    ]
    extra_styles: dict[str, dict[str, Any]] = {}
    if not stmt.unit_cubes:
        hidden_key = f"__{stmt.id}_hidden" + (f"_{op.style}" if op.style else "")
        extra_styles[hidden_key] = _hidden_style(op.style, styles)
        h = projection.hidden_corner
        for axis in range(3):
            other = list(h)
            other[axis] = 1 - other[axis]
            ops.append(ir.Draw(obj=edge_id(stmt.id, h, tuple(other)), style=hidden_key))  # type: ignore[arg-type]
    else:
        grid_key = f"__{stmt.id}_grid"
        extra_styles[grid_key] = dict(GRIDLINE_STYLE)
        ops += [ir.Draw(obj=seg.id, style=grid_key) for seg in gridline_defs(stmt)[1]]
    return Lowering(ops=ops, styles=extra_styles)
