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
