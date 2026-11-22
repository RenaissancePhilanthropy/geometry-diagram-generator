"""Label-label collisions must still be resolved after the line/circle clearance pass.

Collision resolution pushes two overlapping labels apart, and the clearance pass that
follows pushes a label off a drawn line, which could walk it straight back into the label
it had just been separated from. Typical case: a diameter's length label sits where the
center point's label lands, or two labeled diameters share a center."""
from __future__ import annotations

import asyncio
import itertools
import xml.etree.ElementTree as ET

import pytest

from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.pydsl.sandbox import run_script
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline

HEAD = "canvas((-6, 6), (-6, 6))\no = point(0, 0)\nc = circle(o, 4); draw(c)\n"
HORIZ = 'a = point(-4,0); b = point(4,0); d = segment(a,b); draw(d)\n'

LAYOUTS = {
    "center label below the diameter": HEAD + HORIZ
    + 'o.label("O", pos="below"); a.label("A"); b.label("B"); d.label("14 cm")',
    "radius drawn from the center": HEAD + HORIZ
    + 'r = segment(o, point(0,4)); draw(r)\n'
      'o.label("O"); a.label("A"); b.label("B"); d.label("14 cm"); r.label("7 cm")',
    "two labeled diameters": HEAD
    + 'a = point(-4,0); b = point(4,0); p = point(0,4); q = point(0,-4)\n'
      'd1 = segment(a,b); d2 = segment(p,q); draw(d1); draw(d2)\n'
      'o.label("O"); a.label("A"); b.label("B"); p.label("C"); q.label("D"); d1.label("AB"); d2.label("CD")',
}


def _overlaps(svg: str) -> list[tuple[str, str]]:
    boxes = [
        (el.get("data-label-text"), tuple(float(v) for v in el.get("data-bbox").split(",")))
        for el in ET.fromstring(svg).iter() if el.get("data-bbox")
    ]
    found = []
    for (ta, a), (tb, b) in itertools.combinations(boxes, 2):
        if min(a[2], b[2]) - max(a[0], b[0]) > 0 and min(a[3], b[3]) - max(a[1], b[1]) > 0:
            found.append((ta, tb))
    return found


@pytest.mark.parametrize("name", LAYOUTS)
def test_no_labels_overlap(name):
    result = run_script(LAYOUTS[name], timeout_seconds=60)
    assert result.error is None, result.error
    svg = asyncio.run(run_ir_pipeline(result.diagram_ir, SVGRenderer())).svg
    assert _overlaps(svg) == []
