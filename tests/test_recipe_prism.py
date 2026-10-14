"""Recipe surface for rectangular prisms (solids ticket 14): the `prism` op
lowering to the IR definition, the auto canvas, the segment helper reusing the
prism's own edge, fills/labels/draws/checks on prism ids, the gated docs
(byte-identical with solids off) and the pre-lowering rejection with solids off."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from geometry_diagrams.features import FeatureNotEnabledError
from geometry_diagrams.ir import ir
from geometry_diagrams.ir.checks import run_checks
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz
from geometry_diagrams.recipe.catalog import (
    DSL_DOCS, build_generation_prompt, build_generation_prompt_static_block, dsl_docs_for,
    load_recipe,
)
from geometry_diagrams.recipe.dsl import RecipeDSL, reject_disabled_ops
from geometry_diagrams.recipe.lower import LoweringError, lower_to_ir
from geometry_diagrams.strategies.recipe import RecipeStrategy

SOLIDS = frozenset({"solids"})
_PRE = json.loads((Path(__file__).parent / "recipe_prompt_pre_solids.json").read_text())


def _dsl(extra_ops=(), annotations=None, checks=(), prism=None) -> RecipeDSL:
    p = {"op": "prism", "id": "P", "origin": "O", "length": 4, "width": 3, "height": 2}
    p.update(prism or {})
    return RecipeDSL.model_validate({
        "construction": [{"op": "point", "id": "O", "coords": [0, 0]}, p, *extra_ops],
        "annotations": annotations or {},
        "checks": list(checks),
    })


def _prism_def(diagram: ir.DiagramIR) -> ir.RectangularPrism:
    return next(d for d in diagram.define if isinstance(d, ir.RectangularPrism))


# --- the op lowers to the IR definition ---------------------------------------

def test_prism_op_lowers_to_the_ir_definition_with_every_field():
    d = lower_to_ir(_dsl(prism={
        "length": 5, "width": "w", "height": 2.5, "unit_cubes": False, "view": "oblique",
        "depth_angle": 30, "depth_scale": 0.5, "side": "left",
        "vertex_names": list("ABCDEFGH"),
    }))
    p = _prism_def(d)
    assert (p.id, p.origin, p.length, p.width, p.height) == ("P", "O", 5, "w", 2.5)
    assert (p.view, p.depth_angle, p.depth_scale, p.side) == ("oblique", 30, 0.5, "left")
    assert p.vertex_names == list("ABCDEFGH")


def test_prism_defaults_match_the_ir_defaults():
    p = _prism_def(lower_to_ir(_dsl()))
    assert (p.unit_cubes, p.vertex_names, p.view, p.depth_angle, p.depth_scale, p.side) == (
        False, None, "oblique", None, None, "right")


def test_unit_cube_isometric_prism_renders_through_the_shared_pipeline():
    d = lower_to_ir(_dsl(prism={"length": 3, "width": 2, "height": 2, "unit_cubes": True,
                                "view": "isometric"}))
    sym = compile_defs(d)
    assert "P" in sym and "P_front" in sym
    assert "\\tkzDrawSegment" in ir_to_tikz(d, sym)


def test_default_wireframe_prism_draws_the_prism_id_and_compiles_and_renders():
    d = lower_to_ir(_dsl())
    assert any(isinstance(r, ir.Draw) and r.obj == "P" for r in d.render)
    sym = compile_defs(d)
    assert all(r.passed for r in run_checks(d.checks, sym))


# --- auto canvas fits the projected extent --------------------------------------

def _projected_extent(d: ir.DiagramIR):
    sym = compile_defs(d)
    pts = [sym[n] for n in sym if n.startswith("P_v")]
    return (min(float(p.x) for p in pts), max(float(p.x) for p in pts),
            min(float(p.y) for p in pts), max(float(p.y) for p in pts))


@pytest.mark.parametrize("prism", [
    {},
    {"length": 10, "width": 6, "height": 4},
    {"side": "left"},
    {"view": "isometric", "length": 3, "width": 3, "height": 3},
    {"depth_angle": 60, "depth_scale": 0.8},
])
def test_auto_canvas_contains_the_prism_corners(prism):
    d = lower_to_ir(_dsl(prism=prism))
    x0, x1, y0, y1 = _projected_extent(d)
    c = d.canvas
    assert c.xmin <= x0 and x1 <= c.xmax and c.ymin <= y0 and y1 <= c.ymax


def test_auto_canvas_with_offset_origin_includes_the_origin_offset():
    dsl = RecipeDSL.model_validate({"construction": [
        {"op": "point", "id": "O", "coords": [10, 20]},
        {"op": "prism", "id": "P", "origin": "O", "length": 4, "width": 3, "height": 2}]})
    c = lower_to_ir(dsl).canvas
    assert c.xmin <= 10 and c.xmax >= 14 and c.ymin <= 20 and c.ymax >= 22


def test_undefined_origin_is_injected_at_the_origin_like_other_ops():
    dsl = RecipeDSL.model_validate({"construction": [
        {"op": "prism", "id": "P", "origin": "Z", "length": 4, "width": 3, "height": 2}]})
    d = lower_to_ir(dsl)
    compile_defs(d)
    assert d.canvas.xmax >= 4


def test_invalid_view_combination_is_a_lowering_error():
    with pytest.raises(LoweringError, match="depth_angle"):
        lower_to_ir(_dsl(prism={"view": "isometric", "depth_angle": 30}))


# --- segment helper reuses the prism's own edge ---------------------------------

def _edge_dsl(vertex_names=None):
    return _dsl(prism={"vertex_names": vertex_names} if vertex_names else {},
                annotations={"labels": [{"kind": "label_segment",
                                         "endpoints": ["P_v000", "P_v100"], "text": "4 cm"}]})


def test_label_segment_between_two_corners_targets_the_prism_edge_without_a_duplicate():
    d = lower_to_ir(_edge_dsl())
    lbl = next(r for r in d.render if isinstance(r, ir.LabelSegment))
    assert lbl.seg == "P_e_000_100"
    assert not any(isinstance(x, ir.Segment) for x in d.define)


def test_edge_reuse_is_order_independent_and_covers_all_twelve_edges():
    for p, q in [("P_v100", "P_v000"), ("P_v010", "P_v110"), ("P_v001", "P_v101"),
                 ("P_v011", "P_v111"), ("P_v010", "P_v011")]:
        d = lower_to_ir(_dsl(annotations={"labels": [
            {"kind": "label_segment", "endpoints": [p, q], "text": "x"}]}))
        seg = next(r for r in d.render if isinstance(r, ir.LabelSegment)).seg
        assert seg.startswith("P_e_") and not any(isinstance(x, ir.Segment) for x in d.define)
        compile_defs(d)


def test_edge_reuse_works_with_vertex_names():
    names = list("ABCDEFGH")  # product order: A=000, B=001, C=010, D=011, E=100 ...
    d = lower_to_ir(_dsl(prism={"vertex_names": names}, annotations={"labels": [
        {"kind": "label_segment", "endpoints": ["E", "A"], "text": "l"}]}))
    assert next(r for r in d.render if isinstance(r, ir.LabelSegment)).seg == "P_e_000_100"


def test_diagonals_and_non_edges_get_a_normal_segment_indexed_for_true_length():
    d = lower_to_ir(_dsl(checks=[
        {"check": "true_length", "points": ["P_v000", "P_v111"], "expected": 29 ** 0.5}]))
    segs = [x for x in d.define if isinstance(x, ir.Segment)]
    assert [s.id for s in segs] == ["__mark_seg_P_v000_P_v111"]
    sym = compile_defs(d)
    assert all(r.passed for r in run_checks(d.checks, sym))


def test_segment_between_corners_of_different_prisms_is_a_normal_segment():
    dsl = RecipeDSL.model_validate({"construction": [
        {"op": "point", "id": "O", "coords": [0, 0]},
        {"op": "point", "id": "O2", "coords": [8, 0]},
        {"op": "prism", "id": "P", "origin": "O", "length": 1, "width": 1, "height": 1},
        {"op": "prism", "id": "Q", "origin": "O2", "length": 1, "width": 1, "height": 1}],
        "annotations": {"labels": [{"kind": "label_segment",
                                    "endpoints": ["P_v100", "Q_v000"], "text": "gap"}]}})
    d = lower_to_ir(dsl)
    assert [s.id for s in d.define if isinstance(s, ir.Segment)] == ["__mark_seg_P_v100_Q_v000"]


# --- fills, labels, draws and checks on prism ids ---------------------------------

def test_solid_shaded_look_fills_and_draws_visible_face_ids():
    ann = {"auto_draw_all": False,
           "draws": [{"obj": "P_front"}, {"obj": "P_right"}, {"obj": "P_top"}]}
    extra = [{"op": "fill", "id": f"f_{f}", "obj": f"P_{f}", "opacity": 0.5,
              "style": "rgb(158, 197, 234)"} for f in ("front", "right", "top")]
    d = lower_to_ir(_dsl(extra_ops=extra, annotations=ann))
    fills = [r for r in d.render if isinstance(r, ir.Fill)]
    assert [f.obj for f in fills] == ["P_front", "P_right", "P_top"]
    sym = compile_defs(d)
    assert ir_to_tikz(d, sym).count("\\tkzFillPolygon") == 3


def test_free_text_label_centered_on_the_prism_and_draw_of_the_prism_id():
    d = lower_to_ir(_dsl(annotations={
        "labels": [{"kind": "label_free_text", "text": "V", "centroid_of": "P"}],
        "draws": [{"obj": "P"}]}))
    sym = compile_defs(d)
    tikz = ir_to_tikz(d, sym)
    assert "V" in tikz
    assert any(isinstance(r, ir.Draw) and r.obj == "P" for r in d.render)


def test_volume_check_lowers_and_passes_or_fails_on_the_true_volume():
    ok = lower_to_ir(_dsl(checks=[{"check": "volume", "prism": "P", "expected": 24}]))
    v = next(c for c in ok.checks if isinstance(c, ir.VolumeEquals))
    assert (v.prism, v.expected) == ("P", 24) and v.source.startswith("explicit check:")
    assert all(r.passed for r in run_checks(ok.checks, compile_defs(ok)))
    bad = lower_to_ir(_dsl(checks=[{"check": "volume", "prism": "P", "expected": 25}]))
    assert not all(r.passed for r in run_checks(bad.checks, compile_defs(bad)))


def test_true_length_check_on_an_edge_reuses_the_edge_and_passes():
    d = lower_to_ir(_dsl(checks=[
        {"check": "true_length", "points": ["P_v000", "P_v100"], "expected": 4}]))
    t = next(c for c in d.checks if isinstance(c, ir.TrueLengthEquals))
    assert t.seg == "P_e_000_100"
    assert all(r.passed for r in run_checks(d.checks, compile_defs(d)))


# --- docs are gated on the solids group ----------------------------------------------

def test_docs_with_solids_off_are_byte_identical_to_pre_ticket():
    assert DSL_DOCS == _PRE["dsl_docs"]
    assert dsl_docs_for(frozenset()) == _PRE["dsl_docs"]
    assert build_generation_prompt_static_block(dsl_docs_for(frozenset())) == _PRE["static_block"]
    rec = [load_recipe(_PRE["recipe_name"])]
    assert build_generation_prompt("Draw X.", rec, dsl_docs_for(frozenset())) == _PRE["full_prompt"]


def test_docs_with_solids_on_document_the_op_checks_and_guidance():
    on = dsl_docs_for(SOLIDS)
    assert on != DSL_DOCS and on.startswith(DSL_DOCS.split("\n")[0])
    for needle in ("prism:", "origin", "unit_cubes", "vertex_names", "depth_scale", "side",
                   '"check": "volume"', '"check": "true_length"',
                   "front", "right", "top", "hidden", "wireframe", "2/3", "isometric",
                   "schematic", "10 x 6", "rgb(", "free-text", "100"):
        assert needle in on, needle
    # every base line survives, in order (insertion only)
    it = iter(on.split("\n"))
    assert all(line in it for line in DSL_DOCS.split("\n"))
    assert "prism" not in DSL_DOCS and "prism" not in dsl_docs_for(frozenset({}))


# --- rejection with solids off (before lowering) ---------------------------------------

def test_reject_disabled_ops_names_the_op_and_the_remedy():
    with pytest.raises(FeatureNotEnabledError) as e:
        reject_disabled_ops(_dsl(), frozenset())
    msg = str(e.value)
    assert "prism" in msg and "'P'" in msg and "solids" in msg and "Do not use" in msg
    reject_disabled_ops(_dsl(), SOLIDS)


def test_reject_disabled_ops_covers_the_prism_checks():
    dsl = RecipeDSL.model_validate({
        "construction": [{"op": "point", "id": "O", "coords": [0, 0]}],
        "checks": [{"check": "volume", "prism": "P", "expected": 24}]})
    with pytest.raises(FeatureNotEnabledError, match="volume"):
        reject_disabled_ops(dsl, frozenset())


def test_reject_disabled_ops_ignores_non_prism_recipes():
    reject_disabled_ops(RecipeDSL.model_validate({"construction": [
        {"op": "point", "id": "A", "coords": [0, 0]}]}), frozenset())


@pytest.mark.asyncio
async def test_strategy_rejects_prism_recipe_before_lowering_when_solids_off_and_retries():
    from tests.test_recipe_retry import _common_patches, _make_mock_llm, _wrap_dsl

    dsl = _dsl()
    mock_llm = _make_mock_llm([_wrap_dsl(dsl), _wrap_dsl(dsl), _wrap_dsl(dsl)])
    p = _common_patches(mock_llm)
    lower = MagicMock(side_effect=AssertionError("must not lower"))
    with p[0], p[1], p[2], p[3], p[4], p[5], patch(
            "geometry_diagrams.strategies.recipe.lower_to_ir", lower):
        s = RecipeStrategy()
        with pytest.raises(RuntimeError, match="prism"):
            await s.run("a box")
    lower.assert_not_called()
    traces = s._partial_recipe_metadata.attempt_traces
    assert all(t.stage == "feature_gate" and "prism" in t.error for t in traces)


@pytest.mark.asyncio
async def test_strategy_with_solids_on_lowers_and_renders_the_prism():
    from tests.test_recipe_retry import _common_patches, _make_mock_llm, _wrap_dsl

    mock_llm = _make_mock_llm([_wrap_dsl(_dsl())])
    p = _common_patches(mock_llm)
    seen = {}

    async def fake_pipeline(diagram_ir, renderer):
        seen["ir"] = diagram_ir
        return MagicMock()

    with p[0], p[3], p[4], p[5], patch(
            "geometry_diagrams.strategies.recipe._run_ir_pipeline", new=fake_pipeline):
        await RecipeStrategy(features=SOLIDS).run("a box")
    assert _prism_def(seen["ir"]).id == "P"


# --- pipeline smoke (SVG renderer, in-process) ------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_smoke_shaded_solid_with_labels_and_checks_renders_svg():
    from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline

    extra = [{"op": "fill", "id": f"f_{f}", "obj": f"P_{f}", "opacity": 0.6, "style": "#9ec5ea"}
             for f in ("front", "right", "top")]
    dsl = _dsl(
        extra_ops=extra,
        prism={"length": 10, "width": 6, "height": 5, "visible": False},
        annotations={
            "auto_draw_all": False,
            "draws": [{"obj": "P_front"}, {"obj": "P_right"}, {"obj": "P_top"}],
            "labels": [{"kind": "label_segment", "endpoints": ["P_v000", "P_v100"], "text": "10"},
                       {"kind": "label_free_text", "text": "V = 300", "centroid_of": "P"}],
        },
        checks=[{"check": "volume", "prism": "P", "expected": 300},
                {"check": "true_length", "points": ["P_v000", "P_v100"], "expected": 10}],
    )
    result = await run_ir_pipeline(lower_to_ir(dsl), SVGRenderer())
    assert "<svg" in result.svg and "P_v111" in result.sym_table


@pytest.mark.asyncio
async def test_pipeline_smoke_wireframe_prism_renders_svg():
    from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline

    result = await run_ir_pipeline(lower_to_ir(_dsl(prism={"depth_scale": 0.667})), SVGRenderer())
    assert "<svg" in result.svg


@pytest.mark.asyncio
async def test_pipeline_fails_a_wrong_volume_check_like_any_recipe_check():
    from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline

    dsl = _dsl(checks=[{"check": "volume", "prism": "P", "expected": 99}])
    with pytest.raises(RuntimeError):
        await run_ir_pipeline(lower_to_ir(dsl), SVGRenderer())


# --- the guidance examples are executable (derived from catalog.PRISM_EXAMPLES) -----------
#
# catalog.PRISM_EXAMPLES holds every concrete JSON shape the solids-on guidance
# shows; the guidance text is built from it with json.dumps. The test asserts
# each snippet appears verbatim in the guidance, then validates/lowers/renders
# it, so docs drift from the schema fails here. Prose-only advice (do NOT draw
# the prism id for a shaded solid) is covered by the behavior tests below.

def _examples():
    from geometry_diagrams.recipe.catalog import PRISM_EXAMPLES
    return PRISM_EXAMPLES


def test_every_guidance_example_appears_verbatim_in_the_solids_on_docs():
    on = dsl_docs_for(SOLIDS)
    for name, snippet in _examples().items():
        assert json.dumps(snippet) in on, name
        assert json.dumps(snippet) not in DSL_DOCS, name


def _recipe_around(example_name: str) -> RecipeDSL:
    ex = _examples()
    op = dict(ex["op"])
    construction = [{"op": "point", "id": "O", "coords": [0, 0]}, op]
    annotations, checks = {}, []
    if example_name in ("volume", "true_length"):
        checks = [ex[example_name]]
    elif example_name == "draws":
        annotations = dict(ex["draws"])
    elif example_name == "hide_prism":
        construction[1] = {**op, **ex["hide_prism"]}
    elif example_name == "no_auto_draw":
        annotations = dict(ex["no_auto_draw"])
    return RecipeDSL.model_validate(
        {"construction": construction, "annotations": annotations, "checks": checks})


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["op", "volume", "true_length", "draws", "hide_prism", "no_auto_draw"])
async def test_guidance_example_validates_lowers_and_renders(name):
    from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline

    assert name in _examples()
    result = await run_ir_pipeline(lower_to_ir(_recipe_around(name)), SVGRenderer())
    assert "<svg" in result.svg


def test_guidance_check_examples_are_correct_for_the_example_prism():
    for name in ("volume", "true_length"):
        d = lower_to_ir(_recipe_around(name))
        assert all(r.passed for r in run_checks(d.checks, compile_defs(d))), name


def _dashed_count(svg: str) -> int:
    return svg.count("stroke-dasharray")


@pytest.mark.asyncio
async def test_wireframe_draws_hidden_edges_dashed_and_shaded_solid_has_none():
    from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline

    wire = await run_ir_pipeline(lower_to_ir(_dsl()), SVGRenderer())
    faces = [{"op": "fill", "id": f"f_{f}", "obj": f"P_{f}", "opacity": 0.5} for f in ("front", "right", "top")]
    solid = await run_ir_pipeline(lower_to_ir(_dsl(
        extra_ops=faces, prism={"visible": False},
        annotations={"auto_draw_all": False,
                     "draws": [{"obj": f"P_{f}"} for f in ("front", "right", "top")]})), SVGRenderer())
    assert _dashed_count(wire.svg) >= 3
    assert _dashed_count(solid.svg) == 0
