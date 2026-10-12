"""Canvas.aspect: draw the axes with different visual unit lengths (SVG renderer)."""
from __future__ import annotations

import math
import re

import pytest
from pydantic import ValidationError

from geometry_diagrams.ir.ir import (
    AnglePoints, ArcCenterStartEnd, Canvas, CircleCenterRadius, DiagramIR, Draw, DrawPoints,
    EllipseCenterAxes, LabelAngle, LabelPoint, MarkAngles, MarkRightAngles, PointFixed, Segment,
)
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz


def _svg(d):
    return SVGRenderer().render(d, compile_defs(d)).output


def _plane(aspect=None, **extra):
    """The consumer's coordinate plane: x 0..39.71, y 0..449.92, ticks 5 / 50."""
    return DiagramIR(
        canvas=Canvas(
            xmin=0, xmax=39.71, ymin=0, ymax=449.92, axes=True, show_ticks=True, show_tick_labels=True,
            x_tick_step=5, y_tick_step=50, aspect=aspect, **extra,
        ),
        define=[
            PointFixed(id="A", x=10, y=200), PointFixed(id="B", x=25, y=300), PointFixed(id="C", x=25, y=200),
            Segment(id="AB", a="A", b="B"), Segment(id="BC", a="B", b="C"), Segment(id="CA", a="C", b="A"),
        ],
        render=[Draw(obj="AB"), Draw(obj="BC"), Draw(obj="CA"), DrawPoints(points=["A", "B", "C"]),
                LabelPoint(p="A", text="A"), LabelPoint(p="B", text="B"), LabelPoint(p="C", text="C")],
    )


def _viewbox(svg):
    return tuple(float(v) for v in re.search(r'viewBox="([\d. -]+)"', svg).group(1).split())


def _tick_positions(svg):
    """Pixel positions of x-axis ticks (vertical strokes) and y-axis ticks (horizontal strokes)."""
    ticks = re.findall(r'<line x1="([\d.-]+)" y1="([\d.-]+)" x2="([\d.-]+)" y2="([\d.-]+)" stroke="black" stroke-width="1"', svg)
    xs = sorted({float(x1) for x1, y1, x2, y2 in ticks if x1 == x2})
    ys = sorted({float(y1) for x1, y1, x2, y2 in ticks if y1 == y2})
    return xs, ys


# --- schema ----------------------------------------------------------------

def test_aspect_defaults_to_none_and_must_be_positive_and_finite():
    assert Canvas().aspect is None
    for bad in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValidationError):
            Canvas(aspect=bad)


def test_aspect_rejects_an_absurd_drawn_box_ratio_but_not_a_small_aspect():
    Canvas(xmin=0, xmax=40, ymin=0, ymax=100000, aspect=0.001)  # drawn box 100 x 40: fine
    with pytest.raises(ValidationError):
        Canvas(xmin=0, xmax=40, ymin=0, ymax=450, aspect=0.001)   # drawn box 0.45 x 40: far too flat


# --- invariants -------------------------------------------------------------

def test_aspect_none_and_one_render_identically():
    assert _svg(_plane(aspect=None)) == _svg(_plane(aspect=1.0))


def test_aspect_scales_the_drawn_plane():
    svg = _svg(_plane(aspect=0.1))
    _, _, w, h = _viewbox(svg)
    assert w / h == pytest.approx(39.71 / 44.992, rel=0.15)   # ~0.88, was ~0.09 at one uniform scale
    flat = _viewbox(_svg(_plane()))
    assert flat[2] / flat[3] < 0.2


def test_tick_spacing_follows_each_axis_scale():
    xs, ys = _tick_positions(_svg(_plane(aspect=0.1)))
    x_spacing = xs[1] - xs[0]
    y_spacing = ys[1] - ys[0]
    assert y_spacing / x_spacing == pytest.approx(1.0, rel=0.02)   # 50*0.1 == 5


def test_labels_and_tick_marks_stay_pixel_sized():
    def tick_len(svg):
        _, ys = _tick_positions(svg)
        ticks = re.findall(r'<line x1="([\d.-]+)" y1="[\d.-]+" x2="([\d.-]+)" y2="[\d.-]+" stroke="black" stroke-width="1"', svg)
        return max(float(x2) - float(x1) for x1, x2 in ticks)
    assert tick_len(_svg(_plane(aspect=0.1))) == pytest.approx(tick_len(_svg(_plane())), rel=1e-6)
    assert 'font-size="14"' in _svg(_plane(aspect=0.1))


def test_tikz_rejects_aspect():
    d = _plane(aspect=0.1)
    with pytest.raises(ValueError, match="aspect"):
        ir_to_tikz(d, compile_defs(d))


# --- circles, arcs, ellipses under a stretch ---------------------------------

def _shapes(aspect):
    return DiagramIR(
        canvas=Canvas(xmin=0, xmax=40, ymin=0, ymax=400, aspect=aspect),
        define=[
            PointFixed(id="O", x=20, y=200), PointFixed(id="S", x=30, y=200), PointFixed(id="E", x=20, y=210),
            CircleCenterRadius(id="c", center="O", radius=10),
            ArcCenterStartEnd(id="arc", center="O", start="S", end="E"),
            EllipseCenterAxes(id="el", center="O", hradius=6, vradius=3),
        ],
        render=[Draw(obj="c"), Draw(obj="arc"), Draw(obj="el")],
    )


def test_circle_becomes_an_ellipse_with_the_aspect_ratio():
    svg = _svg(_shapes(0.1))
    m = re.search(r'<ellipse[^>]*data-type="circle"[^>]* rx="([\d.]+)" ry="([\d.]+)"', svg) or \
        re.search(r'<ellipse[^>]*data-ir-id="c"[^>]* rx="([\d.]+)" ry="([\d.]+)"', svg)
    assert m is not None, svg
    assert float(m.group(2)) / float(m.group(1)) == pytest.approx(0.1, rel=1e-2)


def test_circle_stays_a_circle_when_aspect_is_none_or_one():
    for a in (None, 1.0):
        assert '<circle' in _svg(_shapes(a))


def test_arc_and_ellipse_radii_follow_each_axis_scale():
    svg = _svg(_shapes(0.1))
    rx, ry = (float(v) for v in re.search(r'data-ir-id="arc"[^>]* d="[^"]*A ([\d.]+) ([\d.]+) 0', svg).groups())
    assert ry / rx == pytest.approx(0.1, rel=1e-2)
    erx, ery = (float(v) for v in re.search(r'data-ir-id="el"[^>]* rx="([\d.]+)" ry="([\d.]+)"', svg).groups())
    assert (ery / erx) == pytest.approx(0.1 * 3 / 6, rel=1e-2)


# --- angle marks and labels ---------------------------------------------------

def _angle(aspect):
    return DiagramIR(
        canvas=Canvas(xmin=0, xmax=40, ymin=0, ymax=40 / aspect, aspect=aspect) if aspect else Canvas(xmin=0, xmax=40, ymin=0, ymax=40),
        define=[PointFixed(id="O", x=5, y=5 / (aspect or 1)), PointFixed(id="P", x=35, y=5 / (aspect or 1)),
                PointFixed(id="Q", x=35, y=35 / (aspect or 1)),
                Segment(id="OP", a="O", b="P"), Segment(id="OQ", a="O", b="Q")],
        render=[Draw(obj="OP"), Draw(obj="OQ"), MarkAngles(angles=[AnglePoints(a="P", o="O", b="Q")]),
                LabelAngle(angle=AnglePoints(a="P", o="O", b="Q"), text="45°")],
    )


def test_angle_label_sits_on_the_pixel_bisector_under_a_stretch():
    # Construction rays are O->(35,5/a) and O->(35,35/a): a 45 degree pixel angle at any aspect.
    svg = _svg(_angle(0.1))
    ox, oy = (float(v) for v in re.search(r'data-endpoints="O,P" x1="([\d.]+)" y1="([\d.]+)"', svg).groups())
    lx, ly = (float(v) for v in re.search(r'data-role="label-angle"[^>]* x="([\d.]+)" y="([\d.]+)"', svg).groups())
    off = math.degrees(math.atan2(-(ly - oy), lx - ox))
    assert off == pytest.approx(22.5, abs=6.0)


def test_right_angle_mark_is_a_parallelogram_along_the_pixel_rays():
    d = DiagramIR(
        canvas=Canvas(xmin=-60, xmax=60, ymin=-10, ymax=100, aspect=0.8),
        define=[PointFixed(id="O", x=0, y=10), PointFixed(id="P", x=20, y=60), PointFixed(id="Q", x=-50, y=30),
                Segment(id="OP", a="O", b="P"), Segment(id="OQ", a="O", b="Q")],
        render=[Draw(obj="OP"), Draw(obj="OQ"), MarkRightAngles(angles=[AnglePoints(a="P", o="O", b="Q")])],
    )
    svg = _svg(d)
    ox, oy, px, py = (float(v) for v in re.search(r'data-endpoints="O,P" x1="([\d.]+)" y1="([\d.]+)" x2="([\d.]+)" y2="([\d.]+)"', svg).groups())
    qx, qy = (float(v) for v in re.search(r'data-endpoints="O,Q" x1="[\d.]+" y1="[\d.]+" x2="([\d.]+)" y2="([\d.]+)"', svg).groups())
    pts = [tuple(float(v) for v in m) for m in re.findall(r'([\d.]+) ([\d.]+)', re.search(r'mark-right-angle"[^>]* d="([^"]+)"', svg).group(1))]
    unit_p = ((px - ox) / math.hypot(px - ox, py - oy), (py - oy) / math.hypot(px - ox, py - oy))
    unit_q = ((qx - ox) / math.hypot(qx - ox, qy - oy), (qy - oy) / math.hypot(qx - ox, qy - oy))
    size = math.hypot(pts[0][0] - ox, pts[0][1] - oy)
    assert pts[0] == pytest.approx((ox + size * unit_p[0], oy + size * unit_p[1]), abs=0.02)
    assert pts[2] == pytest.approx((ox + size * unit_q[0], oy + size * unit_q[1]), abs=0.02)
    assert pts[1] == pytest.approx((pts[0][0] + pts[2][0] - ox, pts[0][1] + pts[2][1] - oy), abs=0.02)
