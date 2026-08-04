# tests/test_pydsl_canvas.py
"""Tests for pydsl canvas/grid support: canvas() records an ir.Canvas onto
Builder._canvas, and Builder.build() passes it through to DiagramIR.canvas
(replacing the previous hardcoded canvas=None). _nice_step() is the
auto-computed grid/tick spacing heuristic canvas() uses when grid_step/
tick_step aren't given explicitly."""
import pytest

from geometry_diagrams.pydsl.api import _nice_step, canvas, point
from geometry_diagrams.pydsl.builder import new_builder_context


def test_nice_step_small_span():
    assert _nice_step(8) == 1.0


def test_nice_step_medium_span():
    assert _nice_step(500) == 50.0


def test_nice_step_large_span():
    assert _nice_step(1000) == 100.0


def test_nice_step_zero_or_negative_span_returns_one():
    assert _nice_step(0) == 1.0
    assert _nice_step(-5) == 1.0


def test_nice_step_residual_thresholds():
    # raw = span / 10. residual = raw / magnitude, magnitude = 10**floor(log10(raw)).
    # residual < 1.5 -> nice=1; < 3 -> nice=2; < 7 -> nice=5; else -> nice=10.
    assert _nice_step(10) == 1.0    # raw=1.0, magnitude=1, residual=1.0  (<1.5 -> 1)
    assert _nice_step(20) == 2.0    # raw=2.0, magnitude=1, residual=2.0  (<3 -> 2)
    assert _nice_step(40) == 5.0    # raw=4.0, magnitude=1, residual=4.0  (<7 -> 5)
    assert _nice_step(80) == 10.0   # raw=8.0, magnitude=1, residual=8.0  (>=7 -> 10)


def test_canvas_records_ir_canvas_with_auto_computed_step():
    with new_builder_context() as builder:
        canvas(x_range=(0, 8), y_range=(0, 6), grid=True)
        ir = builder.build()
    assert ir.canvas is not None
    assert ir.canvas.xmin == 0
    assert ir.canvas.xmax == 8
    assert ir.canvas.ymin == 0
    assert ir.canvas.ymax == 6
    assert ir.canvas.grid is True
    assert ir.canvas.grid_step == 1.0   # auto-computed: max(8, 6) -> _nice_step(8) == 1.0
    assert ir.canvas.axes is False
    assert ir.canvas.tick_step == 1.0   # also auto-computed, independently
    assert ir.canvas.show_ticks is False
    assert ir.canvas.show_tick_labels is False
    assert ir.canvas.show_axis_labels is False
    assert ir.canvas.clip is True       # untouched, ir.Canvas's own default


def test_canvas_grid_step_auto_computes_from_larger_span():
    with new_builder_context() as builder:
        canvas(x_range=(0, 500), y_range=(0, 10), grid=True)
        ir = builder.build()
    assert ir.canvas.grid_step == 50.0  # driven by the larger span (500), not the smaller (10)


def test_canvas_explicit_grid_step_and_tick_step_override_auto_compute():
    with new_builder_context() as builder:
        canvas(x_range=(0, 8), y_range=(0, 6), grid=True, grid_step=2.0,
               axes=True, tick_step=0.5, show_ticks=True,
               show_tick_labels=True, show_axis_labels=True)
        ir = builder.build()
    assert ir.canvas.grid_step == 2.0
    assert ir.canvas.tick_step == 0.5
    assert ir.canvas.axes is True
    assert ir.canvas.show_ticks is True
    assert ir.canvas.show_tick_labels is True
    assert ir.canvas.show_axis_labels is True


def test_canvas_accepts_lists_not_just_tuples():
    with new_builder_context() as builder:
        canvas(x_range=[0, 8], y_range=[0, 6])
        ir = builder.build()
    assert ir.canvas.xmin == 0
    assert ir.canvas.xmax == 8


def test_builder_without_canvas_call_still_has_none_canvas():
    with new_builder_context() as builder:
        point(1, 2)
        ir = builder.build()
    assert ir.canvas is None


def test_canvas_called_twice_raises():
    with new_builder_context():
        canvas(x_range=(0, 8), y_range=(0, 6))
        with pytest.raises(ValueError, match="already called once"):
            canvas(x_range=(0, 4), y_range=(0, 4))


def test_canvas_inverted_x_range_raises():
    with new_builder_context():
        with pytest.raises(ValueError, match="x_range"):
            canvas(x_range=(8, 0), y_range=(0, 6))


def test_canvas_degenerate_x_range_raises():
    with new_builder_context():
        with pytest.raises(ValueError, match="x_range"):
            canvas(x_range=(4, 4), y_range=(0, 6))


def test_canvas_inverted_y_range_raises():
    with new_builder_context():
        with pytest.raises(ValueError, match="y_range"):
            canvas(x_range=(0, 8), y_range=(6, 0))


@pytest.mark.parametrize("bad_step", [0, -1])
def test_canvas_non_positive_grid_step_raises(bad_step):
    with new_builder_context():
        with pytest.raises(ValueError, match="grid_step"):
            canvas(x_range=(0, 8), y_range=(0, 6), grid_step=bad_step)


@pytest.mark.parametrize("bad_step", [0, -1])
def test_canvas_non_positive_tick_step_raises(bad_step):
    with new_builder_context():
        with pytest.raises(ValueError, match="tick_step"):
            canvas(x_range=(0, 8), y_range=(0, 6), tick_step=bad_step)


def test_canvas_excessive_grid_density_from_explicit_step_raises():
    with new_builder_context():
        with pytest.raises(ValueError, match="grid lines"):
            canvas(x_range=(0, 8), y_range=(0, 6), grid=True, grid_step=0.001)


def test_canvas_excessive_tick_density_from_explicit_step_raises():
    with new_builder_context():
        with pytest.raises(ValueError, match="ticks"):
            canvas(x_range=(0, 8), y_range=(0, 6), show_ticks=True, tick_step=0.001)


def test_canvas_large_span_with_auto_computed_step_does_not_raise():
    # Confirms the density backstop only fires on a bad EXPLICIT override,
    # never on the auto-computed default — a large canvas with grid=True
    # and no grid_step given must succeed.
    with new_builder_context() as builder:
        canvas(x_range=(0, 10000), y_range=(0, 10000), grid=True)
        ir = builder.build()
    assert ir.canvas.grid_step == 1000.0


def test_canvas_works_through_the_real_sandbox():
    from geometry_diagrams.pydsl.sandbox import run_script

    script = (
        "canvas(x_range=(0, 8), y_range=(0, 6), grid=True)\n"
        "a = point(1, 2)\n"
        "b = point(7, 6)\n"
        "draw_points(a, b)\n"
    )
    result = run_script(script, timeout_seconds=10.0)
    assert result.error is None, result.error
    assert result.diagram_ir is not None
    assert result.diagram_ir.canvas is not None
    assert result.diagram_ir.canvas.grid is True
    assert result.diagram_ir.canvas.xmin == 0
    assert result.diagram_ir.canvas.xmax == 8


def test_canvas_double_call_through_the_real_sandbox():
    from geometry_diagrams.pydsl.sandbox import run_script

    script = (
        "canvas(x_range=(0, 8), y_range=(0, 6))\n"
        "canvas(x_range=(0, 4), y_range=(0, 4))\n"
    )
    result = run_script(script, timeout_seconds=10.0)
    assert result.error is not None
    assert "already called once" in result.error
    assert result.diagram_ir is None
