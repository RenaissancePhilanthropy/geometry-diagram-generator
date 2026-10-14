"""Backend-neutral color translation layer (solids ticket 05).

A color specification string is parsed once into a backend-neutral value and
each renderer emits it natively: SVG as a hex color, TikZ as a color defined
inside the picture (``\\definecolor{...}{RGB}{r,g,b}``) -- except named
colors (both backends) and xcolor mixes (TikZ), which pass through unchanged.
Anything unrecognized passes through unchanged and adds a renderer warning.

Accepted forms: the shared named colors; ``#rrggbb`` / ``#rgb``;
``rgb(r, g, b)`` (integers 0-255); ``hsv(h, s, v)`` (h degrees 0-360, s and v
0-1); the xcolor mix ``name!pct`` / ``name!pct!name2`` (pct of the first color
mixed with the second, default white).
"""
from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.render_util import parse_color, svg_color, tikz_color
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_svg import ir_to_svg
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline
from tests.availability import renderer_available

SVG_NS = "{http://www.w3.org/2000/svg}"

# (spec, expected RGB 0-255) for every accepted non-named form.
CONVERTED = [
    ("#9ec5ea", (158, 197, 234)),
    ("#9EC5EA", (158, 197, 234)),
    ("#f80", (255, 136, 0)),
    ("rgb(158, 197, 234)", (158, 197, 234)),
    ("rgb(0,0,0)", (0, 0, 0)),
    ("hsv(210, 0.5, 0.8)", (102, 153, 204)),
    ("hsv(0, 1, 1)", (255, 0, 0)),
    ("hsv(360, 1, 1)", (255, 0, 0)),
    # xcolor mixes: pct of the first color, rest white (or the second color),
    # using xcolor's own definitions of the named colors.
    ("cyan!55", (115, 255, 255)),
    ("red!30!blue", (77, 0, 179)),
    ("gray!50", (191, 191, 191)),
    ("black!100", (0, 0, 0)),
]

UNRECOGNIZED = [
    "notacolor", "Red", "#12345", "#ggg", "rgb(256, 0, 0)", "rgb(1.5, 2, 3)",
    "hsv(400, 0.5, 0.5)", "hsv(10, 1.5, 1)", "cyan!150", "foo!30", "red!30!foo",
    "red!", "",
]


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


# ---------------------------------------------------------------------------
# Parse contract
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spec,rgb", CONVERTED)
def test_parse_converts_accepted_forms_to_rgb(spec, rgb):
    parsed = parse_color(spec)
    assert parsed.recognized
    assert parsed.rgb == rgb


@pytest.mark.parametrize("name", ["red", "blue", "teal", "lightgray", "grey", "none"])
def test_named_colors_pass_through_both_backends(name):
    parsed = parse_color(name)
    assert parsed.recognized
    assert svg_color(name) == name
    assert tikz_color(name) == (name, None)


@pytest.mark.parametrize("spec", UNRECOGNIZED)
def test_unrecognized_specs_pass_through_unchanged(spec):
    parsed = parse_color(spec)
    assert not parsed.recognized
    assert svg_color(spec) == spec
    assert tikz_color(spec) == (spec, None)


@pytest.mark.parametrize("spec,rgb", CONVERTED)
def test_svg_emits_hex_for_converted_forms(spec, rgb):
    assert svg_color(spec) == _hex(rgb)


@pytest.mark.parametrize("spec,rgb", [c for c in CONVERTED if "!" not in c[0]])
def test_tikz_defines_hex_rgb_hsv_with_rgb_model(spec, rgb):
    name, definition = tikz_color(spec)
    assert re.fullmatch(r"[a-z][a-z0-9]*", name), name
    assert definition == "\\definecolor{%s}{RGB}{%d,%d,%d}" % (name, *rgb)


def test_tikz_color_names_are_deterministic_from_the_value():
    # Same RGB value, three spellings -> one name.
    names = {tikz_color(s)[0] for s in ("#ff0000", "rgb(255, 0, 0)", "hsv(0, 1, 1)", "#F00")}
    assert len(names) == 1
    assert tikz_color("#ff0000")[0] != tikz_color("#ff0001")[0]


@pytest.mark.parametrize("spec", ["cyan!55", "red!30!blue"])
def test_tikz_leaves_xcolor_mixes_unchanged(spec):
    assert tikz_color(spec) == (spec, None)


# ---------------------------------------------------------------------------
# Renderer fixtures
# ---------------------------------------------------------------------------

def _diagram(styles: dict, render: list) -> ir.DiagramIR:
    return ir.DiagramIR(
        define=[
            ir.PointFixed(id="A", x=0, y=0), ir.PointFixed(id="B", x=4, y=0),
            ir.PointFixed(id="C", x=1, y=3),
            ir.Triangle(id="T", a="A", b="B", c="C"),
            ir.Segment(id="s", a="A", b="B"),
        ],
        styles=styles,
        render=render,
    )


def _svg(diagram: ir.DiagramIR, warnings: list[str] | None = None) -> ET.Element:
    return ET.fromstring(ir_to_svg(diagram, compile_defs(diagram), warnings=warnings))


def _tikz(diagram: ir.DiagramIR, warnings: list[str] | None = None) -> str:
    return ir_to_tikz(diagram, compile_defs(diagram), warnings=warnings)


def _fill_el(root: ET.Element) -> ET.Element:
    (el,) = [e for e in root.iter() if e.get("data-role") == "fill"]
    return el


def _drawn(root: ET.Element, obj_id: str) -> list[ET.Element]:
    return [
        e for e in root.iter()
        if e.get("data-ir-id") == obj_id and e.get("data-role") != "fill" and e.get("stroke")
    ]


ALL_FORMS = [(s, _hex(rgb)) for s, rgb in CONVERTED]


# ---------------------------------------------------------------------------
# SVG emission at every color site
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spec,expected", ALL_FORMS)
def test_svg_fill_style_value(spec, expected):
    root = _svg(_diagram({"f": {"fill": spec}}, [ir.Fill(obj="T", style="f")]))
    assert _fill_el(root).get("fill") == expected


@pytest.mark.parametrize("spec,expected", ALL_FORMS)
def test_svg_fill_bare_style_key(spec, expected):
    root = _svg(_diagram({}, [ir.Fill(obj="T", style=spec)]))
    assert _fill_el(root).get("fill") == expected


@pytest.mark.parametrize("spec,expected", ALL_FORMS)
def test_svg_draw_stroke_style_value_and_bare_key(spec, expected):
    root = _svg(_diagram({"d": {"color": spec}}, [ir.Draw(obj="T", style="d"), ir.Draw(obj="s", style=spec)]))
    assert {e.get("stroke") for e in _drawn(root, "T")} == {expected}
    assert {e.get("stroke") for e in _drawn(root, "s")} == {expected}


@pytest.mark.parametrize("spec,expected", ALL_FORMS)
def test_svg_label_color(spec, expected):
    root = _svg(_diagram(
        {"l": {"color": spec}},
        [ir.LabelFreeText(text="Area", at=[1, 1], style="l"),
         ir.LabelSegment(seg="s", text="4 cm", style=spec)],
    ))
    fills = [e.get("fill") for e in root.iter(f"{SVG_NS}text")]
    assert fills.count(expected) == 2, fills


def test_svg_arrow_marker_matches_converted_stroke():
    root = _svg(_diagram({"a": {"color": "rgb(255, 136, 0)", "->": True}}, [ir.Draw(obj="s", style="a")]))
    (line,) = _drawn(root, "s")
    assert line.get("stroke") == "#ff8800"
    marker_id = re.fullmatch(r"url\(#(.+)\)", line.get("marker-end")).group(1)
    (marker,) = [m for m in root.iter(f"{SVG_NS}marker") if m.get("id") == marker_id]
    assert [p.get("fill") for p in marker.iter(f"{SVG_NS}path")] == ["#ff8800"]


def test_svg_legacy_mix_no_longer_paints_black():
    root = _svg(_diagram({"f": {"fill": "cyan!55"}}, [ir.Fill(obj="T", style="f")]))
    fill = _fill_el(root).get("fill")
    assert fill == "#73ffff"
    assert "!" not in fill


def test_svg_named_colors_unchanged_and_no_warnings():
    warnings: list[str] = []
    root = _svg(_diagram(
        {"f": {"fill": "cyan", "color": "blue"}, "d": {"color": "red"}},
        [ir.Fill(obj="T", style="f"), ir.Draw(obj="s", style="d"), ir.Draw(obj="T", style="purple")],
    ), warnings)
    assert _fill_el(root).get("fill") == "cyan"
    assert {e.get("stroke") for e in _drawn(root, "s")} == {"red"}
    assert {e.get("stroke") for e in _drawn(root, "T")} == {"purple"}
    assert warnings == []


def test_svg_unrecognized_passes_through_with_one_warning():
    warnings: list[str] = []
    root = _svg(_diagram(
        {"d": {"color": "notacolor"}, "e": {"color": "notacolor", "dashed": True}},
        [ir.Draw(obj="s", style="d"), ir.Draw(obj="T", style="e")],
    ), warnings)
    assert {e.get("stroke") for e in _drawn(root, "s")} == {"notacolor"}
    color_warnings = [w for w in warnings if "notacolor" in w]
    assert len(color_warnings) == 1
    assert "unrecognized color" in color_warnings[0].lower()


def test_pipeline_surfaces_unrecognized_color_warning():
    diagram = _diagram({"d": {"color": "bluish"}}, [ir.Draw(obj="s", style="d")])
    result = asyncio.run(run_ir_pipeline(diagram, SVGRenderer()))
    assert any("bluish" in w for w in result.warnings)


def test_svg_prism_hidden_edges_take_bare_converted_color():
    d = ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=0, y=0),
                ir.RectangularPrism(id="P", origin="O", length=3, width=2, height=2)],
        render=[ir.Draw(obj="P", style="#336699")],
    )
    root = ET.fromstring(ir_to_svg(d, compile_defs(d)))
    strokes = {e.get("stroke") for e in root.iter() if (e.get("data-ir-id") or "").startswith("P")}
    assert strokes - {None, "none"} == {"#336699"}
    dashed = [e for e in root.iter() if e.get("stroke-dasharray") and (e.get("data-ir-id") or "").startswith("P")]
    assert dashed and {e.get("stroke") for e in dashed} == {"#336699"}


# ---------------------------------------------------------------------------
# TikZ emission (text; no container needed)
# ---------------------------------------------------------------------------

_DEF_RE = re.compile(r"\\definecolor\{([^}]*)\}\{RGB\}\{(\d+),(\d+),(\d+)\}")


def _definitions(tikz: str) -> list[tuple[str, tuple[int, int, int]]]:
    return [(m.group(1), tuple(int(g) for g in m.group(2, 3, 4))) for m in _DEF_RE.finditer(tikz)]


def _assert_defined_before_use(tikz: str, name: str) -> None:
    lines = tikz.splitlines()
    def_idx = [i for i, ln in enumerate(lines) if ln.startswith(f"\\definecolor{{{name}}}")]
    use_idx = [i for i, ln in enumerate(lines) if f"={name}" in ln and not ln.startswith("\\definecolor")]
    assert len(def_idx) == 1, tikz
    assert use_idx, tikz
    assert def_idx[0] < min(use_idx), tikz


@pytest.mark.parametrize("spec,rgb", [c for c in CONVERTED if "!" not in c[0]])
def test_tikz_fill_draw_label_define_color_once_before_use(spec, rgb):
    tikz = _tikz(_diagram(
        {"f": {"fill": spec}, "d": {"color": spec, "thick": True}, "l": {"color": spec}},
        [ir.Fill(obj="T", style="f"), ir.Draw(obj="T", style="d"), ir.Draw(obj="s", style=spec),
         # TikZ colors only angle (and along-arc) labels today; point,
         # segment and free-text labels ignore their style in TikZ.
         ir.LabelAngle(angle=ir.AngleSpec(a="B", o="A", b="C"), text="x", style="l"),
         ir.LabelAngle(angle=ir.AngleSpec(a="A", o="B", b="C"), text="y", style=spec)],
    ))
    defs = _definitions(tikz)
    assert len(defs) == 1, tikz
    name, got = defs[0]
    assert got == rgb
    assert re.fullmatch(r"[a-z][a-z0-9]*", name)
    _assert_defined_before_use(tikz, name)
    assert spec not in tikz
    assert f"fill={name}" in tikz
    assert tikz.count(f"color={name}") >= 4  # draw style, bare draw, two labels


def test_tikz_distinct_colors_each_defined_once():
    tikz = _tikz(_diagram(
        {"a": {"color": "#ff0000"}, "b": {"color": "rgb(255, 0, 0)"}, "c": {"fill": "hsv(120, 1, 1)"}},
        [ir.Draw(obj="T", style="a"), ir.Draw(obj="s", style="b"), ir.Fill(obj="T", style="c")],
    ))
    defs = _definitions(tikz)
    assert sorted(rgb for _, rgb in defs) == [(0, 255, 0), (255, 0, 0)]
    assert len({n for n, _ in defs}) == 2


@pytest.mark.parametrize("spec", ["cyan!55", "red!30!blue"])
def test_tikz_mix_strings_emitted_unchanged(spec):
    warnings: list[str] = []
    tikz = _tikz(_diagram({"f": {"fill": spec}}, [ir.Fill(obj="T", style="f"), ir.Draw(obj="s", style=spec)]), warnings)
    assert "\\definecolor" not in tikz
    assert f"fill={spec}" in tikz
    assert f"color={spec}" in tikz
    assert warnings == []


def test_tikz_named_colors_no_definitions_no_warnings():
    warnings: list[str] = []
    tikz = _tikz(_diagram(
        {"f": {"fill": "cyan", "color": "blue"}},
        [ir.Fill(obj="T", style="f"), ir.Draw(obj="s", style="red")],
    ), warnings)
    assert "\\definecolor" not in tikz
    assert "fill=cyan" in tikz and "color=red" in tikz
    assert warnings == []


def test_tikz_unrecognized_passes_through_with_warning():
    warnings: list[str] = []
    tikz = _tikz(_diagram({"d": {"color": "notacolor"}}, [ir.Draw(obj="s", style="d")]), warnings)
    assert "color=notacolor" in tikz
    assert "\\definecolor" not in tikz
    assert len([w for w in warnings if "notacolor" in w]) == 1


def test_tikz_prism_hidden_edges_take_bare_converted_color():
    d = ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=0, y=0),
                ir.RectangularPrism(id="P", origin="O", length=3, width=2, height=2)],
        render=[ir.Draw(obj="P", style="#336699")],
    )
    tikz = ir_to_tikz(d, compile_defs(d))
    ((name, rgb),) = _definitions(tikz)
    assert rgb == (0x33, 0x66, 0x99)
    _assert_defined_before_use(tikz, name)
    assert any("dashed" in ln and f"color={name}" in ln for ln in tikz.splitlines())


# ---------------------------------------------------------------------------
# TikZ compile smoke (renderer container; skipped when it is down)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not renderer_available(), reason="TikZ renderer container not running")
@pytest.mark.parametrize("spec,expected", [f for f in ALL_FORMS if f[1] != "#000000"])
def test_tikz_compiles_each_form_with_equivalent_fill(spec, expected):
    from geometry_diagrams.util.tikz_renderer import render_tikz

    diagram = _diagram(
        {"f": {"fill": spec, "draw": spec}},
        [ir.Fill(obj="T", style="f"), ir.Draw(obj="s", style=spec)],
    )
    svg = render_tikz(_tikz(diagram))
    # dvisvgm writes colors as #rrggbb; allow +-1 per channel for xcolor's
    # own fixed-point mixing arithmetic.
    found = {m.lower() for m in re.findall(r"(?:fill|stroke)=['\"](#[0-9a-fA-F]{6})['\"]", svg)}
    want = tuple(int(expected[i:i + 2], 16) for i in (1, 3, 5))
    assert any(
        all(abs(int(f[i:i + 2], 16) - w) <= 1 for i, w in zip((1, 3, 5), want)) for f in found
    ), (expected, found)
