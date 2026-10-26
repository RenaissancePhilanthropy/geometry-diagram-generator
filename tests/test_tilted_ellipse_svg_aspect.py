"""Rotated-ellipses stage 1b: a tilted ellipse in SVG under a non-unit canvas
aspect (the screen image is another, differently tilted ellipse), and label
nudging against a tilted ellipse's true screen outline.

Expectations are computed independently of ``screen_ellipse``: sampled
parametric points are mapped through the page scale by hand, and the emitted
element's own implicit equation is evaluated at them."""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.render_util import screen_ellipse
from geometry_diagrams.ir.to_svg import (
    _LabelPlacement,
    _ellipse_clearance,
    _nearest_point_on_ellipse,
    ir_to_svg,
)
from geometry_diagrams.ir.to_sympy import compile_defs

CX, CY, HR, VR = 1.0, 2.0, 3.0, 1.0
CASES = [(30.0, 2.0), (30.0, 0.5), (-50.0, 2.0), (90.0, 1.7), (135.0, 0.6), (0.5, 3.0)]


def _diagram(rotation, aspect, render, extra=()):
    return ir.DiagramIR(
        canvas=ir.Canvas(xmin=-5, xmax=7, ymin=-4, ymax=8, aspect=aspect),
        define=[
            ir.PointFixed(id="O", x=CX, y=CY),
            ir.EllipseCenterAxes(id="E", center="O", hradius=HR, vradius=VR, rotation_deg=rotation),
            *extra,
        ],
        render=render,
    )


def _root(d):
    return ET.fromstring(ir_to_svg(d, compile_defs(d)))


# Three dots at the far corners of the canvas, so the page scale recovered from
# their (2-decimal) centres is as exact as the output allows.
_SCALE_PTS = [ir.PointFixed(id="P0", x=-5, y=-4), ir.PointFixed(id="P1", x=7, y=-4), ir.PointFixed(id="P2", x=-5, y=8)]


def _scale_of(root):
    """(sx, sy, page x of construction x=0, page y of y=0) from the corner dots."""
    pts = {e.get("data-ir-id"): (float(e.get("cx")), float(e.get("cy")))
           for e in root.iter() if e.get("data-ir-id") in ("P0", "P1", "P2") and e.get("cx")}
    (x0, y0), (x1, _), (_, y2) = pts["P0"], pts["P1"], pts["P2"]
    sx, sy = (x1 - x0) / 12.0, (y0 - y2) / 12.0
    return sx, sy, x0 + 5 * sx, y0 - 4 * sy


def _world_curve_point(t, rotation_deg):
    r = math.radians(rotation_deg)
    u, v = HR * math.cos(t), VR * math.sin(t)
    return CX + u * math.cos(r) - v * math.sin(r), CY + u * math.sin(r) + v * math.cos(r)


def _outline_gap(el, px, py):
    """Distance estimate f/|grad f| of page point (px, py) from the element's
    own ellipse (cx, cy, rx, ry, rotate(phi cx cy))."""
    cx, cy, rx, ry = (float(el.get(k)) for k in ("cx", "cy", "rx", "ry"))
    m = re.match(r"rotate\(([-\d.e+]+) ", el.get("transform", "rotate(0 0 0)"))
    phi = math.radians(float(m.group(1)))
    dx, dy = px - cx, py - cy
    u = dx * math.cos(phi) + dy * math.sin(phi)
    v = -dx * math.sin(phi) + dy * math.cos(phi)
    f = (u / rx) ** 2 + (v / ry) ** 2 - 1.0
    g = math.hypot(2 * u / rx ** 2, 2 * v / ry ** 2)
    return abs(f) / g


def _page(root, wx, wy):
    sx, sy, x0, y0 = _scale_of(root)
    return x0 + sx * wx, y0 - sy * wy


@pytest.mark.parametrize("rotation,aspect", CASES)
@pytest.mark.parametrize("role", ["draw", "fill"])
def test_outline_and_fill_follow_the_curve_under_unequal_units(rotation, aspect, role):
    render = [ir.Draw(obj="E")] if role == "draw" else [ir.Fill(obj="E")]
    d = _diagram(rotation, aspect, render + [ir.DrawPoints(points=["P0", "P1", "P2"])], _SCALE_PTS)
    root = _root(d)
    (el,) = [e for e in root.iter() if e.get("data-ir-id") == "E"]
    assert el.tag.endswith("ellipse")
    for i in range(48):
        wx, wy = _world_curve_point(2 * math.pi * i / 48, rotation)
        px, py = _page(root, wx, wy)
        assert _outline_gap(el, px, py) < 0.01, (rotation, aspect, i)


@pytest.mark.parametrize("rotation,aspect", CASES)
def test_fill_with_holes_path_arcs_follow_the_curve(rotation, aspect):
    d = _diagram(rotation, aspect,
                 [ir.Fill(obj="X", holes=["E"]), ir.DrawPoints(points=["P0", "P1", "P2"])],
                 [ir.CircleCenterRadius(id="X", center="O", radius=5), *_SCALE_PTS])
    root = _root(d)
    sx, sy, x0, y0 = _scale_of(root)
    (path,) = [e for e in root.iter() if e.tag.endswith("path") and e.get("data-ir-id") == "X"]
    # the hole is the second subpath: M x y A rx ry phi 1 0 x y A rx ry phi 1 0 x y Z
    hole = path.get("d").split("Z")[1]
    nums = [float(v) for v in re.findall(r"-?\d+\.?\d*(?:e-?\d+)?", hole)]
    (mx, my, rx, ry, phi, _, _, ex, ey, rx2, ry2, phi2, _, _, bx, by) = nums
    assert (rx2, ry2, phi2) == (rx, ry, phi) and (bx, by) == (mx, my)
    el = ET.Element("ellipse", {"rx": str(rx), "ry": str(ry), "transform": f"rotate({phi} 0 0)", "cx": "0", "cy": "0"})
    # center from the independent mapping
    ccx, ccy = _page(root, CX, CY)
    el.set("cx", str(ccx)); el.set("cy", str(ccy))
    for i in range(48):
        px, py = _page(root, *_world_curve_point(2 * math.pi * i / 48, rotation))
        assert _outline_gap(el, px, py) < 0.01
    # both arc ends are antipodal about the center and lie on the curve
    assert (mx + ex) / 2 == pytest.approx(ccx, abs=0.01) and (my + ey) / 2 == pytest.approx(ccy, abs=0.01)
    assert _outline_gap(el, mx, my) < 0.01


def test_screen_ellipse_matches_hand_cases():
    # no tilt: axes scale by (sx, sy) with no angle
    rx, ry, phi = screen_ellipse(3.0, 1.0, 0.0, 10.0, 20.0)
    assert (rx, ry) == pytest.approx((30.0, 20.0)) or (rx, ry) == pytest.approx((20.0, 30.0))
    # 90 degrees on unequal scales: hradius points along y, so it spans 3*sy vertically
    big, small, phi = screen_ellipse(3.0, 1.0, math.pi / 2, 10.0, 20.0)
    assert sorted([big, small]) == pytest.approx([10.0, 60.0])


@pytest.mark.parametrize("aspect", [None, 1, 2.0])
def test_non_unit_aspect_no_longer_raises(aspect):
    d = _diagram(30.0, aspect, [ir.Draw(obj="E"), ir.Fill(obj="E")])
    _root(d)


def test_equal_units_output_is_unchanged_from_the_pre_aspect_form():
    d = _diagram(30.0, None, [ir.Draw(obj="E")])
    (el,) = [e for e in _root(d).iter() if e.get("data-ir-id") == "E"]
    assert el.get("transform").startswith("rotate(-30 ")
    assert float(el.get("rx")) / float(el.get("ry")) == pytest.approx(3.0, rel=1e-3)


# --- nudging ------------------------------------------------------------------

def _lp(x, y, w=14.0, h=14.0):
    return _LabelPlacement(x=x, y=y, text="A", color="black", anchor="middle", width_est=w, height_est=h)


def _brute_nearest(px, py, cx, cy, hr, vr, phi, n=200_000):
    c, s = math.cos(phi), math.sin(phi)
    best = None
    for i in range(n):
        t = 2 * math.pi * i / n
        u, v = hr * math.cos(t), vr * math.sin(t)
        bx, by = cx + u * c - v * s, cy + u * s + v * c
        d2 = (px - bx) ** 2 + (py - by) ** 2
        if best is None or d2 < best[0]:
            best = (d2, bx, by)
    return best[1], best[2]


@pytest.mark.parametrize("phi", [0.5, 1.2, -0.9, math.pi / 2])
@pytest.mark.parametrize("p", [(130.0, 40.0), (3.0, 1.0), (-60.0, -20.0)])
def test_nearest_point_on_a_tilted_ellipse_matches_brute_force(phi, p):
    nx, ny = _nearest_point_on_ellipse(p[0], p[1], 5.0, -2.0, 100.0, 40.0, phi=phi)
    bx, by = _brute_nearest(p[0], p[1], 5.0, -2.0, 100.0, 40.0, phi)
    assert math.hypot(nx - bx, ny - by) < 0.05


def _same_verdict(a, b):
    if a is None or b is None:
        return a is None and b is None
    return a == pytest.approx(b)


def test_quarter_turn_equals_the_swapped_axis_aligned_ellipse():
    for lx, ly in [(0.0, 60.0), (40.0, 5.0), (3.0, 52.0), (0.0, 0.0), (20.0, 20.0)]:
        lp = _lp(lx, ly)
        assert _same_verdict(
            _ellipse_clearance(lx, ly, lp, (0.0, 0.0, 100.0, 50.0, math.pi / 2)),
            _ellipse_clearance(lx, ly, lp, (0.0, 0.0, 50.0, 100.0)),
        )


def test_clearance_follows_the_tilted_outline_not_the_untilted_twin():
    twin = (0.0, 0.0, 100.0, 20.0)
    tilted = (0.0, 0.0, 100.0, 20.0, math.radians(45))
    c = s = math.sqrt(0.5)
    # a rim point of the twin (x=-50) lies far outside the 45-degree outline
    x, y = -50.0, 20.0 * math.sqrt(0.75)
    assert _ellipse_clearance(x, y, _lp(x, y), twin) is not None
    assert _ellipse_clearance(x, y, _lp(x, y), tilted) is None
    # a point on the tilted outline (u=60, v=16) is nowhere near the twin
    u, v = 60.0, 20.0 * math.sqrt(1 - 0.36)
    x, y = u * c - v * s, u * s + v * c
    assert _ellipse_clearance(x, y, _lp(x, y), twin) is None
    dx, dy, deficit = _ellipse_clearance(x, y, _lp(x, y), tilted)
    assert deficit > 0
    # pushed along the tilted outline's outward normal, which is not axis-aligned
    nx, ny = _brute_nearest(x, y, 0, 0, 100, 20, math.radians(45))
    assert math.hypot(nx - x, ny - y) < 0.05  # sanity: the point is on the curve


@pytest.mark.parametrize("aspect", [None, 2.0, 0.5])
def test_end_to_end_label_nudged_by_the_tilted_outline_only_when_it_overlaps(aspect):
    pts = [ir.PointFixed(id="Q", x=0, y=0)]
    def label_pos(rotation, qx, qy, with_ellipse=True):
        d = ir.DiagramIR(
            canvas=ir.Canvas(xmin=-6, xmax=6, ymin=-4, ymax=4, aspect=aspect),
            define=[ir.PointFixed(id="O", x=0, y=0),
                    ir.EllipseCenterAxes(id="E", center="O", hradius=4, vradius=1, rotation_deg=rotation),
                    ir.PointFixed(id="Q", x=qx, y=qy)],
            render=([ir.Draw(obj="E")] if with_ellipse else []) + [ir.LabelPoint(p="Q", text="Q")],
        )
        root = _root(d)
        (t,) = [e for e in root.iter() if e.tag.endswith("text") and e.get("data-label-text") == "Q"]
        return float(t.get("x")), float(t.get("y"))
    # Q sits on the tilted curve's end (t=0 point of the 40-degree ellipse)
    r = math.radians(40)
    qx, qy = 4 * math.cos(r), 4 * math.sin(r)
    bare = label_pos(40, qx, qy, with_ellipse=False)
    assert label_pos(40, qx, qy) != bare           # overlapped by the tilted outline: nudged
    # the same spot is clear of the tilted outline when the ellipse is tilted elsewhere
    # (Q far from it) -> not moved relative to the bare label
    assert label_pos(40, qx, 3.4) == label_pos(40, qx, 3.4, with_ellipse=False)
