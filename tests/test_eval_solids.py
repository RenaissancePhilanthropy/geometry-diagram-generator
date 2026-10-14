"""Eval harness support for solids (solids ticket 17): the solid_count
structural check, requires_features scenario gating, the --features flag and
its wiring, and prism property types resolved on the full compiled symbol
table (never on the 2D float coordinates).

No LLM, network or renderer needed.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from evals.run import _STRATEGY_MAP, _run_structural_checks, run_scenario
from evals.scenarios import (
    _validate_scenarios, load_scenarios, split_by_required_features,
)
from evals.sympy_checks import _validate_properties_sympy, _validate_prism_properties
from geometry_diagrams.ir import ir
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult

SOLIDS_YAML = Path(__file__).resolve().parent.parent / "evals" / "scenarios_solids.yaml"


def _prism_ir(length=2, width=4, height=5, **kw) -> dict:
    return {"define": [
        {"kind": "point_fixed", "id": "O", "x": 0, "y": 0},
        {"kind": "rectangular_prism", "id": "P", "origin": "O",
         "length": length, "width": width, "height": height, **kw},
    ]}


def _sc(type_, **args) -> list[dict]:
    return [{"name": "c", "type": type_, "args": args}]


# --- solid_count structural check -------------------------------------------

def test_solid_count_counts_prism_defs_by_kind_and_min():
    d = _prism_ir()
    r = _run_structural_checks(_sc("solid_count", kind="rectangular_prism", min=1), d, None)
    assert r["c"]["passed"] is True
    r = _run_structural_checks(_sc("solid_count", kind="rectangular_prism", min=2), d, None)
    assert r["c"]["passed"] is False and "found 1" in r["c"]["message"]
    r = _run_structural_checks(_sc("solid_count", kind="cylinder", min=1), d, None)
    assert r["c"]["passed"] is False


def test_solid_count_without_kind_counts_any_solid_and_defaults_min_1():
    assert _run_structural_checks(_sc("solid_count"), _prism_ir(), None)["c"]["passed"] is True
    no_solid = {"define": [{"kind": "point_fixed", "id": "O", "x": 0, "y": 0}]}
    assert _run_structural_checks(_sc("solid_count"), no_solid, None)["c"]["passed"] is False


def test_solid_count_literal_dimensions():
    d = _prism_ir(length=2, width=4, height=5)
    ok = _run_structural_checks(_sc("solid_count", min=1, length=2, width=4, height=5), d, None)
    assert ok["c"]["passed"] is True
    bad = _run_structural_checks(_sc("solid_count", min=1, length=2, width=4, height=6), d, None)
    assert bad["c"]["passed"] is False
    # an expression dimension never matches a literal
    expr = _prism_ir(length="a+1")
    assert _run_structural_checks(_sc("solid_count", length=2), expr, None)["c"]["passed"] is False


def test_solid_count_needs_authored_ir():
    r = _run_structural_checks(_sc("solid_count"), None, "\\tkz...")
    assert r["c"]["passed"] is False


def test_prism_never_counts_toward_polygon_count():
    r = _run_structural_checks(_sc("polygon_count", min=1), _prism_ir(), None)
    assert r["c"]["passed"] is False
    r = _run_structural_checks(_sc("polygon_count", min=1, sides=4), _prism_ir(), None)
    assert r["c"]["passed"] is False


def test_polygon_count_unchanged_for_plain_polygons():
    d = {"define": [{"kind": "polygon", "id": "q", "points": ["A", "B", "C", "D"]}]}
    assert _run_structural_checks(_sc("polygon_count", min=1, sides=4), d, None)["c"]["passed"]


# --- validator ---------------------------------------------------------------

def _scenario(**over):
    s = {"id": "s", "prompt": "p"}
    s.update(over)
    return [s]


def test_validator_accepts_solid_count_and_rejects_unknown_types():
    out = _validate_scenarios(_scenario(structural_checks=[
        {"name": "n", "type": "solid_count", "args": {"kind": "rectangular_prism", "min": 1}}]))
    assert out[0]["structural_checks"][0]["type"] == "solid_count"
    with pytest.raises(ValueError, match="supported: polygon_count") as ei:
        _validate_scenarios(_scenario(structural_checks=[{"name": "n", "type": "bogus"}]))
    assert "authored 2D plane polygons only" in str(ei.value)


def test_validator_rejects_bad_solid_count_args():
    for bad in ({"min": "x"}, {"kind": 3}, {"length": "two"}, {"min": -1}):
        with pytest.raises(ValueError):
            _validate_scenarios(_scenario(structural_checks=[
                {"name": "n", "type": "solid_count", "args": bad}]))


def test_validator_requires_features_normalized_and_checked():
    assert _validate_scenarios(_scenario())[0]["requires_features"] == []
    assert _validate_scenarios(_scenario(requires_features=["solids"]))[0]["requires_features"] == ["solids"]
    with pytest.raises(ValueError, match="nope"):
        _validate_scenarios(_scenario(requires_features=["nope"]))
    with pytest.raises(ValueError):
        _validate_scenarios(_scenario(requires_features="solids"))


def test_validator_accepts_prism_property_types():
    out = _validate_scenarios(_scenario(expected_properties=[
        {"name": "v", "type": "prism_volume", "args": ["*", 40]},
        {"name": "d", "type": "prism_dimensions", "args": ["*", 2, 4, 5]},
    ]))
    assert [p["type"] for p in out[0]["expected_properties"]] == ["prism_volume", "prism_dimensions"]


# --- skip logic --------------------------------------------------------------

def test_split_by_required_features_runs_and_skips_with_reason():
    scs = _validate_scenarios([
        {"id": "plain", "prompt": "p"},
        {"id": "needs", "prompt": "p", "requires_features": ["solids"]},
    ])
    run, skipped = split_by_required_features(scs, frozenset())
    assert [s["id"] for s in run] == ["plain"]
    assert skipped == [("needs", "requires feature group(s) not enabled: solids")]
    run, skipped = split_by_required_features(scs, frozenset({"solids"}))
    assert [s["id"] for s in run] == ["plain", "needs"] and skipped == []


# --- --features flag and wiring ---------------------------------------------

def test_features_cli_type_parses_and_validates():
    from evals.run import _features_arg
    assert _features_arg("solids") == frozenset({"solids"})
    assert _features_arg("") == frozenset()
    with pytest.raises(argparse.ArgumentTypeError, match="bogus"):
        _features_arg("bogus")


def test_features_cli_flag_parses_through_the_real_parser(capsys):
    from evals.run import _build_arg_parser
    parser = _build_arg_parser()
    assert parser.parse_args([]).features == frozenset()
    assert parser.parse_args(["--features", "solids"]).features == frozenset({"solids"})
    with pytest.raises(SystemExit):
        parser.parse_args(["--features", "bogus"])
    assert "bogus" in capsys.readouterr().err


def test_requested_gated_scenario_id_errors_with_group_and_flag():
    from evals.run import _check_requested_scenario_ids
    scs = _validate_scenarios([
        {"id": "plain", "prompt": "p"},
        {"id": "needs", "prompt": "p", "requires_features": ["solids"]},
    ])
    with pytest.raises(ValueError) as ei:
        _check_requested_scenario_ids("needs", scs, frozenset())
    msg = str(ei.value)
    assert "'needs'" in msg and "solids" in msg and "--features solids" in msg
    assert "Unknown" not in msg


def test_requested_unknown_scenario_id_still_errors_as_unknown():
    from evals.run import _check_requested_scenario_ids
    scs = _validate_scenarios([{"id": "plain", "prompt": "p"}])
    with pytest.raises(ValueError, match="Unknown scenario id"):
        _check_requested_scenario_ids("plain,nope", scs, frozenset())


def test_requested_gated_scenario_id_passes_when_enabled_and_then_runs():
    from evals.run import _check_requested_scenario_ids
    scs = _validate_scenarios([{"id": "needs", "prompt": "p", "requires_features": ["solids"]}])
    enabled = frozenset({"solids"})
    _check_requested_scenario_ids("needs", scs, enabled)  # no error
    run, skipped = split_by_required_features(scs, enabled)
    assert [s["id"] for s in run] == ["needs"] and skipped == []


@pytest.mark.parametrize("name", sorted(_STRATEGY_MAP))
def test_every_real_strategy_accepts_and_exposes_features(name):
    strategy = _STRATEGY_MAP[name](features=frozenset({"solids"}))
    assert strategy.features == frozenset({"solids"})
    assert _STRATEGY_MAP[name]().features == frozenset()


class _Capturing:
    inits: list = []

    def __init__(self, enable_cache: bool = False, features=None):
        _Capturing.inits.append(features)
        self.features = frozenset(features or ())

    async def run(self, prompt, model=None, renderer=None, **kwargs):
        return StructuredRunResult(
            diagram_ir=ir.DiagramIR(define=[], checks=[], render=[]),
            tikz="", svg="", sym_table={}, sym_full={},
        )


@pytest.mark.parametrize("name", ["python_full", "structured", "recipe"])
async def test_run_scenario_builds_every_strategy_with_features(tmp_path, monkeypatch, name):
    _Capturing.inits = []
    monkeypatch.setitem(_STRATEGY_MAP, name, _Capturing)
    await run_scenario(
        {"id": "s", "prompt": "p"}, name, "m", 1, tmp_path, "b",
        features=frozenset({"solids"}),
    )
    assert _Capturing.inits == [frozenset({"solids"})]


async def test_run_scenario_without_features_constructs_as_before(tmp_path, monkeypatch):
    class _Old:
        def __init__(self, enable_cache: bool = False):
            pass

        async def run(self, prompt, model=None, renderer=None):
            return await _Capturing().run(prompt)

    monkeypatch.setitem(_STRATEGY_MAP, "structured", _Old)
    rec = await run_scenario({"id": "s", "prompt": "p"}, "structured", "m", 1, tmp_path, "b")
    assert rec["generation_success"] is True


# --- prism property types on the full symbol table ---------------------------

def _sym(length=2, width=4, height=5):
    d = ir.DiagramIR.model_validate({
        **_prism_ir(length, width, height), "render": [{"kind": "draw", "obj": "P"}], "checks": [],
    })
    return compile_defs(d)


def _prop(type_, *args):
    return [{"name": "p", "type": type_, "args": list(args)}]


def test_prism_volume_property_pass_and_off_by_one_fails():
    sym = _sym()
    assert _validate_prism_properties(_prop("prism_volume", "P", 40), sym)[0]["passed"] is True
    assert _validate_prism_properties(_prop("prism_volume", "*", 40), sym)[0]["passed"] is True
    off = _sym(length=2, width=4, height=6)  # 48, off-by-one dimension
    res = _validate_prism_properties(_prop("prism_volume", "P", 40), off)[0]
    assert res["passed"] is False and "40" in res["message"]
    assert _validate_prism_properties(_prop("prism_volume", "*", 40), off)[0]["passed"] is False


def test_prism_volume_is_near_exact_not_loose():
    sym = _sym()
    assert _validate_prism_properties(_prop("prism_volume", "P", 40.1), sym)[0]["passed"] is False


def test_prism_dimensions_property():
    sym = _sym()
    assert _validate_prism_properties(_prop("prism_dimensions", "P", 2, 4, 5), sym)[0]["passed"]
    assert not _validate_prism_properties(_prop("prism_dimensions", "P", 2, 4, 6), sym)[0]["passed"]
    assert not _validate_prism_properties(_prop("prism_dimensions", "P", 4, 2, 5), sym)[0]["passed"]


def test_prism_property_errors_fail_not_pass():
    sym = _sym()
    assert not _validate_prism_properties(_prop("prism_volume", "missing", 40), sym)[0]["passed"]
    assert not _validate_prism_properties(_prop("prism_volume", "*", 40), {})[0]["passed"]


def test_2d_property_evaluator_ignores_prism_types():
    # the float table evaluator must neither evaluate nor silently "pass" them
    assert _validate_properties_sympy(_prop("prism_volume", "P", 40), {"O": (0.0, 0.0)}) == []


async def test_run_scenario_records_prism_checks_and_gates_on_failure(tmp_path, monkeypatch):
    class _Prism(_Capturing):
        async def run(self, prompt, model=None, renderer=None, **kw):
            d = ir.DiagramIR.model_validate({
                **_prism_ir(2, 4, 6), "render": [{"kind": "draw", "obj": "P"}], "checks": []})
            return StructuredRunResult(
                diagram_ir=d, tikz="", svg="<svg/>", sym_table={},
                sym_full=compile_defs(d),
            )

    monkeypatch.setitem(_STRATEGY_MAP, "structured", _Prism)
    sc = {"id": "s", "prompt": "p",
          "expected_properties": _prop("prism_volume", "*", 40)}
    rec = await run_scenario(sc, "structured", "m", 1, tmp_path, "b")
    assert rec["prism_property_checks"][0]["passed"] is False
    assert rec["gate_status"] == "fail" and "prism:p" in rec["gate_failures"]
    assert rec["sympy_property_checks"] == []


# --- the new scenario file ---------------------------------------------------

def test_solids_scenario_file_loads_and_is_gated():
    scs = {s["id"]: s for s in load_scenarios(str(SOLIDS_YAML))}
    assert set(scs) >= {"prism-unit-cubes-isometric", "prism-oblique-solid", "prism-oblique-wireframe-base-area"}
    for s in scs.values():
        assert s["requires_features"] == ["solids"]
        assert any(c["type"] == "solid_count" for c in s["structural_checks"])
    v = {p["type"]: p["args"] for p in scs["prism-unit-cubes-isometric"]["expected_properties"]}
    assert v["prism_volume"][1] == 40 and v["prism_dimensions"][1:] == [2, 4, 5]
    assert scs["prism-oblique-solid"]["expected_properties"][0]["args"][1] == 198
    wf = scs["prism-oblique-wireframe-base-area"]
    assert all(p["type"] != "prism_dimensions" for p in wf["expected_properties"])
    assert any(p["args"][1] == 300 for p in wf["expected_properties"])
