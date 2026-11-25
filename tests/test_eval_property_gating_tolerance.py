"""Failed expected_properties gate the run (behind a flag), and each property can
set an absolute ``tol`` and/or a figure-relative ``rel_tol``."""
from __future__ import annotations

import pytest

from evals import check_types as ct
from evals import scenarios as sc
from evals.run import _build_arg_parser, _collect_check_outcomes, _finalize_gate_status
from evals.sympy_checks import _figure_scale, _validate_properties_sympy, property_tolerance


def _load(*props: dict) -> list[dict]:
    (s,) = sc._validate_scenarios([{"id": "s", "prompt": "p", "expected_properties": list(props)}])
    return s["expected_properties"]


# --- gating ---------------------------------------------------------------------

def _record(*results: dict) -> dict:
    return {"svg_rendered": True, "generation_success": True, "sympy_property_checks": list(results)}


def test_failed_property_gates_by_default():
    rec = _record({"name": "a", "type": "midpoint", "passed": False, "message": "x"},
                  {"name": "b", "type": "midpoint", "passed": True, "message": ""})
    failures, skipped, had = _collect_check_outcomes(rec)
    assert failures == ["property:a"] and skipped == [] and had
    _finalize_gate_status(rec)
    assert rec["gate_status"] == "fail" and rec["gate_failures"] == ["property:a"]


def test_flag_off_records_the_failure_without_gating():
    rec = _record({"name": "a", "type": "midpoint", "passed": False, "message": "x"})
    failures, _, _ = _collect_check_outcomes(rec, gate_properties=False)
    assert failures == []
    _finalize_gate_status(rec, gate_properties=False)
    assert rec["gate_status"] == "pass" and rec["sympy_property_checks"][0]["passed"] is False


def test_passing_properties_do_not_fail_the_gate():
    rec = _record({"name": "b", "type": "midpoint", "passed": True, "message": ""})
    _finalize_gate_status(rec)
    assert rec["gate_status"] == "pass"


def test_cli_flag_defaults_to_gating():
    parser = _build_arg_parser()
    assert parser.parse_args([]).no_property_gate is False
    assert parser.parse_args(["--no-property-gate"]).no_property_gate is True


# --- tolerances -----------------------------------------------------------------

def _figure(k: float) -> dict:
    """A, B, C almost collinear (C is 0.001 off the line AB), the whole figure scaled by k."""
    return {"A": (0.0, 0.0), "B": (10.0 * k, 0.0), "C": (5.0 * k, 0.001 * k)}


def _collinear(**tol) -> list[dict]:
    return _load({"name": "c", "type": "collinear", "args": ["A", "B", "C"], **tol})


def _verdict(k: float, **tol) -> bool:
    (r,) = _validate_properties_sympy(_collinear(**tol), _figure(k))
    return r["passed"]


def test_default_tolerance_is_unchanged_and_absolute():
    # cross = 10k * 0.001k = 0.01 k^2: passes below 5e-3 only at tiny scale.
    assert _verdict(0.5) is True and _verdict(1.0) is False and _verdict(100.0) is False


def test_absolute_tol_overrides_the_default():
    assert _verdict(1.0, tol=0.05) is True
    assert _verdict(1.0, tol=1e-6) is False


def test_relative_tol_gives_the_same_verdict_at_every_scale():
    # collinear compares an area: the tolerance scales with the figure squared.
    verdicts = {_verdict(k, rel_tol=1e-3) for k in (0.01, 1.0, 100.0)}
    assert len(verdicts) == 1
    assert {_verdict(k, rel_tol=1e-6) for k in (0.01, 1.0, 100.0)} == {False}


def test_with_both_the_larger_tolerance_wins():
    assert property_tolerance({"tol": 1.0, "rel_tol": 1e-9, "type": "midpoint"}, 5e-3, 10.0) == 1.0
    assert property_tolerance({"tol": 1e-9, "rel_tol": 0.1, "type": "midpoint"}, 5e-3, 10.0) == pytest.approx(1.0)
    assert property_tolerance({"type": "midpoint"}, 5e-3, 10.0) == 5e-3


def test_result_reports_the_tolerance_only_when_the_property_set_one():
    (with_tol,) = _validate_properties_sympy(_collinear(tol=0.05), _figure(1.0))
    (without,) = _validate_properties_sympy(_collinear(), _figure(1.0))
    assert with_tol["tol"] == 0.05 and "tol" not in without


def test_angle_check_takes_an_absolute_tol_in_radians():
    pts = {"O": (0.0, 0.0), "A": (1.0, 0.0), "B": (0.0, 1.0)}
    pts["B"] = (0.02, 1.0)  # about 1.15 degrees off a right angle
    ra = {"name": "r", "type": "right_angle", "args": ["A", "O", "B"]}
    assert _validate_properties_sympy(_load(ra), pts)[0]["passed"] is False
    assert _validate_properties_sympy(_load({**ra, "tol": 0.05}), pts)[0]["passed"] is True


def test_figure_scale_is_the_bounding_box_diagonal():
    assert _figure_scale({"A": (0.0, 0.0), "B": (3.0, 4.0)}) == 5.0
    assert _figure_scale({"A": (1.0, 1.0)}) == 1.0 and _figure_scale({}) == 1.0


# --- loading --------------------------------------------------------------------

def test_loader_keeps_tolerances_and_leaves_other_properties_untouched():
    plain, tuned = _load(
        {"name": "a", "type": "midpoint", "args": ["M", "A", "B"]},
        {"name": "b", "type": "midpoint", "args": ["M", "A", "B"], "tol": 0.1, "rel_tol": 0.01},
    )
    assert set(plain) == {"name", "type", "args"}
    assert tuned["tol"] == 0.1 and tuned["rel_tol"] == 0.01


@pytest.mark.parametrize("bad", [0, -1, "x", True, float("inf"), float("nan")])
@pytest.mark.parametrize("key", ["tol", "rel_tol"])
def test_loader_rejects_a_bad_tolerance(key, bad):
    with pytest.raises(ValueError, match=f"'{key}' must be a positive finite number"):
        _load({"name": "a", "type": "midpoint", "args": [], key: bad})


_VALID_ARGS = {
    "right_angle": ["A", "O", "B"], "angle_equal": [["A", "O", "B"], ["C", "P", "D"]],
    "angle_value": ["A", "O", "B", 90], "angle_bisector": ["D", "A", "B", "C"],
    "not_between": ["D", "B", "C"], "same_side": ["P", "Q", "A", "B"], "opposite_side": ["P", "Q", "A", "B"],
}


def test_loader_rejects_rel_tol_on_dimensionless_checks():
    for ptype, args in _VALID_ARGS.items():
        with pytest.raises(ValueError, match="'rel_tol' does not apply"):
            _load({"name": "a", "type": ptype, "args": args, "rel_tol": 0.01})
        assert _load({"name": "a", "type": ptype, "args": args, "tol": 0.01})[0]["tol"] == 0.01


def test_loader_rejects_tolerances_on_types_that_ignore_them():
    for ptype in ("prism_volume", "stack_cube_count", "label_present", "mark_present"):
        with pytest.raises(ValueError, match="not supported for type"):
            _load({"name": "a", "type": ptype, "args": ["*", 1], "tol": 0.1})


def test_every_property_with_a_tolerance_dimension_is_a_supported_type():
    assert {t for t in ct.property_type_names() if ct.tolerance_dimension(t) is not None} == ct.property_type_names("geometry")


def test_a_bad_tolerance_is_recorded_as_an_error_not_raised():
    (r,) = _validate_properties_sympy(
        [{"name": "c", "type": "midpoint", "args": ["M", "A", "B"], "rel_tol": "x"}], _figure(1.0),
    )
    assert r["passed"] is False and r["message"].startswith("Error:")


# Near-miss figures per length-scaling family: the verdict at a given rel_tol must
# be the same at every figure scale (a wrong dimension in the check's registration
# flips it). distance_equals' expected length is filled in as the true 10 * k.
_SCALED = {
    "midpoint": (lambda k: {"A": (0.0, 0.0), "B": (10 * k, 0.0), "M": (5.01 * k, 0.0)}, ["M", "A", "B"]),
    "equal_lengths": (
        lambda k: {"A": (0.0, 0.0), "B": (10 * k, 0.0), "C": (0.0, k), "D": (10.01 * k, k)},
        [["A", "B"], ["C", "D"]],
    ),
    "point_on_line": (lambda k: {"P": (5 * k, 0.01 * k), "A": (0.0, 0.0), "B": (10 * k, 0.0)}, ["P", "A", "B"]),
    "distance_equals": (lambda k: {"A": (0.0, 0.0), "B": (10.01 * k, 0.0)}, [["A", "B"], None]),
    "collinear": (lambda k: {"A": (0.0, 0.0), "B": (10 * k, 0.0), "C": (5 * k, 0.01 * k)}, ["A", "B", "C"]),
    "parallel": (
        lambda k: {"A": (0.0, 0.0), "B": (10 * k, 0.0), "C": (0.0, k), "D": (10 * k, 1.01 * k)},
        [["A", "B"], ["C", "D"]],
    ),
    "perpendicular": (
        lambda k: {"A": (0.0, 0.0), "B": (10 * k, 0.0), "C": (0.0, 0.0), "D": (0.1 * k, 10 * k)},
        [["A", "B"], ["C", "D"]],
    ),
}


@pytest.mark.parametrize("ptype", list(_SCALED))
@pytest.mark.parametrize("rel_tol", [1e-6, 1e-3, 3e-3, 1e-2, 3e-2, 0.5])
def test_relative_tolerance_is_scale_invariant_for_every_scaling_family(ptype, rel_tol):
    make, args = _SCALED[ptype]
    verdicts = set()
    for k in (0.01, 1.0, 100.0):
        filled = [10.0 * k if a is None else a for a in args]
        prop = {"name": "p", "type": ptype, "args": filled, "rel_tol": rel_tol}
        (r,) = _validate_properties_sympy(_load(prop), make(k))
        assert "Error" not in r["message"], r
        verdicts.add(r["passed"])
    assert len(verdicts) == 1, f"{ptype} verdict changes with figure scale at rel_tol={rel_tol}"


def test_scaling_families_not_covered_above_are_the_ones_listed():
    scaling = {t for t in ct.property_type_names("geometry") if ct.tolerance_dimension(t) > 0}
    assert scaling - set(_SCALED) == {
        "point_on_segment", "point_on_circle", "tangent", "intersects", "equidistant_from_sides", "centroid",
    }
