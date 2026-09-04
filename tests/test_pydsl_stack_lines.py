# tests/test_pydsl_stack_lines.py
"""Tests for stack_lines() — the general primitive (ticket 04) extracted
from equation_steps()'s core loop. Unlike equation_steps(), stack_lines()
does NOT call canvas() itself: it only places labels and returns the
extent a caller needs to fold into its own canvas() call, so it composes
with other geometry in a larger diagram that owns a single canvas() call.

See test_pydsl_equation_steps.py for equation_steps()'s own behavior
(unchanged by this ticket) and its end-to-end rendering seam."""
import pytest

from geometry_diagrams.ir.ir import Canvas as CanvasDef
from geometry_diagrams.ir.ir import LabelFreeText
from geometry_diagrams.pydsl.api import canvas, stack_lines
from geometry_diagrams.pydsl.builder import new_builder_context


# ---------------------------------------------------------------------------
# Seam (a): stack_lines() in isolation
# ---------------------------------------------------------------------------

def test_stack_lines_records_stacked_label_free_text_ops_with_decreasing_y():
    with new_builder_context() as builder:
        stack_lines(["3x + 5 = 20", "3x = 15", "x = 5"])
        ir = builder.build()
    labels = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert len(labels) == 3
    assert [l.text for l in labels] == ["3x + 5 = 20", "3x = 15", "x = 5"]
    ys = [l.at[1] for l in labels]
    assert ys == [0.0, -1.2, -2.4]
    assert all(l.at[0] == 0.0 for l in labels)


def test_stack_lines_respects_x_and_y_step_overrides():
    with new_builder_context() as builder:
        stack_lines(["a", "b"], x=3.0, y_step=2.0)
        ir = builder.build()
    labels = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert [l.at for l in labels] == [[3.0, 0.0], [3.0, -2.0]]


def test_stack_lines_returns_extent_covering_all_placed_labels():
    with new_builder_context():
        half_width, y_min, y_max = stack_lines(["a", "b", "c", "d"], y_step=1.2)
    # 4 lines at y = 0, -1.2, -2.4, -3.6 must all fall strictly inside
    # [y_min, y_max], with the range sized to the line count.
    assert y_min < -3.6
    assert y_max > 0.0
    assert half_width > 0.0


def test_stack_lines_does_not_call_canvas():
    # The whole point of this ticket: stack_lines() must not touch the
    # builder's canvas state, so a script with its own geometry can call
    # canvas() itself exactly once, after (or before) calling stack_lines().
    with new_builder_context() as builder:
        assert builder._canvas is None
        stack_lines(["a", "b"])
        assert builder._canvas is None


def test_stack_lines_does_not_prevent_a_subsequent_canvas_call():
    with new_builder_context() as builder:
        half_width, y_min, y_max = stack_lines(["a", "b"])
        canvas(x_range=(-half_width, half_width), y_range=(y_min, y_max))
        ir = builder.build()
    assert ir.canvas is not None


def test_stack_lines_rejects_empty_lines():
    with new_builder_context():
        with pytest.raises(ValueError):
            stack_lines([])


def test_stack_lines_requires_a_builder():
    with pytest.raises(RuntimeError):
        stack_lines(["a"])


def test_stack_lines_is_exported_ungated_in_pydsl_all():
    import geometry_diagrams.pydsl as pydsl_module

    assert "stack_lines" in pydsl_module.__all__
    assert pydsl_module.stack_lines is stack_lines


def test_stack_lines_appears_in_generated_stub_with_no_flag_required():
    from geometry_diagrams.pydsl.stub import generate_stub

    stub = generate_stub()
    assert "def stack_lines(" in stub


# ---------------------------------------------------------------------------
# Seam (c): stack_lines() used inside a larger diagram with its own geometry
# and its own single canvas() call
# ---------------------------------------------------------------------------

def test_stack_lines_composes_with_other_geometry_under_one_canvas_call():
    from geometry_diagrams.ir.to_sympy import compile_defs
    from geometry_diagrams.ir.renderer import SVGRenderer
    from geometry_diagrams.pydsl.api import point, segment

    with new_builder_context() as builder:
        p1 = point(-5.0, 3.0)
        p2 = point(5.0, 3.0)
        segment(p1, p2)

        # Stack some annotation text off to the side, inside the same
        # diagram, well below the segment.
        half_width, y_min, y_max = stack_lines(
            ["3x + 5 = 20", "3x = 15", "x = 5"], x=0.0, y_step=1.2
        )

        # The calling script folds stack_lines()'s extent into its own
        # single canvas() call, alongside the extent needed for its own
        # geometry (the segment spans x in [-5, 5], y = 3).
        xmin = min(-5.0, -half_width)
        xmax = max(5.0, half_width)
        ymin = min(y_min, 3.0)
        ymax = max(y_max, 3.0 + 1.0)
        canvas(x_range=(xmin, xmax), y_range=(ymin, ymax))

        ir = builder.build()

    assert ir.canvas is not None
    assert isinstance(ir.canvas, CanvasDef)
    # Segment endpoints and every stacked label must fall inside the
    # single canvas that was set.
    labels = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert len(labels) == 3
    for l in labels:
        lx, ly = l.at
        assert ir.canvas.xmin <= lx <= ir.canvas.xmax
        assert ir.canvas.ymin <= ly <= ir.canvas.ymax
    assert ir.canvas.xmin <= -5.0 and ir.canvas.xmax >= 5.0
    assert ir.canvas.ymin <= 3.0 <= ir.canvas.ymax

    sym = compile_defs(ir)
    svg = SVGRenderer().render(ir, sym).output
    assert svg.count('data-role="label-free-text"') == 3
