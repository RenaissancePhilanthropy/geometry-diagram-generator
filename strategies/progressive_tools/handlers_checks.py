"""Phase 3 (checks) tool handlers and tool filtering."""
from __future__ import annotations

import json

from ir import ir
from ir.checks import run_checks, CheckResult
from .state import DiagramState

_LINEAR_KINDS = {"segment", "ray", "line_through", "line_parallel_through",
                 "line_perp_through", "line_angle_bisector", "line_tangent"}
_CIRCLE_KINDS = {"circle_center_point", "circle_center_radius", "circle_through3"}
_POINT_KINDS = {
    "point_fixed", "point_free", "point_on", "point_midpoint", "point_between",
    "point_foot", "point_rotate", "point_reflect", "point_triangle_center",
    "point_intersection",
}
_CLOSED_SHAPE_KINDS = {"triangle", "polygon", "polygon_exterior"} | _CIRCLE_KINDS


def check_tool_names_for_state(state: DiagramState) -> list[str]:
    """Return the names of check tools applicable to the current construction."""
    kinds = [d.kind for d in state.defs]
    point_count = sum(1 for k in kinds if k in _POINT_KINDS)
    linear_count = sum(1 for k in kinds if k in _LINEAR_KINDS)
    segment_count = sum(1 for k in kinds if k == "segment")
    circle_count = sum(1 for k in kinds if k in _CIRCLE_KINDS)
    triangle_count = sum(1 for k in kinds if k == "triangle")
    has_line_tangent = any(k == "line_tangent" for k in kinds)
    has_any_object = len(state.defs) > 0

    tools: list[str] = []

    if point_count >= 2:
        tools.append("add_distinct_points_check")
    type_counts: dict[str, int] = {}
    for k in kinds:
        type_counts[k] = type_counts.get(k, 0) + 1
    if any(v >= 2 for v in type_counts.values()):
        tools.append("add_distinct_objects_check")
    if point_count >= 3:
        tools += ["add_collinear_check", "add_non_collinear_check"]
    if linear_count >= 2:
        tools += ["add_parallel_check", "add_not_parallel_check", "add_perpendicular_check"]
    if circle_count >= 1 and has_line_tangent:
        tools.append("add_tangent_check")
    if has_any_object and point_count >= 1:
        tools += ["add_contains_check", "add_not_contains_check"]
    if point_count >= 3:
        tools += ["add_right_angle_check", "add_angle_equal_check"]
    if segment_count >= 2:
        tools += ["add_equal_length_check", "add_ratio_equal_check"]
    if triangle_count >= 2:
        tools.append("add_similar_triangles_check")
    if linear_count >= 1 and point_count >= 2:
        tools += ["add_same_side_check", "add_opposite_side_check"]

    return tools


def _add_check(state: DiagramState, check: ir.Check) -> str:
    state.checks.append(check)
    return json.dumps({"status": "registered", "check": check.kind})


def handle_add_distinct_points_check(
    state: DiagramState, p: str, q: str, level: str = "must"
) -> str:
    state._tool_call_count += 1
    return _add_check(state, ir.DistinctPoints(a=p, b=q, level=level))


def handle_add_distinct_objects_check(
    state: DiagramState, a: str, b: str, level: str = "must"
) -> str:
    state._tool_call_count += 1
    return _add_check(state, ir.DistinctObjects(a=a, b=b, level=level))


def handle_add_collinear_check(
    state: DiagramState, points: list[str], level: str = "must"
) -> str:
    state._tool_call_count += 1
    return _add_check(state, ir.Collinear(points=points, level=level))


def handle_add_non_collinear_check(
    state: DiagramState, p: str, q: str, r: str, level: str = "must"
) -> str:
    state._tool_call_count += 1
    return _add_check(state, ir.NonCollinear(a=p, b=q, c=r, level=level))


def handle_add_parallel_check(
    state: DiagramState, l1: str, l2: str, level: str = "must"
) -> str:
    state._tool_call_count += 1
    return _add_check(state, ir.Parallel(l1=l1, l2=l2, level=level))


def handle_add_not_parallel_check(
    state: DiagramState, l1: str, l2: str, level: str = "must"
) -> str:
    state._tool_call_count += 1
    return _add_check(state, ir.NotParallel(l1=l1, l2=l2, level=level))


def handle_add_perpendicular_check(
    state: DiagramState, l1: str, l2: str, level: str = "must"
) -> str:
    state._tool_call_count += 1
    return _add_check(state, ir.Perpendicular(l1=l1, l2=l2, level=level))


def handle_add_contains_check(
    state: DiagramState, obj: str, point: str, level: str = "must"
) -> str:
    state._tool_call_count += 1
    return _add_check(state, ir.Contains(obj=obj, p=point, level=level))


def handle_add_not_contains_check(
    state: DiagramState, obj: str, point: str, level: str = "must"
) -> str:
    state._tool_call_count += 1
    return _add_check(state, ir.NotContains(obj=obj, p=point, level=level))


def handle_add_right_angle_check(
    state: DiagramState, a: str, vertex: str, b: str, level: str = "must"
) -> str:
    state._tool_call_count += 1
    return _add_check(state, ir.RightAngle(angle=ir.AnglePoints(a=a, o=vertex, b=b), level=level))


def handle_add_angle_equal_check(
    state: DiagramState,
    a1: str, v1: str, b1: str,
    a2: str, v2: str, b2: str,
    level: str = "must",
) -> str:
    state._tool_call_count += 1
    angle1 = ir.AnglePoints(a=a1, o=v1, b=b1)
    angle2 = ir.AnglePoints(a=a2, o=v2, b=b2)
    return _add_check(state, ir.AngleEqual(a1=angle1, a2=angle2, level=level))


def handle_add_equal_length_check(
    state: DiagramState, segments: list[str], level: str = "must"
) -> str:
    state._tool_call_count += 1
    return _add_check(state, ir.EqualLength(segs=segments, level=level))


def handle_add_ratio_equal_check(
    state: DiagramState,
    s1: str, s2: str, s3: str, s4: str,
    level: str = "must",
) -> str:
    state._tool_call_count += 1
    return _add_check(state, ir.RatioEqual(s1=s1, s2=s2, s3=s3, s4=s4, level=level))


def handle_add_similar_triangles_check(
    state: DiagramState, tri1: str, tri2: str, level: str = "must"
) -> str:
    state._tool_call_count += 1
    return _add_check(state, ir.SimilarTriangles(t1=tri1, t2=tri2, level=level))


def handle_add_tangent_check(
    state: DiagramState, line: str, circle: str, level: str = "must"
) -> str:
    state._tool_call_count += 1
    return _add_check(state, ir.Tangent(line=line, circle=circle, level=level))


def handle_add_same_side_check(
    state: DiagramState, line_a: str, line_b: str, p: str, q: str, level: str = "must"
) -> str:
    state._tool_call_count += 1
    return _add_check(state, ir.SameSide(line_a=line_a, line_b=line_b, p=p, q=q, level=level))


def handle_add_opposite_side_check(
    state: DiagramState, line_a: str, line_b: str, p: str, q: str, level: str = "must"
) -> str:
    state._tool_call_count += 1
    return _add_check(state, ir.OppositeSide(line_a=line_a, line_b=line_b, p=p, q=q, level=level))


def handle_finalize_checks(state: DiagramState) -> str:
    """Run all accumulated checks. Returns results JSON.

    Sets state._checks_finalized = True only if no must-level failures.
    prefer-level failures are reported but do not block advancement.
    Also stores results in state._last_check_results for use by repair loop.
    """
    state._tool_call_count += 1
    if state.sym is None:
        return json.dumps({"status": "error", "error": "Construction not finalized yet."})

    results: list[CheckResult] = run_checks(state.checks, state.sym)
    must_failures = [r for r in results if not r.passed and r.check.level == "must"]
    all_must_passed = len(must_failures) == 0

    if all_must_passed:
        state._checks_finalized = True

    result_list = [
        {
            "check": r.check.kind,
            "passed": r.passed,
            "level": r.check.level,
            "message": r.message,
        }
        for r in results
    ]
    state._last_check_results = result_list
    return json.dumps({"all_passed": all_must_passed, "results": result_list})
