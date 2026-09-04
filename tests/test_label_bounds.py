# tests/test_label_bounds.py
"""Tests for geometry_diagrams/ir/label_bounds.py's find_out_of_bounds_labels().

Two label kinds matter equally here: plain-text labels (rendered by
to_svg.py as <text> elements) and math/LaTeX labels (rendered as <g>-wrapped
MathGlyph path groups, no <text> element at all) -- see to_svg.py's
label_needs_mathtext()/MathGlyph. A checker that only looked at <text>
elements would silently miss every math label, which is exactly the
correctness bug this ticket exists to avoid, so every case below is tested
for both kinds.
"""
from __future__ import annotations

from geometry_diagrams.ir.label_bounds import find_out_of_bounds_labels
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.pydsl.api import canvas, label_text, point
from geometry_diagrams.pydsl.builder import new_builder_context


def _render(build_fn) -> str:
    with new_builder_context() as builder:
        build_fn()
        ir = builder.build()
    sym = compile_defs(ir)
    return SVGRenderer().render(ir, sym).output


def test_clean_plain_text_label_is_not_flagged():
    def build():
        canvas(x_range=(-5, 5), y_range=(-5, 5))
        point(0, 0)
        label_text("hello", at=(0, 0))

    svg = _render(build)
    assert "<text" in svg
    assert find_out_of_bounds_labels(svg) == []


def test_out_of_bounds_plain_text_label_is_flagged():
    def build():
        canvas(x_range=(-5, 5), y_range=(-5, 5))
        point(0, 0)
        # Far outside the declared canvas range -> maps well outside the
        # rendered viewBox in pixel space.
        label_text("way off canvas", at=(500, 0))

    svg = _render(build)
    assert "<text" in svg
    violations = find_out_of_bounds_labels(svg)
    assert len(violations) == 1
    v = violations[0]
    assert v.text == "way off canvas"
    assert v.overflow > 0


def test_clean_math_label_is_not_flagged():
    def build():
        canvas(x_range=(-5, 5), y_range=(-5, 5))
        point(0, 0)
        label_text(r"\frac{1}{2}", at=(0, 0))

    svg = _render(build)
    assert "<text" not in svg  # math label -> <g>-wrapped MathGlyph, not <text>
    assert find_out_of_bounds_labels(svg) == []


def test_out_of_bounds_math_label_is_flagged():
    def build():
        canvas(x_range=(-5, 5), y_range=(-5, 5))
        point(0, 0)
        label_text(r"\frac{1}{2}", at=(500, 0))

    svg = _render(build)
    assert "<text" not in svg  # confirms this exercises the MathGlyph <g> path
    violations = find_out_of_bounds_labels(svg)
    assert len(violations) == 1
    v = violations[0]
    assert r"\frac{1}{2}" in v.text
    assert v.overflow > 0


def test_svg_with_no_viewbox_returns_no_violations():
    assert find_out_of_bounds_labels("<svg></svg>") == []


def test_svg_with_no_labels_returns_no_violations():
    svg = '<svg viewBox="0 0 100 100"></svg>'
    assert find_out_of_bounds_labels(svg) == []
