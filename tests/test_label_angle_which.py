"""LabelAngle `which`: a reflex label sits on the major side of its vertex."""
from __future__ import annotations

import math
import re

from geometry_diagrams.ir.ir import (
    AnglePoints, DiagramIR, Draw, LabelAngle, MarkAngles, PointFixed, Segment,
)
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz

T = (0.0, 0.0)
F = (4.0, 0.0)
G = (4.0 * math.cos(math.radians(83)), 4.0 * math.sin(math.radians(83)))


def _diagram(label_which=None, mark_which="interior", order=("G", "T", "F")):
    kwargs = {} if label_which is None else {"which": label_which}
    return DiagramIR(
        define=[
            PointFixed(id="T", x=T[0], y=T[1]),
            PointFixed(id="F", x=F[0], y=F[1]),
            PointFixed(id="G", x=G[0], y=G[1]),
            Segment(id="TF", a="T", b="F"),
            Segment(id="TG", a="T", b="G"),
        ],
        render=[
            Draw(obj="TF"),
            Draw(obj="TG"),
            MarkAngles(angles=[AnglePoints(a="F", o="T", b="G")], which=mark_which),
            LabelAngle(angle=AnglePoints(a=order[0], o=order[1], b=order[2]), text="x", **kwargs),
        ],
    )


def _svg(d):
    return SVGRenderer().render(d, compile_defs(d)).output


def _label_side(svg):
    """Dot product of (label - vertex) with the minor-wedge bisector, in SVG pixel space."""
    vx, vy = (float(v) for v in re.search(r'data-endpoints="T,F" x1="([\d.]+)" y1="([\d.]+)"', svg).groups())
    lx, ly = (float(v) for v in re.search(r'data-role="label-angle"[^>]* x="([\d.]+)" y="([\d.]+)"', svg).groups())
    bis = math.radians(83 / 2)
    return (lx - vx) * math.cos(bis) + (-(ly - vy)) * math.sin(bis)


def test_default_label_is_on_the_minor_side():
    assert _label_side(_svg(_diagram())) > 0


def test_reflex_label_is_on_the_major_side():
    assert _label_side(_svg(_diagram(label_which="reflex", mark_which="reflex"))) < 0


def test_reflex_label_side_does_not_depend_on_point_order():
    a = _svg(_diagram(label_which="reflex", order=("G", "T", "F")))
    b = _svg(_diagram(label_which="reflex", order=("F", "T", "G")))
    assert _label_side(a) < 0 and _label_side(b) < 0


def test_ir_without_which_renders_identically_to_explicit_interior():
    assert _svg(_diagram()) == _svg(_diagram(label_which="interior"))


def test_tikz_reflex_label_uses_the_large_arc_orientation():
    d = _diagram(label_which="reflex", mark_which="reflex")
    assert "\\tkzLabelAngle(G,T,F)" in ir_to_tikz(d, compile_defs(d))
    d = _diagram()
    assert "\\tkzLabelAngle(F,T,G)" in ir_to_tikz(d, compile_defs(d))


# ---------------------------------------------------------------------------
# A LabelAngle stays inside its wedge, however thin
# ---------------------------------------------------------------------------

from geometry_diagrams.ir.ir import DrawPoints, LabelPoint, PointFixed as _PF  # noqa: E402


def _wedge_diagram(theta_deg, far, below, size=2.0):
    s = -1 if below else 1
    t = math.tan(math.radians(theta_deg))
    defs = [
        _PF(id="N", x=0, y=0), _PF(id="E", x=size, y=0), _PF(id="J", x=size, y=s * size * t),
        Segment(id="NE", a="N", b="E"), Segment(id="EJ", a="E", b="J"), Segment(id="NJ", a="N", b="J"),
    ]
    rend = [
        Draw(obj="NE"), Draw(obj="EJ"), Draw(obj="NJ"),
        MarkAngles(angles=[AnglePoints(a="E", o="N", b="J")]),
        LabelAngle(angle=AnglePoints(a="E", o="N", b="J"), text="x"),
        LabelPoint(p="N", text="N"), LabelPoint(p="E", text="E"), LabelPoint(p="J", text="J"),
    ]
    if far:
        defs.append(_PF(id="Z", x=far, y=0))
        rend.append(DrawPoints(points=["Z"]))
    return DiagramIR(define=defs, render=rend)


def _angle_off_bisector_deg(svg, theta_deg, below):
    nx, ny = (float(v) for v in re.search(r'data-endpoints="N,E" x1="([\d.]+)" y1="([\d.]+)"', svg).groups())
    lx, ly = (float(v) for v in re.search(r'data-role="label-angle"[^>]* x="([\d.]+)" y="([\d.]+)"', svg).groups())
    ang = math.degrees(math.atan2(-(ly - ny), lx - nx))
    return ang - (-theta_deg / 2 if below else theta_deg / 2)


def test_angle_label_never_leaves_its_wedge():
    for theta in (10, 20, 30, 45, 60, 90):
        for below in (False, True):
            for far in (0, 5, 10, 15, 25, 40):
                svg = _svg(_wedge_diagram(theta, far, below))
                off = _angle_off_bisector_deg(svg, theta, below)
                assert abs(off) < theta / 2, f"theta={theta} far={far} below={below}: {off:.1f}deg off bisector"


def test_angle_label_that_fits_stays_on_the_bisector():
    svg = _svg(_wedge_diagram(30, 0, False))
    assert abs(_angle_off_bisector_deg(svg, 30, False)) < 1.0
