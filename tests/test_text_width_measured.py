"""_estimate_text_width measures label text with the bundled font's metrics."""
import pytest

from geometry_diagrams.ir import to_svg
from geometry_diagrams.ir.to_svg import _estimate_text_width


def test_word_width_matches_real_font():
    assert _estimate_text_width("3 units", 14) == pytest.approx(42.7, rel=0.02)


def test_single_capital_matches_real_font():
    assert _estimate_text_width("H", 14) == pytest.approx(10.7, rel=0.02)


def test_floor_applied_to_one_char_string():
    assert _estimate_text_width("i", 14) == pytest.approx(0.6 * 14)
    assert _estimate_text_width("", 14) == pytest.approx(0.6 * 14)


def test_dollar_delimiters_are_stripped():
    assert _estimate_text_width("$3 units$", 14) == pytest.approx(
        _estimate_text_width("3 units", 14))


def test_latex_command_counts_as_one_char_and_grouping_dropped():
    assert _estimate_text_width(r"\alpha", 14) == pytest.approx(
        _estimate_text_width("X", 14))
    assert _estimate_text_width("x_{2}^{3}", 14) == pytest.approx(
        _estimate_text_width("x23", 14))


def test_scales_linearly_with_font_size():
    assert _estimate_text_width("3 units", 28) == pytest.approx(
        2 * _estimate_text_width("3 units", 14))


def test_missing_font_falls_back_to_flat_rule(monkeypatch):
    monkeypatch.setattr(to_svg, "_measure_text_em", lambda family, text: None)
    assert _estimate_text_width("3 units", 14) == pytest.approx(7 * 14 * 0.65)


def test_unknown_family_falls_back_without_raising(monkeypatch):
    monkeypatch.setenv("DIAGRAM_FONT_FAMILY", "NoSuchFont")
    to_svg._load_font.cache_clear()
    try:
        assert _estimate_text_width("abc", 14) == pytest.approx(3 * 14 * 0.65)
    finally:
        to_svg._load_font.cache_clear()
