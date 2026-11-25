"""``LabelSegment.pos`` places a straight segment's label that fraction of the way from the
first endpoint to the second (0-1, like tkz's ``pos=``); it was only honoured for arcs and
sectors in SVG. ``None`` keeps the midpoint."""
from __future__ import annotations

import re

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.to_svg import ir_to_svg
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz

BBOX = re.compile(r'data-role="label-segment"[^>]*data-bbox="([\d.,-]+)"')
LINE = re.compile(r'<line data-ir-id="s" data-type="segment"[^>]*? x1="([\d.-]+)" y1="([\d.-]+)" x2="([\d.-]+)" y2="([\d.-]+)"')


def _diagram(pos, *, extra_defs=(), extra_render=(), kind="segment") -> ir.DiagramIR:
    side = {"segment": lambda: ir.Segment(id="s", a="A", b="B"), "ray": lambda: ir.Ray(id="s", a="A", b="B"),
            "line": lambda: ir.LineThrough(id="s", p="A", q="B")}[kind]()
    return ir.DiagramIR(
        canvas=ir.Canvas(xmin=-1, xmax=11, ymin=-4, ymax=4),
        define=[ir.PointFixed(id="A", x=0.0, y=0.0), ir.PointFixed(id="B", x=10.0, y=0.0), side, *extra_defs],
        render=[ir.Draw(obj="s"), ir.LabelSegment(seg="s", text="x", pos=pos), *extra_render],
    )


def _svg(d, warnings=None) -> str:
    return ir_to_svg(d, compile_defs(d), warnings=warnings)


def _fraction(svg: str) -> float:
    """Where along the drawn segment the label box's centre projects, 0 = first endpoint."""
    x0, _, x1, _ = map(float, BBOX.search(svg).group(1).split(","))
    ax, _, bx, _ = map(float, LINE.search(svg).groups())
    return ((x0 + x1) / 2 - ax) / (bx - ax)


def test_no_pos_keeps_the_midpoint():
    assert _fraction(_svg(_diagram(None))) == pytest.approx(0.5, abs=1e-3)
    assert _svg(_diagram(None)) == _svg(_diagram(0.5))  # an explicit 0.5 is the same figure


@pytest.mark.parametrize("pos", [0.0, 0.25, 0.75, 1.0])
def test_pos_places_the_label_that_fraction_along_the_segment(pos):
    assert _fraction(_svg(_diagram(pos))) == pytest.approx(pos, abs=1e-3)


def _center_x(svg: str) -> float:
    x0, _, x1, _ = map(float, BBOX.search(svg).group(1).split(","))
    return (x0 + x1) / 2


@pytest.mark.parametrize("kind", ["ray", "line"])
def test_pos_applies_to_a_ray_and_a_line_through_two_points(kind):
    """Measured from the two defining points (the drawn ray/line runs on past them), so the
    label sits where the segment A-B's label does."""
    assert _center_x(_svg(_diagram(0.25, kind=kind))) == pytest.approx(
        _center_x(_svg(_diagram(0.25, kind="segment"))), abs=0.5)
    assert _center_x(_svg(_diagram(0.25, kind=kind))) != pytest.approx(
        _center_x(_svg(_diagram(0.75, kind=kind))), abs=1.0)


def test_pos_runs_from_the_first_endpoint_to_the_second():
    d = ir.DiagramIR(
        canvas=ir.Canvas(xmin=-1, xmax=11, ymin=-4, ymax=4),
        define=[ir.PointFixed(id="A", x=0.0, y=0.0), ir.PointFixed(id="B", x=10.0, y=0.0), ir.Segment(id="s", a="B", b="A")],
        render=[ir.Draw(obj="s"), ir.LabelSegment(seg="s", text="x", pos=0.25)],
    )
    svg = _svg(d)
    x0, _, x1, _ = map(float, BBOX.search(svg).group(1).split(","))
    ax, _, bx, _ = map(float, LINE.search(svg).groups())
    assert ((x0 + x1) / 2 - ax) / (bx - ax) == pytest.approx(0.25, abs=1e-3)  # a quarter of the way from B


def test_an_out_of_range_pos_is_clamped_with_a_warning():
    warnings: list[str] = []
    svg = _svg(_diagram(1.5), warnings)
    assert _fraction(svg) == pytest.approx(1.0, abs=1e-3)
    assert any("pos=1.5" in w and "outside 0-1" in w for w in warnings)
    in_range: list[str] = []
    _svg(_diagram(0.4), in_range)
    assert not any("outside" in w for w in in_range)


def test_an_obstructed_pos_may_switch_sides_but_never_slides_off_its_spot():
    # a tall vertical segment crosses at x=2.5: the label asked for at 0.25 would sit on it
    cross = (ir.PointFixed(id="C", x=2.5, y=-3.0), ir.PointFixed(id="D", x=2.5, y=3.0), ir.Segment(id="t", a="C", b="D"))
    d = _diagram(0.25, extra_defs=cross, extra_render=(ir.Draw(obj="t"),))
    frac = _fraction(_svg(d))
    assert frac == pytest.approx(0.25, abs=0.06)


def test_tikz_and_svg_agree_on_what_pos_means():
    d = _diagram(0.25)
    tikz = ir_to_tikz(d, compile_defs(d))
    assert "pos=0.25" in tikz and r"\tkzLabelSegment[pos=0.25](A,B)" in tikz  # from the first point A
    assert _fraction(_svg(d)) == pytest.approx(0.25, abs=1e-3)
