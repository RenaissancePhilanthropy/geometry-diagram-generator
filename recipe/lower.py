# recipe/lower.py
"""RecipeDSL → DiagramIR lowering pass.

Public API: lower_to_ir(dsl: RecipeDSL) -> DiagramIR

No SymPy dependency. Pure structural transformation. Triangle coordinates
are computed using recipe.solve.solve_triangle (basic trig only).
"""
from __future__ import annotations

import math
from typing import Any

from pydantic import TypeAdapter

from ir.ir import (
    DiagramIR, Canvas, Params,
    PointFixed, PointMidpoint, PointFoot, PointBetween, PointTriangleCenter,
    PointReflect, PointRotate, PointIntersection, PointAlias,
    LineThrough, LineParallelThrough, LinePerpendicularThrough, LineAngleBisector,
    LineTangent, Segment, Ray,
    CircleCenterPoint, CircleCenterRadius, CircleThrough3,
    Triangle, Polygon, PolygonExterior,
    Check, Perpendicular, Contains, RightAngle, AnglePoints,
    AngleEqual, EqualLength, Parallel, RatioEqual,
    Draw, DrawPoints, LabelPoint, MarkRightAngles,
    MarkAngles, MarkSegments, LabelSegment as IRLabelSegment,
    RenderOp, DefStmt, PickRule,
)
from recipe.dsl import (
    RecipeDSL, DSLAnnotations,
    TriangleOp, CircleOp, PolygonOp, PointOp, PointExternalOp, CanvasOp,
    RegularPolygonOp, PointAlongOp, ExtendSegmentOp,
    MidpointOp, IntersectionOp, PerpendicularOp, ParallelOp,
    LineThroughOp, SegmentOp, RayOp, ReflectionOp, RotationOp,
    PointOnSegmentOp, TangentLineOp, PointFootOp, CircleThrough3Op,
    AltitudeOp, CircumcircleOp, IncircleOp, PerpendicularBisectorOp,
    AngleBisectorOp, CentroidOp, MedianOp, PolygonExteriorOp,
    MarkAngle, MarkRightAngle, MarkEqualLengths, MarkParallel, MarkProportional,
    LabelSegment as DSLLabelSegment,
    DrawObj,
)
from recipe.solve import solve_triangle


class LoweringError(ValueError):
    """Raised when a RecipeDSL cannot be lowered to DiagramIR."""


_PICK_RULE_ADAPTER: TypeAdapter[PickRule] = TypeAdapter(PickRule)

_DEG_TO_RAD = math.pi / 180.0

_GENERIC_VERTICES = ("A", "B", "C")


def _remap_triangle_spec(vertices: list[str], spec: dict) -> dict:
    """Remap generic A/B/C spec keys to the actual vertex names.

    When the LLM generates a triangle with vertices [D, E, F] but uses generic
    spec keys like ``angle_A``, ``angle_B``, ``side_AB`` (meant positionally),
    this function translates those keys to use the real vertex names
    (``angle_D``, ``angle_E``, ``side_DE``).

    The remapping is only applied when the vertex set is *completely disjoint*
    from {A, B, C}, i.e. none of the actual vertices are named A, B, or C.
    If any actual vertex shares a name with a generic label, the spec keys may
    be intentional references to that vertex, so we leave the spec unchanged.
    """
    if set(vertices) & set(_GENERIC_VERTICES):
        return spec  # actual vertices include A/B/C — cannot safely remap

    mapping = {g: v for g, v in zip(_GENERIC_VERTICES, vertices)}

    remapped: dict = {}
    for key, val in spec.items():
        if key.startswith("angle_"):
            letter = key[len("angle_"):]
            remapped[f"angle_{mapping.get(letter, letter)}"] = val
        elif key.startswith("side_") and len(key) == 7:
            # side_XY — two-character vertex pair
            l0, l1 = key[5], key[6]
            remapped[f"side_{mapping.get(l0, l0)}{mapping.get(l1, l1)}"] = val
        elif key == "right_angle_at":
            letter = str(val)
            remapped[key] = mapping.get(letter, letter)
        else:
            remapped[key] = val
    return remapped


class _Lowerer:
    """Stateful lowering context for a single RecipeDSL."""

    def __init__(self) -> None:
        self._defs: list[DefStmt] = []
        self._checks: list[Check] = []
        self._renders: list[RenderOp] = []
        self._canvas: Canvas | None = None
        # Maps triangle DSL id → [v0, v1, v2] vertex names (for circumcircle etc.)
        self._triangle_vertices: dict[str, list[str]] = {}
        # All non-implicit point IDs defined in construction order
        self._point_ids: list[str] = []
        # All non-implicit drawable object IDs (set for O(1) membership, order via _defs)
        self._drawable: set[str] = set()
        # Right-angle triples from triangle specs and altitude ops
        self._right_angle_triples: list[tuple[str, str, str]] = []  # (a, vertex, b)
        # Resolved coordinate floats for auto-canvas computation (keyed by point id)
        self._coord_floats: dict[str, tuple[float, float]] = {}
        # Named + inline styles to forward to DiagramIR.styles
        self._styles: dict[str, dict[str, Any]] = {}
        self._inline_style_counter: int = 0

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def lower(self, dsl: RecipeDSL) -> DiagramIR:
        for op in dsl.construction:
            self._lower_op(op)
        self._apply_annotations(dsl.annotations, dsl.construction)
        canvas = self._canvas or self._auto_canvas()
        return DiagramIR(
            define=self._defs,
            checks=self._checks,
            render=self._renders,
            canvas=canvas,
            styles=self._styles,
        )

    # ------------------------------------------------------------------
    # Op dispatch
    # ------------------------------------------------------------------

    def _lower_op(self, op: Any) -> None:
        match op:
            # --- Foundation ---
            case TriangleOp():
                self._lower_triangle(op)
            case CircleOp():
                self._lower_circle(op)
            case PolygonOp():
                self._add(Polygon(id=op.id, points=op.vertices))
                self._drawable.add(op.id)
            case PointOp():
                self._add(PointFixed(id=op.id, x=op.coords[0], y=op.coords[1]))
                self._point_ids.append(op.id)
                self._coord_floats[op.id] = (op.coords[0], op.coords[1])
            case CanvasOp():
                self._canvas = Canvas(
                    xmin=op.x_range[0], xmax=op.x_range[1],
                    ymin=op.y_range[0], ymax=op.y_range[1],
                    grid=op.grid, axes=op.axes,
                )
            case RegularPolygonOp():
                self._lower_regular_polygon(op)
            case PointExternalOp():
                self._lower_point_external(op)
            # --- Derived (passthroughs) ---
            case MidpointOp():
                self._add(PointMidpoint(id=op.id, p=op.of[0], q=op.of[1]))
                self._point_ids.append(op.id)
            case IntersectionOp():
                pick = _PICK_RULE_ADAPTER.validate_python(op.selector) if op.selector else None
                self._add(PointIntersection(id=op.id, obj1=op.of[0], obj2=op.of[1], pick=pick))
                self._point_ids.append(op.id)
            case PerpendicularOp():
                self._lower_perpendicular(op)
            case ParallelOp():
                self._lower_parallel(op)
            case LineThroughOp():
                self._add(LineThrough(id=op.id, p=op.points[0], q=op.points[1]))
                self._drawable.add(op.id)
            case SegmentOp():
                self._add(Segment(id=op.id, a=op.endpoints[0], b=op.endpoints[1]))
                self._drawable.add(op.id)
            case RayOp():
                self._add(Ray(id=op.id, a=op.from_, b=op.through))
                self._drawable.add(op.id)
            case ReflectionOp():
                self._add(PointReflect(id=op.id, source=op.point, across=op.over))
                self._point_ids.append(op.id)
            case RotationOp():
                angle_rad = float(op.angle) * _DEG_TO_RAD
                self._add(PointRotate(id=op.id, center=op.center, source=op.point, angle=angle_rad))
                self._point_ids.append(op.id)
            case PointOnSegmentOp():
                self._add(PointBetween(id=op.id, a=op.segment[0], b=op.segment[1], ratio=op.ratio))
                self._point_ids.append(op.id)
            case TangentLineOp():
                self._lower_tangent_line(op)
            case PointAlongOp():
                self._lower_point_along(op)
            case ExtendSegmentOp():
                self._lower_extend_segment(op)
            case PointFootOp():
                self._lower_point_foot(op)
            case CircleThrough3Op():
                self._lower_circle_through_3(op)
            # --- Composite ---
            case AltitudeOp():
                self._lower_altitude(op)
            case CircumcircleOp():
                self._lower_circumcircle(op)
            case IncircleOp():
                self._lower_incircle(op)
            case PerpendicularBisectorOp():
                self._lower_perp_bisector(op)
            case AngleBisectorOp():
                self._add(LineAngleBisector(id=op.id, vertex=op.vertex, a=op.ray1_toward, b=op.ray2_toward))
                self._drawable.add(op.id)
            case CentroidOp():
                self._add(PointTriangleCenter(id=op.id, tri=op.of, which="centroid"))
                self._point_ids.append(op.id)
            case MedianOp():
                self._lower_median(op)
            case PolygonExteriorOp():
                self._add(PolygonExterior(
                    id=op.id, a=op.base[0], b=op.base[1],
                    ref=op.ref_point, sides=op.n,
                ))
                self._drawable.add(op.id)
                # Emit point aliases for user-given vertex names so they can be
                # referenced in annotations, marks, and other ops.
                # Base points occupy indices 0..len(base)-1; new vertices start after.
                base_count = len(op.base)
                for i, vname in enumerate(op.vertices or []):
                    auto_name = f"{op.id}_v{base_count + i}"
                    self._add(PointAlias(id=vname, ref=auto_name))
                    self._point_ids.append(vname)
            case _:
                raise LoweringError(f"Unhandled DSL op type: {type(op).__name__}")

    # ------------------------------------------------------------------
    # Foundation helpers
    # ------------------------------------------------------------------

    def _lower_triangle(self, op: TriangleOp) -> None:
        try:
            spec = _remap_triangle_spec(op.vertices, op.spec)
            coords = solve_triangle(op.vertices, spec, center=op.center)
        except Exception as e:
            raise LoweringError(f"Triangle '{op.id}': {e}") from e

        for name in op.vertices:
            x, y = coords[name]
            self._add(PointFixed(id=name, x=round(x, 10), y=round(y, 10)))
            self._point_ids.append(name)
            self._coord_floats[name] = (round(x, 10), round(y, 10))

        self._add(Triangle(id=op.id, a=op.vertices[0], b=op.vertices[1], c=op.vertices[2]))
        self._drawable.add(op.id)
        self._triangle_vertices[op.id] = list(op.vertices)

        # Auto-generate right_angle check if spec has right_angle_at
        if "right_angle_at" in op.spec:
            ra = op.spec["right_angle_at"]
            others = [v for v in op.vertices if v != ra]
            triple = (others[0], ra, others[1])
            self._checks.append(RightAngle(angle=AnglePoints(a=triple[0], o=triple[1], b=triple[2])))
            self._right_angle_triples.append(triple)

    def _lower_circle(self, op: CircleOp) -> None:
        if op.radius is not None:
            self._add(CircleCenterRadius(id=op.id, center=op.center, radius=op.radius))
        else:
            self._add(CircleCenterPoint(id=op.id, center=op.center, through=op.through))
        self._drawable.add(op.id)

    def _lower_regular_polygon(self, op: RegularPolygonOp) -> None:
        n = len(op.vertices)
        radius = float(op.radius)
        start_rad = math.radians(float(op.start_angle))
        if op.center in self._coord_floats:
            cx, cy = self._coord_floats[op.center]
        else:
            cx, cy = 0.0, 0.0  # fallback; center should always be defined first
        for i, vid in enumerate(op.vertices):
            angle = start_rad + i * 2 * math.pi / n
            x = round(cx + radius * math.cos(angle), 10)
            y = round(cy + radius * math.sin(angle), 10)
            self._defs.append(PointFixed(id=vid, x=x, y=y))
            self._point_ids.append(vid)
            self._coord_floats[vid] = (x, y)
        if op.star:
            reordered = [op.vertices[(i * 2) % n] for i in range(n)]
        else:
            reordered = list(op.vertices)
        self._defs.append(Polygon(id=op.id, points=reordered))
        self._drawable.add(op.id)

    def _lower_point_external(self, op: PointExternalOp) -> None:
        # Find circle center and radius from previously defined circles
        circle_def = next((d for d in self._defs if d.id == op.relative_to), None)
        if circle_def is None:
            raise LoweringError(f"point_external: circle {op.relative_to!r} not defined yet")
        center_id = getattr(circle_def, "center", None)
        if center_id not in self._coord_floats:
            raise LoweringError(
                f"point_external: center of {op.relative_to!r} not in coord table"
            )
        cx, cy = self._coord_floats[center_id]
        # Get radius — try literal from the circle def, or from coord table
        raw_r = getattr(circle_def, "radius", None)
        try:
            r = float(raw_r)
        except (TypeError, ValueError):
            raise LoweringError(
                f"point_external: cannot resolve radius of {op.relative_to!r} numerically"
            )
        # Parse direction: numeric degrees or named cardinal
        _DIRECTIONS = {"right": 0.0, "left": 180.0, "above": 90.0, "below": 270.0}
        dir_str = str(op.direction)
        if dir_str in _DIRECTIONS:
            angle_deg = _DIRECTIONS[dir_str]
        else:
            try:
                angle_deg = float(dir_str)
            except ValueError:
                raise LoweringError(f"point_external: unrecognised direction {op.direction!r}")
        angle_rad = math.radians(angle_deg)
        dist = float(op.distance_ratio) * r
        px = round(cx + dist * math.cos(angle_rad), 10)
        py = round(cy + dist * math.sin(angle_rad), 10)
        self._defs.append(PointFixed(id=op.id, x=px, y=py))
        self._point_ids.append(op.id)
        self._coord_floats[op.id] = (px, py)

    def _lower_tangent_line(self, op: TangentLineOp) -> None:
        pick = _PICK_RULE_ADAPTER.validate_python(op.selector) if op.selector else None
        if op.from_point:
            self._add(LineTangent(id=op.id, point=op.from_point, circle=op.circle, pick=pick))
        elif op.at:
            # Tangent at a point on circle requires the circle's center id,
            # which the lowerer does not currently track. Raise explicitly rather
            # than emitting IR with an unresolvable placeholder id.
            raise LoweringError(
                f"TangentLineOp '{op.id}': 'at=' tangent (tangent at a point on the circle) "
                "is not yet supported. Use 'from_point=' for an external tangent, "
                "or emit a line_perp_through manually using the circle center."
            )
        else:
            raise LoweringError(f"TangentLineOp '{op.id}': must specify 'from_point' or 'at'")
        self._drawable.add(op.id)

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------

    def _lower_perpendicular(self, op: PerpendicularOp) -> None:
        to_line_id = self._resolve_to_line(op.id, op.to_line)
        self._defs.append(LinePerpendicularThrough(id=op.id, through=op.through, to_line=to_line_id))
        self._drawable.add(op.id)

    def _lower_parallel(self, op: ParallelOp) -> None:
        to_line_id = self._resolve_to_line(op.id, op.to_line)
        self._defs.append(LineParallelThrough(id=op.id, through=op.through, to_line=to_line_id))
        self._drawable.add(op.id)

    def _resolve_to_line(self, op_id: str, to_line: str | list) -> str:
        """Return a line ID, emitting an implicit LineThroughOp if to_line is a point pair."""
        if isinstance(to_line, str):
            return to_line
        # [A, B] form — emit an implicit line_through
        ref_id = f"__{op_id}_ref"
        self._defs.append(LineThrough(id=ref_id, p=to_line[0], q=to_line[1]))
        return ref_id

    # ------------------------------------------------------------------
    # Composite helpers
    # ------------------------------------------------------------------

    def _lower_altitude(self, op: AltitudeOp) -> None:
        # Resolve the two base points
        if op.triangle is not None:
            if op.triangle not in self._triangle_vertices:
                raise LoweringError(
                    f"altitude: triangle {op.triangle!r} not found"
                )
            all_verts = self._triangle_vertices[op.triangle]
            base_pts = [v for v in all_verts if v != op.from_vertex]
            if len(base_pts) != 2:
                raise LoweringError(
                    f"altitude: from_vertex {op.from_vertex!r} not in triangle {op.triangle!r}"
                )
        else:
            base_pts = list(op.to_side)
        p, q = base_pts[0], base_pts[1]
        base_id = f"__{op.id}_base"
        self._defs.append(LineThrough(id=base_id, p=p, q=q))
        self._defs.append(LinePerpendicularThrough(id=op.id, through=op.from_vertex, to_line=base_id))
        self._defs.append(PointFoot(id=op.foot, source=op.from_vertex, onto=base_id))
        # Segment from vertex to foot — creates the {from_vertex, foot} linear pair so
        # mark_right_angles validation can confirm the foot lies on the altitude.
        self._defs.append(Segment(id=f"__{op.id}_seg", a=op.from_vertex, b=op.foot))
        self._point_ids.append(op.foot)
        self._drawable.add(op.id)
        # Right-angle triple: corner is foot, arms are from_vertex and one base point
        self._right_angle_triples.append((op.from_vertex, op.foot, p))
        # Auto-check perpendicularity
        self._checks.append(Perpendicular(l1=op.id, l2=base_id))

    def _lower_circumcircle(self, op: CircumcircleOp) -> None:
        verts = self._triangle_vertices.get(op.of)
        if verts is None:
            raise LoweringError(
                f"CircumcircleOp '{op.id}': triangle '{op.of}' not found. "
                "Define the triangle before the circumcircle."
            )
        self._add(PointTriangleCenter(id=op.center, tri=op.of, which="circumcenter"))
        self._add(CircleCenterPoint(id=op.id, center=op.center, through=verts[0]))
        self._point_ids.append(op.center)
        self._drawable.add(op.id)
        # Auto-generate contains checks for all three vertices
        for v in verts:
            self._checks.append(Contains(p=v, obj=op.id))

    def _lower_incircle(self, op: IncircleOp) -> None:
        if op.of not in self._triangle_vertices:
            raise LoweringError(f"incircle: triangle {op.of!r} not found")
        verts = self._triangle_vertices[op.of]
        a_id, b_id, c_id = verts[0], verts[1], verts[2]
        # Emit incenter
        self._defs.append(PointTriangleCenter(id=op.center, tri=op.of, which="incenter"))
        self._point_ids.append(op.center)
        # Compute inradius numerically from solved coordinates
        if all(v in self._coord_floats for v in [a_id, b_id, c_id]):
            ax, ay = self._coord_floats[a_id]
            bx, by = self._coord_floats[b_id]
            cx, cy = self._coord_floats[c_id]
            side_a = math.hypot(bx - cx, by - cy)  # BC (opposite A)
            side_b = math.hypot(ax - cx, ay - cy)  # AC (opposite B)
            side_c = math.hypot(ax - bx, ay - by)  # AB (opposite C)
            s = (side_a + side_b + side_c) / 2
            area = abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay)) / 2
            inradius: float | str = round(area / s, 10)
        else:
            # Fallback: Heron's formula as string expression (derived triangle)
            a, b, c = a_id, b_id, c_id
            inradius = (
                f"sqrt((length({b},{c})+length({a},{c})+length({a},{b}))/2 - length({b},{c})) "
                f"* sqrt((length({b},{c})+length({a},{c})+length({a},{b}))/2 - length({a},{c})) "
                f"* sqrt((length({b},{c})+length({a},{c})+length({a},{b}))/2 - length({a},{b})) "
                f"/ sqrt((length({b},{c})+length({a},{c})+length({a},{b}))/2)"
            )
        self._defs.append(CircleCenterRadius(id=op.id, center=op.center, radius=inradius))
        self._drawable.add(op.id)

    def _lower_point_along(self, op: PointAlongOp) -> None:
        from_id = op.from_
        toward_id = op.toward
        if from_id not in self._coord_floats:
            raise LoweringError(f"point_along: from point {from_id!r} not in coord table")
        if toward_id not in self._coord_floats:
            raise LoweringError(f"point_along: toward point {toward_id!r} not in coord table")
        fx, fy = self._coord_floats[from_id]
        tx, ty = self._coord_floats[toward_id]
        dx, dy = tx - fx, ty - fy
        mag = math.hypot(dx, dy)
        if mag < 1e-12:
            raise LoweringError(f"point_along: from and toward points are coincident")
        ux, uy = dx / mag, dy / mag
        dist = float(op.distance)
        px = round(fx + dist * ux, 10)
        py = round(fy + dist * uy, 10)
        self._defs.append(PointFixed(id=op.id, x=px, y=py))
        self._point_ids.append(op.id)
        self._coord_floats[op.id] = (px, py)

    def _lower_extend_segment(self, op: ExtendSegmentOp) -> None:
        a_id, b_id = op.segment[0], op.segment[1]
        beyond_id = op.beyond
        other_id = b_id if beyond_id == a_id else a_id
        if beyond_id not in self._coord_floats:
            raise LoweringError(f"extend_segment: beyond point {beyond_id!r} not in coord table")
        if other_id not in self._coord_floats:
            raise LoweringError(f"extend_segment: other endpoint {other_id!r} not in coord table")
        bx, by = self._coord_floats[beyond_id]
        ox, oy = self._coord_floats[other_id]
        dx, dy = bx - ox, by - oy
        mag = math.hypot(dx, dy)
        if mag < 1e-12:
            raise LoweringError(f"extend_segment: endpoints are coincident")
        ux, uy = dx / mag, dy / mag
        dist = float(op.by)
        px = round(bx + dist * ux, 10)
        py = round(by + dist * uy, 10)
        self._defs.append(PointFixed(id=op.id, x=px, y=py))
        self._point_ids.append(op.id)
        self._coord_floats[op.id] = (px, py)

    def _lower_point_foot(self, op: PointFootOp) -> None:
        self._defs.append(PointFoot(id=op.id, source=op.source, onto=op.onto))
        self._point_ids.append(op.id)

    def _lower_circle_through_3(self, op: CircleThrough3Op) -> None:
        if len(op.through) != 3:
            raise LoweringError(f"circle_through_3: expected exactly 3 points, got {len(op.through)}")
        a, b, c = op.through
        # Triangle must precede its circumcenter in the definition DAG
        self._defs.append(Triangle(id=f"__{op.id}_tri", a=a, b=b, c=c))
        self._defs.append(PointTriangleCenter(id=op.center,
                                              tri=f"__{op.id}_tri", which="circumcenter"))
        self._defs.append(CircleCenterPoint(id=op.id, center=op.center, through=a))
        self._point_ids.append(op.center)
        self._drawable.add(op.id)

    def _lower_perp_bisector(self, op: PerpendicularBisectorOp) -> None:
        base_id = f"__{op.id}_base"
        self._add(LineThrough(id=base_id, p=op.of[0], q=op.of[1]))
        self._add(PointMidpoint(id=op.mid, p=op.of[0], q=op.of[1]))
        self._add(LinePerpendicularThrough(id=op.id, through=op.mid, to_line=base_id))
        self._point_ids.append(op.mid)
        self._drawable.add(op.id)
        # Always draw the base segment unless the user already defined one
        # between those two points (to avoid a duplicate Draw op).
        p0, p1 = op.of[0], op.of[1]
        already_has_seg = any(
            isinstance(d, Segment) and {d.a, d.b} == {p0, p1}
            for d in self._defs
        )
        if not already_has_seg:
            seg_id = f"__{op.id}_seg"
            self._add(Segment(id=seg_id, a=p0, b=p1))
            # Add Draw directly — auto_draw_all skips __-prefixed IDs.
            self._renders.append(Draw(obj=seg_id))

    def _lower_median(self, op: MedianOp) -> None:
        # Resolve the two base points
        if op.triangle is not None:
            if op.triangle not in self._triangle_vertices:
                raise LoweringError(f"median: triangle {op.triangle!r} not found")
            all_verts = self._triangle_vertices[op.triangle]
            base_pts = [v for v in all_verts if v != op.from_vertex]
            if len(base_pts) != 2:
                raise LoweringError(
                    f"median: from_vertex {op.from_vertex!r} not in triangle {op.triangle!r}"
                )
        else:
            base_pts = list(op.to_side)
        p, q = base_pts[0], base_pts[1]
        mid_id = op.mid
        self._defs.append(PointMidpoint(id=mid_id, p=p, q=q))
        self._defs.append(Segment(id=op.id, a=op.from_vertex, b=mid_id))
        self._point_ids.append(mid_id)
        self._drawable.add(op.id)

    # ------------------------------------------------------------------
    # Annotation expansion
    # ------------------------------------------------------------------

    def _resolve_style(self, style: str | dict | None) -> str | None:
        """Resolve a DrawObj.style to a StyleId string suitable for RenderBase.style.

        - None → None
        - str → returned as-is (named style ref or bare TikZ color name)
        - dict → registered in self._styles under an auto-generated key, key returned
        """
        if style is None:
            return None
        if isinstance(style, str):
            return style
        self._inline_style_counter += 1
        key = f"__style_{self._inline_style_counter}"
        self._styles[key] = style
        return key

    def _resolve_angle_mark(self, mark: Any) -> tuple[str, str, str]:
        """Return (a, vertex, b) resolving at/of shorthand if used."""
        if mark.a is not None:
            return (mark.a, mark.vertex, mark.b)
        tri_id = mark.of
        if tri_id not in self._triangle_vertices:
            raise LoweringError(
                f"{mark.kind}: triangle {tri_id!r} not found — available: {list(self._triangle_vertices)}"
            )
        verts = self._triangle_vertices[tri_id]
        vertex = mark.at
        if vertex not in verts:
            raise LoweringError(
                f"{mark.kind}: vertex {vertex!r} not in triangle {tri_id!r} (vertices: {verts})"
            )
        others = [v for v in verts if v != vertex]
        return (others[0], vertex, others[1])

    def _angle_deg(self, a: str, vertex: str, b: str) -> float | None:
        """Compute unsigned angle a-vertex-b in degrees from coord_floats, or None."""
        if not all(p in self._coord_floats for p in (a, vertex, b)):
            return None
        ax, ay = self._coord_floats[a]
        vx, vy = self._coord_floats[vertex]
        bx, by = self._coord_floats[b]
        v1 = (ax - vx, ay - vy)
        v2 = (bx - vx, by - vy)
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        cross = abs(v1[0] * v2[1] - v1[1] * v2[0])
        return math.degrees(math.atan2(cross, dot))

    def _candidate_angles_at(self, vertex: str, expected: float | str) -> str:
        """Return a string listing angles at vertex that match expected, for error hints."""
        target: float | None = None
        category: str | None = None
        if isinstance(expected, (int, float)):
            target = expected
        else:
            category = expected

        other_pts = [
            pid for pid in self._point_ids
            if pid != vertex and pid in self._coord_floats and not pid.startswith("__")
        ]
        matches: list[str] = []
        for i in range(len(other_pts)):
            for j in range(i + 1, len(other_pts)):
                deg = self._angle_deg(other_pts[i], vertex, other_pts[j])
                if deg is None:
                    continue
                if target is not None and abs(deg - target) <= 5.0:
                    matches.append(f"{other_pts[i]}-{vertex}-{other_pts[j]} = {deg:.1f}°")
                elif category is not None:
                    cat = "right" if abs(deg - 90) < 5 else ("acute" if deg < 90 else "obtuse")
                    if cat == category:
                        matches.append(f"{other_pts[i]}-{vertex}-{other_pts[j]} = {deg:.1f}° ({cat})")
        if not matches:
            return ""
        return " | candidates: " + ", ".join(matches)

    def _check_angle_expected(self, a: str, vertex: str, b: str, expected: Any) -> None:
        """Validate angle a-vertex-b against expected value. Raises LoweringError on mismatch."""
        angle_deg = self._angle_deg(a, vertex, b)
        if angle_deg is None:
            return  # coords not available at lowering time; defer to IR check

        if isinstance(expected, (int, float)):
            if abs(angle_deg - expected) > 5.0:
                hint = self._candidate_angles_at(vertex, expected)
                raise LoweringError(
                    f"MarkAngle at {vertex}: expected {expected}° but "
                    f"{a}-{vertex}-{b} = {angle_deg:.1f}°{hint}"
                )
        else:
            cat = "right" if abs(angle_deg - 90) < 5 else ("acute" if angle_deg < 90 else "obtuse")
            if cat != expected:
                hint = self._candidate_angles_at(vertex, expected)
                raise LoweringError(
                    f"MarkAngle at {vertex}: expected {expected} but "
                    f"{a}-{vertex}-{b} = {angle_deg:.1f}° ({cat}){hint}"
                )

    def _apply_annotations(self, ann: DSLAnnotations, dsl_ops: list | None = None) -> None:
        import warnings

        # Copy named styles from annotations into the IR styles dict
        for name, props in ann.styles.items():
            self._styles[name] = props

        # Warn when auto_draw_all is off but no explicit draws were provided
        if not ann.auto_draw_all and not ann.draws:
            warnings.warn(
                "auto_draw_all is false but no explicit draws provided — "
                "nothing will be drawn. Did you forget to add draws?",
                UserWarning,
                stacklevel=2,
            )

        # Collect object IDs that have explicit draws so auto_draw_all can skip them
        explicit_draw_obj_ids: set[str] = {d.obj for d in ann.draws if d.obj is not None}

        if ann.auto_draw_all:
            # Build set of explicitly hidden op IDs
            hidden_ids: set[str] = set()
            if dsl_ops:
                for op in dsl_ops:
                    if not op.visible:
                        hidden_ids.add(op.id)
            for obj_id in self._drawable:
                if not obj_id.startswith("__"):
                    if obj_id in hidden_ids:
                        continue  # explicitly hidden — do not auto-draw
                    if obj_id in explicit_draw_obj_ids:
                        continue  # explicit draw takes precedence (preserves style)
                    self._renders.append(Draw(obj=obj_id))
            # Emit a single DrawPoints for all non-implicit points
            non_implicit = [pid for pid in self._point_ids if not pid.startswith("__")]
            if non_implicit:
                self._renders.append(DrawPoints(points=non_implicit))

        if ann.auto_label_points:
            for pid in self._point_ids:
                if not pid.startswith("__"):
                    self._renders.append(LabelPoint(p=pid))

        if ann.auto_mark_right_angles:
            for triple in self._right_angle_triples:
                a, vertex, b = triple
                self._renders.append(MarkRightAngles(angles=[AnglePoints(a=a, o=vertex, b=b)]))

        angle_groups: dict[int, list[AnglePoints]] = {}
        proportional_pairs: list[list[str]] = []
        for mark in ann.marks:
            if isinstance(mark, MarkAngle):
                a, vertex, b = self._resolve_angle_mark(mark)
                if mark.expected is not None:
                    self._check_angle_expected(a, vertex, b, mark.expected)
                self._renders.append(MarkAngles(
                    angles=[AnglePoints(a=a, o=vertex, b=b)],
                    group=str(mark.group) if mark.group is not None else None,
                ))
                if mark.group is not None:
                    angle_groups.setdefault(mark.group, []).append(AnglePoints(a=a, o=vertex, b=b))
            elif isinstance(mark, MarkRightAngle):
                a, vertex, b = self._resolve_angle_mark(mark)
                self._renders.append(MarkRightAngles(
                    angles=[AnglePoints(a=a, o=vertex, b=b)],
                ))
                self._checks.append(RightAngle(
                    angle=AnglePoints(a=a, o=vertex, b=b),
                    source=f"annotation: mark_right_angle({a},{vertex},{b})",
                ))
            elif isinstance(mark, MarkEqualLengths):
                seg_ids = [self._ensure_segment(pair[0], pair[1]) for pair in mark.segments]
                group_str = str(mark.group) if mark.group is not None else None
                self._renders.append(MarkSegments(segs=seg_ids, group=group_str))
                if len(seg_ids) >= 2:
                    self._checks.append(EqualLength(
                        segs=seg_ids,
                        source=f"annotation: mark_equal_lengths group={mark.group}",
                    ))
            elif isinstance(mark, MarkParallel):
                seg_ids = [self._ensure_segment(pair[0], pair[1]) for pair in mark.segments]
                group_str = f"parallel_{mark.group}" if mark.group is not None else "parallel"
                self._renders.append(MarkSegments(segs=seg_ids, group=group_str))
                for i in range(len(seg_ids)):
                    for j in range(i + 1, len(seg_ids)):
                        self._checks.append(Parallel(
                            l1=seg_ids[i], l2=seg_ids[j],
                            source=f"annotation: mark_parallel group={mark.group}",
                        ))
            elif isinstance(mark, MarkProportional):
                seg_ids = [self._ensure_segment(pair[0], pair[1]) for pair in mark.segments]
                group_str = f"proportional_{mark.group}" if mark.group is not None else "proportional"
                self._renders.append(MarkSegments(segs=seg_ids, group=group_str))
                # Collect the pair for cross-entry ratio checks below
                if len(seg_ids) >= 2:
                    proportional_pairs.append(seg_ids)

        # Cross-entry proportionality: all mark_proportional entries claim the
        # same ratio.  e.g. [AB,DE], [BC,EF], [AC,DF] → AB/DE == BC/EF == AC/DF.
        if len(proportional_pairs) >= 2:
            ref = proportional_pairs[0]
            for i in range(1, len(proportional_pairs)):
                cur = proportional_pairs[i]
                self._checks.append(RatioEqual(
                    s1=ref[0], s2=ref[1],
                    s3=cur[0], s4=cur[1],
                    source="annotation: mark_proportional (constant ratio)",
                ))

        for group_id, angles in angle_groups.items():
            for i in range(len(angles)):
                for j in range(i + 1, len(angles)):
                    self._checks.append(AngleEqual(
                        a1=angles[i], a2=angles[j],
                        source=f"annotation: mark_angle group={group_id}",
                    ))

        for label in ann.labels:
            if isinstance(label, DSLLabelSegment):
                p, q = label.endpoints[0], label.endpoints[1]
                seg_id = self._ensure_segment(p, q)
                self._renders.append(IRLabelSegment(seg=seg_id, text=label.text))

        # Explicit draws (with optional per-element styles)
        for draw_obj in ann.draws:
            style_key = self._resolve_style(draw_obj.style)
            if draw_obj.endpoints is not None:
                seg_id = self._ensure_segment(draw_obj.endpoints[0], draw_obj.endpoints[1])
                self._renders.append(Draw(obj=seg_id, style=style_key))
            else:
                self._renders.append(Draw(obj=draw_obj.obj, style=style_key))

    def _ensure_segment(self, p: str, q: str) -> str:
        """Return the id of a Segment def for endpoints (p, q), creating one if needed."""
        for d in self._defs:
            if isinstance(d, Segment) and {d.a, d.b} == {p, q}:
                return d.id
        seg_id = f"__mark_seg_{p}_{q}"
        self._defs.append(Segment(id=seg_id, a=p, b=q))
        return seg_id

    # ------------------------------------------------------------------
    # Canvas
    # ------------------------------------------------------------------

    def _auto_canvas(self) -> Canvas:
        """Compute canvas from solved coordinate floats with 1-unit padding."""
        if not self._coord_floats:
            return Canvas()  # default
        xs = [c[0] for c in self._coord_floats.values()]
        ys = [c[1] for c in self._coord_floats.values()]
        pad = 1.0
        return Canvas(
            xmin=round(min(xs) - pad, 1),
            xmax=round(max(xs) + pad, 1),
            ymin=round(min(ys) - pad, 1),
            ymax=round(max(ys) + pad, 1),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _add(self, stmt: DefStmt) -> None:
        self._defs.append(stmt)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lower_to_ir(dsl: RecipeDSL) -> DiagramIR:
    """Compile RecipeDSL to DiagramIR.

    Args:
        dsl: A validated RecipeDSL object.

    Returns:
        DiagramIR ready for compile_defs() -> run_checks() -> ir_to_tikz().

    Raises:
        LoweringError: If the DSL cannot be lowered (e.g., undefined reference).
    """
    return _Lowerer().lower(dsl)
