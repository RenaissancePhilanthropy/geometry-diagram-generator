from __future__ import annotations

import math
from graphlib import CycleError, TopologicalSorter
from random import Random
from typing import Any

import sympy as sp
import sympy.geometry as spg

import geometry_diagrams.ir.ir as ir
from geometry_diagrams.ir.errors import ExprEvalError, IntersectionError, IRCompileError, PickError, UndefinedRefError
from geometry_diagrams.ir.refs import def_references

# Symbol table: maps definition id -> SymPy geometry object
SymTable = dict[str, Any]


class Arc:
    """Marker type for a circular arc in the symbol table.

    SymPy has no native Arc type, so we store this lightweight wrapper.
    ``center``, ``start``, ``end`` are SymPy ``Point`` objects, and
    ``radius`` is a numeric (sympy expression) = ``center.distance(start)``.
    The arc sweeps counter-clockwise from ``start`` to the point where the
    ray ``center → end`` meets the circle.
    """

    __slots__ = ("center", "start", "end", "radius", "reflex")

    def __init__(self, center: spg.Point, start: spg.Point, end: spg.Point, radius: Any, reflex: bool = False):
        self.center = center
        self.start = start
        self.end = end
        self.radius = radius
        self.reflex = reflex

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Arc(center={self.center}, start={self.start}, end={self.end}, r={self.radius})"


class Sector:
    """Marker type for a closed circular sector in the symbol table.

    Represents the pie-slice region (center + arc). Like Arc, SymPy has no
    native Sector type. Fields mirror Arc but the object is treated as a
    closed fillable region rather than just the curved edge.
    """

    __slots__ = ("center", "start", "end", "radius", "reflex")

    def __init__(self, center: spg.Point, start: spg.Point, end: spg.Point, radius: Any, reflex: bool = False):
        self.center = center
        self.start = start
        self.end = end
        self.radius = radius
        self.reflex = reflex

    def __repr__(self) -> str:  # pragma: no cover
        return f"Sector(center={self.center}, start={self.start}, end={self.end}, r={self.radius})"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compile_defs(
    diagram: ir.DiagramIR,
    *,
    rng: Random | None = None,
) -> SymTable:
    """
    Walk diagram.define in topological order, compiling each DefStmt to a
    SymPy geometry object. Returns a symbol table mapping each definition's
    id to its resolved object.

    Args:
        diagram: The full DiagramIR.
        rng: RNG for PointFree / PointOnRandom. Defaults to Random(42).

    Raises:
        UndefinedRefError: A referenced id is not yet in the symbol table.
        IntersectionError: An intersection produced no usable points.
        PickError: A pick rule could not select a unique candidate.
        ExprEvalError: A string expression could not be evaluated.
    """
    if rng is None:
        rng = Random(42)

    canvas = diagram.canvas or ir.Canvas()
    params: dict[str, Any] = {}
    if diagram.params:
        for name, raw in diagram.params.assign.items():
            params[name] = _eval_expr(raw, {}, def_id="<params>")

    all_ids = {stmt.id for stmt in diagram.define}
    stmts_by_id = {stmt.id: stmt for stmt in diagram.define}

    # Build a mapping from polygon sub-vertex names → their parent polygon ID.
    # PolygonExterior and PolygonOnEdge register sub-vertices in sym as a side effect,
    # so any DefStmt that references a sub-vertex name needs to depend on the polygon.
    poly_vertex_to_poly: dict[str, str] = {}
    for stmt in diagram.define:
        if isinstance(stmt, ir.PolygonExterior):
            names = stmt.vertex_names or [f"{stmt.id}_v{i}" for i in range(stmt.sides)]
            # Only register NEW vertices (skip base vertices a=names[0], b=names[1]).
            # Base vertices are inputs from a prior statement; registering them here
            # would overwrite the parent polygon's ownership and create a self-loop.
            for vname in names[2:]:
                if vname not in all_ids:  # only synthesized names, not real DefStmts
                    poly_vertex_to_poly[vname] = stmt.id
        if isinstance(stmt, ir.PolygonOnEdge):
            for vname in stmt.vertex_names[2:]:   # only new vertices
                if vname not in all_ids:
                    poly_vertex_to_poly[vname] = stmt.id

    # Build dependency graph and sort topologically so forward references work.
    # Substitute polygon sub-vertex refs with their parent polygon so the sort
    # correctly places the polygon before any statement that uses its vertices.
    graph: dict[str, set[str]] = {}
    for stmt in diagram.define:
        raw_refs = def_references(stmt)
        resolved = {poly_vertex_to_poly.get(r, r) for r in raw_refs}
        graph[stmt.id] = resolved & all_ids

    try:
        order = list(TopologicalSorter(graph).static_order())
    except CycleError as e:
        raise IRCompileError("<cycle>", f"Circular dependency in definitions: {e}") from e

    sym: SymTable = {}
    for sid in order:
        stmt = stmts_by_id[sid]
        obj = _compile_one(stmt, sym, params, canvas, rng, all_def_ids=all_ids)
        sym[stmt.id] = obj
        # PolygonExterior: also register its computed vertices as sub-points.
        # Use explicit vertex_names if provided (lowerer fills these); otherwise
        # fall back to the auto-generated {id}_v{i} pattern.
        if isinstance(stmt, ir.PolygonExterior) and isinstance(obj, spg.Polygon):
            for i, vertex in enumerate(obj.vertices):
                if stmt.vertex_names and i < len(stmt.vertex_names):
                    sub_id = stmt.vertex_names[i]
                else:
                    sub_id = f"{stmt.id}_v{i}"
                if sub_id not in sym:
                    sym[sub_id] = vertex
        # PolygonOnEdge: register vertices[2..N-1] in sym
        if isinstance(stmt, ir.PolygonOnEdge) and isinstance(obj, spg.Polygon):
            for i, vname in enumerate(stmt.vertex_names):
                if vname not in sym:
                    sym[vname] = obj.vertices[i]

    return sym


# ---------------------------------------------------------------------------
# Single-statement compiler
# ---------------------------------------------------------------------------

def _compile_one(
    stmt: ir.DefStmt,
    sym: SymTable,
    params: dict[str, Any],
    canvas: ir.Canvas,
    rng: Random,
    all_def_ids: set[str] | None = None,
) -> Any:
    did = stmt.id  # for error messages

    def ev(raw: int | float | str) -> sp.Basic:
        return _eval_expr(raw, params, def_id=did)

    def ref(obj_id: str) -> Any:
        return _resolve(sym, obj_id, def_id=did, all_def_ids=all_def_ids)

    match stmt:
        # --- Points ---
        case ir.PointFixed(x=x, y=y):
            return spg.Point(ev(x), ev(y))

        case ir.PointFree(hint_xy=hint):
            if hint is not None:
                return spg.Point(sp.S(hint[0]), sp.S(hint[1]))
            # Sample uniformly within canvas bounds
            x = rng.uniform(float(canvas.xmin), float(canvas.xmax))
            y = rng.uniform(float(canvas.ymin), float(canvas.ymax))
            return spg.Point(sp.Float(x), sp.Float(y))

        case ir.PointOn(on=on_id, how=how):
            obj = ref(on_id)
            return _point_on_object(obj, how, sym, rng, did)

        case ir.PointMidpoint(p=p_id, q=q_id):
            return spg.Segment(ref(p_id), ref(q_id)).midpoint

        case ir.PointBetween(a=a_id, b=b_id, ratio=ratio):
            a = ref(a_id)
            b = ref(b_id)
            t = sp.S(_parse_between_ratio(ratio))
            return spg.Point(a.x + t * (b.x - a.x), a.y + t * (b.y - a.y))

        case ir.PointFoot(source=source_id, onto=onto_id):
            source_pt = ref(source_id)
            onto_obj = ref(onto_id)
            # Project onto the underlying infinite line (works for Line/Segment/Ray)
            if isinstance(onto_obj, spg.Line):
                line = onto_obj
            elif isinstance(onto_obj, (spg.Segment, spg.Ray)):
                line = spg.Line(onto_obj.p1, onto_obj.p2)
            else:
                raise IRCompileError(did, f"point_foot: 'onto' must be a line/segment/ray, got {type(onto_obj).__name__}")
            perp = line.perpendicular_line(source_pt)
            candidates = line.intersection(perp)
            pts = [c for c in candidates if isinstance(c, spg.Point)]
            if not pts:
                raise IntersectionError(did, f"no foot from {source_id!r} onto {onto_id!r}")
            return pts[0]

        case ir.PointRotate(center=center_id, source=source_id, angle=angle):
            return ref(source_id).rotate(ev(angle), ref(center_id))

        case ir.PointReflect(source=source_id, across=across_id):
            source_pt = ref(source_id)
            across_obj = ref(across_id)
            if isinstance(across_obj, spg.Point):
                # Point symmetry: 2*center - source
                return spg.Point(2 * across_obj.x - source_pt.x, 2 * across_obj.y - source_pt.y)
            elif isinstance(across_obj, spg.Line):
                return source_pt.reflect(across_obj)           # Point.reflect(Line) — NOT Line.reflect(Point)
            elif isinstance(across_obj, (spg.Segment, spg.Ray)):
                line = spg.Line(across_obj.p1, across_obj.p2)
                return source_pt.reflect(line)                 # Point.reflect(Line) — NOT Line.reflect(Point)
            else:
                raise IRCompileError(did, f"point_reflect: 'across' must be a point or linear object, got {type(across_obj).__name__}")

        case ir.PointTriangleCenter(tri=tri_id, which=which):
            tri = ref(tri_id)
            return getattr(tri, which)

        case ir.PointIntersection(obj1=obj1_id, obj2=obj2_id, pick=pick):
            if obj1_id == obj2_id:
                raise IRCompileError(did, f"cannot intersect '{obj1_id}' with itself — use two distinct objects")
            obj1, obj2 = ref(obj1_id), ref(obj2_id)
            try:
                raw = obj1.intersection(obj2)
            except ValueError as exc:
                if "LinearEntity" in str(exc):
                    raise IRCompileError(
                        did,
                        f"intersection failed: line/circle intersection received invalid arguments — "
                        f"ensure the line is defined as a LineThrough, Ray, or Segment, not as two separate points "
                        f"(underlying error: {exc})"
                    ) from exc
                raise
            # SymPy may return the geometry object itself (not a list) when objects
            # are identical (e.g. two equal circles → Circle, not []).
            candidates = raw if isinstance(raw, list) else []
            points = [c for c in candidates if isinstance(c, spg.Point)]
            if not points:
                raise IntersectionError(did, f"no intersection points between {obj1_id!r} and {obj2_id!r}")
            return _apply_pick(points, pick, sym, did, canvas=canvas)

        case ir.PointAlias(ref=ref_id):
            return ref(ref_id)

        # --- Lines ---
        case ir.LineThrough(p=p_id, q=q_id):
            return spg.Line(ref(p_id), ref(q_id))

        case ir.LineParallelThrough(through=through_id, to_line=line_id):
            return ref(line_id).parallel_line(ref(through_id))

        case ir.LinePerpendicularThrough(through=through_id, to_line=line_id):
            return ref(line_id).perpendicular_line(ref(through_id))

        case ir.LineAngleBisector(a=a_id, vertex=vertex_id, b=b_id):
            return _angle_bisector_line(ref(a_id), ref(vertex_id), ref(b_id), did)

        case ir.LineTangent(point=point_id, circle=circle_id, pick=pick):
            circle = ref(circle_id)
            point = ref(point_id)
            tangents = circle.tangent_lines(point)
            if not tangents:
                raise IntersectionError(did, f"no tangent lines from {point_id!r} to {circle_id!r}")
            # Tangent lines are Line objects; apply pick treating them as Line candidates
            if pick is None:
                if len(tangents) == 1:
                    return tangents[0]
                raise PickError(did, f"ambiguous: {len(tangents)} tangent lines, no pick rule")
            # For tangents, PickIndex is the natural pick; spatial picks use touch point
            match pick:
                case ir.PickIndex(k=k):
                    if k >= len(tangents):
                        raise PickError(did, f"index {k} out of range for {len(tangents)} tangent lines")
                    return tangents[k]
                case ir.PickUpperOfLine(a=a_id, b=b_id) | ir.PickLowerOfLine(a=a_id, b=b_id):
                    a_pt = _resolve(sym, a_id, def_id=did)
                    b_pt = _resolve(sym, b_id, def_id=did)
                    sign_target = 1 if isinstance(pick, ir.PickUpperOfLine) else -1

                    def _touch_point(t_line):
                        pts = t_line.intersection(circle)
                        return pts[0] if pts else None

                    candidates = [
                        t for t in tangents
                        if (tp := _touch_point(t)) is not None
                        and float(_cross_sign(a_pt, b_pt, tp).evalf()) * sign_target > 0
                    ]
                    direction = "upper" if sign_target > 0 else "lower"
                    if not candidates:
                        raise PickError(did, f"no {direction} tangent relative to {a_id}→{b_id}")
                    return candidates[0]
                case _:
                    return tangents[0]

        # --- Segments / Rays ---
        case ir.Segment(a=a_id, b=b_id):
            return spg.Segment(ref(a_id), ref(b_id))

        case ir.Ray(a=a_id, b=b_id):
            return spg.Ray(ref(a_id), ref(b_id))

        # --- Circles ---
        case ir.CircleCenterPoint(center=center_id, through=through_id):
            c, p = ref(center_id), ref(through_id)
            return spg.Circle(c, c.distance(p))

        case ir.CircleCenterRadius(center=center_id, radius=radius):
            return spg.Circle(ref(center_id), ev(radius))

        case ir.CircleThrough3(a=a_id, b=b_id, c=c_id):
            return spg.Circle(ref(a_id), ref(b_id), ref(c_id))

        # --- Arcs ---
        case ir.ArcCenterStartEnd(center=center_id, start=start_id, end=end_id, reflex=reflex):
            c, s, e = ref(center_id), ref(start_id), ref(end_id)
            r = c.distance(s)
            return Arc(center=c, start=s, end=e, radius=r, reflex=reflex)

        case ir.SectorCenterStartEnd(center=center_id, start=start_id, end=end_id, reflex=reflex):
            c, s, e = ref(center_id), ref(start_id), ref(end_id)
            r = c.distance(s)
            return Sector(center=c, start=s, end=e, radius=r, reflex=reflex)

        # --- Ellipses ---
        case ir.EllipseCenterAxes(center=center_id, hradius=hradius, vradius=vradius):
            return spg.Ellipse(ref(center_id), ev(hradius), ev(vradius))

        case ir.EllipseBBox(corner1=c1_id, corner2=c2_id):
            p1, p2 = ref(c1_id), ref(c2_id)
            center = spg.Point((p1.x + p2.x) / 2, (p1.y + p2.y) / 2)
            hr = sp.Abs(p2.x - p1.x) / 2
            vr = sp.Abs(p2.y - p1.y) / 2
            if float(hr.evalf()) < 1e-10 or float(vr.evalf()) < 1e-10:
                raise IRCompileError(did, "EllipseBBox: bounding box has zero width or height")
            return spg.Ellipse(center, hr, vr)

        case ir.EllipseFoci(focus1=f1_id, focus2=f2_id, major_axis=major_axis, through=through_id):
            f1, f2 = ref(f1_id), ref(f2_id)
            center = spg.Point((f1.x + f2.x) / 2, (f1.y + f2.y) / 2)
            c_dist = float(f1.distance(f2).evalf()) / 2  # focal distance c
            # Determine orientation
            dx = float((f2.x - f1.x).evalf())
            dy = float((f2.y - f1.y).evalf())
            if abs(dy) > 1e-9 and abs(dx) > 1e-9:
                raise IRCompileError(
                    did, f"EllipseFoci: foci must be axis-aligned (horizontal or vertical), "
                    f"got dx={dx:.4g}, dy={dy:.4g}"
                )
            horizontal = abs(dy) <= 1e-9  # foci on same horizontal line → major axis horizontal
            if major_axis is not None:
                a = float(ev(major_axis).evalf()) / 2
            else:
                p = ref(through_id)
                a = (float(f1.distance(p).evalf()) + float(f2.distance(p).evalf())) / 2
            b_sq = a ** 2 - c_dist ** 2
            if b_sq < 0:
                raise IRCompileError(did, "EllipseFoci: major axis too short (b² < 0)")
            b = b_sq ** 0.5
            if horizontal:
                return spg.Ellipse(center, sp.S(a), sp.S(b))
            else:
                return spg.Ellipse(center, sp.S(b), sp.S(a))

        case ir.EllipseCenterEccentricity(
            center=center_id, semi_major=semi_major, eccentricity=eccentricity, orientation=orientation
        ):
            a = float(ev(semi_major).evalf())
            e = float(ev(eccentricity).evalf())
            if not (0 <= e < 1):
                raise IRCompileError(did, f"EllipseCenterEccentricity: eccentricity must be in [0,1), got {e}")
            b = a * (1 - e ** 2) ** 0.5
            if orientation == "horizontal":
                return spg.Ellipse(ref(center_id), sp.S(a), sp.S(b))
            else:
                return spg.Ellipse(ref(center_id), sp.S(b), sp.S(a))

        # --- Higher-order shapes ---
        case ir.Triangle(a=a_id, b=b_id, c=c_id):
            return spg.Triangle(ref(a_id), ref(b_id), ref(c_id))

        case ir.Polygon(points=point_ids):
            return spg.Polygon(*[ref(pid) for pid in point_ids])

        case ir.PolygonExterior(a=a_id, b=b_id, ref=ref_id, sides=sides):
            a_pt = ref(a_id)
            b_pt = ref(b_id)
            ref_pt = ref(ref_id)
            if sides < 3:
                raise IRCompileError(did, f"polygon_exterior requires sides >= 3, got {sides}")
            cross = _cross_sign(a_pt, b_pt, ref_pt)
            cross_val = float(cross.evalf())
            if abs(cross_val) < 1e-10:
                raise IRCompileError(
                    did, f"ref point {ref_id!r} is on line {a_id!r}-{b_id!r}; cannot determine exterior side"
                )
            # We want the polygon on the OPPOSITE side from ref.
            # rot > 0 puts the polygon to the right of a→b; rot < 0 puts it to the left.
            # The rotation angle is the interior angle of a regular n-gon: (n-2)π/n.
            # Rotating prev2 around prev1 by this angle produces the correct next vertex.
            rot = sp.Rational(1, 1) if cross_val > 0 else sp.Rational(-1, 1)
            step = sp.Rational(sides - 2, sides) * sp.pi
            rot_angle = rot * step
            # Build vertices: start from a and b, then generate n-2 more
            # by rotating the last edge endpoint around the previous vertex
            vertices = [a_pt, b_pt]
            for _ in range(sides - 2):
                prev2 = vertices[-2]
                prev1 = vertices[-1]
                new_v = prev2.rotate(rot_angle, prev1)
                vertices.append(new_v)
            return spg.Polygon(*vertices)

        case ir.PolygonOnEdge(a=a_id, b=b_id, ref=ref_id):
            a_pt = ref(a_id)
            b_pt = ref(b_id)
            ref_pt = ref(ref_id)
            n = len(stmt.vertex_names)

            # Validate claimed base length if provided
            if stmt.claimed_base_length is not None:
                base_dist = float(a_pt.distance(b_pt).evalf())
                if abs(base_dist - stmt.claimed_base_length) > 1e-4:
                    raise IRCompileError(
                        did,
                        f"polygon_on_edge: claimed base length {stmt.claimed_base_length} "
                        f"does not match actual |{a_id}–{b_id}| = {base_dist:.6f}. "
                        f"Omit side_lengths[0] to let it be inferred automatically."
                    )

            # Determine orientation sign from ref_point
            cross = _cross_sign(a_pt, b_pt, ref_pt)
            cross_val = float(cross.evalf())
            if abs(cross_val) < 1e-10:
                raise IRCompileError(
                    did, f"ref_point {ref_id!r} lies on line {a_id!r}–{b_id!r}; cannot determine side"
                )
            # sign: +1 = CCW turns (polygon to LEFT of a→b)
            #       -1 = CW turns  (polygon to RIGHT of a→b)
            # We want polygon on OPPOSITE side from ref_point.
            # cross_val > 0 → ref is LEFT of a→b → polygon goes RIGHT → sign = -1
            # cross_val < 0 → ref is RIGHT of a→b → polygon goes LEFT → sign = +1
            sign = -1.0 if cross_val > 0 else 1.0

            # Numeric base coordinates
            ax = float(a_pt.x.evalf()); ay = float(a_pt.y.evalf())
            bx = float(b_pt.x.evalf()); by = float(b_pt.y.evalf())
            heading = math.degrees(math.atan2(by - ay, bx - ax))

            # Turtle walk from b, turning at each vertex and walking the non-base sides
            # vertices: [a, b, v2, v3, ..., v_{n-1}]
            # side_lengths: [b→v2, v2→v3, ..., v_{n-1}→a]  (N-1 values)
            vertices_pts = [a_pt, b_pt]
            x, y = bx, by
            for i in range(n - 1):
                # Turn at vertex i+1 (angles[i+1])
                exterior = sign * (180.0 - stmt.angles[i + 1])
                heading += exterior
                dx = stmt.side_lengths[i] * math.cos(math.radians(heading))
                dy = stmt.side_lengths[i] * math.sin(math.radians(heading))
                x += dx
                y += dy
                if i < n - 2:
                    vertices_pts.append(spg.Point(sp.Float(x), sp.Float(y)))

            return spg.Polygon(*vertices_pts)

        case _:
            raise IRCompileError(did, f"unhandled definition kind: {stmt.kind!r}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _eval_expr(
    raw: int | float | str,
    params: dict[str, Any],
    *,
    def_id: str,
    sym: "SymTable | None" = None,
) -> sp.Basic:
    """Evaluate a numeric or string expression to a SymPy value.

    Supports geometric functions length(A,B), radius(c), angle(A,B,C)
    when sym is provided. Raises ExprEvalError if a geometric function
    is called but sym is None.
    """
    if isinstance(raw, (int, float)):
        return sp.S(raw)

    import math as _math

    def _resolve_geo(arg: Any, label: str) -> Any:
        """Resolve a geo-function argument to an object in sym.

        sympify passes arguments as either SymPy Symbol objects (for
        unrecognised names) or as the value already bound in locals_map
        (for names that clash with SymPy builtins like Q or E).  We
        handle both cases: if arg is already a geometry object (i.e. it
        came through locals_map), return it directly; otherwise coerce
        to str and look it up in sym.
        """
        if sym is None:
            raise ExprEvalError(def_id, f"{label}() requires sym table (not available here)")
        # If arg is already a geometry object from sym, return it directly.
        if isinstance(arg, (spg.Point, spg.Circle, spg.Line, spg.Segment, spg.Ray,
                            spg.Triangle, spg.Polygon)):
            return arg
        key = str(arg)
        obj = sym.get(key)
        if obj is None:
            raise ExprEvalError(def_id, f"{label}(): unknown id {key!r}")
        return obj

    def _length(a_arg: Any, b_arg: Any) -> sp.Basic:
        if sym is None:
            raise ExprEvalError(def_id, "length() requires sym table (not available here)")
        a_pt = _resolve_geo(a_arg, "length")
        b_pt = _resolve_geo(b_arg, "length")
        return sp.Float(float(a_pt.distance(b_pt).evalf()))

    def _radius(c_arg: Any) -> sp.Basic:
        if sym is None:
            raise ExprEvalError(def_id, "radius() requires sym table (not available here)")
        c_obj = _resolve_geo(c_arg, "radius")
        if not hasattr(c_obj, "radius"):
            raise ExprEvalError(def_id, f"radius(): {c_arg!r} is not a circle")
        return sp.Float(float(c_obj.radius.evalf()))

    def _angle(a_arg: Any, vertex_arg: Any, b_arg: Any) -> sp.Basic:
        """Non-reflex angle at vertex (degrees)."""
        if sym is None:
            raise ExprEvalError(def_id, "angle() requires sym table (not available here)")
        a_pt = _resolve_geo(a_arg, "angle")
        v_pt = _resolve_geo(vertex_arg, "angle")
        b_pt = _resolve_geo(b_arg, "angle")
        va_x = float((a_pt.x - v_pt.x).evalf())
        va_y = float((a_pt.y - v_pt.y).evalf())
        vb_x = float((b_pt.x - v_pt.x).evalf())
        vb_y = float((b_pt.y - v_pt.y).evalf())
        dot = va_x * vb_x + va_y * vb_y
        mag_a = _math.hypot(va_x, va_y)
        mag_b = _math.hypot(vb_x, vb_y)
        if mag_a < 1e-12 or mag_b < 1e-12:
            raise ExprEvalError(def_id, "angle(): degenerate angle — vertex coincides with a leg point")
        cos_theta = max(-1.0, min(1.0, dot / (mag_a * mag_b)))
        return sp.Float(_math.degrees(_math.acos(cos_theta)))

    locals_map: dict[str, Any] = {
        "pi": sp.pi,
        "sqrt": sp.sqrt,
        "E": sp.E,
        "length": _length,
        "radius": _radius,
        "angle": _angle,
        **params,
    }
    # Populate sym entries into locals so SymPy resolves identifier names
    # (including those that clash with SymPy builtins like Q, E, S) to the
    # geometry objects rather than SymPy internal objects.
    if sym is not None:
        locals_map.update(sym)
    try:
        return sp.sympify(raw, locals=locals_map)
    except Exception as exc:
        raise ExprEvalError(def_id, f"could not evaluate {raw!r}: {exc}") from exc


def _parse_between_ratio(ratio: float | str | None) -> float:
    """Convert a ratio spec to a float t in [0, 1]."""
    if ratio is None:
        return 0.5
    if isinstance(ratio, (int, float)):
        return float(ratio)
    # Parse "m:n" string
    parts = str(ratio).split(":")
    if len(parts) == 2:
        try:
            m, n = float(parts[0]), float(parts[1])
            return m / (m + n)
        except (ValueError, ZeroDivisionError):
            pass
    # Parse "a/b" fraction string
    parts = str(ratio).split("/")
    if len(parts) == 2:
        try:
            return float(parts[0]) / float(parts[1])
        except (ValueError, ZeroDivisionError):
            pass
    raise IRCompileError("<parse_ratio>", f"Cannot parse ratio {ratio!r}; expected float, 'M:N', or 'a/b'")


def _resolve(sym: SymTable, ref_id: str, *, def_id: str, all_def_ids: set[str] | None = None) -> Any:
    """Look up ref_id in sym, raising UndefinedRefError if missing."""
    try:
        return sym[ref_id]
    except KeyError:
        if all_def_ids and ref_id in all_def_ids:
            raise UndefinedRefError(
                def_id,
                f"references '{ref_id}', which is defined later in the list — "
                f"move the definition of '{ref_id}' before '{def_id}'",
            )
        raise UndefinedRefError(def_id, f"references undefined id {ref_id!r}")


def _apply_pick(
    points: list[spg.Point2D],
    pick: ir.PickRule | None,
    sym: SymTable,
    def_id: str,
    canvas: ir.Canvas | None = None,
) -> spg.Point2D:
    """Select one point from candidates using the pick rule."""
    if pick is None:
        if len(points) == 1:
            return points[0]
        # Auto-pick heuristic: prefer in-canvas, then closest to centroid of
        # previously-defined points. Known limitation: when both candidates are
        # in-bounds (e.g. two intersections of a vertical line with a circle),
        # the centroid tiebreaker picks the closest one to the current construction
        # center of mass — this is arbitrary and may not match the LLM's intent.
        # If the intended candidate matters, always provide an explicit pick rule.
        candidates = list(points)
        if canvas is not None:
            in_bounds = [
                p for p in points
                if float(canvas.xmin) <= float(p.x) <= float(canvas.xmax)
                and float(canvas.ymin) <= float(p.y) <= float(canvas.ymax)
            ]
            if len(in_bounds) == 1:
                return in_bounds[0]
            if in_bounds:
                candidates = in_bounds
        # Pick closest to centroid of previously-defined points
        existing_pts = [v for v in sym.values() if isinstance(v, spg.Point)]
        if existing_pts:
            cx = sum(float(p.x) for p in existing_pts) / len(existing_pts)
            cy = sum(float(p.y) for p in existing_pts) / len(existing_pts)
            centroid = spg.Point(sp.Float(cx), sp.Float(cy))
            return min(candidates, key=lambda p: float(p.distance(centroid).evalf()))
        return candidates[0]

    match pick:
        case ir.PickIndex(k=k):
            if k >= len(points):
                raise PickError(def_id, f"index {k} out of range for {len(points)} candidates")
            return points[k]

        case ir.PickClosestTo(p=ref_id):
            ref_pt = _resolve(sym, ref_id, def_id=def_id)
            return min(points, key=lambda pt: pt.distance(ref_pt))

        case ir.PickOnObject(obj=obj_id):
            obj = _resolve(sym, obj_id, def_id=def_id)
            on = [p for p in points if obj.contains(p)]
            if not on:
                raise PickError(def_id, f"no candidate lies on {obj_id!r}")
            return on[0]

        case ir.PickSameSide(line=(a_id, b_id), ref_point=ref_id):
            a = _resolve(sym, a_id, def_id=def_id)
            b = _resolve(sym, b_id, def_id=def_id)
            ref_pt = _resolve(sym, ref_id, def_id=def_id)
            ref_sign = _cross_sign(a, b, ref_pt)
            same = [p for p in points if (_cross_sign(a, b, p) * ref_sign) > 0]
            if not same:
                raise PickError(def_id, f"no candidate on same side of ({a_id},{b_id}) as {ref_id!r}")
            return same[0]

        case ir.PickInsideTriangle(tri=tri_id):
            tri = _resolve(sym, tri_id, def_id=def_id)
            inside = [p for p in points if tri.encloses_point(p)]
            if not inside:
                raise PickError(def_id, f"no candidate inside triangle {tri_id!r}")
            return inside[0]

        case ir.PickBetween(a=a_id, b=b_id):
            a_pt = _resolve(sym, a_id, def_id=def_id)
            b_pt = _resolve(sym, b_id, def_id=def_id)
            seg = spg.Segment(a_pt, b_pt)
            between = [p for p in points if seg.contains(p)]
            if not between:
                direction = b_pt - a_pt
                seg_len_sq = float((direction.x**2 + direction.y**2).evalf())
                def _param(p) -> float:
                    if seg_len_sq < 1e-12:
                        return 0.0
                    dp = p - a_pt
                    return float((dp.x * direction.x + dp.y * direction.y).evalf()) / seg_len_sq

                if points:
                    ts = [_param(p) for p in points]
                    nearest_t = min(ts, key=lambda t: min(abs(t), abs(t - 1)))
                    if nearest_t < 0:
                        extra = f" (nearest candidate is before {a_id!r}, t\u2248{nearest_t:.2f})"
                    else:
                        extra = f" (nearest candidate is beyond {b_id!r}, t\u2248{nearest_t:.2f})"
                else:
                    extra = " (no intersection candidates at all)"
                raise PickError(def_id, f"no candidate lies between {a_id!r} and {b_id!r}{extra}")
            return between[0]

        case ir.PickBeyond(from_point=from_id, past_point=past_id):
            from_pt = _resolve(sym, from_id, def_id=def_id)
            past_pt = _resolve(sym, past_id, def_id=def_id)
            def _is_beyond(p: spg.Point) -> bool:
                dx_dir = float((past_pt.x - from_pt.x).evalf())
                dy_dir = float((past_pt.y - from_pt.y).evalf())
                dx_p   = float((p.x - past_pt.x).evalf())
                dy_p   = float((p.y - past_pt.y).evalf())
                return dx_dir * dx_p + dy_dir * dy_p > 0
            beyond = [p for p in points if _is_beyond(p)]
            if not beyond:
                raise PickError(def_id, f"no candidate beyond {past_id!r} from {from_id!r}")
            return beyond[0]

        case ir.PickInterior(polygon=poly_id):
            poly = _resolve(sym, poly_id, def_id=def_id)
            inside = [p for p in points if poly.encloses_point(p)]
            if not inside:
                raise PickError(def_id, f"no candidate inside polygon {poly_id!r}")
            return inside[0]

        case ir.PickExterior(polygon=poly_id):
            poly = _resolve(sym, poly_id, def_id=def_id)
            outside = [p for p in points if not poly.encloses_point(p) and not poly.contains(p)]
            if not outside:
                raise PickError(def_id, f"no candidate outside polygon {poly_id!r}")
            return outside[0]

        case ir.PickOppositeSide() as pick_rule:
            a_id, b_id = pick_rule.line_through[0], pick_rule.line_through[1]
            ref_id = pick_rule.ref_point
            a_pt = _resolve(sym, a_id, def_id=def_id)
            b_pt = _resolve(sym, b_id, def_id=def_id)
            ref_pt = _resolve(sym, ref_id, def_id=def_id)
            ref_sign = float(_cross_sign(a_pt, b_pt, ref_pt).evalf())
            opposite = [p for p in points if float(_cross_sign(a_pt, b_pt, p).evalf()) * ref_sign < 0]
            if not opposite:
                raise PickError(def_id, f"no candidate on opposite side of ({a_id},{b_id}) from {ref_id!r}")
            return opposite[0]

        case ir.PickUpperOfLine(a=a_id, b=b_id):
            a_pt = _resolve(sym, a_id, def_id=def_id)
            b_pt = _resolve(sym, b_id, def_id=def_id)
            upper = [p for p in points if float(_cross_sign(a_pt, b_pt, p).evalf()) > 0]  # type: ignore[union-attr]
            if not upper:
                _dx: Any = b_pt.x - a_pt.x
                _dy: Any = b_pt.y - a_pt.y
                angle_deg = math.degrees(math.atan2(float(_dy.evalf()), float(_dx.evalf())))
                _rev = {id(v): k for k, v in sym.items() if isinstance(v, spg.Point)}
                dists = ", ".join(
                    f"{_rev.get(id(p), '?')}: {float(_cross_sign(a_pt, b_pt, p).evalf()):+.3f}"  # type: ignore[union-attr]
                    for p in points
                )
                raise PickError(
                    def_id,
                    f"no candidate on the 'above' side of directed line {a_id!r}→{b_id!r} "
                    f"(directed angle: {angle_deg:.1f}°). "
                    f"Candidates and their signed distances: {dists}"
                )
            return upper[0]

        case ir.PickLowerOfLine(a=a_id, b=b_id):
            a_pt = _resolve(sym, a_id, def_id=def_id)
            b_pt = _resolve(sym, b_id, def_id=def_id)
            lower = [p for p in points if float(_cross_sign(a_pt, b_pt, p).evalf()) < 0]  # type: ignore[union-attr]
            if not lower:
                _dx: Any = b_pt.x - a_pt.x
                _dy: Any = b_pt.y - a_pt.y
                angle_deg = math.degrees(math.atan2(float(_dy.evalf()), float(_dx.evalf())))
                _rev = {id(v): k for k, v in sym.items() if isinstance(v, spg.Point)}
                dists = ", ".join(
                    f"{_rev.get(id(p), '?')}: {float(_cross_sign(a_pt, b_pt, p).evalf()):+.3f}"  # type: ignore[union-attr]
                    for p in points
                )
                raise PickError(
                    def_id,
                    f"no candidate on the 'below' side of directed line {a_id!r}→{b_id!r} "
                    f"(directed angle: {angle_deg:.1f}°). "
                    f"Candidates and their signed distances: {dists}"
                )
            return lower[0]

        case ir.PickChain(rules=rules):
            _FILTER_KINDS = frozenset({
                "between", "beyond", "interior", "exterior",
                "opposite_side", "upper_of_line", "lower_of_line",
                "same_side",
            })

            def _chain_apply(pts: list[spg.Point2D], rule: ir.PickRule) -> list[spg.Point2D]:
                if rule.kind in _FILTER_KINDS:
                    survivors = []
                    for p in pts:
                        try:
                            _apply_pick([p], rule, sym, def_id, canvas=canvas)
                            survivors.append(p)
                        except PickError:
                            pass
                    return survivors
                else:
                    return [_apply_pick(pts, rule, sym, def_id, canvas=canvas)]

            remaining = list(points)
            for rule in rules:
                if not remaining:
                    break
                remaining = _chain_apply(remaining, rule)
                if not remaining:
                    raise PickError(def_id, f"pick_chain: rule {rule.kind!r} eliminated all candidates")
            if not remaining:
                raise PickError(def_id, "pick_chain: all rules eliminated all candidates")
            return remaining[0]

        case _:
            raise PickError(def_id, f"unhandled pick kind: {pick.kind!r}")


def _point_on_object(
    obj: Any,
    how: ir.PointOnHow,
    sym: SymTable,
    rng: Random,
    def_id: str,
) -> spg.Point:
    """Compute a concrete point on obj using the PointOnHow method."""
    match how:
        case ir.PointOnParam(t=t):
            return _eval_param(obj, t, def_id)
        case ir.PointOnRandom():
            t = _sample_param(obj, rng)
            return _eval_param(obj, t, def_id)
        case ir.PointOnIntent(constraints=constraints):
            return _point_on_intent(obj, constraints, sym, rng, def_id)
        case _:
            raise IRCompileError(def_id, f"unhandled PointOnHow kind: {how.kind!r}")


def _sample_param(obj: Any, rng: Random) -> float:
    """Sample a parameter t appropriate for the object type."""
    if isinstance(obj, spg.Ellipse):  # covers Circle too (Circle subclasses Ellipse)
        return rng.uniform(0, 2 * math.pi)
    # Segment, Ray, Line: [0, 1) for segment; [0, 1) maps intuitively
    return rng.random()


def _eval_param(obj: Any, t: float, def_id: str) -> spg.Point:
    """Evaluate the parametric point on obj at parameter t."""
    if isinstance(obj, spg.Segment):
        a, b = obj.p1, obj.p2
        return spg.Point(a.x + sp.S(t) * (b.x - a.x), a.y + sp.S(t) * (b.y - a.y))
    if isinstance(obj, spg.Ellipse):  # covers Circle (Circle subclasses Ellipse)
        cx, cy = obj.center.x, obj.center.y
        a, b = obj.hradius, obj.vradius
        return spg.Point(cx + a * sp.cos(sp.S(t)), cy + b * sp.sin(sp.S(t)))
    if isinstance(obj, (spg.Line, spg.Ray)):
        # arbitrary_point uses a symbol; substitute t numerically
        sym_t = sp.Symbol("_t")
        apt = obj.arbitrary_point(sym_t)
        return spg.Point(apt.x.subs(sym_t, sp.S(t)), apt.y.subs(sym_t, sp.S(t)))
    raise IRCompileError(def_id, f"cannot place point on object of type {type(obj).__name__}")


def _point_on_intent(
    obj: Any,
    constraints: list[ir.SpatialConstraint],
    sym: SymTable,
    rng: Random,
    def_id: str,
    max_attempts: int = 200,
) -> spg.Point:
    """Sample points on obj until all constraints are satisfied."""
    constraint_failures: dict[str, int] = {}
    for _ in range(max_attempts):
        t = _sample_param(obj, rng)
        candidate = _eval_param(obj, t, def_id)
        ok = True
        for c in constraints:
            if not _check_spatial_constraint(c, candidate, sym):
                constraint_failures[c.kind] = constraint_failures.get(c.kind, 0) + 1
                ok = False
                break
        if ok:
            return candidate
    most_failed = max(constraint_failures, key=lambda k: constraint_failures[k], default="unknown")
    raise IRCompileError(
        def_id,
        f"Could not satisfy all constraints after {max_attempts} attempts; "
        f"most blocking: {most_failed!r}"
    )


def _check_spatial_constraint(
    constraint: ir.SpatialConstraint,
    candidate: spg.Point,
    sym: SymTable,
) -> bool:
    match constraint:
        case ir.SameSideConstraint(line=line_pts, ref=ref_id):
            a, b, ref = sym[line_pts[0]], sym[line_pts[1]], sym[ref_id]
            sign_ref = float((_cross_sign(a, b, ref)).evalf())
            sign_cand = float((_cross_sign(a, b, candidate)).evalf())
            return (sign_ref * sign_cand) > 0

        case ir.NotNearConstraint(point=pt_id, min_dist=min_d):
            ref_pt = sym[pt_id]
            return float(candidate.distance(ref_pt).evalf()) >= min_d

        case ir.ArcBetweenConstraint():
            return True  # TODO: implement full arc check

        case ir.BeyondConstraint():
            return True  # TODO: implement for segment parameterization

        case _:
            return True


def _angle_bisector_line(
    a: spg.Point2D,
    vertex: spg.Point2D,
    b: spg.Point2D,
    def_id: str,
) -> spg.Line:
    """
    Construct the interior angle bisector line of angle A-vertex-B.
    Uses the unit-vector sum method: normalize direction vecs from vertex to
    A and B, sum them to get bisector direction.
    """
    va = a - vertex
    vb = b - vertex
    ma = sp.sqrt(va.x**2 + va.y**2)
    mb = sp.sqrt(vb.x**2 + vb.y**2)
    if ma == 0 or mb == 0:
        raise IRCompileError(def_id, "degenerate angle: vertex coincides with a leg point")
    ua_x, ua_y = va.x / ma, va.y / ma
    ub_x, ub_y = vb.x / mb, vb.y / mb
    dir_x, dir_y = ua_x + ub_x, ua_y + ub_y
    if dir_x == 0 and dir_y == 0:
        # Supplementary angle: bisector is perpendicular to the line AB
        return spg.Line(vertex, vertex + spg.Point(-va.y / ma, va.x / ma))
    return spg.Line(vertex, vertex + spg.Point(dir_x, dir_y))


def _cross_sign(a: spg.Point2D, b: spg.Point2D, p: spg.Point2D) -> sp.Basic:
    """Signed cross product (B-A) × (P-A). Positive = P left of A→B."""
    ab_x, ab_y = b.x - a.x, b.y - a.y
    ap_x, ap_y = p.x - a.x, p.y - a.y
    return ab_x * ap_y - ab_y * ap_x
