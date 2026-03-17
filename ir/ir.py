from __future__ import annotations

from typing import Annotated, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, ConfigDict

# -----------------------
# IDs
# -----------------------

PointId = str
LineId = str
SegmentId = str
RayId = str
CircleId = str
TriangleId = str
PolygonId = str
StyleId = str
ObjId = str  # compiler resolves actual type (line/segment/ray/circle/triangle/polygon)


# -----------------------
# Params / Canvas
# -----------------------

class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assign: Dict[str, Union[int, float, str]] = Field(default_factory=dict)


class Canvas(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["cartesian"] = "cartesian"
    xmin: float = -5
    xmax: float = 5
    ymin: float = -5
    ymax: float = 5
    grid: bool = False
    grid_step: float = 1.0
    axes: bool = False
    tick_step: float = 1.0
    show_ticks: bool = False
    show_tick_labels: bool = False
    show_axis_labels: bool = False
    clip: bool = True


class PointOnMethod(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str


class PointOnRandom(PointOnMethod):
    kind: Literal["random"] = "random"


class PointOnParam(PointOnMethod):
    kind: Literal["param"] = "param"
    # For lines/segments/rays: parameter along object; compiler decides mapping
    # For circles: parameter interpreted as angle in radians by convention
    t: float



# -----------------------
# Spatial constraints for PointOnIntent
# -----------------------

class SpatialConstraintBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str


class SameSideConstraint(SpatialConstraintBase):
    """Point must be on the same side of the given line as ref."""
    kind: Literal["same_side"] = "same_side"
    line: List[PointId]  # exactly 2 point IDs defining the line
    ref: PointId


class NotNearConstraint(SpatialConstraintBase):
    """Point must be at least min_dist away from the given reference point."""
    kind: Literal["not_near"] = "not_near"
    point: PointId
    min_dist: float = 0.5


class ArcBetweenConstraint(SpatialConstraintBase):
    """For circles: point must be on the arc from from_point to to_point (CCW).
    NOTE: enforcement is not yet implemented — accepted in schema but currently no-ops.
    Do NOT document this constraint to the LLM until it is implemented."""
    kind: Literal["arc_between"] = "arc_between"
    from_point: PointId
    to_point: PointId


class BeyondConstraint(SpatialConstraintBase):
    """Point must be beyond ref_point along the object's natural parameterization.
    NOTE: enforcement is not yet implemented — accepted in schema but currently no-ops.
    Do NOT document this constraint to the LLM until it is implemented."""
    kind: Literal["beyond"] = "beyond"
    ref: PointId


SpatialConstraint = Annotated[
    Union[SameSideConstraint, NotNearConstraint, ArcBetweenConstraint, BeyondConstraint],
    Field(discriminator="kind")
]


class PointOnIntent(PointOnMethod):
    """Constraint-based placement: compiler samples until all constraints are satisfied."""
    kind: Literal["intent"] = "intent"
    constraints: List[SpatialConstraint]


PointOnHow = Annotated[Union[PointOnRandom, PointOnParam, PointOnIntent], Field(discriminator="kind")]


# -----------------------
# Angle specs
# -----------------------

class AnglePoints(BaseModel):
    """Classic (a, o, b) point triple: angle at o, from ray oa to ray ob."""
    model_config = ConfigDict(extra="forbid")
    a: PointId
    o: PointId
    b: PointId


# AngleSpec is just AnglePoints; kept as alias for forward-compatible field annotations
AngleSpec = AnglePoints


# -----------------------
# Picking / disambiguation
# -----------------------

class PickBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str


class PickIndex(PickBase):
    kind: Literal["index"] = "index"
    k: int = 0


class PickOnObject(PickBase):
    """
    Choose the candidate point that lies on `obj` (segment/ray/line/circle),
    using SymPy .contains when available.
    """
    kind: Literal["on_object"] = "on_object"
    obj: ObjId


class PickClosestTo(PickBase):
    kind: Literal["closest_to"] = "closest_to"
    p: PointId


class PickSameSide(PickBase):
    kind: Literal["same_side"] = "same_side"
    line: List[PointId]  # oriented line through (a,b), expects exactly 2 elements
    ref_point: PointId


class PickInsideTriangle(PickBase):
    kind: Literal["inside_triangle"] = "inside_triangle"
    tri: TriangleId


PickRule = Annotated[
    Union[PickIndex, PickOnObject, PickClosestTo, PickSameSide, PickInsideTriangle],
    Field(discriminator="kind")
]


# -----------------------
# Definitions (DAG)
# -----------------------

class DefBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: str


class PointFixed(DefBase):
    kind: Literal["point_fixed"] = "point_fixed"
    x: Union[int, float, str]
    y: Union[int, float, str]


class PointFree(DefBase):
    kind: Literal["point_free"] = "point_free"
    hint_xy: Optional[List[float]] = None  # soft preferred location [x, y]; compiler may ignore


class PointOn(DefBase):
    kind: Literal["point_on"] = "point_on"
    on: ObjId
    how: PointOnHow


class Segment(DefBase):
    kind: Literal["segment"] = "segment"
    a: PointId
    b: PointId


class Ray(DefBase):
    kind: Literal["ray"] = "ray"
    a: PointId
    b: PointId  # ray from a through b


class LineThrough(DefBase):
    kind: Literal["line_through"] = "line_through"
    p: PointId
    q: PointId


class LineParallelThrough(DefBase):
    kind: Literal["line_parallel_through"] = "line_parallel_through"
    through: PointId
    to_line: LineId


class LinePerpendicularThrough(DefBase):
    kind: Literal["line_perp_through"] = "line_perp_through"
    through: PointId
    to_line: LineId


class CircleCenterPoint(DefBase):
    kind: Literal["circle_center_point"] = "circle_center_point"
    center: PointId
    through: PointId


class CircleCenterRadius(DefBase):
    kind: Literal["circle_center_radius"] = "circle_center_radius"
    center: PointId
    radius: Union[int, float, str]


class CircleThrough3(DefBase):
    kind: Literal["circle_through3"] = "circle_through3"
    a: PointId
    b: PointId
    c: PointId


class Triangle(DefBase):
    kind: Literal["triangle"] = "triangle"
    a: PointId
    b: PointId
    c: PointId


class Polygon(DefBase):
    """Closed polygon with 3+ vertices (in order). Subsumes Triangle for drawing."""
    kind: Literal["polygon"] = "polygon"
    points: List[PointId]  # 3 or more, closed automatically


class PointMidpoint(DefBase):
    """Midpoint of segment PQ. Semantic sugar over PointOn(param=0.5)."""
    kind: Literal["point_midpoint"] = "point_midpoint"
    p: PointId
    q: PointId


class PointFoot(DefBase):
    """Foot of the perpendicular from `source` to the line containing `onto`.
    Works for line/segment/ray — always projects onto the infinite line."""
    kind: Literal["point_foot"] = "point_foot"
    source: PointId
    onto: ObjId


class PointBetween(DefBase):
    """A point on the segment from `a` to `b` at position given by `ratio`.

    ratio: float 0-1 (fraction from a toward b), or string "m:n" (m parts
           from a, n parts toward b). Defaults to 0.5 (midpoint).
    """
    kind: Literal["point_between"] = "point_between"
    a: PointId
    b: PointId
    ratio: Optional[Union[float, str]] = None


class PointTriangleCenter(DefBase):
    """Named center of a triangle. Maps to Triangle(a,b,c).<which> in SymPy."""
    kind: Literal["point_triangle_center"] = "point_triangle_center"
    tri: TriangleId
    which: Literal["circumcenter", "incenter", "centroid", "orthocenter"]


class LineAngleBisector(DefBase):
    """Line bisecting angle A-vertex-B."""
    kind: Literal["line_angle_bisector"] = "line_angle_bisector"
    a: PointId
    vertex: PointId
    b: PointId


class LineTangent(DefBase):
    """Tangent line from an external point to a circle. Maps to Circle.tangent_lines(point)."""
    kind: Literal["line_tangent"] = "line_tangent"
    point: PointId
    circle: CircleId
    pick: Optional[PickRule] = None


class PointRotate(DefBase):
    """Point obtained by rotating source around center by angle (radians). Maps to Point.rotate()."""
    kind: Literal["point_rotate"] = "point_rotate"
    center: PointId
    source: PointId
    angle: Union[int, float, str]  # radians; str allows symbolic (e.g. "pi/2")


class PointReflect(DefBase):
    """Reflection of `source` across a point (point symmetry) or line/segment/ray (mirror)."""
    kind: Literal["point_reflect"] = "point_reflect"
    source: PointId
    across: ObjId  # a PointId (point reflection) or LineId/SegmentId/RayId (mirror)


class PointIntersection(DefBase):
    """
    Intersection of two objects intended to yield a single point.
    Compiler computes candidates via SymPy and applies pick to disambiguate.
    """
    kind: Literal["point_intersection"] = "point_intersection"
    obj1: ObjId
    obj2: ObjId
    pick: Optional[PickRule] = None


DefStmt = Annotated[
    Union[
        PointFixed, PointFree, PointOn, PointMidpoint, PointFoot, PointBetween, PointRotate, PointReflect,
        PointTriangleCenter, PointIntersection,
        Segment, Ray,
        LineThrough, LineParallelThrough, LinePerpendicularThrough,
        LineAngleBisector, LineTangent,
        CircleCenterPoint, CircleCenterRadius, CircleThrough3,
        Triangle, Polygon,
    ],
    Field(discriminator="kind")
]


# -----------------------
# Checks (predicates)
# -----------------------

class CheckBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    level: Literal["must", "prefer"] = "must"
    tol: Optional[float] = None


class DistinctPoints(CheckBase):
    kind: Literal["distinct_points"] = "distinct_points"
    a: PointId
    b: PointId


class DistinctObjects(CheckBase):
    kind: Literal["distinct_objects"] = "distinct_objects"
    a: ObjId
    b: ObjId


class NonCollinear(CheckBase):
    kind: Literal["non_collinear"] = "non_collinear"
    a: PointId
    b: PointId
    c: PointId


class Contains(CheckBase):
    kind: Literal["contains"] = "contains"
    p: PointId
    obj: ObjId


class NotContains(CheckBase):
    kind: Literal["not_contains"] = "not_contains"
    p: PointId
    obj: ObjId


class Parallel(CheckBase):
    kind: Literal["parallel"] = "parallel"
    l1: LineId
    l2: LineId


class NotParallel(CheckBase):
    kind: Literal["not_parallel"] = "not_parallel"
    l1: LineId
    l2: LineId


class Perpendicular(CheckBase):
    kind: Literal["perpendicular"] = "perpendicular"
    l1: LineId
    l2: LineId


class AngleEqual(CheckBase):
    kind: Literal["angle_equal"] = "angle_equal"
    a1: AngleSpec
    a2: AngleSpec


class SimilarTriangles(CheckBase):
    kind: Literal["similar_triangles"] = "similar_triangles"
    t1: TriangleId
    t2: TriangleId
    # Optional correspondence for labeling/ratios; compiler can validate consistency
    correspond: Optional[List[List[PointId]]] = None  # each inner list is [t1_vertex, t2_vertex]


class RatioEqual(CheckBase):
    """
    |s1|/|s2| == |s3|/|s4|
    """
    kind: Literal["ratio_equal"] = "ratio_equal"
    s1: SegmentId
    s2: SegmentId
    s3: SegmentId
    s4: SegmentId


class Collinear(CheckBase):
    """Three or more points are collinear. Maps to Point.is_collinear(...)."""
    kind: Literal["collinear"] = "collinear"
    points: List[PointId]  # 3+


class EqualLength(CheckBase):
    """All listed segments have the same length."""
    kind: Literal["equal_length"] = "equal_length"
    segs: List[SegmentId]  # 2+


class RightAngle(CheckBase):
    """Angle a-o-b is 90 degrees."""
    kind: Literal["right_angle"] = "right_angle"
    angle: AngleSpec


class Tangent(CheckBase):
    """A line/ray/segment is tangent to a circle. Maps to Line.is_tangent(circle)."""
    kind: Literal["tangent"] = "tangent"
    line: ObjId
    circle: CircleId


Check = Annotated[
    Union[
        DistinctPoints, DistinctObjects,
        NonCollinear, Collinear,
        Contains, NotContains,
        Parallel, NotParallel, Perpendicular,
        RightAngle, AngleEqual,
        EqualLength, RatioEqual,
        SimilarTriangles,
        Tangent,
    ],
    Field(discriminator="kind")
]


# -----------------------
# Render ops (semantic)
# -----------------------

class RenderBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    style: Optional[StyleId] = None


class Draw(RenderBase):
    kind: Literal["draw"] = "draw"
    obj: ObjId
    # Optional for infinite lines: tkzDrawLine add=... style, etc.
    add: Optional[List[float]] = None  # [forward, backward] extensions


class DrawPoints(RenderBase):
    kind: Literal["draw_points"] = "draw_points"
    points: List[PointId]


class MarkAngles(RenderBase):
    kind: Literal["mark_angles"] = "mark_angles"
    angles: List[AngleSpec]
    which: Literal["interior", "exterior", "reflex"] = "interior"
    group: Optional[str] = None


class MarkSegments(RenderBase):
    kind: Literal["mark_segments"] = "mark_segments"
    segs: List[SegmentId]
    group: Optional[str] = None


class LabelPoint(RenderBase):
    kind: Literal["label_point"] = "label_point"
    p: PointId
    text: Optional[str] = None
    pos: Literal["auto", "above", "below", "left", "right"] = "auto"


class LabelAngle(RenderBase):
    kind: Literal["label_angle"] = "label_angle"
    angle: AngleSpec
    text: str
    pos: Optional[float] = None  # tkz label pos fraction if you want


class LabelSegment(RenderBase):
    kind: Literal["label_segment"] = "label_segment"
    seg: SegmentId
    text: str
    pos: Optional[float] = None


class MarkRightAngles(RenderBase):
    """Emits the square symbol at each angle. Distinct from MarkAngles (arc)."""
    kind: Literal["mark_right_angles"] = "mark_right_angles"
    angles: List[AngleSpec]


class Fill(RenderBase):
    """Fill a closed object (polygon, triangle, circle) with optional opacity."""
    kind: Literal["fill"] = "fill"
    obj: ObjId
    opacity: float = 1.0


RenderOp = Annotated[
    Union[
        Draw, DrawPoints, Fill,
        MarkAngles, MarkRightAngles, MarkSegments,
        LabelPoint, LabelAngle, LabelSegment,
    ],
    Field(discriminator="kind")
]


# -----------------------
# Top-level IR
# -----------------------

class DiagramIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    params: Optional[Params] = None
    canvas: Optional[Canvas] = None

    define: List[DefStmt]
    checks: List[Check] = Field(default_factory=list)
    render: List[RenderOp] = Field(default_factory=list)

    styles: Dict[str, Dict[str, Union[str, int, float, bool]]] = Field(default_factory=dict)
