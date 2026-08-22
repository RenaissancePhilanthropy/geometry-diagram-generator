"""Tests for geometry_diagrams/strategies/pre_assert_step.py -- the pre-step
LLM-calling layer on top of ir/pre_assert_filter.py's pure 4-stage pre-filter
(tickets 01-02).

Only the LLM call is mocked (same convention as tests/test_python_full_strategy.py)
-- parsing, per-check filtering, and advisory-text assembly are all pure and
tested directly with hand-built fixtures, no live model call needed. One
integration test exercises `propose_and_filter_checks` end to end (including
the one mechanical stage-1 retry) against a mocked model response.

Scenarios reused from .scratch/pre-assert-proposal/experiment_01.py's SCENARIOS
set per issues/03-pre-step-call.md's own suggestion, adapted to this module's
own point-definition grammar (see pre_assert_step.py's module docstring for why
that grammar differs from the real pydsl API and from experiment_02.py's
REAL_API_VOCAB, which itself referenced a "point_between" function that isn't
part of the real, current pydsl API).
"""
from __future__ import annotations

import random
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from geometry_diagrams.ir import ir as ir_mod
from geometry_diagrams.strategies.pre_assert_step import (
    FilteredCheck,
    ParsedCheck,
    assemble_advisory_text,
    build_assert_vocabulary_block,
    build_pre_step_system_prompt,
    call_pre_step_model,
    filter_parsed_check,
    parse_proposal_text,
    propose_and_filter_checks,
)

_CIRCUMSCRIBED_CIRCLE_REQUEST = (
    "Draw a triangle ABC with its circumscribed circle. Label the "
    "circumcenter O and all three vertices A, B, and C."
)
_EULER_LINE_REQUEST = (
    "Draw a triangle ABC showing three triangle centers: the circumcenter O, "
    "centroid G, and orthocenter H, indicating that they are collinear on "
    "the Euler line. Label all six points A, B, C, O, G, and H."
)
_ISOSCELES_REQUEST = (
    "Draw an isosceles triangle ABC where AB equals AC. Label all three "
    "vertices A, B, and C."
)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def test_build_assert_vocabulary_block_has_24_real_signatures():
    """Sanity check against the shipped assert_* feature's actual vocabulary --
    generated from live introspection, not a hand-copied string (see module
    docstring; mirrors instructions_python_full.py's approach)."""
    block = build_assert_vocabulary_block()
    lines = block.splitlines()
    assert len(lines) == 24
    assert all(line.startswith("def assert_") for line in lines)
    assert "def assert_collinear(" in block
    assert "def assert_in_canvas(" in block  # listed even though unsupported downstream


def test_build_pre_step_system_prompt_includes_vocab_and_grammar():
    prompt = build_pre_step_system_prompt()
    assert "def assert_equal_length(" in prompt
    assert "midpoint(A, B)" in prompt
    assert "triangle_center(A, B, C" in prompt
    assert "3-5" in prompt


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def test_parse_recognizes_all_five_point_definition_forms():
    text = """\
M = midpoint(B, C)
F = foot_of_perpendicular(A, B, C)
bis = angle_bisector(A, B, C)
H = triangle_center(A, B, C, "orthocenter")
circ = circle_through(A, B, C)
assert_distinct_points(M, F)
"""
    proposal = parse_proposal_text(text)
    assert proposal.unparsed_lines == []
    assert len(proposal.checks) == 1
    check = proposal.checks[0].check
    assert isinstance(check, ir_mod.DistinctPoints)
    defs_by_id = {d.id: d for d in proposal.checks[0].defs}
    assert isinstance(defs_by_id["M"], ir_mod.PointMidpoint)
    assert defs_by_id["M"].p == "B" and defs_by_id["M"].q == "C"
    assert isinstance(defs_by_id["F"], ir_mod.PointFoot)
    assert defs_by_id["F"].source == "A"
    onto = defs_by_id[defs_by_id["F"].onto]
    assert isinstance(onto, ir_mod.LineThrough) and onto.p == "B" and onto.q == "C"
    assert isinstance(defs_by_id["bis"], ir_mod.LineAngleBisector)
    assert defs_by_id["bis"].a == "A" and defs_by_id["bis"].vertex == "B" and defs_by_id["bis"].b == "C"
    tri_center = defs_by_id["H"]
    assert isinstance(tri_center, ir_mod.PointTriangleCenter) and tri_center.which == "orthocenter"
    tri = defs_by_id[tri_center.tri]
    assert isinstance(tri, ir_mod.Triangle) and (tri.a, tri.b, tri.c) == ("A", "B", "C")
    assert isinstance(defs_by_id["circ"], ir_mod.CircleThrough3)


def test_parse_resolves_wrapper_calls_inline():
    text = "assert_equal_length(segment(O, A), segment(O, B))\n"
    proposal = parse_proposal_text(text)
    assert len(proposal.checks) == 1
    parsed = proposal.checks[0]
    check = parsed.check
    assert isinstance(check, ir_mod.EqualLength)
    defs_by_id = {d.id: d for d in parsed.defs}
    seg1 = defs_by_id[check.segs[0]]
    seg2 = defs_by_id[check.segs[1]]
    assert {(seg1.a, seg1.b), (seg2.a, seg2.b)} == {("O", "A"), ("O", "B")}


def test_parse_resolves_angle_and_triangle_wrappers():
    text = (
        "assert_right_angle(angle(A, M, B))\n"
        "assert_similar_triangles(triangle(A, B, C), triangle(D, E, F))\n"
    )
    proposal = parse_proposal_text(text)
    assert len(proposal.checks) == 2
    right_angle = proposal.checks[0].check
    assert isinstance(right_angle, ir_mod.RightAngle)
    assert (right_angle.angle.a, right_angle.angle.o, right_angle.angle.b) == ("A", "M", "B")
    similar = proposal.checks[1].check
    assert isinstance(similar, ir_mod.SimilarTriangles)


def test_parse_extracts_trailing_comment():
    text = "assert_collinear(O, G, H)  # Euler line theorem\n"
    proposal = parse_proposal_text(text)
    assert proposal.checks[0].comment == "Euler line theorem"
    assert proposal.checks[0].raw_text == "assert_collinear(O, G, H)"


def test_parse_flags_unknown_assert_name():
    text = "assert_equal(O, A)\n"
    proposal = parse_proposal_text(text)
    parsed = proposal.checks[0]
    assert parsed.check is None
    assert parsed.unresolved_name == "assert_equal"


def test_parse_flags_unsupported_argument_shape_as_parse_error():
    """assert_distance's second argument must be a literal number -- a bound
    variable (something this grammar never teaches how to define as a plain
    number) can't be resolved, and should be reported as a parse error, not
    silently guessed at or crash the parser."""
    text = "assert_distance(segment(A, B), some_length)\n"
    proposal = parse_proposal_text(text)
    parsed = proposal.checks[0]
    assert parsed.check is None
    assert parsed.unresolved_name is None
    assert parsed.parse_error is not None


def test_parse_ignores_assert_in_canvas_no_backing_check_kind():
    """assert_in_canvas is a real assert_* name (so stage 1 doesn't flag it),
    but has no backing ir.Check kind (see asserts.py) -- this module's builder
    table deliberately doesn't handle it, so it's a parse_error, not a crash."""
    text = "assert_in_canvas(A)\n"
    proposal = parse_proposal_text(text)
    parsed = proposal.checks[0]
    assert parsed.check is None
    assert parsed.unresolved_name is None
    assert parsed.parse_error is not None


def test_parse_records_prose_and_blank_lines_as_unparsed_not_errors():
    text = (
        "Here is my proposal for this construction:\n"
        "\n"
        "assert_not_collinear(A, B, C)\n"
    )
    proposal = parse_proposal_text(text)
    assert len(proposal.checks) == 1
    assert proposal.unparsed_lines == ["Here is my proposal for this construction:"]


def test_parse_tolerates_stray_code_fence_markers():
    text = "```python\nassert_not_collinear(A, B, C)\n```\n"
    proposal = parse_proposal_text(text)
    assert len(proposal.checks) == 1
    assert proposal.checks[0].check is not None


def test_parse_rejects_arbitrary_new_point_definition():
    """A point defined any way other than the five recognized forms (here: a
    fixed literal coordinate, which real pydsl scripts write as point(x, y))
    is not added to point_defs -- per the module's design, this simply leaves
    `Z` un-derived. Downstream, grounding treats it as an ordinary "base"
    point (gets a random coordinate, same as A/B/C) so a generically-true
    claim about it still grounds fine and passes the lints -- it's
    request-relevance (stage 4) that actually catches it, since `Z` is
    neither literally named in the request nor derived via an allow-listed
    primitive."""
    text = (
        "Z = point(3.0, 4.0)\n"
        "assert_distinct_points(Z, A)\n"
    )
    proposal = parse_proposal_text(text)
    assert "Z = point(3.0, 4.0)" in proposal.unparsed_lines
    parsed = proposal.checks[0]
    assert parsed.check is not None  # DistinctPoints(Z, A) builds fine syntactically
    result = filter_parsed_check(parsed, "Draw a triangle ABC.")
    assert result.outcome == "extra"
    assert result.stage == "relevance"
    assert "'Z'" in result.message


def test_parsing_full_scenario_snippet_from_experiment_01_scenario_set():
    """A realistic multi-check proposal for the euler-line scenario (one of
    experiment_01.py's SCENARIOS), exercising several point-def forms and
    wrapper calls together."""
    text = """\
# O, G, H are collinear on the Euler line -- the central claim of the request
assert_collinear(O, G, H)

# G is the centroid of ABC
assert_centroid(G, A, B, C)

M = midpoint(B, C)
F = foot_of_perpendicular(A, B, C)
# H lies on every altitude, so H, A, F are collinear
assert_collinear(H, A, F)
"""
    proposal = parse_proposal_text(text)
    assert len(proposal.checks) == 3
    kinds = [type(c.check).__name__ for c in proposal.checks]
    assert kinds == ["Collinear", "Centroid", "Collinear"]


# ---------------------------------------------------------------------------
# End-to-end filtering: routing through all 4 stages
# ---------------------------------------------------------------------------

def _rng(seed: int = 1) -> random.Random:
    return random.Random(seed)


def test_filter_routes_unknown_name_to_api_name_stage():
    """filter_parsed_check is called directly here, with no retry having run at
    all -- unlike test_propose_and_filter_checks_still_rejects_if_retry_does_not_fix_it,
    which reaches this same stage through the full orchestrator after a real
    retry. The message must be accurate for both call shapes: it must not
    unconditionally assert that a retry ran, since filter_parsed_check itself
    has no way of knowing whether one did."""
    parsed = ParsedCheck(raw_text="assert_equal(O, A)", comment=None, check=None,
                          unresolved_name="assert_equal")
    result = filter_parsed_check(parsed, _CIRCUMSCRIBED_CIRCLE_REQUEST)
    assert result.outcome == "rejected"
    assert result.stage == "api_name"
    assert "assert_equal" in result.message
    assert "if the one mechanical name-correction retry ran" in result.message


def test_filter_routes_unparseable_call_to_parse_stage():
    parsed = ParsedCheck(raw_text="assert_in_canvas(A)", comment=None, check=None,
                          parse_error="no backing ir.Check kind")
    result = filter_parsed_check(parsed, _CIRCUMSCRIBED_CIRCLE_REQUEST)
    assert result.outcome == "rejected"
    assert result.stage == "parse"


def test_filter_routes_geometrically_false_claim_to_grounding_stage():
    """assert_on(O, circ) where circ is the actual circumcircle and O is just a
    random point (not the real circumcenter) -- confidently wrong, caught by
    stage 2 grounding before it ever reaches request-relevance."""
    circ = ir_mod.CircleThrough3(id="circ", a="A", b="B", c="C")
    check = ir_mod.Contains(p="O", obj="circ")
    parsed = ParsedCheck(raw_text="assert_on(O, circ)", comment=None, check=check, defs=[circ])
    result = filter_parsed_check(parsed, _CIRCUMSCRIBED_CIRCLE_REQUEST, rng=_rng(2))
    assert result.outcome == "rejected"
    assert result.stage == "grounding"


def test_filter_routes_degenerate_lint_case_to_lint_stage():
    check = ir_mod.Collinear(points=["A", "M"])
    parsed = ParsedCheck(raw_text="assert_collinear(A, M)", comment=None, check=check, defs=[])
    result = filter_parsed_check(parsed, _ISOSCELES_REQUEST, rng=_rng(3))
    assert result.outcome == "rejected"
    assert result.stage == "lint"


def test_filter_routes_ab_equals_ac_on_bare_triangle_to_grounding_not_relevance():
    """AB=AC on a bare, generic triangle request is pre_assert_filter.py's own
    documented "extra" example that check_request_relevance (stage 4, tested
    in isolation) fails to catch -- but run through the FULL pipeline, this
    check is caught anyway, one stage earlier: it isn't true in general (only
    true because of how a specific construction happened to place its
    points), so an independent random instance of A, B, C fails it at
    grounding (stage 2) before request-relevance ever gets a look. A genuine,
    if incidental, finding worth recording -- stage 4's documented blind spot
    for "no new point, just a fresh constraint on covered points" doesn't
    actually let a false claim of this shape through the full pipeline,
    because such a claim is (by construction of the scenario) not generically
    true either."""
    ab = ir_mod.Segment(id="AB", a="A", b="B")
    ac = ir_mod.Segment(id="AC", a="A", b="C")
    check = ir_mod.EqualLength(segs=["AB", "AC"])
    parsed = ParsedCheck(
        raw_text="assert_equal_length(segment(A, B), segment(A, C))", comment=None,
        check=check, defs=[ab, ac],
    )
    request = "Draw a triangle ABC. Label all three vertices A, B, and C."
    result = filter_parsed_check(parsed, request, rng=_rng(4))
    assert result.outcome == "rejected"
    assert result.stage == "grounding"


def test_filter_routes_new_uncovered_point_to_relevance_extra():
    """A genuinely uncovered new point (fixed, no request coverage, no
    allow-listed derivation) paired with a generically-true claim about it
    (two random points are almost surely distinct) -- grounds true, no lint
    finding, so it's request-relevance (stage 4) that must catch it, landing
    in "extra" rather than "entailed" or "rejected"."""
    z = ir_mod.PointFixed(id="Z", x=3.0, y=4.0)
    check = ir_mod.DistinctPoints(a="Z", b="O")
    request = (
        "Draw a circle with center O and a chord AB. Label the center O "
        "and the chord's endpoints A and B."
    )
    parsed = ParsedCheck(
        raw_text="assert_distinct_points(Z, O)", comment=None,
        check=check, defs=[z],
    )
    result = filter_parsed_check(parsed, request, rng=_rng(5))
    assert result.outcome == "extra"
    assert result.stage == "relevance"
    assert "'Z'" in result.message


def test_filter_passes_genuine_theorem_as_entailed():
    """The incenter lies on every angle bisector -- a genuine theorem, grounds
    true, no lint finding, and I (a triangle-center-derived point, covered by
    the allow-list) is request-covered."""
    request = (
        "Draw triangle ABC with all three angle bisectors meeting at the "
        "incenter I. Label A, B, C, and I."
    )
    tri = ir_mod.Triangle(id="tri", a="A", b="B", c="C")
    i_point = ir_mod.PointTriangleCenter(id="I", tri="tri", which="incenter")
    bisB = ir_mod.LineAngleBisector(id="bisB", a="A", vertex="B", b="C")
    check = ir_mod.Contains(p="I", obj="bisB")
    parsed = ParsedCheck(
        raw_text="assert_on(I, bisB)", comment="I is the incenter, on every bisector",
        check=check, defs=[tri, i_point, bisB],
    )
    result = filter_parsed_check(parsed, request, rng=_rng(6))
    assert result.outcome == "entailed"
    assert result.stage == "relevance"
    assert result.message is None


def test_filter_confirms_euler_line_true_theorem_as_entailed():
    tri = ir_mod.Triangle(id="tri", a="A", b="B", c="C")
    o = ir_mod.PointTriangleCenter(id="O", tri="tri", which="circumcenter")
    g = ir_mod.PointTriangleCenter(id="G", tri="tri", which="centroid")
    h = ir_mod.PointTriangleCenter(id="H", tri="tri", which="orthocenter")
    check = ir_mod.Collinear(points=["O", "G", "H"])
    parsed = ParsedCheck(
        raw_text="assert_collinear(O, G, H)", comment=None, check=check,
        defs=[tri, o, g, h],
    )
    result = filter_parsed_check(parsed, _EULER_LINE_REQUEST, rng=_rng(7))
    assert result.outcome == "entailed"


# ---------------------------------------------------------------------------
# Advisory-text assembly
# ---------------------------------------------------------------------------

def test_assemble_advisory_text_empty_when_nothing_entailed():
    filtered = [
        FilteredCheck(raw_text="x", comment=None, check=None, outcome="rejected",
                       stage="grounding", message="nope"),
        FilteredCheck(raw_text="y", comment=None, check=None, outcome="extra",
                       stage="relevance", message="uncovered"),
    ]
    assert assemble_advisory_text(filtered) == ""


def test_assemble_advisory_text_includes_only_entailed_checks():
    filtered = [
        FilteredCheck(raw_text="assert_collinear(O, G, H)", comment="Euler line",
                       check=None, outcome="entailed", stage="relevance", message=None),
        FilteredCheck(raw_text="assert_equal_length(seg(O,Z), seg(O,A))", comment=None,
                       check=None, outcome="extra", stage="relevance", message="uncovered 'Z'"),
        FilteredCheck(raw_text="assert_on(O, circ)", comment=None, check=None,
                       outcome="rejected", stage="grounding", message="false"),
    ]
    text = assemble_advisory_text(filtered)
    assert "assert_collinear(O, G, H)" in text
    assert "Euler line" in text
    assert "assert_equal_length" not in text  # the "extra" one must not leak in
    assert "assert_on(O, circ)" not in text  # the rejected one must not leak in
    assert "OPTIONAL" in text  # advisory-safety framing, not a hard contract


def test_assemble_advisory_text_never_contains_hard_contract_language():
    filtered = [
        FilteredCheck(raw_text="assert_not_collinear(A, B, C)", comment=None,
                       check=None, outcome="entailed", stage="relevance", message=None),
    ]
    text = assemble_advisory_text(filtered)
    assert "OPTIONAL" in text
    assert "do not" in text.lower()  # explicit anti-steering framing, not a hard contract
    assert "graded" not in text.lower()
    assert "REQUIRED" not in text


# ---------------------------------------------------------------------------
# The LLM-calling layer (mocked -- same convention as test_python_full_strategy.py)
# ---------------------------------------------------------------------------

def _mock_llm(*responses: str) -> MagicMock:
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=[MagicMock(content=r) for r in responses])
    return mock_llm


@pytest.mark.asyncio
async def test_call_pre_step_model_returns_raw_text():
    mock_llm = _mock_llm("assert_not_collinear(A, B, C)\n")
    with patch("geometry_diagrams.strategies.pre_assert_step.get_chat_model", return_value=mock_llm):
        text = await call_pre_step_model(_ISOSCELES_REQUEST, "anthropic:claude-sonnet-4-6")
    assert text == "assert_not_collinear(A, B, C)\n"
    assert mock_llm.ainvoke.call_count == 1


@pytest.mark.asyncio
async def test_propose_and_filter_checks_end_to_end_no_retry_needed():
    """A clean recorded-style response (real assert_* names throughout) --
    exercises the full orchestrator without needing the retry path."""
    response = """\
# H lies on every altitude of ABC
M = midpoint(B, C)
assert_collinear(H, A, M)  # not the real altitude foot, so this should ground false

# O is equidistant from the vertices -- the actual circumcenter property
assert_equal_length(segment(O, A), segment(O, B))
"""
    mock_llm = _mock_llm(response)
    with patch("geometry_diagrams.strategies.pre_assert_step.get_chat_model", return_value=mock_llm):
        result = await propose_and_filter_checks(
            _EULER_LINE_REQUEST, "anthropic:claude-sonnet-4-6", rng=_rng(42),
        )
    assert result.retried is False
    assert mock_llm.ainvoke.call_count == 1
    assert len(result.filtered_checks) == 2
    stages = {fc.raw_text: fc.stage for fc in result.filtered_checks}
    assert all(stage in ("grounding", "relevance") for stage in stages.values())


@pytest.mark.asyncio
async def test_propose_and_filter_checks_retries_once_on_hallucinated_name():
    """The one mechanical retry: a first response with a hallucinated
    assert_equal name gets one correction round-trip, and the corrected
    response is what actually gets parsed/filtered."""
    bad_response = "assert_equal(O, A)\n"
    corrected_response = "assert_distinct_points(O, A)\n"
    mock_llm = _mock_llm(bad_response, corrected_response)
    with patch("geometry_diagrams.strategies.pre_assert_step.get_chat_model", return_value=mock_llm):
        result = await propose_and_filter_checks(
            _CIRCUMSCRIBED_CIRCLE_REQUEST, "anthropic:claude-sonnet-4-6", rng=_rng(1),
        )
    assert result.retried is True
    assert mock_llm.ainvoke.call_count == 2
    assert result.raw_response == corrected_response
    assert len(result.filtered_checks) == 1
    assert result.filtered_checks[0].outcome == "entailed"


@pytest.mark.asyncio
async def test_propose_and_filter_checks_still_rejects_if_retry_does_not_fix_it():
    bad_response = "assert_equal(O, A)\n"
    still_bad_response = "assert_equal(O, A)\n"  # model fails to correct itself
    mock_llm = _mock_llm(bad_response, still_bad_response)
    with patch("geometry_diagrams.strategies.pre_assert_step.get_chat_model", return_value=mock_llm):
        result = await propose_and_filter_checks(
            _CIRCUMSCRIBED_CIRCLE_REQUEST, "anthropic:claude-sonnet-4-6",
        )
    assert result.retried is True
    assert len(result.filtered_checks) == 1
    assert result.filtered_checks[0].outcome == "rejected"
    assert result.filtered_checks[0].stage == "api_name"
    assert result.advisory_text == ""
