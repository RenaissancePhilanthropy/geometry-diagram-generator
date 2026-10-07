# geometry_diagrams/ir/constructions.py
"""Reusable DiagramIR construction helpers.

Each helper here is a pure function built entirely out of existing
DefStmt/RenderOp kinds (ir.py) -- no new IR node types. They exist so
common multi-statement patterns don't need to be hand-rolled (and
hand-tuned-by-eyeball) by every DiagramIR-assembling caller.
"""
from __future__ import annotations

from typing import Union

from . import ir


def _negate(angle: Union[int, float, str]) -> Union[int, float, str]:
    if isinstance(angle, (int, float)):
        return -angle
    return f"-({angle})"


def mark_crossing_arcs(
    point_id: str,
    center_ids: list[str],
    half_angle: Union[int, float, str],
    *,
    id_prefix: str,
) -> tuple[list[ir.DefStmt], list[ir.RenderOp]]:
    """Build defs/render-ops for a compass-construction tick mark through
    `point_id`: one small arc per id in `center_ids`, each the arc of the
    circle centered there that passes through `point_id`, spanning
    `half_angle` radians on either side of it.

    Each arc's start/end are `point_id` rotated by -+half_angle about its
    center (ir.PointRotate), so every arc passes through point_id exactly
    regardless of that center's actual distance to it -- ArcCenterStartEnd's
    radius is derived as center.distance(start), not a free parameter, so
    picking some other "decorative" radius independent of that distance is
    what produces a visible miss. Because the endpoints are derived from
    point_id rather than frozen as fixed coordinates, the arcs stay correct
    if point_id's definition changes later (e.g. a PointIntersection whose
    inputs move).

    With center_ids of length 2 this draws the classic "X" crossing through
    an intersection point; more centers draw a rosette through the same
    point.

    Returns (defs, render_ops) -- extend your own DiagramIR.define /
    DiagramIR.render lists with them. id_prefix must be unique per call
    (across all calls contributing to the same DiagramIR): generated ids
    are f"{id_prefix}_{center_id}_start" / "_end" / "_arc".
    """
    if len(center_ids) < 1:
        raise ValueError("mark_crossing_arcs(): center_ids must have at least one entry")

    defs: list[ir.DefStmt] = []
    render_ops: list[ir.RenderOp] = []
    for center_id in center_ids:
        start_id = f"{id_prefix}_{center_id}_start"
        end_id = f"{id_prefix}_{center_id}_end"
        arc_id = f"{id_prefix}_{center_id}_arc"
        defs.append(ir.PointRotate(id=start_id, center=center_id, source=point_id, angle=_negate(half_angle)))
        defs.append(ir.PointRotate(id=end_id, center=center_id, source=point_id, angle=half_angle))
        defs.append(ir.ArcCenterStartEnd(id=arc_id, center=center_id, start=start_id, end=end_id))
        render_ops.append(ir.Draw(obj=arc_id))
    return defs, render_ops
