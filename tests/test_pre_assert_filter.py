# tests/test_pre_assert_filter.py
"""Tests for ir/pre_assert_filter.py -- the pre-assert pre-filter's three
prototype-validated pure-function stages (API-name validation, generic-instance
grounding, structural lints). No LLM calls anywhere in this module or these tests.

Fixtures are ported from the discardable prototype under
.scratch/pre-assert-proposal/ (worked_example_strategy1.py,
experiment_strategy1_broad.py, experiment_strategy1_part2.py) -- known-correct
and known-wrong proposed checks from real model output, not invented cases.
"""
import random

import pytest

from geometry_diagrams.ir import ir as ir_mod
from geometry_diagrams.ir.pre_assert_filter import (
    REAL_ASSERT_NAMES,
    build_name_correction_message,
    extract_assert_tokens,
    find_unknown_assert_names,
    find_unknown_assert_names_after_retry,
    ground_and_evaluate,
    lint_collinear_arity,
    lint_self_referential_contains,
    random_point_defs,
    run_lints,
)


# ---------------------------------------------------------------------------
# Stage 1: API-name validation
# ---------------------------------------------------------------------------

def test_real_assert_names_has_24_entries():
    """Sanity check against the shipped assert_* feature's actual vocabulary."""
    assert len(REAL_ASSERT_NAMES) == 24
    assert "assert_collinear" in REAL_ASSERT_NAMES
    assert "assert_angle_equal" in REAL_ASSERT_NAMES


def test_extract_assert_tokens_finds_all_shaped_tokens():
    text = "assert_collinear(O, M, A)\nassert_equal(OA, OB)\nassert_angle_equal(x, y)"
    tokens = extract_assert_tokens(text)
    assert tokens == ["assert_collinear", "assert_equal", "assert_angle_equal"]


def test_find_unknown_assert_names_flags_hallucinated_name():
    """Real prototype case (ticket 05): a 4-check proposal with one hallucinated
    name, assert_equal, which doesn't exist in the real API."""
    text = (
        "assert_collinear(H, A, F)\n"
        "assert_equal(OA, OB)\n"
        "assert_centroid(G, A, B, C)\n"
        "assert_on(I, bisB)\n"
    )
    unknown = find_unknown_assert_names(text)
    assert unknown == ["assert_equal"]


def test_find_unknown_assert_names_no_false_positives_on_real_names():
    text = (
        "assert_collinear(O, G, H)\n"
        "assert_equal_length(G1G2, G2G3)\n"
        "assert_centroid(G, G1, G2, G3)\n"
        "assert_right_angle(A, M, B)\n"
        "assert_ratio_equal(AB, DE, BC, EF)\n"
    )
    assert find_unknown_assert_names(text) == []


def test_build_name_correction_message_mentions_unknown_and_real_names():
    msg = build_name_correction_message(["assert_equal"])
    assert "assert_equal" in msg
    assert "assert_equal_length" in msg  # one of the real names, listed as reference
    assert "fix" in msg.lower()


def test_find_unknown_assert_names_after_retry_clears_on_corrected_response():
    """Real prototype outcome (ticket 05): one mechanical retry produced a fully
    corrected response (assert_equal -> assert_angle_equal / assert_ratio_equal)
    with zero unknown functions remaining."""
    corrected = (
        "assert_angle_equal(A, B, C, D)\n"
        "assert_ratio_equal(AB, DE, BC, EF)\n"
    )
    assert find_unknown_assert_names_after_retry(corrected) == []


def test_find_unknown_assert_names_after_retry_still_flags_if_uncorrected():
    still_bad = "assert_equal(OA, OB)\n"
    assert find_unknown_assert_names_after_retry(still_bad) == ["assert_equal"]


# ---------------------------------------------------------------------------
# Stage 2: independent generic-instance grounding
# ---------------------------------------------------------------------------

def _rand_triangle(seed: int = 1):
    rng = random.Random(seed)
    return random_point_defs(["A", "B", "C"], rng=rng)


def test_grounding_flags_confidently_wrong_circumcenter_on_circumcircle():
    """worked_example_strategy1.py case 1: assert_on(O, circumcircle(A,B,C)) is
    geometrically false (a circle's center is never on the circle)."""
    defs = _rand_triangle() + [
        ir_mod.CircleThrough3(id="circ", a="A", b="B", c="C"),
        ir_mod.Triangle(id="tri", a="A", b="B", c="C"),
        ir_mod.PointTriangleCenter(id="O", tri="tri", which="circumcenter"),
    ]
    check = ir_mod.Contains(p="O", obj="circ")
    result = ground_and_evaluate(defs, check)
    assert result.passed is False


def test_grounding_confirms_altitude_foot_collinearity():
    """worked_example_strategy1.py case 2: assert_collinear(H, A, F) where F is
    the foot of the perpendicular from A to BC -- a genuine theorem (H lies on
    every altitude)."""
    defs = _rand_triangle() + [
        ir_mod.Triangle(id="tri", a="A", b="B", c="C"),
        ir_mod.PointTriangleCenter(id="H", tri="tri", which="orthocenter"),
        ir_mod.Segment(id="BC", a="B", b="C"),
        ir_mod.PointFoot(id="F", source="A", onto="BC"),
    ]
    check = ir_mod.Collinear(points=["H", "A", "F"])
    result = ground_and_evaluate(defs, check)
    assert result.passed is True


def test_grounding_flags_euler_line_false_collinearity():
    """experiment_strategy1_broad.py: assert_collinear(O, M, A) does not hold in
    general -- a confidently-wrong claim the API-name check can't catch."""
    defs = _rand_triangle(seed=7) + [
        ir_mod.Triangle(id="tri", a="A", b="B", c="C"),
        ir_mod.PointTriangleCenter(id="O", tri="tri", which="circumcenter"),
        ir_mod.PointMidpoint(id="M", p="B", q="C"),
    ]
    check = ir_mod.Collinear(points=["O", "M", "A"])
    result = ground_and_evaluate(defs, check)
    assert result.passed is False


def test_grounding_confirms_euler_line_true_collinearity():
    """experiment_strategy1_broad.py: assert_collinear(O, G, H) -- the actual
    Euler line theorem, genuinely true."""
    defs = _rand_triangle(seed=7) + [
        ir_mod.Triangle(id="tri", a="A", b="B", c="C"),
        ir_mod.PointTriangleCenter(id="O", tri="tri", which="circumcenter"),
        ir_mod.PointTriangleCenter(id="G", tri="tri", which="centroid"),
        ir_mod.PointTriangleCenter(id="H", tri="tri", which="orthocenter"),
    ]
    check = ir_mod.Collinear(points=["O", "G", "H"])
    result = ground_and_evaluate(defs, check)
    assert result.passed is True


def test_grounding_flags_malformed_arity_call_as_failure():
    """experiment_strategy1_broad.py: EqualLength given raw point ids instead of
    real segment ids -- a type-broken call that should surface as a failure, not
    crash the pre-filter."""
    defs = _rand_triangle(seed=7) + [
        ir_mod.Triangle(id="tri", a="A", b="B", c="C"),
        ir_mod.PointTriangleCenter(id="O", tri="tri", which="circumcenter"),
    ]
    check = ir_mod.EqualLength(segs=["O", "A", "O", "B"])
    result = ground_and_evaluate(defs, check)
    assert result.passed is False


def test_grounding_confirms_incenter_on_angle_bisector():
    """experiment_strategy1_broad.py angle-bisectors-incenter scenario: a genuine
    theorem (the incenter lies on every angle bisector)."""
    defs = _rand_triangle(seed=7) + [
        ir_mod.Triangle(id="tri", a="A", b="B", c="C"),
        ir_mod.PointTriangleCenter(id="I", tri="tri", which="incenter"),
        ir_mod.LineAngleBisector(id="bisB", a="A", vertex="B", b="C"),
    ]
    check = ir_mod.Contains(p="I", obj="bisB")
    result = ground_and_evaluate(defs, check)
    assert result.passed is True


def test_grounding_confirms_napoleon_theorem():
    """experiment_strategy1_broad.py napoleon-theorem scenario: outer Napoleon
    triangle is equilateral -- a genuine, non-trivial theorem."""
    defs = _rand_triangle(seed=7) + [
        ir_mod.Triangle(id="tri0", a="A", b="B", c="C"),
        ir_mod.PolygonExterior(id="e1", a="B", b="C", ref="A", sides=3),
        ir_mod.PolygonExterior(id="e2", a="C", b="A", ref="B", sides=3),
        ir_mod.PolygonExterior(id="e3", a="A", b="B", ref="C", sides=3),
        ir_mod.Triangle(id="t1", a="B", b="C", c="e1_v2"),
        ir_mod.Triangle(id="t2", a="C", b="A", c="e2_v2"),
        ir_mod.Triangle(id="t3", a="A", b="B", c="e3_v2"),
        ir_mod.PointTriangleCenter(id="G1", tri="t1", which="centroid"),
        ir_mod.PointTriangleCenter(id="G2", tri="t2", which="centroid"),
        ir_mod.PointTriangleCenter(id="G3", tri="t3", which="centroid"),
        ir_mod.Segment(id="G1G2", a="G1", b="G2"),
        ir_mod.Segment(id="G2G3", a="G2", b="G3"),
    ]
    check = ir_mod.EqualLength(segs=["G1G2", "G2G3"])
    result = ground_and_evaluate(defs, check)
    assert result.passed is True


def test_grounding_surfaces_error_for_unresolvable_reference_in_defs():
    """A proposal's own defs reference a point id that was never defined --
    compile_defs raises UndefinedRefError (an IRCompileError subclass);
    grounding should surface this as a failure, not raise out of the filter."""
    defs = _rand_triangle(seed=3) + [
        ir_mod.Segment(id="S", a="A", b="MISSING"),
    ]
    check = ir_mod.Collinear(points=["A", "B", "C"])
    result = ground_and_evaluate(defs, check)
    assert result.passed is False
    assert "Grounding error" in result.message


def test_grounding_surfaces_error_for_unresolvable_reference_in_check():
    """A check referencing an id absent from the compiled sym table (but defs
    themselves compile fine) is caught by checks._check_one's own exception
    handling, not by ground_and_evaluate's narrower IRCompileError catch --
    both paths must still surface as a failure, not raise."""
    defs = _rand_triangle(seed=3)
    check = ir_mod.Collinear(points=["A", "B", "NOPE"])
    result = ground_and_evaluate(defs, check)
    assert result.passed is False


def test_grounding_does_not_swallow_a_real_implementation_bug():
    """ground_and_evaluate's except clause is narrowed to IRCompileError --
    a TypeError from passing a check where a DefStmt is expected (a genuine
    caller bug, not a proposal-grounding failure) must propagate rather than
    being mislabeled as a grounding error."""
    defs = _rand_triangle(seed=3) + [ir_mod.Collinear(points=["A", "B", "C"])]  # not a DefStmt
    check = ir_mod.Collinear(points=["A", "B", "C"])
    with pytest.raises(Exception):
        ground_and_evaluate(defs, check)


# ---------------------------------------------------------------------------
# Stage 3: structural lints
# ---------------------------------------------------------------------------

def test_lint_collinear_arity_flags_two_distinct_points():
    """experiment_strategy1_part2.py: assert_collinear(A, M) with only 2 distinct
    points is vacuously true and tests nothing."""
    check = ir_mod.Collinear(points=["A", "M"])
    assert lint_collinear_arity(check) is not None


def test_lint_collinear_arity_passes_three_distinct_points():
    check = ir_mod.Collinear(points=["O", "G", "H"])
    assert lint_collinear_arity(check) is None


def test_lint_collinear_arity_flags_duplicate_points_below_three_distinct():
    """Three listed points but only 2 distinct ids -- still vacuous."""
    check = ir_mod.Collinear(points=["A", "A", "M"])
    assert lint_collinear_arity(check) is not None


def test_lint_self_referential_contains_flags_point_on_its_own_segment():
    """experiment_strategy1_part2.py: assert_on(I, segment(A, I)) -- I is one of
    the segment's own defining endpoints, tautological."""
    defs = [
        ir_mod.PointFixed(id="A", x=0.0, y=0.0),
        ir_mod.PointFixed(id="I", x=1.0, y=1.0),
        ir_mod.Segment(id="AI", a="A", b="I"),
    ]
    defs_by_id = {d.id: d for d in defs}
    check = ir_mod.Contains(p="I", obj="AI")
    assert lint_self_referential_contains(check, defs_by_id) is not None


def test_lint_self_referential_contains_passes_normal_containment():
    """assert_on(I, angle_bisector(A,B,C)) -- I is not a defining endpoint of the
    bisector line, not tautological."""
    defs = [
        ir_mod.PointFixed(id="A", x=0.0, y=0.0),
        ir_mod.PointFixed(id="B", x=1.0, y=0.0),
        ir_mod.PointFixed(id="C", x=0.0, y=1.0),
        ir_mod.PointFixed(id="I", x=0.3, y=0.3),
        ir_mod.LineAngleBisector(id="bisB", a="A", vertex="B", b="C"),
    ]
    defs_by_id = {d.id: d for d in defs}
    check = ir_mod.Contains(p="I", obj="bisB")
    assert lint_self_referential_contains(check, defs_by_id) is None


def test_lint_self_referential_contains_ignores_non_contains_checks():
    check = ir_mod.Collinear(points=["A", "B", "C"])
    assert lint_self_referential_contains(check, {}) is None


def test_lint_self_referential_contains_handles_unknown_object_gracefully():
    check = ir_mod.Contains(p="I", obj="not_defined")
    assert lint_self_referential_contains(check, {}) is None


@pytest.mark.parametrize(
    "label,check,defs,expect_flagged",
    [
        (
            "assert_on(O, circumcircle) -- real check, not degenerate",
            ir_mod.Contains(p="O", obj="circ"),
            [
                ir_mod.PointFixed(id="A", x=0.0, y=0.0),
                ir_mod.PointFixed(id="B", x=1.0, y=0.0),
                ir_mod.PointFixed(id="C", x=0.0, y=1.0),
                ir_mod.Triangle(id="tri", a="A", b="B", c="C"),
                ir_mod.PointTriangleCenter(id="O", tri="tri", which="circumcenter"),
                ir_mod.CircleThrough3(id="circ", a="A", b="B", c="C"),
            ],
            False,
        ),
        (
            "assert_collinear(O,G,H) -- real Euler line check",
            ir_mod.Collinear(points=["O", "G", "H"]),
            [],
            False,
        ),
        (
            "assert_collinear(A,M) -- degenerate: 2 distinct points",
            ir_mod.Collinear(points=["A", "M"]),
            [],
            True,
        ),
        (
            "assert_on(I, bisector) -- real incenter/bisector check",
            ir_mod.Contains(p="I", obj="bisB"),
            [
                ir_mod.PointFixed(id="A", x=0.0, y=0.0),
                ir_mod.PointFixed(id="B", x=1.0, y=0.0),
                ir_mod.PointFixed(id="C", x=0.0, y=1.0),
                ir_mod.LineAngleBisector(id="bisB", a="A", vertex="B", b="C"),
            ],
            False,
        ),
        (
            "assert_on(I, segment(A,I)) -- degenerate: self-referential",
            ir_mod.Contains(p="I", obj="AI"),
            [
                ir_mod.PointFixed(id="A", x=0.0, y=0.0),
                ir_mod.PointFixed(id="I", x=1.0, y=1.0),
                ir_mod.Segment(id="AI", a="A", b="I"),
            ],
            True,
        ),
    ],
)
def test_run_lints_matches_prototype_expectations(label, check, defs, expect_flagged):
    """experiment_strategy1_part2.py part (a): zero false positives across real
    checks, 2/2 true positives on the known degenerate cases."""
    finding = run_lints(check, defs)
    assert (finding is not None) == expect_flagged, label
