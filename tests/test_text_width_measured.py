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


def test_unbundled_family_falls_back_to_nunito_metrics(monkeypatch):
    expected = _estimate_text_width("3 units", 14)
    monkeypatch.setenv("DIAGRAM_FONT_FAMILY", "NoSuchFont")
    assert _estimate_text_width("3 units", 14) == pytest.approx(expected)


def test_flat_rule_only_when_nunito_itself_is_unavailable(monkeypatch):
    monkeypatch.setattr(to_svg, "_load_font", lambda family: None)
    assert _estimate_text_width("abc", 14) == pytest.approx(3 * 14 * 0.65)


def test_concurrent_measurement_is_thread_safe_and_stable():
    """Shared FT2Font use from several threads used to abort the process;
    run in a subprocess so a crash fails this test rather than pytest."""
    import subprocess
    import sys
    import textwrap

    code = textwrap.dedent("""
        import threading
        from geometry_diagrams.ir.to_svg import _estimate_text_width as e
        texts = ["3 units", "H", "ABCDE", "Hello world", "x^2", "11 units"]
        want = {t: e(t, 14) for t in texts}
        bad = []
        def w():
            for _ in range(3000):
                for t in texts:
                    if e(t, 14) != want[t]:
                        bad.append(t)
        ts = [threading.Thread(target=w) for _ in range(8)]
        [x.start() for x in ts]; [x.join() for x in ts]
        assert not bad, bad[:3]
        print("ok")
    """)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0 and "ok" in r.stdout, (r.returncode, r.stderr[-500:])


def _svg_with(family, monkeypatch, env=None):
    from geometry_diagrams.ir.font import FontConfig
    from geometry_diagrams.ir.to_sympy import compile_defs
    from geometry_diagrams.recipe.catalog import load_recipe
    from geometry_diagrams.recipe.dsl import RecipeDSL
    from geometry_diagrams.recipe.lower import lower_to_ir

    if env:
        monkeypatch.setenv("DIAGRAM_FONT_FAMILY", env)
    d = lower_to_ir(RecipeDSL.model_validate(load_recipe("altitude").example))
    cfg = FontConfig(family=family) if family else None
    return to_svg.ir_to_svg(d, compile_defs(d), [], font_config=cfg)


def test_render_measures_with_the_passed_font_config(monkeypatch):
    seen = []
    real = to_svg._measure_text_em
    monkeypatch.setattr(to_svg, "_measure_text_em",
                        lambda family, text: (seen.append(family), real(family, text))[1])
    _svg_with("NunitoSans", monkeypatch, env="NoSuchFont")
    assert seen and set(seen) == {"NunitoSans"}
    seen.clear()
    _svg_with("OtherFamily", monkeypatch, env="NunitoSans")
    assert seen and set(seen) == {"OtherFamily"}


def test_unbundled_passed_family_measures_like_nunito(monkeypatch):
    # OtherFamily is not bundled -> NunitoSans metrics; the font-face data
    # lookup is not exercised (embed_fonts is off).
    a = _svg_with("OtherFamily", monkeypatch)
    b = _svg_with("NunitoSans", monkeypatch)
    import re
    assert re.findall(r'data-bbox="[^"]*"', a) == re.findall(r'data-bbox="[^"]*"', b)


def test_no_config_still_uses_env_default(monkeypatch):
    seen = []
    real = to_svg._measure_text_em
    monkeypatch.setattr(to_svg, "_measure_text_em",
                        lambda family, text: (seen.append(family), real(family, text))[1])
    _svg_with(None, monkeypatch, env="EnvFamily")
    assert set(seen) == {"EnvFamily"}


def test_plain_measurement_does_not_touch_global_warning_filters(monkeypatch):
    import warnings

    real = warnings.catch_warnings
    calls = []

    def spy(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(warnings, "catch_warnings", spy)
    try:
        assert _estimate_text_width("3 units", 14) == pytest.approx(42.7, rel=0.02)
        n = len(calls)
    finally:
        monkeypatch.undo()
    assert n == 0


def test_missing_glyph_does_not_warn_or_raise():
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert _estimate_text_width("\u03b1\u03b2", 14) > 0
