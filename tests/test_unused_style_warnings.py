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


def test_tikz_warns_unused_but_not_unknown_keys():
    w = _tikz_warnings({"f": {"very thick": True}}, [ir.Fill(obj="T", style=None)])
    assert any("not used" in m for m in w)
    assert not any("ignores" in m for m in w)
