"""Unit tests for ir/constructions.py's reusable DiagramIR helpers."""
from __future__ import annotations

import pytest

from geometry_diagrams.ir.ir import (
    DiagramIR,
    PointFixed, PointOn, PointOnParam,
    CircleCenterRadius,
)
from geometry_diagrams.ir.to_sympy import compile_defs, point_on_arc
from geometry_diagrams.ir.constructions import mark_crossing_arcs


def test_mark_crossing_arcs_passes_exactly_through_point_regardless_of_radius():
    # Two circles with DIFFERENT radii and a point on one of them -- the
    # naive "shared decorative radius" approach misses the point whenever
    # radii differ; mark_crossing_arcs must not.
    defs, render_ops = mark_crossing_arcs(
        point_id="A", center_ids=["M", "N"], half_angle=0.2, id_prefix="x",
    )
    sym = compile_defs(DiagramIR(
        define=[
            PointFixed(id="M", x=0, y=0),
            PointFixed(id="N", x=10, y=3),
            CircleCenterRadius(id="cM", center="M", radius=5),
            CircleCenterRadius(id="cN", center="N", radius=8),
            PointOn(id="A", on="cM", how=PointOnParam(t=0.8)),
            *defs,
        ],
        render=render_ops,
    ))
    for arc_id in ("x_M_arc", "x_N_arc"):
        assert point_on_arc(sym["A"], sym[arc_id], tol=1e-9), f"A not on {arc_id}"


def test_mark_crossing_arcs_rejects_empty_centers():
    with pytest.raises(ValueError):
        mark_crossing_arcs(point_id="A", center_ids=[], half_angle=0.2, id_prefix="x")


def test_mark_crossing_arcs_generated_ids_are_prefixed():
    defs, render_ops = mark_crossing_arcs(
        point_id="A", center_ids=["M"], half_angle=0.2, id_prefix="tick1",
    )
    ids = {d.id for d in defs}
    assert ids == {"tick1_M_start", "tick1_M_end", "tick1_M_arc"}
    assert render_ops[0].obj == "tick1_M_arc"
