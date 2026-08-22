"""The pre-assert pre-step call: the LLM-calling layer on top of
`geometry_diagrams.ir.pre_assert_filter`'s pure 4-stage pre-filter (tickets
01-02), plus the response parsing that turns a raw model proposal into the
structured `ir.Check`/`ir.DefStmt` objects that filter needs.

Deliberately scoped per .scratch/pydsl-pre-assert-pipeline/issues/03-pre-step-call.md:
- YES: the pre-step LLM call, response parsing, running each parsed check
  through all 4 pre-filter stages, and advisory-text assembly.
- NO: any `PythonFullStrategy`/graph integration (ticket 04's job) --
  nothing here reads or writes `PythonFullPipelineState`.

Only `call_pre_step_model`, `call_pre_step_retry_model`, and the orchestrator
`propose_and_filter_checks` touch the network. Every other function in this
module is pure -- parsing, grounding-point bookkeeping, and per-check
filtering can all be exercised with plain text/data fixtures, no live model
call needed (see tests/test_pre_assert_step.py).

## The point-definition grammar this module's prompt teaches the model

Ticket 02's request-relevance rule (`check_request_relevance`) only
recognizes a point/object as "covered" if it's either literally named in
the request, or derived from already-covered points via one of five fixed
primitives: midpoint, foot-of-perpendicular, angle bisector, a named
triangle center, circle-through-3-points. A proposal that introduces a new
point any other way will always fail that stage -- so this module's system
prompt teaches the model a small, closed grammar with exactly those five
point-definition forms (see `_POINT_DEF_BUILDERS` below), plus a handful of
simple grouping wrappers (`segment`, `line_through`, `triangle`, `polygon`,
`angle`) for referencing already-covered points inside an `assert_*` call.

This grammar is NOT the real pydsl API (compare `centroid(t: Triangle)`,
which takes a `Triangle` *handle* built by an earlier `triangle(...)` call,
against this module's `triangle_center(A, B, C, "centroid")`, which takes
three point ids and a kind string directly) -- and that's fine, because the
proposal text is never executed as code. It exists only to be parsed into
`ir.DefStmt`/`ir.Check` objects for the pre-filter; matching real pydsl
syntax exactly would gain nothing and cost real parsing complexity (e.g.
threading a `Triangle` handle's own hidden id through). The real API is
still what this module's `assert_*` vocabulary is generated from (see
`build_assert_vocabulary_block`) -- that's the one place hallucination
actually matters, per the prototype's finding that including it is the
difference between near-0% and near-100% hallucinated names.

A proposal's new-point definition using any other form (e.g. a bare
arithmetic expression, or a real pydsl call this grammar doesn't recognize)
is simply not turned into an `ir.DefStmt` -- any check that then references
it fails to ground (an unresolved reference) or fails request-relevance (an
uncovered id), either way landing in the "rejected"/"extra" bucket rather
than crashing the parser. This is a deliberate simplification per the
ticket's own guidance ("keep it simple... anything else will always fail
the request-relevance check anyway").
"""
from __future__ import annotations

import ast
import itertools
from dataclasses import dataclass, field
from random import Random

from langchain_core.messages import AIMessage, HumanMessage

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.pre_assert_filter import (
    REAL_ASSERT_NAMES,
    build_name_correction_message,
    check_request_relevance,
    direct_ids_referenced,
    find_unknown_assert_names,
    find_unknown_assert_names_after_retry,
    ground_and_evaluate,
    random_point_defs,
    run_lints,
)
from .llm import get_chat_model, make_system_message

# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def build_assert_vocabulary_block() -> str:
    """The real 24 assert_* signatures + docstrings, generated from the live
    pydsl API -- mirrors instructions_python_full.py's build_python_full_instructions()
    approach (call the stub generator at prompt-build time) rather than hand-copying a
    vocabulary string that can drift out of sync with the real API. `generate_stub()`
    already iterates `pydsl.__all__` in declaration order (functions, then handle
    classes, then assert_* functions last); filtering to lines starting with "def
    assert_" is sufficient to isolate just the assert_* vocabulary without needing to
    special-case handle classes here.
    """
    from geometry_diagrams.pydsl.stub import generate_stub

    lines = [line for line in generate_stub().splitlines() if line.startswith("def assert_")]
    return "\n".join(lines)


_POINT_DEF_GRAMMAR = """\
## Defining new points/objects

If a check genuinely needs a point that isn't named in the request, define it BEFORE the \
assert_*(...) call that uses it, using ONLY one of these five forms (one assignment per line, \
using the exact function names below -- these are NOT real pydsl functions, just this \
proposal's own shorthand for describing a derivation):

  NAME = midpoint(A, B)                          # midpoint of A and B
  NAME = foot_of_perpendicular(P, A, B)           # foot of the perpendicular from P onto line AB
  NAME = angle_bisector(A, VERTEX, B)             # the bisector LINE of angle A-VERTEX-B
  NAME = triangle_center(A, B, C, "KIND")         # KIND is one of: "centroid", "circumcenter", \
"incenter", "orthocenter"
  NAME = circle_through(A, B, C)                  # the circle through three points

  # NOTE for a future maintainer grepping for these names: `angle_bisector` and
  # `foot_of_perpendicular` above deliberately collide with real
  # geometry_diagrams.pydsl.api function names of the same name but different
  # signatures -- real `angle_bisector(vertex, toward1, toward2)` takes the
  # vertex FIRST (this grammar's form takes it in the MIDDLE: `angle_bisector(A,
  # VERTEX, B)`), and real `foot_of_perpendicular(point, line)` takes 2 args (a
  # point and an already-built line handle), not this grammar's 3 (`P, A, B`,
  # two bare points defining the line instead of a line handle). This is safe
  # only because this grammar's text is never executed as pydsl code -- it is
  # parsed straight into `ir.DefStmt` objects by `_build_point_definition`
  # below (see module docstring) -- but do not assume the two call shapes are
  # interchangeable if you ever see both names in the same place.

Do NOT define a new point any other way (no arbitrary coordinates, no arbitrary ratios/lengths, \
no other function names) -- a check that depends on such a point will always be rejected, since \
it can't be verified as following from the request.

Inside an assert_*(...) call, you may also reference already-covered points via these plain \
grouping wrappers (not full derivations, just groupings -- use ids you already have):

  segment(P, Q), line_through(P, Q), triangle(P, Q, R), polygon(P, Q, R, ...), angle(A, O, B)
"""


def build_pre_step_system_prompt() -> str:
    """The pre-step's system prompt: proposes 3-5 checks as point-definitions (see
    `_POINT_DEF_GRAMMAR`) + assert_*(...) calls, with the real assert_* vocabulary always
    included (see module docstring for why -- validated in the prototype as the difference
    between near-0% and near-100% hallucinated names)."""
    return f"""\
You are reviewing a geometry construction request BEFORE it gets built. Propose 3-5 geometric \
invariants a CORRECT construction of this request must satisfy -- properties a grader could \
check against the final coordinates to catch a construction bug.

{build_assert_vocabulary_block()}

{_POINT_DEF_GRAMMAR}

## Rules

- Prioritize checks that are NOT already guaranteed by exactly how you would place/construct \
the named points -- do not just restate an input constraint the request already hands you. \
Favor independent, derived properties that a real bug in a DIFFERENT part of the construction \
could actually violate.
- Use the points named in the request directly where relevant; only define a new point per the \
grammar above if a check genuinely needs one.
- Output ONLY point-definition lines and assert_*(...) call lines, one statement per line. A \
"#" comment may follow any line to explain what bug the check would catch. No prose paragraphs, \
no code fences, no imports, no other statements.
"""


# ---------------------------------------------------------------------------
# The LLM calls (the only network-touching functions in this module)
# ---------------------------------------------------------------------------


def _content_to_text(content) -> str:
    return content if isinstance(content, str) else str(content)


async def call_pre_step_model(request: str, model_id: str) -> str:
    """The pre-step's primary call: propose checks for `request`. A separate call from
    script generation (per spec.md's Implementation Decisions), never folded into the
    same request as the construction script itself."""
    llm = get_chat_model(model_id)
    messages = [
        make_system_message(build_pre_step_system_prompt(), model_id=model_id),
        HumanMessage(content=f"Construction request:\n{request}"),
    ]
    response = await llm.ainvoke(messages)
    return _content_to_text(response.content)


async def call_pre_step_retry_model(
    request: str, model_id: str, original_response: str, correction_message: str,
) -> str:
    """The one mechanical retry validated in the prototype: replay the original exchange,
    then hand the model `correction_message` (from
    `pre_assert_filter.build_name_correction_message`) asking it to fix only the lines
    using an unknown assert_* name. Exactly one retry -- see
    `find_unknown_assert_names_after_retry`'s docstring for why there's no further loop."""
    llm = get_chat_model(model_id)
    messages = [
        make_system_message(build_pre_step_system_prompt(), model_id=model_id),
        HumanMessage(content=f"Construction request:\n{request}"),
        AIMessage(content=original_response),
        HumanMessage(content=correction_message),
    ]
    response = await llm.ainvoke(messages)
    return _content_to_text(response.content)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


@dataclass
class ParsedCheck:
    """One assert_*(...) call extracted from a proposal, plus whatever new-point
    DefStmts (accumulated from every point-definition line seen so far in the
    proposal) it might depend on. `check`/`unresolved_name`/`parse_error` are
    mutually informative: `check` is None whenever the line could not be built into
    a structured ir.Check, and exactly one of `unresolved_name` (the function name
    isn't in the real API at all) / `parse_error` (a recognized function but an
    argument shape this module's parser doesn't handle) explains why."""

    raw_text: str
    comment: str | None
    check: "ir.Check | None"
    defs: list[ir.DefStmt] = field(default_factory=list)
    unresolved_name: str | None = None
    parse_error: str | None = None


@dataclass
class ParsedProposal:
    """The result of parsing one proposal's full text: every assert_*(...) call found,
    plus every line that was neither a recognized point-definition nor a recognized
    assert_*(...) call (comments, prose, code fences, blank lines) -- kept for
    diagnosability, not silently dropped."""

    checks: list[ParsedCheck]
    unparsed_lines: list[str] = field(default_factory=list)


def _split_code_and_comment(line: str) -> tuple[str, str | None]:
    """Split `line` into its code part and trailing "#" comment, if any. Naive
    split on the first "#" -- safe here because this module's whole point-
    definition/assert_* grammar has exactly one place a string literal can appear
    (triangle_center's kind argument, e.g. "centroid"), and none of the four
    allowed kind strings contain "#"."""
    if "#" not in line:
        return line, None
    code, comment = line.split("#", 1)
    return code, comment.strip() or None


def _parse_one_statement(code: str) -> "ast.Assign | ast.Expr | None":
    """Parse `code` as exactly one Python statement (an assignment or a bare call
    expression) -- returns None (not raises) for anything else, since a stray
    prose line or blank line is expected input, not a parser bug."""
    code = code.strip()
    if not code:
        return None
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError:
        return None
    if len(tree.body) != 1:
        return None
    stmt = tree.body[0]
    if isinstance(stmt, ast.Assign):
        return stmt
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        return stmt
    return None


_WRAPPER_FIELD_ORDER = {
    "segment": ("Segment", ("a", "b")),
    "line_through": ("LineThrough", ("p", "q")),
    "triangle": ("Triangle", ("a", "b", "c")),
}


def _resolve_ref_arg(
    node: ast.expr, aux_defs: list[ir.DefStmt], counter: "itertools.count[int]",
) -> str | None:
    """Resolve one assert_*(...) argument to a point/object id: a bare Name is
    returned as-is; a recognized grouping-wrapper Call (segment/line_through/
    triangle/polygon) materializes an anonymous DefStmt into `aux_defs` and
    returns its synthetic id. Anything else (an arithmetic expression, an
    unrecognized call, a literal) returns None -- the caller treats that as an
    unparseable check rather than guessing."""
    if isinstance(node, ast.Name):
        return node.id
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
        return None
    fn = node.func.id
    args = node.args
    if fn == "polygon":
        if len(args) < 3 or not all(isinstance(a, ast.Name) for a in args):
            return None
        wid = f"_pre_step_w{next(counter)}"
        aux_defs.append(ir.Polygon(id=wid, points=[a.id for a in args]))
        return wid
    spec = _WRAPPER_FIELD_ORDER.get(fn)
    if spec is None:
        return None
    cls_name, field_names = spec
    if len(args) != len(field_names) or not all(isinstance(a, ast.Name) for a in args):
        return None
    wid = f"_pre_step_w{next(counter)}"
    cls = getattr(ir, cls_name)
    aux_defs.append(cls(id=wid, **{f: a.id for f, a in zip(field_names, args)}))
    return wid


def _resolve_angle_arg(node: ast.expr) -> "ir.AnglePoints | None":
    """Resolve one assert_right_angle/assert_angle_equal argument: must be an
    inline angle(A, O, B) call with three bare-Name points -- a bound variable
    holding an angle ref is not supported (this module's grammar never teaches
    the model to define one, so a proposal that tries is treated as
    unparseable rather than silently guessed at)."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "angle"):
        return None
    if len(node.args) != 3 or not all(isinstance(a, ast.Name) for a in node.args):
        return None
    a, o, b = node.args
    return ir.AnglePoints(a=a.id, o=o.id, b=b.id)


def _const_float(node: ast.expr) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    return None


def _build_check_from_call(
    call: ast.Call, aux_defs: list[ir.DefStmt], counter: "itertools.count[int]",
) -> "ir.Check | None":
    """Build an ir.Check from one assert_*(...) call's AST, or None if this
    module's parser can't map its argument shapes (an unsupported wrapper, a
    non-literal numeric argument, a variable-bound angle ref, ...). Every real
    assert_* function except assert_in_canvas (which has no backing ir.Check
    kind -- see asserts.py's own docstring) is handled below."""
    fn = call.func.id if isinstance(call.func, ast.Name) else None
    args = call.args

    def ref(node: ast.expr) -> str | None:
        return _resolve_ref_arg(node, aux_defs, counter)

    if fn == "assert_distinct_points" and len(args) == 2:
        p, q = ref(args[0]), ref(args[1])
        if p and q:
            return ir.DistinctPoints(a=p, b=q)
    elif fn == "assert_distinct_objects" and len(args) == 2:
        a, b = ref(args[0]), ref(args[1])
        if a and b:
            return ir.DistinctObjects(a=a, b=b)
    elif fn == "assert_not_collinear" and len(args) == 3:
        ids = [ref(a) for a in args]
        if all(ids):
            return ir.NonCollinear(a=ids[0], b=ids[1], c=ids[2])
    elif fn == "assert_collinear" and len(args) >= 2:
        ids = [ref(a) for a in args]
        if all(ids):
            return ir.Collinear(points=ids)
    elif fn == "assert_on" and len(args) == 2:
        p, obj = ref(args[0]), ref(args[1])
        if p and obj:
            return ir.Contains(p=p, obj=obj)
    elif fn == "assert_not_on" and len(args) == 2:
        p, obj = ref(args[0]), ref(args[1])
        if p and obj:
            return ir.NotContains(p=p, obj=obj)
    elif fn == "assert_parallel" and len(args) == 2:
        l1, l2 = ref(args[0]), ref(args[1])
        if l1 and l2:
            return ir.Parallel(l1=l1, l2=l2)
    elif fn == "assert_not_parallel" and len(args) == 2:
        l1, l2 = ref(args[0]), ref(args[1])
        if l1 and l2:
            return ir.NotParallel(l1=l1, l2=l2)
    elif fn == "assert_perpendicular" and len(args) == 2:
        l1, l2 = ref(args[0]), ref(args[1])
        if l1 and l2:
            return ir.Perpendicular(l1=l1, l2=l2)
    elif fn == "assert_right_angle" and len(args) == 1:
        angle = _resolve_angle_arg(args[0])
        if angle:
            return ir.RightAngle(angle=angle)
    elif fn == "assert_angle_equal" and len(args) == 2:
        a1, a2 = _resolve_angle_arg(args[0]), _resolve_angle_arg(args[1])
        if a1 and a2:
            return ir.AngleEqual(a1=a1, a2=a2)
    elif fn == "assert_equal_length" and len(args) >= 2:
        ids = [ref(a) for a in args]
        if all(ids):
            return ir.EqualLength(segs=ids)
    elif fn == "assert_distance" and len(args) == 2:
        seg, expected = ref(args[0]), _const_float(args[1])
        if seg and expected is not None:
            return ir.DistanceEquals(seg=seg, expected=expected)
    elif fn == "assert_ratio_equal" and len(args) == 4:
        ids = [ref(a) for a in args]
        if all(ids):
            return ir.RatioEqual(s1=ids[0], s2=ids[1], s3=ids[2], s4=ids[3])
    elif fn == "assert_similar_triangles" and len(args) == 2:
        t1, t2 = ref(args[0]), ref(args[1])
        if t1 and t2:
            return ir.SimilarTriangles(t1=t1, t2=t2)
    elif fn == "assert_congruent_triangles" and len(args) == 2:
        t1, t2 = ref(args[0]), ref(args[1])
        if t1 and t2:
            return ir.CongruentTriangles(t1=t1, t2=t2)
    elif fn == "assert_tangent" and len(args) == 2:
        line, circle = ref(args[0]), ref(args[1])
        if line and circle:
            return ir.Tangent(line=line, circle=circle)
    elif fn == "assert_opposite_side" and len(args) == 4:
        ids = [ref(a) for a in args]
        if all(ids):
            return ir.OppositeSide(p=ids[0], q=ids[1], line_a=ids[2], line_b=ids[3])
    elif fn == "assert_same_side" and len(args) == 4:
        ids = [ref(a) for a in args]
        if all(ids):
            return ir.SameSide(p=ids[0], q=ids[1], line_a=ids[2], line_b=ids[3])
    elif fn == "assert_centroid" and len(args) == 4:
        ids = [ref(a) for a in args]
        if all(ids):
            return ir.Centroid(g=ids[0], a=ids[1], b=ids[2], c=ids[3])
    elif fn == "assert_convex" and len(args) == 1:
        polygon = ref(args[0])
        if polygon:
            return ir.Convex(polygon=polygon)
    elif fn == "assert_ccw" and len(args) == 1:
        polygon = ref(args[0])
        if polygon:
            return ir.CCW(polygon=polygon)
    elif fn == "assert_min_distance" and len(args) == 3:
        p, q, min_dist = ref(args[0]), ref(args[1]), _const_float(args[2])
        if p and q and min_dist is not None:
            return ir.MinDistance(a=p, b=q, min_dist=min_dist)
    return None


_POINT_DEF_BUILDERS = frozenset(
    {"midpoint", "foot_of_perpendicular", "angle_bisector", "triangle_center", "circle_through"}
)


def _build_point_definition(
    name: str, call: ast.Call, counter: "itertools.count[int]",
) -> "tuple[ir.DefStmt, list[ir.DefStmt]] | None":
    """Build the DefStmt(s) for one `NAME = <primitive>(...)` line, per the five
    forms `_POINT_DEF_GRAMMAR` teaches. Returns (primary_def, aux_defs) --
    aux_defs holds the anonymous intermediate object a primitive needs (e.g.
    foot_of_perpendicular's line, triangle_center's triangle) -- or None if the
    call isn't one of the five recognized forms with the right argument shapes."""
    fn = call.func.id if isinstance(call.func, ast.Name) else None
    args = call.args
    aux: list[ir.DefStmt] = []

    if fn == "midpoint" and len(args) == 2 and all(isinstance(a, ast.Name) for a in args):
        p, q = args
        return ir.PointMidpoint(id=name, p=p.id, q=q.id), aux

    if fn == "foot_of_perpendicular" and len(args) == 3 and all(isinstance(a, ast.Name) for a in args):
        # `foot_of_perpendicular` here is this grammar's own 3-arg shorthand
        # (point, then the two points defining the line), NOT the real
        # geometry_diagrams.pydsl.api.foot_of_perpendicular(point, line), which
        # takes 2 args and a Line handle -- deliberate name collision, safe
        # because this text is only ever parsed into DefStmts, never executed
        # as pydsl code (see _POINT_DEF_GRAMMAR's own note above).
        source, line_a, line_b = args
        line_id = f"_pre_step_w{next(counter)}"
        aux.append(ir.LineThrough(id=line_id, p=line_a.id, q=line_b.id))
        return ir.PointFoot(id=name, source=source.id, onto=line_id), aux

    if fn == "angle_bisector" and len(args) == 3 and all(isinstance(a, ast.Name) for a in args):
        # `angle_bisector` here is this grammar's own shorthand with the
        # vertex in the MIDDLE (A, VERTEX, B), NOT the real
        # geometry_diagrams.pydsl.api.angle_bisector(vertex, toward1, toward2),
        # which takes the vertex FIRST -- deliberate name collision, safe for
        # the same reason as foot_of_perpendicular above (never executed as
        # code).
        a, vertex, b = args
        return ir.LineAngleBisector(id=name, a=a.id, vertex=vertex.id, b=b.id), aux

    if fn == "triangle_center" and len(args) == 4:
        a, b, c, kind_node = args
        if (
            all(isinstance(x, ast.Name) for x in (a, b, c))
            and isinstance(kind_node, ast.Constant)
            and isinstance(kind_node.value, str)
            and kind_node.value in ("centroid", "circumcenter", "incenter", "orthocenter")
        ):
            tri_id = f"_pre_step_w{next(counter)}"
            aux.append(ir.Triangle(id=tri_id, a=a.id, b=b.id, c=c.id))
            return ir.PointTriangleCenter(id=name, tri=tri_id, which=kind_node.value), aux

    if fn == "circle_through" and len(args) == 3 and all(isinstance(a, ast.Name) for a in args):
        a, b, c = args
        return ir.CircleThrough3(id=name, a=a.id, b=b.id, c=c.id), aux

    return None


def parse_proposal_text(text: str) -> ParsedProposal:
    """Parse a raw pre-step response into structured checks. Pure: no model/network
    call, no compile_defs/checks.py dependency -- just AST-level parsing per the
    grammar `build_pre_step_system_prompt` teaches. Tolerant of the model's own
    prose/comments/code fences: any line that isn't a recognized point-definition
    or assert_*(...) call is recorded in `.unparsed_lines`, not treated as an
    error."""
    point_defs: dict[str, ir.DefStmt] = {}
    checks: list[ParsedCheck] = []
    unparsed_lines: list[str] = []
    counter = itertools.count(1)

    for raw_line in text.splitlines():
        if raw_line.strip().startswith("```"):
            continue  # tolerate stray code-fence markers even though the prompt asks for none
        code, comment = _split_code_and_comment(raw_line)
        stmt = _parse_one_statement(code)
        if stmt is None:
            if raw_line.strip():
                unparsed_lines.append(raw_line)
            continue

        if isinstance(stmt, ast.Assign):
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                unparsed_lines.append(raw_line)
                continue
            if not isinstance(stmt.value, ast.Call) or not isinstance(stmt.value.func, ast.Name):
                unparsed_lines.append(raw_line)
                continue
            name = stmt.targets[0].id
            built = _build_point_definition(name, stmt.value, counter)
            if built is None:
                # Not one of the five recognized derivation forms -- deliberately not
                # added to point_defs (see module docstring): any check referencing
                # `name` later will fail to ground/pass relevance on its own.
                unparsed_lines.append(raw_line)
                continue
            primary, aux = built
            for d in aux:
                point_defs[d.id] = d
            point_defs[name] = primary
            continue

        call = stmt.value
        assert isinstance(call, ast.Call)
        fn = call.func.id if isinstance(call.func, ast.Name) else None
        if fn is None or not fn.startswith("assert_"):
            unparsed_lines.append(raw_line)
            continue
        if fn not in REAL_ASSERT_NAMES:
            checks.append(
                ParsedCheck(
                    raw_text=code.strip(), comment=comment, check=None,
                    defs=list(point_defs.values()), unresolved_name=fn,
                )
            )
            continue
        aux_defs: list[ir.DefStmt] = []
        built_check = _build_check_from_call(call, aux_defs, counter)
        if built_check is None:
            checks.append(
                ParsedCheck(
                    raw_text=code.strip(), comment=comment, check=None,
                    defs=list(point_defs.values()),
                    parse_error=(
                        f"could not map {fn}(...)'s arguments to a structured check "
                        "-- unsupported argument shape (e.g. a variable-bound angle "
                        "ref, a non-literal number, or an unrecognized wrapper call)"
                    ),
                )
            )
            continue
        checks.append(
            ParsedCheck(
                raw_text=code.strip(), comment=comment, check=built_check,
                defs=list(point_defs.values()) + aux_defs,
            )
        )

    return ParsedProposal(checks=checks, unparsed_lines=unparsed_lines)


# ---------------------------------------------------------------------------
# End-to-end filtering: run one parsed check through all 4 pre-filter stages
# ---------------------------------------------------------------------------

@dataclass
class FilteredCheck:
    """One parsed check's full pre-filter verdict: which stage it was resolved at
    (not just a bare pass/fail -- per the ticket's own requirement), and why.

    `outcome`:
      - "entailed": passed every stage -- goes into the advisory text.
      - "extra": passed stages 1-3 but failed stage 4 (request-relevance) --
        the rarer category spec.md gates behind a per-model allowlist
        (ticket 04's job, not this module's); kept here, tagged, but never
        included in `assemble_advisory_text`'s output.
      - "rejected": failed stage 1, 2, or 3 -- dropped entirely, never shown
        to the script-writer in any form.
    `stage`: which stage produced this outcome ("api_name" for an unknown
    assert_* name that survived the one retry, "parse" for a line this
    module's parser couldn't map to a Check at all, "grounding", "lint", or
    "relevance").
    `message`: None only for a clean "entailed" pass; otherwise the specific
    rejection/extra reason, for diagnosability.
    """

    raw_text: str
    comment: str | None
    check: "ir.Check | None"
    outcome: str
    stage: str
    message: str | None


# DefStmt kinds this module's own point-definition/wrapper builders produce,
# and which of their fields hold point/object-id references -- used only to
# find which ids are "base" (request-named, ungrounded) points needing a
# random PointFixed def before stage 2 grounding can run. Deliberately a
# separate, smaller table from pre_assert_filter.py's coverage tables (this
# one is about *this module's own* DefStmt vocabulary, not the general
# transparent-wrapper/allow-list distinction stage 4 already owns).
_OWN_DEF_REFERENCE_FIELDS: dict[str, tuple[str, ...]] = {
    "Segment": ("a", "b"),
    "LineThrough": ("p", "q"),
    "Triangle": ("a", "b", "c"),
    "Polygon": ("points",),
    "PointMidpoint": ("p", "q"),
    "PointFoot": ("source", "onto"),
    "LineAngleBisector": ("a", "vertex", "b"),
    "PointTriangleCenter": ("tri",),
    "CircleThrough3": ("a", "b", "c"),
}


def _referenced_ids(defstmt: ir.DefStmt) -> list[str]:
    ids: list[str] = []
    for f in _OWN_DEF_REFERENCE_FIELDS.get(type(defstmt).__name__, ()):
        value = getattr(defstmt, f)
        ids.extend(value if isinstance(value, list) else [value])
    return ids


def _base_point_ids(check: ir.Check, defs: list[ir.DefStmt]) -> set[str]:
    """Every id `check` depends on (directly or via `defs`'s own chain) that
    isn't itself the id of a def in `defs` -- these are the "base" points
    (presumably named directly in the request) grounding needs a concrete
    coordinate for."""
    defs_by_id = {d.id: d for d in defs}
    stack = list(direct_ids_referenced(check))
    seen: set[str] = set()
    base: set[str] = set()
    while stack:
        obj_id = stack.pop()
        if obj_id in seen:
            continue
        seen.add(obj_id)
        d = defs_by_id.get(obj_id)
        if d is None:
            base.add(obj_id)
            continue
        stack.extend(_referenced_ids(d))
    return base


def _defs_with_grounded_base_points(
    check: ir.Check, defs: list[ir.DefStmt], rng: Random | None = None,
) -> list[ir.DefStmt]:
    """`defs` plus a random PointFixed for every base point `check` needs that
    isn't already defined -- the concrete instance stage 2 grounding needs."""
    base_ids = sorted(_base_point_ids(check, defs) - {d.id for d in defs})
    return random_point_defs(base_ids, rng=rng) + list(defs)


def filter_parsed_check(parsed: ParsedCheck, request: str, rng: Random | None = None) -> FilteredCheck:
    """Run one parsed check through the full 4-stage pre-filter, in order, stopping
    at the first stage it fails: API-name validity (already resolved during
    parsing -- see `unresolved_name`), independent generic-instance grounding,
    the two structural lints, and the request-relevance rule. Pure: takes no
    model/network dependency, only `parsed`/`request`/an optional `rng` for
    grounding's random coordinates."""
    if parsed.unresolved_name is not None:
        return FilteredCheck(
            raw_text=parsed.raw_text, comment=parsed.comment, check=None,
            outcome="rejected", stage="api_name",
            message=(
                f"{parsed.unresolved_name!r} is not a real assert_* function -- rejected "
                "outright; if the one mechanical name-correction retry ran on this "
                "response at all, this name was still not resolved by it (this stage "
                "itself never retries -- see propose_and_filter_checks for the only "
                "retry that can happen, at most once, before parsing)"
            ),
        )
    if parsed.check is None:
        return FilteredCheck(
            raw_text=parsed.raw_text, comment=parsed.comment, check=None,
            outcome="rejected", stage="parse",
            message=parsed.parse_error or "could not parse this line into a structured check",
        )

    check = parsed.check
    grounded_defs = _defs_with_grounded_base_points(check, parsed.defs, rng=rng)
    grounding_result = ground_and_evaluate(grounded_defs, check)
    if not grounding_result.passed:
        return FilteredCheck(
            raw_text=parsed.raw_text, comment=parsed.comment, check=check,
            outcome="rejected", stage="grounding", message=grounding_result.message,
        )

    lint_message = run_lints(check, parsed.defs)
    if lint_message:
        return FilteredCheck(
            raw_text=parsed.raw_text, comment=parsed.comment, check=check,
            outcome="rejected", stage="lint", message=lint_message,
        )

    relevance_message = check_request_relevance(check, parsed.defs, request)
    if relevance_message:
        return FilteredCheck(
            raw_text=parsed.raw_text, comment=parsed.comment, check=check,
            outcome="extra", stage="relevance", message=relevance_message,
        )

    return FilteredCheck(
        raw_text=parsed.raw_text, comment=parsed.comment, check=check,
        outcome="entailed", stage="relevance", message=None,
    )


# ---------------------------------------------------------------------------
# Advisory-text assembly
# ---------------------------------------------------------------------------


def assemble_advisory_text(filtered: list[FilteredCheck]) -> str:
    """Prose advisory context built from checks that passed every pre-filter
    stage ("entailed") only. "extra" checks (passed grounding/lints but failed
    request-relevance) and "rejected" checks are never included here -- per
    spec.md, the "extra" category is only ever handed to a script-writer model
    on the (ticket 04-owned) advisory-safety allowlist, and this module's own
    output makes no per-model decision at all.

    Framed as explicitly optional per the prototype's validated
    advisory-safety framing (experiment_07_emphatic.py: "this is entirely
    OPTIONAL... do NOT restructure, complicate, or constrain your
    construction in any way to satisfy it") -- never literal code to splice
    or a hard contract the construction must pass.
    """
    entailed = [f for f in filtered if f.outcome == "entailed"]
    if not entailed:
        return ""
    bullets = "\n".join(
        f"- {f.raw_text}" + (f"  ({f.comment})" if f.comment else "") for f in entailed
    )
    return (
        "## Extra context (optional)\n\n"
        "The following geometric properties are worth considering for this construction, but "
        "are entirely OPTIONAL -- do NOT restructure, complicate, or constrain your "
        "construction in any way to satisfy them. Build them in only if they fit naturally; a "
        "construction that satisfies the primary request without any of them is still a "
        "perfectly correct answer.\n\n"
        f"{bullets}"
    )


# ---------------------------------------------------------------------------
# Orchestration: the one impure entry point tying the layers together
# ---------------------------------------------------------------------------


@dataclass
class PreAssertProposalResult:
    """The full pre-step result: the raw model text (post-retry, if one happened),
    whether the retry fired, every parsed check's filter verdict, any unparsed
    lines (for diagnosability), and the assembled advisory text."""

    raw_response: str
    retried: bool
    filtered_checks: list[FilteredCheck]
    unparsed_lines: list[str]
    advisory_text: str


async def propose_and_filter_checks(
    request: str, model_id: str, rng: Random | None = None,
) -> PreAssertProposalResult:
    """The full pre-step, end to end: call the model, run stage 1 (API-name
    validation) on the raw response text with its one mechanical retry if
    needed, parse the (possibly corrected) response into individual checks,
    run each through stages 2-4, and assemble the survivors' advisory text.

    This is the one function in this module that both calls the model and
    calls the pure pre-filter functions -- everything it delegates to
    (`parse_proposal_text`, `filter_parsed_check`, `assemble_advisory_text`)
    remains independently testable without a live model call.
    """
    raw_text = await call_pre_step_model(request, model_id)
    unknown = find_unknown_assert_names(raw_text)
    retried = False
    if unknown:
        correction_message = build_name_correction_message(unknown)
        raw_text = await call_pre_step_retry_model(request, model_id, raw_text, correction_message)
        retried = True
        find_unknown_assert_names_after_retry(raw_text)  # surfaced per-check via stage "api_name"

    proposal = parse_proposal_text(raw_text)
    filtered = [filter_parsed_check(parsed, request, rng=rng) for parsed in proposal.checks]
    advisory_text = assemble_advisory_text(filtered)
    return PreAssertProposalResult(
        raw_response=raw_text, retried=retried, filtered_checks=filtered,
        unparsed_lines=proposal.unparsed_lines, advisory_text=advisory_text,
    )
