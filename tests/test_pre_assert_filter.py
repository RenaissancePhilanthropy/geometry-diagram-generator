# tests/test_pre_assert_filter.py
"""Tests for ir/pre_assert_filter.py -- the pre-assert pre-filter's four
stages: three prototype-validated pure-function stages (API-name validation,
generic-instance grounding, structural lints) plus the fourth,
NOT-prototype-validated request-relevance rule (see that module's docstrings
and .scratch/pydsl-pre-assert-pipeline/reports/02-request-relevance-rule-report.md
for the honest account of where it does and doesn't work). No LLM calls
anywhere in this module or these tests.

Fixtures for stages 1-3 are ported from the discardable prototype under
.scratch/pre-assert-proposal/ (worked_example_strategy1.py,
experiment_strategy1_broad.py, experiment_strategy1_part2.py) -- known-correct
and known-wrong proposed checks from real model output, not invented cases.

Fixtures for stage 4 (see the "Stage 4" section far below) are:
- negative: real request strings + real proposed checks from
  .scratch/pre-assert-proposal/experiment_01_results.json,
  experiment_01b_results.json, and experiment_06_proposals_results.json (the
  raw data behind issues/08-relevance-filter-scoping.md's "~60 checks, all
  classified entailed" finding), reconstructed as structured ir.Check/
  ir.DefStmt fixtures the way ticket 01 already reconstructed its own
  fixtures from prose.
- positive: the one given synthetic "extra" case from
  issues/03-splice-vs-advisory.md, plus new synthetic cases built the same
  way (a request that leaves a property free, paired with a check that
  constrains it via a point not on the allow-list).
"""
import random

import pytest

from geometry_diagrams.ir import ir as ir_mod
from geometry_diagrams.ir.pre_assert_filter import (
    REAL_ASSERT_NAMES,
    build_name_correction_message,
    check_request_relevance,
    direct_ids_referenced,
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

def test_real_assert_names_has_25_entries():
    """Sanity check against the shipped assert_* feature's actual vocabulary."""
    assert len(REAL_ASSERT_NAMES) == 25
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


# ---------------------------------------------------------------------------
# Stage 4: request-relevance rule (UNVALIDATED -- see pre_assert_filter.py's
# module docstring and check_request_relevance's docstring)
# ---------------------------------------------------------------------------

_AP = ir_mod.AnglePoints


# --- Negative fixtures: real checks from the ~60-check corpus (ticket 08) ---
# Each entry reconstructs one real proposed check (from experiment_01,
# experiment_01b, or experiment_06_proposals_results.json) as structured
# ir.Check/ir.DefStmt objects, using the real request string for that
# scenario. All ~60 real checks were classified "entailed" by ticket 08's
# manual review; none of these should be flagged by the mechanical rule.

_CIRCUMSCRIBED_CIRCLE_REQUEST = (
    "Draw a triangle ABC with its circumscribed circle. Label the "
    "circumcenter O and all three vertices A, B, and C."
)
_CIRCUMSCRIBED_CIRCLE_DEFS = [
    ir_mod.Triangle(id="tri", a="A", b="B", c="C"),
    ir_mod.PointTriangleCenter(id="O", tri="tri", which="circumcenter"),
    ir_mod.CircleThrough3(id="circ", a="A", b="B", c="C"),
    ir_mod.Segment(id="OA", a="O", b="A"),
    ir_mod.Segment(id="OB", a="O", b="B"),
]

_EULER_LINE_REQUEST = (
    "Draw a triangle ABC showing three triangle centers: the circumcenter O, "
    "centroid G, and orthocenter H, indicating that they are collinear on "
    "the Euler line. Label all six points A, B, C, O, G, and H."
)
_EULER_LINE_DEFS = [
    ir_mod.Triangle(id="tri", a="A", b="B", c="C"),
    ir_mod.PointTriangleCenter(id="O", tri="tri", which="circumcenter"),
    ir_mod.PointTriangleCenter(id="G", tri="tri", which="centroid"),
    ir_mod.PointTriangleCenter(id="H", tri="tri", which="orthocenter"),
    ir_mod.PointMidpoint(id="M", p="B", q="C"),
    ir_mod.Segment(id="BC", a="B", b="C"),
    ir_mod.PointFoot(id="F", source="A", onto="BC"),
    ir_mod.Segment(id="OA", a="O", b="A"),
    ir_mod.Segment(id="OB", a="O", b="B"),
]

_NAPOLEON_REQUEST = (
    "Draw triangle ABC. On each side, construct an equilateral triangle "
    "pointing outward: triangle on BC with outer vertex P, on CA with outer "
    "vertex Q, on AB with outer vertex R. Find the centroids G1 (of triangle "
    "on BC), G2 (of triangle on CA), G3 (of triangle on AB). Label A, B, C, "
    "P, Q, R, G1, G2, G3"
)
_NAPOLEON_DEFS = [
    ir_mod.Triangle(id="t1", a="B", b="C", c="P"),
    ir_mod.Triangle(id="t2", a="C", b="A", c="Q"),
    ir_mod.Triangle(id="t3", a="A", b="B", c="R"),
    ir_mod.PointTriangleCenter(id="G1", tri="t1", which="centroid"),
    ir_mod.PointTriangleCenter(id="G2", tri="t2", which="centroid"),
    ir_mod.PointTriangleCenter(id="G3", tri="t3", which="centroid"),
    ir_mod.PointMidpoint(id="M1", p="B", q="C"),
    ir_mod.Triangle(id="tri0", a="A", b="B", c="C"),
    ir_mod.PointTriangleCenter(id="G", tri="tri0", which="centroid"),
    ir_mod.Segment(id="G1G2", a="G1", b="G2"),
    ir_mod.Segment(id="G2G3", a="G2", b="G3"),
    ir_mod.Segment(id="G3G1", a="G3", b="G1"),
    ir_mod.Segment(id="G1B", a="G1", b="B"),
    ir_mod.Segment(id="G1P", a="G1", b="P"),
    ir_mod.Segment(id="G1C", a="G1", b="C"),
    ir_mod.Segment(id="G2C", a="G2", b="C"),
    ir_mod.Segment(id="G2A", a="G2", b="A"),
    ir_mod.Segment(id="G2Q", a="G2", b="Q"),
]

_ISOSCELES_REQUEST = (
    "Draw an isosceles triangle ABC where AB equals AC. Label all three "
    "vertices A, B, and C."
)
_ISOSCELES_DEFS = [
    ir_mod.Segment(id="AB", a="A", b="B"),
    ir_mod.Segment(id="AC", a="A", b="C"),
    ir_mod.PointMidpoint(id="M", p="B", q="C"),
    ir_mod.Triangle(id="tri", a="A", b="B", c="C"),
    ir_mod.PointTriangleCenter(id="O", tri="tri", which="circumcenter"),
    ir_mod.PointTriangleCenter(id="H", tri="tri", which="orthocenter"),
    ir_mod.LineThrough(id="AM", p="A", q="M"),
    ir_mod.LineThrough(id="BC", p="B", q="C"),
]

_NINE_POINT_REQUEST = (
    "Draw triangle ABC with the nine-point circle. Show the midpoints of "
    "each side: D on BC, E on AC, F on AB. Label the nine-point center N "
    "and all seven points A, B, C, D, E, F, N."
)
_NINE_POINT_DEFS = [
    ir_mod.PointMidpoint(id="D", p="B", q="C"),
    ir_mod.PointMidpoint(id="E", p="A", q="C"),
    ir_mod.PointMidpoint(id="F", p="A", q="B"),
    ir_mod.CircleThrough3(id="nine_pt", a="D", b="E", c="F"),
    ir_mod.Segment(id="ND", a="N", b="D"),
    ir_mod.Segment(id="NE", a="N", b="E"),
    ir_mod.Triangle(id="tri", a="A", b="B", c="C"),
    ir_mod.PointTriangleCenter(id="H", tri="tri", which="orthocenter"),
    # proposal's own stated derivation: "M is the midpoint of segment NH ...
    # H = orthocenter of ABC" -- both N (literal) and H (named triangle
    # center) are covered, so the midpoint M is covered too.
    ir_mod.PointMidpoint(id="M", p="N", q="H"),
]

_INCENTER_REQUEST = (
    "Draw triangle ABC with all three angle bisectors meeting at the "
    "incenter I. Label A, B, C, and I."
)
_INCENTER_DEFS = [
    ir_mod.LineAngleBisector(id="bisB", a="A", vertex="B", b="C"),
    ir_mod.LineAngleBisector(id="bisA", a="B", vertex="A", b="C"),
    ir_mod.Segment(id="AB", a="A", b="B"),
    ir_mod.Segment(id="BC", a="B", b="C"),
    ir_mod.PointFoot(id="foot_ItoAB", source="I", onto="AB"),
    ir_mod.PointFoot(id="foot_ItoBC", source="I", onto="BC"),
    ir_mod.Segment(id="IfootAB", a="I", b="foot_ItoAB"),
    ir_mod.Segment(id="IfootBC", a="I", b="foot_ItoBC"),
    ir_mod.Segment(id="AI", a="A", b="I"),
]

_CYCLIC_QUAD_REQUEST = (
    "Draw a cyclic quadrilateral ABCD inscribed in a circle with center O. "
    "Label all five points A, B, C, D, and O."
)
_CYCLIC_QUAD_DEFS = [
    ir_mod.CircleCenterPoint(id="circ", center="O", through="A"),
    ir_mod.Segment(id="OA", a="O", b="A"),
    ir_mod.Segment(id="OB", a="O", b="B"),
]

_SIMILAR_TRIANGLES_REQUEST = (
    "Draw two similar triangles ABC and DEF side by side, with "
    "corresponding sides marked to show the similarity. Label all six "
    "vertices A, B, C, D, E, and F."
)
_SIMILAR_TRIANGLES_DEFS = [
    ir_mod.Triangle(id="t1", a="A", b="B", c="C"),
    ir_mod.Triangle(id="t2", a="D", b="E", c="F"),
    ir_mod.Segment(id="AB", a="A", b="B"),
    ir_mod.Segment(id="DE", a="D", b="E"),
    ir_mod.Segment(id="BC", a="B", b="C"),
    ir_mod.Segment(id="EF", a="E", b="F"),
    ir_mod.Segment(id="CA", a="C", b="A"),
    ir_mod.Segment(id="FD", a="F", b="D"),
]

_TANGENT_CIRCLE_REQUEST = (
    "Draw a circle with center O and a tangent line from an external point "
    "P, touching the circle at point T. Label the center O, the external "
    "point P, and the tangency point T."
)
_TANGENT_CIRCLE_DEFS = [
    ir_mod.CircleCenterPoint(id="circ", center="O", through="T"),
    ir_mod.LineThrough(id="PT", p="P", q="T"),
]


@pytest.mark.parametrize(
    "label,request_str,defs,check",
    [
        (
            "circumscribed-circle: assert_on(O, circumcircle(A,B,C))",
            _CIRCUMSCRIBED_CIRCLE_REQUEST,
            _CIRCUMSCRIBED_CIRCLE_DEFS,
            ir_mod.Contains(p="O", obj="circ"),
        ),
        (
            "circumscribed-circle: assert_equal_length(seg(O,A), seg(O,B))",
            _CIRCUMSCRIBED_CIRCLE_REQUEST,
            _CIRCUMSCRIBED_CIRCLE_DEFS,
            ir_mod.EqualLength(segs=["OA", "OB"]),
        ),
        (
            "circumscribed-circle: assert_on(A, circumcircle(A,B,C))",
            _CIRCUMSCRIBED_CIRCLE_REQUEST,
            _CIRCUMSCRIBED_CIRCLE_DEFS,
            ir_mod.Contains(p="A", obj="circ"),
        ),
        (
            "circumscribed-circle (gpt-5.6-luna): assert_on(A, Γ) with a "
            "non-ASCII circle id",
            _CIRCUMSCRIBED_CIRCLE_REQUEST,
            _CIRCUMSCRIBED_CIRCLE_DEFS
            + [ir_mod.CircleThrough3(id="Γ", a="A", b="B", c="C")],
            ir_mod.Contains(p="A", obj="Γ"),
        ),
        (
            "euler-line: assert_collinear(O, G, H)",
            _EULER_LINE_REQUEST,
            _EULER_LINE_DEFS,
            ir_mod.Collinear(points=["O", "G", "H"]),
        ),
        (
            "euler-line: assert_centroid(G, A, B, C)",
            _EULER_LINE_REQUEST,
            _EULER_LINE_DEFS,
            ir_mod.Centroid(g="G", a="A", b="B", c="C"),
        ),
        (
            "euler-line: assert_collinear(O, M, A), M=midpoint(B,C)",
            _EULER_LINE_REQUEST,
            _EULER_LINE_DEFS,
            ir_mod.Collinear(points=["O", "M", "A"]),
        ),
        (
            "euler-line: assert_equal_length(O,A,O,B) circumradius check",
            _EULER_LINE_REQUEST,
            _EULER_LINE_DEFS,
            ir_mod.EqualLength(segs=["OA", "OB"]),
        ),
        (
            "euler-line: assert_collinear(H,A,F), F=foot of perp from A onto BC",
            _EULER_LINE_REQUEST,
            _EULER_LINE_DEFS,
            ir_mod.Collinear(points=["H", "A", "F"]),
        ),
        (
            "napoleon: assert_equal_length(seg(G1,G2), seg(G2,G3))",
            _NAPOLEON_REQUEST,
            _NAPOLEON_DEFS,
            ir_mod.EqualLength(segs=["G1G2", "G2G3"]),
        ),
        (
            "napoleon: assert_equal_length(seg(G1,B), seg(G1,P))",
            _NAPOLEON_REQUEST,
            _NAPOLEON_DEFS,
            ir_mod.EqualLength(segs=["G1B", "G1P"]),
        ),
        (
            "napoleon: assert_collinear(P, G1, M1), M1=midpoint(B,C)",
            _NAPOLEON_REQUEST,
            _NAPOLEON_DEFS,
            ir_mod.Collinear(points=["P", "G1", "M1"]),
        ),
        (
            "napoleon: assert_centroid(G, A, B, C), G=centroid(ABC)",
            _NAPOLEON_REQUEST,
            _NAPOLEON_DEFS,
            ir_mod.Centroid(g="G", a="A", b="B", c="C"),
        ),
        (
            "napoleon: assert_centroid(G, G1, G2, G3)",
            _NAPOLEON_REQUEST,
            _NAPOLEON_DEFS,
            ir_mod.Centroid(g="G", a="G1", b="G2", c="G3"),
        ),
        (
            "isosceles: assert_equal_length(segment(A,B), segment(A,C))",
            _ISOSCELES_REQUEST,
            _ISOSCELES_DEFS,
            ir_mod.EqualLength(segs=["AB", "AC"]),
        ),
        (
            "isosceles: assert_equal_angle(angle(A,B,C), angle(A,C,B))",
            _ISOSCELES_REQUEST,
            _ISOSCELES_DEFS,
            ir_mod.AngleEqual(a1=_AP(a="A", o="B", b="C"), a2=_AP(a="A", o="C", b="B")),
        ),
        (
            "isosceles: assert_collinear(A, M), M=midpoint(B,C)",
            _ISOSCELES_REQUEST,
            _ISOSCELES_DEFS,
            ir_mod.Collinear(points=["A", "M"]),
        ),
        (
            "isosceles: assert_right_angle(angle(A, M, B))",
            _ISOSCELES_REQUEST,
            _ISOSCELES_DEFS,
            ir_mod.RightAngle(angle=_AP(a="A", o="M", b="B")),
        ),
        (
            "isosceles (gpt-oss-20b): assert_perpendicular(line(A,M), line(B,C))",
            _ISOSCELES_REQUEST,
            _ISOSCELES_DEFS,
            ir_mod.Perpendicular(l1="AM", l2="BC"),
        ),
        (
            "isosceles (nemotron): assert_collinear(M, O, H)",
            _ISOSCELES_REQUEST,
            _ISOSCELES_DEFS,
            ir_mod.Collinear(points=["M", "O", "H"]),
        ),
        (
            "isosceles (multiple models): assert_not_collinear(A, B, C)",
            _ISOSCELES_REQUEST,
            _ISOSCELES_DEFS,
            ir_mod.NonCollinear(a="A", b="B", c="C"),
        ),
        (
            "nine-point-circle: assert_on(D, nine_point_circle(A,B,C))",
            _NINE_POINT_REQUEST,
            _NINE_POINT_DEFS,
            ir_mod.Contains(p="D", obj="nine_pt"),
        ),
        (
            "nine-point-circle: assert_on(F, nine_point_circle(A,B,C))",
            _NINE_POINT_REQUEST,
            _NINE_POINT_DEFS,
            ir_mod.Contains(p="F", obj="nine_pt"),
        ),
        (
            "nine-point-circle: assert_equal_length(seg(N,D), seg(N,E))",
            _NINE_POINT_REQUEST,
            _NINE_POINT_DEFS,
            ir_mod.EqualLength(segs=["ND", "NE"]),
        ),
        (
            "nine-point-circle: assert_centroid(M,A,B,C), M=midpoint(N,H)",
            _NINE_POINT_REQUEST,
            _NINE_POINT_DEFS,
            ir_mod.Centroid(g="M", a="A", b="B", c="C"),
        ),
        (
            "angle-bisectors-incenter: assert_on(I, angle_bisector(A,B,C))",
            _INCENTER_REQUEST,
            _INCENTER_DEFS,
            ir_mod.Contains(p="I", obj="bisB"),
        ),
        (
            "angle-bisectors-incenter: assert_on(I, angle_bisector(B,A,C))",
            _INCENTER_REQUEST,
            _INCENTER_DEFS,
            ir_mod.Contains(p="I", obj="bisA"),
        ),
        (
            "angle-bisectors-incenter: assert_equal_length(foot_ItoAB, foot_ItoBC)",
            _INCENTER_REQUEST,
            _INCENTER_DEFS,
            ir_mod.EqualLength(segs=["IfootAB", "IfootBC"]),
        ),
        (
            "angle-bisectors-incenter: assert_on(I, segment(A,I)) self-referential",
            _INCENTER_REQUEST,
            _INCENTER_DEFS,
            ir_mod.Contains(p="I", obj="AI"),
        ),
        (
            "cyclic-quadrilateral: assert_on(A, circle(O, O_A))",
            _CYCLIC_QUAD_REQUEST,
            _CYCLIC_QUAD_DEFS,
            ir_mod.Contains(p="A", obj="circ"),
        ),
        (
            "cyclic-quadrilateral: assert_on(D, circle(O, O_A))",
            _CYCLIC_QUAD_REQUEST,
            _CYCLIC_QUAD_DEFS,
            ir_mod.Contains(p="D", obj="circ"),
        ),
        (
            "cyclic-quadrilateral: assert_equal_length(seg(O,A), seg(O,B))",
            _CYCLIC_QUAD_REQUEST,
            _CYCLIC_QUAD_DEFS,
            ir_mod.EqualLength(segs=["OA", "OB"]),
        ),
        (
            "similar-triangles: assert_similar_triangles(ABC, DEF)",
            _SIMILAR_TRIANGLES_REQUEST,
            _SIMILAR_TRIANGLES_DEFS,
            ir_mod.SimilarTriangles(t1="t1", t2="t2"),
        ),
        (
            "similar-triangles: assert_equal(angle(A,B,C), angle(D,E,F))",
            _SIMILAR_TRIANGLES_REQUEST,
            _SIMILAR_TRIANGLES_DEFS,
            ir_mod.AngleEqual(a1=_AP(a="A", o="B", b="C"), a2=_AP(a="D", o="E", b="F")),
        ),
        (
            "similar-triangles: assert_equal(ratio(AB,DE), ratio(BC,EF))",
            _SIMILAR_TRIANGLES_REQUEST,
            _SIMILAR_TRIANGLES_DEFS,
            ir_mod.RatioEqual(s1="AB", s2="DE", s3="BC", s4="EF"),
        ),
        (
            "tangent-to-circle: assert_right_angle(angle(O,T,P))",
            _TANGENT_CIRCLE_REQUEST,
            _TANGENT_CIRCLE_DEFS,
            ir_mod.RightAngle(angle=_AP(a="O", o="T", b="P")),
        ),
        (
            "tangent-to-circle: assert_on(T, circle(O, O_radius))",
            _TANGENT_CIRCLE_REQUEST,
            _TANGENT_CIRCLE_DEFS,
            ir_mod.Contains(p="T", obj="circ"),
        ),
        (
            "tangent-to-circle: assert_on(P, line(P,T)) self-referential",
            _TANGENT_CIRCLE_REQUEST,
            _TANGENT_CIRCLE_DEFS,
            ir_mod.Contains(p="P", obj="PT"),
        ),
    ],
)
def test_check_request_relevance_negative_corpus_never_flagged(label, request_str, defs, check):
    """Real checks from the ~60-check corpus behind
    issues/08-relevance-filter-scoping.md, reconstructed as structured
    ir.Check/ir.DefStmt fixtures against the real request string for each
    scenario. Ticket 08's manual classification found every one of these
    "entailed"; the mechanical rule must agree."""
    assert check_request_relevance(check, defs, request_str) is None, label


# --- Documented gap: constructions the request names but whose individual
# new vertices aren't labeled by letter, and which use a DefStmt kind
# (PolygonExterior; a generic line/circle intersection) outside the fixed
# five-item allow-list. These are two more REAL checks from the same ~60
# check corpus (pythagorean-theorem, tangent-to-circle) that the rule, as
# specified, does NOT correctly pass -- an honest finding, not smoothed over.
# See check_request_relevance's docstring and the ticket 02 report.

_PYTHAGOREAN_REQUEST = (
    "Draw a right triangle ABC with the right angle at C. Construct squares "
    "on each of the three sides to illustrate the Pythagorean theorem. "
    "Label the vertices A, B, and C."
)
_PYTHAGOREAN_DEFS = [
    ir_mod.PolygonExterior(
        id="sqAC", a="A", b="C", ref="B", sides=4, vertex_names=["A", "C", "C1", "A1"]
    ),
    ir_mod.PolygonExterior(
        id="sqAB", a="A", b="B", ref="C", sides=4, vertex_names=["A", "B", "B2", "A2"]
    ),
    ir_mod.Segment(id="AC", a="A", b="C"),
    ir_mod.Segment(id="CC1", a="C", b="C1"),
    ir_mod.Segment(id="AA1", a="A", b="A1"),
    ir_mod.Segment(id="AB", a="A", b="B"),
    ir_mod.Segment(id="AA2", a="A", b="A2"),
]


def test_check_request_relevance_gap_polygon_exterior_vertices_not_recognized():
    """Real check: assert_equal_length(segment(A,C), segment(C,C1)) -- the
    request explicitly asks for "squares on each of the three sides", and
    C1 is one of the square-on-AC's own vertices, but PolygonExterior isn't
    on the five-item allow-list and "C1" isn't a literal label in the
    request text. Ticket 08 classified this "entailed" (the construction
    itself -- squares on each side -- is exactly what was asked for); the
    mechanical rule flags it as "extra". This is reported as a real gap,
    not patched by adding PolygonExterior to the allow-list ad hoc -- see
    check_request_relevance's docstring."""
    check = ir_mod.EqualLength(segs=["AC", "CC1"])
    result = check_request_relevance(check, _PYTHAGOREAN_DEFS, _PYTHAGOREAN_REQUEST)
    assert result is not None  # documents the gap: this is INCORRECTLY flagged


def test_check_request_relevance_gap_polygon_exterior_right_angle_not_recognized():
    """Same gap, a second real check: assert_right_angle(angle(C1,A,A1))."""
    check = ir_mod.RightAngle(angle=_AP(a="C1", o="A", b="A1"))
    result = check_request_relevance(check, _PYTHAGOREAN_DEFS, _PYTHAGOREAN_REQUEST)
    assert result is not None  # documents the gap: this is INCORRECTLY flagged


def test_check_request_relevance_baseline_right_angle_at_c_still_passes():
    """Control case in the same scenario: the core right-angle check
    references only A, B, C (all literal), so it is correctly NOT flagged --
    the gap above is specific to the square's own new vertices, not the
    whole scenario."""
    check = ir_mod.RightAngle(angle=_AP(a="A", o="C", b="B"))
    assert check_request_relevance(check, _PYTHAGOREAN_DEFS, _PYTHAGOREAN_REQUEST) is None


# --- Positive fixtures: proposed checks that impose a genuinely new,
# unrequested constraint ("extra") ---

def test_check_request_relevance_does_not_flag_ab_equals_ac_case():
    """The one given "extra" example anywhere in the investigation
    (issues/03-splice-vs-advisory.md / experiment_03.py's actual REQUEST
    constant): a bare, generic triangle request plus an injected AB=AC
    constraint the request never asked for.

    HONEST FINDING (not a passing fixture -- see check_request_relevance's
    docstring for the full account): this check references only A, B, and C,
    all of which are literally named by the request, so the rule as
    specified passes it as "entailed". It does NOT catch this case. The
    rule's coverage-based design detects "extra via an uncovered new point";
    it cannot detect "extra via a new constraint on already-covered points
    that introduces no new point at all" -- which is exactly this case's
    shape. This test asserts the actual (non-catching) behavior so the gap
    is pinned down by a test, not just prose."""
    request = "Draw a triangle ABC. Label all three vertices A, B, and C."
    defs = [
        ir_mod.Segment(id="AB", a="A", b="B"),
        ir_mod.Segment(id="AC", a="A", b="C"),
    ]
    check = ir_mod.EqualLength(segs=["AB", "AC"])
    result = check_request_relevance(check, defs, request)
    assert result is None  # NOT flagged -- documents the rule's blind spot


def test_check_request_relevance_flags_new_point_forcing_diagonal_collinearity():
    """Synthetic "extra" case #1 (independently constructed, per the
    ticket's "point on the allow-list" shape): "draw quadrilateral ABCD"
    leaves where the diagonals meet entirely free. The proposal introduces M
    at an arbitrary 1:3 point on diagonal AC (point_between with an
    unrequested ratio, not the allow-listed midpoint primitive) and asserts
    B, M, D are collinear -- forcing a specific, unrequested relationship
    between the diagonals."""
    request = "Draw quadrilateral ABCD. Label the four vertices A, B, C, and D."
    defs = [ir_mod.PointBetween(id="M", a="A", b="C", ratio=0.25)]
    check = ir_mod.Collinear(points=["B", "M", "D"])
    result = check_request_relevance(check, defs, request)
    assert result is not None
    assert "'M'" in result


def test_check_request_relevance_flags_new_point_with_fixed_coordinates():
    """Synthetic "extra" case #2: "draw a circle with center O and a chord
    AB" leaves the chord's length/position free. The proposal introduces an
    arbitrary fixed point Z (not derived from O, A, or B at all) and asserts
    OZ = OA -- an unrequested constraint tying the free chord to a point the
    request never mentioned."""
    request = (
        "Draw a circle with center O and a chord AB. Label the center O "
        "and the chord's endpoints A and B."
    )
    defs = [
        ir_mod.PointFixed(id="Z", x=3.0, y=4.0),
        ir_mod.Segment(id="OZ", a="O", b="Z"),
        ir_mod.Segment(id="OA", a="O", b="A"),
    ]
    check = ir_mod.EqualLength(segs=["OZ", "OA"])
    result = check_request_relevance(check, defs, request)
    assert result is not None
    assert "'Z'" in result


def test_check_request_relevance_flags_unrequested_square_on_bare_triangle():
    """Synthetic "extra" case #3: contrast with the pythagorean-theorem gap
    above. Here "draw triangle ABC" does NOT request any square construction
    at all (unlike pythagorean-theorem's "construct squares on each side"),
    so PolygonExterior's new vertices are correctly flagged -- the gap
    documented above is specific to a request that already names the
    polygon construction; when it doesn't, the rule works as intended."""
    request = "Draw triangle ABC. Label the three vertices A, B, and C."
    defs = [
        ir_mod.PolygonExterior(
            id="sq", a="A", b="B", ref="C", sides=4, vertex_names=["A", "B", "B1", "A1"]
        ),
        ir_mod.Segment(id="AB", a="A", b="B"),
        ir_mod.Segment(id="AB1", a="A", b="B1"),
    ]
    check = ir_mod.EqualLength(segs=["AB", "AB1"])
    result = check_request_relevance(check, defs, request)
    assert result is not None
    assert "'B1'" in result


def test_check_request_relevance_message_names_first_uncovered_reference():
    """The failure message should name the specific uncovered id, not just
    say "extra" -- so a maintainer routing the check can see why."""
    request = "Draw a triangle ABC. Label all three vertices A, B, and C."
    check = ir_mod.EqualLength(segs=["AZ", "AC"])
    result = check_request_relevance(
        check, [ir_mod.Segment(id="AZ", a="A", b="Z"), ir_mod.Segment(id="AC", a="A", b="C")],
        request,
    )
    assert result is not None
    assert "'Z'" in result


def test_direct_ids_referenced_handles_representative_check_kinds():
    """Sanity check on the extraction helper itself, independent of
    coverage resolution -- every field that should surface a referenced id
    does, for a representative sample of Check kinds."""
    assert direct_ids_referenced(ir_mod.Collinear(points=["A", "B", "C"])) == ["A", "B", "C"]
    assert direct_ids_referenced(ir_mod.Contains(p="I", obj="bisB")) == ["I", "bisB"]
    assert direct_ids_referenced(ir_mod.EqualLength(segs=["AB", "AC"])) == ["AB", "AC"]
    assert direct_ids_referenced(
        ir_mod.RightAngle(angle=_AP(a="A", o="M", b="B"))
    ) == ["A", "M", "B"]
    assert direct_ids_referenced(ir_mod.Centroid(g="G", a="A", b="B", c="C")) == [
        "G", "A", "B", "C",
    ]
