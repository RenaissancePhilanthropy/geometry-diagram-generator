from __future__ import annotations

import math
from random import Random
from typing import Any

import sympy as sp
import sympy.geometry as spg

import ir.ir as ir
from ir.errors import ExprEvalError, IntersectionError, IRCompileError, PickError, UndefinedRefError

# Symbol table: maps definition id -> SymPy geometry object
SymTable = dict[str, Any]


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

    sym: SymTable = {}
    for stmt in diagram.define:
        obj = _compile_one(stmt, sym, params, canvas, rng)
        sym[stmt.id] = obj
        # PolygonExterior: also register its computed vertices as sub-points
        # v0=a, v1=b are already in sym; register v2..v_{n-1}
        if isinstance(stmt, ir.PolygonExterior) and isinstance(obj, spg.Polygon):
            for i, vertex in enumerate(obj.vertices):
                sub_id = f"{stmt.id}_v{i}"
                if sub_id not in sym:
                    sym[sub_id] = vertex

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
) -> Any:
    did = stmt.id  # for error messages

    def ev(raw: int | float | str) -> sp.Basic:
        return _eval_expr(raw, params, def_id=did)

    def ref(obj_id: str) -> Any:
        return _resolve(sym, obj_id, def_id=did)

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
            obj1, obj2 = ref(obj1_id), ref(obj2_id)
            raw = obj1.intersection(obj2)
            # SymPy may return the geometry object itself (not a list) when objects
            # are identical (e.g. two equal circles → Circle, not []).
            candidates = raw if isinstance(raw, list) else []
            points = [c for c in candidates if isinstance(c, spg.Point)]
            if not points:
                raise IntersectionError(did, f"no intersection points between {obj1_id!r} and {obj2_id!r}")
            return _apply_pick(points, pick, sym, did, canvas=canvas)

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
            # For tangents, PickIndex is the natural pick; convert to point pick via index
            match pick:
                case ir.PickIndex(k=k):
                    if k >= len(tangents):
                        raise PickError(did, f"index {k} out of range for {len(tangents)} tangent lines")
                    return tangents[k]
                case _:
                    # For other pick rules, pick based on which tangent's foot is closest etc.
                    # Default to first tangent for now; more sophisticated dispatch can be added.
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


def _resolve(sym: SymTable, ref_id: str, *, def_id: str) -> Any:
    """Look up ref_id in sym, raising UndefinedRefError if missing."""
    try:
        return sym[ref_id]
    except KeyError:
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
                raise PickError(def_id, f"no candidate lies between {a_id!r} and {b_id!r}")
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
            upper = [p for p in points if float(_cross_sign(a_pt, b_pt, p).evalf()) > 0]
            if not upper:
                raise PickError(def_id, f"no candidate above directed line {a_id!r}→{b_id!r}")
            return upper[0]

        case ir.PickLowerOfLine(a=a_id, b=b_id):
            a_pt = _resolve(sym, a_id, def_id=def_id)
            b_pt = _resolve(sym, b_id, def_id=def_id)
            lower = [p for p in points if float(_cross_sign(a_pt, b_pt, p).evalf()) < 0]
            if not lower:
                raise PickError(def_id, f"no candidate below directed line {a_id!r}→{b_id!r}")
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
    if isinstance(obj, spg.Circle):
        return rng.uniform(0, 2 * math.pi)
    # Segment, Ray, Line: [0, 1) for segment; [0, 1) maps intuitively
    return rng.random()


def _eval_param(obj: Any, t: float, def_id: str) -> spg.Point:
    """Evaluate the parametric point on obj at parameter t."""
    if isinstance(obj, spg.Segment):
        a, b = obj.p1, obj.p2
        return spg.Point(a.x + sp.S(t) * (b.x - a.x), a.y + sp.S(t) * (b.y - a.y))
    if isinstance(obj, spg.Circle):
        cx, cy, r = obj.center.x, obj.center.y, obj.radius
        return spg.Point(cx + r * sp.cos(sp.S(t)), cy + r * sp.sin(sp.S(t)))
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
