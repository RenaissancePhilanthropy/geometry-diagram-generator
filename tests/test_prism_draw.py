"""Drawing prisms (solids ticket 09): the synthesized edges and faces with
their public ids, the draw lowering (three visible face outlines and three
dashed hidden edges at the hidden corner) through both renderers' entry
functions for every view, style preservation, the derived-id collision error,
the lowering hook's ordered-sequence contract, and the authored IR / eval
metrics staying free of derived definitions.

Expected faces and hidden corners are the DOCUMENTED rule, written out per
view (not recomputed from the projection code): right-hand views show front,
right and top and hide corner (0,0,1) (back-bottom-left); side=left shows
front, left and top and hides corner (1,0,1) (back-bottom-right). Corner bits
are (length, height, width).
"""
from __future__ import annotations

import asyncio
import dataclasses
import re
import xml.etree.ElementTree as ET

import pytest
import sympy.geometry as spg

from evals.ir_diagnostics import classify_ir
from evals.run import _run_structural_checks
from geometry_diagrams.ir import ir
from geometry_diagrams.ir.derived import (
    REGISTRY,
    Lowering,
    effective_defs,
    effective_diagram,
    lower_render,
)
from geometry_diagrams.ir.errors import IRCompileError
from geometry_diagrams.ir.renderer import SVGRenderer, TikZRenderer
from geometry_diagrams.ir.to_svg import ir_to_svg
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline
from tests.availability import renderer_available

FACES = ("front", "back", "left", "right", "top", "bottom")
# Documented corner sets of each face (bits are length, height, width).
FACE_CORNERS = {
    "front": {"000", "100", "110", "010"},
    "back": {"001", "101", "111", "011"},
    "left": {"000", "010", "011", "001"},
    "right": {"100", "110", "111", "101"},
    "bottom": {"000", "100", "101", "001"},
    "top": {"010", "110", "111", "011"},
}

# (view kwargs, visible faces, hidden corner bits)
VIEWS = {
    "oblique": (dict(view="oblique"), {"front", "right", "top"}, "001"),
    "oblique_left": (dict(view="oblique", side="left"), {"front", "left", "top"}, "101"),
    "isometric": (dict(view="isometric"), {"front", "right", "top"}, "001"),
    "isometric_left": (dict(view="isometric", side="left"), {"front", "left", "top"}, "101"),
}


def _hidden_edges(corner: str) -> set[frozenset[str]]:
    """The three edges meeting at ``corner``, as corner-bit pairs."""
    out = set()
    for axis in range(3):
        other = list(corner)
        other[axis] = "1" if corner[axis] == "0" else "0"
        out.add(frozenset({corner, "".join(other)}))
    return out


def _edge_id(prism: str, pair: frozenset[str]) -> str:
    lo, hi = sorted(pair)
    return f"{prism}_e_{lo}_{hi}"


def _prism(**overrides) -> ir.RectangularPrism:
    fields = dict(id="P", origin="O", length=4, width=3, height=2)
    fields.update(overrides)
    return ir.RectangularPrism(**fields)


def _diagram(prism=None, render=None, extra=(), styles=None) -> ir.DiagramIR:
    return ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=1, y=2), prism or _prism(), *extra],
        render=render if render is not None else [ir.Draw(obj="P")],
        styles=styles or {},
    )


def _svg(diagram: ir.DiagramIR) -> ET.Element:
    return ET.fromstring(ir_to_svg(diagram, compile_defs(diagram)))


def _stroked_polygons(root: ET.Element) -> dict[str, ET.Element]:
    return {
        el.get("data-ir-id"): el
        for el in root.iter()
        if el.tag.endswith("polygon") and el.get("data-role") != "fill" and el.get("data-ir-id")
    }


def _lines(root: ET.Element) -> dict[str, ET.Element]:
    return {el.get("data-ir-id"): el for el in root.iter() if el.tag.endswith("line") and el.get("data-ir-id")}


def _dashed(el: ET.Element) -> bool:
    return bool(el.get("stroke-dasharray"))


def _bits_of(names: str, prefix: str = "P_v") -> set[str]:
    return {n[len(prefix):] for n in names.split(",")}


# --- public ids through the effective view -----------------------------------

def test_prism_synthesizes_twelve_edges_and_six_faces_with_public_ids():
    sym = compile_defs(_diagram())
    faces = {f"P_{name}" for name in FACES}
    edges = set()
    bits = [f"{a}{b}{c}" for a in "01" for b in "01" for c in "01"]
    for p in bits:
        for q in bits:
            if p < q and sum(x != y for x, y in zip(p, q)) == 1:
                edges.add(f"P_e_{p}_{q}")
    assert len(edges) == 12
    for fid in faces:
        assert isinstance(sym[fid], spg.Polygon), fid
    for eid in edges:
        assert isinstance(sym[eid], spg.Segment), eid
    view_ids = {d.id for d in effective_defs(_diagram())}
    assert faces | edges <= view_ids


def test_face_and_edge_endpoints_follow_renamed_corners():
    names = list("ABCDEFGH")  # product order 000, 001, 010, 011, 100, 101, 110, 111
    d = _diagram(prism=_prism(vertex_names=names))
    view = {s.id: s for s in effective_defs(d)}
    bit_to_name = dict(zip(["000", "001", "010", "011", "100", "101", "110", "111"], names))
    assert {view["P_e_000_100"].a, view["P_e_000_100"].b} == {"A", "E"}
    assert set(view["P_bottom"].points) == {bit_to_name[b] for b in FACE_CORNERS["bottom"]}


# --- SVG lowering, every view --------------------------------------------------

@pytest.mark.parametrize("view_name", list(VIEWS))
def test_svg_draw_shows_three_visible_faces_and_three_dashed_hidden_edges(view_name):
    kwargs, visible, hidden_corner = VIEWS[view_name]
    root = _svg(_diagram(prism=_prism(**kwargs)))

    polys = _stroked_polygons(root)
    assert set(polys) == {f"P_{f}" for f in visible}
    for fid, el in polys.items():
        assert _bits_of(el.get("data-vertices")) == FACE_CORNERS[fid[2:]]
        assert not _dashed(el)

    dashed = {lid: el for lid, el in _lines(root).items() if _dashed(el)}
    expected = _hidden_edges(hidden_corner)
    assert set(dashed) == {_edge_id("P", pair) for pair in expected}
    for el in dashed.values():
        assert f"P_v{hidden_corner}" in el.get("data-endpoints").split(",")
    # nothing else is drawn as a line
    assert set(_lines(root)) == set(dashed)


def test_svg_unit_cubes_draws_only_the_three_visible_faces():
    root = _svg(_diagram(prism=_prism(unit_cubes=True, view="isometric")))
    assert set(_stroked_polygons(root)) == {"P_front", "P_right", "P_top"}
    assert not any(_dashed(el) for el in root.iter())


def test_svg_solid_prism_is_drawn_and_filled_through_face_ids_without_hidden_edges():
    faces = ["P_front", "P_right", "P_top"]
    render = [ir.Fill(obj=f, opacity=0.4) for f in faces] + [ir.Draw(obj=f) for f in faces]
    root = _svg(_diagram(render=render))
    assert set(_stroked_polygons(root)) == set(faces)
    fills = {el.get("data-ir-id") for el in root.iter() if el.get("data-role") == "fill"}
    assert fills == set(faces)
    assert not any(_dashed(el) for el in root.iter())


def test_svg_draw_through_the_pipeline_renders_the_prism():
    result = asyncio.run(run_ir_pipeline(_diagram(), SVGRenderer()))
    root = ET.fromstring(result.svg)
    assert set(_stroked_polygons(root)) == {"P_front", "P_right", "P_top"}
    assert sum(_dashed(el) for el in _lines(root).values()) == 3


# --- style preservation -------------------------------------------------------

def test_named_style_is_kept_on_faces_and_merged_with_dashed_on_hidden_edges():
    styles = {"bold": {"color": "blue", "thick": True}}
    root = _svg(_diagram(render=[ir.Draw(obj="P", style="bold")], styles=styles))
    for el in _stroked_polygons(root).values():
        assert el.get("stroke") == "blue" and el.get("stroke-width") == "2.5"
        assert not _dashed(el)
    dashed = [el for el in _lines(root).values() if _dashed(el)]
    assert len(dashed) == 3
    for el in dashed:
        assert el.get("stroke") == "blue" and el.get("stroke-width") == "2.5"


def test_bare_color_style_is_kept_on_faces_and_hidden_edges():
    root = _svg(_diagram(render=[ir.Draw(obj="P", style="red")]))
    assert {el.get("stroke") for el in _stroked_polygons(root).values()} == {"red"}
    dashed = [el for el in _lines(root).values() if _dashed(el)]
    assert len(dashed) == 3 and {el.get("stroke") for el in dashed} == {"red"}


def test_dotted_author_style_still_gives_dashed_hidden_edges():
    styles = {"dots": {"dotted": True}}
    root = _svg(_diagram(render=[ir.Draw(obj="P", style="dots")], styles=styles))
    dashed = [el for el in _lines(root).values() if _dashed(el)]
    assert {el.get("stroke-dasharray") for el in dashed} == {"6,3"}


def test_lowering_leaves_the_authored_render_and_styles_unchanged():
    styles = {"bold": {"color": "blue", "thick": True}}
    d = _diagram(render=[ir.Draw(obj="P", style="bold")], styles=styles)
    before = d.model_copy(deep=True)
    ir_to_svg(d, compile_defs(d))
    ir_to_tikz(d, compile_defs(d))
    assert d == before


# --- TikZ text (no container needed) ----------------------------------------

_POLY = re.compile(r"\\tkzDrawPolygon(\[[^\]]*\])?\(([^)]*)\)")
_SEG = re.compile(r"\\tkzDrawSegment(\[[^\]]*\])?\(([^)]*)\)")


@pytest.mark.parametrize("view_name", list(VIEWS))
def test_tikz_text_draws_three_visible_faces_and_three_dashed_hidden_edges(view_name):
    kwargs, visible, hidden_corner = VIEWS[view_name]
    d = _diagram(prism=_prism(**kwargs))
    tikz = ir_to_tikz(d, compile_defs(d))

    polys = _POLY.findall(tikz)
    assert len(polys) == 3
    assert {frozenset(_bits_of(pts)) for _, pts in polys} == {frozenset(FACE_CORNERS[f]) for f in visible}
    assert all("dashed" not in (opts or "") for opts, _ in polys)

    segs = _SEG.findall(tikz)
    dashed = [pts for opts, pts in segs if "dashed" in (opts or "")]
    assert len(dashed) == 3 and len(segs) == 3
    assert {frozenset(_bits_of(pts)) for pts in dashed} == _hidden_edges(hidden_corner)
    assert "unhandled" not in tikz


def test_tikz_text_keeps_the_author_style_on_faces_and_hidden_edges():
    styles = {"bold": {"color": "blue", "thick": True}}
    d = _diagram(render=[ir.Draw(obj="P", style="bold")], styles=styles)
    tikz = ir_to_tikz(d, compile_defs(d))
    for opts, _ in _POLY.findall(tikz):
        assert set(opts.strip("[]").split(",")) == {"color=blue", "thick"}
    seg_opts = [set(opts.strip("[]").split(",")) for opts, _ in _SEG.findall(tikz)]
    assert seg_opts == [{"color=blue", "thick", "dashed"}] * 3


def test_tikz_text_unit_cubes_has_no_hidden_edges():
    d = _diagram(prism=_prism(unit_cubes=True, view="isometric"))
    tikz = ir_to_tikz(d, compile_defs(d))
    assert len(_POLY.findall(tikz)) == 3
    assert "dashed" not in tikz


@pytest.mark.skipif(not renderer_available(), reason="TikZ renderer container not running")
@pytest.mark.parametrize("view_name", list(VIEWS))
@pytest.mark.parametrize("unit_cubes", [False, True])
def test_tikz_compile_smoke_for_each_view(view_name, unit_cubes):
    kwargs, _, _ = VIEWS[view_name]
    styles = {"bold": {"color": "blue", "thick": True}}
    d = _diagram(
        prism=_prism(unit_cubes=unit_cubes, **kwargs),
        render=[ir.Fill(obj="P_top", opacity=0.3), ir.Draw(obj="P", style="bold")],
        styles=styles,
    )
    warnings: list[str] = []
    result = TikZRenderer().render(d, compile_defs(d), warnings=warnings)
    assert "<svg" in result.output
    assert warnings == []


# --- derived-id collisions ------------------------------------------------------

@pytest.mark.parametrize(
    "authored",
    [
        ir.Polygon(id="P_front", points=["O", "P_v100", "P_v110"]),
        ir.Segment(id="P_e_000_100", a="O", b="P_v111"),
        ir.PointFixed(id="P_top", x=0, y=0),
        ir.PointFixed(id="P_v011", x=0, y=0),
    ],
    ids=["face", "edge", "point-named-like-face", "corner"],
)
def test_authored_definition_named_like_a_derived_id_is_a_typed_error(authored):
    d = _diagram(extra=[authored])
    with pytest.raises(IRCompileError) as exc:
        compile_defs(d)
    assert authored.id in str(exc.value)
    with pytest.raises(IRCompileError):
        asyncio.run(run_ir_pipeline(d, SVGRenderer()))


def test_collision_is_raised_by_the_renderers_entry_functions_too():
    good = _diagram()
    sym = compile_defs(good)
    bad = _diagram(extra=[ir.Segment(id="P_e_000_001", a="O", b="P_v111")])
    with pytest.raises(IRCompileError):
        ir_to_svg(bad, sym)
    with pytest.raises(IRCompileError):
        ir_to_tikz(bad, sym)


def test_corner_name_equal_to_another_prisms_face_id_is_a_typed_error():
    names = ["P_front", *[f"Q{i}" for i in range(7)]]
    d = _diagram(extra=[ir.RectangularPrism(id="Q", origin="O", length=1, width=1, height=1, vertex_names=names)])
    with pytest.raises(IRCompileError, match="P_front"):
        compile_defs(d)


def test_check_exclusive_ids_covers_synthesized_ids():
    names = ["P_e_000_001", *[f"Q{i}" for i in range(7)]]
    stmts = [_prism(), ir.RectangularPrism(id="Q", origin="O", length=1, width=1, height=1, vertex_names=names)]
    with pytest.raises(IRCompileError, match="P_e_000_001"):
        REGISTRY.check_exclusive_ids(stmts)


def test_effective_view_is_idempotent_on_an_already_effective_diagram():
    d = _diagram()
    once = effective_diagram(d)
    assert [s.id for s in effective_defs(once)] == [s.id for s in once.define]
    assert effective_defs(once) == once.define


def test_incremental_builder_rejects_an_authored_id_named_like_a_derived_one():
    with new_builder_context():
        b = get_builder()
        b._add(ir.PointFixed(id="O", x=0, y=0))
        b._add(_prism())
        b._advance_sym()
        b._add(ir.Segment(id="P_front", a="O", b="P_v111"))
        with pytest.raises(IRCompileError, match="P_front"):
            b._advance_sym()


# --- the lowering hook's ordered-sequence contract ----------------------------

@dataclasses.dataclass
class _FutureOrderedPolygon:
    """Stand-in for a render op type that does not exist yet (ticket 19)."""

    kind: str
    obj: str


def _ordered_lowering(stmt, op, styles):
    return Lowering(
        ops=[
            ir.Draw(obj=f"{stmt.id}_back", style="s1"),
            ir.Fill(obj=f"{stmt.id}_back", opacity=0.5),
            _FutureOrderedPolygon(kind="ordered_polygon", obj=f"{stmt.id}_left"),
            ir.Draw(obj=f"{stmt.id}_top", style="s2"),
            ir.Draw(obj=f"{stmt.id}_front", style="s1"),
        ],
        styles={"s1": {"color": "red"}, "s2": {"color": "green"}},
    )


@pytest.fixture
def ordered_lowering(monkeypatch):
    entry = REGISTRY._by_kind["rectangular_prism"]
    monkeypatch.setitem(
        REGISTRY._by_kind, "rectangular_prism", dataclasses.replace(entry, lower_draw=_ordered_lowering)
    )


def test_lowering_hook_passes_an_ordered_mixed_sequence_through_in_place(ordered_lowering):
    d = _diagram(render=[ir.DrawPoints(points=["O"]), ir.Draw(obj="P"), ir.DrawPoints(points=["P_v111"])])
    lowered = lower_render(effective_diagram(d))
    kinds = [(op.kind, getattr(op, "obj", None)) for op in lowered.render]
    assert kinds == [
        ("draw_points", None),
        ("draw", "P_back"),
        ("fill", "P_back"),
        ("ordered_polygon", "P_left"),
        ("draw", "P_top"),
        ("draw", "P_front"),
        ("draw_points", None),
    ]
    assert lowered.styles["s1"] == {"color": "red"}


def test_lowered_sequence_order_survives_both_renderers(ordered_lowering, monkeypatch):
    # Renderers ignore the future op type today; drop it here and check the
    # same-kind draws keep the hook's order (renderers sort fills before
    # strokes, a stable sort, so cross-kind order is NOT yet honored).
    def without_future(stmt, op, styles):
        low = _ordered_lowering(stmt, op, styles)
        return Lowering(ops=[o for o in low.ops if not isinstance(o, _FutureOrderedPolygon)], styles=low.styles)

    entry = REGISTRY._by_kind["rectangular_prism"]
    monkeypatch.setitem(REGISTRY._by_kind, "rectangular_prism", dataclasses.replace(entry, lower_draw=without_future))
    d = _diagram()
    sym = compile_defs(d)
    root = ET.fromstring(ir_to_svg(d, sym))
    stroked = [el.get("data-ir-id") for el in root.iter()
               if el.tag.endswith("polygon") and el.get("data-role") != "fill"]
    assert stroked == ["P_back", "P_top", "P_front"]
    colors = [el.get("stroke") for el in root.iter() if el.tag.endswith("polygon") and el.get("data-role") != "fill"]
    assert colors == ["red", "green", "red"]

    tikz = ir_to_tikz(d, sym)
    drawn = [frozenset(_bits_of(pts)) for _, pts in _POLY.findall(tikz)]
    assert drawn == [frozenset(FACE_CORNERS[f]) for f in ("back", "top", "front")]


# --- authored IR and eval metrics never see derived definitions ---------------

def test_pipeline_keeps_authored_ir_and_eval_metrics_free_of_derived_defs():
    d = _diagram()
    authored = d.model_dump()
    result = asyncio.run(run_ir_pipeline(d, SVGRenderer()))
    assert result.diagram_ir.model_dump() == authored
    assert [s.id for s in result.diagram_ir.define] == ["O", "P"]
    assert classify_ir(result.diagram_ir) == classify_ir(ir.DiagramIR(define=[ir.PointFixed(id="O", x=1, y=2)]))
    checks = _run_structural_checks(
        [{"name": "poly", "type": "polygon_count", "args": {"min": 1}}],
        result.diagram_ir.model_dump(),
        None,
    )
    assert checks["poly"]["passed"] is False


# --- fix round 1: exclusivity check idempotent on an effective list ----------

def test_compile_of_an_already_effective_diagram_matches_the_authored_compile():
    d = _diagram()
    again, once = compile_defs(effective_diagram(d)), compile_defs(d)
    assert set(again) == set(once)
    for key, obj in once.items():
        if key == "P":  # the Prism object has identity equality
            assert (again[key].length, again[key].width, again[key].height) == (obj.length, obj.width, obj.height)
            assert again[key].corners == obj.corners
        else:
            assert again[key] == obj, key


def test_exclusivity_check_on_an_effective_list_raises_only_for_genuine_collisions():
    d = _diagram()
    REGISTRY.check_exclusive_ids(effective_defs(d))  # no false collision
    clash = ir.PointFixed(id="P_v011", x=0, y=0)
    authored = [*d.define, clash]
    with pytest.raises(IRCompileError, match="P_v011"):
        REGISTRY.check_exclusive_ids(authored)
    effective_with_clash = [*effective_defs(d), clash]
    with pytest.raises(IRCompileError, match="P_v011"):
        REGISTRY.check_exclusive_ids(effective_with_clash)
