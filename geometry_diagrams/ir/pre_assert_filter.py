"""Pre-assert pre-filter, stages 1-3: API-name validation, independent
generic-instance grounding, and the two structural lints.

These three stages were validated by a discardable prototype
(.scratch/pre-assert-proposal/, see issues/05-validation-pass.md) as
deterministic pure functions with no LLM judgment call needed to detect a
problem -- only, optionally, to fix one once flagged (stage 1's one mechanical
retry). This module ports that validated behavior; it does not re-derive it.

Deliberately NOT covered here (see .scratch/pydsl-pre-assert-pipeline/spec.md):
- the request-relevance rule (stage 4, ticket 02) -- unvalidated, designed fresh
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
from .to_sympy import compile_defs

# ---------------------------------------------------------------------------
# Stage 1: API-name validation
# ---------------------------------------------------------------------------

# The real 24-function assert_* vocabulary, introspected the same way
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
    except Exception as exc:  # noqa: BLE001 - deliberately broad: any
        # compilation failure (unresolved ref, degenerate construction, bad
        # pick, ...) is itself evidence the proposal doesn't ground cleanly.
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
