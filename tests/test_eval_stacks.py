"""Eval harness support for block stacks (block-stacks ticket 09): solid_count
with kind block_stack and a literal cube_count, and the stack_cube_count
property type evaluated through query_stack on the full compiled symbol table
(its own path, failures prefixed ``stack:``).

No LLM, network or renderer needed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from evals.run import _STRATEGY_MAP, _run_structural_checks, run_scenario
from evals.scenarios import _validate_scenarios, load_scenarios, split_by_required_features
from evals.sympy_checks import (
    _validate_prism_properties, _validate_properties_sympy, _validate_stack_properties,
)
from geometry_diagrams.ir import ir
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult

SOLIDS_YAML = Path(__file__).resolve().parent.parent / "evals" / "scenarios_solids.yaml"

HEIGHTS = [[1, 2, 3], [3, 1, 2]]  # 12 cubes


def _stack_ir(heights=None, cubes=None, sid="S") -> dict:
    d = {"kind": "block_stack", "id": sid, "origin": "O"}
    if cubes is not None:
        d["cubes"] = cubes
    else:
        d["heights"] = HEIGHTS if heights is None else heights
    return {"define": [{"kind": "point_fixed", "id": "O", "x": 0, "y": 0}, d]}


def _sym(**kw):
    d = ir.DiagramIR.model_validate({
        **_stack_ir(**kw), "render": [{"kind": "draw", "obj": "S"}], "checks": []})
    return compile_defs(d)


def _sc(**args) -> list[dict]:
    return [{"name": "c", "type": "solid_count", "args": args}]


def _prop(*args):
    return [{"name": "p", "type": "stack_cube_count", "args": list(args)}]


# --- solid_count with block_stack / cube_count ---------------------------------

def test_solid_count_block_stack_kind_counts_stacks():
    r = _run_structural_checks(_sc(kind="block_stack", min=1), _stack_ir(), None)
    assert r["c"]["passed"] is True
    r = _run_structural_checks(_sc(kind="block_stack", min=2), _stack_ir(), None)
    assert r["c"]["passed"] is False and "found 1" in r["c"]["message"]
    # a stack is not a prism
    r = _run_structural_checks(_sc(kind="rectangular_prism", min=1), _stack_ir(), None)
    assert r["c"]["passed"] is False


def test_solid_count_cube_count_heights_and_cubes():
    ok = _run_structural_checks(_sc(kind="block_stack", cube_count=12), _stack_ir(), None)
    assert ok["c"]["passed"] is True
    bad = _run_structural_checks(_sc(kind="block_stack", cube_count=11), _stack_ir(), None)
    assert bad["c"]["passed"] is False and "cube_count" in bad["c"]["message"]
    arch = [[0, 0, 0], [0, 1, 0], [2, 0, 0], [2, 1, 0], [1, 1, 0]]
    assert _run_structural_checks(
        _sc(kind="block_stack", cube_count=5), _stack_ir(cubes=arch), None)["c"]["passed"]


def test_solid_count_cube_count_accepts_integral_floats_like_compile():
    r = _run_structural_checks(_sc(kind="block_stack", cube_count=3),
                               _stack_ir(heights=[[2.0, 1]]), None)
    assert r["c"]["passed"] is True
    for h in ([[1.5]], [[True, 1]], [[-1, 2]], [[float("nan")]], [[float("inf")]]):
        r = _run_structural_checks(_sc(kind="block_stack", cube_count=1), _stack_ir(heights=h), None)
        assert r["c"]["passed"] is False, h


def test_solid_count_cube_count_malformed_or_non_stack_never_matches():
    # an expression/ragged/non-integer heights never matches a literal count
    for h in ([[1, "a"]], [[1.5]], "x"):
        r = _run_structural_checks(_sc(cube_count=1), _stack_ir(heights=h), None)
        assert r["c"]["passed"] is False
    # a prism has no cube count
    prism = {"define": [{"kind": "rectangular_prism", "id": "P", "origin": "O",
                         "length": 1, "width": 1, "height": 1}]}
    assert _run_structural_checks(_sc(cube_count=1), prism, None)["c"]["passed"] is False


def test_solid_count_stack_counts_each_stack_once_with_matching_count():
    two = _stack_ir()
    two["define"].append({"kind": "block_stack", "id": "T", "origin": "O", "heights": [[2]]})
    assert _run_structural_checks(
        _sc(kind="block_stack", cube_count=2, min=1), two, None)["c"]["passed"]
    assert not _run_structural_checks(
        _sc(kind="block_stack", cube_count=12, min=2), two, None)["c"]["passed"]


def _scenario(**over):
    s = {"id": "s", "prompt": "p"}
    s.update(over)
    return [s]


def test_validator_accepts_cube_count_and_rejects_bad_values():
    out = _validate_scenarios(_scenario(structural_checks=[
        {"name": "n", "type": "solid_count", "args": {"kind": "block_stack", "cube_count": 12}}]))
    assert out[0]["structural_checks"][0]["args"]["cube_count"] == 12
    for bad in ({"cube_count": "12"}, {"cube_count": 1.5}, {"cube_count": -1},
                {"cube_count": True}, {"cubecount": 3}):
        with pytest.raises(ValueError):
            _validate_scenarios(_scenario(structural_checks=[
                {"name": "n", "type": "solid_count", "args": bad}]))


# --- stack_cube_count property -------------------------------------------------

def test_stack_cube_count_pass_wrong_count_and_star():
    sym = _sym()
    assert _validate_stack_properties(_prop("S", 12), sym)[0]["passed"] is True
    assert _validate_stack_properties(_prop("*", 12), sym)[0]["passed"] is True
    bad = _validate_stack_properties(_prop("S", 11), sym)[0]
    assert bad["passed"] is False and "12" in bad["message"] and "11" in bad["message"]
    assert _validate_stack_properties(_prop("*", 11), sym)[0]["passed"] is False


def test_stack_cube_count_star_matches_any_of_several_stacks():
    d = ir.DiagramIR.model_validate({
        "define": _stack_ir()["define"] + [
            {"kind": "block_stack", "id": "T", "origin": "O", "heights": [[2]]}],
        "render": [{"kind": "draw", "obj": "S"}, {"kind": "draw", "obj": "T"}], "checks": []})
    sym = compile_defs(d)
    assert _validate_stack_properties(_prop("*", 2), sym)[0]["passed"] is True
    assert _validate_stack_properties(_prop("T", 12), sym)[0]["passed"] is False


def test_stack_cube_count_missing_stack_or_no_stack_fails():
    sym = _sym()
    r = _validate_stack_properties(_prop("Z", 12), sym)[0]
    assert r["passed"] is False and r["message"].startswith("Error")
    r = _validate_stack_properties(_prop("*", 12), {})[0]
    assert r["passed"] is False and "no stack" in r["message"]
    # a diagram with only a prism has no stack
    prism_ir = {"define": [
        {"kind": "point_fixed", "id": "O", "x": 0, "y": 0},
        {"kind": "rectangular_prism", "id": "P", "origin": "O",
         "length": 1, "width": 1, "height": 1}],
        "render": [{"kind": "draw", "obj": "P"}], "checks": []}
    psym = compile_defs(ir.DiagramIR.model_validate(prism_ir))
    assert _validate_stack_properties(_prop("*", 1), psym)[0]["passed"] is False
    # naming a non-stack id fails too
    assert _validate_stack_properties(_prop("P", 1), psym)[0]["passed"] is False


def test_stack_property_is_not_evaluated_by_other_evaluators():
    sym = _sym()
    assert _validate_properties_sympy(_prop("S", 12), {"O": (0.0, 0.0)}) == []
    assert _validate_prism_properties(_prop("S", 12), sym) == []
    # and the stack evaluator ignores prism types
    assert _validate_stack_properties(
        [{"name": "v", "type": "prism_volume", "args": ["*", 1]}], sym) == []


def test_validator_accepts_stack_cube_count_and_rejects_bad_args():
    out = _validate_scenarios(_scenario(expected_properties=[
        {"name": "n", "type": "stack_cube_count", "args": ["*", 12]}]))
    assert out[0]["expected_properties"][0]["type"] == "stack_cube_count"
    for bad in (["*"], ["*", 12, 1], [3, 12], ["", 12], ["*", "12"], ["*", 1.5],
                ["*", -1], ["*", True]):
        with pytest.raises(ValueError, match="stack_cube_count"):
            _validate_scenarios(_scenario(expected_properties=[
                {"name": "n", "type": "stack_cube_count", "args": bad}]))


class _StackRun:
    count = 12

    def __init__(self, enable_cache: bool = False, features=None):
        self.features = frozenset(features or ())

    async def run(self, prompt, model=None, renderer=None, **kw):
        d = ir.DiagramIR.model_validate({
            **_stack_ir(), "render": [{"kind": "draw", "obj": "S"}], "checks": []})
        return StructuredRunResult(
            diagram_ir=d, tikz="", svg="<svg/>", sym_table={}, sym_full=compile_defs(d))


async def test_run_scenario_records_stack_checks_and_gates_with_stack_prefix(tmp_path, monkeypatch):
    monkeypatch.setitem(_STRATEGY_MAP, "structured", _StackRun)
    sc = {"id": "s", "prompt": "p", "expected_properties": _prop("*", 13)}
    rec = await run_scenario(sc, "structured", "m", 1, tmp_path, "b")
    assert rec["stack_property_checks"][0]["passed"] is False
    assert rec["gate_status"] == "fail" and "stack:p" in rec["gate_failures"]
    assert not any(f.startswith("prism:") for f in rec["gate_failures"])
    assert rec["prism_property_checks"] == [] and rec["sympy_property_checks"] == []

    sc = {"id": "s", "prompt": "p", "expected_properties": _prop("*", 12)}
    rec = await run_scenario(sc, "structured", "m", 1, tmp_path, "b")
    assert rec["stack_property_checks"][0]["passed"] is True
    assert "stack:p" not in rec["gate_failures"]


# --- the scenario file -----------------------------------------------------------

def test_stack_scenarios_load_are_gated_and_have_both_checks():
    scs = {s["id"]: s for s in load_scenarios(str(SOLIDS_YAML))}
    stack_ids = sorted(i for i in scs if i.startswith("stack-"))
    assert len(stack_ids) == 3
    for i in stack_ids:
        s = scs[i]
        assert s["requires_features"] == ["solids"]
        sc = [c for c in s["structural_checks"] if c["type"] == "solid_count"]
        assert sc and sc[0]["args"]["kind"] == "block_stack"
        props = [p for p in s["expected_properties"] if p["type"] == "stack_cube_count"]
        assert props and props[0]["args"][1] == sc[0]["args"]["cube_count"]
    assert scs["stack-isometric-heightmap"]["structural_checks"][0]["args"]["cube_count"] == 12
    assert scs["stack-overhang-arch"]["structural_checks"][0]["args"]["cube_count"] == 5


def test_stack_scenarios_skip_without_solids_and_run_with_it():
    scs = load_scenarios(str(SOLIDS_YAML))
    stack = [s for s in scs if s["id"].startswith("stack-")]
    runnable, skipped = split_by_required_features(stack, frozenset())
    assert runnable == [] and len(skipped) == 3
    runnable, skipped = split_by_required_features(stack, frozenset({"solids"}))
    assert len(runnable) == 3 and skipped == []


# --- stack_extents / stack_is_height_map (ticket 11) -------------------------------

def _ext(*args):
    return [{"name": "e", "type": "stack_extents", "args": list(args)}]


def _hm(*args):
    return [{"name": "h", "type": "stack_is_height_map", "args": list(args)}]


def test_stack_extents_correct_wrong_star_and_messages():
    sym = _sym()  # HEIGHTS [[1,2,3],[3,1,2]] -> length 3, width 2, height 3
    assert _validate_stack_properties(_ext("S", 3, 2, 3), sym)[0]["passed"] is True
    assert _validate_stack_properties(_ext("*", 3, 2, 3), sym)[0]["passed"] is True
    bad = _validate_stack_properties(_ext("S", 3, 3, 2), sym)[0]
    assert bad["passed"] is False
    assert "(3, 2, 3)" in bad["message"] and "(3, 3, 2)" in bad["message"]
    assert _validate_stack_properties(_ext("*", 3, 3, 2), sym)[0]["passed"] is False


def test_stack_extents_and_height_map_star_matches_any_of_several_stacks():
    d = ir.DiagramIR.model_validate({
        "define": _stack_ir()["define"] + [
            {"kind": "block_stack", "id": "T", "origin": "O", "cubes": [[0, 0, 0], [2, 0, 0], [1, 1, 0]]}],
        "render": [{"kind": "draw", "obj": "S"}, {"kind": "draw", "obj": "T"}], "checks": []})
    sym = compile_defs(d)
    assert _validate_stack_properties(_ext("*", 3, 1, 2), sym)[0]["passed"] is True
    assert _validate_stack_properties(_ext("S", 3, 1, 2), sym)[0]["passed"] is False
    assert _validate_stack_properties(_hm("*", False), sym)[0]["passed"] is True
    assert _validate_stack_properties(_hm("S", False), sym)[0]["passed"] is False


def test_stack_is_height_map_correct_wrong_and_message():
    sym = _sym()
    assert _validate_stack_properties(_hm("S", True), sym)[0]["passed"] is True
    bad = _validate_stack_properties(_hm("*", False), sym)[0]
    assert bad["passed"] is False and "True" in bad["message"] and "False" in bad["message"]


def test_stack_extents_height_map_missing_stack_and_no_stack():
    sym = _sym()
    for mk, rest in ((_ext, (1, 1, 1)), (_hm, (True,))):
        r = _validate_stack_properties(mk("Z", *rest), sym)[0]
        assert r["passed"] is False and r["message"].startswith("Error")
        r = _validate_stack_properties(mk("*", *rest), {})[0]
        assert r["passed"] is False and "no stack" in r["message"]
    prism_ir = {"define": [
        {"kind": "point_fixed", "id": "O", "x": 0, "y": 0},
        {"kind": "rectangular_prism", "id": "P", "origin": "O",
         "length": 1, "width": 1, "height": 1}],
        "render": [{"kind": "draw", "obj": "P"}], "checks": []}
    psym = compile_defs(ir.DiagramIR.model_validate(prism_ir))
    assert _validate_stack_properties(_ext("*", 1, 1, 1), psym)[0]["passed"] is False
    assert _validate_stack_properties(_hm("*", True), psym)[0]["passed"] is False


def test_new_stack_properties_not_evaluated_by_other_evaluators():
    sym = _sym()
    for props in (_ext("S", 3, 2, 3), _hm("S", True)):
        assert _validate_properties_sympy(props, {"O": (0.0, 0.0)}) == []
        assert _validate_prism_properties(props, sym) == []


def test_validator_accepts_and_rejects_bad_extents_and_height_map_args():
    out = _validate_scenarios(_scenario(expected_properties=_ext("*", 3, 1, 2) + _hm("*", False)))
    assert [p["type"] for p in out[0]["expected_properties"]] == ["stack_extents", "stack_is_height_map"]
    for bad in (["*"], ["*", 3, 1], ["*", 3, 1, 2, 4], [3, 3, 1, 2], ["", 3, 1, 2],
                ["*", "3", 1, 2], ["*", 3.5, 1, 2], ["*", -1, 1, 2], ["*", True, 1, 2]):
        with pytest.raises(ValueError, match="stack_extents"):
            _validate_scenarios(_scenario(expected_properties=[
                {"name": "n", "type": "stack_extents", "args": bad}]))
    for bad in (["*"], ["*", 1], ["*", "true"], [3, True], ["", True], ["*", True, 1]):
        with pytest.raises(ValueError, match="stack_is_height_map"):
            _validate_scenarios(_scenario(expected_properties=[
                {"name": "n", "type": "stack_is_height_map", "args": bad}]))


ARCH_OK = [[0, 0, 0], [0, 1, 0], [2, 0, 0], [2, 1, 0], [1, 1, 0]]
ARCH_YZ_SWAPPED = [[0, 0, 0], [0, 0, 1], [2, 0, 0], [2, 0, 1], [1, 0, 1]]


def _arch_verdicts(cubes):
    sc = {s["id"]: s for s in load_scenarios(str(SOLIDS_YAML))}["stack-overhang-arch"]
    sym = _sym(cubes=cubes)
    props = {r["type"]: r for r in _validate_stack_properties(sc["expected_properties"], sym)}
    structural = _run_structural_checks(sc["structural_checks"], _stack_ir(cubes=cubes), None)
    return props, structural


def test_arch_scenario_accepts_correct_arch():
    props, structural = _arch_verdicts(ARCH_OK)
    assert set(props) == {"stack_cube_count", "stack_extents", "stack_is_height_map"}
    assert all(r["passed"] for r in props.values()), props
    assert all(r["passed"] for r in structural.values())


def test_arch_scenario_rejects_yz_swapped_arch_but_count_still_passes():
    props, structural = _arch_verdicts(ARCH_YZ_SWAPPED)
    assert props["stack_cube_count"]["passed"] is True
    assert all(r["passed"] for r in structural.values())  # count 5 still matches
    assert props["stack_extents"]["passed"] is False
    assert props["stack_is_height_map"]["passed"] is False
