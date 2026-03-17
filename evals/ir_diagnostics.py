"""
Static analysis of DiagramIR to classify failure modes.

Used in eval runs to add diagnostic metadata to result records.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import ir.ir as ir


@dataclass
class IRDiagnostics:
    """Static analysis results from a DiagramIR, describing quality signals."""

    hardcoded_count: int = 0
    """Number of point_fixed definitions (potential hardcoding of derived points)."""

    parametric_count: int = 0
    """Number of point_on(t=...) uses (fragile: LLM must guess correct parameter)."""

    missing_pick_count: int = 0
    """Number of point_intersection definitions without a pick rule."""

    primitive_count: int = 0
    """Number of high-level construction primitives used:
    point_foot, point_between, point_reflect, point_midpoint,
    point_intersection, point_triangle_center."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_ir(diagram: ir.DiagramIR) -> IRDiagnostics:
    """Analyze a DiagramIR statically to produce quality/failure-mode metrics."""
    d = IRDiagnostics()
    for stmt in diagram.define:
        match stmt:
            case ir.PointFixed():
                d.hardcoded_count += 1
            case ir.PointOn(how=ir.PointOnParam()):
                d.parametric_count += 1
            case ir.PointIntersection(pick=None):
                d.missing_pick_count += 1
            case (
                ir.PointFoot()
                | ir.PointBetween()
                | ir.PointReflect()
                | ir.PointMidpoint()
                | ir.PointTriangleCenter()
            ):
                d.primitive_count += 1
            # PointIntersection also counts as a primitive (constructive)
            case ir.PointIntersection():
                d.primitive_count += 1
    return d
