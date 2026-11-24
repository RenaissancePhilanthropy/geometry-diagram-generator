"""Unknown eval check types load as skipped checks, and the registries agree."""
from __future__ import annotations

import logging

import pytest

from evals import run as eval_run
from evals import scenarios as sc
from evals.run import _STRUCTURAL_EVALUATORS, _collect_check_outcomes, _run_structural_checks


def _scenario(**extra) -> list[dict]:
    return [{"id": "s1", "prompt": "Draw a triangle.", **extra}]


def test_every_loadable_structural_type_has_an_evaluator_and_back():
    assert set(sc._STRUCTURAL_ARG_VALIDATORS) == set(_STRUCTURAL_EVALUATORS)


def test_unknown_property_type_loads_marked_unsupported_and_warns_once(caplog):
    raw = _scenario(expected_properties=[
        {"name": "a", "type": "future_check", "args": ["A"]},
        {"name": "b", "type": "future_check", "args": ["B"]},
        {"name": "c", "type": "collinear", "args": ["A", "B", "C"]},
    ])
    with caplog.at_level(logging.WARNING, logger="evals.scenarios"):
        (s,) = sc._validate_scenarios(raw)
    props = {p["name"]: p for p in s["expected_properties"]}
    assert props["a"]["unsupported"] and props["b"]["unsupported"]
    assert "unsupported" not in props["c"]
    assert len([r for r in caplog.records if "future_check" in r.getMessage()]) == 1


def test_unknown_structural_type_loads_marked_unsupported():
    (s,) = sc._validate_scenarios(_scenario(structural_checks=[
        {"name": "x", "type": "future_count", "args": {"min": 2}},
    ]))
    assert s["structural_checks"][0]["unsupported"] is True


def test_strict_restores_the_error():
    with pytest.raises(ValueError, match="future_check"):
        sc._validate_scenarios(
            _scenario(expected_properties=[{"name": "a", "type": "future_check", "args": []}]),
            strict=True,
        )
    with pytest.raises(ValueError, match="future_count"):
        sc._validate_scenarios(
            _scenario(structural_checks=[{"name": "x", "type": "future_count"}]), strict=True
        )


def test_malformed_unknown_checks_still_fail():
    with pytest.raises(ValueError, match="'args' must be a list"):
        sc._validate_scenarios(_scenario(expected_properties=[{"name": "a", "type": "future_check"}]))
    with pytest.raises(ValueError, match="'name' must be a non-empty string"):
        sc._validate_scenarios(_scenario(structural_checks=[{"type": "future_count"}]))


def test_known_types_still_validate_their_args():
    with pytest.raises(ValueError, match="solid_count"):
        sc._validate_scenarios(_scenario(structural_checks=[
            {"name": "x", "type": "solid_count", "args": {"bogus": 1}},
        ]))


def test_unsupported_structural_check_is_skipped_not_passed_and_soft_passes_the_gate():
    results = _run_structural_checks(
        [{"name": "x", "type": "future_count", "args": {}, "unsupported": True}], {"define": []}, None,
    )
    assert results["x"]["passed"] is None and results["x"]["skipped"] is True
    failures, skipped, had = _collect_check_outcomes({"structural_checks": results})
    assert failures == [] and skipped == ["structural:x"] and had


def test_unsupported_property_check_is_skipped_by_the_gate():
    from evals.sympy_checks import _validate_properties_sympy
    results = _validate_properties_sympy([{"name": "a", "type": "future_check", "args": []}], {})
    assert results[0]["passed"] is None
    record = {"sympy_property_checks": results}
    failures, skipped, _ = _collect_check_outcomes(record)
    assert failures == [] and skipped == ["property:a"]


def test_registered_structural_type_is_loadable_and_evaluated():
    sc.register_structural_type("demo_count")
    _STRUCTURAL_EVALUATORS["demo_count"] = lambda args, ir, tikz: {"passed": True, "message": ""}
    try:
        (s,) = sc._validate_scenarios(_scenario(structural_checks=[{"name": "d", "type": "demo_count"}]))
        assert "unsupported" not in s["structural_checks"][0]
        assert _run_structural_checks(s["structural_checks"], {}, None)["d"]["passed"] is True
    finally:
        _STRUCTURAL_EVALUATORS.pop("demo_count")
        sc._STRUCTURAL_ARG_VALIDATORS.pop("demo_count")
