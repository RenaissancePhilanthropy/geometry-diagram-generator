"""Tick marks (MarkArcs) and text along the curve (LabelAlongArc) on elliptical
arcs and sectors, in both renderers.

Every expectation is computed here, independently of the renderer, from the
parametric ellipse (x, y) = (hr cos t, vr sin t): the point and the ellipse's
own outward normal at a parametric angle, and arc length by dense numeric
integration. The renderers are only ever read through their output (SVG
element attributes, emitted TikZ source).
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from geometry_diagrams.ir.ir import (
    Canvas,
    DiagramIR,
    EllipticalArcCenterStartEnd,
    EllipticalSectorCenterStartEnd,
    LabelAlongArc,
    MarkArcs,
    PointFixed,
    Segment,
    Draw,
)
from geometry_diagrams.ir.render_util import (
    SEG_TICK_HALF_LENGTH,
    SEG_TICK_SPACING,
    TIKZ_TEXT_EM,
    TEXT_ADVANCE_EM,
    arc_text_glyphs,
)
from geometry_diagrams.ir.to_svg import _ARC_TEXT_OFFSET, _FONT_SIZE, _TICK_LEN, ir_to_svg
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz

# (id, hr, vr, IR start t, IR end t, reflex, expected CCW sweep in degrees)
CASES = [
    pytest.param(10, 1, 20, 70, False, (20, 70), id="eccentric-10to1-minor"),
    pytest.param(10, 1, 30, 330, True, (30, 330), id="eccentric-10to1-reflex"),
    pytest.param(4, 3, 100, 200, False, (100, 200), id="moderate-4to3"),
    pytest.param(3, 3 * 0.6, 250, 10, False, (250, 10 + 360), id="minor-wrapping-0"),
]
KINDS = [EllipticalArcCenterStartEnd, EllipticalSectorCenterStartEnd]


# ---------------------------------------------------------------------------
# Independent expectations
# ---------------------------------------------------------------------------

def _point(hr, vr, t):
    return np.array([hr * math.cos(t), vr * math.sin(t)])


def _normal(hr, vr, t):
    n = np.array([vr * math.cos(t), hr * math.sin(t)])
    return n / np.linalg.norm(n)


def _curve(hr, vr, t, signed_offset):
    return _point(hr, vr, t) + signed_offset * _normal(hr, vr, t)


def _walk(hr, vr, t0, signed_offset, distances):
    """Parameter values at the given signed arc-length distances from t0 along
    the (offset) curve, by dense polyline integration."""
    t = np.linspace(t0 - math.pi, t0 + math.pi, 400001)
    pts = np.stack([
        hr * np.cos(t) + signed_offset * vr * np.cos(t) / np.hypot(vr * np.cos(t), hr * np.sin(t)),
        vr * np.sin(t) + signed_offset * hr * np.sin(t) / np.hypot(vr * np.cos(t), hr * np.sin(t)),
    ])
    cum = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(pts[0]), np.diff(pts[1])))])
    cum -= cum[len(t) // 2]
    return np.interp(distances, cum, t)


def _tangent_angle_deg(hr, vr, t, signed_offset, sign):
    h = 1e-6
    d = _curve(hr, vr, t + h, signed_offset) - _curve(hr, vr, t - h, signed_offset)
    d = d * sign
    return math.degrees(math.atan2(d[1], d[0]))


def _mid_t(sweep):
    return math.radians((sweep[0] + sweep[1]) / 2)


def _angle_diff(a, b):
    return abs((a - b + 180) % 360 - 180)


def _diagram(kind, hr, vr, s_deg, e_deg, reflex, op, *, calibrate=True):
    s, e = math.radians(s_deg), math.radians(e_deg)
    defs = [
        PointFixed(id="O", x=0, y=0),
        PointFixed(id="U", x=1, y=0),
        PointFixed(id="S", x=hr * math.cos(s), y=vr * math.sin(s)),
        PointFixed(id="E", x=hr * math.cos(e), y=vr * math.sin(e)),
        Segment(id="cal", a="O", b="U"),
        kind(id="ea", center="O", hradius=hr, vradius=vr, start="S", end="E", reflex=reflex),
    ]
    pad = hr * 1.25 + 1
    return DiagramIR(
        canvas=Canvas(xmin=-pad, xmax=pad, ymin=-pad, ymax=pad),
        define=defs,
        render=([Draw(obj="cal")] if calibrate else []) + [op],
    )


# ---------------------------------------------------------------------------
# SVG parsing
# ---------------------------------------------------------------------------

class _Frame:
    """Pixel <-> geometry mapping read back off the SVG via the calibration
    segment O-U (the origin and one construction unit along +x)."""

    def __init__(self, root):
        cal = next(el for el in root.iter() if el.get("data-ir-id") == "cal")
        self.ox, self.oy = float(cal.get("x1")), float(cal.get("y1"))
        self.k = float(cal.get("x2")) - self.ox

    def to_px(self, g):
        return np.array([self.ox + g[0] * self.k, self.oy - g[1] * self.k])


def _render_svg(diagram):
    warnings: list[str] = []
    svg = ir_to_svg(diagram, compile_defs(diagram), warnings=warnings)
    root = ET.fromstring(svg)
    return root, _Frame(root), warnings


def _svg_ticks(root):
    return [
        (np.array([float(el.get("x1")), float(el.get("y1"))]),
         np.array([float(el.get("x2")), float(el.get("y2"))]))
        for el in root.iter() if el.get("data-role") == "mark-arc"
    ]


def _svg_glyphs(root):
    wrapper = next(el for el in root.iter() if el.get("data-role") == "label-along-arc")
    out = []
    for el in wrapper:
        m = re.match(r"rotate\(([-\d.]+),", el.get("transform"))
        out.append((el.text, np.array([float(el.get("x")), float(el.get("y"))]), -float(m.group(1))))
    return out


def _expected_ticks(hr, vr, sweep, n, half, spacing):
    tm = _mid_t(sweep)
    offs = [(i - (n - 1) / 2) * spacing for i in range(n)]
    ts = _walk(hr, vr, tm, 0.0, offs)
    return [(_point(hr, vr, t) - half * _normal(hr, vr, t),
             _point(hr, vr, t) + half * _normal(hr, vr, t)) for t in ts]


def _check_ticks(actual, expected, tol):
    """Compare strokes as unordered sets of (center, direction)."""
    assert len(actual) == len(expected)
    used = set()
    for a1, a2 in actual:
        ac = (a1 + a2) / 2
        best = min((i for i in range(len(expected)) if i not in used),
                   key=lambda i: np.linalg.norm((expected[i][0] + expected[i][1]) / 2 - ac))
        used.add(best)
        e1, e2 = expected[best]
        # the same stroke up to the order of its two endpoints
        same = (np.linalg.norm(a1 - e1) < tol and np.linalg.norm(a2 - e2) < tol) or (
            np.linalg.norm(a1 - e2) < tol and np.linalg.norm(a2 - e1) < tol)
        assert same, f"stroke {a1},{a2} != expected {e1},{e2}"


# ---------------------------------------------------------------------------
# SVG: ticks
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("hr,vr,s,e,reflex,sweep", CASES)
@pytest.mark.parametrize("n", [1, 3])
def test_svg_ticks_sit_on_the_ellipse_along_its_own_normal(kind, hr, vr, s, e, reflex, sweep, n):
    d = _diagram(kind, hr, vr, s, e, reflex, MarkArcs(arcs=["ea"], ticks=n))
    root, f, warnings = _render_svg(d)
    assert not [w for w in warnings if "ea" in w]
    expected = [
        (f.to_px(a), f.to_px(b))
        for a, b in _expected_ticks(hr, vr, sweep, n, _TICK_LEN / f.k, 4.0 / f.k)
    ]
    _check_ticks(_svg_ticks(root), expected, tol=0.05)


def test_svg_eccentric_tick_is_not_radial():
    """On a 10:1 ellipse the stroke's direction differs visibly from the
    center-to-point (radial) direction -- the test that would pass if the
    circular code were reused unchanged is the one this guards against."""
    hr, vr, s, e = 10, 1, 20, 70
    d = _diagram(EllipticalArcCenterStartEnd, hr, vr, s, e, False, MarkArcs(arcs=["ea"], ticks=1))
    root, f, _ = _render_svg(d)
    (a, b), = _svg_ticks(root)
    stroke = (b - a) / np.linalg.norm(b - a)
    tm = _mid_t((s, e))
    p = _point(hr, vr, tm)
    radial = np.array([p[0], -p[1]]) / np.linalg.norm(p)  # pixel space (y flipped)
    cos_angle = abs(float(stroke @ radial))
    assert cos_angle < 0.9  # radial would be ~1.0
    nrm = _normal(hr, vr, tm)
    assert abs(float(stroke @ np.array([nrm[0], -nrm[1]]))) == pytest.approx(1.0, abs=1e-3)


# ---------------------------------------------------------------------------
# SVG: text along the curve
# ---------------------------------------------------------------------------

def _text_expectation(hr, vr, sweep, text, adv_unit, offset, side, pos, flip):
    """Independent glyph layout: (char, geometry center, rotation_deg)."""
    glyphs = arc_text_glyphs(text, adv_unit)
    advs = [a for _, a in glyphs]
    t0 = math.radians(sweep[0] + pos * (sweep[1] - sweep[0]))
    sgn = 1.0 if side == "outside" else -1.0
    if flip is None:
        up = 1.0 if _normal(hr, vr, t0)[1] >= 0 else -1.0
    else:
        up = -1.0 if flip else 1.0
    step = -up
    total = sum(advs)
    cum, dists = 0.0, []
    for a in advs:
        dists.append(step * (-total / 2 + cum + a / 2))
        cum += a
    ts = _walk(hr, vr, t0, sgn * offset, dists)
    return [
        (ch, _curve(hr, vr, t, sgn * offset), _tangent_angle_deg(hr, vr, t, sgn * offset, step))
        for (ch, _), t in zip(glyphs, ts)
    ]


TEXT_CASES = [
    # hr, vr, s, e, reflex, sweep, kind-agnostic params
    pytest.param(10, 1, 20, 70, False, (20, 70), "outside", 0.5, None, id="eccentric-outside-auto"),
    pytest.param(10, 1, 20, 70, False, (20, 70), "inside", 0.5, None, id="eccentric-inside"),
    pytest.param(10, 1, 30, 330, True, (30, 330), "outside", 0.25, None, id="reflex-upper-auto"),
    pytest.param(10, 1, 30, 330, True, (30, 330), "outside", 0.75, None, id="reflex-lower-auto"),
    pytest.param(4, 3, 100, 200, False, (100, 200), "outside", 0.5, True, id="moderate-flip"),
]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("hr,vr,s,e,reflex,sweep,side,pos,flip", TEXT_CASES)
def test_svg_glyphs_follow_the_curve_by_arc_length(kind, hr, vr, s, e, reflex, sweep, side, pos, flip):
    text = "arc len"
    d = _diagram(kind, hr, vr, s, e, reflex, LabelAlongArc(arc="ea", text=text, side=side, pos=pos, flip=flip))
    root, f, warnings = _render_svg(d)
    assert not [w for w in warnings if "ea" in w]
    got = _svg_glyphs(root)
    exp = _text_expectation(hr, vr, sweep, text, _FONT_SIZE / f.k, _ARC_TEXT_OFFSET / f.k, side, pos, flip)
    non_space = [g for g in exp if g[0].strip()]
    assert [c for c, _, _ in got] == [c for c, _, _ in non_space]
    for (_, p, rot), (_, gp, grot) in zip(got, non_space):
        assert np.linalg.norm(p - f.to_px(gp)) < 0.1
        assert _angle_diff(rot, grot) < 0.5  # rot is the geometry angle (SVG rotate() negated)


def test_svg_eccentric_text_is_not_squeezed_on_the_sharp_end():
    """Glyph centers are one advance apart ALONG the offset curve even where
    curvature is extreme: consecutive pixel chords never exceed the advance and
    the cumulative polyline distance equals it."""
    hr, vr = 10, 1
    text = "abcdef"
    d = _diagram(EllipticalArcCenterStartEnd, hr, vr, -40, 40, False,
                 LabelAlongArc(arc="ea", text=text, side="outside", pos=0.5))
    root, f, _ = _render_svg(d)
    pts = [p for _, p, _ in _svg_glyphs(root)]
    adv_px = _FONT_SIZE * TEXT_ADVANCE_EM
    for a, b in zip(pts, pts[1:]):
        chord = float(np.linalg.norm(a - b))
        assert chord <= adv_px + 0.2
        assert chord > 0.8 * adv_px


def test_svg_readable_text_is_upright_on_upper_and_lower_halves():
    for pos in (0.25, 0.75):
        d = _diagram(EllipticalArcCenterStartEnd, 10, 1, 30, 330, True,
                     LabelAlongArc(arc="ea", text="word", pos=pos))
        root, _, _ = _render_svg(d)
        for _, _, rot in _svg_glyphs(root):
            assert abs(rot) < 90  # never upside down


def test_svg_overlong_text_degrades_like_circular_for_unlayoutable():
    d = _diagram(EllipticalArcCenterStartEnd, 4, 3, 100, 200, False,
                 LabelAlongArc(arc="ea", text="P_1"))
    root, _, warnings = _render_svg(d)
    assert any("cannot be laid out per glyph" in w for w in warnings)
    singles = [el for el in root.iter() if el.get("data-role") == "label-along-arc"]
    assert len(singles) == 1 and singles[0].tag.endswith("text")


@pytest.mark.parametrize("op", [MarkArcs(arcs=["cal"], ticks=2), LabelAlongArc(arc="cal", text="abc")])
def test_svg_a_non_arc_still_warns(op):
    d = _diagram(EllipticalArcCenterStartEnd, 4, 3, 100, 200, False, op)
    root, _, warnings = _render_svg(d)
    assert any("'cal' is not an arc/sector" in w for w in warnings)
    assert _svg_ticks(root) == []


# ---------------------------------------------------------------------------
# TikZ: emitted source
# ---------------------------------------------------------------------------

def _render_tikz(diagram):
    warnings: list[str] = []
    return ir_to_tikz(diagram, compile_defs(diagram), warnings=warnings), warnings


_DRAW_RE = re.compile(r"^\\draw(?:\[[^\]]*\])? \(([-\d.e]+),([-\d.e]+)\) -- \(([-\d.e]+),([-\d.e]+)\);$", re.M)
_NODE_RE = re.compile(r"^\\node\[rotate=([-\d.e]+)[^\]]*\] at \(([-\d.e]+),([-\d.e]+)\) \{\$(.*)\$\};$", re.M)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("hr,vr,s,e,reflex,sweep", CASES)
@pytest.mark.parametrize("n", [1, 3])
def test_tikz_ticks_sit_on_the_ellipse_along_its_own_normal(kind, hr, vr, s, e, reflex, sweep, n):
    d = _diagram(kind, hr, vr, s, e, reflex, MarkArcs(arcs=["ea"], ticks=n), calibrate=False)
    tikz, warnings = _render_tikz(d)
    assert not [w for w in warnings if "ea" in w]
    actual = [(np.array([float(a), float(b)]), np.array([float(c), float(dd)]))
              for a, b, c, dd in _DRAW_RE.findall(tikz)]
    expected = _expected_ticks(hr, vr, sweep, n, SEG_TICK_HALF_LENGTH, SEG_TICK_SPACING)
    _check_ticks(actual, expected, tol=2e-3)


def _tikz_offset(hr, vr):
    return max(0.18, min(hr, vr) * 0.09)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("hr,vr,s,e,reflex,sweep,side,pos,flip", TEXT_CASES)
def test_tikz_glyphs_follow_the_curve_by_arc_length(kind, hr, vr, s, e, reflex, sweep, side, pos, flip):
    text = "arc len"
    d = _diagram(kind, hr, vr, s, e, reflex,
                 LabelAlongArc(arc="ea", text=text, side=side, pos=pos, flip=flip), calibrate=False)
    tikz, warnings = _render_tikz(d)
    assert not [w for w in warnings if "ea" in w]
    got = [(ch, np.array([float(x), float(y)]), float(rot)) for rot, x, y, ch in _NODE_RE.findall(tikz)]
    exp = [g for g in _text_expectation(hr, vr, sweep, text, TIKZ_TEXT_EM, _tikz_offset(hr, vr), side, pos, flip)
           if g[0].strip()]
    assert [c for c, _, _ in got] == [c for c, _, _ in exp]
    for (_, p, rot), (_, gp, grot) in zip(got, exp):
        assert np.linalg.norm(p - gp) < 2e-3
        assert _angle_diff(rot, grot) < 0.05


@pytest.mark.parametrize("op", [MarkArcs(arcs=["cal"], ticks=2), LabelAlongArc(arc="cal", text="abc")])
def test_tikz_a_non_arc_still_warns(op):
    d = _diagram(EllipticalArcCenterStartEnd, 4, 3, 100, 200, False, op, calibrate=False)
    tikz, warnings = _render_tikz(d)
    assert any("'cal' is not an arc/sector" in w for w in warnings)
