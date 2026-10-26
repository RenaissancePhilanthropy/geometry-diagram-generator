"""Rotated-ellipses stage 1b: a tilted ellipse in SVG under a non-unit canvas
aspect (the screen image is another, differently tilted ellipse), and label
nudging against a tilted ellipse's true screen outline.

Expectations are computed independently of ``screen_ellipse``: sampled
parametric points are mapped through the page scale by hand, and the emitted
element's own implicit equation is evaluated at them."""
from __future__ import annotations

import math
import random
import re
import xml.etree.ElementTree as ET

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.render_util import screen_ellipse
from geometry_diagrams.ir.to_svg import (
    _LabelPlacement,
    _ellipse_clearance,
    _nearest_point_on_ellipse,
    _CANVAS_MARGIN_PX,
    _NUDGE_MARGIN,
    _SVG_SIZE,
    ir_to_svg,
)
from geometry_diagrams.ir.to_sympy import compile_defs

CX, CY, HR, VR = 1.0, 2.0, 3.0, 1.0
CANVAS = (-5, 7, -4, 8)
CASES = [(30.0, 2.0), (30.0, 0.5), (-50.0, 2.0), (90.0, 1.7), (135.0, 0.6), (0.5, 3.0)]


def _diagram(rotation, aspect, render, extra=()):
    return ir.DiagramIR(
        canvas=ir.Canvas(xmin=CANVAS[0], xmax=CANVAS[1], ymin=CANVAS[2], ymax=CANVAS[3], aspect=aspect),
        define=[
            ir.PointFixed(id="O", x=CX, y=CY),
            ir.EllipseCenterAxes(id="E", center="O", hradius=HR, vradius=VR, rotation_deg=rotation),
            *extra,
        ],
        render=render,
    )


def _root(d):
    return ET.fromstring(ir_to_svg(d, compile_defs(d)))


def _mapper(root, canvas, aspect):
    """Construction -> page mapping from the canvas alone (the same box-fit rule as
    the renderer, written out here), checked against the SVG's own size."""
    xmin, xmax, ymin, ymax = canvas
    w, h, a = xmax - xmin, ymax - ymin, (1.0 if aspect is None else aspect)
    s = (_SVG_SIZE - 2 * _CANVAS_MARGIN_PX) / max(w, h * a)
    sx, sy = s, s * a
    svg_h = h * sy + 2 * _CANVAS_MARGIN_PX
    assert float(root.get("width")) == pytest.approx(w * sx + 2 * _CANVAS_MARGIN_PX, abs=0.01)
    assert float(root.get("height")) == pytest.approx(svg_h, abs=0.01)
    return lambda x, y: ((x - xmin) * sx + _CANVAS_MARGIN_PX, svg_h - ((y - ymin) * sy + _CANVAS_MARGIN_PX))


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


@pytest.mark.parametrize("rotation,aspect", CASES)
@pytest.mark.parametrize("role", ["draw", "fill"])
def test_outline_and_fill_follow_the_curve_under_unequal_units(rotation, aspect, role):
    render = [ir.Draw(obj="E")] if role == "draw" else [ir.Fill(obj="E")]
    d = _diagram(rotation, aspect, render)
    root = _root(d)
    page = _mapper(root, CANVAS, aspect)
    (el,) = [e for e in root.iter() if e.get("data-ir-id") == "E"]
    assert el.tag.endswith("ellipse")
    for i in range(48):
        wx, wy = _world_curve_point(2 * math.pi * i / 48, rotation)
        px, py = page(wx, wy)
        assert _outline_gap(el, px, py) < 0.01, (rotation, aspect, i)


@pytest.mark.parametrize("rotation,aspect", CASES)
def test_fill_with_holes_path_arcs_follow_the_curve(rotation, aspect):
    d = _diagram(rotation, aspect,
                 [ir.Fill(obj="X", holes=["E"])],
                 [ir.CircleCenterRadius(id="X", center="O", radius=5)])
    root = _root(d)
    page = _mapper(root, CANVAS, aspect)
    (path,) = [e for e in root.iter() if e.tag.endswith("path") and e.get("data-ir-id") == "X"]
    # the hole is the second subpath: M x y A rx ry phi 1 0 x y A rx ry phi 1 0 x y Z
    hole = path.get("d").split("Z")[1]
    nums = [float(v) for v in re.findall(r"-?\d+\.?\d*(?:e-?\d+)?", hole)]
    (mx, my, rx, ry, phi, _, _, ex, ey, rx2, ry2, phi2, _, _, bx, by) = nums
    assert (rx2, ry2, phi2) == (rx, ry, phi) and (bx, by) == (mx, my)
    el = ET.Element("ellipse", {"rx": str(rx), "ry": str(ry), "transform": f"rotate({phi} 0 0)", "cx": "0", "cy": "0"})
    # center from the independent mapping
    ccx, ccy = page(CX, CY)
    el.set("cx", str(ccx)); el.set("cy", str(ccy))
    for i in range(48):
        px, py = page(*_world_curve_point(2 * math.pi * i / 48, rotation))
        assert _outline_gap(el, px, py) < 0.01
    # both arc ends are antipodal about the center and lie on the curve
    assert (mx + ex) / 2 == pytest.approx(ccx, abs=0.01) and (my + ey) / 2 == pytest.approx(ccy, abs=0.01)
    assert _outline_gap(el, mx, my) < 0.01


def test_screen_ellipse_matches_hand_cases():
    # no tilt: M = diag(sx*hr, sy*vr) = diag(30, 20), so (rx, ry) = (30, 20) along the page x axis
    rx, ry, phi = screen_ellipse(3.0, 1.0, 0.0, 10.0, 20.0)
    assert (rx, ry) == pytest.approx((30.0, 20.0))
    assert phi % 180.0 == pytest.approx(0.0, abs=1e-9) or phi % 180.0 == pytest.approx(180.0, abs=1e-9)
    # 90 degrees on unequal scales: hradius points along construction y, so it spans 3*sy = 60
    # vertically on the page and vradius spans 1*sx = 10 across: rx = 60 on a vertical axis
    rx, ry, phi = screen_ellipse(3.0, 1.0, math.pi / 2, 10.0, 20.0)
    assert (rx, ry) == pytest.approx((60.0, 10.0))
    assert phi % 180.0 == pytest.approx(90.0, abs=1e-9)
    # equal scales, 30 degrees counterclockwise: the SVG angle (y down) is -30, i.e. 150 mod 180
    rx, ry, phi = screen_ellipse(3.0, 1.0, math.radians(30), 1.0, 1.0)
    assert (rx, ry) == pytest.approx((3.0, 1.0))
    assert phi % 180.0 == pytest.approx(150.0, abs=1e-9)


@pytest.mark.parametrize("aspect", [None, 1, 2.0])
def test_non_unit_aspect_no_longer_raises(aspect):
    d = _diagram(30.0, aspect, [ir.Draw(obj="E"), ir.Fill(obj="E")])
    _root(d)


def test_equal_units_axes_and_angle_as_before_at_finer_precision():
    d = _diagram(30.0, None, [ir.Draw(obj="E")])
    (el,) = [e for e in _root(d).iter() if e.get("data-ir-id") == "E"]
    assert el.get("transform").startswith("rotate(-30.00000 ")
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
    # Step 0.5 px outward along the tilted outline's normal (the gradient of the
    # implicit form, rotated into place): the push must follow that normal, which is
    # not axis-aligned, so its cosine with the normal is near 1.
    gu, gv = u / 100.0 ** 2, v / 20.0 ** 2
    nx, ny = gu * c - gv * s, gu * s + gv * c
    norm = math.hypot(nx, ny)
    nx, ny = nx / norm, ny / norm
    px, py = x + 0.5 * nx, y + 0.5 * ny
    dx, dy, deficit = _ellipse_clearance(px, py, _lp(px, py), tilted)
    assert deficit > 0
    assert dx * nx + dy * ny > MIN_PUSH_COSINE
    assert abs(nx) > 0.3 and abs(ny) > 0.3  # the normal really is slanted
    bx, by = _brute_nearest(px, py, 0, 0, 100, 20, math.radians(45))
    assert math.hypot(bx - x, by - y) < 0.05  # sanity: the nearest outline point is the one we left


MIN_PUSH_COSINE = 0.999  # the push is the nearest-point direction, which is the normal for a 0.5 px step


# --- the 0.01 px criterion as a guarantee ---------------------------------------

SWEEP_ASPECTS = [0.25, 0.4, 0.5, 0.7, 1.3, 1.7, 2.0, 2.5, 4.0]


def _sweep_case(rng):
    half = rng.choice([3.0, 4.0, 6.0, 10.0])
    aspect = rng.choice(SWEEP_ASPECTS)
    hr = rng.uniform(0.1, 0.8) * half
    vr = hr * rng.choice([1.0, rng.uniform(0.02, 1.0), rng.uniform(0.02, 0.2)])
    cx, cy = rng.uniform(-0.1, 0.1) * half, rng.uniform(-0.1, 0.1) * half
    return half, aspect, hr, vr, cx, cy, rng.uniform(0.0, 360.0)


def _sweep_diagram(half, aspect, hr, vr, cx, cy, rot, render):
    return ir.DiagramIR(
        canvas=ir.Canvas(xmin=-half, xmax=half, ymin=-half, ymax=half, aspect=aspect),
        define=[ir.PointFixed(id="O", x=cx, y=cy),
                ir.EllipseCenterAxes(id="E", center="O", hradius=hr, vradius=vr, rotation_deg=rot),
                ir.CircleCenterRadius(id="X", center="O", radius=0.85 * half)],
        render=render,
    )


def _curve(cx, cy, hr, vr, rot, t):
    r = math.radians(rot)
    u, v = hr * math.cos(t), vr * math.sin(t)
    return cx + u * math.cos(r) - v * math.sin(r), cy + u * math.sin(r) + v * math.cos(r)


def test_worst_outline_error_over_a_random_sweep_is_below_a_hundredth_of_a_pixel():
    """Draw, fill and the fill-with-holes arcs, 480 cases over rotations, aspects
    (1:4 to 4:1), radii (up to ~240 px, the most a 500 px page holds) and thin
    ellipses; every sampled curve point, mapped by hand, is within 0.01 px of the
    emitted outline. The worst error is recorded for the report."""
    rng = random.Random(20261025)
    worst = 0.0
    for case in range(480):
        half, aspect, hr, vr, cx, cy, rot = _sweep_case(rng)
        role = ("draw", "fill", "hole")[case % 3]
        render = {"draw": [ir.Draw(obj="E")], "fill": [ir.Fill(obj="E")],
                  "hole": [ir.Fill(obj="X", holes=["E"])]}[role]
        root = _root(_sweep_diagram(half, aspect, hr, vr, cx, cy, rot, render))
        page = _mapper(root, (-half, half, -half, half), aspect)
        if role == "hole":
            (path,) = [e for e in root.iter() if e.tag.endswith("path") and e.get("data-ir-id") == "X"]
            nums = [float(v) for v in re.findall(r"-?\d+\.?\d*(?:e-?\d+)?", path.get("d").split("Z")[1])]
            (mx, my, rx, ry, phi, _, _, ex, ey, *_rest) = nums
            ccx, ccy = page(cx, cy)
            el = ET.Element("ellipse", {"cx": str(ccx), "cy": str(ccy), "rx": str(rx), "ry": str(ry),
                                        "transform": f"rotate({phi} 0 0)"})
            # the arcs pass through their own endpoints, which must be curve points
            ends = [(mx, my), (ex, ey)]
        else:
            (el,) = [e for e in root.iter() if e.get("data-ir-id") == "E"]
            ends = []
        for i in range(64):
            px, py = page(*_curve(cx, cy, hr, vr, rot, 2 * math.pi * i / 64))
            worst = max(worst, _outline_gap(el, px, py))
        for px, py in ends:
            worst = max(worst, _outline_gap(el, px, py))
        assert worst < 0.01, (case, role, half, aspect, hr, vr, rot, worst)
    print(f"worst sampled outline error: {worst:.5f} px")
    assert worst < 0.01


# --- end-to-end label nudging, as numbers ---------------------------------------

LABEL_CANVAS = (-6, 6, -4, 4)
TILT = 40.0
# (aspect, label point that the 40-degree outline must push, label point whose
# clearance from that outline is just above the threshold but which the untilted
# twin's outline would push)
NUDGE_CASES = [
    (None, (4 * math.cos(math.radians(TILT)), 4 * math.sin(math.radians(TILT))), (-0.5, -1.5)),
    (2.0, (4 * math.cos(math.radians(TILT)), 4 * math.sin(math.radians(TILT))), (-2.75, -1.0)),
    (0.5, (4 * math.cos(math.radians(TILT)), 4 * math.sin(math.radians(TILT))), (-3.0, -1.5)),
]


def _label_diagram(rotation, aspect, q, with_ellipse=True):
    return ir.DiagramIR(
        canvas=ir.Canvas(xmin=-6, xmax=6, ymin=-4, ymax=4, aspect=aspect),
        define=[ir.PointFixed(id="O", x=0, y=0),
                ir.EllipseCenterAxes(id="E", center="O", hradius=4, vradius=1, rotation_deg=rotation),
                ir.PointFixed(id="Q", x=q[0], y=q[1])],
        render=([ir.Draw(obj="E")] if with_ellipse else []) + [ir.LabelPoint(p="Q", text="Q")],
    )


def _label(root):
    (t,) = [e for e in root.iter() if e.get("data-label-text") == "Q"]
    x0, y0, x1, y1 = (float(v) for v in t.get("data-bbox").split(","))
    return (x0, y0, x1, y1), (float(t.get("x")), float(t.get("y")))


def _dense_outline(el, n=8000):
    cx, cy, rx, ry = (float(el.get(k)) for k in ("cx", "cy", "rx", "ry"))
    m = re.match(r"rotate\(([-\d.e+]+) ", el.get("transform", "rotate(0 0 0)"))
    phi = math.radians(float(m.group(1)))
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        u, v = rx * math.cos(t), ry * math.sin(t)
        pts.append((cx + u * math.cos(phi) - v * math.sin(phi), cy + u * math.sin(phi) + v * math.cos(phi)))
    return pts


def _verdict(outline, bbox):
    """(gap, needed clearance, outward unit direction) of a label box centre against
    a dense outline, by brute force."""
    x0, y0, x1, y1 = bbox
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    nx, ny = min(outline, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
    gap = math.hypot(cx - nx, cy - ny)
    dx, dy = (cx - nx) / gap, (cy - ny) / gap
    return gap, abs((x1 - x0) / 2 * dx) + abs((y1 - y0) / 2 * dy) + _NUDGE_MARGIN, (dx, dy)


@pytest.mark.parametrize("aspect,on_outline,near_miss", NUDGE_CASES)
def test_label_on_the_tilted_outline_is_pushed_out_to_its_clearance(aspect, on_outline, near_miss):
    tilted = _dense_outline(next(e for e in _root(_label_diagram(TILT, aspect, on_outline)).iter()
                                 if e.get("data-ir-id") == "E"))
    bare_box, bare_xy = _label(_root(_label_diagram(TILT, aspect, on_outline, with_ellipse=False)))
    gap0, need0, (nx, ny) = _verdict(tilted, bare_box)
    assert gap0 < need0 - 1.0                      # the bare label does violate the outline
    box, xy = _label(_root(_label_diagram(TILT, aspect, on_outline)))
    gap, need, _ = _verdict(tilted, box)
    assert gap >= need - 0.3, (gap, need)          # now at (or just inside) its clearance
    moved = (xy[0] - bare_xy[0], xy[1] - bare_xy[1])
    assert math.hypot(*moved) > 1.0
    # moved away from the outline, along the outward normal at the bare label
    assert (moved[0] * nx + moved[1] * ny) / math.hypot(*moved) > 0.9


@pytest.mark.parametrize("aspect,on_outline,near_miss", NUDGE_CASES)
def test_near_miss_label_keeps_its_exact_position_though_the_untilted_twin_would_push_it(aspect, on_outline, near_miss):
    tilted = _dense_outline(next(e for e in _root(_label_diagram(TILT, aspect, near_miss)).iter()
                                 if e.get("data-ir-id") == "E"))
    twin = _dense_outline(next(e for e in _root(_label_diagram(0, aspect, near_miss)).iter()
                               if e.get("data-ir-id") == "E"))
    with_tilt = _root(_label_diagram(TILT, aspect, near_miss))
    bare = ir_to_svg(_label_diagram(TILT, aspect, near_miss, with_ellipse=False),
                     compile_defs(_label_diagram(TILT, aspect, near_miss, with_ellipse=False)))
    bare_box, bare_xy = _label(ET.fromstring(bare))
    gap, need, _ = _verdict(tilted, bare_box)
    assert 0.1 < gap - need < 2.5                  # just clear of the tilted outline
    gap_t, need_t, _ = _verdict(twin, bare_box)
    assert gap_t < need_t - 0.5                    # the untilted twin would have pushed it
    box, xy = _label(with_tilt)
    assert (box, xy) == (bare_box, bare_xy)        # unmoved, to the printed digit
