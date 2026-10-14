"""Unit-cube prisms (solids ticket 12): gridlines on the three visible faces.

Expected gridline geometry is written out from the DOCUMENTED axis images of
each view (not recomputed from the projection code). Prism coordinates are
(length, height, width); the visible faces are front (width=0), right
(length=max) or left (length=0), and top (height=max).
"""
from __future__ import annotations

import asyncio
import math
import re
import time
import xml.etree.ElementTree as ET

import pytest
import sympy.geometry as spg

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.derived import REGISTRY, effective_defs
from geometry_diagrams.ir.errors import IRCompileError
from geometry_diagrams.ir.queries import list_objects
from geometry_diagrams.ir.renderer import SVGRenderer, TikZRenderer
from geometry_diagrams.ir.to_svg import ir_to_svg
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline
from tests.availability import renderer_available

C30, S30 = math.cos(math.radians(30)), 0.5
OX, OY = 1.0, 2.0

# view kwargs -> (length, height, width) axis images, visible faces as
# (fixed axis index, "min"|"max")
VIEWS = {
    "oblique": (
        dict(view="oblique", depth_angle=45, depth_scale=0.5),
        ((1, 0), (0, 1), (0.5 * math.cos(math.pi / 4), 0.5 * math.sin(math.pi / 4))),
        [(2, 0), (0, 1), (1, 1)],
    ),
    "oblique_left": (
        dict(view="oblique", side="left", depth_angle=45, depth_scale=0.5),
        ((1, 0), (0, 1), (-0.5 * math.cos(math.pi / 4), 0.5 * math.sin(math.pi / 4))),
        [(2, 0), (0, 0), (1, 1)],
    ),
    "isometric": (
        dict(view="isometric"),
        ((C30, -S30), (0, 1), (C30, S30)),
        [(2, 0), (0, 1), (1, 1)],
    ),
    "isometric_left": (
        dict(view="isometric", side="left"),
        ((C30, S30), (0, 1), (-C30, S30)),
        [(2, 0), (0, 0), (1, 1)],
    ),
}
DIMS = [(4, 3, 2), (2, 5, 4), (1, 1, 1), (3, 1, 6)]  # (length, width, height)


def _diagram(length, width, height, render=None, styles=None, **kw) -> ir.DiagramIR:
    return ir.DiagramIR(
        define=[
            ir.PointFixed(id="O", x=OX, y=OY),
            ir.RectangularPrism(
                id="P", origin="O", length=length, width=width, height=height, unit_cubes=True, **kw
            ),
        ],
        render=render if render is not None else [ir.Draw(obj="P")],
        styles=styles or {},
    )


def _project(axes, l, h, w):
    return (
        OX + l * axes[0][0] + h * axes[1][0] + w * axes[2][0],
        OY + l * axes[0][1] + h * axes[1][1] + w * axes[2][1],
    )


def _expected_gridlines(view_name, length, width, height):
    """{face: set of frozenset of rounded 2D endpoints} from the documented rule."""
    _, axes, visible = VIEWS[view_name]
    dims = (length, height, width)
    out = {}
    for fixed, side in visible:
        u, v = [i for i in range(3) if i != fixed]
        face = set()

        def pt(a, b):
            c = [0, 0, 0]
            c[fixed] = dims[fixed] if side == 1 else 0
            c[u], c[v] = a, b
            return tuple(round(x, 6) for x in _project(axes, *c))

        for k in range(1, dims[u]):
            face.add(frozenset({pt(k, 0), pt(k, dims[v])}))
        for j in range(1, dims[v]):
            face.add(frozenset({pt(0, j), pt(dims[u], j)}))
        out[(fixed, side)] = face
    return out


def _grid_ids(d):
    return [s.id for s in effective_defs(d) if s.id.startswith("__P_g")]


def _compiled_gridlines(d):
    sym = compile_defs(d)
    segs = [sym[i] for i in _grid_ids(d) if isinstance(sym[i], spg.Segment)]
    return {
        frozenset({tuple(round(float(c), 6) for c in (p.x, p.y)) for p in (s.p1, s.p2)})
        for s in segs
    }, len(segs)


@pytest.mark.parametrize("view_name", list(VIEWS))
@pytest.mark.parametrize("dims", DIMS)
def test_gridlines_are_the_interior_cuts_of_each_visible_face(view_name, dims):
    length, width, height = dims
    d = _diagram(length, width, height, **VIEWS[view_name][0])
    got, n = _compiled_gridlines(d)
    expected = _expected_gridlines(view_name, length, width, height)
    want = set().union(*expected.values())
    assert got == want
    assert n == len(want)  # no duplicated lines
    # counts per face: front (L-1)+(H-1), side (W-1)+(H-1), top (L-1)+(W-1)
    assert n == (length - 1 + height - 1) + (width - 1 + height - 1) + (length - 1 + width - 1)


def test_isometric_2x4x5_has_two_columns_on_front_and_four_on_right():
    d = _diagram(2, 4, 5, **VIEWS["isometric"][0])
    expected = _expected_gridlines("isometric", 2, 4, 5)
    front, right = expected[(2, 0)], expected[(0, 1)]
    # front: length 2 -> 1 vertical line, height 5 -> 4 horizontal lines
    assert len(front) == 1 + 4
    # right: width 4 -> 3 vertical lines (parallel to the height axis), 4 horizontal
    assert len(right) == 3 + 4
    got, _ = _compiled_gridlines(d)
    assert front <= got and right <= got
    # columns are the image-vertical lines (parallel to the height axis)
    def vertical(lines):
        return [s for s in lines if len({p[0] for p in s}) == 1]

    assert len(vertical(front)) == 1  # two columns on the front face
    assert len(vertical(right)) == 3  # four columns on the right face


@pytest.mark.parametrize("view_name", list(VIEWS))
def test_svg_has_the_gridlines_thin_and_gray(view_name):
    d = _diagram(3, 2, 2, **VIEWS[view_name][0])
    root = ET.fromstring(ir_to_svg(d, compile_defs(d)))
    grid = [
        el for el in root.iter()
        if el.tag.endswith("line") and (el.get("data-ir-id") or "").startswith("__P_g")
    ]
    assert len(grid) == (2 + 1) + (1 + 1) + (2 + 1)
    for el in grid:
        assert el.get("stroke") == "gray"
        assert el.get("stroke-width") == "0.75"
        assert not el.get("stroke-dasharray")
    polys = {
        el.get("data-ir-id") for el in root.iter()
        if el.tag.endswith("polygon") and el.get("data-role") != "fill" and el.get("data-ir-id")
    }
    assert len(polys) == 3  # face outlines still drawn once each


def test_svg_face_fills_stay_under_the_gridlines():
    d = _diagram(2, 2, 2, render=[ir.Fill(obj="P_top", opacity=0.4), ir.Draw(obj="P")])
    root = ET.fromstring(ir_to_svg(d, compile_defs(d)))
    order = [el for el in root.iter() if el.get("data-role") == "fill" or (el.get("data-ir-id") or "").startswith("__P_g")]
    roles = ["fill" if el.get("data-role") == "fill" else "grid" for el in order]
    assert roles.count("fill") == 1 and "grid" in roles
    assert roles.index("fill") < roles.index("grid")


def test_gridline_style_does_not_take_the_authors_style():
    styles = {"bold": {"color": "blue", "thick": True}}
    d = _diagram(2, 2, 2, render=[ir.Draw(obj="P", style="bold")], styles=styles, view="isometric")
    root = ET.fromstring(ir_to_svg(d, compile_defs(d)))
    for el in root.iter():
        if el.tag.endswith("line") and (el.get("data-ir-id") or "").startswith("__P_g"):
            assert el.get("stroke") == "gray"
        if el.tag.endswith("polygon") and el.get("data-role") != "fill" and el.get("data-ir-id"):
            assert el.get("stroke") == "blue"
    assert d.styles == styles  # authored styles untouched


def test_no_gridlines_without_unit_cubes_or_without_a_draw():
    plain = ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=1, y=2),
                ir.RectangularPrism(id="P", origin="O", length=3, width=2, height=2)],
        render=[ir.Draw(obj="P")],
    )
    assert "__P_g" not in ir_to_svg(plain, compile_defs(plain))
    undrawn = _diagram(3, 2, 2, render=[])
    assert "<line" not in ir_to_svg(undrawn, compile_defs(undrawn))


@pytest.mark.parametrize("view_name", list(VIEWS))
def test_tikz_text_has_thin_gray_gridline_segments_per_face(view_name):
    d = _diagram(3, 2, 4, **VIEWS[view_name][0])
    tikz = ir_to_tikz(d, compile_defs(d))
    segs = re.findall(r"\\tkzDrawSegment(\[[^\]]*\])?\(([^)]*)\)", tikz)
    assert len(segs) == (2 + 3) + (1 + 3) + (2 + 1)
    for opts, _ in segs:
        assert set(opts.strip("[]").split(",")) == {"color=gray", "thin"}
    assert len(re.findall(r"\\tkzDrawPolygon", tikz)) == 3
    assert "unhandled" not in tikz and "dashed" not in tikz


def test_gridline_points_and_segments_are_hidden_from_the_object_listing_and_authored_ir():
    d = _diagram(3, 2, 2)
    authored = d.model_dump()
    assert _grid_ids(d)
    assert [s.id for s in d.define] == ["O", "P"]
    listing = list_objects(compile_defs(d))
    assert not any(k.startswith("__") for k in listing)
    result = asyncio.run(run_ir_pipeline(d, SVGRenderer()))
    assert result.diagram_ir.model_dump() == authored


@pytest.mark.parametrize("hidden", ["__P_g0", "__P_gp0"])
@pytest.mark.parametrize("kind", ["point", "segment"])
def test_authored_definition_with_a_gridline_id_is_a_typed_error(hidden, kind):
    probe = _grid_ids(_diagram(3, 3, 3))
    assert probe  # the spelling below must really be a synthesized id
    ids = {s.id for s in effective_defs(_diagram(3, 3, 3))}
    assert hidden in ids
    extra = (
        ir.PointFixed(id=hidden, x=0, y=0) if kind == "point" else ir.Segment(id=hidden, a="O", b="P_v111")
    )
    d = _diagram(3, 3, 3)
    d.define.append(extra)
    with pytest.raises(IRCompileError):
        compile_defs(d)
    with pytest.raises(IRCompileError):
        REGISTRY.check_exclusive_ids(d.define)
    with pytest.raises(IRCompileError):
        ir_to_svg(d, {})


def test_large_prism_renders_within_a_few_seconds_and_under_the_op_cap():
    from geometry_diagrams.pydsl.builder import DEFAULT_OP_CAP

    d = _diagram(8, 3, 7, view="isometric")
    start = time.perf_counter()
    sym = compile_defs(d)
    svg = ir_to_svg(d, sym)
    elapsed = time.perf_counter() - start
    n_defs = len(effective_defs(d))
    assert n_defs < DEFAULT_OP_CAP
    assert elapsed < 10
    assert svg.count("data-ir-id=\"__P_g") >= (7 + 6) + (2 + 6) + (7 + 2)


@pytest.mark.skipif(not renderer_available(), reason="TikZ renderer container not running")
@pytest.mark.parametrize("view_name", list(VIEWS))
@pytest.mark.parametrize("dims", [(2, 4, 5), (8, 3, 7)])
def test_tikz_compile_smoke_unit_cubes(view_name, dims):
    length, width, height = dims
    d = _diagram(length, width, height, **VIEWS[view_name][0])
    warnings: list[str] = []
    result = TikZRenderer().render(d, compile_defs(d), warnings=warnings)
    assert "<svg" in result.output
    assert warnings == []
