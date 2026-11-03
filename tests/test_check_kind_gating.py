"""Gated check kinds (feature group ``measured_checks``): the check-kind rule
table consulted by ``require_features``, the first gated kind ``midpoint``,
and the union-completeness guard (every ``Check`` union member must reach a
real evaluator arm and be handled by the pre-assert reference extractor)."""
from __future__ import annotations

import typing

import pytest

from geometry_diagrams.features import (
    CHECK_RULES, FEATURE_GROUPS, FeatureNotEnabledError, require_features,
)
from geometry_diagrams.ir import ir
from geometry_diagrams.ir.checks import _check_one, run_checks
from geometry_diagrams.ir.pre_assert_filter import direct_ids_referenced
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs

GROUP = "measured_checks"


def _diagram(mx=1.0, my=0.0, scale=1.0, rot=0.0, a=(0.0, 0.0), b=(2.0, 0.0), tol=None) -> ir.DiagramIR:
    import math

    def r(p):
        c, s = math.cos(rot), math.sin(rot)
        return (scale * (c * p[0] - s * p[1]), scale * (s * p[0] + c * p[1]))

    pa, pb, pm = r(a), r(b), r((mx, my))
    return ir.DiagramIR(
        define=[
            ir.PointFixed(id="A", x=pa[0], y=pa[1]),
            ir.PointFixed(id="B", x=pb[0], y=pb[1]),
            ir.PointFixed(id="M", x=pm[0], y=pm[1]),
        ],
        checks=[ir.Midpoint(m="M", a="A", b="B", tol=tol)],
        render=[ir.DrawPoints(points=["A", "B", "M"])],
    )


def _verdict(d: ir.DiagramIR):
    return run_checks(d.checks, compile_defs(d))[0]


# --- gating ------------------------------------------------------------------

def test_group_registered_and_rule_table_names_midpoint():
    assert GROUP in FEATURE_GROUPS
    assert CHECK_RULES["midpoint"] == GROUP


def test_midpoint_rejected_when_group_off_with_kind_group_and_how_to_enable():
    with pytest.raises(FeatureNotEnabledError) as e:
        require_features(_diagram(), frozenset())
    msg = str(e.value)
    assert "midpoint" in msg and GROUP in msg and "GEOMETRY_FEATURES=measured_checks" in msg


def test_midpoint_accepted_when_group_on():
    require_features(_diagram(), frozenset({GROUP}))


def test_other_groups_do_not_enable_it():
    with pytest.raises(FeatureNotEnabledError):
        require_features(_diagram(), frozenset({"solids"}))


def test_stored_ir_with_gated_check_compiles_checks_and_renders_with_group_off():
    d = _diagram()
    sym = compile_defs(d)
    assert run_checks(d.checks, sym)[0].passed
    assert "<svg" in SVGRenderer().render(d, sym).output


# --- midpoint evaluation -----------------------------------------------------

def test_midpoint_passes_and_fails_with_measured_vs_claimed():
    assert _verdict(_diagram()).passed
    bad = _verdict(_diagram(mx=1.5))
    assert not bad.passed
    assert "'M'" in bad.message and "(1.5000, 0.0000)" in bad.message and "(1.0000, 0.0000)" in bad.message


@pytest.mark.parametrize("scale", [1e-3, 1.0, 1e3])
@pytest.mark.parametrize("rot", [0.0, 0.7, 2.5])
def test_midpoint_verdict_is_scale_and_rotation_invariant(scale, rot):
    assert _verdict(_diagram(scale=scale, rot=rot)).passed
    assert _verdict(_diagram(mx=1.0 + 2e-3, scale=scale, rot=rot)).passed   # within 5e-3 * |ab| (|ab| = 2)
    assert not _verdict(_diagram(mx=1.0 + 2e-2, scale=scale, rot=rot)).passed


def test_midpoint_honours_own_tol():
    assert not _verdict(_diagram(mx=1.0 + 2e-3, tol=1e-4)).passed
    assert _verdict(_diagram(mx=1.0 + 2e-3, tol=1e-2)).passed


def test_midpoint_of_coincident_endpoints_is_exact_only():
    ok = _diagram(mx=1.0, my=1.0, a=(1.0, 1.0), b=(1.0, 1.0))
    assert _verdict(ok).passed
    assert not _verdict(_diagram(mx=1.0 + 1e-6, my=1.0, a=(1.0, 1.0), b=(1.0, 1.0))).passed


# --- completeness ------------------------------------------------------------

def _union_members():
    inner = typing.get_args(ir.Check)[0]
    return list(typing.get_args(inner))


def _placeholder(cls):
    values = {}
    for name, field in cls.model_fields.items():
        if name in ("kind", "level", "tol", "source") and name != "kind":
            continue
        if name == "kind":
            values[name] = field.default
        elif field.annotation is ir.AngleSpec:
            values[name] = ir.AnglePoints(a="P", o="Q", b="R")
        elif field.annotation in (float, int):
            values[name] = 1
        elif typing.get_origin(field.annotation) is list:
            values[name] = ["P", "Q"]
        else:
            values[name] = "P"
    return cls.model_construct(**values)


def test_union_is_enumerated():
    assert len(_union_members()) >= 31 and ir.Midpoint in _union_members()


@pytest.mark.parametrize("cls", _union_members(), ids=lambda c: c.__name__)
def test_every_union_member_reaches_a_real_evaluator_arm(cls):
    warnings: list[str] = []
    check = _placeholder(cls)
    sym = compile_defs(ir.DiagramIR(define=[ir.PointFixed(id="P", x=0, y=0)]))
    result = _check_one(check, sym, 5e-3, warnings)
    assert "unrecognized check kind" not in result.message, cls.__name__
    assert warnings == []


@pytest.mark.parametrize("cls", _union_members(), ids=lambda c: c.__name__)
def test_every_union_member_is_handled_by_the_extractor(cls):
    ids = direct_ids_referenced(_placeholder(cls))
    assert ids and all(isinstance(i, str) for i in ids)
