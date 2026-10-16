"""Advisory warning: separately drawn solids whose screen boxes overlap.

Solids are not depth-sorted against each other, so overlapping solids paint
in draw order. ``DerivedRegistry.overlap_warnings`` (fed by each kind's
``screen_bounds`` hook) warns once per overlapping pair of DRAWN solids.
"""
from __future__ import annotations

import asyncio

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.derived import REGISTRY
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.strategies.ir_pipeline import format_warnings_for_retry, run_ir_pipeline

PHRASE = "draw order is not depth order"


def _msg(a: str, b: str) -> str:
    return f"draw order is not depth order; solids '{a}' and '{b}' overlap on screen"


def _stack(sid: str, origin: str) -> ir.BlockStack:
    return ir.BlockStack(id=sid, origin=origin, heights=[[2, 1], [1, 3]])


def _prism(pid: str, origin: str) -> ir.RectangularPrism:
    return ir.RectangularPrism(id=pid, origin=origin, length=3, width=2, height=2)


def _diagram(solids: list, origins: dict[str, tuple[float, float]], draw: list[str]) -> ir.DiagramIR:
    points = [ir.PointFixed(id=k, x=x, y=y) for k, (x, y) in origins.items()]
    return ir.DiagramIR(define=[*points, *solids], render=[ir.Draw(obj=d) for d in draw])


def _overlap(diagram: ir.DiagramIR) -> list[str]:
    return REGISTRY.overlap_warnings(diagram, compile_defs(diagram))


def _run(diagram: ir.DiagramIR):
    return asyncio.run(run_ir_pipeline(diagram, SVGRenderer()))


NEAR = {"O": (0, 0), "Q": (1, 1)}
FAR = {"O": (0, 0), "Q": (30, 0)}


def test_two_stacks_overlap_warn_once():
    d = _diagram([_stack("S1", "O"), _stack("S2", "Q")], NEAR, ["S1", "S2"])
    assert _overlap(d) == [_msg("S1", "S2")]


def test_stack_and_prism_overlap():
    d = _diagram([_stack("S1", "O"), _prism("P", "Q")], NEAR, ["S1", "P"])
    assert _overlap(d) == [_msg("S1", "P")]


def test_two_prisms_overlap():
    d = _diagram([_prism("P1", "O"), _prism("P2", "Q")], NEAR, ["P1", "P2"])
    assert _overlap(d) == [_msg("P1", "P2")]


def test_three_solids_pairwise_in_authored_order():
    origins = {"O": (0, 0), "Q": (1, 0), "R": (0, 1)}
    d = _diagram([_prism("A", "O"), _stack("B", "Q"), _prism("C", "R")], origins, ["C", "A", "B"])
    assert _overlap(d) == [_msg("A", "B"), _msg("A", "C"), _msg("B", "C")]


def test_side_by_side_never_warns():
    d = _diagram([_stack("S1", "O"), _prism("P", "Q")], FAR, ["S1", "P"])
    assert _overlap(d) == []


def test_lone_solid_never_warns():
    d = _diagram([_stack("S1", "O")], {"O": (0, 0)}, ["S1"])
    assert _overlap(d) == []


def test_undrawn_solid_does_not_participate():
    d = _diagram([_stack("S1", "O"), _prism("P", "Q")], NEAR, ["S1"])
    assert _overlap(d) == []
    d = _diagram([_stack("S1", "O"), _prism("P", "Q")], NEAR, [])
    assert _overlap(d) == []


def test_touching_boxes_do_not_warn():
    # A prism's box is [ox, ox+dx_max] wide; place the second at exactly the
    # first's right edge and bottom-aligned.
    d1 = _diagram([_prism("P1", "O")], {"O": (0, 0)}, ["P1"])
    sym = compile_defs(d1)
    xmin, ymin, xmax, ymax = REGISTRY.screen_bounds(sym["P1"])
    d = _diagram([_prism("P1", "O"), _prism("P2", "Q")], {"O": (0, 0), "Q": (xmax - xmin, 0)}, ["P1", "P2"])
    assert _overlap(d) == []
    # Nudged inward by a positive amount: now they overlap.
    d = _diagram([_prism("P1", "O"), _prism("P2", "Q")], {"O": (0, 0), "Q": (xmax - xmin - 0.1, 0)}, ["P1", "P2"])
    assert _overlap(d) == [_msg("P1", "P2")]


def test_screen_bounds_matches_projected_points():
    d = _diagram([_stack("S1", "O"), _prism("P", "Q")], NEAR, ["S1", "P"])
    sym = compile_defs(d)
    prism = sym["P"]
    xs = [float(p.x) for p in prism.corners.values()]
    ys = [float(p.y) for p in prism.corners.values()]
    assert REGISTRY.screen_bounds(sym["P"]) == (min(xs), min(ys), max(xs), max(ys))
    st = sym["S1"]
    xs = [float(p.x) for p in st.lattice.values()]
    ys = [float(p.y) for p in st.lattice.values()]
    assert REGISTRY.screen_bounds(st) == (min(xs), min(ys), max(xs), max(ys))
    assert REGISTRY.screen_bounds(sym["O"]) is None


def test_warning_reaches_pipeline_result_and_retry_prompt():
    d = _diagram([_stack("S1", "O"), _prism("P", "Q")], NEAR, ["S1", "P"])
    result = _run(d)
    assert _msg("S1", "P") in result.warnings
    assert sum(PHRASE in w for w in result.warnings) == 1
    prompt = format_warnings_for_retry(result.warnings)
    assert f"- {_msg('S1', 'P')}" in prompt


def test_no_warning_without_overlap_in_pipeline():
    d = _diagram([_stack("S1", "O"), _prism("P", "Q")], FAR, ["S1", "P"])
    assert not any(PHRASE in w for w in _run(d).warnings)
