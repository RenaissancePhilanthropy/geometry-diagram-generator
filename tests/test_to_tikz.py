from __future__ import annotations

from ir.ir import Canvas, DiagramIR, Draw, LabelPoint, PointFixed, Triangle
from ir.to_sympy import compile_defs
from ir.to_tikz import ir_to_tikz


def _compile_tikz(diagram: DiagramIR) -> str:
    sym = compile_defs(diagram)
    return ir_to_tikz(diagram, sym)


def test_ir_to_tikz_emits_raw_coordinate_plane():
    diagram = DiagramIR(
        canvas=Canvas(
            xmin=-0.5,
            xmax=4.2,
            ymin=-0.5,
            ymax=3.6,
            grid=True,
            grid_step=1,
            axes=True,
            tick_step=1,
            show_ticks=True,
            show_tick_labels=True,
            show_axis_labels=True,
        ),
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=0, y=3),
            Triangle(id="T", a="A", b="B", c="C"),
        ],
        render=[Draw(obj="T")],
    )

    tikz = _compile_tikz(diagram)

    assert "\\tkzGrid" not in tikz
    assert "\\tkzAxeXY" not in tikz
    assert "\\draw[gray!35,thin,step=1] (-1,-1) grid (5,4);" in tikz
    assert "\\draw[->,thick] (-0.5,0) -- (4.2,0) node[right] {$x$};" in tikz
    assert "\\draw[->,thick] (0,-0.5) -- (0,3.6) node[above] {$y$};" in tikz
    assert "\\node[below, font=\\small] at (1,0) {1};" in tikz
    assert "\\node[left, font=\\small] at (0,1) {1};" in tikz


def test_ir_to_tikz_expands_bounds_to_include_origin_for_axes():
    diagram = DiagramIR(
        canvas=Canvas(xmin=1, xmax=4, ymin=1, ymax=3, axes=True),
        define=[PointFixed(id="A", x=1, y=1)],
        render=[LabelPoint(p="A", pos="above")],
    )

    tikz = _compile_tikz(diagram)

    assert "\\tkzInit[xmin=0,xmax=4,ymin=0,ymax=3]" in tikz
    assert "\\draw[->,thick] (0,0) -- (4,0);" in tikz
    assert "\\draw[->,thick] (0,0) -- (0,3);" in tikz


def test_ir_to_tikz_label_point_text_preserves_point_name():
    diagram = DiagramIR(
        define=[PointFixed(id="A", x=0, y=0)],
        render=[LabelPoint(p="A", text=r"A\,(0,0)", pos="below")],
    )

    tikz = _compile_tikz(diagram)

    assert r"\tkzLabelPoint[below](A){$A\,(0,0)$}" in tikz
