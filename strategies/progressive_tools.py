from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from pydantic import TypeAdapter
from pydantic_ai import Agent

import sympy.geometry as spg

from ir import ir
from ir.errors import IRCompileError
from ir.ir import DiagramIR
from ir.to_sympy import SymTable, compile_defs
from strategies.base import DEFAULT_AGENT_MODEL, SubstanceStrategy

logger = logging.getLogger(__name__)

MAX_REPAIR_CYCLES = 3


@dataclass
class DiagramState:
    """Accumulated diagram state across all 4 phases."""
    canvas: ir.Canvas | None = None
    defs: list[ir.DefStmt] = field(default_factory=list)
    sym: SymTable | None = None          # populated by finalize_construction()
    checks: list[ir.Check] = field(default_factory=list)
    render_ops: list[ir.RenderOp] = field(default_factory=list)
    repair_count: int = 0
    # Internal phase completion flags
    _construction_finalized: bool = field(default=False, repr=False)
    _checks_finalized: bool = field(default=False, repr=False)
    _render_finalized: bool = field(default=False, repr=False)
    _last_check_results: list[dict] = field(default_factory=list, repr=False)


# ---------------------------------------------------------------------------
# Dependency graph utilities
# ---------------------------------------------------------------------------

# Fields that hold point/object reference IDs in DefStmt models
_REF_FIELDS = {
    "p", "q", "a", "b", "c",               # geometric endpoints/vertices
    "on", "onto", "source", "across",       # point_on, point_foot, point_reflect
    "center", "through",                    # circles
    "to_line",                              # line_parallel/perp
    "tri",                                  # point_triangle_center
    "obj1", "obj2",                         # point_intersection
    "circle", "point",                      # line_tangent
    "ref",                                  # polygon_exterior
    "vertex",                               # line_angle_bisector
}
# Fields that are never IDs
_NON_REF_FIELDS = {"kind", "id", "x", "y", "hint_xy", "ratio", "angle",
                   "radius", "sides", "level", "tol", "which", "how", "k", "opacity"}


def def_references(stmt: ir.DefStmt) -> set[str]:
    """Return the set of definition IDs that this DefStmt directly references."""
    refs: set[str] = set()
    data = stmt.model_dump()
    for key, value in data.items():
        if key in _NON_REF_FIELDS:
            continue
        if key == "points" and isinstance(value, list):
            refs.update(v for v in value if isinstance(v, str))
        elif key in _REF_FIELDS and isinstance(value, str):
            refs.add(value)
        elif key == "pick" and isinstance(value, dict):
            for pk, pv in value.items():
                if pk == "kind":
                    continue
                if isinstance(pv, str):
                    refs.add(pv)
                elif isinstance(pv, list):
                    refs.update(v for v in pv if isinstance(v, str))
    return refs


def cascade_remove(state: DiagramState, target_id: str) -> list[str]:
    """Remove target_id and all transitively dependent definitions from state.defs.

    Also clears state.sym since the symbol table is now stale.
    Returns the list of removed IDs.
    """
    # BFS: find all IDs that transitively depend on target_id
    to_remove: set[str] = {target_id}
    changed = True
    while changed:
        changed = False
        for stmt in state.defs:
            if stmt.id not in to_remove and def_references(stmt) & to_remove:
                to_remove.add(stmt.id)
                changed = True

    removed_ordered = [d.id for d in state.defs if d.id in to_remove]
    state.defs = [d for d in state.defs if d.id not in to_remove]
    state.sym = None  # symbol table is now stale
    state._construction_finalized = False
    state._checks_finalized = False
    state._render_finalized = False
    return removed_ordered


@dataclass
class ProgressiveToolsRunResult:
    """Result of a ProgressiveToolsStrategy run."""
    tikz: str
    svg: str
    input_tokens: int = 0
    output_tokens: int = 0
    repair_cycles: int = 0


# ---------------------------------------------------------------------------
# Phase 1: Canvas tool handler
# ---------------------------------------------------------------------------

def handle_init_diagram(
    state: DiagramState,
    grid: bool = False,
    xmin: float = -5,
    xmax: float = 5,
    ymin: float = -5,
    ymax: float = 5,
) -> str:
    """Tool handler for init_diagram. Sets state.canvas and returns JSON summary."""
    state.canvas = ir.Canvas(
        kind="cartesian",
        xmin=xmin, xmax=xmax,
        ymin=ymin, ymax=ymax,
        grid=grid,
    )
    return json.dumps({
        "status": "ok",
        "canvas": {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax, "grid": grid},
    })


# ---------------------------------------------------------------------------
# Phase 2: Construction tool handlers — utilities
# ---------------------------------------------------------------------------

def _check_unique_id(state: DiagramState, id: str) -> str | None:
    """Return error JSON if ID already exists, else None."""
    if any(d.id == id for d in state.defs):
        return json.dumps({"error": f"ID '{id}' is already in use. Choose a different ID."})
    return None


def _registered(id: str) -> str:
    return json.dumps({"id": id, "status": "registered"})


# ---------------------------------------------------------------------------
# Phase 2: Construction tool handlers — points
# ---------------------------------------------------------------------------

def handle_add_point_fixed(state: DiagramState, id: str, x: str, y: str) -> str:
    if err := _check_unique_id(state, id):
        return err
    state.defs.append(ir.PointFixed(id=id, x=x, y=y))
    return _registered(id)


def handle_add_point_free(
    state: DiagramState,
    id: str,
    hint_xy: list[float] | None = None,
) -> str:
    if err := _check_unique_id(state, id):
        return err
    state.defs.append(ir.PointFree(id=id, hint_xy=hint_xy))
    return _registered(id)


def handle_add_point_on(state: DiagramState, id: str, on: str, how: dict) -> str:
    if err := _check_unique_id(state, id):
        return err
    try:
        how_obj = TypeAdapter(ir.PointOnHow).validate_python(how)
    except Exception as e:
        return json.dumps({"error": f"Invalid 'how' argument: {e}"})
    state.defs.append(ir.PointOn(id=id, on=on, how=how_obj))
    return _registered(id)


def handle_add_point_midpoint(state: DiagramState, id: str, p: str, q: str) -> str:
    if err := _check_unique_id(state, id):
        return err
    state.defs.append(ir.PointMidpoint(id=id, p=p, q=q))
    return _registered(id)


def handle_add_point_between(
    state: DiagramState, id: str, a: str, b: str, ratio: str | float
) -> str:
    if err := _check_unique_id(state, id):
        return err
    state.defs.append(ir.PointBetween(id=id, a=a, b=b, ratio=ratio))
    return _registered(id)


def handle_add_point_foot(state: DiagramState, id: str, source: str, onto: str) -> str:
    if err := _check_unique_id(state, id):
        return err
    state.defs.append(ir.PointFoot(id=id, source=source, onto=onto))
    return _registered(id)


def handle_add_point_rotate(
    state: DiagramState, id: str, center: str, source: str, angle: str | float
) -> str:
    if err := _check_unique_id(state, id):
        return err
    state.defs.append(ir.PointRotate(id=id, center=center, source=source, angle=angle))
    return _registered(id)


def handle_add_point_reflect(
    state: DiagramState, id: str, source: str, across: str
) -> str:
    if err := _check_unique_id(state, id):
        return err
    state.defs.append(ir.PointReflect(id=id, source=source, across=across))
    return _registered(id)


def handle_add_point_triangle_center(
    state: DiagramState,
    id: str,
    tri: str,
    which: str,
) -> str:
    if err := _check_unique_id(state, id):
        return err
    state.defs.append(ir.PointTriangleCenter(id=id, tri=tri, which=which))
    return _registered(id)


def handle_add_point_intersection(
    state: DiagramState,
    id: str,
    obj1: str,
    obj2: str,
    pick: dict | None = None,
) -> str:
    if err := _check_unique_id(state, id):
        return err
    pick_obj = None
    if pick is not None:
        try:
            pick_obj = TypeAdapter(ir.PickRule).validate_python(pick)
        except Exception as e:
            return json.dumps({"error": f"Invalid pick rule: {e}"})
    state.defs.append(ir.PointIntersection(id=id, obj1=obj1, obj2=obj2, pick=pick_obj))
    return _registered(id)


# ---------------------------------------------------------------------------
# Phase 2: Construction tool handlers — linear objects
# ---------------------------------------------------------------------------

def handle_add_segment(state: DiagramState, id: str, a: str, b: str) -> str:
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.Segment(id=id, a=a, b=b))
    return _registered(id)


def handle_add_ray(state: DiagramState, id: str, a: str, b: str) -> str:
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.Ray(id=id, a=a, b=b))
    return _registered(id)


def handle_add_line_through(state: DiagramState, id: str, a: str, b: str) -> str:
    """Note: IR fields are p/q, not a/b."""
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.LineThrough(id=id, p=a, q=b))
    return _registered(id)


def handle_add_line_parallel_through(
    state: DiagramState, id: str, through: str, parallel_to: str
) -> str:
    """parallel_to → IR field to_line."""
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.LineParallelThrough(id=id, through=through, to_line=parallel_to))
    return _registered(id)


def handle_add_line_perp_through(
    state: DiagramState, id: str, through: str, perp_to: str
) -> str:
    """perp_to → IR field to_line."""
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.LinePerpendicularThrough(id=id, through=through, to_line=perp_to))
    return _registered(id)


def handle_add_line_angle_bisector(
    state: DiagramState, id: str, a: str, vertex: str, b: str
) -> str:
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.LineAngleBisector(id=id, a=a, vertex=vertex, b=b))
    return _registered(id)


def handle_add_line_tangent(
    state: DiagramState,
    id: str,
    from_point: str,
    to_circle: str,
    pick: dict | None = None,
) -> str:
    """from_point → IR 'point'; to_circle → IR 'circle'."""
    if err := _check_unique_id(state, id): return err
    pick_obj = None
    if pick is not None:
        try:
            pick_obj = TypeAdapter(ir.PickRule).validate_python(pick)
        except Exception as e:
            return json.dumps({"error": f"Invalid pick rule: {e}"})
    state.defs.append(ir.LineTangent(id=id, point=from_point, circle=to_circle, pick=pick_obj))
    return _registered(id)


# ---------------------------------------------------------------------------
# Phase 2: Construction tool handlers — circles
# ---------------------------------------------------------------------------

def handle_add_circle_center_point(
    state: DiagramState, id: str, center: str, through: str
) -> str:
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.CircleCenterPoint(id=id, center=center, through=through))
    return _registered(id)


def handle_add_circle_center_radius(
    state: DiagramState, id: str, center: str, radius: str | float
) -> str:
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.CircleCenterRadius(id=id, center=center, radius=radius))
    return _registered(id)


def handle_add_circle_through3(
    state: DiagramState, id: str, a: str, b: str, c: str
) -> str:
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.CircleThrough3(id=id, a=a, b=b, c=c))
    return _registered(id)


# ---------------------------------------------------------------------------
# Phase 2: Construction tool handlers — composite shapes
# ---------------------------------------------------------------------------

def handle_add_triangle(state: DiagramState, id: str, a: str, b: str, c: str) -> str:
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.Triangle(id=id, a=a, b=b, c=c))
    return _registered(id)


def handle_add_polygon(state: DiagramState, id: str, vertices: list[str]) -> str:
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.Polygon(id=id, points=vertices))
    return _registered(id)


def handle_add_polygon_exterior(
    state: DiagramState,
    id: str,
    v1: str,
    v2: str,
    sides: int,
    ref_point: str,
) -> str:
    """v1→IR a, v2→IR b, ref_point→IR ref."""
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.PolygonExterior(id=id, a=v1, b=v2, sides=sides, ref=ref_point))
    return _registered(id)


# ---------------------------------------------------------------------------
# Phase 2: Edit/control handlers
# ---------------------------------------------------------------------------

def handle_remove_definition(state: DiagramState, id: str) -> str:
    """Remove a definition and all transitively dependent definitions."""
    if not any(d.id == id for d in state.defs):
        return json.dumps({"error": f"ID '{id}' not found in construction"})
    removed = cascade_remove(state, id)
    return json.dumps({"removed": removed})


# ---------------------------------------------------------------------------
# Phase 2: Finalize construction handler
# ---------------------------------------------------------------------------

def handle_finalize_construction(state: DiagramState) -> str:
    """Compile all accumulated defs via SymPy. Returns compiled object summary."""
    transient_ir = DiagramIR(canvas=state.canvas, define=state.defs)
    try:
        sym = compile_defs(transient_ir)
    except IRCompileError as e:
        return json.dumps({"status": "error", "error": str(e)})
    except Exception as e:
        return json.dumps({"status": "error", "error": f"Compilation failed: {e}"})

    state.sym = sym
    state._construction_finalized = True

    # Build human-readable summary of compiled objects
    compiled = []
    for def_stmt in state.defs:
        obj = sym.get(def_stmt.id)
        entry: dict = {"id": def_stmt.id, "kind": def_stmt.kind}
        if isinstance(obj, spg.Point):
            entry["coordinates"] = [float(obj.x), float(obj.y)]
        elif isinstance(obj, spg.Segment):
            entry["length"] = float(obj.length)
        elif isinstance(obj, spg.Circle):
            entry["center"] = [float(obj.center.x), float(obj.center.y)]
            entry["radius"] = float(obj.radius)
        elif isinstance(obj, (spg.Triangle, spg.Polygon)):
            entry["vertices"] = [[float(v.x), float(v.y)] for v in obj.vertices]
        compiled.append(entry)

    return json.dumps({"status": "ok", "compiled": compiled})


# ---------------------------------------------------------------------------
# Phase 3: Check tool filtering
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Phase 3: Check tool handlers
# ---------------------------------------------------------------------------

from ir.checks import run_checks, CheckResult


def _add_check(state: DiagramState, check: ir.Check) -> str:
    state.checks.append(check)
    return json.dumps({"status": "registered", "check": check.kind})


def handle_add_distinct_points_check(
    state: DiagramState, p: str, q: str, level: str = "must"
) -> str:
    return _add_check(state, ir.DistinctPoints(a=p, b=q, level=level))


def handle_add_distinct_objects_check(
    state: DiagramState, a: str, b: str, level: str = "must"
) -> str:
    return _add_check(state, ir.DistinctObjects(a=a, b=b, level=level))


def handle_add_collinear_check(
    state: DiagramState, points: list[str], level: str = "must"
) -> str:
    return _add_check(state, ir.Collinear(points=points, level=level))


def handle_add_non_collinear_check(
    state: DiagramState, p: str, q: str, r: str, level: str = "must"
) -> str:
    return _add_check(state, ir.NonCollinear(a=p, b=q, c=r, level=level))


def handle_add_parallel_check(
    state: DiagramState, l1: str, l2: str, level: str = "must"
) -> str:
    return _add_check(state, ir.Parallel(l1=l1, l2=l2, level=level))


def handle_add_not_parallel_check(
    state: DiagramState, l1: str, l2: str, level: str = "must"
) -> str:
    return _add_check(state, ir.NotParallel(l1=l1, l2=l2, level=level))


def handle_add_perpendicular_check(
    state: DiagramState, l1: str, l2: str, level: str = "must"
) -> str:
    return _add_check(state, ir.Perpendicular(l1=l1, l2=l2, level=level))


def handle_add_contains_check(
    state: DiagramState, obj: str, point: str, level: str = "must"
) -> str:
    return _add_check(state, ir.Contains(obj=obj, p=point, level=level))


def handle_add_not_contains_check(
    state: DiagramState, obj: str, point: str, level: str = "must"
) -> str:
    return _add_check(state, ir.NotContains(obj=obj, p=point, level=level))


def handle_add_right_angle_check(
    state: DiagramState, a: str, vertex: str, b: str, level: str = "must"
) -> str:
    return _add_check(state, ir.RightAngle(angle=ir.AnglePoints(a=a, o=vertex, b=b), level=level))


def handle_add_angle_equal_check(
    state: DiagramState,
    a1: str, v1: str, b1: str,
    a2: str, v2: str, b2: str,
    level: str = "must",
) -> str:
    angle1 = ir.AnglePoints(a=a1, o=v1, b=b1)
    angle2 = ir.AnglePoints(a=a2, o=v2, b=b2)
    return _add_check(state, ir.AngleEqual(a1=angle1, a2=angle2, level=level))


def handle_add_equal_length_check(
    state: DiagramState, segments: list[str], level: str = "must"
) -> str:
    return _add_check(state, ir.EqualLength(segs=segments, level=level))


def handle_add_ratio_equal_check(
    state: DiagramState,
    s1: str, s2: str, s3: str, s4: str,
    level: str = "must",
) -> str:
    return _add_check(state, ir.RatioEqual(s1=s1, s2=s2, s3=s3, s4=s4, level=level))


def handle_add_similar_triangles_check(
    state: DiagramState, tri1: str, tri2: str, level: str = "must"
) -> str:
    return _add_check(state, ir.SimilarTriangles(t1=tri1, t2=tri2, level=level))


def handle_add_tangent_check(
    state: DiagramState, line: str, circle: str, level: str = "must"
) -> str:
    return _add_check(state, ir.Tangent(line=line, circle=circle, level=level))


def handle_add_same_side_check(
    state: DiagramState, line_a: str, line_b: str, p: str, q: str, level: str = "must"
) -> str:
    return _add_check(state, ir.SameSide(line_a=line_a, line_b=line_b, p=p, q=q, level=level))


def handle_add_opposite_side_check(
    state: DiagramState, line_a: str, line_b: str, p: str, q: str, level: str = "must"
) -> str:
    return _add_check(state, ir.OppositeSide(line_a=line_a, line_b=line_b, p=p, q=q, level=level))


def handle_finalize_checks(state: DiagramState) -> str:
    """Run all accumulated checks. Returns results JSON.

    Sets state._checks_finalized = True only if no must-level failures.
    prefer-level failures are reported but do not block advancement.
    Also stores results in state._last_check_results for use by repair loop.
    """
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
