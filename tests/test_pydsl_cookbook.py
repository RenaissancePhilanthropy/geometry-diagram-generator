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
from geometry_diagrams.pydsl.cookbook import array_of, tick_marks, unit_grid
from geometry_diagrams.pydsl.sandbox import run_script


def test_cookbook_names_lists_the_three_ticket_09_helpers():
    assert pydsl_module.COOKBOOK_NAMES == ["unit_grid", "array_of", "tick_marks"]


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


# --- end-to-end sandbox wiring (the ticket 08 gotcha, for real) --------------

def test_cookbook_helpers_unreachable_in_sandbox_without_the_flag():
    script = "canvas(x_range=(-1, 5), y_range=(-1, 5))\nunit_grid(0, 0, 2, 2)\n"
    result = run_script(script, enable_cookbook=False)
    assert result.error is not None


def test_cookbook_helpers_reachable_in_real_sandbox_with_flag_enabled():
    """Runs an actual script through the real subprocess sandbox (not a
    mock, not a direct Python call) with enable_cookbook=True, using all
    three new helpers together — this is what would have raised
    AttributeError if COOKBOOK_NAMES had been updated without also
    re-exporting the functions from pydsl/__init__.py."""
    script = """
canvas(x_range=(-1, 10), y_range=(-6, 6))
unit_grid(0, 0, cols=3, rows=3)
shapes = array_of(4, shape="circle", cols=2, origin=(0, -4))
a = point(0, 3)
b = point(6, 3)
tick_marks(a, b, n=4)
"""
    result = run_script(script, timeout_seconds=10.0, enable_cookbook=True)
    assert result.error is None, result.error
    assert result.diagram_ir is not None
