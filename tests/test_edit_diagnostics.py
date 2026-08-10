"""Tests for the pydsl edit-locality diagnostic (ir/edit_diagnostics.py)."""
from __future__ import annotations

from geometry_diagrams.ir.ir import DiagramIR, PointFixed, Segment, Triangle
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.render_util import build_entity_manifest
from geometry_diagrams.ir.edit_diagnostics import check_edit_locality


def _triangle_diagram(bx: float) -> DiagramIR:
    return DiagramIR(
        define=[
            PointFixed(id="p_a", x=0.0, y=0.0),
            PointFixed(id="p_b", x=bx, y=0.0),
            PointFixed(id="p_c", x=0.0, y=3.0),
            PointFixed(id="p_d", x=10.0, y=10.0),  # unrelated free point
            Triangle(id="tri1", a="p_a", b="p_b", c="p_c"),
        ],
        render=[],
    )


def _compile(diagram: DiagramIR, variable_ids: dict):
    sym = compile_defs(diagram)
    manifest = build_entity_manifest(diagram, sym, variable_ids)
    return manifest, sym


def test_locality_check_reports_no_violation_for_a_correctly_scoped_edit():
    variable_ids = {"a": "p_a", "b": "p_b", "c": "p_c", "d": "p_d", "t": "tri1"}
    old_ir = _triangle_diagram(bx=4.0)
    new_ir = _triangle_diagram(bx=8.0)  # only p_b's x changed -> t is downstream
    old_manifest, old_sym = _compile(old_ir, variable_ids)
    new_manifest, new_sym = _compile(new_ir, variable_ids)

    diag = check_edit_locality(old_manifest, old_ir, old_sym, new_manifest, new_ir, new_sym)

    assert diag.violations == []
    assert "d" not in diag.downstream_names
    assert {"b", "t"} <= diag.downstream_names
    assert diag.unmatched_old_names == set()
    assert diag.unmatched_new_names == set()


def test_locality_check_flags_an_unrelated_entity_that_moved():
    variable_ids = {"a": "p_a", "b": "p_b", "c": "p_c", "d": "p_d", "t": "tri1"}
    old_ir = _triangle_diagram(bx=4.0)
    new_ir = _triangle_diagram(bx=4.0)
    new_ir.define[3] = PointFixed(id="p_d", x=99.0, y=99.0)  # "d" moved despite no def change elsewhere
    old_manifest, old_sym = _compile(old_ir, variable_ids)
    new_manifest, new_sym = _compile(new_ir, variable_ids)

    diag = check_edit_locality(old_manifest, old_ir, old_sym, new_manifest, new_ir, new_sym)

    violated_names = {v["name"] for v in diag.violations}
    assert "d" in violated_names
    assert "t" not in violated_names


def test_locality_check_reports_name_churn_without_position_false_positive():
    old_variable_ids = {"a": "p_a", "b": "p_b", "c": "p_c", "d": "p_d", "t": "tri1"}
    new_variable_ids = {"a": "p_a", "b": "p_b", "c": "p_c", "d": "p_d", "triangle_shape": "tri1"}
    old_ir = _triangle_diagram(bx=4.0)
    new_ir = _triangle_diagram(bx=4.0)
    old_manifest, old_sym = _compile(old_ir, old_variable_ids)
    new_manifest, new_sym = _compile(new_ir, new_variable_ids)

    diag = check_edit_locality(old_manifest, old_ir, old_sym, new_manifest, new_ir, new_sym)

    assert "t" in diag.unmatched_old_names
    assert "triangle_shape" in diag.unmatched_new_names
    assert diag.violations == []
