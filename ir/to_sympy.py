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
            return _point_on_object(obj, how, rng, did)

        case ir.PointMidpoint(p=p_id, q=q_id):
            return spg.Segment(ref(p_id), ref(q_id)).midpoint

        case ir.PointRotate(center=center_id, source=source_id, angle=angle):
            return ref(source_id).rotate(ev(angle), ref(center_id))

        case ir.PointTriangleCenter(tri=tri_id, which=which):
            tri = ref(tri_id)
            return getattr(tri, which)

        case ir.PointIntersection(obj1=obj1_id, obj2=obj2_id, pick=pick):
            obj1, obj2 = ref(obj1_id), ref(obj2_id)
            candidates = obj1.intersection(obj2)
            points = [c for c in candidates if isinstance(c, spg.Point)]
            if not points:
                raise IntersectionError(did, f"no intersection points between {obj1_id!r} and {obj2_id!r}")
            return _apply_pick(points, pick, sym, did)

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
) -> sp.Basic:
    """Evaluate a numeric or string expression to a SymPy value."""
    if isinstance(raw, (int, float)):
        return sp.S(raw)
    try:
        return sp.sympify(raw, locals={"pi": sp.pi, "sqrt": sp.sqrt, "E": sp.E, **params})
    except Exception as exc:
        raise ExprEvalError(def_id, f"could not evaluate {raw!r}: {exc}") from exc


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
) -> spg.Point2D:
    """Select one point from candidates using the pick rule."""
    if pick is None:
        if len(points) == 1:
            return points[0]
        raise PickError(def_id, f"ambiguous: {len(points)} intersection candidates, no pick rule")

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

        case _:
            raise PickError(def_id, f"unhandled pick kind: {pick.kind!r}")


def _point_on_object(
    obj: Any,
    how: ir.PointOnHow,
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
