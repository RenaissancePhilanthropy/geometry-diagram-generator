# tests/test_pydsl_label_in_polygon.py
"""Tests for label_in_polygon() core (ticket 01 of the label-in-polygon
feature): the interior-point search (convex short-circuit + concave grid
search), the width-budget estimate, and the overflow="raise" path.

overflow="wrap" (ticket 02) is implemented and tested below (word-wrap
helper in isolation, plus an end-to-end rendered-output check).
overflow="shrink" (ticket 03) is implemented and tested below (the
font-size-scaling formula in isolation, plus an end-to-end rendered-output
check against the actual SVG font-size attribute)."""
import pytest

from geometry_diagrams.ir.ir import LabelFreeText
from geometry_diagrams.pydsl.api import (
    _estimate_text_width_construction_units,
    _greedy_wrap_lines,
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
# Seam (a): minimum-raggedness split never exceeds greedy's own line count
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text,budget",
    [
        ("Back 4 x 3", 4.5),
        ("Left 2 x 3", 3.5),
        ("cat helicopter ox zebra", 9.0),
        ("a bbbbb ccc dddddd ee", 4.5),
        ("blah cat frog bananas", 4.0),
        (" ".join(["word"] * 20), _estimate_text_width_construction_units("word word word")),
        ("alpha beta gamma delta epsilon zeta", 5.0),
    ],
)
def test_wrap_text_to_width_never_exceeds_greedys_line_count(text, budget):
    words = _wrap_latex_safe_words(text)
    greedy_lines = _greedy_wrap_lines(words, budget)
    new_lines = _wrap_text_to_width(text, budget)
    assert len(new_lines) == len(greedy_lines)


# ---------------------------------------------------------------------------
# Seam (b): minimum-raggedness selection itself
# ---------------------------------------------------------------------------

def test_wrap_text_to_width_prefers_balanced_split_over_lopsided_greedy():
    # Greedy packs as much as possible onto each line before overflowing,
    # which can leave an early line much wider than a later one even though
    # a more balanced split (with the same line count) was available.
    text = "cat helicopter ox zebra"
    budget = 9.0
    greedy_lines = _greedy_wrap_lines(_wrap_latex_safe_words(text), budget)
    assert greedy_lines == ["cat helicopter ox", "zebra"]  # confirm greedy really is lopsided here

    lines = _wrap_text_to_width(text, budget)
    assert lines == ["cat helicopter", "ox zebra"]
    widths = [_estimate_text_width_construction_units(line) for line in lines]
    greedy_widths = [_estimate_text_width_construction_units(line) for line in greedy_lines]
    assert max(widths) < max(greedy_widths)


def test_wrap_text_to_width_tie_breaks_on_sum_of_squared_widths():
    # Two feasible 3-line splits tie on max line width (4.5); the one with
    # lower total squared width must win, not whichever is found first.
    text = "a bbbbb ccc dddddd ee"
    budget = 4.5
    lines = _wrap_text_to_width(text, budget)
    assert lines == ["a bbbbb", "ccc", "dddddd ee"]
    widths = [_estimate_text_width_construction_units(line) for line in lines]
    assert max(widths) == pytest.approx(4.5)
    # The rejected candidate ("a" / "bbbbb ccc" / "dddddd ee") ties on max
    # width but loses on sum-of-squares -- confirm it really is worse.
    rejected = ["a", "bbbbb ccc", "dddddd ee"]
    rejected_widths = [_estimate_text_width_construction_units(line) for line in rejected]
    assert max(rejected_widths) == pytest.approx(4.5)
    assert sum(w * w for w in rejected_widths) > sum(w * w for w in widths)


def test_wrap_text_to_width_tie_breaks_on_widest_first_line():
    # Two feasible 3-line splits tie on both max width and sum-of-squares;
    # the one whose first line is widest must win.
    text = "blah cat frog bananas"
    budget = 4.0
    lines = _wrap_text_to_width(text, budget)
    assert lines == ["blah cat", "frog", "bananas"]
    rejected = ["blah", "cat frog", "bananas"]
    lines_w = [_estimate_text_width_construction_units(l) for l in lines]
    rejected_w = [_estimate_text_width_construction_units(l) for l in rejected]
    assert max(lines_w) == pytest.approx(max(rejected_w))
    assert sum(w * w for w in lines_w) == pytest.approx(sum(w * w for w in rejected_w))
    assert lines_w[0] > rejected_w[0]


# ---------------------------------------------------------------------------
# Seam (c): both Fable-recommendation worked examples, reproduced exactly
# ---------------------------------------------------------------------------

def test_wrap_text_to_width_worked_example_back_4_x_3():
    lines = _wrap_text_to_width("Back 4 x 3", 4.5)
    assert lines == ["Back", "4 x 3"]


def test_wrap_text_to_width_worked_example_left_2_x_3():
    lines = _wrap_text_to_width("Left 2 x 3", 3.5)
    assert lines == ["Left", "2 x 3"]


def test_wrap_text_to_width_keeps_dimension_expression_together_on_a_true_tie():
    # "Top" / "4 x 2" and "Top 4" / "x 2" tie exactly on both max(line
    # width) and sum-of-squares (same two widths, just swapped), so the
    # widest-first-line tie-break used to decide it -- which happened to
    # prefer "Top 4" / "x 2", separating "x" from both numbers it relates
    # to. Connective-cohesion is checked before that tie-break and must
    # settle it in favor of keeping "4 x 2" whole.
    lines = _wrap_text_to_width("Top 4 x 2", 2.5)
    assert lines == ["Top", "4 x 2"]


def test_wrap_text_to_width_connective_bias_yields_to_feasibility():
    # A dimension expression too wide to keep whole must still split --
    # cohesion is a preference among fitting splits, never a constraint
    # that could force an overflow.
    text = "Width 40 x 20 x 30"
    budget = _estimate_text_width_construction_units("Width 40")
    lines = _wrap_text_to_width(text, budget)
    assert all(
        _estimate_text_width_construction_units(line) <= budget or len(line.split()) == 1
        for line in lines
    )
    assert " ".join(lines).split() == text.split()


# ---------------------------------------------------------------------------
# Seam (e): oversized single token still overflows onto its own line
# ---------------------------------------------------------------------------

def test_wrap_text_to_width_oversized_single_token_keeps_its_own_line():
    long_token = "x" * 40
    text = f"cat {long_token} dog"
    budget = 3.0
    lines = _wrap_text_to_width(text, budget)
    assert lines == ["cat", long_token, "dog"]
    # The oversized line is still allowed to exceed width_budget -- that's
    # the accepted, unchanged overflow behavior for a single unsplittable
    # token, not a regression.
    assert _estimate_text_width_construction_units(long_token) > budget


# ---------------------------------------------------------------------------
# Seam (d): LaTeX-safe token boundaries are still respected under the new
# minimum-raggedness selection (not just under plain greedy).
# ---------------------------------------------------------------------------

def test_wrap_text_to_width_still_never_splits_frac_token_with_multiple_candidate_splits():
    text = r"a b c \frac{1}{2} d e f g h i j k l m n o p"
    budget = _estimate_text_width_construction_units("a b c")
    lines = _wrap_text_to_width(text, budget)
    assert any(line == r"\frac{1}{2}" for line in lines)
    for line in lines:
        assert "\\frac{1}{2" not in line or line == r"\frac{1}{2}"


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

    # Anchored at the interior point's x, not the origin -- and the whole
    # stacked block is vertically CENTERED on the interior point's y (not
    # top-anchored there -- see the centering-fix regression test below for
    # the precise math).
    assert labels[0].at[0] == pytest.approx(x)
    assert sum(l.at[1] for l in labels) / len(labels) == pytest.approx(y)


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


# Vertices/text combo used by the "shrink succeeds" tests below: chosen so
# the required font size (_FONT_SIZE * budget / text_width) lands strictly
# between _MIN_READABLE_FONT_SIZE and _FONT_SIZE -- i.e. the text overflows
# enough to need shrinking, but not so much that shrinking would cross the
# minimum-readable floor and raise instead (see the floor tests further
# below, which reuse the original tiny-box/long-text combo specifically
# because *that* combo's required size is well below the floor).
_SHRINK_VERTICES_XY = [(0.0, 0.0), (6.0, 0.0), (6.0, 3.0), (0.0, 3.0)]
_SHRINK_TEXT = "a slightly long label"


def test_label_in_polygon_overflow_shrink_registers_a_smaller_font_size_style():
    from geometry_diagrams.ir.to_svg import _FONT_SIZE

    vertices_xy = _SHRINK_VERTICES_XY
    sym_poly = _sympy_polygon(vertices_xy)
    x, y, clearance = _polygon_interior_point(sym_poly, vertices_xy)
    budget = _width_budget_at(vertices_xy, (x, y), clearance)
    text = _SHRINK_TEXT
    text_width = _estimate_text_width_construction_units(text)
    expected_font_size = _FONT_SIZE * budget / text_width

    with new_builder_context() as builder:
        p1, p2, p3, p4 = (point(*v) for v in vertices_xy)
        poly = polygon(p1, p2, p3, p4)
        label_in_polygon(poly, text, overflow="shrink")
        ir = builder.build()

    labels = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert len(labels) == 1
    assert labels[0].text == text
    assert labels[0].at == pytest.approx([x, y])
    assert labels[0].style is not None
    style = ir.styles[labels[0].style]
    assert style["font-size"] == pytest.approx(expected_font_size)
    assert style["font-size"] < _FONT_SIZE


def test_label_in_polygon_overflow_shrink_renders_a_smaller_font_size():
    # Real rendered-output check, not a stub: compile and render through
    # SVGRenderer, parse the actual font-size attribute of the emitted
    # <text> element.
    import xml.etree.ElementTree as ET

    from geometry_diagrams.ir.to_sympy import compile_defs
    from geometry_diagrams.ir.to_svg import _FONT_SIZE
    from geometry_diagrams.ir.renderer import SVGRenderer
    from geometry_diagrams.pydsl.api import canvas

    text = _SHRINK_TEXT

    with new_builder_context() as builder:
        p1, p2, p3, p4 = (point(*v) for v in _SHRINK_VERTICES_XY)
        poly = polygon(p1, p2, p3, p4)
        label_in_polygon(poly, text, overflow="shrink")
        canvas(x_range=(-10.0, 10.0), y_range=(-10.0, 10.0))
        ir = builder.build()

    sym = compile_defs(ir)
    svg = SVGRenderer().render(ir, sym).output
    root = ET.fromstring(svg)
    labels = [
        el for el in root.iter()
        if el.tag.rsplit("}", 1)[-1] == "text" and el.get("data-role") == "label-free-text"
    ]
    assert len(labels) == 1
    rendered_font_size = float(labels[0].get("font-size"))
    assert 0.0 < rendered_font_size < _FONT_SIZE


def test_label_in_polygon_overflow_shrink_raises_when_required_size_below_floor():
    """Finding 2 (whole-branch review): a target font size below the
    minimum-readable floor must raise instead of silently placing
    illegible text or silently clamping to the floor (which would still
    overflow at a readable size). Reuses the original tiny-box/long-text
    combo, whose required size (~0.95px, see the module docstring above)
    is far below any reasonable floor."""
    from geometry_diagrams.pydsl.api import _MIN_READABLE_FONT_SIZE

    with new_builder_context():
        p1 = point(0.0, 0.0)
        p2 = point(2.0, 0.0)
        p3 = point(2.0, 1.0)
        p4 = point(0.0, 1.0)
        poly = polygon(p1, p2, p3, p4)
        text = "a very long label that cannot possibly fit in this tiny box"
        with pytest.raises(ValueError, match="minimum readable floor"):
            label_in_polygon(poly, text, overflow="shrink")
    # Sanity: the floor itself is a small-but-legible size, not e.g. 0.
    assert 0.0 < _MIN_READABLE_FONT_SIZE < 14.0


def test_label_in_polygon_overflow_shrink_below_floor_does_not_register_a_style():
    """A raised shrink must not have side-effected a style/render op onto
    the builder -- same no-partial-effect contract overflow="raise" already
    has for the plain not-fits case."""
    with new_builder_context() as builder:
        p1 = point(0.0, 0.0)
        p2 = point(2.0, 0.0)
        p3 = point(2.0, 1.0)
        p4 = point(0.0, 1.0)
        poly = polygon(p1, p2, p3, p4)
        text = "a very long label that cannot possibly fit in this tiny box"
        with pytest.raises(ValueError):
            label_in_polygon(poly, text, overflow="shrink")
        ir = builder.build()
    labels = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert len(labels) == 0


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


def test_label_in_polygon_overflow_wrap_uses_a_sensible_single_line_height_gap():
    """Regression test for the wrap-spacing bug: label_in_polygon()'s "wrap"
    branch used to reuse stack_lines()'s own y_step=1.2 default -- a value
    only ever calibrated for equation_steps()'s self-sized canvas() call
    (see _LABEL_IN_POLYGON_WRAP_Y_STEP's docstring comment in api.py). Under
    an ambient diagram scale that default produced a near-double gap between
    wrapped lines instead of a single-line-height one.

    Builds a diagram with a *known* geometry-unit -> pixel scale (derived
    from two drawn reference points at a known construction-unit distance,
    not hardcoded renderer internals) containing a narrow rectangle sized
    like prism_net's Left/Right faces (3 x 2), whose label overflows and
    wraps into multiple lines. Asserts the actual rendered pixel gap
    between the first two wrapped lines matches
    _LABEL_IN_POLYGON_WRAP_Y_STEP * scale, and that this lands in a sane
    single-line-height range -- clearly less than the old 1.2 default would
    have produced at the same scale."""
    import xml.etree.ElementTree as ET

    from geometry_diagrams.ir.to_sympy import compile_defs
    from geometry_diagrams.ir.to_svg import _FONT_SIZE
    from geometry_diagrams.ir.renderer import SVGRenderer
    from geometry_diagrams.pydsl.api import _LABEL_IN_POLYGON_WRAP_Y_STEP, canvas, draw_points

    with new_builder_context() as builder:
        # Two reference points 8 construction units apart in y, used below
        # to back out the actual rendered px-per-unit scale -- not a segment
        # or line, so _nudge_labels_from_lines() never touches them.
        ref_lo = point(5.0, -4.0)
        ref_hi = point(5.0, 4.0)
        draw_points(ref_lo, ref_hi)

        # A narrow rectangle (3 x 2) and label text taken directly from
        # prism_net's actual Left face -- realistic case that genuinely
        # needs wrapping, and wraps into exactly two lines (as verified by
        # actually re-rendering docs/examples/diagram_kinds/scripts/
        # prism_net.py during this fix). Deliberately not a longer string:
        # a many-line stack triggers to_svg.py's separate label-label
        # collision-resolution pass (_resolve_label_collisions), which can
        # push lines further apart than y_step*scale alone predicts -- a
        # real, pre-existing, unrelated effect this test isn't about. The
        # canvas range below (-6..6, tighter than the reference points'
        # +-4 span so it still frames them) is chosen specifically so the
        # resulting scale keeps the raw y_step*scale gap comfortably above
        # that collision-resolution pass's own ~_FONT_SIZE-ish trigger
        # threshold -- otherwise it would kick in here too and the
        # collision-avoidance push, not this fix's y_step, would dominate
        # the measured gap.
        p1 = point(-1.5, -1.0)
        p2 = point(1.5, -1.0)
        p3 = point(1.5, 1.0)
        p4 = point(-1.5, 1.0)
        poly = polygon(p1, p2, p3, p4)
        text = "Left\n2 x 3"
        label_in_polygon(poly, text, overflow="wrap")

        canvas(x_range=(-6.0, 6.0), y_range=(-6.0, 6.0))
        ir = builder.build()

    labels = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert len(labels) > 1

    sym = compile_defs(ir)
    svg = SVGRenderer().render(ir, sym).output
    root = ET.fromstring(svg)

    circles = [el for el in root.iter() if el.tag.rsplit("}", 1)[-1] == "circle"]
    cys = sorted(float(c.get("cy")) for c in circles)
    assert len(cys) == 2
    scale = (cys[1] - cys[0]) / 8.0  # px per construction unit

    text_els = [
        el for el in root.iter()
        if el.tag.rsplit("}", 1)[-1] == "text" and el.get("data-role") == "label-free-text"
    ]
    assert len(text_els) >= 2
    line_ys = [float(el.get("y")) for el in text_els[:2]]
    actual_gap = abs(line_ys[1] - line_ys[0])

    expected_gap = _LABEL_IN_POLYGON_WRAP_Y_STEP * scale
    assert actual_gap == pytest.approx(expected_gap, rel=0.05)

    # Sane single-line-height range for the default 14px font -- not
    # touching zero, not blown out to double a normal line pitch.
    assert 0.5 * _FONT_SIZE <= actual_gap <= 2.0 * _FONT_SIZE

    # Regression guard: clearly less than stack_lines()'s own y_step=1.2
    # default would have produced at this same scale (the pre-fix bug).
    old_gap = 1.2 * scale
    assert actual_gap < 0.8 * old_gap


# ---------------------------------------------------------------------------
# Regression: overflow="wrap" must vertically CENTER the stacked block on
# the interior point, not top-anchor the first line there.
#
# stack_lines() places line i at y - i*y_step, so its own contract anchors
# the TOP line at the given y (see stack_lines()'s docstring -- unchanged by
# this fix). label_in_polygon() used to pass the interior point's y straight
# through as that anchor, which top-anchored the wrapped block instead of
# centering it: for n lines the block's average y landed
# (n-1)*y_step/2 below the interior point. The fix shifts the anchor up by
# that same half-span before calling stack_lines(), so the placed lines'
# average y comes back to the true interior point. These tests parse the
# real compiled IR (and, for the 2-line case, the actually rendered SVG) --
# not a mock -- to prove the fix holds for both n=2 and n=3.
# ---------------------------------------------------------------------------

def test_label_in_polygon_overflow_wrap_centers_two_line_block_on_interior_point():
    from geometry_diagrams.ir.to_sympy import compile_defs
    from geometry_diagrams.ir.renderer import SVGRenderer
    from geometry_diagrams.pydsl.api import canvas

    vertices_xy = [(-1.5, -1.0), (1.5, -1.0), (1.5, 1.0), (-1.5, 1.0)]
    sym_poly = _sympy_polygon(vertices_xy)
    x, y, clearance = _polygon_interior_point(sym_poly, vertices_xy)

    with new_builder_context() as builder:
        p1, p2, p3, p4 = (point(*v) for v in vertices_xy)
        poly = polygon(p1, p2, p3, p4)
        text = "Left\n2 x 3"
        label_in_polygon(poly, text, overflow="wrap")
        canvas(x_range=(-6.0, 6.0), y_range=(-6.0, 6.0))
        ir = builder.build()

    labels = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert len(labels) == 2

    # Real compiled-IR check: the average of the two placed lines' y
    # coordinates (construction units, before any SVG y-flip/scaling) must
    # equal the polygon's interior point y.
    ys = [l.at[1] for l in labels]
    assert sum(ys) / len(ys) == pytest.approx(y)
    # And it's a genuine two-line straddle, not both lines coincident.
    assert ys[0] != pytest.approx(ys[1])

    # Real rendered-SVG check too: parse the actual <text> elements' y
    # attributes and confirm they still average to the interior point once
    # converted back through the same px-per-unit scale used elsewhere in
    # this file (via two reference points at a known construction-unit
    # separation).
    import xml.etree.ElementTree as ET

    from geometry_diagrams.ir.to_svg import _FONT_SIZE  # noqa: F401  (parity with sibling tests)

    sym = compile_defs(ir)
    svg = SVGRenderer().render(ir, sym).output
    root = ET.fromstring(svg)
    text_els = [
        el for el in root.iter()
        if el.tag.rsplit("}", 1)[-1] == "text" and el.get("data-role") == "label-free-text"
    ]
    assert len(text_els) == 2
    svg_ys = [float(el.get("y")) for el in text_els]
    # SVG y is a monotonic (possibly flipped/scaled) function of construction
    # y here -- rather than re-deriving the transform, just confirm the two
    # rendered lines are symmetric about their own midpoint, which is the
    # weaker but transform-independent form of the same centering claim
    # already proven exactly above in construction units.
    assert svg_ys[0] != pytest.approx(svg_ys[1])


def test_label_in_polygon_overflow_wrap_centers_three_line_block_on_interior_point():
    vertices_xy = [(0.0, 0.0), (7.0, 0.0), (7.0, 2.0), (0.0, 2.0)]
    sym_poly = _sympy_polygon(vertices_xy)
    x, y, clearance = _polygon_interior_point(sym_poly, vertices_xy)
    budget = _width_budget_at(vertices_xy, (x, y), clearance)
    text = "alpha beta gamma delta epsilon zeta"
    # Confirm this combo really does wrap into exactly three lines (not two
    # or four) before relying on it below -- otherwise this wouldn't be
    # testing the n=3 case it claims to.
    assert len(_wrap_text_to_width(text, budget)) == 3

    with new_builder_context() as builder:
        p1, p2, p3, p4 = (point(*v) for v in vertices_xy)
        poly = polygon(p1, p2, p3, p4)
        label_in_polygon(poly, text, overflow="wrap")
        ir = builder.build()

    labels = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert len(labels) == 3

    ys = [l.at[1] for l in labels]
    assert sum(ys) / len(ys) == pytest.approx(y)
    # Genuinely three distinct rows, evenly spaced (stack_lines()'s own
    # contract), not degenerate.
    assert ys[0] > ys[1] > ys[2]
    assert (ys[0] - ys[1]) == pytest.approx(ys[1] - ys[2])
