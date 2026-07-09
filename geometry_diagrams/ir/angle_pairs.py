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

import sympy as sp
import sympy.geometry as spg

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
        v1, v2 = sym[pending.v1], sym[pending.v2]
        r1, r2 = sym[pending.ray_ref_v1], sym[pending.ray_ref_v2]

        s1 = _side(v1, v2, r1)
        s2_natural = _side(v1, v2, r2)

        want_s2 = s1 if pending.relation == "corresponding" else -s1

        if s2_natural == want_s2:
            line_ray_v2_id = pending.ray_ref_v2
        else:
            line_ray_v2_id = f"__pair{i}_{pending.v2}_line"
            sym[line_ray_v2_id] = _mirror(v2, r2)

        if pending.relation == "corresponding":
            trans_ray_v1_id = pending.v2  # toward the other vertex — always a real named point
            trans_ray_v2_id = f"__pair{i}_{pending.v2}_trans"
            sym[trans_ray_v2_id] = _mirror(v2, v1)  # away from the other vertex
        elif pending.relation == "alternate_interior":
            trans_ray_v1_id = pending.v2
            trans_ray_v2_id = pending.v1
        else:  # alternate_exterior
            trans_ray_v1_id = f"__pair{i}_{pending.v1}_trans"
            sym[trans_ray_v1_id] = _mirror(v1, v2)
            trans_ray_v2_id = f"__pair{i}_{pending.v2}_trans"
            sym[trans_ray_v2_id] = _mirror(v2, v1)

        new_render.append(MarkAngles(
            angles=[AnglePoints(a=pending.ray_ref_v1, o=pending.v1, b=trans_ray_v1_id)],
            group=pending.group,
        ))
        new_render.append(MarkAngles(
            angles=[AnglePoints(a=line_ray_v2_id, o=pending.v2, b=trans_ray_v2_id)],
            group=pending.group,
        ))

    return diagram_ir.model_copy(update={"render": new_render, "pending_angle_pairs": []})
