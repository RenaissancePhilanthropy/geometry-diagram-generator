"""Warnings for a `styles` entry no render op names, or with keys the renderer ignores."""
from __future__ import annotations

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.to_svg import ir_to_svg
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz
from tests.test_color_layer import _diagram


def _svg_warnings(styles, ops):
    d = _diagram(styles, ops)
    w: list[str] = []
    ir_to_svg(d, compile_defs(d), warnings=w)
    return w


def _tikz_warnings(styles, ops):
    d = _diagram(styles, ops)
    w: list[str] = []
    ir_to_tikz(d, compile_defs(d), warnings=w)
    return w


def test_guessed_dash_entry_warns_unused_and_unknown_key():
    w = _svg_warnings({"s_CO": {"dash": "dashed"}}, [ir.Fill(obj="T", style=None)])
    assert any("'s_CO' is not used" in m for m in w)
    assert any("'s_CO'" in m and "dash" in m and "ignores" in m for m in w)


def test_unknown_key_on_a_used_style_warns_only_about_keys():
    w = _svg_warnings({"f": {"fill": "red", "dash": "dashed"}}, [ir.Fill(obj="T", style="f")])
    assert not any("not used" in m for m in w)
    assert any("ignores: dash" in m for m in w)


def test_valid_used_style_adds_no_warning():
    w = _svg_warnings({"f": {"fill": "red", "dashed": True}}, [ir.Fill(obj="T", style="f")])
    assert not any("styles entry" in m for m in w)


def test_tikz_warns_unused_entries():
    w = _tikz_warnings({"f": {"very thick": True}}, [ir.Fill(obj="T", style=None)])
    assert any("not used" in m for m in w)


def test_tikz_warns_about_keys_that_would_fail_the_latex_build():
    w = _tikz_warnings({"f": {"dash": "dashed", "font-size": 14, "color": "red"}}, [ir.Fill(obj="T", style="f")])
    (m,) = [m for m in w if "does not recognise" in m]
    assert "'f'" in m and "dash" in m and "font-size" in m and "color" not in m.split(":", 1)[1].split("(use")[0]
    assert not any("not used" in m for m in w)


def test_tikz_accepts_valid_options_and_the_renderer_keys():
    valid = {"very thick": True, "dashed": True, "opacity": 0.5, "->": True, "line_width": 2,
             "clip": "own_extent", "color": "red", "fill": "blue", "rounded corners": "2pt", "densely dotted": True}
    w = _tikz_warnings({"f": valid}, [ir.Fill(obj="T", style="f")])
    assert not any("styles entry" in m for m in w)


def test_svg_and_tikz_notes_differ():
    svg = _svg_warnings({"f": {"dash": "dashed"}}, [ir.Fill(obj="T", style="f")])
    tikz = _tikz_warnings({"f": {"dash": "dashed"}}, [ir.Fill(obj="T", style="f")])
    assert any("keys the renderer ignores: dash" in m for m in svg)
    assert any("keys TikZ does not recognise (the LaTeX build would fail): dash" in m for m in tikz)
