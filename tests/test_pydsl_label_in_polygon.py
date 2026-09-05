# tests/test_pydsl_label_in_polygon.py
"""Tests for label_in_polygon() core (ticket 01 of the label-in-polygon
feature): the interior-point search (convex short-circuit + concave grid
search), the width-budget estimate, and the overflow="raise" path.

overflow="wrap" (ticket 02) is implemented and tested below (word-wrap
helper in isolation, plus an end-to-end rendered-output check).
overflow="shrink" (ticket 03) is NOT implemented here — see the
NotImplementedError stub in api.py's overflow dispatch, tested below only
insofar as it raises (not that it works)."""
import pytest

from geometry_diagrams.ir.ir import LabelFreeText
from geometry_diagrams.pydsl.api import (
    _estimate_text_width_construction_units,
    _grid_search_interior_point,
    _horizontal_ray_width,
    _polygon_interior_point,
    _sympy_polygon,
    _width_budget_at,
    _wrap_latex_safe_words,
    _wrap_text_to_width,
    label_in_polygon,
    point,
    polygon,
)
from geometry_diagrams.pydsl.builder import new_builder_context


def _rect_vertices_xy(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


# ---------------------------------------------------------------------------
# Seam (a): interior-point search — convex short-circuit
# ---------------------------------------------------------------------------

def test_convex_polygon_short_circuits_to_centroid_without_grid_search(monkeypatch):
    vertices_xy = _rect_vertices_xy(0.0, 0.0, 4.0, 2.0)
    sym_poly = _sympy_polygon(vertices_xy)
    assert sym_poly.is_convex()

    def _boom(*args, **kwargs):
        raise AssertionError("grid search must not run for a convex polygon")

    monkeypatch.setattr("geometry_diagrams.pydsl.api._grid_search_interior_point", _boom)

    x, y, clearance = _polygon_interior_point(sym_poly, vertices_xy)
    c = sym_poly.centroid
    assert x == pytest.approx(float(c.x))
    assert y == pytest.approx(float(c.y))
    assert clearance > 0.0


# ---------------------------------------------------------------------------
# Seam (a): interior-point search — concave polygon (grid search)
# ---------------------------------------------------------------------------

def _u_shape_vertices_xy():
    # A "U" / staple shape whose plain centroid falls in the notch, outside
    # the polygon -- unlike a rectangle or other convex shape, where the
    # centroid already works and this feature would add nothing.
    return [(0, 0), (10, 0), (10, 10), (7, 10), (7, 3), (3, 3), (3, 10), (0, 10)]


def test_u_shape_is_concave_and_its_plain_centroid_falls_outside():
    vertices_xy = _u_shape_vertices_xy()
    sym_poly = _sympy_polygon(vertices_xy)
    assert not sym_poly.is_convex()
    c = sym_poly.centroid
    assert not sym_poly.encloses_point(c)


def test_grid_search_finds_a_genuinely_interior_point_for_concave_polygon():
    vertices_xy = _u_shape_vertices_xy()
    sym_poly = _sympy_polygon(vertices_xy)

    x, y, clearance = _grid_search_interior_point(sym_poly, vertices_xy)

    assert sym_poly.encloses_point((x, y))
    assert clearance > 0.0


def test_polygon_interior_point_dispatches_to_grid_search_for_concave_polygon():
    vertices_xy = _u_shape_vertices_xy()
    sym_poly = _sympy_polygon(vertices_xy)

    x, y, clearance = _polygon_interior_point(sym_poly, vertices_xy)

    # Must be a real interior point -- the whole point of this feature over
    # a plain centroid, which we already showed lands outside this shape.
    assert sym_poly.encloses_point((x, y))
    assert clearance > 0.0


# ---------------------------------------------------------------------------
# Seam (c): width-budget estimate
# ---------------------------------------------------------------------------

def test_width_budget_uses_horizontal_ray_cast_tighter_than_two_times_clearance():
    # A wide, short rectangle -- exactly the shape this feature is motivated
    # by. Centroid clearance is 20 (half the height), giving a naive
    # 2*clearance budget of 40 against 60 of real horizontal room.
    vertices_xy = _rect_vertices_xy(0.0, 0.0, 60.0, 40.0)
    sym_poly = _sympy_polygon(vertices_xy)
    x, y, clearance = _polygon_interior_point(sym_poly, vertices_xy)
    assert clearance == pytest.approx(20.0)

    budget = _width_budget_at(vertices_xy, (x, y), clearance)

    assert budget > 2.0 * clearance
    assert budget == pytest.approx(60.0)


def test_horizontal_ray_width_matches_full_run_through_point():
    vertices_xy = _rect_vertices_xy(0.0, 0.0, 60.0, 40.0)
    run = _horizontal_ray_width(vertices_xy, (30.0, 20.0))
    assert run == pytest.approx(60.0)


def test_text_width_estimate_is_construction_units_not_svg_pixels():
    from geometry_diagrams.pydsl.api import _EQUATION_STEPS_CHAR_WIDTH

    text = "hello world"
    assert _estimate_text_width_construction_units(text) == pytest.approx(
        len(text) * _EQUATION_STEPS_CHAR_WIDTH
    )


# ---------------------------------------------------------------------------
# Seam (d)/(e): label_in_polygon() end to end -- fits vs overflow="raise"
# ---------------------------------------------------------------------------

def test_label_in_polygon_places_single_label_when_text_fits():
    with new_builder_context() as builder:
        p1 = point(0.0, 0.0)
        p2 = point(60.0, 0.0)
        p3 = point(60.0, 40.0)
        p4 = point(0.0, 40.0)
        poly = polygon(p1, p2, p3, p4)
        label_in_polygon(poly, "hi", overflow="raise")
        ir = builder.build()

    labels = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert len(labels) == 1
    assert labels[0].text == "hi"
    assert labels[0].at == pytest.approx([30.0, 20.0])


def test_label_in_polygon_overflow_raise_raises_when_text_does_not_fit():
    with new_builder_context():
        p1 = point(0.0, 0.0)
        p2 = point(2.0, 0.0)
        p3 = point(2.0, 1.0)
        p4 = point(0.0, 1.0)
        poly = polygon(p1, p2, p3, p4)
        with pytest.raises(ValueError):
            label_in_polygon(
                poly,
                "a very long label that cannot possibly fit in this tiny box",
                overflow="raise",
            )


def test_label_in_polygon_overflow_raise_does_not_raise_when_text_fits():
    with new_builder_context() as builder:
        p1 = point(0.0, 0.0)
        p2 = point(60.0, 0.0)
        p3 = point(60.0, 40.0)
        p4 = point(0.0, 40.0)
        poly = polygon(p1, p2, p3, p4)
        # Should not raise.
        label_in_polygon(poly, "fits", overflow="raise")
        ir = builder.build()
    labels = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert len(labels) == 1


def test_label_in_polygon_places_real_interior_point_for_concave_polygon():
    # An L-shape (a concave polygon) built from real point() handles, going
    # through the full label_in_polygon() call (not the internal helpers
    # directly) -- proves the end-to-end path also gets a genuine interior
    # point, not the polygon's plain centroid.
    with new_builder_context() as builder:
        pts = [
            point(0.0, 0.0), point(4.0, 0.0), point(4.0, 2.0),
            point(2.0, 2.0), point(2.0, 4.0), point(0.0, 4.0),
        ]
        poly = polygon(*pts)
        label_in_polygon(poly, "L", overflow="raise")
        ir = builder.build()

    labels = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert len(labels) == 1
    lx, ly = labels[0].at
    sym_poly = _sympy_polygon([(p.x, p.y) for p in pts])
    assert sym_poly.encloses_point((lx, ly))


def test_label_in_polygon_rejects_unknown_overflow_value():
    with new_builder_context():
        p1 = point(0.0, 0.0)
        p2 = point(4.0, 0.0)
        p3 = point(4.0, 4.0)
        p4 = point(0.0, 4.0)
        poly = polygon(p1, p2, p3, p4)
        with pytest.raises(ValueError):
            label_in_polygon(poly, "x", overflow="bogus")


# ---------------------------------------------------------------------------
# Seam (b): word-wrap helper, in isolation
# ---------------------------------------------------------------------------

def test_wrap_latex_safe_words_splits_plain_text_on_whitespace():
    words = _wrap_latex_safe_words("a very long label that cannot possibly fit")
    assert words == ["a", "very", "long", "label", "that", "cannot", "possibly", "fit"]


def test_wrap_latex_safe_words_keeps_braced_command_atomic_even_with_internal_space():
    # \text{...} (and any other braced command) may contain internal
    # whitespace -- that space must NOT become a wrap point.
    words = _wrap_latex_safe_words(r"before \text{hello world} after")
    assert words == ["before", r"\text{hello world}", "after"]


def test_wrap_latex_safe_words_keeps_frac_atomic():
    words = _wrap_latex_safe_words(r"see \frac{1}{2} here")
    assert words == ["see", r"\frac{1}{2}", "here"]


def test_wrap_text_to_width_breaks_long_plain_string_into_lines_that_each_fit():
    text = " ".join(["word"] * 20)
    budget = _estimate_text_width_construction_units("word word word")  # ~3 words per line
    lines = _wrap_text_to_width(text, budget)
    assert len(lines) > 1
    for line in lines:
        assert _estimate_text_width_construction_units(line) <= budget


def test_wrap_text_to_width_reassembles_to_original_words_in_order():
    text = " ".join(["word"] * 20)
    budget = _estimate_text_width_construction_units("word word word")
    lines = _wrap_text_to_width(text, budget)
    assert " ".join(lines).split() == text.split()


def test_wrap_text_to_width_never_splits_a_frac_token_mid_command():
    text = r"a b c \frac{1}{2} d e f g h i j k l m n o p"
    budget = _estimate_text_width_construction_units("a b c")
    lines = _wrap_text_to_width(text, budget)
    joined = " ".join(lines)
    assert r"\frac{1}{2}" in joined
    # The token must appear whole on some single line, never straddling two.
    assert any(r"\frac{1}{2}" in line for line in lines)
    for line in lines:
        # Never a partial fragment like "\frac{1}{2" or "}" on its own from
        # a split token.
        assert "\\frac{1}{2" not in line or r"\frac{1}{2}" in line


def test_wrap_text_to_width_single_short_string_returns_one_line():
    lines = _wrap_text_to_width("hi", 100.0)
    assert lines == ["hi"]


# ---------------------------------------------------------------------------
# Seam (d): label_in_polygon() end to end -- overflow="wrap"
# ---------------------------------------------------------------------------

def test_label_in_polygon_overflow_wrap_produces_stacked_lines_that_each_fit():
    with new_builder_context() as builder:
        p1 = point(0.0, 0.0)
        p2 = point(2.0, 0.0)
        p3 = point(2.0, 1.0)
        p4 = point(0.0, 1.0)
        poly = polygon(p1, p2, p3, p4)
        text = "a very long label that cannot possibly fit in this tiny box"
        label_in_polygon(poly, text, overflow="wrap")
        ir = builder.build()

    labels = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert len(labels) > 1
    # Reassembling the wrapped lines' words reproduces the original text.
    assert " ".join(l.text for l in labels).split() == text.split()

    # Each individual line must fit the same width budget label_in_polygon()
    # computed internally.
    vertices_xy = [(0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (0.0, 1.0)]
    sym_poly = _sympy_polygon(vertices_xy)
    x, y, clearance = _polygon_interior_point(sym_poly, vertices_xy)
    budget = _width_budget_at(vertices_xy, (x, y), clearance)
    for l in labels:
        # A line with more than one word must fit the budget; a lone word
        # is allowed to exceed it since it can't be split further (accepted
        # per _wrap_text_to_width()'s docstring).
        if " " in l.text:
            assert _estimate_text_width_construction_units(l.text) <= budget

    # Anchored at the interior point's x/y, not the origin.
    assert labels[0].at[0] == pytest.approx(x)
    assert labels[0].at[1] == pytest.approx(y)


def test_label_in_polygon_overflow_wrap_renders_multiple_label_free_text_ops():
    # Real rendered-output check (not just "didn't crash"): compile and
    # render through the SVGRenderer, confirm every wrapped line actually
    # made it into the rendered SVG.
    from geometry_diagrams.ir.to_sympy import compile_defs
    from geometry_diagrams.ir.renderer import SVGRenderer

    with new_builder_context() as builder:
        p1 = point(0.0, 0.0)
        p2 = point(2.0, 0.0)
        p3 = point(2.0, 1.0)
        p4 = point(0.0, 1.0)
        poly = polygon(p1, p2, p3, p4)
        text = "a very long label that cannot possibly fit in this tiny box"
        label_in_polygon(poly, text, overflow="wrap")
        ir = builder.build()
        # label_in_polygon()/stack_lines() do not call canvas() -- the
        # calling script must, same contract as stack_lines() documents.
        from geometry_diagrams.pydsl.api import canvas

        canvas(x_range=(-10.0, 10.0), y_range=(-10.0, 10.0))
        ir = builder.build()

    labels = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert len(labels) > 1

    sym = compile_defs(ir)
    svg = SVGRenderer().render(ir, sym).output
    assert svg.count('data-role="label-free-text"') == len(labels)


def test_label_in_polygon_overflow_shrink_is_not_yet_implemented():
    with new_builder_context():
        p1 = point(0.0, 0.0)
        p2 = point(2.0, 0.0)
        p3 = point(2.0, 1.0)
        p4 = point(0.0, 1.0)
        poly = polygon(p1, p2, p3, p4)
        with pytest.raises(NotImplementedError):
            label_in_polygon(
                poly,
                "a very long label that cannot possibly fit in this tiny box",
                overflow="shrink",
            )


def test_label_in_polygon_accepts_a_triangle_handle():
    from geometry_diagrams.pydsl.api import triangle

    with new_builder_context() as builder:
        p1 = point(0.0, 0.0)
        p2 = point(60.0, 0.0)
        p3 = point(30.0, 40.0)
        tri = triangle(p1, p2, p3)
        label_in_polygon(tri, "tri", overflow="raise")
        ir = builder.build()

    labels = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert len(labels) == 1


def test_label_in_polygon_is_exported_ungated_in_pydsl_all():
    import geometry_diagrams.pydsl as pydsl_module

    assert "label_in_polygon" in pydsl_module.__all__
    assert pydsl_module.label_in_polygon is label_in_polygon


def test_label_in_polygon_appears_in_generated_stub_with_no_flag_required():
    from geometry_diagrams.pydsl.stub import generate_stub

    stub = generate_stub()
    assert "def label_in_polygon(" in stub
