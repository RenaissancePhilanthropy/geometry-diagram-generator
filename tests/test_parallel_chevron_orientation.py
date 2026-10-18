"""Parallel chevrons in one group all point the same way, whatever endpoint
order each segment was authored with."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from geometry_diagrams.ir.ir import Canvas, DiagramIR, MarkSegments, PointFixed, Segment
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_svg import ir_to_svg
from geometry_diagrams.ir.to_tikz import ir_to_tikz


def _diagram(second: tuple[str, str], group: str = "parallel_1", ticks=None) -> DiagramIR:
    # AB points +x at y=0; CD lies along +x at y=2 (C left, D right).
    return DiagramIR(
        canvas=Canvas(xmin=-1, xmax=5, ymin=-1, ymax=3),
        define=[
            PointFixed(id="A", x=0, y=0), PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=0, y=2), PointFixed(id="D", x=4, y=2),
            Segment(id="AB", a="A", b="B"),
            Segment(id="CD", a=second[0], b=second[1]),
        ],
        render=[MarkSegments(segs=["AB", "CD"], group=group, ticks=ticks)],
    )


def _chevron_dx(svg: str, seg: str) -> float:
    """Tip x minus wing x of the first chevron arm: >0 means it points +x."""
    lines = [
        el for el in ET.fromstring(svg).iter()
        if el.get("data-segment") == seg and el.get("data-role") == "mark-segment"
    ]
    arm = lines[0]
    return float(arm.get("x2")) - float(arm.get("x1"))


def _svg(d: DiagramIR) -> str:
    return ir_to_svg(d, compile_defs(d))


def test_svg_opposite_authored_order_is_flipped_to_match():
    svg = _svg(_diagram(("D", "C")))
    assert _chevron_dx(svg, "AB") > 0
    assert _chevron_dx(svg, "CD") > 0


def test_svg_same_authored_order_is_unchanged():
    svg = _svg(_diagram(("C", "D")))
    assert _chevron_dx(svg, "AB") > 0
    assert _chevron_dx(svg, "CD") > 0


def test_svg_first_segment_sets_the_direction():
    d = _diagram(("C", "D"))
    d.define[4] = Segment(id="AB", a="B", b="A")  # first segment points -x
    svg = _svg(d)
    assert _chevron_dx(svg, "AB") < 0
    assert _chevron_dx(svg, "CD") < 0


def _tikz_tip_dx(tikz: str) -> list[float]:
    """For each chevron stroke `\\draw (wing) -- (tip);`, tip x minus wing x."""
    import re
    return [
        float(x2) - float(x1)
        for x1, _y1, x2, _y2 in re.findall(
            r"\\draw\s*\(([-\d.]+),([-\d.]+)\) -- \(([-\d.]+),([-\d.]+)\);", tikz
        )
    ]


def test_tikz_chevrons_all_point_the_same_way_when_authored_opposite():
    d = _diagram(("D", "C"))
    dxs = _tikz_tip_dx(ir_to_tikz(d, compile_defs(d)))
    assert len(dxs) == 4   # two segments x one chevron x two strokes
    assert all(dx > 0 for dx in dxs)


def test_tikz_chevrons_unchanged_when_authored_the_same_way():
    d = _diagram(("C", "D"))
    assert all(dx > 0 for dx in _tikz_tip_dx(ir_to_tikz(d, compile_defs(d))))


def test_tikz_first_segment_sets_the_direction():
    d = _diagram(("C", "D"))
    d.define[4] = Segment(id="AB", a="B", b="A")
    assert all(dx < 0 for dx in _tikz_tip_dx(ir_to_tikz(d, compile_defs(d))))


def test_equal_length_ticks_are_never_reoriented():
    d = _diagram(("D", "C"), group="1")
    tikz = ir_to_tikz(d, compile_defs(d))
    assert "(D,C)" in tikz
