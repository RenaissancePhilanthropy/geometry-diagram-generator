"""Canvas bounds follow what is drawn: an arc's swept extent, and only drawn circles."""
from __future__ import annotations

import pytest

from geometry_diagrams.ir.ir import (
    ArcCenterStartEnd, CircleCenterRadius, DiagramIR, Draw, PointFixed, Segment,
)
from geometry_diagrams.ir.render_util import compute_bounds, drawn_object_ids
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.render_util import extract_coords as _coords, synthesize_helpers


def _bounds(d: DiagramIR):
    sym = compile_defs(d)
    coords = _coords(sym)
    return compute_bounds(coords, synthesize_helpers(d, sym, coords), sym, drawn_object_ids(d))


def _short_arc(draw: bool):
    # radius 10 about the origin, 0..40 degrees
    return DiagramIR(
        define=[
            PointFixed(id="O", x=0, y=0), PointFixed(id="S", x=10, y=0),
            PointFixed(id="E", x=10 * 0.7660444431, y=10 * 0.6427876097),
            ArcCenterStartEnd(id="arc", center="O", start="S", end="E"),
        ],
        render=[Draw(obj="arc")] if draw else [],
    )


def test_short_arc_does_not_include_its_full_circle():
    xmin, xmax, ymin, ymax = _bounds(_short_arc(True))
    # Full circle would give xmin <= -10 and ymin <= -10.
    assert xmin > -3 and ymin > -3
    assert xmax >= 10 and ymax >= 6.4


def test_arc_includes_axis_extreme_inside_sweep():
    d = DiagramIR(
        define=[
            PointFixed(id="O", x=0, y=0), PointFixed(id="S", x=10, y=0),
            PointFixed(id="E", x=-10, y=0),
            ArcCenterStartEnd(id="arc", center="O", start="S", end="E"),
        ],
        render=[Draw(obj="arc")],
    )
    _, _, ymin, ymax = _bounds(d)
    assert ymax >= 10  # passes through 90 degrees
    assert ymin > -3   # but not 270


def test_undrawn_circle_does_not_move_bounds():
    def build(draw):
        return DiagramIR(
            define=[
                PointFixed(id="O", x=0, y=0), PointFixed(id="P", x=1, y=0),
                CircleCenterRadius(id="c", center="O", radius=10),
            ],
            render=[Draw(obj="c")] if draw else [],
        )
    xmin, xmax, _, _ = _bounds(build(False))
    assert xmax < 5
    xmin, xmax, ymin, ymax = _bounds(build(True))
    assert xmin <= -10 and xmax >= 10 and ymin <= -10 and ymax >= 10
