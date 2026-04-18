# recipe/dsl.py
"""RecipeDSL Pydantic schema — the high-level geometry DSL.

LLMs generate RecipeDSL JSON; the lowering pass compiles it to DiagramIR.
IDs starting with '__' are reserved for lowering intermediates and are
rejected at parse time.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ir.ir import PickRule


# ---------------------------------------------------------------------------
# Shared validators
# ---------------------------------------------------------------------------

def _reject_reserved_id(id_: str) -> str:
    if id_.startswith("__"):
        raise ValueError(f"IDs starting with '__' are reserved for lowering intermediates; got {id_!r}")
    return id_


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class DSLOpBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: str
    id: str
    visible: bool = True  # set False to suppress from auto_draw_all

    @field_validator("id")
    @classmethod
    def id_not_reserved(cls, v: str) -> str:
        return _reject_reserved_id(v)


# ---------------------------------------------------------------------------
# Foundation ops
# ---------------------------------------------------------------------------

class TriangleSpec(BaseModel):
    """Triangle constraints using positional A/B/C slots.

    A=vertices[0], B=vertices[1], C=vertices[2] always.
    Provide any combination of sides and angles that uniquely determines
    the triangle. right_angle_at takes priority over angle constraints.

    Supported forms:
        SSS:       side_AB, side_BC, side_CA
        SAS:       two sides + included angle (e.g. side_AB, angle_B, side_BC)
        ASA/AAS:   two angles + one side
        right_at:  right_angle_at + at least 2 other constraints
    """
    model_config = ConfigDict(extra="forbid")

    side_AB: Optional[float] = None
    side_BC: Optional[float] = None
    side_CA: Optional[float] = None
    angle_A: Optional[float] = None
    angle_B: Optional[float] = None
    angle_C: Optional[float] = None
    right_angle_at: Optional[Literal["A", "B", "C"]] = None

    @model_validator(mode="after")
    def _validate_sufficient_constraints(self) -> "TriangleSpec":
        sides = [k for k in ["side_AB", "side_BC", "side_CA"]
                 if getattr(self, k) is not None]
        angles = [k for k in ["angle_A", "angle_B", "angle_C"]
                  if getattr(self, k) is not None]

        if self.right_angle_at is not None:
            if len(sides) + len(angles) + 1 < 3:
                raise ValueError(
                    "right_angle_at triangle needs at least 2 additional constraints "
                    "(sides and/or angles)"
                )
            return self

        total = len(sides) + len(angles)
        if total < 3:
            raise ValueError(
                f"Triangle needs at least 3 constraints, got {total}. "
                "Supported: SSS, SAS, ASA, AAS, or right_angle_at+2."
            )
        if len(sides) == 0:
            raise ValueError(
                "At least one side length is required (AAA is underdetermined — "
                "infinitely many similar triangles)"
            )
        return self


class TriangleOp(DSLOpBase):
    """Triangle defined by angles/sides. A/B/C in spec are positional slots:
    A=vertices[0], B=vertices[1], C=vertices[2]."""
    op: Literal["triangle"] = "triangle"
    vertices: list[str]  # exactly 3 names for the vertices
    spec: TriangleSpec
    center: Optional[list[float]] = None


class CircleOp(DSLOpBase):
    """Circle from center + radius or center + through-point."""
    op: Literal["circle"] = "circle"
    center: str
    radius: Optional[Union[int, float, str]] = None
    through: Optional[str] = None

    @model_validator(mode="after")
    def radius_or_through(self) -> "CircleOp":
        if self.radius is None and self.through is None:
            raise ValueError("CircleOp requires either 'radius' or 'through'")
        return self


class EllipseOp(DSLOpBase):
    """Axis-aligned ellipse.  Exactly one form must be specified:

    - center_axes: {center, hradius, vradius}
    - bbox:        {bbox: [corner1_id, corner2_id]}
    - foci:        {foci: [focus1_id, focus2_id], major_axis: 2a}
                   or {foci: [...], through: point_id}
    - eccentricity:{center, semi_major, eccentricity, orientation}
    """
    op: Literal["ellipse"] = "ellipse"
    # center_axes form
    center: Optional[str] = None
    hradius: Optional[Union[int, float, str]] = None
    vradius: Optional[Union[int, float, str]] = None
    # bbox form
    bbox: Optional[list[str]] = None          # [corner1_id, corner2_id]
    # foci form
    foci: Optional[list[str]] = None          # [focus1_id, focus2_id]
    major_axis: Optional[Union[int, float, str]] = None   # total length 2a
    through: Optional[str] = None             # point on ellipse (foci form only)
    # eccentricity form
    semi_major: Optional[Union[int, float, str]] = None
    eccentricity: Optional[Union[int, float, str]] = None
    orientation: Optional[Literal["horizontal", "vertical"]] = None

    @model_validator(mode="after")
    def _exactly_one_form(self) -> "EllipseOp":
        center_axes = self.center is not None and self.hradius is not None and self.vradius is not None
        bbox = self.bbox is not None
        foci = self.foci is not None and (self.major_axis is not None or self.through is not None)
        ecc = (self.center is not None and self.semi_major is not None and self.eccentricity is not None)
        forms = [center_axes, bbox, foci, ecc]
        if forms.count(True) != 1:
            raise ValueError(
                "EllipseOp requires exactly one form: "
                "center_axes ({center, hradius, vradius}), "
                "bbox ({bbox:[c1,c2]}), "
                "foci ({foci:[f1,f2], major_axis or through}), "
                "or eccentricity ({center, semi_major, eccentricity}). "
                f"Got: center_axes={center_axes}, bbox={bbox}, foci={foci}, eccentricity={ecc}"
            )
        if bbox and (self.bbox is None or len(self.bbox) != 2):
            raise ValueError("EllipseOp bbox must be a list of exactly 2 point IDs")
        if foci and (self.foci is None or len(self.foci) != 2):
            raise ValueError("EllipseOp foci must be a list of exactly 2 point IDs")
        return self


class PolygonOp(DSLOpBase):
    """Polygon from existing named vertices."""
    op: Literal["polygon"] = "polygon"
    vertices: list[str]  # 3 or more


class PointOp(DSLOpBase):
    """Explicit point with coordinates (grid mode)."""
    op: Literal["point"] = "point"
    coords: list[float]  # [x, y]


class PointExternalOp(DSLOpBase):
    """Point outside a circle at a given direction and distance ratio."""
    op: Literal["point_external"] = "point_external"
    relative_to: str   # circle id
    direction: Union[Literal["left", "right", "above", "below"], float]  # Cardinals or numeric angle in degrees
    distance_ratio: float  # multiple of radius


class CanvasOp(DSLOpBase):
    """Set canvas bounds (maps to DiagramIR.canvas, not a def statement)."""
    op: Literal["canvas"] = "canvas"
    x_range: list[float]  # [xmin, xmax]
    y_range: list[float]  # [ymin, ymax]
    grid: bool = False
    axes: bool = False


# ---------------------------------------------------------------------------
# Derived ops (IR passthroughs)
# ---------------------------------------------------------------------------

class MidpointOp(DSLOpBase):
    op: Literal["midpoint"] = "midpoint"
    of: list[str]  # exactly [P, Q]


class IntersectionOp(DSLOpBase):
    op: Literal["intersection"] = "intersection"
    of: list[str]  # exactly [obj1, obj2]
    selector: Optional[PickRule] = None


class PerpendicularOp(DSLOpBase):
    op: Literal["perpendicular"] = "perpendicular"
    to_line: Union[str, list[str]]  # line id OR [A, B] point pair (avoids forced LineThroughOp)
    through: str


class ParallelOp(DSLOpBase):
    op: Literal["parallel"] = "parallel"
    to_line: Union[str, list[str]]  # line id OR [A, B] point pair
    through: str


class LineThroughOp(DSLOpBase):
    op: Literal["line_through"] = "line_through"
    points: list[str]  # exactly [A, B]


class SegmentOp(DSLOpBase):
    op: Literal["segment"] = "segment"
    endpoints: list[str]  # exactly [A, B]


class RayOp(DSLOpBase):
    op: Literal["ray"] = "ray"
    from_: str = Field(alias="from")
    through: str
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ReflectionOp(DSLOpBase):
    op: Literal["reflection"] = "reflection"
    point: str    # source
    over: str     # axis (line id or point id)


class RotationOp(DSLOpBase):
    op: Literal["rotation"] = "rotation"
    point: str    # source
    center: str
    angle: Union[int, float, str]  # degrees; lowering converts to radians


class PointOnSegmentOp(DSLOpBase):
    op: Literal["point_on_segment"] = "point_on_segment"
    segment: list[str]  # [A, B]
    ratio: Optional[Union[float, str]] = None  # 0–1 or "m:n"


class TangentLineOp(DSLOpBase):
    op: Literal["tangent_line"] = "tangent_line"
    circle: str
    at: Optional[str] = None          # point on the circle → tangent at that point
    from_point: Optional[str] = None  # external point → tangent lines from there
    selector: Optional[PickRule] = None

    @model_validator(mode="after")
    def _validate_exactly_one_point(self) -> "TangentLineOp":
        if (self.at is None) == (self.from_point is None):
            raise ValueError("tangent_line requires exactly one of 'at' or 'from_point'")
        return self


# ---------------------------------------------------------------------------
# Composite ops
# ---------------------------------------------------------------------------

class AltitudeOp(DSLOpBase):
    """Altitude from vertex to opposite side.

    id resolves to the altitude *line* (the perpendicular).
    foot is a separately-named point on the base.

    Preferred: specify `triangle` (triangle id) — lowering infers the opposite side.
    Fallback: specify `to_side` ([P, Q]) — explicit base points for non-triangle cases.
    """
    op: Literal["altitude"] = "altitude"
    from_vertex: str
    triangle: Optional[str] = None    # preferred: triangle id; lowering infers opposite side
    to_side: Optional[list[str]] = None  # explicit 2-point base, for non-triangle cases
    foot: str

    @model_validator(mode="after")
    def _validate_base(self) -> "AltitudeOp":
        if self.triangle is None and self.to_side is None:
            raise ValueError("altitude requires either 'triangle' or 'to_side'")
        if self.triangle is not None and self.to_side is not None:
            raise ValueError("altitude: specify 'triangle' or 'to_side', not both")
        return self


class CircumcircleOp(DSLOpBase):
    """Circumscribed circle of a triangle or three points.

    Specify exactly one of:
      - ``of``: a triangle ID (existing form)
      - ``points``: exactly 3 point IDs
    """
    op: Literal["circumcircle"] = "circumcircle"
    of: Optional[str] = None        # triangle id
    points: Optional[list[str]] = None  # OR exactly 3 point IDs
    center: str                     # name for circumcenter point

    @model_validator(mode="after")
    def _of_xor_points(self) -> "CircumcircleOp":
        if not self.of and not self.points:
            raise ValueError("CircumcircleOp requires 'of' (triangle) or 'points' (3 points)")
        if self.of and self.points:
            raise ValueError("CircumcircleOp: specify 'of' or 'points', not both")
        if self.points is not None and len(self.points) != 3:
            raise ValueError(f"'points' must have exactly 3 point IDs, got {len(self.points)}")
        return self


class IncircleOp(DSLOpBase):
    """Inscribed circle of a triangle or three points.

    Specify exactly one of:
      - ``of``: a triangle ID (existing form)
      - ``points``: exactly 3 point IDs
    """
    op: Literal["incircle"] = "incircle"
    of: Optional[str] = None
    points: Optional[list[str]] = None
    center: str

    @model_validator(mode="after")
    def _of_xor_points(self) -> "IncircleOp":
        if not self.of and not self.points:
            raise ValueError("IncircleOp requires 'of' (triangle) or 'points' (3 points)")
        if self.of and self.points:
            raise ValueError("IncircleOp: specify 'of' or 'points', not both")
        if self.points is not None and len(self.points) != 3:
            raise ValueError(f"'points' must have exactly 3 point IDs, got {len(self.points)}")
        return self


class PerpendicularBisectorOp(DSLOpBase):
    """Perpendicular bisector of a segment."""
    op: Literal["perpendicular_bisector"] = "perpendicular_bisector"
    of: list[str]   # [P, Q]
    mid: str        # name for midpoint


class AngleBisectorOp(DSLOpBase):
    """Angle bisector line at a vertex."""
    op: Literal["angle_bisector"] = "angle_bisector"
    vertex: str
    ray1_toward: str
    ray2_toward: str


class CentroidOp(DSLOpBase):
    """Centroid of a triangle."""
    op: Literal["centroid"] = "centroid"
    of: str  # triangle id


class MedianOp(DSLOpBase):
    """Median from vertex to midpoint of opposite side.

    Preferred: specify `triangle` (triangle id) — lowering infers the opposite side.
    Fallback: specify `to_side` ([P, Q]) — explicit base points for non-triangle cases.
    """
    op: Literal["median"] = "median"
    from_vertex: str
    triangle: Optional[str] = None    # preferred: triangle id
    to_side: Optional[list[str]] = None  # explicit 2-point base
    mid: str

    @model_validator(mode="after")
    def _validate_base(self) -> "MedianOp":
        if self.triangle is None and self.to_side is None:
            raise ValueError("median requires either 'triangle' or 'to_side'")
        if self.triangle is not None and self.to_side is not None:
            raise ValueError("median: specify 'triangle' or 'to_side', not both")
        return self


class PolygonExteriorOp(DSLOpBase):
    """Regular polygon on exterior of an edge (e.g., square on segment)."""
    op: Literal["polygon_exterior"] = "polygon_exterior"
    base: list[str]   # [P, Q] — edge
    ref_point: str    # polygon placed on opposite side from this point
    n: int            # number of sides (3=equilateral triangle, 4=square)
    vertices: list[str]  # names for the computed vertices (v2..v_{n-1})


class RegularPolygonOp(DSLOpBase):
    """Regular polygon computed from center, radius, and start angle.

    Lowering emits N point_fixed defs (named by `vertices`) then a polygon def.
    Set star=True to connect every 2nd vertex (star polygon, e.g. pentagram {5/2}).
    Requires an odd number of vertices >= 5.
    """
    op: Literal["regular_polygon"] = "regular_polygon"
    center: str
    radius: Union[int, float, str]
    start_angle: Union[int, float, str] = 0  # degrees; 0 = first vertex at rightmost
    vertices: list[str]  # exactly N names, one per vertex
    star: bool = False  # True → connect every 2nd vertex (star polygon)

    @model_validator(mode="after")
    def _check_star_valid(self) -> "RegularPolygonOp":
        if self.star:
            n = len(self.vertices)
            if n < 5 or n % 2 == 0:
                raise ValueError(
                    f"star=True requires an odd number of vertices >= 5 (got {n})"
                )
        return self


class PointAlongOp(DSLOpBase):
    """Point at a given distance along a line from a reference point.

    Lowering computes the unit vector from `from_` toward `toward`,
    then places the result at from_ + distance * unit_vector.
    """
    op: Literal["point_along"] = "point_along"
    on: str                        # line/segment/ray id (for context; may be unused in lowering)
    from_: str = Field(alias="from")
    distance: Union[int, float, str]
    toward: str                    # named point indicating direction of travel
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ExtendSegmentOp(DSLOpBase):
    """Point beyond a specified endpoint of a segment by a given extra distance.

    Lowering emits a PointFixed computed beyond `beyond` in the direction away from
    the other endpoint.
    """
    op: Literal["extend_segment"] = "extend_segment"
    segment: list[str]              # [A, B]
    beyond: str                     # which endpoint to extend beyond (must be A or B)
    by: Union[int, float, str]      # extra distance beyond that endpoint


class PointFootOp(DSLOpBase):
    """Foot of perpendicular from a point onto a line.

    Projects `source` onto `onto` without constructing a named altitude line.
    Equivalent to IR's `point_foot` directly.
    """
    op: Literal["point_foot"] = "point_foot"
    source: str   # the point to project
    onto: str     # line/segment id


class CircleThrough3Op(DSLOpBase):
    """Circumcircle through three arbitrary points (not necessarily a named triangle)."""
    op: Literal["circle_through_3"] = "circle_through_3"
    through: list[str]  # exactly 3 point IDs
    center: str         # name for the circumcenter point


class RectangleSpec(BaseModel):
    """Rectangle dimensions using positional A/B/C/D slots.

    A=vertices[0], B=vertices[1], C=vertices[2], D=vertices[3] always.
    Provide at least two adjacent side lengths. Adjacent pairs:
        AB+BC, BC+CD, CD+DA, DA+AB
    Opposite pairs (AB+CD, BC+DA) are not sufficient.
    """
    model_config = ConfigDict(extra="forbid")

    side_AB: Optional[float] = None
    side_BC: Optional[float] = None
    side_CD: Optional[float] = None
    side_DA: Optional[float] = None
    rotation: float = 0.0  # degrees CCW

    @model_validator(mode="after")
    def _validate_two_adjacent(self) -> "RectangleSpec":
        provided = [k for k in ["side_AB", "side_BC", "side_CD", "side_DA"]
                    if getattr(self, k) is not None]
        if len(provided) < 2:
            raise ValueError(
                "Rectangle needs at least 2 side lengths. "
                "Provide two adjacent sides, e.g. side_AB and side_BC."
            )
        ADJACENT = {
            ("side_AB", "side_BC"), ("side_BC", "side_CD"),
            ("side_CD", "side_DA"), ("side_DA", "side_AB"),
        }
        pairs = [(provided[i], provided[j])
                 for i in range(len(provided)) for j in range(i + 1, len(provided))]
        if not any((a, b) in ADJACENT or (b, a) in ADJACENT for a, b in pairs):
            raise ValueError(
                "Rectangle needs two adjacent side lengths (sharing a vertex). "
                "Opposite sides (side_AB + side_CD or side_BC + side_DA) are not sufficient."
            )
        return self


class RectangleOp(DSLOpBase):
    """Axis-aligned rectangle with labeled side lengths.

    ``vertices`` lists the 4 corner names in perimeter order: A, B, C, D
    where AB and BC are adjacent sides. A/B/C/D in ``spec`` are positional
    slots: A=vertices[0], B=vertices[1], C=vertices[2], D=vertices[3].

    ``spec`` keys:
    - ``side_AB``, ``side_BC``, etc.: lengths for positional slot pairs.
      Provide at least two adjacent sides.
    - ``rotation`` (optional, degrees CCW, default 0).

    ``center`` (optional): [x, y] override for the rectangle centroid; default (2, 2).

    Default layout (rotation=0): A top-left, B top-right, C bottom-right, D bottom-left.
    """
    op: Literal["rectangle"] = "rectangle"
    vertices: list[str]
    spec: RectangleSpec
    center: Optional[list[float]] = None

    @field_validator("vertices")
    @classmethod
    def _four_vertices(cls, v: list[str]) -> list[str]:
        if len(v) != 4:
            raise ValueError(f"RectangleOp requires exactly 4 vertices, got {len(v)}")
        return v


class PolygonFromSidesOp(DSLOpBase):
    """Polygon constructed from given consecutive side lengths.

    Vertices are placed to form the maximum-area polygon.
    side_lengths[i] = distance from vertices[i] to vertices[(i+1) % N].
    """
    op: Literal["polygon_from_sides"] = "polygon_from_sides"
    vertices: list[str]
    side_lengths: list[float]
    center: Optional[list[float]] = None

    @model_validator(mode="after")
    def _check_lengths_match(self) -> "PolygonFromSidesOp":
        if len(self.vertices) != len(self.side_lengths):
            raise ValueError(
                f"polygon_from_sides: len(vertices)={len(self.vertices)} "
                f"must equal len(side_lengths)={len(self.side_lengths)}"
            )
        if len(self.vertices) < 3:
            raise ValueError(
                f"polygon_from_sides requires at least 3 vertices, got {len(self.vertices)}"
            )
        return self


class ArcOp(DSLOpBase):
    """Circular arc from ``start`` CCW to the ray through ``end``.

    Radius = |center − start|.  The arc sweeps counter-clockwise starting at
    ``start`` until it reaches the ray from ``center`` through ``end``.
    ``end`` need not lie on the circle; only its direction from ``center`` is
    used.  For a full-circle sweep, use a ``circle`` op instead.

    Example (quarter-arc of the unit circle from the +x axis to the +y axis):
      {op: "arc", id: "arc1", center: "O", start: "A", end: "B"}
    """
    op: Literal["arc"] = "arc"
    center: str
    start: str
    end: str
    reflex: bool = False


class FillOp(DSLOpBase):
    """Fill a closed shape, optionally punching holes with the even-odd rule.

    ``obj``: the outer closed shape to fill (polygon, circle, triangle id).
    ``holes``: list of shape IDs that cut transparent regions from ``obj``.
    ``opacity``: fill opacity (0.0–1.0).
    ``style``: named style key or inline style dict (same as DrawObj).

    Example (shade ring between circle and quadrilateral):
      {op: "fill", id: "shade", obj: "circ", holes: ["quad"], opacity: 0.3}
    """
    op: Literal["fill"] = "fill"
    obj: str
    holes: list[str] = Field(default_factory=list)
    opacity: float = 1.0
    style: Optional[Union[str, dict[str, Any]]] = None


# ---------------------------------------------------------------------------
# DSLOp discriminated union
# ---------------------------------------------------------------------------

DSLOp = Annotated[
    Union[
        # Foundation
        TriangleOp, CircleOp, EllipseOp, PolygonOp, PointOp, PointExternalOp, CanvasOp,
        # Derived
        MidpointOp, IntersectionOp, PerpendicularOp, ParallelOp,
        LineThroughOp, SegmentOp, RayOp, ReflectionOp, RotationOp,
        PointOnSegmentOp, TangentLineOp, PointFootOp, CircleThrough3Op,
        # Composite
        AltitudeOp, CircumcircleOp, IncircleOp, PerpendicularBisectorOp,
        AngleBisectorOp, CentroidOp, MedianOp, PolygonExteriorOp,
        # Foundation (continued)
        RegularPolygonOp, RectangleOp, PolygonFromSidesOp, ArcOp,
        # Derived (continued)
        PointAlongOp, ExtendSegmentOp,
        # Render-only
        FillOp,
    ],
    Field(discriminator="op")
]


# ---------------------------------------------------------------------------
# Annotation models (typed; LLM errors caught at parse time)
# ---------------------------------------------------------------------------

class MarkAngle(BaseModel):
    """Mark an angle arc at `vertex` between rays toward `a` and `b`."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["mark_angle"] = "mark_angle"
    a: Optional[str] = None
    vertex: Optional[str] = None
    b: Optional[str] = None
    at: Optional[str] = None  # vertex name within triangle (shorthand)
    of: Optional[str] = None  # triangle id (shorthand)
    group: Optional[int] = None  # tick-group for equal-angle marking
    expected: Optional[Union[float, Literal["acute", "right", "obtuse"]]] = None

    @model_validator(mode="after")
    def _check_form(self) -> "MarkAngle":
        has_explicit = all(v is not None for v in [self.a, self.vertex, self.b])
        has_shorthand = self.at is not None and self.of is not None
        if has_explicit == has_shorthand:
            raise ValueError(
                "mark_angle: specify exactly one of (a, vertex, b) or (at, of)"
            )
        return self


class MarkRightAngle(BaseModel):
    """Mark a right-angle square at `vertex`."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["mark_right_angle"] = "mark_right_angle"
    a: Optional[str] = None
    vertex: Optional[str] = None
    b: Optional[str] = None
    at: Optional[str] = None  # vertex name within triangle (shorthand)
    of: Optional[str] = None  # triangle id (shorthand)

    @model_validator(mode="after")
    def _check_form(self) -> "MarkRightAngle":
        has_explicit = all(v is not None for v in [self.a, self.vertex, self.b])
        has_shorthand = self.at is not None and self.of is not None
        if has_explicit == has_shorthand:
            raise ValueError(
                "mark_right_angle: specify exactly one of (a, vertex, b) or (at, of)"
            )
        return self


class MarkEqualLengths(BaseModel):
    """Mark equal-length tick marks on a group of segments."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["mark_equal_lengths"] = "mark_equal_lengths"
    segments: list[list[str]]   # [[A,B],[C,D], ...]
    group: Optional[int] = None


class MarkParallel(BaseModel):
    """Mark parallel arrow marks on a group of segments."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["mark_parallel"] = "mark_parallel"
    segments: list[list[str]]
    group: Optional[int] = None


class MarkProportional(BaseModel):
    """Mark proportional-length tick marks on groups of corresponding segments.

    Use instead of mark_equal_lengths when segments are proportional but not
    equal (e.g. corresponding sides of similar triangles).  Each inner list is
    a pair [P, Q] of endpoints.  The lowerer verifies that the ratio between
    consecutive pairs is constant.
    """
    model_config = ConfigDict(extra="forbid")
    kind: Literal["mark_proportional"] = "mark_proportional"
    segments: list[list[str]]   # [[A,B],[D,E], ...] — corresponding segments
    group: Optional[int] = None


class LabelSegment(BaseModel):
    """Place a text label at the midpoint of a segment."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["label_segment"] = "label_segment"
    endpoints: list[str]  # [A, B]
    text: str
    pos: Literal[
        "auto", "above", "below", "left", "right",
        "above left", "above right", "below left", "below right",
    ] = "auto"


class LabelPoint(BaseModel):
    """Place/override the label text at a point.

    When a point already has an auto-generated label (auto_label_points=true),
    a matching label_point entry overrides its text and/or position.  Omit
    ``text`` to keep the point id but change only ``pos``.
    """
    model_config = ConfigDict(extra="forbid")
    kind: Literal["label_point"] = "label_point"
    point: str
    text: Optional[str] = None  # None → use point id
    pos: Literal[
        "auto", "above", "below", "left", "right",
        "above left", "above right", "below left", "below right",
    ] = "auto"


class LabelAngle(BaseModel):
    """Place a text label inside the angle at ``vertex`` between rays to ``a`` and ``b``.

    Accepts the same explicit/shorthand forms as ``mark_angle``:
      - explicit: a, vertex, b
      - shorthand: at (vertex within triangle), of (triangle id)
    Pair with a ``mark_angle`` entry in ``annotations.marks`` if you also want
    the arc to be drawn.
    """
    model_config = ConfigDict(extra="forbid")
    kind: Literal["label_angle"] = "label_angle"
    a: Optional[str] = None
    vertex: Optional[str] = None
    b: Optional[str] = None
    at: Optional[str] = None  # vertex name within triangle (shorthand)
    of: Optional[str] = None  # triangle id (shorthand)
    text: str
    pos: Literal[
        "auto", "above", "below", "left", "right",
        "above left", "above right", "below left", "below right",
    ] = "auto"

    @model_validator(mode="after")
    def _check_form(self) -> "LabelAngle":
        has_explicit = all(v is not None for v in [self.a, self.vertex, self.b])
        has_shorthand = self.at is not None and self.of is not None
        if has_explicit == has_shorthand:
            raise ValueError(
                "label_angle: specify exactly one of (a, vertex, b) or (at, of)"
            )
        return self


AnnotationMark = Annotated[
    Union[MarkAngle, MarkRightAngle, MarkEqualLengths, MarkParallel, MarkProportional],
    Field(discriminator="kind")
]


# ---------------------------------------------------------------------------
# DSL checks (typed; validated at parse time; lowering consumption TBD)
# ---------------------------------------------------------------------------

class CheckDistance(BaseModel):
    """Assert distance between two points equals expected."""
    model_config = ConfigDict(extra="forbid")
    check: Literal["distance"] = "distance"
    points: list[str]   # [A, B]
    expected: float


class CheckParallel(BaseModel):
    """Assert two segments are parallel."""
    model_config = ConfigDict(extra="forbid")
    check: Literal["parallel"] = "parallel"
    seg1: list[str]     # [A, B]
    seg2: list[str]     # [C, D]


class CheckPerpendicular(BaseModel):
    """Assert two segments are perpendicular."""
    model_config = ConfigDict(extra="forbid")
    check: Literal["perpendicular"] = "perpendicular"
    seg1: list[str]
    seg2: list[str]


class CheckAngleEquals(BaseModel):
    """Assert angle at vertex (a–vertex–b) equals expected degrees."""
    model_config = ConfigDict(extra="forbid")
    check: Literal["angle_equals"] = "angle_equals"
    points: list[str]   # [a, vertex, b]
    expected: float     # degrees


class CheckCollinear(BaseModel):
    """Assert 3+ points are collinear."""
    model_config = ConfigDict(extra="forbid")
    check: Literal["collinear"] = "collinear"
    points: list[str]   # 3 or more point IDs


class CheckPointOnCircle(BaseModel):
    """Assert a point lies on a circle."""
    model_config = ConfigDict(extra="forbid")
    check: Literal["on_circle"] = "on_circle"
    point: str
    circle: str


class CheckTangent(BaseModel):
    """Assert two objects are tangent."""
    model_config = ConfigDict(extra="forbid")
    check: Literal["tangent"] = "tangent"
    obj1: str
    obj2: str


DSLCheck = Annotated[
    Union[
        CheckDistance, CheckParallel, CheckPerpendicular,
        CheckAngleEquals, CheckCollinear, CheckPointOnCircle,
        CheckTangent,
    ],
    Field(discriminator="check"),
]

AnnotationLabel = Annotated[
    Union[LabelSegment, LabelPoint, LabelAngle],
    Field(discriminator="kind")
]


class DrawObj(BaseModel):
    """Explicit draw directive for a single element.

    Use ``obj`` to reference an existing construction ID (triangle, segment, etc.)
    or ``endpoints`` as a vertex-pair shorthand — the lowerer auto-creates the
    segment def via ``_ensure_segment``.

    ``style`` accepts:
    - a string: a named key into ``annotations.styles``, or a bare TikZ color
      name like ``"red"`` that ``_style_str`` in ``to_tikz.py`` recognises.
    - a dict: inline TikZ style properties, e.g. ``{"color": "red", "thick": True}``.
      The lowerer registers these in ``DiagramIR.styles`` under an auto-generated key.
    """
    model_config = ConfigDict(extra="forbid")
    obj: Optional[str] = None
    endpoints: Optional[list[str]] = None
    style: Optional[Union[str, dict[str, Any]]] = None

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "DrawObj":
        if self.obj is None and self.endpoints is None:
            raise ValueError("DrawObj requires either 'obj' or 'endpoints'")
        if self.obj is not None and self.endpoints is not None:
            raise ValueError("DrawObj: specify 'obj' or 'endpoints', not both")
        return self


# ---------------------------------------------------------------------------
# Annotations
# ---------------------------------------------------------------------------

class DSLAnnotations(BaseModel):
    model_config = ConfigDict(extra="allow")  # allow extra annotation keys for future use
    auto_draw_all: bool = True
    auto_label_points: bool = True
    auto_mark_right_angles: bool = False
    draws: list[DrawObj] = Field(default_factory=list)
    marks: list[AnnotationMark] = Field(default_factory=list)
    labels: list[AnnotationLabel] = Field(default_factory=list)
    styles: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Top-level RecipeDSL
# ---------------------------------------------------------------------------

class RecipeDSL(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["abstract", "grid", "mixed"] = "abstract"
    construction: list[DSLOp]
    annotations: DSLAnnotations = Field(default_factory=DSLAnnotations)
    checks: list[DSLCheck] = Field(default_factory=list)
    # Note: checks are validated at parse time but not yet consumed by the lowerer.
    # Lowerer auto-generates checks from construction ops. Explicit check
    # consumption is a planned follow-on (see design spec section 2.3).

    @model_validator(mode="before")
    @classmethod
    def check_reserved_ids(cls, data: Any) -> Any:
        """Reject any construction op whose id starts with '__'."""
        construction = data.get("construction", [])
        for op in construction:
            if isinstance(op, dict):
                id_ = op.get("id", "")
                if isinstance(id_, str) and id_.startswith("__"):
                    raise ValueError(
                        f"IDs starting with '__' are reserved for lowering intermediates; got {id_!r}"
                    )
        return data
