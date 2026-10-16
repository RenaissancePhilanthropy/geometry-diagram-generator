"""Block stack cube-count check and query-tool exposure (block-stacks ticket 05)."""
from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import ValidationError

from geometry_diagrams.facade import query_diagram_description
from geometry_diagrams.ir import ir
from geometry_diagrams.ir.checks import run_checks
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.strategies.ir_pipeline import PipelineError, run_ir_pipeline
from geometry_diagrams.strategies.structured import dispatch_query

HEIGHTS = [[2, 1], [1, 3]]  # 7 cubes
CUBES = [[0, 0, 0], [0, 1, 0], [1, 0, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [1, 2, 1]]


def _diagram(checks=(), **stack) -> ir.DiagramIR:
    stack = stack or {"heights": HEIGHTS}
    return ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=0, y=0), ir.BlockStack(id="S", origin="O", **stack)],
        render=[ir.Draw(obj="S")],
        checks=list(checks),
    )


def _run(check, **stack):
    [r] = run_checks([check], compile_defs(_diagram(**stack)))
    return r


@pytest.mark.parametrize("stack", [{"heights": HEIGHTS}, {"cubes": CUBES}])
def test_correct_count_passes_for_heights_and_cubes(stack):
    assert _run(ir.CubeCountEquals(stack="S", expected=7), **stack).passed


@pytest.mark.parametrize("stack", [{"heights": HEIGHTS}, {"cubes": CUBES}])
def test_off_by_one_fails_naming_actual_and_expected(stack):
    r = _run(ir.CubeCountEquals(stack="S", expected=8), **stack)
    assert not r.passed
    assert "7" in r.message and "8" in r.message and "'S'" in r.message


def test_integral_float_accepted_non_integral_rejected():
    assert ir.CubeCountEquals(stack="S", expected=7.0).expected == 7
    with pytest.raises(ValidationError):
        ir.CubeCountEquals(stack="S", expected=7.5)


def test_non_stack_and_unknown_ids_fail_with_clear_message():
    for bad in ("O", "nope"):
        r = _run(ir.CubeCountEquals(stack=bad, expected=1))
        assert not r.passed
        assert "cube_count_equals" in r.message and repr(bad) in r.message
        assert "Error in" not in r.message  # a typed rejection, not a stray exception


def test_pipeline_fails_on_wrong_count_and_passes_on_right_one():
    ok = asyncio.run(run_ir_pipeline(
        _diagram(checks=[ir.CubeCountEquals(stack="S", expected=7)]), SVGRenderer()))
    assert ok.svg
    with pytest.raises(PipelineError):
        asyncio.run(run_ir_pipeline(
            _diagram(checks=[ir.CubeCountEquals(stack="S", expected=6)]), SVGRenderer()))


def test_check_round_trips_through_json():
    d = _diagram(checks=[ir.CubeCountEquals(stack="S", expected=7)])
    assert ir.DiagramIR.model_validate_json(d.model_dump_json()).checks[0].kind == "cube_count_equals"


def test_dispatch_query_stack():
    sym = compile_defs(_diagram())
    got = json.loads(dispatch_query(sym, "stack", {"stack": "S"}))
    assert got["cube_count"] == 7 and got["is_height_map"] is True
    assert json.loads(dispatch_query(sym, "stack", {"id": "S"})) == got
    assert "error" in json.loads(dispatch_query(sym, "stack", {"stack": "O"}))


SOLIDS = frozenset({"solids"})


def _agent_description(cls, features) -> str:
    graph = cls(features=features).build_agent(model="anthropic:claude-haiku-4-5-20251001")
    return graph.nodes["tools"].bound.tools_by_name["query_diagram"].description


def _assert_lists_stack_query(text: str) -> None:
    assert "stack" in text
    for word in ("cube_count", "volume", "length", "width", "height", "is_height_map"):
        assert word in text, word


def _all_descriptions(features):
    from evals.run import _make_query_tool
    from geometry_diagrams.strategies.python_full import PythonFullStrategy
    from geometry_diagrams.strategies.recipe import RecipeStrategy
    from geometry_diagrams.strategies.structured import StructureStrategy

    out = {cls.__name__: _agent_description(cls, features)
           for cls in (StructureStrategy, RecipeStrategy, PythonFullStrategy)}
    out["facade"] = query_diagram_description(features)
    out["eval"] = _make_query_tool({}, features).description
    return out


def test_every_query_tool_site_lists_the_stack_query_only_with_solids():
    for name, text in _all_descriptions(SOLIDS).items():
        _assert_lists_stack_query(text)
        stack_sentence = text[text.index("cube_count"):text.index("is_height_map")]
        assert "extents" not in stack_sentence, name
    for name, text in _all_descriptions(frozenset()).items():
        assert "cube_count" not in text and "is_height_map" not in text, name


def test_stack_query_answers_with_solids_off_through_the_eval_tool():
    from evals.run import _make_query_tool
    sym = compile_defs(_diagram())
    out = json.loads(_make_query_tool(sym, frozenset()).invoke(
        {"query_type": "stack", "params": {"stack": "S"}}))
    assert out["cube_count"] == 7
