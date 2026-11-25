"""regrade.py re-runs expected_properties from the stored figure (SVG-only records too)
and recomputes the gate with the runner's own rule."""
from __future__ import annotations

import pytest

from evals.regrade import _regrade_record
from geometry_diagrams.ir import ir


def _record(**extra) -> dict:
    d = ir.DiagramIR(
        canvas=ir.Canvas(xmin=-1, xmax=5, ymin=-1, ymax=1),
        define=[
            ir.PointFixed(id="pa", x=0.0, y=0.0), ir.PointFixed(id="pb", x=4.0, y=0.0),
            ir.PointFixed(id="pm", x=2.5, y=0.0),  # not the midpoint
        ],
        render=[ir.LabelPoint(p="pa", text="A"), ir.LabelPoint(p="pb", text="B"), ir.LabelPoint(p="pm", text="M")],
    )
    return {
        "scenario_id": "s", "strategy": "recipe", "generation_success": True, "svg_rendered": True,
        "svg_checks": {"passed": True, "failures": []}, "gate_status": "pass", "gate_failures": [],
        "diagram_ir": d.model_dump(mode="json"), "tikz_code": "", "sympy_property_checks": [], **extra,
    }


def _scenario(*props) -> dict:
    return {"id": "s", "prompt": "p", "expected_properties": list(props)}


MIDPOINT = {"name": "m", "type": "midpoint", "args": ["M", "A", "B"]}


def test_an_svg_only_record_is_regraded_for_properties():
    rec, summary = _regrade_record(_record(), _scenario(MIDPOINT))
    assert rec["sympy_property_checks"][0]["passed"] is False
    assert rec["gate_status"] == "fail" and rec["gate_failures"] == ["property:m"]
    assert "gate: pass -> fail" in summary and "properties_changed=1" in summary


def test_a_name_that_resolves_to_nothing_gates_with_its_own_suffix():
    bad = {"name": "m", "type": "midpoint", "args": ["Q", "A", "B"]}
    rec, _ = _regrade_record(_record(), _scenario(bad))
    assert rec["gate_failures"] == ["property:m:unresolved"]


def test_a_passing_property_keeps_the_gate_passing():
    ok = {"name": "m", "type": "midpoint", "args": ["M", "A", "B"], "tol": 5.0}
    rec, summary = _regrade_record(_record(), _scenario(ok))
    assert rec["sympy_property_checks"][0]["passed"] is True and rec["gate_status"] == "pass"


def test_no_property_gate_records_the_failure_without_gating():
    rec, _ = _regrade_record(_record(), _scenario(MIDPOINT), gate_properties=False)
    assert rec["sympy_property_checks"][0]["passed"] is False and rec["gate_status"] == "pass"


def test_keep_recorded_properties_does_not_rerun_them():
    recorded = [{"name": "m", "type": "midpoint", "passed": True, "message": ""}]
    rec, _ = _regrade_record(
        _record(sympy_property_checks=recorded), _scenario(MIDPOINT), recompute_properties=False,
    )
    assert rec["sympy_property_checks"] == recorded and rec["gate_status"] == "pass"


def test_a_record_that_cannot_be_recompiled_keeps_its_recorded_verdicts():
    recorded = [{"name": "m", "type": "midpoint", "passed": False, "message": "old"}]
    rec, _ = _regrade_record(
        _record(sympy_property_checks=recorded, diagram_ir={"nonsense": 1}), _scenario(MIDPOINT),
    )
    assert rec["sympy_property_checks"] == recorded and rec["gate_failures"] == ["property:m"]


def test_edit_chain_records_are_left_alone():
    chain = _record(chain_id="c1", gate_status="fail")
    rec, summary = _regrade_record(chain, _scenario(MIDPOINT))
    assert rec is chain and summary == "edit-chain" and rec["gate_status"] == "fail"


def test_the_input_record_is_not_mutated():
    original = _record()
    before = dict(original)
    _regrade_record(original, _scenario(MIDPOINT))
    assert original == before


def test_tikz_records_still_regrade_their_tikz_checks_and_the_gate_uses_both():
    rec = _record(
        tikz_code="\\tkzDefPoint(0,0){A}\\tkzDefPoint(4,0){B}\\tkzDefPoint(2.5,0){M}",
        tikz_checks={"m": {"passed": True, "type": "midpoint", "skipped": False}},
    )
    new, summary = _regrade_record(rec, _scenario(MIDPOINT))
    # the tikz check (tolerance 0.01) now fails too; the property is counted once
    assert new["tikz_checks"]["m"]["passed"] is False
    assert new["gate_failures"] == ["m"] and new["gate_status"] == "fail"


def _unlabelled_record(**extra) -> dict:
    """A python_full-like record: opaque ids and no labels, names only in variable_ids."""
    d = ir.DiagramIR(
        canvas=ir.Canvas(xmin=-1, xmax=5, ymin=-1, ymax=1),
        define=[ir.PointFixed(id="__pydsl_pt_1", x=0.0, y=0.0), ir.PointFixed(id="__pydsl_pt_2", x=4.0, y=0.0),
                ir.PointFixed(id="__pydsl_pt_3", x=2.0, y=0.0)],
    )
    return {**_record(**extra), "diagram_ir": d.model_dump(mode="json")}


def test_regrade_resolves_names_through_the_stored_variable_ids():
    ids = {"A": "__pydsl_pt_1", "B": "__pydsl_pt_2", "M": "__pydsl_pt_3", "seg": "__pydsl_seg_9"}
    ok, _ = _regrade_record(_unlabelled_record(variable_ids=ids), _scenario(MIDPOINT))
    assert ok["sympy_property_checks"][0]["passed"] is True and ok["gate_status"] == "pass"
    old, _ = _regrade_record(_unlabelled_record(), _scenario(MIDPOINT))  # a record from before they were stored
    assert old["gate_failures"] == ["property:m:unresolved"]
