# geometry_diagrams/pydsl/api.py
"""Public builder-shim API. Every function here records an op against the
ambient Builder (see builder.py) and returns a handle."""
from __future__ import annotations

import math

from geometry_diagrams.ir.ir import AnglePoints, CircleCenterRadius, Draw, DrawPoints, LineAngleBisector, LineParallelThrough, LinePerpendicularThrough, LineThrough, MarkAngles, MarkSegments, PointDilate, PointFixed, PointFoot, PointMidpoint, PointOn, PointOnParam, PointReflect, PointRotate, PointTriangleCenter
from geometry_diagrams.ir.ir import Polygon as PolygonDef
from geometry_diagrams.ir.ir import Segment as SegmentDef
from geometry_diagrams.ir.ir import Triangle as TriangleDef
from geometry_diagrams.pydsl.builder import get_builder
from geometry_diagrams.pydsl.handles import AngleRef, Altitude, Arc, Circle, Ellipse, Line, Median, PerpendicularBisectorLine, Point, Polygon, Polyline, Ray, Sector, Segment, Triangle, _record_literal_point, _sanitize_label_text

_TARGET_LINES = 10        # nice-step heuristic aims for roughly this many grid/tick lines
_MAX_GRID_LINES = 500     # backstop for an explicit override, not the common path


def _nice_step(span: float, target_lines: float = _TARGET_LINES) -> float:
    """Round span/target_lines up to a 'nice' number: 1, 2, or 5 times a power
    of 10 — the same heuristic chart libraries use for axis tick spacing.
    E.g. span=8 -> 1.0; span=500 -> 50.0; span=1000 -> 100.0."""
    if span <= 0:
        return 1.0
    raw = span / target_lines
    magnitude = 10 ** math.floor(math.log10(raw))
    residual = raw / magnitude
    if residual < 1.5:
        nice = 1
    elif residual < 3:
        nice = 2
    elif residual < 7:
        nice = 5
    else:
        nice = 10
    return nice * magnitude


def point(x: float, y: float) -> Point:
    """A point fixed at literal coordinates (x, y)."""
    builder = get_builder()
    pid = builder._fresh_hidden_id("pt")
    builder._add(PointFixed(id=pid, x=x, y=y))
    builder._coord_floats[pid] = (float(x), float(y))
    return Point(id=pid, _builder=builder, _x=float(x), _y=float(y))


def line_through(p: Point, q: Point) -> Line:
    """The line through two points."""
    builder = get_builder()
    lid = builder._fresh_hidden_id("line")
    builder._add(LineThrough(id=lid, p=p.id, q=q.id))
    return Line(id=lid)


def ray(a: Point, b: Point) -> Ray:
    """A ray starting at a, extending through and beyond b."""
    from geometry_diagrams.ir.ir import Ray as RayDef

    builder = get_builder()
    rid = builder._fresh_hidden_id("ray")
    builder._add(RayDef(id=rid, a=a.id, b=b.id))
    return Ray(id=rid)


def triangle(a: Point, b: Point, c: Point) -> Triangle:
    """A triangle over three existing points."""
    builder = get_builder()
    tid = builder._fresh_hidden_id("tri")
    builder._add(TriangleDef(id=tid, a=a.id, b=b.id, c=c.id))
    return Triangle(id=tid, vertices=(a, b, c), _builder=builder)


def polygon(*vertices: Point) -> Polygon:
    """A polygon over 3 or more points, in perimeter order. The shape is
    closed automatically — the last point connects back to the first.
    Do not repeat the first point at the end; that produces a
    coincident-vertex error rather than a no-op."""
    if len(vertices) < 3:
        raise ValueError(f"polygon requires at least 3 vertices, got {len(vertices)}")
    n = len(vertices)
    for i in range(n):
        prev, cur = vertices[i - 1], vertices[i]  # i=0 wraps to last->first
        if prev._x is None or prev._y is None or cur._x is None or cur._y is None:
            continue
        if math.hypot(cur._x - prev._x, cur._y - prev._y) < 1e-9:
            raise ValueError(
                f"polygon() vertices {prev.id!r} and {cur.id!r} are coincident. "
                "polygon() already closes the shape automatically — do not repeat "
                "the first point as the last."
            )
    builder = get_builder()
    pid = builder._fresh_hidden_id("poly")
    builder._add(PolygonDef(id=pid, points=[v.id for v in vertices]))
    return Polygon(id=pid, vertices=tuple(vertices), _builder=builder)


def polyline(*points: Point) -> Polyline:
    """An open chain of 2 or more points, drawn in order with NO closing
    edge back to the first point (unlike polygon()). Only CONSECUTIVE
    coincident points are rejected — the first and last points ARE allowed
    to coincide (e.g. a closed-looking traced path), since polyline()
    never adds a wraparound edge the way polygon() does."""
    if len(points) < 2:
        raise ValueError(f"polyline requires at least 2 points, got {len(points)}")
    for i in range(1, len(points)):
        prev, cur = points[i - 1], points[i]
        if prev._x is None or prev._y is None or cur._x is None or cur._y is None:
            continue
        if math.hypot(cur._x - prev._x, cur._y - prev._y) < 1e-9:
            raise ValueError(
                f"polyline() vertices {prev.id!r} and {cur.id!r} are coincident "
                "consecutive points."
            )
    from geometry_diagrams.ir.ir import PolylineOpen

    builder = get_builder()
    pid = builder._fresh_hidden_id("polyline")
    builder._add(PolylineOpen(id=pid, points=[p.id for p in points]))
    return Polyline(id=pid, vertices=tuple(points), _builder=builder)


def regular_polygon(center: Point, radius: float, n: int, start_angle: float = 0.0) -> Polygon:
    """A regular n-gon centered at `center` with circumradius `radius`.
    start_angle (radians) rotates the first vertex; n must be >= 3."""
    if n < 3:
        raise ValueError(f"regular_polygon() requires n >= 3, got {n}")
    builder = get_builder()
    pts = []
    for i in range(n):
        angle = start_angle + i * 2 * math.pi / n
        x = center.x + radius * math.cos(angle)
        y = center.y + radius * math.sin(angle)
        pts.append(_record_literal_point(builder, x, y))
    return polygon(*pts)


def rectangle(
    corner: Point,
    width: float,
    height: float,
    rotation: float = 0.0,
    pivot: str = "center",
) -> Polygon:
    """An axis-aligned-before-rotation rectangle: `corner` is one corner in
    the unrotated frame, extending by width/height. `rotation` (radians, CCW)
    then rotates all four corners around either the rectangle's own center
    (pivot="center", default — the shape spins in place) or around `corner`
    itself (pivot="corner"). pivot must be "center" or "corner"."""
    if pivot not in ("center", "corner"):
        raise ValueError(f"rectangle(): pivot must be 'center' or 'corner', got {pivot!r}")
    builder = get_builder()
    corners = [
        (corner.x, corner.y),
        (corner.x + width, corner.y),
        (corner.x + width, corner.y + height),
        (corner.x, corner.y + height),
    ]
    if pivot == "center":
        cx = sum(c[0] for c in corners) / 4
        cy = sum(c[1] for c in corners) / 4
    else:
        cx, cy = corner.x, corner.y
    cos_r, sin_r = math.cos(rotation), math.sin(rotation)
    pts = []
    for x, y in corners:
        rx = cx + (x - cx) * cos_r - (y - cy) * sin_r
        ry = cy + (x - cx) * sin_r + (y - cy) * cos_r
        pts.append(_record_literal_point(builder, rx, ry))
    return polygon(*pts)


def walk(from_point: Point, heading: float, distance: float) -> Point:
    """A point `distance` away from from_point in direction `heading`
    (radians, counter-clockwise from the +x axis — same convention as
    rotate_point()). Use in a loop with your own running heading to build a
    polygon's vertices one side at a time, then pass the collected points to
    polygon(*pts):
        pts, h = [start], 0.0
        for side, turn in steps:
            pts.append(walk(pts[-1], h, side))
            h += turn
        poly = polygon(*pts)
    """
    builder = get_builder()
    x = from_point.x + distance * math.cos(heading)
    y = from_point.y + distance * math.sin(heading)
    return _record_literal_point(builder, x, y)


def distance(p: Point, q: Point) -> float:
    """The distance between p and q — works for any two points once both
    positions are determined, not just point(x, y) literals."""
    return math.hypot(p.x - q.x, p.y - q.y)


def segment(p: Point, q: Point) -> Segment:
    """A segment between any two points (deduplicated with segments already
    obtained via Triangle.side()/Polygon.side() for the same pair)."""
    if p.id == q.id:
        raise ValueError(f"segment() needs two distinct points, got {p.id!r} twice")
    builder = get_builder()
    return builder._get_or_create_segment(p.id, q.id)


def circumcircle(t: Triangle) -> Circle:
    """The circumscribed circle of a triangle.

    The IR itself doesn't need a radius value for the SymPy resolution path
    (CircleCenterPoint's "through" point already pins the circle's size);
    `.radius` on the returned handle is purely a convenience value for the
    script. It's computed lazily (see Circle.radius) via R = (a*b*c)/(4*Area),
    which — like incircle's Heron-formula inradius below — depends only on
    the triangle's side lengths, so it's computable whenever all three
    vertices are concrete (PointFixed) coordinates, tracked in
    builder._coord_floats.
    """
    from geometry_diagrams.ir.ir import CircleCenterPoint

    builder = get_builder()
    center_id = builder._fresh_hidden_id("circumcenter")
    builder._add(PointTriangleCenter(id=center_id, tri=t.id, which="circumcenter"))
    a_id, b_id, c_id = (v.id for v in t.vertices)
    cid = builder._fresh_hidden_id("circumcircle")
    builder._add(CircleCenterPoint(id=cid, center=center_id, through=a_id))

    def _compute_radius():
        coord_floats = builder._coord_floats
        if not all(v in coord_floats for v in (a_id, b_id, c_id)):
            raise NotImplementedError(
                "circumcircle(...).radius requires all three vertices to be "
                "concrete point(x, y) literals in Phase 1a."
            )
        ax, ay = coord_floats[a_id]
        bx, by = coord_floats[b_id]
        cx, cy = coord_floats[c_id]
        side_a = math.hypot(bx - cx, by - cy)
        side_b = math.hypot(ax - cx, ay - cy)
        side_c = math.hypot(ax - bx, ay - by)
        area = abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay)) / 2
        if area == 0:
            raise ValueError(
                f"circumcircle(...).radius: vertices {a_id!r}, {b_id!r}, {c_id!r} "
                "are collinear — a circumradius doesn't exist for a degenerate triangle."
            )
        return round((side_a * side_b * side_c) / (4 * area), 10)

    return Circle(id=cid, center=Point(id=center_id, _builder=builder), _radius_thunk=_compute_radius, _from_derived_center=True)


def incircle(t: Triangle) -> Circle:
    """The inscribed circle of a triangle.

    Mirrors geometry_diagrams/recipe/lower.py's _lower_incircle: computes the
    inradius numerically via Heron's formula when all three vertices are
    already concrete (PointFixed) coordinates, tracked in builder._coord_floats;
    falls back to a symbolic length-expression string otherwise. This is
    replicating an existing output-computation, not new eager validation —
    no script is ever rejected by this logic.
    """
    builder = get_builder()
    center_id = builder._fresh_hidden_id("incenter")
    builder._add(PointTriangleCenter(id=center_id, tri=t.id, which="incenter"))
    a_id, b_id, c_id = (v.id for v in t.vertices)
    cid = builder._fresh_hidden_id("incircle")

    coord_floats = builder._coord_floats
    if all(v in coord_floats for v in (a_id, b_id, c_id)):
        ax, ay = coord_floats[a_id]
        bx, by = coord_floats[b_id]
        cx, cy = coord_floats[c_id]
        side_a = math.hypot(bx - cx, by - cy)
        side_b = math.hypot(ax - cx, ay - cy)
        side_c = math.hypot(ax - bx, ay - by)
        s = (side_a + side_b + side_c) / 2
        area = abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay)) / 2
        radius: "float | str" = round(area / s, 10)
    else:
        radius = (
            f"sqrt((length({b_id},{c_id})+length({a_id},{c_id})+length({a_id},{b_id}))/2 - length({b_id},{c_id})) "
            f"* sqrt((length({b_id},{c_id})+length({a_id},{c_id})+length({a_id},{b_id}))/2 - length({a_id},{c_id})) "
            f"* sqrt((length({b_id},{c_id})+length({a_id},{c_id})+length({a_id},{b_id}))/2 - length({a_id},{b_id})) "
            f"/ sqrt((length({b_id},{c_id})+length({a_id},{c_id})+length({a_id},{b_id}))/2)"
        )
    builder._add(CircleCenterRadius(id=cid, center=center_id, radius=radius))
    return Circle(id=cid, center=Point(id=center_id, _builder=builder), _radius_thunk=lambda: radius, _from_derived_center=True)


def circle(center: Point, radius: float) -> Circle:
    """A circle with the given center and radius."""
    if radius <= 0:
        raise ValueError(f"circle(): radius must be positive, got {radius!r}")
    builder = get_builder()
    cid = builder._fresh_hidden_id("circle")
    builder._add(CircleCenterRadius(id=cid, center=center.id, radius=radius))
    return Circle(id=cid, center=center, _radius_thunk=lambda: radius)


def _validate_on_circle(fn_name: str, circle: Circle, point: Point, point_role: str) -> None:
    """Raise if point is knowably NOT on circle. Skipped (no raise) whenever
    circle.center's coordinates, point's coordinates, or circle.radius can't
    currently be resolved to concrete numbers — same "validate only what's
    knowable" policy as circumcircle(...).radius's NotImplementedError
    fallback. Checking both start and end (not just start) matters: an
    off-circle end can be swapped into the rendered anchor position by
    render_util.py's arc_params, corrupting the diagram just as much as an
    off-circle start would."""
    cx, cy = circle.center._x, circle.center._y
    px, py = point._x, point._y
    if cx is None or cy is None or px is None or py is None:
        return
    try:
        radius = circle.radius
    except NotImplementedError:
        return
    if isinstance(radius, str):
        return  # defense-in-depth only: a str radius only ever comes from
                 # incircle()'s symbolic fallback, whose center is always
                 # unknown too — the cx is None check above already returns
                 # first in every real case, so this branch is intentionally
                 # unreachable today.
    actual = math.hypot(px - cx, py - cy)
    if abs(actual - radius) > max(radius * 1e-6, 1e-9):
        raise ValueError(
            f"{fn_name}(): {point_role} point {point.id!r} is not on the given "
            f"circle (distance {actual:.6g} from center, circle radius is "
            f"{radius:.6g}). Use point_on(circle, angle) to get a point "
            "guaranteed to lie on the circle."
        )


def _validate_on_ellipse(fn_name: str, ellipse: Ellipse, point: Point, point_role: str) -> None:
    """Raise if point is knowably NOT on ellipse. Mirrors _validate_on_circle's
    skip policy exactly, but checks the ellipse equation
    ((px-cx)/hr)**2 + ((py-cy)/vr)**2 == 1 within tolerance instead of a
    simple distance check."""
    cx, cy = ellipse.center._x, ellipse.center._y
    px, py = point._x, point._y
    if cx is None or cy is None or px is None or py is None:
        return
    try:
        hr, vr = ellipse.hradius, ellipse.vradius
    except NotImplementedError:
        return
    value = ((px - cx) / hr) ** 2 + ((py - cy) / vr) ** 2
    if abs(value - 1.0) > 1e-6:
        raise ValueError(
            f"{fn_name}(): {point_role} point {point.id!r} is not on the given "
            f"ellipse (({point_role} - center normalized) evaluates to {value:.6g}, "
            "expected 1.0). Use point_on(ellipse, angle) to get a point "
            "guaranteed to lie on the ellipse."
        )


def _arc_or_sector(kind: str, shape, start: Point, end: Point, reflex: bool) -> str:
    """Build and record the correct IR def (circular or elliptical
    arc/sector) based on whether shape is a Circle or Ellipse. Returns the
    fresh id. kind is "arc" or "sector"."""
    from geometry_diagrams.ir.ir import (
        ArcCenterStartEnd, EllipticalArcCenterStartEnd,
        EllipticalSectorCenterStartEnd, SectorCenterStartEnd,
    )

    if isinstance(shape, Ellipse):
        _validate_on_ellipse(kind, shape, start, "start")
        _validate_on_ellipse(kind, shape, end, "end")
        try:
            hradius, vradius = shape.hradius, shape.vradius
        except NotImplementedError:
            raise ValueError(
                f"{kind}(): shape's hradius/vradius aren't resolvable yet — "
                "this happens for an ellipse(corner1=..., corner2=...) built "
                "from non-literal corners. Use a literal ellipse(center=...) "
                "or a circle() instead."
            )
        builder = get_builder()
        new_id = builder._fresh_hidden_id(kind)
        def_cls = EllipticalArcCenterStartEnd if kind == "arc" else EllipticalSectorCenterStartEnd
        builder._add(def_cls(
            id=new_id, center=shape.center.id, hradius=hradius,
            vradius=vradius, start=start.id, end=end.id, reflex=reflex,
        ))
    else:
        _validate_on_circle(kind, shape, start, "start")
        _validate_on_circle(kind, shape, end, "end")
        builder = get_builder()
        new_id = builder._fresh_hidden_id(kind)
        def_cls = ArcCenterStartEnd if kind == "arc" else SectorCenterStartEnd
        builder._add(def_cls(id=new_id, center=shape.center.id, start=start.id, end=end.id, reflex=reflex))
    return new_id


def arc(shape: "Circle | Ellipse", start: Point, end: Point, reflex: bool = False) -> Arc:
    """The arc between start and end along the boundary of shape (a circle()
    or ellipse()) — both must lie on shape; use point_on(shape, t) to
    construct them (an off-boundary point can silently shift the rendered
    arc away from shape). reflex=False (the default) draws whichever of the
    two arcs spans <=180°; reflex=True draws the other one."""
    aid = _arc_or_sector("arc", shape, start, end, reflex)
    return Arc(id=aid)


def sector(shape: "Circle | Ellipse", start: Point, end: Point, reflex: bool = False) -> Sector:
    """The closed pie-slice region bounded by the two radii to start and end
    and the arc between them, on shape (a circle() or ellipse()). Same
    start/end contract as arc() — see its docstring."""
    sid = _arc_or_sector("sector", shape, start, end, reflex)
    return Sector(id=sid)


def regular_sectors(circle: Circle, n: int) -> tuple[Sector, ...]:
    """Divide circle into n equal pie slices, returned in counter-clockwise
    order starting from angle 0. n must be >= 2. circle must be a literal
    circle() (not circumcircle()/incircle()) — same restriction
    regular_polygon() already has on its own center parameter."""
    if n < 2:
        raise ValueError(f"regular_sectors() requires n >= 2, got {n}")
    if circle._from_derived_center:
        raise ValueError(
            "regular_sectors(): circle must be a literal circle(), not "
            "circumcircle()/incircle()"
        )
    radius = circle.radius
    builder = get_builder()
    boundary_pts = []
    for i in range(n):
        angle = i * 2 * math.pi / n
        # Round the OFFSET, not the absolute coordinate — see this plan's
        # Global Constraints section for why this exact distinction matters.
        x = circle.center.x + round(radius * math.cos(angle), 10)
        y = circle.center.y + round(radius * math.sin(angle), 10)
        boundary_pts.append(_record_literal_point(builder, x, y))
    return tuple(
        sector(circle, boundary_pts[i], boundary_pts[(i + 1) % n])
        for i in range(n)
    )


def ellipse(
    center: "Point | None" = None,
    hradius: "float | None" = None,
    vradius: "float | None" = None,
    corner1: "Point | None" = None,
    corner2: "Point | None" = None,
) -> Ellipse:
    """An axis-aligned ellipse. Exactly one of:
    - center, hradius, vradius — center point and semi-axis lengths (both > 0).
    - corner1, corner2 — opposite corners of the bounding box.
    All three of the first group, or both of the second, must be given together."""
    from geometry_diagrams.ir.ir import EllipseBBox, EllipseCenterAxes

    center_axes_parts = [center is not None, hradius is not None, vradius is not None]
    bbox_parts = [corner1 is not None, corner2 is not None]
    has_center_axes = all(center_axes_parts)
    has_bbox = all(bbox_parts)
    if has_center_axes and has_bbox:
        raise ValueError(
            "ellipse(): give exactly one of (center, hradius, vradius) or "
            "(corner1, corner2), not both"
        )
    if any(center_axes_parts) and not has_center_axes:
        raise ValueError("ellipse(): center, hradius, and vradius must all be given together")
    if any(bbox_parts) and not has_bbox:
        raise ValueError("ellipse(): corner1 and corner2 must both be given together")
    if not has_center_axes and not has_bbox:
        raise ValueError("ellipse() requires either (center, hradius, vradius) or (corner1, corner2)")

    builder = get_builder()
    eid = builder._fresh_hidden_id("ellipse")

    if has_center_axes:
        if hradius <= 0 or vradius <= 0:
            raise ValueError(
                f"ellipse(): hradius and vradius must be positive, got "
                f"{hradius!r}, {vradius!r}"
            )
        builder._add(EllipseCenterAxes(id=eid, center=center.id, hradius=hradius, vradius=vradius))
        return Ellipse(id=eid, center=center, _hradius_thunk=lambda: hradius, _vradius_thunk=lambda: vradius)

    builder._add(EllipseBBox(id=eid, corner1=corner1.id, corner2=corner2.id))
    mid_id = builder._fresh_hidden_id("ellipse_center")
    builder._add(PointMidpoint(id=mid_id, p=corner1.id, q=corner2.id))
    center_pt = Point(id=mid_id, _builder=builder)

    def _compute_hradius():
        coord_floats = builder._coord_floats
        if corner1.id not in coord_floats or corner2.id not in coord_floats:
            raise NotImplementedError(
                "ellipse(...).hradius requires both corners to be concrete "
                "point(x, y) literals."
            )
        x1, _ = coord_floats[corner1.id]
        x2, _ = coord_floats[corner2.id]
        return abs(x2 - x1) / 2

    def _compute_vradius():
        coord_floats = builder._coord_floats
        if corner1.id not in coord_floats or corner2.id not in coord_floats:
            raise NotImplementedError(
                "ellipse(...).vradius requires both corners to be concrete "
                "point(x, y) literals."
            )
        _, y1 = coord_floats[corner1.id]
        _, y2 = coord_floats[corner2.id]
        return abs(y2 - y1) / 2

    return Ellipse(id=eid, center=center_pt, _hradius_thunk=_compute_hradius, _vradius_thunk=_compute_vradius)


def median(t: Triangle, from_vertex: Point) -> Median:
    """The median from a vertex to the midpoint of the opposite side."""
    vertex_ids = [v.id for v in t.vertices]
    if from_vertex.id not in vertex_ids:
        raise ValueError(f"{from_vertex.id!r} is not a vertex of triangle {t.id!r}")
    others = [pid for pid in vertex_ids if pid != from_vertex.id]
    builder = get_builder()
    mid_id = builder._fresh_hidden_id("midpoint")
    builder._add(PointMidpoint(id=mid_id, p=others[0], q=others[1]))
    seg_id = builder._fresh_hidden_id("median_seg")
    builder._add(SegmentDef(id=seg_id, a=from_vertex.id, b=mid_id))
    return Median(id=seg_id, midpoint=Point(id=mid_id, _builder=builder), segment=Segment(id=seg_id, _builder=builder))


def altitude(t: Triangle, from_vertex: Point) -> Altitude:
    """The altitude from a vertex, perpendicular to the opposite side."""
    vertex_ids = [v.id for v in t.vertices]
    if from_vertex.id not in vertex_ids:
        raise ValueError(f"{from_vertex.id!r} is not a vertex of triangle {t.id!r}")
    others = [pid for pid in vertex_ids if pid != from_vertex.id]
    builder = get_builder()

    base_id = builder._fresh_hidden_id("altitude_base")
    builder._add(LineThrough(id=base_id, p=others[0], q=others[1]))

    line_id = builder._fresh_hidden_id("altitude_line")
    builder._add(
        LinePerpendicularThrough(id=line_id, through=from_vertex.id, to_line=base_id)
    )

    foot_id = builder._fresh_hidden_id("altitude_foot")
    builder._add(PointFoot(id=foot_id, source=from_vertex.id, onto=base_id))

    seg_id = builder._fresh_hidden_id("altitude_seg")
    builder._add(SegmentDef(id=seg_id, a=from_vertex.id, b=foot_id))

    return Altitude(
        id=line_id, foot=Point(id=foot_id, _builder=builder), line=Line(id=line_id),
        segment=Segment(id=seg_id, _builder=builder),
    )


def angle(a: Point, o: Point, b: Point) -> AngleRef:
    """The angle at vertex o, between rays o->a and o->b — use this for any
    angle that ISN'T a triangle/polygon vertex angle (Triangle.angle_at()/
    Polygon.angle_at() cover that case): a linear pair at a point on a line,
    a central angle of a circle (o = the circle's center), the angle between
    a tangent line and a radius, or the angle at a transversal intersection.
    Same argument order as Triangle.angle_at()/Polygon.angle_at() — o is the
    vertex, a and b are the two ray endpoints, not the other way around."""
    if o.id == a.id or o.id == b.id:
        raise ValueError(f"angle(): vertex {o.id!r} must be distinct from both a and b")
    builder = get_builder()
    return AngleRef(a=a, o=o, b=b, _builder=builder)


def mark_angle(ref: AngleRef, group: int | None = None) -> None:
    """Mark an angle arc for rendering, optionally tagged with an equal-angle group."""
    builder = get_builder()
    builder._add_render(
        MarkAngles(
            angles=[AnglePoints(a=ref.a.id, o=ref.o.id, b=ref.b.id)],
            group=str(group) if group is not None else None,
        )
    )


def _mark_segments(kind: str, segments: tuple[Segment, ...]) -> None:
    if len(segments) < 2:
        raise ValueError(f"mark_{kind}() requires at least 2 segments, got {len(segments)}")
    builder = get_builder()
    group = builder._fresh_mark_group(kind)
    builder._add_render(MarkSegments(segs=[s.id for s in segments], group=group))


def mark_equal(*segments: Segment) -> None:
    """Mark segments as equal in length with matching tick marks. Each
    call gets a fresh tick symbol automatically — pass all mutually-equal
    segments in ONE call (e.g. mark_equal(ab, cd, ef)) rather than
    multiple calls, since separate calls always get visually distinct
    symbols, never the same one. Requires at least 2 segments. Note: only
    6 distinct tick symbols exist (shared with mark_proportional()'s
    calls too) and marks draw at each segment's midpoint — more than 6
    mark_equal()/mark_proportional() calls in one diagram silently reuse
    a symbol, and a segment passed to two different mark_*() calls gets
    overlapping marks at the same midpoint."""
    _mark_segments("equal", segments)


def mark_parallel(*segments: Segment) -> None:
    """Mark segments as parallel with matching chevron marks (>, >>, >>>,
    ...). Same one-call-per-group contract as mark_equal(). Requires at
    least 2 segments. Note: only 3 distinct chevron counts exist — a 4th
    mark_parallel() call in one diagram silently reuses one."""
    _mark_segments("parallel", segments)


def mark_proportional(*segments: Segment) -> None:
    """Mark segments as proportional (not necessarily equal) — NOTE:
    renders with the same tick-mark symbols as mark_equal(), since the
    underlying renderer has no separate visual convention for
    "proportional." Use this over mark_equal() only for the script's own
    semantic clarity; the diagram itself won't look different. Requires
    at least 2 segments. Shares mark_equal()'s 6-symbol limit (see its
    docstring) — the two functions draw from the same symbol cycle."""
    _mark_segments("proportional", segments)


def mark_right_angle(ref: AngleRef) -> None:
    """Mark an angle with the right-angle square symbol, e.g.
    mark_right_angle(t.angle_at(b)) — distinct from mark_angle()'s arc.
    Takes exactly one angle per call (no group parameter, unlike
    mark_angle()'s optional equal-angle group) — a right angle is
    unambiguously 90°, so there's no equivalence class to group."""
    from geometry_diagrams.ir.ir import MarkRightAngles

    builder = get_builder()
    builder._add_render(
        MarkRightAngles(angles=[AnglePoints(a=ref.a.id, o=ref.o.id, b=ref.b.id)])
    )


def point_on(obj, t: float) -> Point:
    """A point at parameter t along a line or segment (t=0/1 are the object's
    defining points; for a line, t outside [0, 1] extends past them in either
    direction), or at angle t (radians) on a circle or ellipse — use this
    instead of hand-computing coordinates to place a point on an existing
    line/segment/circle/ellipse, or to extend a line's visible extent. This
    is the correct way to build arc()/sector()'s start/end points, guaranteed
    to land exactly on the shape's boundary."""
    builder = get_builder()
    pid = builder._fresh_hidden_id("pt_on")
    builder._add(PointOn(id=pid, on=obj.id, how=PointOnParam(t=t)))
    return Point(id=pid, _builder=builder)


def rotate_point(source: Point, center: Point, angle: float) -> Point:
    """Rotate source around center by angle radians (positive = counter-clockwise)."""
    builder = get_builder()
    pid = builder._fresh_hidden_id("rot")
    builder._add(PointRotate(id=pid, center=center.id, source=source.id, angle=angle))
    return Point(id=pid, _builder=builder)


def reflect_point(source: Point, across) -> Point:
    """Reflect source across a point (point symmetry) or a line/segment (mirror)."""
    builder = get_builder()
    pid = builder._fresh_hidden_id("refl")
    builder._add(PointReflect(id=pid, source=source.id, across=across.id))
    return Point(id=pid, _builder=builder)


def dilate_point(source: Point, center: Point, ratio: float) -> Point:
    """Scale source about center by ratio: result = center + ratio*(source - center).

    For points with known literal coordinates, plain arithmetic on the Point
    handles themselves (`center + ratio * (source - center)`) does the same
    thing and needs no import — use this when either point's coordinates
    aren't known yet (e.g. dilating about a computed triangle center)."""
    builder = get_builder()
    pid = builder._fresh_hidden_id("dil")
    builder._add(PointDilate(id=pid, center=center.id, source=source.id, ratio=ratio))
    return Point(id=pid, _builder=builder)


def perpendicular_through(point: Point, line) -> Line:
    """The line through `point`, perpendicular to `line` (a Line/Segment/Ray)."""
    builder = get_builder()
    line_id = builder._fresh_hidden_id("perp")
    builder._add(LinePerpendicularThrough(id=line_id, through=point.id, to_line=line.id))
    return Line(id=line_id)


def parallel_through(point: Point, line) -> Line:
    """The line through `point`, parallel to `line` (a Line/Segment/Ray)."""
    builder = get_builder()
    line_id = builder._fresh_hidden_id("parallel")
    builder._add(LineParallelThrough(id=line_id, through=point.id, to_line=line.id))
    return Line(id=line_id)


def angle_bisector(vertex: Point, toward1: Point, toward2: Point) -> Line:
    """The line bisecting the angle at `vertex`, between rays toward toward1/toward2."""
    builder = get_builder()
    line_id = builder._fresh_hidden_id("bisector")
    builder._add(LineAngleBisector(id=line_id, a=toward1.id, vertex=vertex.id, b=toward2.id))
    return Line(id=line_id)


def centroid(t: Triangle) -> Point:
    """The centroid of triangle `t`."""
    builder = get_builder()
    pid = builder._fresh_hidden_id("centroid")
    builder._add(PointTriangleCenter(id=pid, tri=t.id, which="centroid"))
    return Point(id=pid, _builder=builder)


def foot_of_perpendicular(point: Point, line) -> Point:
    """The foot of the perpendicular dropped from `point` onto `line`
    (a Line/Segment/Ray) — always projects onto the infinite line."""
    builder = get_builder()
    pid = builder._fresh_hidden_id("foot")
    builder._add(PointFoot(id=pid, source=point.id, onto=line.id))
    return Point(id=pid, _builder=builder)


def perpendicular_bisector(p: Point, q: Point) -> PerpendicularBisectorLine:
    """The perpendicular bisector of segment p-q. Does not draw the
    segment p-q itself — draw() it separately if you want it visible."""
    builder = get_builder()
    base_id = builder._fresh_hidden_id("bisector_base")
    builder._add(LineThrough(id=base_id, p=p.id, q=q.id))
    mid_id = builder._fresh_hidden_id("bisector_mid")
    builder._add(PointMidpoint(id=mid_id, p=p.id, q=q.id))
    line_id = builder._fresh_hidden_id("bisector")
    builder._add(LinePerpendicularThrough(id=line_id, through=mid_id, to_line=base_id))
    return PerpendicularBisectorLine(
        id=line_id, midpoint=Point(id=mid_id, _builder=builder), line=Line(id=line_id)
    )


def intersection(
    obj1,
    obj2,
    near: "Point | None" = None,
    side_of: "tuple[Point, Point] | None" = None,
    side: "str | None" = None,
) -> Point:
    """The intersection point of obj1 and obj2 (lines/segments/rays/circles).

    Disambiguate when there's more than one candidate (e.g. a line crossing
    a circle twice) with EITHER:
    - near=P — the candidate closest to P, or
    - side_of=(A, B), side="left"|"right" — the candidate on that side of
      the directed line from A to B (walking from A toward B).
    Give at most one of these. With neither, and more than one candidate
    exists, an automatic (documented-as-arbitrary) heuristic picks one —
    prefer giving near/side_of+side whenever the choice matters."""
    from geometry_diagrams.ir.ir import PickClosestTo, PickLowerOfLine, PickUpperOfLine, PointIntersection

    has_near = near is not None
    has_side = side_of is not None or side is not None
    if has_near and has_side:
        raise ValueError("intersection(): give at most one of 'near' or 'side_of'+'side', not both")
    if (side_of is not None) != (side is not None):
        raise ValueError("intersection(): 'side_of' and 'side' must be given together")
    if side is not None and side not in ("left", "right"):
        raise ValueError(f"intersection(): side must be 'left' or 'right', got {side!r}")

    pick = None
    if has_near:
        pick = PickClosestTo(p=near.id)
    elif has_side:
        a, b = side_of
        pick = PickUpperOfLine(a=a.id, b=b.id) if side == "left" else PickLowerOfLine(a=a.id, b=b.id)

    builder = get_builder()
    pid = builder._fresh_hidden_id("isect")
    builder._add(PointIntersection(id=pid, obj1=obj1.id, obj2=obj2.id, pick=pick))
    return Point(id=pid, _builder=builder)


def tangent_line(
    circle: Circle,
    at: "Point | None" = None,
    from_point: "Point | None" = None,
    near: "Point | None" = None,
    side_of: "tuple[Point, Point] | None" = None,
    side: "str | None" = None,
) -> Line:
    """The tangent line to `circle`. Exactly one of:
    - at=P — P is a point already ON the circle; the tangent there (always
      unambiguous — near/side_of/side are silently ignored if also given,
      matching the DSL lowerer's own at= branch, which has no equivalent
      validation either).
    - from_point=P — P is external to the circle; there are 0, 1, or 2
      tangent lines from an external point. Disambiguate a 2-tangent case
      with near=Q (closest touch point to Q) or side_of=(A,B), side=
      "left"|"right" (same convention as intersection()). With neither,
      and 2 tangent lines exist, unlike intersection() there is no
      arbitrary-heuristic fallback — compilation fails later, inside
      compile_defs(), with geometry_diagrams.ir.errors.PickError."""
    from geometry_diagrams.ir.ir import LinePerpendicularThrough, LineThrough, LineTangent, PickClosestTo, PickLowerOfLine, PickUpperOfLine

    if (at is None) == (from_point is None):
        raise ValueError("tangent_line() requires exactly one of 'at' or 'from_point'")

    builder = get_builder()
    if at is not None:
        radius_id = builder._fresh_hidden_id("tangent_radius")
        builder._add(LineThrough(id=radius_id, p=circle.center.id, q=at.id))
        line_id = builder._fresh_hidden_id("tangent")
        builder._add(LinePerpendicularThrough(id=line_id, through=at.id, to_line=radius_id))
        return Line(id=line_id)

    has_near = near is not None
    has_side = side_of is not None or side is not None
    if has_near and has_side:
        raise ValueError("tangent_line(): give at most one of 'near' or 'side_of'+'side', not both")
    if (side_of is not None) != (side is not None):
        raise ValueError("tangent_line(): 'side_of' and 'side' must be given together")
    if side is not None and side not in ("left", "right"):
        raise ValueError(f"tangent_line(): side must be 'left' or 'right', got {side!r}")

    pick = None
    if has_near:
        pick = PickClosestTo(p=near.id)
    elif has_side:
        a, b = side_of
        pick = PickUpperOfLine(a=a.id, b=b.id) if side == "left" else PickLowerOfLine(a=a.id, b=b.id)

    line_id = builder._fresh_hidden_id("tangent")
    builder._add(LineTangent(id=line_id, point=from_point.id, circle=circle.id, pick=pick))
    return Line(id=line_id)


def draw(
    obj,
    color: "str | None" = None,
    thick: bool = False,
    thin: bool = False,
    width: "float | None" = None,
    dashed: bool = False,
    dotted: bool = False,
    arrow_start: bool = False,
    arrow_end: bool = False,
) -> None:
    """Draw a constructed object (triangle, polygon, circle, arc, sector,
    line, or segment), with optional stroke styling:
    - color: any string the renderer understands (not validated by pydsl
      itself — passed straight through, matching the recipe DSL's own
      permissiveness).
    - thick/thin: preset stroke widths. Give at most one, and not
      together with width.
    - width: an explicit numeric stroke width, given instead of
      thick/thin (must be positive).
    - dashed/dotted: give at most one.
    - arrow_start/arrow_end: draw an arrowhead at the start/end of the
      shape's path. For an open shape (line/segment/ray/arc) this marks
      the obvious start/end point. For a closed shape (polygon, circle,
      sector) the underlying renderers do not treat this consistently —
      SVG's polygon/path elements DO honor start/end markers at the
      shape's first/last recorded vertex, so an arrow can visibly appear
      on a polygon under SVGRenderer even though nothing here explicitly
      asked for that. Not rejected, but the correct expectation is "an
      arrow may appear at an arbitrary vertex," not "no effect."
    """
    if isinstance(obj, Point):
        raise ValueError("draw() doesn't take a Point — use draw_points(...) instead")
    if isinstance(obj, AngleRef):
        raise ValueError("draw() doesn't take an AngleRef — use mark_angle(...) instead")
    width_group = [thick, thin, width is not None]
    if sum(width_group) > 1:
        raise ValueError("draw(): give at most one of thick, thin, or width")
    if width is not None and width <= 0:
        raise ValueError(f"draw(): width must be positive, got {width!r}")
    if dashed and dotted:
        raise ValueError("draw(): give at most one of dashed or dotted")

    style: dict = {}
    if color is not None:
        style["color"] = color
    if thick:
        style["thick"] = True
    if thin:
        style["thin"] = True
    if width is not None:
        style["line_width"] = width
    if dashed:
        style["dashed"] = True
    if dotted:
        style["dotted"] = True
    if arrow_start and arrow_end:
        style["<->"] = True
    elif arrow_start:
        style["<-"] = True
    elif arrow_end:
        style["->"] = True

    builder = get_builder()
    style_key = builder._register_style(style) if style else None
    builder._add_render(Draw(obj=obj.id, style=style_key))


def draw_points(*points: Point) -> None:
    """Draw one or more points as visible markers."""
    builder = get_builder()
    builder._add_render(DrawPoints(points=[p.id for p in points]))


def fill(
    obj,
    color: "str | None" = None,
    opacity: float = 1.0,
    holes: "object" = (),
) -> None:
    """Fill a constructed object's interior (triangle, polygon, circle,
    sector) with the given color. opacity is 0 (fully transparent) to 1
    (fully opaque). Filling a shape with no enclosed interior (a line,
    segment, ray, or arc) has no defined visual effect and is not
    rejected — same permissiveness as draw()'s arrow_start/arrow_end on a
    closed shape.
    holes: shapes whose interiors are punched out as transparent cutouts
    (rings, annuli, "the region between the circle and the square") —
    each must be a previously constructed shape with an interior
    (triangle, polygon, circle, ellipse, sector), not a Point or
    AngleRef. No containment check is performed — same permissiveness as
    the underlying renderer, which silently applies the even-odd rule
    regardless of whether a hole is fully inside obj, partially
    overlapping, or outside it entirely."""
    if isinstance(obj, Point):
        raise ValueError("fill() doesn't take a Point — use draw_points(...) instead")
    if isinstance(obj, AngleRef):
        raise ValueError("fill() doesn't take an AngleRef — use mark_angle(...) instead")
    if not 0 <= opacity <= 1:
        raise ValueError(f"fill(): opacity must be between 0 and 1, got {opacity!r}")
    holes = tuple(holes)  # materialize once: the loop below and the [h.id for h in
                           # holes] construction later must see the same items, which
                           # silently breaks for a one-shot generator argument
    for hole in holes:
        if isinstance(hole, Point):
            raise ValueError("fill(): a hole can't be a Point — use draw_points(...) instead")
        if isinstance(hole, AngleRef):
            raise ValueError("fill(): a hole can't be an AngleRef — use mark_angle(...) instead")

    from geometry_diagrams.ir.ir import Fill

    style: dict = {}
    if color is not None:
        style["color"] = color
    # opacity is ALSO written into the style dict, not left to Fill's own
    # `opacity` field alone. to_tikz.py's Fill handler only merges in
    # Fill.opacity when NO style dict is registered; the moment a style
    # dict exists (e.g. because color was given), the TikZ path builds its
    # options string purely from that dict and Fill.opacity is silently
    # ignored, rendering fully opaque regardless of what was asked for.
    # Writing "opacity" into the style dict closes this: to_svg.py's
    # _fill_attrs already prefers the style dict's opacity over the Fill
    # op's own field, and to_tikz.py's generic pass-through emits a valid
    # `opacity=0.3` TikZ option from the same dict entry.
    if opacity != 1.0:
        style["opacity"] = opacity

    builder = get_builder()
    style_key = builder._register_style(style) if style else None
    builder._add_render(Fill(
        obj=obj.id, holes=[h.id for h in holes], opacity=opacity, style=style_key,
    ))


def label_text(
    text: str,
    at: "tuple[float, float] | None" = None,
    centroid_of: "Triangle | Polygon | None" = None,
) -> None:
    """Place free-standing text at explicit (x, y) coordinates, or at the
    centroid of a triangle/polygon. Exactly one of `at`/`centroid_of` must
    be given."""
    from geometry_diagrams.ir.ir import LabelFreeText

    has_at = at is not None
    has_centroid = centroid_of is not None
    if has_at == has_centroid:
        raise ValueError("label_text() requires exactly one of 'at' or 'centroid_of'")
    text = _sanitize_label_text(text, "label_text")
    builder = get_builder()
    builder._add_render(LabelFreeText(
        text=text,
        at=[float(at[0]), float(at[1])] if has_at else None,
        centroid_of=centroid_of.id if has_centroid else None,
    ))


def canvas(
    x_range: "tuple[float, float] | list[float]",
    y_range: "tuple[float, float] | list[float]",
    grid: bool = False,
    grid_step: "float | None" = None,
    axes: bool = False,
    tick_step: "float | None" = None,
    show_ticks: bool = False,
    show_tick_labels: bool = False,
    show_axis_labels: bool = False,
) -> None:
    """Set canvas bounds and optional grid/axes styling for the diagram.
    Call at most once per script. grid_step/tick_step default to an
    automatically chosen 'nice' number (1, 2, 5, 10, ...) based on the
    canvas size if not given. Note: if axes=True, the displayed bounds
    expand to include the origin even if x_range/y_range don't."""
    from geometry_diagrams.ir.ir import Canvas as CanvasDef

    builder = get_builder()
    if builder._canvas is not None:
        raise ValueError(
            "canvas() was already called once in this script — only one call is allowed"
        )
    xmin, xmax = x_range
    ymin, ymax = y_range
    if xmin >= xmax:
        raise ValueError(f"canvas(): x_range must satisfy x_range[0] < x_range[1], got {list(x_range)!r}")
    if ymin >= ymax:
        raise ValueError(f"canvas(): y_range must satisfy y_range[0] < y_range[1], got {list(y_range)!r}")
    if grid_step is not None and grid_step <= 0:
        raise ValueError(f"canvas(): grid_step must be > 0, got {grid_step!r}")
    if tick_step is not None and tick_step <= 0:
        raise ValueError(f"canvas(): tick_step must be > 0, got {tick_step!r}")

    span = max(xmax - xmin, ymax - ymin)
    effective_grid_step = grid_step if grid_step is not None else _nice_step(span)
    effective_tick_step = tick_step if tick_step is not None else _nice_step(span)

    if grid:
        n_grid_lines = (xmax - xmin) / effective_grid_step + (ymax - ymin) / effective_grid_step
        if n_grid_lines > _MAX_GRID_LINES:
            raise ValueError(
                f"canvas(): grid_step={effective_grid_step!r} over this range would draw "
                f"~{int(n_grid_lines)} grid lines (limit {_MAX_GRID_LINES}) — use a larger grid_step"
            )
    if show_ticks or show_tick_labels:
        n_tick_lines = (xmax - xmin) / effective_tick_step + (ymax - ymin) / effective_tick_step
        if n_tick_lines > _MAX_GRID_LINES:
            raise ValueError(
                f"canvas(): tick_step={effective_tick_step!r} over this range would draw "
                f"~{int(n_tick_lines)} ticks (limit {_MAX_GRID_LINES}) — use a larger tick_step"
            )
    builder._canvas = CanvasDef(
        xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax,
        grid=grid, grid_step=effective_grid_step,
        axes=axes, tick_step=effective_tick_step,
        show_ticks=show_ticks, show_tick_labels=show_tick_labels,
        show_axis_labels=show_axis_labels,
    )
