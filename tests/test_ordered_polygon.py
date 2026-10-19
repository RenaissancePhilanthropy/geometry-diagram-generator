"""Ticket 19: the ordered filled-and-stroked polygon primitive (``ir.OrderedPolygon``).

Both renderers emit it in strict list order, each polygon painting its opaque
fill and its stroke together, so painter's-algorithm block stacks hide what is
behind a face (today's Fill + Draw pair is hoisted: all fills, then all
strokes, so outlines of far faces show through near fills).
"""
from __future__ import annotations

import dataclasses
import math
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.derived import REGISTRY, Lowering
from geometry_diagrams.ir.label_bounds import find_out_of_bounds_labels
from geometry_diagrams.ir.to_svg import ir_to_svg
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz
from tests.availability import renderer_available

SVG_POLY = re.compile(r"<polygon\b[^>]*>")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _square_defs():
    return [
        ir.PointFixed(id="A", x=0, y=0), ir.PointFixed(id="B", x=2, y=0),
        ir.PointFixed(id="C", x=2, y=2), ir.PointFixed(id="D", x=0, y=2),
        ir.PointFixed(id="E", x=1, y=1), ir.PointFixed(id="F", x=3, y=1),
        ir.PointFixed(id="G", x=3, y=3), ir.PointFixed(id="H", x=1, y=3),
    ]


def _diagram(define, render, canvas=None):
    """A DiagramIR whose render list may hold OrderedPolygons. They are not in
    the validated ``RenderOp`` union (hooks emit them after validation, as
    ``lower_render`` does), so the list is attached without validation."""
    return ir.DiagramIR(define=define, canvas=canvas).model_copy(update={"render": list(render)})


def _svg(diagram):
    return ir_to_svg(diagram, compile_defs(diagram), [])


def _tikz(diagram, warnings=None):
    return ir_to_tikz(diagram, compile_defs(diagram), warnings=warnings)


def _two_overlapping(first_fill="#112233", second_fill="lightblue"):
    return _diagram(
        _square_defs(),
        [
            ir.OrderedPolygon(points=["A", "B", "C", "D"], fill=first_fill),
            ir.OrderedPolygon(points=["E", "F", "G", "H"], fill=second_fill),
        ],
    )


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------

def test_svg_emits_polygons_in_list_order_with_own_stroke():
    polys = SVG_POLY.findall(_svg(_two_overlapping()))
    assert len(polys) == 2
    assert 'fill="#112233"' in polys[0] and 'fill="lightblue"' in polys[1]
    for p in polys:
        assert 'stroke="black"' in p
        assert "fill-opacity" not in p  # opaque: hides what is behind it


def test_svg_order_follows_list_not_kind():
    d = _two_overlapping()
    d.render.reverse()
    polys = SVG_POLY.findall(_svg(d))
    assert 'fill="lightblue"' in polys[0] and 'fill="#112233"' in polys[1]


def test_svg_interleaved_with_ordinary_ops_keeps_its_own_order():
    d = _diagram(
        define=_square_defs() + [ir.Polygon(id="P1", points=["A", "B", "C", "D"]),
                                 ir.Polygon(id="P2", points=["E", "F", "G", "H"])],
        render=[
            ir.OrderedPolygon(points=["A", "B", "C", "D"], fill="#ff0000"),
            ir.Draw(obj="P2"),
            ir.OrderedPolygon(points=["E", "F", "G", "H"], fill="#00ff00"),
            ir.Fill(obj="P1", style="blue"),
            ir.LabelPoint(p="A", text="A"),
        ],
    )
    svg = _svg(d)
    red, draw, green = (svg.index('fill="#ff0000"'), svg.index('data-ir-id="P2"'),
                        svg.index('fill="#00ff00"'))
    assert red < draw < green               # list order among draws/ordered polygons
    assert svg.index('data-role="fill"') < red   # ordinary Fill stays in the fill layer
    assert svg.index(">A<") > green or svg.rfind("<text") > green  # labels on top


def test_svg_color_layer_forms():
    d = _diagram(
        define=_square_defs(),
        render=[
            ir.OrderedPolygon(points=["A", "B", "C", "D"], fill="#f80", stroke="rgb(1,2,3)"),
            ir.OrderedPolygon(points=["E", "F", "G", "H"], fill="hsv(210, 0.5, 0.8)", stroke="red!50"),
        ],
    )
    polys = SVG_POLY.findall(_svg(d))
    assert 'fill="#ff8800"' in polys[0] and 'stroke="#010203"' in polys[0]
    assert 'fill="#6699cc"' in polys[1]


def test_svg_unrecognized_color_warns_once():
    d = _diagram(define=_square_defs(),
                     render=[ir.OrderedPolygon(points=["A", "B", "C", "D"], fill="notacolor"),
                             ir.OrderedPolygon(points=["E", "F", "G", "H"], fill="notacolor")])
    w: list[str] = []
    ir_to_svg(d, compile_defs(d), w)
    assert len([m for m in w if "notacolor" in m]) == 1


def test_svg_undefined_point_warns_and_skips():
    d = _diagram(define=_square_defs(),
                     render=[ir.OrderedPolygon(points=["A", "B", "nope"], fill="red")])
    w: list[str] = []
    svg = ir_to_svg(d, compile_defs(d), w)
    assert not SVG_POLY.findall(svg)
    assert any("nope" in m for m in w)


def test_svg_point_bounds_cover_the_polygon_and_labels_stay_inside_viewbox():
    d = _diagram(
        define=[ir.PointFixed(id="A", x=0, y=0), ir.PointFixed(id="B", x=40, y=0),
                ir.PointFixed(id="C", x=40, y=1)],
        render=[ir.OrderedPolygon(points=["A", "B", "C"], fill="red"),
                ir.LabelPoint(p="B", text="far right label")],
    )
    svg = _svg(d)
    assert find_out_of_bounds_labels(svg) == []
    assert len(SVG_POLY.findall(svg)) == 1


def test_existing_fill_and_draw_still_hoist_fills_before_strokes():
    d = _diagram(
        define=_square_defs() + [ir.Polygon(id="P1", points=["A", "B", "C", "D"]),
                                 ir.Polygon(id="P2", points=["E", "F", "G", "H"])],
        render=[ir.Draw(obj="P1"), ir.Fill(obj="P2", style="blue")],
    )
    svg = _svg(d)
    assert svg.index('data-role="fill"') < svg.index('data-ir-id="P1"')


# ---------------------------------------------------------------------------
# TikZ
# ---------------------------------------------------------------------------

def _ordered_lines(tikz: str) -> list[str]:
    return [ln for ln in tikz.splitlines() if ln.startswith("\\filldraw")]


def test_tikz_emits_filldraw_in_list_order():
    tikz = _tikz(_two_overlapping())
    lines = _ordered_lines(tikz)
    assert len(lines) == 2
    assert "fill=#112233" not in tikz  # hex is \definecolor'd, never emitted raw
    assert "fill=lightblue" not in lines[1]  # CSS name xcolor lacks is defined too
    assert lines[0].index("(0,0)") < len(lines[0]) and "(0,0) -- (2,0) -- (2,2) -- (0,2) -- cycle" in lines[0]
    assert "(1,1) -- (3,1) -- (3,3) -- (1,3) -- cycle" in lines[1]
    assert "opacity" not in lines[0]


def test_tikz_colors_defined_before_use():
    tikz = _tikz(_two_overlapping())
    defs = re.findall(r"\\definecolor\{(\w+)\}\{RGB\}\{(\d+),(\d+),(\d+)\}", tikz)
    by_rgb = {(int(r), int(g), int(b)): n for n, r, g, b in defs}
    assert (0x11, 0x22, 0x33) in by_rgb and (0xad, 0xd8, 0xe6) in by_rgb
    first_use = tikz.index("\\filldraw")
    for name in by_rgb.values():
        assert tikz.index(f"\\definecolor{{{name}}}") < first_use
        assert f"fill={name}" in tikz


def test_tikz_stroke_color_and_width():
    d = _diagram(define=_square_defs(),
                     render=[ir.OrderedPolygon(points=["A", "B", "C", "D"], fill="red", stroke="#336699",
                                               stroke_width=2.5)])
    tikz = _tikz(d)
    (line,) = _ordered_lines(tikz)
    assert "line width=2.5pt" in line and "fill=red" in line
    assert "draw=tkzc_336699" in line or re.search(r"draw=\w*336699", line)
    assert "line join=round" in line


def test_tikz_interleaved_with_ordinary_ops_keeps_its_own_order():
    d = _diagram(
        define=_square_defs() + [ir.Polygon(id="P1", points=["A", "B", "C", "D"]),
                                 ir.Polygon(id="P2", points=["E", "F", "G", "H"])],
        render=[
            ir.OrderedPolygon(points=["A", "B", "C", "D"], fill="red"),
            ir.Draw(obj="P2"),
            ir.OrderedPolygon(points=["E", "F", "G", "H"], fill="green"),
            ir.Fill(obj="P1", style="blue"),
            ir.LabelPoint(p="A", text="A"),
        ],
    )
    tikz = _tikz(d)
    i_red, i_draw, i_green = (tikz.index("fill=red"), tikz.index("tkzDrawPolygon"),
                              tikz.index("fill=green"))
    assert i_red < i_draw < i_green
    assert tikz.index("fill=blue") < i_red     # ordinary fill layer stays behind
    assert tikz.index("\\tkzLabelPoint") > i_green


def test_tikz_undefined_point_warns_and_skips():
    d = _diagram(define=_square_defs(),
                     render=[ir.OrderedPolygon(points=["A", "B", "nope"], fill="red")])
    w: list[str] = []
    tikz = _tikz(d, w)
    assert "\\filldraw" not in tikz and any("nope" in m for m in w)


# ---------------------------------------------------------------------------
# Not-used => unchanged
# ---------------------------------------------------------------------------

def test_existing_recipe_render_is_pinned():
    """Byte-identity guard: a catalog recipe's SVG and TikZ are pinned against
    digests taken at the commit before ticket 19 (PYTHONHASHSEED=0)."""
    import hashlib
    import os
    from geometry_diagrams.recipe.catalog import load_recipe
    from geometry_diagrams.recipe.dsl import RecipeDSL
    from geometry_diagrams.recipe.lower import lower_to_ir

    if os.environ.get("PYTHONHASHSEED") != "0":
        pytest.skip("digests are pinned for PYTHONHASHSEED=0")
    d = lower_to_ir(RecipeDSL.model_validate(load_recipe("altitude").example))
    sym = compile_defs(d)
    got_svg = hashlib.sha256(ir_to_svg(d, sym, []).encode()).hexdigest()
    got_tikz = hashlib.sha256(ir_to_tikz(d, sym, warnings=[]).encode()).hexdigest()
    assert (got_svg, got_tikz) == PINNED_ALTITUDE


PINNED_ALTITUDE = (
    "4149bbef07e45324acb6f5bc6b6f7b0156a238f39e72f56a62860c0c5fc7305d",
    "2483fcf317f204f26fe4101ec5808ad2732e5c7483edbbf9558412f248282df1",
)


def test_ordered_polygon_not_in_llm_facing_schema():
    assert "ordered_polygon" not in str(ir.DiagramIR.model_json_schema())


# ---------------------------------------------------------------------------
# Registry hook can emit it
# ---------------------------------------------------------------------------

def test_lower_draw_hook_can_emit_the_primitive(monkeypatch):
    """A derived kind's lower_draw returns OrderedPolygons; both renderers
    paint them in the hook's order."""
    entry = REGISTRY.get(ir.RectangularPrism(id="P", origin="O", length=1, width=1, height=1))

    def hook(stmt, op, styles):
        return Lowering(ops=[ir.OrderedPolygon(points=["A", "B", "C", "D"], fill="#aa0000"),
                             ir.OrderedPolygon(points=["E", "F", "G", "H"], fill="#00aa00")])

    monkeypatch.setitem(REGISTRY._by_kind, "rectangular_prism", dataclasses.replace(entry, lower_draw=hook))
    d = _diagram(define=_square_defs() + [ir.PointFixed(id="O", x=5, y=5),
                                              ir.RectangularPrism(id="P", origin="O", length=1, width=1, height=1)],
                     render=[ir.Draw(obj="P")])
    svg = _svg(d)
    assert svg.index('fill="#aa0000"') < svg.index('fill="#00aa00"')
    tikz = _tikz(d)
    lines = _ordered_lines(tikz)
    assert len(lines) == 2 and lines[0].index("(0,0)") >= 0


# ---------------------------------------------------------------------------
# The prototype's irregular stack (painter order, exterior faces only)
# ---------------------------------------------------------------------------

DX, DY = 0.5 * math.cos(math.radians(30)), 0.5 * math.sin(math.radians(30))
COL = {"front": "#c3d6ef", "right": "#97b5dc", "top": "#e6eefa"}
H = [[3, 2, 4],
     [2, 1, 2],
     [1, 2, 1],
     [2, 1, 1]]


def stack_faces(heights=H, cull=True):
    """Painter-ordered [(face name, 4 lattice corners)] for a grid of column
    heights: farthest cube first, exterior faces only when ``cull``."""
    cubes = {(i, j, k) for i, row in enumerate(heights) for k, h in enumerate(row) for j in range(h)}

    def faces(c):
        i, j, k = c
        out = []
        if not cull or (i, j, k - 1) not in cubes:
            out.append(("front", [(i, j, k), (i + 1, j, k), (i + 1, j + 1, k), (i, j + 1, k)]))
        if not cull or (i + 1, j, k) not in cubes:
            out.append(("right", [(i + 1, j, k), (i + 1, j, k + 1), (i + 1, j + 1, k + 1), (i + 1, j + 1, k)]))
        if not cull or (i, j + 1, k) not in cubes:
            out.append(("top", [(i, j + 1, k), (i + 1, j + 1, k), (i + 1, j + 1, k + 1), (i, j + 1, k + 1)]))
        return out

    order = sorted(cubes, key=lambda c: (c[0] + c[1] - c[2], -c[2], c[0], c[1]))
    return [f for c in order for f in faces(c)]


def stack_diagram(heights=H, cull=True, ordered=True):
    """Hand-built stack: lattice-point defs plus one op per face in painter
    order. ``ordered=False`` is the pre-ticket workaround (Fill + Draw of a
    Polygon per face), which the renderers hoist into fills-then-strokes."""
    seq = stack_faces(heights, cull)
    ids: dict[tuple, str] = {}
    defs: list = []
    render: list = []
    for n, (name, quad) in enumerate(seq):
        pids = []
        for lat in quad:
            if lat not in ids:
                i, j, k = lat
                ids[lat] = f"p{len(ids)}"
                defs.append(ir.PointFixed(id=ids[lat], x=round(i + k * DX, 6), y=round(j + k * DY, 6)))
            pids.append(ids[lat])
        if ordered:
            render.append(ir.OrderedPolygon(points=pids, fill=COL[name], stroke="black", stroke_width=1.5))
        else:
            defs.append(ir.Polygon(id=f"f{n}", points=pids))
            render += [ir.Fill(obj=f"f{n}", style=COL[name], opacity=1.0), ir.Draw(obj=f"f{n}")]
    xs = [d.x for d in defs if isinstance(d, ir.PointFixed)]
    ys = [d.y for d in defs if isinstance(d, ir.PointFixed)]
    return _diagram(defs, render, canvas=ir.Canvas(xmin=min(xs) - .5, xmax=max(xs) + .5,
                                                   ymin=min(ys) - .5, ymax=max(ys) + .5))


def test_stack_fixture_matches_prototype_counts():
    assert len(stack_faces(cull=False)) > len(stack_faces(cull=True)) > 0


def test_svg_stack_has_one_polygon_per_face_in_painter_order():
    seq = stack_faces()
    polys = SVG_POLY.findall(_svg(stack_diagram()))
    assert len(polys) == len(seq)
    assert [re.search(r'fill="(#[0-9a-f]{6})"', p).group(1) for p in polys] == [COL[n] for n, _ in seq]
    # every polygon carries its own fill AND stroke, so no stroke can be
    # painted before a later face's fill
    assert all('stroke="black"' in p and 'stroke-width="1.5"' in p for p in polys)


def test_svg_stack_has_no_separate_fill_layer():
    svg = _svg(stack_diagram())
    assert 'data-role="fill"' not in svg


def test_svg_naive_workaround_hoists_every_fill_before_any_stroke():
    """The bug the primitive fixes: Fill + Draw per face puts all fills first,
    so far-face outlines are painted over near fills' neighbors."""
    svg = _svg(stack_diagram(ordered=False))
    fills = [m.start() for m in re.finditer(r'data-role="fill"', svg)]
    strokes = [m.start() for m in re.finditer(r'data-ir-id="f\d+"(?![^>]*data-role="fill")', svg)]
    assert fills and strokes and max(fills) < min(strokes)


def test_tikz_stack_one_filldraw_per_face_in_painter_order():
    seq = stack_faces()
    tikz = _tikz(stack_diagram())
    lines = _ordered_lines(tikz)
    assert len(lines) == len(seq)
    by_rgb = {(int(r), int(g), int(b)): n for n, r, g, b in
              re.findall(r"\\definecolor\{(\w+)\}\{RGB\}\{(\d+),(\d+),(\d+)\}", tikz)}
    names = [by_rgb[tuple(int(COL[n][i:i + 2], 16) for i in (1, 3, 5))] for n, _ in seq]
    assert [re.search(r"fill=(\w+)", ln).group(1) for ln in lines] == names
    assert "\\tkzDrawPolygon" not in tikz and not re.search(r"\\fill[\[ ]", tikz)


# ---------------------------------------------------------------------------
# TikZ compile (container, else skipped) and local lualatex fallback
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not renderer_available(), reason="TikZ renderer container not running")
def test_tikz_stack_compiles_in_container():
    from geometry_diagrams.util.tikz_renderer import render_tikz

    svg = render_tikz(_tikz(stack_diagram()))
    assert svg.count("<path") >= len(stack_faces())
    assert "#c3d6ef" in svg.lower()


@pytest.mark.skipif(not renderer_available(), reason="TikZ renderer container not running")
def test_tikz_color_forms_compile_in_container():
    from geometry_diagrams.util.tikz_renderer import render_tikz

    svg = render_tikz(_tikz(_two_overlapping("#336699", "lightblue"))).lower()
    # dvisvgm abbreviates #336699 to #369
    assert "#369" in svg and "#add8e6" in svg


def test_svg_ordered_polygon_edges_register_for_label_nudging(monkeypatch):
    """Label nudging pushes text off every drawn line; an OrderedPolygon's
    outline must be registered as obstacles too (one segment per edge, closing
    edge included), the same way an ordinary drawn polygon's edges are."""
    import geometry_diagrams.ir.to_svg as to_svg_mod

    captured: list[tuple[float, float, float, float]] = []
    original = to_svg_mod._nudge_labels_from_lines

    def spy(labels, drawn_segments, *args):
        if not captured:
            captured.extend(drawn_segments)
        return original(labels, drawn_segments, *args)

    monkeypatch.setattr(to_svg_mod, "_nudge_labels_from_lines", spy)
    d = _diagram(
        _square_defs(),
        [ir.OrderedPolygon(points=["A", "B", "C", "D"], fill="#112233")],
    )
    _svg(d)
    assert len(captured) == 4


# ---------------------------------------------------------------------------
# stroke_width default: each backend's ordinary draw width
# ---------------------------------------------------------------------------

def test_default_stroke_width_is_each_backends_ordinary_draw_width():
    """None (the default) means the width an ordinary Draw gets: 1.5 px in
    SVG; in TikZ tkz-euclide's own ``line style`` (the style its draw macros
    use), never a hard-coded number that could drift from it."""
    assert ir.OrderedPolygon(points=["A", "B", "C"], fill="red").stroke_width is None
    d = _diagram(_square_defs() + [ir.Segment(id="s", a="A", b="C")],
                 [ir.OrderedPolygon(points=["A", "B", "C", "D"], fill="red"), ir.Draw(obj="s")])
    svg = _svg(d)
    (poly,) = SVG_POLY.findall(svg)
    assert 'stroke-width="1.5"' in poly
    assert re.search(r'data-ir-id="s"[^>]*stroke-width="1.5"', svg)
    (line,) = _ordered_lines(_tikz(d))
    assert line.startswith("\\filldraw[line style,") and "line width" not in line


@pytest.mark.parametrize("width,svg_w,tikz_opt", [
    (2.5, "2.5", "line width=2.5pt"), ("thick", "2.5", "thick"), ("thin", "0.75", "thin"),
])
def test_explicit_stroke_width_is_honored(width, svg_w, tikz_opt):
    d = _diagram(_square_defs(), [ir.OrderedPolygon(points=["A", "B", "C", "D"], fill="red", stroke_width=width)])
    (poly,) = SVG_POLY.findall(_svg(d))
    assert f'stroke-width="{svg_w}"' in poly
    (line,) = _ordered_lines(_tikz(d))
    assert tikz_opt in line.split("]")[0]
