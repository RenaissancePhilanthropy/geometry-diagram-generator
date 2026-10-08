"""Per-axis tick/grid steps on Canvas: x_/y_ fields default to the shared one."""
from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from geometry_diagrams.ir.ir import Canvas, DiagramIR, DrawPoints, PointFixed
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz


def _diagram(**canvas_kwargs):
    base = dict(xmin=0, xmax=40, ymin=0, ymax=450, axes=True, show_ticks=True, show_tick_labels=True)
    base.update(canvas_kwargs)
    return DiagramIR(
        canvas=Canvas(**base),
        define=[PointFixed(id="A", x=10, y=200)],
        render=[DrawPoints(points=["A"])],
    )


def _svg(d):
    return SVGRenderer().render(d, compile_defs(d)).output


def _tikz(d):
    return ir_to_tikz(d, compile_defs(d))


def _tick_label_counts(svg):
    x_labels = len(re.findall(r'text-anchor="middle" dominant-baseline="hanging"', svg))
    y_labels = len(re.findall(r'text-anchor="end" dominant-baseline="central"', svg))
    return x_labels, y_labels


def _grid_line_counts(svg):
    lines = re.findall(r'<line x1="([\d.-]+)" y1="([\d.-]+)" x2="([\d.-]+)" y2="([\d.-]+)" stroke="#ccc"', svg)
    vertical = sum(1 for x1, _, x2, _ in lines if x1 == x2)
    horizontal = sum(1 for _, y1, _, y2 in lines if y1 == y2)
    return vertical, horizontal


def test_axis_step_fields_default_to_none_and_must_be_positive():
    c = Canvas()
    assert (c.x_tick_step, c.y_tick_step, c.x_grid_step, c.y_grid_step) == (None, None, None, None)
    for field in ("x_tick_step", "y_tick_step", "x_grid_step", "y_grid_step"):
        with pytest.raises(ValidationError):
            Canvas(**{field: 0})


# tick_values skips the origin and the axis end, so 0..40 by 5 draws 7 ticks.
def test_svg_ticks_use_each_axis_own_step():
    x_labels, y_labels = _tick_label_counts(_svg(_diagram(tick_step=5, y_tick_step=50)))
    assert (x_labels, y_labels) == (7, 8)


def test_svg_shared_step_is_unchanged_without_per_axis_fields():
    x_labels, y_labels = _tick_label_counts(_svg(_diagram(tick_step=5)))
    assert (x_labels, y_labels) == (7, 89)


def test_svg_grid_uses_each_axis_own_step():
    vertical, horizontal = _grid_line_counts(_svg(_diagram(grid=True, grid_step=5, y_grid_step=50)))
    assert (vertical, horizontal) == (9, 10)


def test_svg_x_only_override():
    x_labels, y_labels = _tick_label_counts(_svg(_diagram(tick_step=50, x_tick_step=10)))
    assert (x_labels, y_labels) == (3, 8)


def test_equal_explicit_steps_render_identically_to_the_shared_field():
    shared = _diagram(grid=True, grid_step=5, tick_step=5)
    explicit = _diagram(grid=True, grid_step=5, tick_step=5, x_tick_step=5, y_tick_step=5, x_grid_step=5, y_grid_step=5)
    assert _svg(shared) == _svg(explicit)
    assert _tikz(shared) == _tikz(explicit)


def test_tikz_grid_and_ticks_use_each_axis_own_step():
    out = _tikz(_diagram(grid=True, grid_step=5, y_grid_step=50, tick_step=5, y_tick_step=50))
    assert "step={(5,50)}" in out
    assert len(re.findall(r"\\node\[below, font=\\small\] at", out)) == 7
    assert len(re.findall(r"\\node\[left, font=\\small\] at", out)) == 8


def test_tikz_equal_grid_steps_keep_the_scalar_form():
    assert "step=5]" in _tikz(_diagram(grid=True, grid_step=5))
