"""Tests for the experimental cookbook module and its gating plumbing.

Ticket 08 built the (previously empty) infrastructure; ticket 09 adds the
first three real helper functions (unit_grid, array_of, tick_marks) and
exercises them both directly (IR-fragment shape, via new_builder_context()
— same convention as test_pydsl_draw_brace.py) and through the real
sandbox with enable_cookbook=True (the getattr(pydsl_module, name) gotcha
flagged in ticket 08's review)."""
from __future__ import annotations

import math
import types

import pytest

import geometry_diagrams.pydsl as pydsl_module
from geometry_diagrams.ir.ir import CircleCenterRadius, Draw, Polygon as PolygonDef, PointFixed, Segment as SegmentDef
from geometry_diagrams.pydsl.api import canvas, point
from geometry_diagrams.pydsl.builder import new_builder_context
from geometry_diagrams.pydsl.cookbook import array_of, bar, bars, table_grid, tick_marks, unit_grid
from geometry_diagrams.pydsl.sandbox import run_script


def test_cookbook_names_lists_the_ticket_09_10_and_11_helpers():
    assert pydsl_module.COOKBOOK_NAMES == ["unit_grid", "array_of", "tick_marks", "bar", "bars", "table_grid"]


def test_cookbook_names_is_not_exported_in_all():
    """Kept out of __all__ so it's never handed to the sandbox child as a
    regular callable tool — it's a name list, not itself an API function."""
    assert "COOKBOOK_NAMES" not in pydsl_module.__all__


def test_cookbook_names_are_all_reachable_as_pydsl_package_attributes():
    """The critical wiring gotcha flagged in ticket 08's review:
    _sandbox_child.py's _build_tool_names does getattr(pydsl_module, name)
    for each COOKBOOK_NAMES entry — every name here must actually be
    importable off the geometry_diagrams.pydsl package namespace, not just
    listed as a string."""
    for name in pydsl_module.COOKBOOK_NAMES:
        assert hasattr(pydsl_module, name), (
            f"{name!r} is in COOKBOOK_NAMES but not importable as "
            f"geometry_diagrams.pydsl.{name} — sandbox execution with "
            f"enable_cookbook=True would raise AttributeError"
        )


def test_build_tool_names_excludes_cookbook_by_default():
    from geometry_diagrams.pydsl._sandbox_child import _build_tool_names

    fake_module = types.SimpleNamespace(__all__=["point", "triangle"], COOKBOOK_NAMES=["future_helper"])
    assert _build_tool_names(fake_module, enable_cookbook=False) == ["point", "triangle"]


def test_build_tool_names_includes_cookbook_when_enabled():
    from geometry_diagrams.pydsl._sandbox_child import _build_tool_names

    fake_module = types.SimpleNamespace(__all__=["point", "triangle"], COOKBOOK_NAMES=["future_helper"])
    assert _build_tool_names(fake_module, enable_cookbook=True) == ["point", "triangle", "future_helper"]


def test_build_tool_names_with_real_module_adds_exactly_the_cookbook_names():
    from geometry_diagrams.pydsl._sandbox_child import _build_tool_names

    assert _build_tool_names(pydsl_module, enable_cookbook=False) == list(pydsl_module.__all__)
    with_cookbook = _build_tool_names(pydsl_module, enable_cookbook=True)
    assert with_cookbook == list(pydsl_module.__all__) + list(pydsl_module.COOKBOOK_NAMES)


# --- unit_grid ---------------------------------------------------------------

def test_unit_grid_draws_cols_plus_1_and_rows_plus_1_lines():
    with new_builder_context() as builder:
        canvas(x_range=(-1, 5), y_range=(-1, 5))
        unit_grid(0, 0, cols=3, rows=2)
        ir = builder.build()
    segment_ids = {d.id for d in ir.define if isinstance(d, SegmentDef)}
    draws = [r for r in ir.render if isinstance(r, Draw) and r.obj in segment_ids]
    # (3 + 1) vertical + (2 + 1) horizontal = 7 lines
    assert len(draws) == 7


def test_unit_grid_lines_span_the_full_grid_extent():
    with new_builder_context() as builder:
        canvas(x_range=(-1, 5), y_range=(-1, 5))
        unit_grid(2, 3, cols=2, rows=1, cell_size=1.5)
        ir = builder.build()
    points_by_id = {d.id: d for d in ir.define if isinstance(d, PointFixed)}
    segs = [d for d in ir.define if isinstance(d, SegmentDef)]
    xs = sorted({points_by_id[s.a].x for s in segs} | {points_by_id[s.b].x for s in segs})
    ys = sorted({points_by_id[s.a].y for s in segs} | {points_by_id[s.b].y for s in segs})
    assert xs[0] == pytest.approx(2.0)
    assert xs[-1] == pytest.approx(2.0 + 2 * 1.5)
    assert ys[0] == pytest.approx(3.0)
    assert ys[-1] == pytest.approx(3.0 + 1 * 1.5)


def test_unit_grid_rejects_non_positive_dimensions():
    with new_builder_context():
        canvas(x_range=(-1, 5), y_range=(-1, 5))
        with pytest.raises(ValueError):
            unit_grid(0, 0, cols=0, rows=2)
        with pytest.raises(ValueError):
            unit_grid(0, 0, cols=2, rows=2, cell_size=0)


def test_unit_grid_requires_a_builder():
    with pytest.raises(RuntimeError):
        unit_grid(0, 0, cols=2, rows=2)


# --- array_of ----------------------------------------------------------------

def test_array_of_places_n_shapes_and_returns_n_handles():
    with new_builder_context() as builder:
        canvas(x_range=(-1, 10), y_range=(-10, 1))
        shapes = array_of(5, shape="circle", cols=3)
        ir = builder.build()
    assert len(shapes) == 5
    circle_ids = {d.id for d in ir.define if isinstance(d, CircleCenterRadius)}
    assert circle_ids == {s.id for s in shapes}
    draws = [r for r in ir.render if isinstance(r, Draw) and r.obj in circle_ids]
    assert len(draws) == 5


def test_array_of_default_cols_is_roughly_square():
    with new_builder_context() as builder:
        canvas(x_range=(-1, 10), y_range=(-10, 1))
        shapes = array_of(9)  # default cols = ceil(sqrt(9)) = 3
        ir = builder.build()
    assert len(shapes) == 9
    points_by_id = {d.id: d for d in ir.define if isinstance(d, PointFixed)}
    centers = [points_by_id[s.center].y for s in ir.define if isinstance(s, CircleCenterRadius)]
    # 3 distinct rows (3x3 grid)
    assert len({round(y, 6) for y in centers}) == 3


def test_array_of_squares_use_rectangle_defs():
    with new_builder_context() as builder:
        canvas(x_range=(-1, 10), y_range=(-10, 1))
        shapes = array_of(4, shape="square", cols=2)
        ir = builder.build()
    rects = [d for d in ir.define if isinstance(d, PolygonDef)]
    assert len(rects) == 4
    assert len(shapes) == 4


def test_array_of_fills_when_color_given():
    from geometry_diagrams.ir.ir import Fill

    with new_builder_context() as builder:
        canvas(x_range=(-1, 10), y_range=(-10, 1))
        array_of(3, shape="circle", cols=3, color="blue")
        ir = builder.build()
    fills = [r for r in ir.render if isinstance(r, Fill)]
    assert len(fills) == 3


def test_array_of_rejects_bad_shape():
    with new_builder_context():
        canvas(x_range=(-1, 10), y_range=(-10, 1))
        with pytest.raises(ValueError):
            array_of(3, shape="triangle")


def test_array_of_rejects_n_less_than_1():
    with new_builder_context():
        canvas(x_range=(-1, 10), y_range=(-10, 1))
        with pytest.raises(ValueError):
            array_of(0)


# --- tick_marks ----------------------------------------------------------------

def test_tick_marks_places_n_ticks_including_endpoints():
    with new_builder_context() as builder:
        canvas(x_range=(-1, 11), y_range=(-2, 2))
        p1 = point(0, 0)
        p2 = point(10, 0)
        ticks = tick_marks(p1, p2, n=11)
        ir = builder.build()
    assert len(ticks) == 11
    points_by_id = {d.id: d for d in ir.define if isinstance(d, PointFixed)}
    seg_defs = {d.id: d for d in ir.define if isinstance(d, SegmentDef)}
    first_seg = seg_defs[ticks[0].id]
    a, b = points_by_id[first_seg.a], points_by_id[first_seg.b]
    assert math.isclose((a.x + b.x) / 2, 0.0, abs_tol=1e-9)
    assert math.isclose((a.y + b.y) / 2, 0.0, abs_tol=1e-9)
    last_seg = seg_defs[ticks[-1].id]
    a, b = points_by_id[last_seg.a], points_by_id[last_seg.b]
    assert math.isclose((a.x + b.x) / 2, 10.0, abs_tol=1e-9)
    assert math.isclose((a.y + b.y) / 2, 0.0, abs_tol=1e-9)


def test_tick_marks_are_perpendicular_to_the_segment():
    with new_builder_context() as builder:
        canvas(x_range=(-1, 11), y_range=(-2, 2))
        p1 = point(0, 0)
        p2 = point(10, 0)
        ticks = tick_marks(p1, p2, n=3, length=0.4)
        ir = builder.build()
    points_by_id = {d.id: d for d in ir.define if isinstance(d, PointFixed)}
    seg_defs = {d.id: d for d in ir.define if isinstance(d, SegmentDef)}
    mid_seg = seg_defs[ticks[1].id]
    a, b = points_by_id[mid_seg.a], points_by_id[mid_seg.b]
    # Horizontal p1->p2 segment => ticks must be vertical (same x, differing y).
    assert math.isclose(a.x, b.x, abs_tol=1e-9)
    assert math.isclose(abs(a.y - b.y), 0.4, abs_tol=1e-9)


def test_tick_marks_rejects_n_less_than_2():
    with new_builder_context():
        canvas(x_range=(-1, 11), y_range=(-2, 2))
        with pytest.raises(ValueError):
            tick_marks(point(0, 0), point(10, 0), n=1)


def test_tick_marks_rejects_coincident_points():
    with new_builder_context():
        canvas(x_range=(-1, 11), y_range=(-2, 2))
        p = point(0, 0)
        with pytest.raises(ValueError):
            tick_marks(p, p, n=3)


# --- bar ----------------------------------------------------------------

def test_bar_draws_a_rectangle_at_the_given_position_and_size():
    with new_builder_context() as builder:
        canvas(x_range=(-1, 5), y_range=(-1, 5))
        rect = bar(1, 0, width=2, height=3)
        ir = builder.build()
    rects = [d for d in ir.define if isinstance(d, PolygonDef)]
    assert len(rects) == 1
    assert rects[0].id == rect.id
    points_by_id = {d.id: d for d in ir.define if isinstance(d, PointFixed)}
    xs = sorted({points_by_id[pid].x for pid in rects[0].points})
    ys = sorted({points_by_id[pid].y for pid in rects[0].points})
    assert xs == pytest.approx([1.0, 3.0])
    assert ys == pytest.approx([0.0, 3.0])
    draws = [r for r in ir.render if isinstance(r, Draw) and r.obj == rect.id]
    assert len(draws) == 1


def test_bar_fills_when_fill_color_given():
    from geometry_diagrams.ir.ir import Fill

    with new_builder_context() as builder:
        canvas(x_range=(-1, 5), y_range=(-1, 5))
        rect = bar(0, 0, width=1, height=1, fill_color="blue", fill_opacity=0.5)
        ir = builder.build()
    fills = [r for r in ir.render if isinstance(r, Fill) and r.obj == rect.id]
    assert len(fills) == 1
    style = ir.styles[fills[0].style]
    assert style["color"] == "blue"
    assert fills[0].opacity == pytest.approx(0.5)


def test_bar_does_not_fill_when_no_fill_color_given():
    from geometry_diagrams.ir.ir import Fill

    with new_builder_context() as builder:
        canvas(x_range=(-1, 5), y_range=(-1, 5))
        bar(0, 0, width=1, height=1)
        ir = builder.build()
    assert [r for r in ir.render if isinstance(r, Fill)] == []


def test_bar_labels_at_centroid_when_label_given():
    from geometry_diagrams.ir.ir import LabelFreeText

    with new_builder_context() as builder:
        canvas(x_range=(-1, 5), y_range=(-1, 5))
        bar(0, 0, width=2, height=2, label="12")
        ir = builder.build()
    labels = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert len(labels) == 1
    assert labels[0].text == "12"


def test_bar_forwards_draw_style_kwargs():
    with new_builder_context() as builder:
        canvas(x_range=(-1, 5), y_range=(-1, 5))
        rect = bar(0, 0, width=1, height=1, color="red", thick=True)
        ir = builder.build()
    draws = [r for r in ir.render if isinstance(r, Draw) and r.obj == rect.id]
    style = ir.styles[draws[0].style]
    assert style["color"] == "red"
    assert style["thick"] is True


def test_bar_rejects_zero_width_or_height():
    with new_builder_context():
        canvas(x_range=(-1, 5), y_range=(-1, 5))
        with pytest.raises(ValueError):
            bar(0, 0, width=0, height=1)
        with pytest.raises(ValueError):
            bar(0, 0, width=1, height=0)


def test_bar_requires_a_builder():
    with pytest.raises(RuntimeError):
        bar(0, 0, width=1, height=1)


# --- bars ------------------------------------------------------------------

def test_bars_places_one_bar_per_value_vertical():
    with new_builder_context() as builder:
        canvas(x_range=(-1, 10), y_range=(-1, 10))
        rects = bars([2, 4, 3], x0=0, y0=0, bar_width=1, gap=0.5)
        ir = builder.build()
    assert len(rects) == 3
    points_by_id = {d.id: d for d in ir.define if isinstance(d, PointFixed)}
    rect_defs = {d.id: d for d in ir.define if isinstance(d, PolygonDef)}
    heights = []
    x_starts = []
    for r in rects:
        xs = [points_by_id[pid].x for pid in rect_defs[r.id].points]
        ys = [points_by_id[pid].y for pid in rect_defs[r.id].points]
        heights.append(max(ys) - min(ys))
        x_starts.append(min(xs))
    assert heights == pytest.approx([2, 4, 3])
    # bar_width=1, gap=0.5 => starts at 0, 1.5, 3.0
    assert x_starts == pytest.approx([0.0, 1.5, 3.0])


def test_bars_horizontal_orientation_stacks_along_y():
    with new_builder_context() as builder:
        canvas(x_range=(-1, 10), y_range=(-1, 10))
        rects = bars([2, 4], x0=0, y0=0, bar_width=1, gap=0.5, orientation="horizontal")
        ir = builder.build()
    points_by_id = {d.id: d for d in ir.define if isinstance(d, PointFixed)}
    rect_defs = {d.id: d for d in ir.define if isinstance(d, PolygonDef)}
    widths = []
    y_starts = []
    for r in rects:
        xs = [points_by_id[pid].x for pid in rect_defs[r.id].points]
        ys = [points_by_id[pid].y for pid in rect_defs[r.id].points]
        widths.append(max(xs) - min(xs))
        y_starts.append(min(ys))
    assert widths == pytest.approx([2, 4])
    assert y_starts == pytest.approx([0.0, 1.5])


def test_bars_labels_each_bar_when_labels_given():
    from geometry_diagrams.ir.ir import LabelFreeText

    with new_builder_context() as builder:
        canvas(x_range=(-1, 10), y_range=(-1, 10))
        bars([4, 4, 4], x0=0, y0=0, labels=["a", "b", "c"])
        ir = builder.build()
    labels = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert sorted(l.text for l in labels) == ["a", "b", "c"]


def test_bars_fills_every_bar_with_the_same_color():
    from geometry_diagrams.ir.ir import Fill

    with new_builder_context() as builder:
        canvas(x_range=(-1, 10), y_range=(-1, 10))
        bars([1, 2, 3], fill_color="green")
        ir = builder.build()
    fills = [r for r in ir.render if isinstance(r, Fill)]
    assert len(fills) == 3
    assert all(ir.styles[f.style]["color"] == "green" for f in fills)


def test_bars_rejects_empty_values():
    with new_builder_context():
        canvas(x_range=(-1, 10), y_range=(-1, 10))
        with pytest.raises(ValueError):
            bars([])


def test_bars_rejects_mismatched_labels_length():
    with new_builder_context():
        canvas(x_range=(-1, 10), y_range=(-1, 10))
        with pytest.raises(ValueError):
            bars([1, 2, 3], labels=["only one"])


def test_bars_rejects_bad_orientation():
    with new_builder_context():
        canvas(x_range=(-1, 10), y_range=(-1, 10))
        with pytest.raises(ValueError):
            bars([1, 2], orientation="diagonal")


# --- table_grid --------------------------------------------------------------

def test_table_grid_draws_interior_and_exterior_lines():
    with new_builder_context() as builder:
        canvas(x_range=(-1, 10), y_range=(-10, 1))
        table_grid(0, 0, col_widths=[2, 2, 2], row_heights=[1, 1])
        ir = builder.build()
    segment_ids = {d.id for d in ir.define if isinstance(d, SegmentDef)}
    draws = [r for r in ir.render if isinstance(r, Draw) and r.obj in segment_ids]
    # (3 cols => 4 vertical lines) + (2 rows => 3 horizontal lines) = 7
    assert len(draws) == 7


def test_table_grid_cell_extents_and_centers_for_uniform_grid():
    with new_builder_context():
        canvas(x_range=(-1, 10), y_range=(-10, 1))
        grid = table_grid(0, 0, col_widths=[2, 2], row_heights=[1, 1])
    assert grid.n_rows == 2
    assert grid.n_cols == 2
    top_left = grid.cell(0, 0)
    assert (top_left.x0, top_left.y0, top_left.x1, top_left.y1) == pytest.approx((0.0, 0.0, 2.0, -1.0))
    assert (top_left.cx, top_left.cy) == pytest.approx((1.0, -0.5))
    bottom_right = grid.cell(1, 1)
    assert (bottom_right.x0, bottom_right.y0, bottom_right.x1, bottom_right.y1) == pytest.approx((2.0, -1.0, 4.0, -2.0))
    assert (bottom_right.cx, bottom_right.cy) == pytest.approx((3.0, -1.5))


def test_table_grid_supports_variable_column_widths_and_row_heights():
    with new_builder_context():
        canvas(x_range=(-1, 20), y_range=(-10, 1))
        grid = table_grid(5, 5, col_widths=[1, 3, 2], row_heights=[2, 1])
    # col 0: [5, 6), col 1: [6, 9), col 2: [9, 11)
    assert grid.cell(0, 1).x0 == pytest.approx(6.0)
    assert grid.cell(0, 1).x1 == pytest.approx(9.0)
    assert grid.cell(0, 2).x0 == pytest.approx(9.0)
    assert grid.cell(0, 2).x1 == pytest.approx(11.0)
    # row 0: [5, 3), row 1: [3, 2) (top at y0=5, dropping by row_heights)
    assert grid.cell(0, 0).y0 == pytest.approx(5.0)
    assert grid.cell(0, 0).y1 == pytest.approx(3.0)
    assert grid.cell(1, 0).y0 == pytest.approx(3.0)
    assert grid.cell(1, 0).y1 == pytest.approx(2.0)


def test_table_grid_cells_tile_without_gaps_or_overlaps():
    with new_builder_context():
        canvas(x_range=(-1, 20), y_range=(-10, 1))
        grid = table_grid(0, 0, col_widths=[1, 2, 3], row_heights=[1, 2, 1])
    for r in range(grid.n_rows):
        for c in range(grid.n_cols - 1):
            assert grid.cell(r, c).x1 == pytest.approx(grid.cell(r, c + 1).x0)
    for c in range(grid.n_cols):
        for r in range(grid.n_rows - 1):
            assert grid.cell(r, c).y1 == pytest.approx(grid.cell(r + 1, c).y0)


def test_table_grid_rejects_empty_widths_or_heights():
    with new_builder_context():
        canvas(x_range=(-1, 10), y_range=(-10, 1))
        with pytest.raises(ValueError):
            table_grid(0, 0, col_widths=[], row_heights=[1])
        with pytest.raises(ValueError):
            table_grid(0, 0, col_widths=[1], row_heights=[])


def test_table_grid_rejects_non_positive_dimensions():
    with new_builder_context():
        canvas(x_range=(-1, 10), y_range=(-10, 1))
        with pytest.raises(ValueError):
            table_grid(0, 0, col_widths=[1, 0], row_heights=[1])
        with pytest.raises(ValueError):
            table_grid(0, 0, col_widths=[1], row_heights=[1, -1])


def test_table_grid_requires_a_builder():
    with pytest.raises(RuntimeError):
        table_grid(0, 0, col_widths=[1], row_heights=[1])


def test_table_grid_forwards_draw_style_kwargs():
    with new_builder_context() as builder:
        canvas(x_range=(-1, 10), y_range=(-10, 1))
        table_grid(0, 0, col_widths=[1], row_heights=[1], color="blue", thick=True)
        ir = builder.build()
    segment_ids = {d.id for d in ir.define if isinstance(d, SegmentDef)}
    draws = [r for r in ir.render if isinstance(r, Draw) and r.obj in segment_ids]
    assert draws
    style = ir.styles[draws[0].style]
    assert style["color"] == "blue"
    assert style["thick"] is True


# --- end-to-end sandbox wiring (the ticket 08 gotcha, for real) --------------

def test_cookbook_helpers_unreachable_in_sandbox_without_the_flag():
    script = "canvas(x_range=(-1, 5), y_range=(-1, 5))\nunit_grid(0, 0, 2, 2)\n"
    result = run_script(script, enable_cookbook=False)
    assert result.error is not None


def test_cookbook_helpers_reachable_in_real_sandbox_with_flag_enabled():
    """Runs an actual script through the real subprocess sandbox (not a
    mock, not a direct Python call) with enable_cookbook=True, using all
    six cookbook helpers together (ticket 09's three, ticket 10's
    bar/bars, and ticket 11's table_grid) — this is what would have raised
    AttributeError if COOKBOOK_NAMES had been updated without also
    re-exporting the functions from pydsl/__init__.py."""
    script = """
canvas(x_range=(-1, 10), y_range=(-10, 6))
unit_grid(0, 0, cols=3, rows=3)
shapes = array_of(4, shape="circle", cols=2, origin=(0, -4))
a = point(0, 3)
b = point(6, 3)
tick_marks(a, b, n=4)
single = bar(0, -5, width=1, height=1, fill_color="orange", label="1")
series = bars([1, 2, 3], x0=2, y0=-5, bar_width=0.8, fill_color="teal", labels=["a", "b", "c"])
grid = table_grid(0, -9, col_widths=[1.5, 1.5], row_heights=[1, 1])
label_text("A", at=(grid.cell(0, 0).cx, grid.cell(0, 0).cy))
label_text("B", at=(grid.cell(1, 1).cx, grid.cell(1, 1).cy))
"""
    result = run_script(script, timeout_seconds=10.0, enable_cookbook=True)
    assert result.error is None, result.error
    assert result.diagram_ir is not None


def test_bar_and_bars_unreachable_in_sandbox_without_the_flag():
    script = "canvas(x_range=(-1, 5), y_range=(-1, 5))\nbar(0, 0, width=1, height=1)\n"
    result = run_script(script, enable_cookbook=False)
    assert result.error is not None


def test_table_grid_unreachable_in_sandbox_without_the_flag():
    script = "canvas(x_range=(-1, 5), y_range=(-1, 5))\ntable_grid(0, 0, col_widths=[1], row_heights=[1])\n"
    result = run_script(script, enable_cookbook=False)
    assert result.error is not None
