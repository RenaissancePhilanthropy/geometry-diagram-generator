"""Slanted prism dimension-edge labels: the label box touches the edge's line
at the edge midpoint (the box slides along the edge), SVG renderer.

Pure rule tests live in tests/test_render_util.py (``away_label_center``);
these render prisms and measure the result from the SVG."""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.label_bounds import find_out_of_bounds_labels
from geometry_diagrams.ir.render_util import (
    AWAY_SLIDE_MAX_NORMAL_X,
    AWAY_SLIDE_MIN_NORMAL_X,
    away_normal,
)
from geometry_diagrams.ir.to_svg import _AWAY_LABEL_GAP, ir_to_svg
from geometry_diagrams.ir.to_sympy import compile_defs
from tests.test_prism_label_fields import EXPECTED_EDGE, VIEWS
from tests.test_prism_shading_labels import (
    _bbox,
    _box_corners,
    _corners_px,
    _side,
    _solid_render,
    _tint_styles,
)

LABELS = {"length_label": "L", "width_label": "W", "height_label": "H"}
DIMS = {"a": (3, 11, 6), "tall": (2, 2, 8), "cube": (2, 4, 5)}  # length, width, height

# Label boxes recorded (measured-font text widths) for edges the slide rule must leave
# alone: oblique views' near-horizontal length edge and vertical height edge.
UNCHANGED_BOXES = {
    "oblique/left/a/H": "333.76,320.86,344.41,334.86",
    "oblique/left/a/L": "263.60,453.87,272.00,467.87",
    "oblique/left/cube/H": "267.79,283.59,278.44,297.59",
    "oblique/left/cube/L": "200.29,439.98,208.69,453.98",
    "oblique/left/tall/H": "182.42,258.78,193.07,272.78",
    "oblique/left/tall/L": "127.69,450.20,136.09,464.20",
    "oblique/right/a/H": "35.48,320.86,46.13,334.86",
    "oblique/right/a/L": "107.89,453.87,116.29,467.87",
    "oblique/right/cube/H": "49.36,283.59,60.02,297.59",
    "oblique/right/cube/L": "119.12,439.98,127.52,453.98",
    "oblique/right/tall/H": "39.15,258.78,49.80,272.78",
    "oblique/right/tall/L": "96.13,450.20,104.53,464.20",
}


def _render(view, side, dims, mode):
    length, width, height = DIMS[dims]
    prism = ir.RectangularPrism(
        id="P", origin="O", length=length, width=width, height=height,
        view=view, side=side, **LABELS,
    )
    kw = {}
    render = [ir.Draw(obj="P")]
    if mode == "solid":
        render, kw = _solid_render(side), {"styles": _tint_styles()}
    d = ir.DiagramIR(define=[ir.PointFixed(id="O", x=0, y=0), prism], render=render, **kw)
    svg = ir_to_svg(d, compile_defs(d), warnings=[])
    return svg, ET.fromstring(svg)


def _label(root, text):
    (el,) = [e for e in root.iter() if e.get("data-label-text") == text and e.get("data-bbox")]
    return _bbox(el)


def _center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def _field_edges(side):
    return {
        LABELS[f]: edge for f, edge in EXPECTED_EDGE[side].items()
    }


def _slanted_cases():
    for view, side in VIEWS:
        for dims in DIMS:
            yield view, side, dims


@pytest.mark.parametrize("view,side,dims", list(_slanted_cases()))
def test_slanted_edge_label_corner_touches_the_edge_at_its_midpoint(view, side, dims):
    svg, root = _render(view, side, dims, "wireframe")
    corners = _corners_px(root, side)
    seen_slanted = set()
    for text, (p, q) in _field_edges(side).items():
        a, b = corners[p], corners[q]
        box = _label(root, text)
        w, h = box[2] - box[0], box[3] - box[1]
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        inside_pt = next(
            c for r, c in corners.items() if r not in (p, q) and abs(_side(c, a, b)) > 1e-6
        )
        n = away_normal(a, b, inside_pt)
        assert n is not None
        slanted = AWAY_SLIDE_MIN_NORMAL_X < abs(n[0]) < AWAY_SLIDE_MAX_NORMAL_X
        if not slanted:
            continue
        seen_slanted.add(text)
        cx, cy = _center(box)
        corner = (cx - math.copysign(1, n[0]) * w / 2, cy - math.copysign(1, n[1]) * h / 2)
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        ex, ey = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        along = (corner[0] - mx) * ex + (corner[1] - my) * ey
        perp = (corner[0] - mx) * n[0] + (corner[1] - my) * n[1]
        assert abs(along) < 1.0, (text, along)
        assert perp == pytest.approx(_AWAY_LABEL_GAP, abs=1.0), (text, perp)
        # whole box outside the silhouette on the outward side
        for c in _box_corners(box):
            assert (c[0] - mx) * n[0] + (c[1] - my) * n[1] > 0
    # the depth edge is slanted in every view; the length edge in isometric views
    assert "W" in seen_slanted
    assert ("L" in seen_slanted) == (view == "isometric")
    assert "H" not in seen_slanted
    assert find_out_of_bounds_labels(svg) == []


@pytest.mark.parametrize("key,expected", sorted(UNCHANGED_BOXES.items()))
def test_near_horizontal_and_vertical_labels_keep_their_recorded_position(key, expected):
    view, side, dims, text = key.split("/")
    _, root = _render(view, side, dims, "wireframe")
    got = _label(root, text)
    want = tuple(float(v) for v in expected.split(","))
    assert got == pytest.approx(want, abs=0.006)


def _drawn_segments(corners):
    bits = sorted(corners)
    return [
        (corners[p], corners[q])
        for i, p in enumerate(bits) for q in bits[i + 1:]
        if sum(x != y for x, y in zip(p, q)) == 1
    ]


def _segment_hits_box(a, b, box, step=0.25):
    x0, y0, x1, y1 = box
    n = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) / step))
    for i in range(n + 1):
        t = i / n
        x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        if x0 <= x <= x1 and y0 <= y <= y1:
            return True
    return False


def _overlap(b1, b2):
    return b1[0] < b2[2] and b2[0] < b1[2] and b1[1] < b2[3] and b2[1] < b1[3]


@pytest.mark.parametrize("mode", ["wireframe", "solid"])
@pytest.mark.parametrize("view,side,dims", list(_slanted_cases()))
def test_no_label_overlaps_another_label_or_a_drawn_edge(view, side, dims, mode):
    svg, root = _render(view, side, dims, mode)
    corners = _corners_px(root, side)
    boxes = {t: _label(root, t) for t in LABELS.values()}
    texts = sorted(boxes)
    for i, t1 in enumerate(texts):
        for t2 in texts[i + 1:]:
            assert not _overlap(boxes[t1], boxes[t2]), (t1, t2)
    for t, box in boxes.items():
        for a, b in _drawn_segments(corners):
            assert not _segment_hits_box(a, b, box), (t, a, b)
    assert find_out_of_bounds_labels(svg) == []
