"""Recipe surface for block stacks (block-stacks ticket 06): the `stack` op and
`cube_count` check lowering to the IR, ids usable by later ops, the gated docs
(byte-identical with solids off), executable guidance examples and the
pre-lowering rejection with solids off."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from geometry_diagrams.features import FeatureNotEnabledError
from geometry_diagrams.ir import ir
from geometry_diagrams.ir.checks import run_checks
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.recipe.catalog import (
    DSL_DOCS, STACK_EXAMPLES, build_generation_prompt, dsl_docs_for, load_recipe,
)
from geometry_diagrams.recipe.dsl import RecipeDSL, reject_disabled_ops
from geometry_diagrams.recipe.lower import LoweringError, lower_to_ir

SOLIDS = frozenset({"solids"})
_PRE = json.loads((Path(__file__).parent / "recipe_prompt_pre_solids.json").read_text())
HEIGHTS = [[1, 2], [3, 0]]


def _dsl(stack=None, extra_ops=(), annotations=None, checks=()) -> RecipeDSL:
    s = {"op": "stack", "id": "S", "origin": "O", "heights": HEIGHTS}
    s.update(stack or {})
    return RecipeDSL.model_validate({
        "construction": [{"op": "point", "id": "O", "coords": [0, 0]}, s, *extra_ops],
        "annotations": annotations or {},
        "checks": list(checks),
    })


def _stack_def(d: ir.DiagramIR) -> ir.BlockStack:
    return next(x for x in d.define if isinstance(x, ir.BlockStack))


# --- lowering ----------------------------------------------------------------------

def test_stack_op_lowers_to_the_ir_definition_with_every_field():
    d = lower_to_ir(_dsl({"view": "oblique", "depth_angle": 30, "depth_scale": 0.5,
                          "side": "left", "front_color": "red", "side_color": "#00ff00",
                          "top_color": "hsv(0,0,1)"}))
    s = _stack_def(d)
    assert (s.id, s.origin, s.heights, s.cubes) == ("S", "O", HEIGHTS, None)
    assert (s.view, s.depth_angle, s.depth_scale, s.side) == ("oblique", 30, 0.5, "left")
    assert (s.front_color, s.side_color, s.top_color) == ("red", "#00ff00", "hsv(0,0,1)")


def test_stack_defaults_match_the_ir_defaults():
    s = _stack_def(lower_to_ir(_dsl()))
    assert (s.view, s.depth_angle, s.depth_scale, s.side) == ("oblique", None, None, "right")
    assert (s.front_color, s.side_color, s.top_color) == (None, None, None)


def test_stack_op_accepts_a_cube_set():
    d = lower_to_ir(_dsl({"heights": None, "cubes": [[0, 0, 0], [0, 1, 0]]}))
    s = _stack_def(d)
    assert s.heights is None and s.cubes == [[0, 0, 0], [0, 1, 0]]
    assert compile_defs(d)["S"].cube_count == 2


@pytest.mark.parametrize("fields", [{"heights": None}, {"cubes": [[0, 0, 0]]}])
def test_heights_xor_cubes_is_a_typed_compile_error(fields):
    from geometry_diagrams.ir.errors import IRCompileError
    with pytest.raises(IRCompileError, match="exactly one"):
        compile_defs(lower_to_ir(_dsl(fields)))


def test_invalid_view_combination_surfaces_as_an_error():
    with pytest.raises(LoweringError, match=r"stack 'S'.*depth_angle"):
        lower_to_ir(_dsl({"view": "isometric", "depth_angle": 30}))


def test_stack_op_rejects_unknown_fields():
    with pytest.raises(Exception):
        _dsl({"unit_cubes": True})


def test_default_stack_is_drawn_by_auto_draw_all_and_hidden_with_visible_false():
    assert any(isinstance(r, ir.Draw) and r.obj == "S" for r in lower_to_ir(_dsl()).render)
    assert not any(isinstance(r, ir.Draw) and r.obj == "S"
                   for r in lower_to_ir(_dsl({"visible": False})).render)


# --- auto canvas ----------------------------------------------------------------------

@pytest.mark.parametrize("stack", [
    {}, {"side": "left"}, {"view": "isometric"}, {"depth_angle": 60, "depth_scale": 0.8},
    {"heights": [[5, 1, 4]]}, {"heights": None, "cubes": [[0, 0, 0], [3, 2, 1]]},
])
def test_auto_canvas_contains_the_projected_lattice(stack):
    d = lower_to_ir(_dsl(stack))
    sym = compile_defs(d)
    pts = list(sym["S"].lattice.values())
    c = d.canvas
    assert c.xmin <= min(float(p.x) for p in pts) and max(float(p.x) for p in pts) <= c.xmax
    assert c.ymin <= min(float(p.y) for p in pts) and max(float(p.y) for p in pts) <= c.ymax


def test_auto_canvas_includes_an_offset_origin():
    dsl = RecipeDSL.model_validate({"construction": [
        {"op": "point", "id": "O", "coords": [10, 20]},
        {"op": "stack", "id": "S", "origin": "O", "heights": [[2, 2]]}]})
    c = lower_to_ir(dsl).canvas
    assert c.xmin <= 10 and c.xmax >= 12 and c.ymin <= 20 and c.ymax >= 22


def test_undefined_origin_is_injected_at_the_origin():
    dsl = RecipeDSL.model_validate({"construction": [
        {"op": "stack", "id": "S", "origin": "Z", "heights": [[2]]}]})
    compile_defs(lower_to_ir(dsl))


# --- cube_count check ---------------------------------------------------------------------

def test_cube_count_check_lowers_and_passes_or_fails_on_the_count():
    ok = lower_to_ir(_dsl(checks=[{"check": "cube_count", "stack": "S", "expected": 6}]))
    c = next(x for x in ok.checks if isinstance(x, ir.CubeCountEquals))
    assert (c.stack, c.expected) == ("S", 6) and c.source.startswith("explicit check:")
    assert all(r.passed for r in run_checks(ok.checks, compile_defs(ok)))
    bad = lower_to_ir(_dsl(checks=[{"check": "cube_count", "stack": "S", "expected": 7}]))
    assert not all(r.passed for r in run_checks(bad.checks, compile_defs(bad)))


# --- ids usable by later ops ------------------------------------------------------------

def test_stack_and_column_top_ids_are_usable_by_later_ops():
    extra = [{"op": "fill", "id": "f", "obj": "S_top_1_0", "opacity": 0.5, "style": "#ff0000"}]
    ann = {"labels": [
        {"kind": "label_free_text", "text": "top", "centroid_of": "S_top_0_0"},
        {"kind": "label_free_text", "text": "whole", "centroid_of": "S"}],
        "draws": [{"obj": "S_top_0_1"}]}
    d = lower_to_ir(_dsl(extra_ops=extra, annotations=ann))
    assert any(isinstance(r, ir.Fill) and r.obj == "S_top_1_0" for r in d.render)
    sym = compile_defs(d)
    assert "S_top_1_0" in sym and "S_top_0_1" in sym


@pytest.mark.asyncio
async def test_pipeline_renders_stack_with_column_label_and_cube_count():
    from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline
    dsl = _dsl(
        {"front_color": "#aaccee"},
        extra_ops=[{"op": "fill", "id": "f", "obj": "S_top_0_0", "opacity": 0.4}],
        annotations={"labels": [{"kind": "label_free_text", "text": "6", "centroid_of": "S_top_1_0"}]},
        checks=[{"check": "cube_count", "stack": "S", "expected": 6}])
    result = await run_ir_pipeline(lower_to_ir(dsl), SVGRenderer())
    assert "<svg" in result.svg and ">6</text>" in result.svg and not result.warnings


@pytest.mark.asyncio
async def test_wrong_cube_count_fails_the_pipeline():
    from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline
    dsl = _dsl(checks=[{"check": "cube_count", "stack": "S", "expected": 99}])
    with pytest.raises(RuntimeError):
        await run_ir_pipeline(lower_to_ir(dsl), SVGRenderer())


# --- docs gated on solids -----------------------------------------------------------------

def test_docs_with_solids_off_are_byte_identical_and_mention_no_stack():
    assert dsl_docs_for(frozenset()) == _PRE["dsl_docs"] == DSL_DOCS
    assert "stack" not in DSL_DOCS and "cube_count" not in DSL_DOCS
    rec = [load_recipe(_PRE["recipe_name"])]
    assert build_generation_prompt("Draw X.", rec, dsl_docs_for(frozenset())) == _PRE["full_prompt"]


def test_docs_with_solids_on_document_the_op_check_and_guidance():
    on = dsl_docs_for(SOLIDS)
    for needle in ("- stack:", "heights", "cubes", "cube_count", "heights[z][x]", "400", "20",
                   "Never draw individual cubes", "isometric", "front_color", "S_top_"):
        assert needle in on, needle
    it = iter(on.split("\n"))
    assert all(line in it for line in DSL_DOCS.split("\n"))


def test_every_stack_example_appears_verbatim_in_the_solids_on_docs_only():
    on = dsl_docs_for(SOLIDS)
    for name, snippet in STACK_EXAMPLES.items():
        assert json.dumps(snippet) in on, name
        assert json.dumps(snippet) not in DSL_DOCS, name


def _recipe_around(name: str) -> RecipeDSL:
    ex = STACK_EXAMPLES
    stack = ex["isometric_op"] if name == "isometric_op" else ex[name] if name in (
        "op", "cubes_op", "count_label_op") else ex["op"]
    construction = [{"op": "point", "id": "O", "coords": [0, 0]}, dict(stack)]
    checks = [ex[name]] if name == "cube_count" else []
    annotations = {}
    if name == "column_label":
        annotations = {"labels": [ex["column_label"]]}
    return RecipeDSL.model_validate(
        {"construction": construction, "annotations": annotations, "checks": checks})


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["op", "isometric_op", "cubes_op", "count_label_op", "cube_count", "column_label"])
async def test_guidance_example_validates_lowers_and_renders(name):
    from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline
    assert name in STACK_EXAMPLES
    d = lower_to_ir(_recipe_around(name))
    result = await run_ir_pipeline(d, SVGRenderer())
    assert "<svg" in result.svg


def test_guidance_cube_count_example_is_correct_for_the_example_stack():
    d = lower_to_ir(_recipe_around("cube_count"))
    assert all(r.passed for r in run_checks(d.checks, compile_defs(d)))


# --- rejection with solids off ----------------------------------------------------------------

def test_reject_disabled_ops_names_the_stack_op_and_remedy():
    with pytest.raises(FeatureNotEnabledError) as e:
        reject_disabled_ops(_dsl(), frozenset())
    msg = str(e.value)
    assert "stack" in msg and "'S'" in msg and "solids" in msg and "Do not use" in msg
    reject_disabled_ops(_dsl(), SOLIDS)


def test_reject_disabled_ops_covers_the_cube_count_check():
    dsl = RecipeDSL.model_validate({
        "construction": [{"op": "point", "id": "O", "coords": [0, 0]}],
        "checks": [{"check": "cube_count", "stack": "S", "expected": 3}]})
    with pytest.raises(FeatureNotEnabledError, match="cube_count"):
        reject_disabled_ops(dsl, frozenset())
    reject_disabled_ops(dsl, SOLIDS)


@pytest.mark.asyncio
async def test_cubes_example_is_a_real_overhang_not_a_height_map():
    from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline
    d = lower_to_ir(_recipe_around("cubes_op"))
    assert compile_defs(d)["S"].is_height_map is False
    result = await run_ir_pipeline(d, SVGRenderer())
    assert any("height map" in w for w in result.warnings)
