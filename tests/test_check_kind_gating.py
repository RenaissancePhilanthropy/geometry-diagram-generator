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


# Per-class placeholder overrides for kinds whose fields need more than the
# generic by-type placeholder (e.g. fields with parse-time validators). Add an
# entry here when a new kind's fields cannot be built from "P"/1/["P","Q"].
PLACEHOLDER_OVERRIDES: "dict[type, dict]" = {
    ir.ProportionalLengths: {"segs": ["P", "Q"], "values": [1.0, 2.0]},
}


def _placeholder(cls):
    values = {}
    for name, field in cls.model_fields.items():
        if name in ("level", "tol", "source"):
            continue
        ann = field.annotation
        if name == "kind":
            values[name] = field.default
        elif ann is ir.AngleSpec:
            values[name] = ir.AnglePoints(a="P", o="Q", b="R")
        elif ann in (float, int):
            values[name] = 1
        elif not field.is_required():
            continue  # optional fields keep their default
        elif typing.get_origin(ann) is list:
            values[name] = ["P", "Q"]
        elif ann is str:
            values[name] = "P"
        else:
            raise TypeError(
                f"_placeholder: no placeholder for {cls.__name__}.{name}: {ann!r}; "
                "add it to PLACEHOLDER_OVERRIDES"
            )
    values.update(PLACEHOLDER_OVERRIDES.get(cls, {}))
    return cls.model_construct(**values)


def test_union_is_enumerated():
    assert len(_union_members()) >= 33 and {ir.Midpoint, ir.ProportionalLengths, ir.Between} <= set(_union_members())


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


# --- proportional_lengths and between -----------------------------------------

import math  # noqa: E402


def _rot(p, scale, rot):
    c, s = math.cos(rot), math.sin(rot)
    return (scale * (c * p[0] - s * p[1]), scale * (s * p[0] + c * p[1]))


def _prop_diagram(lens=(1.0, 2.0, 3.0), values=(1, 2, 3), scale=1.0, rot=0.0, tol=None) -> ir.DiagramIR:
    define = []
    segs = []
    for i, L in enumerate(lens):
        a, b = _rot((0.0, float(i)), scale, rot), _rot((L, float(i)), scale, rot)
        define += [ir.PointFixed(id=f"A{i}", x=a[0], y=a[1]), ir.PointFixed(id=f"B{i}", x=b[0], y=b[1]),
                   ir.Segment(id=f"s{i}", a=f"A{i}", b=f"B{i}")]
        segs.append(f"s{i}")
    return ir.DiagramIR(
        define=define,
        checks=[ir.ProportionalLengths(segs=segs, values=list(values), tol=tol)],
        render=[ir.Draw(obj="s0")],
    )


def _between_diagram(t=0.5, off=0.0, scale=1.0, rot=0.0, a=(0.0, 0.0), b=(2.0, 0.0), tol=None) -> ir.DiagramIR:
    """P at parameter t along ab (t may be outside [0, 1]), `off` perpendicular."""
    px = a[0] + t * (b[0] - a[0]) - off * (b[1] - a[1]) / (math.dist(a, b) or 1)
    py = a[1] + t * (b[1] - a[1]) + off * (b[0] - a[0]) / (math.dist(a, b) or 1)
    pa, pb, pp = _rot(a, scale, rot), _rot(b, scale, rot), _rot((px, py), scale, rot)
    return ir.DiagramIR(
        define=[ir.PointFixed(id="A", x=pa[0], y=pa[1]), ir.PointFixed(id="B", x=pb[0], y=pb[1]),
                ir.PointFixed(id="P", x=pp[0], y=pp[1])],
        checks=[ir.Between(p="P", a="A", b="B", tol=tol)],
        render=[ir.DrawPoints(points=["A", "B", "P"])],
    )


def test_new_kinds_registered_in_rule_table():
    assert CHECK_RULES["proportional_lengths"] == GROUP
    assert CHECK_RULES["between"] == GROUP


@pytest.mark.parametrize("make", [_prop_diagram, _between_diagram])
def test_new_kinds_gated_off_and_accepted_on(make):
    with pytest.raises(FeatureNotEnabledError) as e:
        require_features(make(), frozenset())
    assert GROUP in str(e.value) and "GEOMETRY_FEATURES=measured_checks" in str(e.value)
    require_features(make(), frozenset({GROUP}))


@pytest.mark.parametrize("make", [_prop_diagram, _between_diagram])
def test_new_kinds_evaluate_and_render_with_group_off(make):
    d = make()
    sym = compile_defs(d)
    assert run_checks(d.checks, sym)[0].passed
    assert "<svg" in SVGRenderer().render(d, sym).output


def test_between_check_does_not_collide_with_between_pick_rule():
    d = ir.DiagramIR.model_validate({
        "define": [
            {"kind": "point_fixed", "id": "A", "x": 0, "y": 0},
            {"kind": "point_fixed", "id": "B", "x": 2, "y": 0},
            {"kind": "point_fixed", "id": "P", "x": 1, "y": 0},
        ],
        "checks": [{"kind": "between", "p": "P", "a": "A", "b": "B"}],
    })
    assert isinstance(d.checks[0], ir.Between)
    assert ir.PickBetween(a="A", b="B").kind == "between"


# --- proportional_lengths ------------------------------------------------------

@pytest.mark.parametrize("scale", [1e-3, 1.0, 1e3])
@pytest.mark.parametrize("rot", [0.0, 0.7, 2.5])
def test_proportional_lengths_pass_fail_boundary_across_scale_and_rotation(scale, rot):
    assert _verdict(_prop_diagram(scale=scale, rot=rot)).passed
    assert _verdict(_prop_diagram(lens=(1.0, 2.0 * 1.004, 3.0), scale=scale, rot=rot)).passed   # inside 5e-3
    bad = _verdict(_prop_diagram(lens=(1.0, 2.0 * 1.02, 3.0), scale=scale, rot=rot))
    assert not bad.passed


def test_proportional_lengths_scale_free_in_values():
    assert _verdict(_prop_diagram(lens=(2.0, 4.0, 6.0), values=(10, 20, 30))).passed


def test_proportional_lengths_message_states_measured_vs_claimed_ratios():
    bad = _verdict(_prop_diagram(lens=(1.0, 2.5, 3.0), values=(1, 2, 3)))
    assert not bad.passed
    assert "2.5" in bad.message and "2.0" in bad.message and "'s1'" in bad.message


def test_proportional_lengths_honours_own_tol():
    d = dict(lens=(1.0, 2.0 * 1.004, 3.0))
    assert not _verdict(_prop_diagram(tol=1e-4, **d)).passed
    assert _verdict(_prop_diagram(tol=1e-2, **d)).passed


def test_proportional_lengths_measures_arcs_like_other_length_checks():
    from geometry_diagrams.ir.checks import _length_of
    d = ir.DiagramIR(
        define=[
            ir.PointFixed(id="O", x=0, y=0), ir.PointFixed(id="S", x=1, y=0), ir.PointFixed(id="E", x=0, y=1),
            ir.PointFixed(id="C", x=2, y=0),
            ir.ArcCenterStartEnd(id="arc", center="O", start="S", end="E"),
            ir.Segment(id="seg", a="O", b="C"),
        ],
        checks=[ir.ProportionalLengths(segs=["arc", "seg"], values=[math.pi / 2, 2.0])],
    )
    sym = compile_defs(d)
    assert _length_of(sym["arc"], "arc") == pytest.approx(math.pi / 2)
    assert run_checks(d.checks, sym)[0].passed


@pytest.mark.parametrize("kwargs, needle", [
    (dict(segs=["a", "b"], values=[1.0]), "same number"),
    (dict(segs=["a"], values=[1.0]), "at least two"),
    (dict(segs=["a", "b"], values=[1.0, 0.0]), "positive"),
    (dict(segs=["a", "b"], values=[1.0, -2.0]), "positive"),
    (dict(segs=["a", "b"], values=[1.0, float("nan")]), "positive"),
])
def test_proportional_lengths_parse_time_validation(kwargs, needle):
    from pydantic import ValidationError
    with pytest.raises(ValidationError) as e:
        ir.ProportionalLengths(**kwargs)
    assert needle in str(e.value)
    with pytest.raises(ValidationError):
        ir.DiagramIR.model_validate({"checks": [{"kind": "proportional_lengths", **kwargs}]})


# --- between ---------------------------------------------------------------------

@pytest.mark.parametrize("scale", [1e-3, 1.0, 1e3])
@pytest.mark.parametrize("rot", [0.0, 0.7, 2.5])
def test_between_pass_fail_boundary_across_scale_and_rotation(scale, rot):
    kw = dict(scale=scale, rot=rot)          # |ab| = 2, so 5e-3 * |ab| = 1e-2 absolute
    assert _verdict(_between_diagram(**kw)).passed
    assert _verdict(_between_diagram(off=4e-3, **kw)).passed                  # within tol of the segment
    off_seg = _verdict(_between_diagram(off=4e-2, **kw))
    assert not off_seg.passed and "not on segment" in off_seg.message
    # at-end boundary: t=0.004 is 0.008 < 0.01 from A
    at_end = _verdict(_between_diagram(t=0.004, **kw))
    assert not at_end.passed and "at an end" in at_end.message and "'A'" in at_end.message
    assert _verdict(_between_diagram(t=0.01, **kw)).passed                    # 0.02 > 0.01 from A
    at_b = _verdict(_between_diagram(t=0.996, **kw))
    assert not at_b.passed and "'B'" in at_b.message
    # beyond the end: off the segment (past b), distance 0.2 > tol
    assert "not on segment" in _verdict(_between_diagram(t=1.1, **kw)).message


def test_between_honours_own_tol():
    assert not _verdict(_between_diagram(off=4e-3, tol=1e-4)).passed
    assert _verdict(_between_diagram(t=0.1, tol=1e-1)).passed is False   # 0.2 from A, tol*|ab| = 0.2: at an end


def test_between_coincident_endpoints_fail_sensibly():
    v = _verdict(_between_diagram(t=0.5, a=(1.0, 1.0), b=(1.0, 1.0)))
    assert not v.passed and ("coincide" in v.message or "at an end" in v.message)
