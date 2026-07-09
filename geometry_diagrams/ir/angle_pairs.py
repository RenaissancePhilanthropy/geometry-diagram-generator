# geometry_diagrams/ir/angle_pairs.py
"""Post-compile resolver for mark_angle_pair annotations.

lower.py cannot compute which specific rays realize a mark_angle_pair
relation (e.g. "alternate interior") because it has no SymPy access and the
vertices involved are often intersection points with no closed-form
coordinates until compile_defs runs. This module resolves each
PendingAnglePair against the compiled SymTable, using the same
signed-cross-product side test already used elsewhere in this codebase
(see to_sympy.py's _cross_sign, and the SameSide/OppositeSide checks).

Call this after compile_defs and before run_checks/rendering.
"""
from __future__ import annotations

import math

import sympy as sp
import sympy.geometry as spg

from .errors import IRCompileError
from .ir import DiagramIR, MarkAngles, AnglePoints
from .to_sympy import SymTable, _cross_sign


def _side(v1: spg.Point2D, v2: spg.Point2D, p: spg.Point2D) -> int:
    """Which side of line v1->v2 point p is on. Raises if p is on the line."""
    cross_val = float(_cross_sign(v1, v2, p).evalf())
    if abs(cross_val) < 1e-9:
        raise ValueError(f"point {p} is collinear with the reference line — cannot determine side")
    return 1 if cross_val > 0 else -1


def _mirror(vertex: spg.Point2D, p: spg.Point2D) -> spg.Point2D:
    """Point symmetric to p through vertex (same idiom as PointReflect in to_sympy.py)."""
    return spg.Point(2 * vertex.x - p.x, 2 * vertex.y - p.y)


def _unit_from_vertex(vertex: spg.Point2D, mirror_point: spg.Point2D) -> spg.Point2D:
    """Point at unit distance from vertex, in the direction of mirror_point.

    Only the ray DIRECTION matters for an angle mark; placing synthesized
    points at unit distance (rather than full mirror distance) keeps them
    from inflating the auto-computed TikZ canvas bounds.
    """
    dx = mirror_point.x - vertex.x
    dy = mirror_point.y - vertex.y
    length = sp.sqrt(dx ** 2 + dy ** 2)
    ux, uy = dx / length, dy / length
    return spg.Point(vertex.x + ux, vertex.y + uy)


def _angle_rad(vertex: spg.Point2D, a: spg.Point2D, b: spg.Point2D) -> float:
    """Unsigned angle at vertex between rays vertex->a and vertex->b, in radians."""
    v1x, v1y = float(a.x - vertex.x), float(a.y - vertex.y)
    v2x, v2y = float(b.x - vertex.x), float(b.y - vertex.y)
    dot = v1x * v2x + v1y * v2y
    cross = abs(v1x * v2y - v1y * v2x)
    return math.atan2(cross, dot)


def _dist(p: spg.Point2D, q: spg.Point2D) -> float:
    return float(sp.sqrt((p.x - q.x) ** 2 + (p.y - q.y) ** 2).evalf())


def resolve_angle_pairs(diagram_ir: DiagramIR, sym: SymTable) -> DiagramIR:
    """Replace every PendingAnglePair with concrete MarkAngles render ops.

    Mutates `sym` in place to register any synthesized implicit points, so
    the caller's existing `sym` reference remains valid for rendering.
    Returns a new DiagramIR (render extended, pending_angle_pairs cleared);
    returns `diagram_ir` unchanged (same object) if there's nothing to do.
    """
    if not diagram_ir.pending_angle_pairs:
        return diagram_ir

    new_render = list(diagram_ir.render)

    for i, pending in enumerate(diagram_ir.pending_angle_pairs):
        def_id = f"mark_angle_pair {pending.v1}-{pending.v2}"

        def _lookup(point_id: str) -> spg.Point2D:
            try:
                obj = sym[point_id]
            except KeyError as exc:
                raise IRCompileError(
                    def_id,
                    f"unknown point id {point_id!r} in mark_angle_pair",
                ) from exc
            if not isinstance(obj, spg.Point2D):
                raise IRCompileError(
                    def_id,
                    f"{point_id!r} is not a point ({type(obj).__name__}) — vertices "
                    f"and rays_along must name point ids, not line/segment ids",
                )
            return obj

        v1, v2 = _lookup(pending.v1), _lookup(pending.v2)
        r1, r2 = _lookup(pending.ray_ref_v1), _lookup(pending.ray_ref_v2)

        if pending.v1 == pending.v2:
            raise IRCompileError(def_id, "vertices must be two distinct points")
        if pending.ray_ref_v1 == pending.v1:
            raise IRCompileError(
                def_id,
                f"rays_along point {pending.ray_ref_v1!r} coincides with its vertex — "
                f"name a DIFFERENT point on the other line through that vertex",
            )
        if pending.ray_ref_v2 == pending.v2:
            raise IRCompileError(
                def_id,
                f"rays_along point {pending.ray_ref_v2!r} coincides with its vertex — "
                f"name a DIFFERENT point on the other line through that vertex",
            )
        if _dist(v1, v2) < 1e-9:
            raise IRCompileError(def_id, "vertices must be two distinct points")
        if _dist(r1, v1) < 1e-9:
            raise IRCompileError(
                def_id,
                f"rays_along point {pending.ray_ref_v1!r} coincides with its vertex — "
                f"name a DIFFERENT point on the other line through that vertex",
            )
        if _dist(r2, v2) < 1e-9:
            raise IRCompileError(
                def_id,
                f"rays_along point {pending.ray_ref_v2!r} coincides with its vertex — "
                f"name a DIFFERENT point on the other line through that vertex",
            )

        try:
            s1 = _side(v1, v2, r1)
        except ValueError as exc:
            raise IRCompileError(
                def_id,
                f"rays_along point {pending.ray_ref_v1!r} lies on the line through "
                f"{pending.v1!r} and {pending.v2!r} (the transversal) — it cannot pick "
                f"a side. Choose a point on the OTHER line through that vertex instead "
                f"(any point on that line works)."
            ) from exc
        try:
            s2_natural = _side(v1, v2, r2)
        except ValueError as exc:
            raise IRCompileError(
                def_id,
                f"rays_along point {pending.ray_ref_v2!r} lies on the line through "
                f"{pending.v1!r} and {pending.v2!r} (the transversal) — it cannot pick "
                f"a side. Choose a point on the OTHER line through that vertex instead "
                f"(any point on that line works)."
            ) from exc

        want_s2 = s1 if pending.relation == "corresponding" else -s1

        if s2_natural == want_s2:
            line_ray_v2_id = pending.ray_ref_v2
        else:
            line_ray_v2_id = f"__pair{i}_{pending.v2}_line"
            sym[line_ray_v2_id] = _unit_from_vertex(v2, _mirror(v2, r2))

        if pending.relation == "corresponding":
            trans_ray_v1_id = pending.v2  # toward the other vertex — always a real named point
            trans_ray_v2_id = f"__pair{i}_{pending.v2}_trans"
            sym[trans_ray_v2_id] = _unit_from_vertex(v2, _mirror(v2, v1))  # away from the other vertex
        elif pending.relation == "alternate_interior":
            trans_ray_v1_id = pending.v2
            trans_ray_v2_id = pending.v1
        else:  # alternate_exterior
            trans_ray_v1_id = f"__pair{i}_{pending.v1}_trans"
            sym[trans_ray_v1_id] = _unit_from_vertex(v1, _mirror(v1, v2))
            trans_ray_v2_id = f"__pair{i}_{pending.v2}_trans"
            sym[trans_ray_v2_id] = _unit_from_vertex(v2, _mirror(v2, v1))

        # The two lines through v1 and v2 (other than the transversal) are
        # assumed parallel by construction — verify that numerically, since a
        # wrongly-placed "parallel" line would otherwise silently get
        # equal-looking tick marks on unequal angles (the old recipes'
        # pairwise AngleEqual checks used to catch this; the DSL rewrite
        # dropped that guardrail).
        angle1 = _angle_rad(v1, sym[pending.ray_ref_v1], sym[trans_ray_v1_id])
        angle2 = _angle_rad(v2, sym[line_ray_v2_id], sym[trans_ray_v2_id])
        if abs(angle1 - angle2) > 5e-3:
            deg1, deg2 = math.degrees(angle1), math.degrees(angle2)
            raise IRCompileError(
                f"mark_angle_pair {pending.v1}-{pending.v2}",
                f"resolved angles differ: {deg1:.1f}° at {pending.v1} vs {deg2:.1f}° "
                f"at {pending.v2} — a {pending.relation} pair requires the two lines "
                f"through the vertices to be PARALLEL; check that both rays_along "
                f"points lie on lines that are actually parallel to each other",
            )

        new_render.append(MarkAngles(
            angles=[AnglePoints(a=pending.ray_ref_v1, o=pending.v1, b=trans_ray_v1_id)],
            group=pending.group,
        ))
        new_render.append(MarkAngles(
            angles=[AnglePoints(a=line_ray_v2_id, o=pending.v2, b=trans_ray_v2_id)],
            group=pending.group,
        ))

    return diagram_ir.model_copy(update={"render": new_render, "pending_angle_pairs": []})
