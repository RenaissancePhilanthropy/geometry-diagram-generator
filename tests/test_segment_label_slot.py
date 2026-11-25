"""A straight segment's label stays attached to it: when the default spot (the
midpoint, on the less crowded side) is cluttered, it moves to a free slot along
the segment or to its other side instead of being shoved into the clutter.

Repro from a diameter drawn through the centre with two radii and a labelled
central angle meeting at its midpoint (the label used to end up 33-50 px from
the diameter, inside the angle's wedge)."""
from __future__ import annotations

import asyncio
import math
import re

import pytest

from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.strategies.python_full import _run_from_script

HEAD = """
canvas(x_range=(-4.1, 4.1), y_range=(-3.8, 4.0))
O = point(0, 0)
circ = circle(O, 3)
A = point_on(circ, 40 * math.pi / 180)
B = point_on(circ, 140 * math.pi / 180)
D = point_on(circ, 0)
E = point_on(circ, math.pi)
diam = segment(D, E)
"""
RADII = "rad1 = segment(O, A)\nrad2 = segment(O, B)\n"
DRAW = "draw(circ, thick=True)\ndraw(diam)\ndraw(rad1)\ndraw(rad2)\n"
CENTRAL = "central = angle(A, O, B)\nmark_angle(central)\n"
SCRIPTS = {
    "radii": HEAD + RADII + 'diam.label("8 cm")\n' + DRAW,
    "marked angle": HEAD + RADII + CENTRAL + 'diam.label("8 cm")\n' + DRAW,
    "angle label": HEAD + RADII + CENTRAL + 'central.label("100°")\ndiam.label("8 cm")\n' + DRAW,
    "angle label after": HEAD + RADII + CENTRAL + 'diam.label("8 cm")\ncentral.label("100°")\n' + DRAW,
}
BBOX = r'<text[^>]*data-role="label-segment" data-for="([^"]+)" data-bbox="([\d.,-]+)"'
SEG = r'<line data-ir-id="([^"]+)" data-type="segment"[^>]*? x1="([\d.-]+)" y1="([\d.-]+)" x2="([\d.-]+)" y2="([\d.-]+)"'


def _render(script: str) -> str:
    return asyncio.run(_run_from_script(script, SVGRenderer(embed_fonts=False))).svg


def _label_gap(svg: str, seg_id: str) -> float:
    """Distance from the segment's line to the centre of its label box."""
    segs = {m.group(1): tuple(map(float, m.groups()[1:])) for m in re.finditer(SEG, svg)}
    (m,) = [m for m in re.finditer(BBOX, svg) if m.group(1) == seg_id]
    x0, y0, x1, y1 = map(float, m.group(2).split(","))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    sx1, sy1, sx2, sy2 = segs[seg_id]
    length = math.hypot(sx2 - sx1, sy2 - sy1)
    return abs((sy2 - sy1) * cx - (sx2 - sx1) * cy + sx2 * sy1 - sy2 * sx1) / length


@pytest.mark.parametrize("name", list(SCRIPTS))
def test_diameter_label_stays_within_20px_of_the_diameter(name):
    svg = _render(SCRIPTS[name])
    seg_ids = {m.group(1) for m in re.finditer(BBOX, svg)}
    assert len(seg_ids) == 1
    assert _label_gap(svg, seg_ids.pop()) <= 20


def test_diameter_label_does_not_overlap_the_angle_label_or_radii():
    svg = _render(SCRIPTS["angle label"])
    boxes = {
        m.group(1): tuple(map(float, m.group(2).split(",")))
        for m in re.finditer(r'<text[^>]*data-role="(label-[a-z-]+)" [^>]*data-bbox="([\d.,-]+)"', svg)
    }
    assert "label-segment" in boxes and "label-angle" in boxes
    a, b = boxes["label-segment"], boxes["label-angle"]
    assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


@pytest.mark.parametrize("name", list(SCRIPTS))
def test_diameter_label_never_reaches_a_radius_midpoint(name):
    """On a diameter, 0.25 and 0.75 are where a radius's label would sit: a slid label stays
    between 0.3 and 0.7, and as near the middle as the clutter allows."""
    svg = _render(SCRIPTS[name])
    segs = {m.group(1): tuple(map(float, m.groups()[1:])) for m in re.finditer(SEG, svg)}
    (m,) = [m for m in re.finditer(BBOX, svg) if m.group(1) in segs and
            (segs[m.group(1)][2] - segs[m.group(1)][0]) ** 2 + (segs[m.group(1)][3] - segs[m.group(1)][1]) ** 2 > 1e4
            and abs(segs[m.group(1)][3] - segs[m.group(1)][1]) < 1e-6]
    x0, y0, x1, y1 = map(float, m.group(2).split(","))
    ax, _, bx, _ = segs[m.group(1)]
    t = (((x0 + x1) / 2) - ax) / (bx - ax)
    assert 0.3 <= t <= 0.7
    assert abs(t - 0.5) <= 0.14
