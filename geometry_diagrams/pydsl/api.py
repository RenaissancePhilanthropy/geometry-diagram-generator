# geometry_diagrams/pydsl/api.py
"""Public builder-shim API. Every function here records an op against the
ambient Builder (see builder.py) and returns a handle."""
from __future__ import annotations

import math

from geometry_diagrams.ir.ir import AnglePoints, CircleCenterRadius, Draw, DrawPoints, LineAngleBisector, LineParallelThrough, LinePerpendicularThrough, LineThrough, MarkAngles, PointDilate, PointFixed, PointFoot, PointMidpoint, PointOn, PointOnParam, PointReflect, PointRotate, PointTriangleCenter
from geometry_diagrams.ir.ir import Polygon as PolygonDef
from geometry_diagrams.ir.ir import Segment as SegmentDef
from geometry_diagrams.ir.ir import Triangle as TriangleDef
from geometry_diagrams.pydsl.builder import get_builder
from geometry_diagrams.pydsl.handles import AngleRef, Altitude, Circle, Line, Median, PerpendicularBisectorLine, Point, Polygon, Segment, Triangle

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
    return Point(id=pid, _builder=builder, x=float(x), y=float(y))


def line_through(p: Point, q: Point) -> Line:
    """The line through two points."""
    builder = get_builder()
    lid = builder._fresh_hidden_id("line")
    builder._add(LineThrough(id=lid, p=p.id, q=q.id))
    return Line(id=lid)


def triangle(a: Point, b: Point, c: Point) -> Triangle:
    """A triangle over three existing points."""
    builder = get_builder()
    tid = builder._fresh_hidden_id("tri")
    builder._add(TriangleDef(id=tid, a=a.id, b=b.id, c=c.id))
    return Triangle(id=tid, vertices=(a, b, c), _builder=builder)


def polygon(*vertices: Point) -> Polygon:
    """A closed polygon over 3 or more existing points, in perimeter order."""
    if len(vertices) < 3:
        raise ValueError(f"polygon requires at least 3 vertices, got {len(vertices)}")
    builder = get_builder()
    pid = builder._fresh_hidden_id("poly")
    builder._add(PolygonDef(id=pid, points=[v.id for v in vertices]))
    return Polygon(id=pid, vertices=tuple(vertices), _builder=builder)


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

    return Circle(id=cid, center=Point(id=center_id, _builder=builder), _radius_thunk=_compute_radius)


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
    return Circle(id=cid, center=Point(id=center_id, _builder=builder), _radius_thunk=lambda: radius)


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


def mark_angle(ref: AngleRef, group: int | None = None) -> None:
    """Mark an angle arc for rendering, optionally tagged with an equal-angle group."""
    builder = get_builder()
    builder._add_render(
        MarkAngles(
            angles=[AnglePoints(a=ref.a.id, o=ref.o.id, b=ref.b.id)],
            group=str(group) if group is not None else None,
        )
    )


def point_on(obj, t: float) -> Point:
    """A point at parameter t along a line or segment (t=0/1 are the object's
    defining points; for a line, t outside [0, 1] extends past them in either
    direction — use this instead of hand-computing coordinates to place a
    point on an existing line/segment, or to extend a line's visible extent."""
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
    return PerpendicularBisectorLine(id=line_id, midpoint=Point(id=mid_id, _builder=builder))


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


def draw(obj) -> None:
    """Draw a constructed object (triangle, polygon, circle, line, or segment)."""
    if isinstance(obj, Point):
        raise ValueError("draw() doesn't take a Point — use draw_points(...) instead")
    if isinstance(obj, AngleRef):
        raise ValueError("draw() doesn't take an AngleRef — use mark_angle(...) instead")
    builder = get_builder()
    builder._add_render(Draw(obj=obj.id))


def draw_points(*points: Point) -> None:
    """Draw one or more points as visible markers."""
    builder = get_builder()
    builder._add_render(DrawPoints(points=[p.id for p in points]))


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
