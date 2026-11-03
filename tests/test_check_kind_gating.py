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
    ir.ImageOf: {"transform": ir.DilationTransform(center="P", factor=1.0)},
}


def _placeholder(cls):
    values = {}
    for name, field in cls.model_fields.items():
        if name in ("level", "tol", "source") or name in PLACEHOLDER_OVERRIDES.get(cls, {}):
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
    assert len(_union_members()) >= 36 and {ir.Midpoint, ir.ProportionalLengths, ir.Between, ir.LengthMultiple, ir.AngleMultiple, ir.PointAt, ir.ImageOf} <= set(_union_members())


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


# --- length_multiple, angle_multiple, point_at ------------------------------------

from pydantic import ValidationError  # noqa: E402

_BAD_FACTORS = [0, 0.0, -2.0, float("nan"), float("inf"), float("-inf")]


def _len_diagram(l1=4.0, l2=2.0, factor=2.0, scale=1.0, rot=0.0, tol=None) -> ir.DiagramIR:
    a0, b0 = _rot((0.0, 0.0), scale, rot), _rot((l1, 0.0), scale, rot)
    a1, b1 = _rot((0.0, 1.0), scale, rot), _rot((l2, 1.0), scale, rot)
    return ir.DiagramIR(
        define=[ir.PointFixed(id="A", x=a0[0], y=a0[1]), ir.PointFixed(id="B", x=b0[0], y=b0[1]),
                ir.PointFixed(id="C", x=a1[0], y=a1[1]), ir.PointFixed(id="D", x=b1[0], y=b1[1]),
                ir.Segment(id="s1", a="A", b="B"), ir.Segment(id="s2", a="C", b="D")],
        checks=[ir.LengthMultiple(s1="s1", s2="s2", factor=factor, tol=tol)],
        render=[ir.Draw(obj="s1")],
    )


def _ang_diagram(deg1=60.0, deg2=30.0, factor=2.0, scale=1.0, rot=0.0, tol=None) -> ir.DiagramIR:
    pts = {"O1": (0, 0), "P1": (1, 0), "Q1": (math.cos(math.radians(deg1)), math.sin(math.radians(deg1))),
           "O2": (5, 0), "P2": (6, 0), "Q2": (5 + math.cos(math.radians(deg2)), math.sin(math.radians(deg2)))}
    define = []
    for k, v in pts.items():
        x, y = _rot(v, scale, rot)
        define.append(ir.PointFixed(id=k, x=x, y=y))
    return ir.DiagramIR(
        define=define,
        checks=[ir.AngleMultiple(a1=ir.AnglePoints(a="P1", o="O1", b="Q1"),
                                 a2=ir.AnglePoints(a="P2", o="O2", b="Q2"), factor=factor, tol=tol)],
        render=[ir.DrawPoints(points=list(pts))],
    )


def _at_diagram(px=3.0, py=4.0, x=3.0, y=4.0, scale=1.0, tol=None) -> ir.DiagramIR:
    return ir.DiagramIR(
        define=[ir.PointFixed(id="P", x=px * scale, y=py * scale)],
        checks=[ir.PointAt(p="P", x=x * scale, y=y * scale, tol=tol)],
        render=[ir.DrawPoints(points=["P"])],
    )


def _circle_diagram(central_deg=80.0, inscribed_factor=2.0) -> ir.DiagramIR:
    def on(deg):
        return (math.cos(math.radians(deg)), math.sin(math.radians(deg)))
    pts = {"O": (0, 0), "A": on(0), "B": on(central_deg), "C": on(200)}
    return ir.DiagramIR(
        define=[ir.PointFixed(id=k, x=v[0], y=v[1]) for k, v in pts.items()],
        checks=[ir.AngleMultiple(a1=ir.AnglePoints(a="A", o="O", b="B"),
                                 a2=ir.AnglePoints(a="A", o="C", b="B"), factor=inscribed_factor)],
        render=[ir.DrawPoints(points=list(pts))],
    )


def test_multiple_kinds_registered_in_rule_table():
    for k in ("length_multiple", "angle_multiple", "point_at"):
        assert CHECK_RULES[k] == GROUP


@pytest.mark.parametrize("make", [_len_diagram, _ang_diagram, _at_diagram])
def test_multiple_kinds_gated_off_and_accepted_on(make):
    with pytest.raises(FeatureNotEnabledError) as e:
        require_features(make(), frozenset())
    assert GROUP in str(e.value) and "GEOMETRY_FEATURES=measured_checks" in str(e.value)
    require_features(make(), frozenset({GROUP}))


@pytest.mark.parametrize("make", [_len_diagram, _ang_diagram, _at_diagram])
def test_multiple_kinds_evaluate_and_render_with_group_off(make):
    d = make()
    sym = compile_defs(d)
    assert run_checks(d.checks, sym)[0].passed
    assert "<svg" in SVGRenderer().render(d, sym).output


def test_extractor_references():
    d = _len_diagram()
    assert set(direct_ids_referenced(d.checks[0])) == {"s1", "s2"}
    assert set(direct_ids_referenced(_ang_diagram().checks[0])) == {"O1", "P1", "Q1", "O2", "P2", "Q2"}
    assert direct_ids_referenced(_at_diagram().checks[0]) == ["P"]


@pytest.mark.parametrize("scale", [1e-3, 1.0, 1e3])
@pytest.mark.parametrize("rot", [0.0, 0.7, 2.5])
def test_length_multiple_pass_fail_boundary_across_scale_and_rotation(scale, rot):
    kw = dict(scale=scale, rot=rot)
    assert _verdict(_len_diagram(**kw)).passed
    assert _verdict(_len_diagram(l1=4.0 * 1.004, **kw)).passed
    bad = _verdict(_len_diagram(l1=4.0 * 1.02, **kw))
    assert not bad.passed and "'s1'" in bad.message and "'s2'" in bad.message
    assert _verdict(_len_diagram(l1=1.0, l2=2.0, factor=0.5, **kw)).passed   # fractional factor


def test_length_multiple_honours_own_tol_and_is_not_equal_length():
    assert not _verdict(_len_diagram(l1=4.0 * 1.004, tol=1e-4)).passed
    assert _verdict(_len_diagram(l1=4.0 * 1.004, tol=1e-2)).passed
    assert _verdict(_len_diagram(l1=2.0, l2=2.0, factor=1.0)).passed
    assert not _verdict(_len_diagram(l1=2.0, l2=2.0, factor=2.0)).passed


@pytest.mark.parametrize("scale", [1e-3, 1.0, 1e3])
@pytest.mark.parametrize("rot", [0.0, 0.7, 2.5])
def test_angle_multiple_pass_fail_boundary_across_scale_and_rotation(scale, rot):
    kw = dict(scale=scale, rot=rot)
    assert _verdict(_ang_diagram(**kw)).passed
    assert _verdict(_ang_diagram(deg1=60.0 + 0.1, **kw)).passed          # 0.1 deg ~ 1.7e-3 rad < 5e-3
    bad = _verdict(_ang_diagram(deg1=65.0, **kw))
    assert not bad.passed
    assert "65.0" in bad.message and "30.0" in bad.message and "2" in bad.message


def test_angle_multiple_honours_own_tol_and_factor_one_matches_angle_equal():
    assert not _verdict(_ang_diagram(deg1=60.1, tol=1e-4)).passed
    assert _verdict(_ang_diagram(deg1=60.1, tol=1e-2)).passed
    assert _verdict(_ang_diagram(deg1=40.0, deg2=40.0, factor=1.0)).passed
    assert _verdict(_ang_diagram(deg1=20.0, deg2=40.0, factor=0.5)).passed


def test_angle_multiple_central_versus_inscribed_is_x_and_2x():
    assert _verdict(_circle_diagram()).passed                       # 80 deg central, 40 deg inscribed
    assert not _verdict(_circle_diagram(inscribed_factor=1.0)).passed
    assert not _verdict(_circle_diagram(inscribed_factor=3.0)).passed


@pytest.mark.parametrize("make", [
    lambda f: ir.LengthMultiple(s1="a", s2="b", factor=f),
    lambda f: ir.AngleMultiple(a1=ir.AnglePoints(a="P", o="Q", b="R"), a2=ir.AnglePoints(a="P", o="Q", b="R"), factor=f),
])
@pytest.mark.parametrize("factor", _BAD_FACTORS)
def test_multiple_factor_validation(make, factor):
    with pytest.raises(ValidationError) as e:
        make(factor)
    assert "factor" in str(e.value) and "positive" in str(e.value)


def test_multiple_factor_validation_through_diagram_ir():
    for factor in (0, -1):
        with pytest.raises(ValidationError):
            ir.DiagramIR.model_validate({"checks": [{"kind": "length_multiple", "s1": "a", "s2": "b", "factor": factor}]})


@pytest.mark.parametrize("scale", [1e-6, 1e-3, 1.0, 1e3, 1e6])
def test_point_at_pass_fail_boundary_across_magnitudes(scale):
    assert _verdict(_at_diagram(scale=scale)).passed
    assert _verdict(_at_diagram(px=3.0 * 1.004, scale=scale)).passed      # within 5e-3 of max(|x|,|y|)
    bad = _verdict(_at_diagram(px=3.5, scale=scale))
    assert not bad.passed and "'P'" in bad.message


def test_point_at_is_in_construction_units_and_has_own_tol():
    assert not _verdict(_at_diagram(px=3.0 * 1.004, tol=1e-4)).passed
    assert _verdict(_at_diagram(px=3.0 * 1.004, tol=1e-2)).passed
    assert _verdict(_at_diagram(px=-3.0, py=-4.0, x=-3.0, y=-4.0)).passed


def test_point_at_origin_is_exact_only():
    assert _verdict(_at_diagram(px=0.0, py=0.0, x=0.0, y=0.0)).passed
    assert not _verdict(_at_diagram(px=1e-9, py=0.0, x=0.0, y=0.0)).passed
    assert not _verdict(_at_diagram(px=0.0, py=0.0, x=1e-9, y=0.0)).passed
    # one coordinate zero while the other sets the scale: relative to that scale
    assert _verdict(_at_diagram(px=1e-6, py=1.0, x=0.0, y=1.0)).passed


def test_point_at_message_states_measured_and_expected():
    bad = _verdict(_at_diagram(px=3.5, py=4.0, x=3.0, y=4.0))
    assert "(3.5000, 4.0000)" in bad.message and "(3.0000, 4.0000)" in bad.message


@pytest.mark.parametrize("v", [float("nan"), float("inf")])
def test_point_at_rejects_non_finite_coordinates(v):
    with pytest.raises(ValidationError):
        ir.PointAt(p="P", x=v, y=0.0)
    with pytest.raises(ValidationError):
        ir.PointAt(p="P", x=0.0, y=v)


# --- image_of -----------------------------------------------------------------

def _image_diagram(kind="rotation", perturb=(0.0, 0.0), scale=1.0, rot=0.0, tol=None,
                   wrong_transform=None, use_check=True) -> ir.DiagramIR:
    """q is built by the matching point DEFINITION, then perturbed; the check
    states the same transform. The whole figure is scaled and rotated."""
    base = {"O": (1.0, 2.0), "P": (4.0, 3.0), "A": (0.0, 0.0), "B": (5.0, 1.0)}
    define = [ir.PointFixed(id=k, x=x, y=y)
              for k, (x, y) in ((k, _rot(v, scale, rot)) for k, v in base.items())]
    define += [ir.LineThrough(id="L", p="A", q="B"), ir.Segment(id="S", a="A", b="B")]
    if kind == "rotation":
        q = ir.PointRotate(id="Q0", center="O", source="P", angle=0.9)
        tf = ir.RotationTransform(center="O", angle=0.9)
    elif kind == "dilation":
        q = ir.PointDilate(id="Q0", center="O", source="P", ratio=-2.5)
        tf = ir.DilationTransform(center="O", factor=-2.5)
    elif kind == "reflect_line":
        q = ir.PointReflect(id="Q0", source="P", across="L")
        tf = ir.ReflectionTransform(across="L")
    elif kind == "reflect_segment":
        q = ir.PointReflect(id="Q0", source="P", across="S")
        tf = ir.ReflectionTransform(across="S")
    elif kind == "reflect_point":
        q = ir.PointReflect(id="Q0", source="P", across="O")
        tf = ir.ReflectionTransform(across="O")
    else:  # translation: Q0 = P + (B - A), built by hand (no definition exists)
        q = None
        tf = ir.TranslationTransform(from_point="A", to_point="B")
    if q is not None:
        define.append(q)
        qx, qy = None, None
    if wrong_transform is not None:
        tf = wrong_transform
    d = ir.DiagramIR(define=define, render=[ir.DrawPoints(points=["P"])])
    sym = compile_defs(d)
    if q is not None:
        qx, qy = float(sym["Q0"].x), float(sym["Q0"].y)
    else:
        px, py = _rot(base["P"], scale, rot)
        qx, qy = px + (float(sym["B"].x) - float(sym["A"].x)), py + (float(sym["B"].y) - float(sym["A"].y))
    d = ir.DiagramIR(
        define=define + [ir.PointFixed(id="Q", x=qx + perturb[0] * scale, y=qy + perturb[1] * scale)],
        checks=[ir.ImageOf(q="Q", p="P", transform=tf, tol=tol)],
        render=[ir.DrawPoints(points=["P", "Q"])],
    )
    return d


_KINDS = ["rotation", "dilation", "reflect_line", "reflect_segment", "reflect_point", "translation"]


def test_image_of_registered_in_rule_table():
    assert CHECK_RULES["image_of"] == GROUP


def test_image_of_gated_off_and_accepted_on():
    with pytest.raises(FeatureNotEnabledError) as e:
        require_features(_image_diagram(), frozenset())
    assert "image_of" in str(e.value) and GROUP in str(e.value)
    require_features(_image_diagram(), frozenset({GROUP}))


def test_image_of_evaluates_and_renders_with_group_off():
    d = _image_diagram()
    sym = compile_defs(d)
    assert run_checks(d.checks, sym)[0].passed
    assert "<svg" in SVGRenderer().render(d, sym).output


def test_image_of_extractor_references():
    assert set(direct_ids_referenced(_image_diagram("rotation").checks[0])) == {"Q", "P", "O"}
    assert set(direct_ids_referenced(_image_diagram("reflect_line").checks[0])) == {"Q", "P", "L"}
    assert set(direct_ids_referenced(_image_diagram("translation").checks[0])) == {"Q", "P", "A", "B"}
    assert set(direct_ids_referenced(_image_diagram("dilation").checks[0])) == {"Q", "P", "O"}


@pytest.mark.parametrize("kind", _KINDS)
def test_image_of_agrees_with_the_matching_definition(kind):
    assert _verdict(_image_diagram(kind)).passed


@pytest.mark.parametrize("kind", _KINDS)
def test_image_of_fails_for_a_perturbed_q_and_states_where_q_is_vs_expected(kind):
    r = _verdict(_image_diagram(kind, perturb=(0.3, 0.2)))
    assert not r.passed
    assert "'Q'" in r.message and "should be" in r.message and "'P'" in r.message


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("scale", [1e-3, 1.0, 1e3])
@pytest.mark.parametrize("rot", [0.0, 0.7, 2.5])
def test_image_of_is_scale_and_rotation_invariant(kind, scale, rot):
    assert _verdict(_image_diagram(kind, scale=scale, rot=rot)).passed
    assert not _verdict(_image_diagram(kind, perturb=(0.3, 0.2), scale=scale, rot=rot)).passed


def test_image_of_wrong_transform_fails():
    wrong = ir.RotationTransform(center="O", angle=-0.9)
    assert not _verdict(_image_diagram("rotation", wrong_transform=wrong)).passed
    assert not _verdict(_image_diagram("dilation", wrong_transform=ir.DilationTransform(center="O", factor=2.5))).passed
    # a reflection is not a rotation
    assert not _verdict(_image_diagram("reflect_line", wrong_transform=ir.RotationTransform(center="A", angle=3.14159))).passed


def test_rotation_angle_is_radians_counter_clockwise():
    d = ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=0, y=0), ir.PointFixed(id="P", x=1, y=0),
                ir.PointFixed(id="Q", x=0, y=1)],
        checks=[ir.ImageOf(q="Q", p="P", transform=ir.RotationTransform(center="O", angle=math.pi / 2))],
    )
    assert _verdict(d).passed
    d.checks[0].transform.angle = 90.0  # degrees would be a different point
    assert not _verdict(d).passed


def test_image_of_tol_is_relative_to_anchor_distance_and_own_tol_is_honoured():
    # |PO| = sqrt(9+1); a 2e-3 * |PO| error passes the default 5e-3, not a 1e-4 tol
    off = 2e-3 * math.hypot(3.0, 1.0)
    assert _verdict(_image_diagram("rotation", perturb=(off, 0.0))).passed
    assert not _verdict(_image_diagram("rotation", perturb=(off, 0.0), tol=1e-4)).passed
    assert _verdict(_image_diagram("rotation", perturb=(0.2, 0.0), tol=0.5)).passed


def test_image_of_is_exact_only_when_the_anchor_distance_is_zero():
    same = ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=1, y=1), ir.PointFixed(id="P", x=1, y=1), ir.PointFixed(id="Q", x=1, y=1)],
        checks=[ir.ImageOf(q="Q", p="P", transform=ir.RotationTransform(center="O", angle=2.0))],
    )
    assert _verdict(same).passed
    near = same.model_copy(deep=True)
    near.define[2] = ir.PointFixed(id="Q", x=1.000001, y=1)
    assert not _verdict(near).passed


def test_image_of_reflection_of_a_point_on_the_mirror_is_exact_only():
    d = ir.DiagramIR(
        define=[ir.PointFixed(id="A", x=0, y=0), ir.PointFixed(id="B", x=1, y=0),
                ir.LineThrough(id="L", p="A", q="B"),
                ir.PointFixed(id="P", x=3, y=0), ir.PointFixed(id="Q", x=3, y=0)],
        checks=[ir.ImageOf(q="Q", p="P", transform=ir.ReflectionTransform(across="L"))],
    )
    assert _verdict(d).passed


@pytest.mark.parametrize("bad", [0, 0.0, float("nan"), float("inf"), float("-inf")])
def test_dilation_factor_must_be_finite_and_non_zero(bad):
    with pytest.raises(ValidationError):
        ir.DilationTransform(center="O", factor=bad)


def test_negative_dilation_factor_is_allowed():
    assert ir.DilationTransform(center="O", factor=-3).factor == -3


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_rotation_angle_must_be_finite(bad):
    with pytest.raises(ValidationError):
        ir.RotationTransform(center="O", angle=bad)


def test_transform_discriminator_is_validated_at_parse_time():
    good = {"kind": "image_of", "q": "Q", "p": "P",
            "transform": {"kind": "rotation", "center": "O", "angle": 1.0}}
    assert ir.DiagramIR.model_validate({"define": [], "checks": [good]}).checks[0].transform.kind == "rotation"
    for bad_tf in ({"kind": "shear", "center": "O"}, {"center": "O", "angle": 1.0},
                   {"kind": "dilation", "center": "O", "factor": 0}):
        bad = dict(good, transform=bad_tf)
        with pytest.raises(ValidationError):
            ir.DiagramIR.model_validate({"define": [], "checks": [bad]})


def test_image_of_json_round_trip_uses_from_to_for_translation():
    c = ir.ImageOf(q="Q", p="P", transform=ir.TranslationTransform(from_point="A", to_point="B"))
    assert ir.DiagramIR.model_validate(ir.DiagramIR(define=[], checks=[c]).model_dump(mode="json")).checks[0] == c


def test_image_of_non_point_operand_is_a_failed_check_not_a_crash():
    d = _image_diagram("rotation")
    d.checks[0].transform = ir.RotationTransform(center="L", angle=1.0)  # a line, not a point
    r = _verdict(d)
    assert not r.passed and "center" in r.message
