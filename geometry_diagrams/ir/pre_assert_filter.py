"""Pre-assert pre-filter, stages 1-4: API-name validation, independent
generic-instance grounding, the two structural lints, and the
request-relevance rule.

Stages 1-3 were validated by a discardable prototype
(.scratch/pre-assert-proposal/, see issues/05-validation-pass.md) as
deterministic pure functions with no LLM judgment call needed to detect a
problem -- only, optionally, to fix one once flagged (stage 1's one mechanical
retry). This module ports that validated behavior; it does not re-derive it.

Stage 4 (request-relevance) is NOT validated by that prototype -- ticket 08's
"0 of ~60 checks were extra" was a manual/human classification of real
checks, not a tested algorithm. It is designed fresh here per
.scratch/pydsl-pre-assert-pipeline/spec.md's Implementation Decisions, and its
own tests (tests/test_pre_assert_filter.py) record an honest, partial result:
see check_request_relevance's docstring and
.scratch/pydsl-pre-assert-pipeline/reports/02-request-relevance-rule-report.md
for where it does and does not cleanly separate the fixtures.

Deliberately NOT covered here (see .scratch/pydsl-pre-assert-pipeline/spec.md):
- the pre-step LLM call that produces proposals in the first place (ticket 03)
- any graph/strategy integration (ticket 04)

Every function in this module is pure and takes no model/network dependency:
inputs are `ir.Check`/`ir.DefStmt` objects or plain text, outputs are booleans,
strings, lists, or `checks.CheckResult`.
"""
from __future__ import annotations

import inspect
import re
from random import Random

import geometry_diagrams.pydsl as pydsl_module
from . import ir
from .checks import DEFAULT_TOL, CheckResult, _check_one
from .errors import IRCompileError
from .to_sympy import compile_defs

# ---------------------------------------------------------------------------
# Stage 1: API-name validation
# ---------------------------------------------------------------------------

# The real 25-function assert_* vocabulary, introspected the same way
# retry.py's PUBLIC_API_FUNCTION_NAMES already does for the shipped
# hallucinated-name retry path -- functions only (not handle classes), and
# restricted to the assert_ prefix since that's the only vocabulary a
# pre-step proposal is allowed to invent calls against.
REAL_ASSERT_NAMES: frozenset[str] = frozenset(
    name
    for name in pydsl_module.__all__
    if name.startswith("assert_") and inspect.isfunction(getattr(pydsl_module, name))
)

_ASSERT_TOKEN_PATTERN = re.compile(r"assert_[a-zA-Z_]+")


def extract_assert_tokens(text: str) -> list[str]:
    """Every assert_[a-zA-Z_]+-shaped token in `text`, deduplicated, in
    first-seen order. Pure regex extraction -- no attempt to parse call
    syntax or arguments, matching the prototype's approach."""
    seen: dict[str, None] = {}
    for tok in _ASSERT_TOKEN_PATTERN.findall(text):
        seen.setdefault(tok, None)
    return list(seen)


def find_unknown_assert_names(text: str) -> list[str]:
    """assert_*-shaped tokens in `text` that are not real pydsl assert_*
    function names. Exact-match diff against REAL_ASSERT_NAMES, not judgment
    -- validated in the prototype with zero false positives/negatives."""
    return [tok for tok in extract_assert_tokens(text) if tok not in REAL_ASSERT_NAMES]


def build_name_correction_message(unknown_names: list[str]) -> str:
    """The one mechanical retry prompt validated in the prototype: 'these
    don't exist, here are the real ones, fix only these lines'. This message
    only needs to be produced once -- see find_unknown_assert_names_after_retry
    for checking the result, since the design is exactly one retry, not a loop."""
    unknown_list = ", ".join(sorted(unknown_names))
    real_list = ", ".join(sorted(REAL_ASSERT_NAMES))
    return (
        f"These function name(s) do not exist in the pydsl API: {unknown_list}. "
        f"The real assert_* functions are: {real_list}. "
        "Fix only the lines that use an unknown name -- leave every other line "
        "unchanged."
    )


def find_unknown_assert_names_after_retry(corrected_text: str) -> list[str]:
    """Apply the one mechanical retry: re-run the same API-name validation
    against the model's corrected response. There is deliberately no further
    retry loop here -- the validated design is exactly one mechanical fix
    attempt (see issues/05-validation-pass.md); any names still unknown after
    this call are reported as-is, not retried again."""
    return find_unknown_assert_names(corrected_text)


# ---------------------------------------------------------------------------
# Stage 2: independent generic-instance grounding
# ---------------------------------------------------------------------------

DEFAULT_COORD_BOUND = 5.0


def random_point_defs(
    ids: list[str],
    rng: Random | None = None,
    bound: float = DEFAULT_COORD_BOUND,
) -> list[ir.PointFixed]:
    """Build PointFixed defs with arbitrary/random coordinates for `ids` --
    the only "made up" input grounding needs. Every other DefStmt in a
    grounded instance is a lookup against this codebase's existing
    vocabulary, not an invention (mirrors the prototype's `rand_triangle()`
    helper in experiment_strategy1_broad.py)."""
    rng = rng if rng is not None else Random()
    return [
        ir.PointFixed(id=pid, x=rng.uniform(-bound, bound), y=rng.uniform(-bound, bound))
        for pid in ids
    ]


def ground_and_evaluate(
    defs: list[ir.DefStmt],
    check: ir.Check,
    tol: float = DEFAULT_TOL,
) -> CheckResult:
    """Build a reference instance from `defs` (existing ir.DefStmt primitives
    only) and evaluate `check` against it via the existing checks._check_one.

    `defs` must already include a definition for every point/object `check`
    references -- including any new implicit points the proposal introduced,
    given their stated derivation (e.g. "midpoint of BC" -> PointMidpoint) --
    and concrete coordinates (e.g. via random_point_defs) for whatever the
    proposal leaves free. No aesthetic/rendering concerns apply; any valid
    instance works, per the prototype's finding.

    Malformed/type-broken calls and unresolvable references surface as
    passed=False with an explanatory message rather than raising -- a broken
    proposal is itself a pre-filter failure worth surfacing, not a crash.
    """
    try:
        sym = compile_defs(ir.DiagramIR(define=defs))
    except IRCompileError as exc:
        # The closed to_sympy.py compile-error hierarchy (UndefinedRefError,
        # IntersectionError, PickError, ExprEvalError, all subclassing
        # IRCompileError -- see errors.py) covers exactly "this proposal
        # doesn't ground cleanly": an unresolved ref, a degenerate
        # construction, an ambiguous pick, a bad expression. Anything outside
        # that hierarchy is a real implementation bug in compile_defs, not a
        # proposal-grounding failure, and must propagate rather than being
        # mislabeled and swallowed here.
        return CheckResult(check=check, passed=False, message=f"Grounding error: {exc!r}")
    return _check_one(check, sym, tol)


# ---------------------------------------------------------------------------
# Stage 3: structural lints
# ---------------------------------------------------------------------------

# DefStmt kinds with two defining endpoints, and the field names holding
# them -- the only shapes a self-referential Contains/NotContains lint needs
# to recognize. Ported verbatim from experiment_strategy1_part2.py.
_ENDPOINT_FIELDS: dict[str, tuple[str, str]] = {
    "Segment": ("a", "b"),
    "Ray": ("a", "b"),
    "LineThrough": ("p", "q"),
}


def lint_collinear_arity(check: ir.Check) -> str | None:
    """A Collinear check given fewer than 3 distinct points is vacuously true
    -- it tests nothing (any 1-2 points are trivially "collinear")."""
    if isinstance(check, ir.Collinear):
        n_distinct = len(set(check.points))
        if n_distinct < 3:
            return (
                f"Collinear given only {n_distinct} distinct point(s) -- "
                "vacuously true, tests nothing"
            )
    return None


def lint_self_referential_contains(
    check: ir.Check,
    defs_by_id: dict[str, ir.DefStmt],
) -> str | None:
    """A Contains/NotContains check is tautological when the target object's
    own defining endpoints include the point being tested -- e.g.
    assert_on(I, segment(A, I)), vacuously true by construction."""
    if not isinstance(check, (ir.Contains, ir.NotContains)):
        return None
    obj_def = defs_by_id.get(check.obj)
    if obj_def is None:
        return None
    fields = _ENDPOINT_FIELDS.get(type(obj_def).__name__)
    if fields is None:
        return None
    endpoints = {getattr(obj_def, f) for f in fields}
    if check.p in endpoints:
        return (
            f"point {check.p!r} is itself one of the defining endpoints of "
            f"{check.obj!r} -- tautological"
        )
    return None


_LINTS = (lint_collinear_arity, lint_self_referential_contains)


def run_lints(check: ir.Check, defs: list[ir.DefStmt]) -> str | None:
    """Run both structural lints against `check`, given the defs it was
    grounded against. Returns the first finding, or None if neither lint
    flags anything."""
    defs_by_id = {d.id: d for d in defs}
    for lint in _LINTS:
        finding = (
            lint(check, defs_by_id) if lint is lint_self_referential_contains else lint(check)
        )
        if finding:
            return finding
    return None


# ---------------------------------------------------------------------------
# Stage 4: request-relevance rule (UNVALIDATED -- see module docstring)
# ---------------------------------------------------------------------------
#
# spec.md's Implementation Decisions describe the rule as: a proposed check
# passes if every point/object it references is either (a) a point whose
# label appears literally in the request string, or (b) a point the
# proposal's own snippet defines via one of a fixed allow-list of derivation
# primitives (midpoint, foot-of-perpendicular, angle bisector, a named
# triangle center, circle-through-3-points) applied only to already-covered
# points.
#
# Two interpretive gaps in that text had to be resolved to make it a runnable
# function, and both are design decisions this ticket makes explicitly rather
# than silently:
#
# 1. "Every point/object it references" literally, taken at face value, would
#    require even a plain `segment(A, B)` wrapper to itself be either
#    literally labeled or produced by one of the five listed primitives --
#    but "segment"/"triangle"/"line_through" aren't on that list, so almost
#    no real check (nearly all of which reference points through segment/
#    triangle wrapper objects) could ever pass. Read that literally, the rule
#    would flag ~all of ticket 08's corpus, which contradicts the ticket's
#    own expectation that the negative fixtures pass cleanly. The resolution
#    adopted here: a pure multi-point *wrapper* object -- one that names no
#    new point and adds no new free parameter, just groups already-covered
#    points (segment, ray, line_through, triangle, polygon, polyline_open,
#    circle-center-through-a-point, point-alias) -- is transparent and
#    decomposes into its referenced points/objects without itself needing to
#    be on the allow-list. The five-item allow-list is reserved for
#    primitives that mint a genuinely *new* point/object from covered inputs.
#    This is an extension beyond the spec's literal five-item enumeration,
#    made here as the only reading that makes the rule non-vacuous; see the
#    report for the full reasoning.
# 2. The spec's allow-list is silent on which DefStmt kinds are pure wrapper
#    vs. which introduce a new free parameter. CircleCenterRadius (an
#    arbitrary radius), PointBetween (an arbitrary ratio), PointFixed with
#    literal coordinates, PointFree, PointOn, PolygonExterior/PolygonOnEdge
#    (a new polygon's non-request-labeled vertices) are all treated as
#    opaque/non-transparent here -- deliberately, since each can carry a new
#    unrequested numeric constraint, which is exactly the failure mode this
#    stage exists to catch.
#
# A third, more serious finding survived honest testing rather than being
# designed around: the rule as specified has a structural blind spot for the
# *one* real "extra" example in the entire investigation (ticket 03's
# AB=AC-on-a-bare-triangle case). See check_request_relevance's docstring.

# Pure "wrapper" DefStmt kinds: they group/rename already-covered points or
# objects and introduce no new point and no new free numeric parameter, so
# they decompose transparently into their referenced ids regardless of the
# five-item allow-list below. Field names list every id-valued field to
# recurse into (list-valued fields, e.g. Polygon.points, are handled by
# _resolve_field_ids).
_TRANSPARENT_WRAPPER_FIELDS: dict[str, tuple[str, ...]] = {
    "Segment": ("a", "b"),
    "Ray": ("a", "b"),
    "LineThrough": ("p", "q"),
    "Triangle": ("a", "b", "c"),
    "Polygon": ("points",),
    "PolylineOpen": ("points",),
    "CircleCenterPoint": ("center", "through"),
    "PointAlias": ("ref",),
}

# The five derivation primitives spec.md's Implementation Decisions names
# explicitly: each mints exactly one new point/object from already-covered
# points via a fixed, parameter-free geometric rule.
_ALLOWED_DERIVATION_FIELDS: dict[str, tuple[str, ...]] = {
    "PointMidpoint": ("p", "q"),
    "PointFoot": ("source", "onto"),
    "PointTriangleCenter": ("tri",),
    "LineAngleBisector": ("a", "vertex", "b"),
    "CircleThrough3": ("a", "b", "c"),
}

# DefStmt kinds recognized for coverage propagation -- the union of the two
# tables above, keyed by class name (matches the dispatch style already used
# by _ENDPOINT_FIELDS above).
_COVERAGE_PROPAGATING_FIELDS: dict[str, tuple[str, ...]] = {
    **_TRANSPARENT_WRAPPER_FIELDS,
    **_ALLOWED_DERIVATION_FIELDS,
}


def _label_appears_in_request(label: str, request: str) -> bool:
    """Whether `label` appears as a standalone token in `request` -- a
    word-boundary match, not a substring, so a single-letter id like "A"
    doesn't spuriously match inside "ABC" or "Draw". Matches the real
    scenario corpus's own phrasing ("Label the circumcenter O and all three
    vertices A, B, and C")."""
    pattern = r"(?<![A-Za-z0-9_])" + re.escape(label) + r"(?![A-Za-z0-9_])"
    return re.search(pattern, request) is not None


def _resolve_field_ids(defstmt: ir.DefStmt, field: str) -> list[str]:
    """The id(s) held by one field of `defstmt` -- a single id, or every
    element of a list field (e.g. Polygon.points)."""
    value = getattr(defstmt, field)
    return list(value) if isinstance(value, list) else [value]


def _find_uncovered_leaf(
    obj_id: str,
    defs_by_id: dict[str, ir.DefStmt],
    request: str,
    _seen: frozenset[str] = frozenset(),
) -> str | None:
    """None if `obj_id` is "covered" for request-relevance purposes: either
    its label appears literally in `request`, or it is reachable from
    literally-covered points through a chain of transparent wrappers and/or
    allow-listed derivation primitives (see the tables above). Otherwise,
    the id of the specific uncovered point/object at the bottom of that
    chain (which may be `obj_id` itself, or a point buried inside a wrapper
    object `obj_id` resolves to) -- named so a caller can say *why* a check
    failed, not just that it did.

    `_seen` guards against a reference cycle in `defs_by_id` (not expected
    from real proposals, but must not infinite-loop on one) -- an id
    revisited within its own resolution chain is treated as its own failure
    rather than raising.
    """
    if obj_id in _seen:
        return obj_id
    if _label_appears_in_request(obj_id, request):
        return None

    defstmt = defs_by_id.get(obj_id)
    if defstmt is None:
        return obj_id

    fields = _COVERAGE_PROPAGATING_FIELDS.get(type(defstmt).__name__)
    if fields is None:
        return obj_id

    seen = _seen | {obj_id}
    for field in fields:
        for ref_id in _resolve_field_ids(defstmt, field):
            leaf = _find_uncovered_leaf(ref_id, defs_by_id, request, seen)
            if leaf is not None:
                return leaf
    return None


def direct_ids_referenced(check: ir.Check) -> list[str]:
    """Every point/object id `check` references directly -- the starting set
    for request-relevance coverage. `_find_uncovered_leaf` resolves each one
    further through `defs`."""
    match check:
        case ir.DistinctPoints(a=a, b=b) | ir.MinDistance(a=a, b=b):
            return [a, b]
        case ir.DistinctObjects(a=a, b=b):
            return [a, b]
        case ir.NonCollinear(a=a, b=b, c=c):
            return [a, b, c]
        case ir.Collinear(points=points):
            return list(points)
        case ir.Contains(p=p, obj=obj) | ir.NotContains(p=p, obj=obj):
            return [p, obj]
        case ir.Parallel(l1=l1, l2=l2) | ir.NotParallel(l1=l1, l2=l2) | ir.Perpendicular(
            l1=l1, l2=l2
        ):
            return [l1, l2]
        case ir.AngleEqual(a1=a1, a2=a2):
            return [a1.a, a1.o, a1.b, a2.a, a2.o, a2.b]
        case ir.SimilarTriangles(t1=t1, t2=t2) | ir.CongruentTriangles(t1=t1, t2=t2):
            return [t1, t2]
        case ir.RatioEqual(s1=s1, s2=s2, s3=s3, s4=s4):
            return [s1, s2, s3, s4]
        case ir.EqualLength(segs=segs):
            return list(segs)
        case ir.DistanceEquals(seg=seg):
            return [seg]
        case ir.RightAngle(angle=angle):
            return [angle.a, angle.o, angle.b]
        case ir.Tangent(line=line, circle=circle):
            return [line, circle]
        case ir.OppositeSide(p=p, q=q, line_a=line_a, line_b=line_b) | ir.SameSide(
            p=p, q=q, line_a=line_a, line_b=line_b
        ):
            return [p, q, line_a, line_b]
        case ir.Centroid(g=g, a=a, b=b, c=c):
            return [g, a, b, c]
        case ir.Convex(polygon=polygon) | ir.CCW(polygon=polygon):
            return [polygon]
        case _:
            raise TypeError(
                f"Unhandled Check type for request-relevance extraction: {type(check).__name__}"
            )


def check_request_relevance(
    check: ir.Check,
    defs: list[ir.DefStmt],
    request: str,
) -> str | None:
    """Stage 4: the request-relevance rule (UNVALIDATED -- see module and
    section docstrings above). Returns None if `check` passes (is
    "entailed"); otherwise a message identifying the first uncovered
    reference (the check is "extra").

    `defs` must include a DefStmt for every point/object the proposal itself
    introduced (mirroring `ground_and_evaluate`'s contract) so its stated
    derivation is visible to this rule -- a point with no DefStmt and no
    literal label in `request` is treated as uncovered, not given the
    benefit of the doubt.

    Honest finding from testing this against real and constructed fixtures
    (see tests/test_pre_assert_filter.py and the ticket 02 report): this
    rule, run exactly as specified, correctly separates every check in
    ticket 08's ~60-check "entailed" corpus from two new synthetic "extra"
    fixtures that each introduce a new, request-uncovered point. It does
    NOT correctly flag the ticket's own given canonical "extra" example
    (ticket 03: `assert_equal_length(segment(A,B), segment(A,C))` against
    the bare request "draw a triangle ABC") -- that check references only
    A, B, and C, which are literally named by the request, so it passes as
    "entailed" under this rule even though it is the one case everyone
    agrees should be "extra". The rule as specified detects "extra via an
    uncovered new point"; it structurally cannot detect "extra via a new
    constraint imposed directly on already-covered points, introducing no
    new point at all" -- which is exactly the shape of the one confirmed
    real-world case. This is reported rather than patched around: see the
    ticket 02 report for the full account and options going forward.
    """
    defs_by_id = {d.id: d for d in defs}
    for obj_id in direct_ids_referenced(check):
        leaf = _find_uncovered_leaf(obj_id, defs_by_id, request)
        if leaf is not None:
            via = f" (referenced via {obj_id!r})" if leaf != obj_id else ""
            return (
                f"{leaf!r}{via} is neither literally named in the request nor derived from "
                "request-covered points via an allow-listed primitive (midpoint, "
                "foot-of-perpendicular, angle bisector, a named triangle center, "
                "circle-through-3-points) -- treated as an unrequested 'extra' addition"
            )
    return None
