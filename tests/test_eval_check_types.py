"""Unknown eval check types load as skipped checks, and the registries agree."""
from __future__ import annotations

import logging

import pytest

from evals import check_types as ct
from evals import scenarios as sc
from evals.run import _collect_check_outcomes, _run_structural_checks


def _scenario(**extra) -> list[dict]:
    return [{"id": "s1", "prompt": "Draw a triangle.", **extra}]


def test_every_registered_type_is_complete():
    """One registry, so no second list can drift: each family has what it needs."""
    for name in ct.property_type_names("geometry"):
        t = ct.property_type(name)
        assert t.evaluate is not None and t.dimension in (0, 1, 2, 4), name
    for name in ct.property_type_names("render"):
        assert ct.property_type(name).evaluate is not None
    for name in ct.property_type_names("prism") | ct.property_type_names("stack"):
        t = ct.property_type(name)
        assert t.evaluate is None and t.dimension is None, name  # evaluated on the full symbol table
    for name in ct.structural_type_names():
        assert ct.structural_type(name).evaluate is not None, name
    assert len(ct.property_type_names()) == 27 and ct.structural_type_names() == {"polygon_count", "solid_count"}


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
    ct.register_structural_type("demo_count", lambda args, ir, tikz: {"passed": True, "message": ""})
    try:
        (s,) = sc._validate_scenarios(_scenario(structural_checks=[{"name": "d", "type": "demo_count"}]))
        assert "unsupported" not in s["structural_checks"][0]
        assert _run_structural_checks(s["structural_checks"], {}, None)["d"]["passed"] is True
    finally:
        ct.unregister("structural", "demo_count")
    (s,) = sc._validate_scenarios(_scenario(structural_checks=[{"name": "d", "type": "demo_count"}]))
    assert s["structural_checks"][0]["unsupported"] is True  # gone again


def test_one_registration_adds_a_geometry_type_end_to_end():
    """A new geometry property is one decorated function: the loader accepts it and runs its
    argument validator, the evaluator runs, names resolve, and rel_tol scales by its dimension."""
    from evals.property_names import NameResolver
    from evals.sympy_checks import _validate_properties_sympy

    def need_two(args, where):
        if len(args) != 2:
            raise ValueError(f"{where}: needs two points")

    @ct.register_property_type("demo_close", dimension=1, validate_args=need_two)
    def _close(args, c):
        d = c.dist(c.pt(args[0]), c.pt(args[1]))
        return d < c.tol, f"distance {d:.3f}"

    try:
        (s,) = sc._validate_scenarios(_scenario(expected_properties=[
            {"name": "n", "type": "demo_close", "args": ["A", "B"], "rel_tol": 0.5}]))
        assert "unsupported" not in s["expected_properties"][0]
        with pytest.raises(ValueError, match="needs two points"):
            sc._validate_scenarios(_scenario(expected_properties=[
                {"name": "n", "type": "demo_close", "args": ["A"]}]))
        pts = {"pa": (0.0, 0.0), "pb": (3.0, 0.0), "far": (10.0, 0.0)}
        from geometry_diagrams.ir import ir
        d = ir.DiagramIR(
            canvas=ir.Canvas(xmin=0, xmax=10, ymin=-1, ymax=1),
            define=[ir.PointFixed(id=k, x=v[0], y=v[1]) for k, v in pts.items()],
            render=[ir.LabelPoint(p="pa", text="A"), ir.LabelPoint(p="pb", text="B")],
        )
        (r,) = _validate_properties_sympy(s["expected_properties"], pts, resolver=NameResolver(pts, d))
        assert r["passed"] is True and r["resolved_names"] == {"A": "pa", "B": "pb"}  # 3 < 0.5 * 10 (the figure)
        (r,) = _validate_properties_sympy(
            [{"name": "n", "type": "demo_close", "args": ["A", "B"], "rel_tol": 0.1}], pts,
            resolver=NameResolver(pts, d),
        )
        assert r["passed"] is False and r["tol"] == pytest.approx(1.0)
    finally:
        ct.unregister("property", "demo_close")
    assert ct.property_type("demo_close") is None


def test_registration_rejects_an_incomplete_type():
    with pytest.raises(ValueError, match="tolerance dimension"):
        ct.register_property_type("bad", lambda a, c: (True, ""))
    with pytest.raises(ValueError, match="needs an evaluator"):
        ct.register_property_type("bad", family="render")(None)
    with pytest.raises(ValueError, match="unknown property family"):
        ct.register_property_type("bad", family="nope", dimension=1)
    with pytest.raises(ValueError, match="takes no tolerance dimension"):
        ct.register_property_type("bad", family="prism", dimension=1)
    assert ct.property_type("bad") is None
