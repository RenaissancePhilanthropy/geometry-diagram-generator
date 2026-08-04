# geometry_diagrams/pydsl/api.py
"""Public builder-shim API. Every function here records an op against the
ambient Builder (see builder.py) and returns a handle."""
from __future__ import annotations

import math

from geometry_diagrams.ir.ir import AnglePoints, CircleCenterRadius, Draw, DrawPoints, LinePerpendicularThrough, LineThrough, MarkAngles, PointFixed, PointFoot, PointMidpoint, PointTriangleCenter
from geometry_diagrams.ir.ir import Polygon as PolygonDef
from geometry_diagrams.ir.ir import Segment as SegmentDef
from geometry_diagrams.ir.ir import Triangle as TriangleDef
from geometry_diagrams.pydsl.builder import get_builder
from geometry_diagrams.pydsl.handles import AngleRef, Altitude, Circle, Line, Median, Point, Polygon, Segment, Triangle


def point(x: float, y: float) -> Point:
    """A point fixed at literal coordinates (x, y)."""
    builder = get_builder()
    pid = builder._fresh_hidden_id("pt")
    builder._add(PointFixed(id=pid, x=x, y=y))
    builder._coord_floats[pid] = (float(x), float(y))
    return Point(id=pid)


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

    return Circle(id=cid, center=Point(id=center_id), _radius_thunk=_compute_radius)


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
    return Circle(id=cid, center=Point(id=center_id), _radius_thunk=lambda: radius)


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
    return Median(id=seg_id, midpoint=Point(id=mid_id), segment=Segment(id=seg_id))


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
        id=line_id, foot=Point(id=foot_id), line=Line(id=line_id),
        segment=Segment(id=seg_id),
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
