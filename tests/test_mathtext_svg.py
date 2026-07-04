"""Tests for geometry_diagrams/ir/mathtext_svg.py

Tests are written FIRST (TDD red phase). All tests must fail before implementation begins.
"""
from __future__ import annotations

import math
import re

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SVG_PATH_CMD = re.compile(r"[MLQCZmlqcz]")


def _only_path_commands(d: str) -> bool:
    """Return True if d contains only valid SVG path commands (M/L/Q/C/Z and coords)."""
    # strip numbers, spaces, commas, dots, minus, 'e' (scientific notation)
    stripped = re.sub(r"[-\d\s.,eE]+", "", d)
    # only M L Q C Z (uppercase, since we emit uppercase only)
    return bool(stripped) and all(c in "MLQCZ" for c in stripped)


def _parse_path_d(d: str) -> list[tuple[str, list[float]]]:
    """Parse SVG path d string into (command, [coords]) tuples."""
    tokens = re.findall(r"[MLQCZ]|[-\d.]+(?:e[-+]?\d+)?", d, flags=re.IGNORECASE)
    result = []
    cmd = None
    coords: list[float] = []
    for t in tokens:
        if t.upper() in "MLQCZ":
            if cmd is not None:
                result.append((cmd, coords))
            cmd = t.upper()
            coords = []
        else:
            coords.append(float(t))
    if cmd is not None:
        result.append((cmd, coords))
    return result


def _path_bounding_box(d: str) -> tuple[float, float, float, float]:
    """Crude bounding box from path vertices (ignores curves, uses control points)."""
    xs, ys = [], []
    for cmd, coords in _parse_path_d(d):
        if cmd == "Z":
            continue
        for i in range(0, len(coords) - 1, 2):
            xs.append(coords[i])
            ys.append(coords[i + 1])
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


# ---------------------------------------------------------------------------
# Import the module under test (does not exist yet → will fail at import)
# ---------------------------------------------------------------------------

from geometry_diagrams.ir.mathtext_svg import (
    MathGlyph,
    render_math_to_svg,
    label_needs_mathtext,
)


# ---------------------------------------------------------------------------
# MathGlyph dataclass
# ---------------------------------------------------------------------------

class TestMathGlyph:
    def test_has_expected_fields(self):
        g = MathGlyph(d="M0 0 Z", width=10.0, height=8.0, x_min=0.0, y_min=-4.0)
        assert g.d == "M0 0 Z"
        assert g.width == 10.0
        assert g.height == 8.0
        assert g.x_min == 0.0
        assert g.y_min == -4.0

    def test_width_height_positive(self):
        g = MathGlyph(d="M0 0 Z", width=5.0, height=3.0, x_min=0.0, y_min=0.0)
        assert g.width > 0
        assert g.height > 0


# ---------------------------------------------------------------------------
# render_math_to_svg — path correctness
# ---------------------------------------------------------------------------

class TestRenderMathToSvgPathFormat:
    """The returned d string must be a well-formed SVG path with only M/L/Q/C/Z."""

    @pytest.mark.parametrize("latex", [
        r"$A$",
        r"$\angle ABC$",
        r"$\overline{AB}$",
        r"$\frac{x+1}{2}$",
        r"$\sqrt{x+1}$",
        r"$x_{i_j}$",
        r"$\vec{v}$",
        r"$\hat{n}$",
        r"$\widehat{ABC}$",
        r"$\theta = 30^\circ$",
        r"$\sum_{i=1}^{n} x_i$",
        r"$\alpha\beta\gamma\pi$",
        r"$r^2 = x^2 + y^2$",
        r"$\frac{x+1}{\sqrt{2}}$",
        r"$\Delta ABC$",
    ])
    def test_returns_mathglyph_not_none(self, latex):
        result = render_math_to_svg(latex, font_size=14.0)
        assert result is not None, f"Expected MathGlyph, got None for {latex!r}"

    @pytest.mark.parametrize("latex", [
        r"$A$",
        r"$\frac{x+1}{2}$",
        r"$\sqrt{x+1}$",
    ])
    def test_d_is_nonempty(self, latex):
        g = render_math_to_svg(latex, font_size=14.0)
        assert g is not None
        assert g.d.strip(), f"Empty d string for {latex!r}"

    @pytest.mark.parametrize("latex", [
        r"$A$",
        r"$\frac{x+1}{2}$",
        r"$\sqrt{x+1}$",
        r"$\alpha\beta$",
        r"$x_{i_j}$",
    ])
    def test_d_uses_only_valid_path_commands(self, latex):
        g = render_math_to_svg(latex, font_size=14.0)
        assert g is not None
        assert _only_path_commands(g.d), (
            f"Unexpected chars in d for {latex!r}: "
            + repr(re.sub(r"[-\d\s.,eE]+", "", g.d))
        )


# ---------------------------------------------------------------------------
# render_math_to_svg — bounding box
# ---------------------------------------------------------------------------

class TestRenderMathToSvgBbox:
    """Bounding box must be positive and scale with font_size."""

    @pytest.mark.parametrize("latex", [
        r"$A$",
        r"$\angle ABC$",
        r"$\frac{x+1}{2}$",
        r"$\sqrt{x+1}$",
        r"$\alpha\beta\gamma$",
    ])
    def test_width_positive(self, latex):
        g = render_math_to_svg(latex, font_size=14.0)
        assert g is not None
        assert g.width > 0, f"width={g.width} for {latex!r}"

    @pytest.mark.parametrize("latex", [
        r"$A$",
        r"$\frac{x+1}{2}$",
    ])
    def test_height_positive(self, latex):
        g = render_math_to_svg(latex, font_size=14.0)
        assert g is not None
        assert g.height > 0, f"height={g.height} for {latex!r}"

    def test_frac_taller_than_simple(self):
        """A fraction must be taller than a simple letter (stacked layout)."""
        simple = render_math_to_svg(r"$A$", font_size=14.0)
        frac = render_math_to_svg(r"$\frac{x+1}{2}$", font_size=14.0)
        assert simple is not None and frac is not None
        assert frac.height > simple.height, (
            f"frac.height={frac.height} should be > simple.height={simple.height}"
        )

    def test_longer_expression_wider(self):
        """A longer expression must be wider than a single letter."""
        single = render_math_to_svg(r"$A$", font_size=14.0)
        long_ = render_math_to_svg(r"$ABCDEF$", font_size=14.0)
        assert single is not None and long_ is not None
        assert long_.width > single.width

    def test_scale_doubles_with_double_font_size(self):
        """Width and height should approximately double when font_size doubles."""
        g14 = render_math_to_svg(r"$\alpha$", font_size=14.0)
        g28 = render_math_to_svg(r"$\alpha$", font_size=28.0)
        assert g14 is not None and g28 is not None
        ratio_w = g28.width / g14.width
        ratio_h = g28.height / g14.height
        assert 1.8 < ratio_w < 2.2, f"Width ratio {ratio_w:.2f} not ≈ 2 on font_size doubling"
        assert 1.8 < ratio_h < 2.2, f"Height ratio {ratio_h:.2f} not ≈ 2 on font_size doubling"

    def test_cap_height_plausible_for_single_letter(self):
        """For a single capital letter at 14px, height should be < 20px (not hundreds)."""
        g = render_math_to_svg(r"$A$", font_size=14.0)
        assert g is not None
        assert 4 < g.height < 25, f"Unexpected height {g.height} for '$A$' at 14px"


# ---------------------------------------------------------------------------
# render_math_to_svg — strips $...$ delimiters
# ---------------------------------------------------------------------------

class TestRenderMathToSvgDelimiters:
    def test_with_dollar_delimiters(self):
        g = render_math_to_svg(r"$\alpha$", font_size=14.0)
        assert g is not None

    def test_without_dollar_delimiters(self):
        g = render_math_to_svg(r"\alpha", font_size=14.0)
        assert g is not None

    def test_same_result_with_and_without_dollars(self):
        with_dollars = render_math_to_svg(r"$\alpha$", font_size=14.0)
        without_dollars = render_math_to_svg(r"\alpha", font_size=14.0)
        assert with_dollars is not None and without_dollars is not None
        # Paths should be identical (same glyph)
        assert with_dollars.d == without_dollars.d
        assert math.isclose(with_dollars.width, without_dollars.width, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# render_math_to_svg — graceful failure
# ---------------------------------------------------------------------------

class TestRenderMathToSvgGracefulFailure:
    def test_empty_string_returns_none_or_glyph(self):
        """Empty input should return None (no content to render)."""
        result = render_math_to_svg("", font_size=14.0)
        assert result is None

    def test_only_whitespace_returns_none(self):
        result = render_math_to_svg("   ", font_size=14.0)
        assert result is None


# ---------------------------------------------------------------------------
# render_math_to_svg — caching (same object returned for repeated calls)
# ---------------------------------------------------------------------------

class TestRenderMathToSvgCaching:
    def test_repeated_call_returns_same_d(self):
        """Calling twice with the same args must return identical results."""
        g1 = render_math_to_svg(r"$\frac{a}{b}$", font_size=14.0)
        g2 = render_math_to_svg(r"$\frac{a}{b}$", font_size=14.0)
        assert g1 is not None and g2 is not None
        assert g1.d == g2.d
        assert g1.width == g2.width

    def test_different_sizes_different_results(self):
        g14 = render_math_to_svg(r"$A$", font_size=14.0)
        g20 = render_math_to_svg(r"$A$", font_size=20.0)
        assert g14 is not None and g20 is not None
        assert g14.d != g20.d


# ---------------------------------------------------------------------------
# label_needs_mathtext — routing classifier
# ---------------------------------------------------------------------------

class TestLabelNeedsMathtext:
    """Plain labels stay in brand font; math constructs route to mathtext."""

    # --- should NOT need mathtext (brand font) ---
    @pytest.mark.parametrize("text", [
        "A", "B", "C",          # single letters
        "AB", "ABC",            # multi-letter
        "5", "12", "3.14",      # numbers
        "a", "b", "c",          # lowercase letters
        "P_1", "x_2",           # simple subscripts (one level, ASCII)
        "c²", "r³",             # unicode superscripts already in font
    ])
    def test_plain_labels_do_not_need_mathtext(self, text):
        assert not label_needs_mathtext(text), f"{text!r} should stay in brand font"

    # --- SHOULD need mathtext ---
    @pytest.mark.parametrize("text", [
        r"\frac{x}{2}",         # fraction
        r"$\frac{x}{2}$",       # fraction with delimiters
        r"\sqrt{x+1}",          # sqrt
        r"\vec{v}",             # vector accent
        r"\hat{n}",             # hat accent
        r"\widehat{ABC}",       # widehat
        r"\widetilde{x}",       # widetilde
        r"\sum_{i=1}^{n}",      # large operator
        r"\int_{0}^{1}",        # integral
        r"\alpha",              # Greek (LaTeX command form)
        r"\theta",
        r"\Delta",
        r"\overrightarrow{AB}", # arrow accent
        r"x_{i_j}",            # nested subscript
        r"\angle ABC",          # geometric symbol
    ])
    def test_math_labels_need_mathtext(self, text):
        assert label_needs_mathtext(text), f"{text!r} should route to mathtext"

    def test_dollar_wrapped_routes_to_mathtext(self):
        # $...$ with any math inside should route to mathtext
        assert label_needs_mathtext(r"$\frac{a}{b}$")
        assert label_needs_mathtext(r"$\sqrt{2}$")

    def test_plain_with_dollar_sign_currency(self):
        # A bare dollar sign is not math — but this is an edge case; we just document the
        # behaviour without being strict: if the text has ONLY "$" it may go either way.
        # The important thing is it doesn't crash.
        result = label_needs_mathtext("$")
        assert isinstance(result, bool)
