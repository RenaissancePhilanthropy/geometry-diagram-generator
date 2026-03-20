from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from pydantic import TypeAdapter
from pydantic_ai import Agent

import sympy.geometry as spg

from ir import ir
from ir.checks import run_checks, CheckResult
from ir.errors import IRCompileError
from ir.ir import DiagramIR
from ir.to_sympy import SymTable, compile_defs
from ir.to_tikz import ir_to_tikz
from strategies.base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from util.tikz_renderer import render_tikz

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
    _tikz: str = field(default="", repr=False)
    _svg: str = field(default="", repr=False)
    _tool_call_count: int = field(default=0, repr=False)


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
    tool_calls: int = 0


# ---------------------------------------------------------------------------
# Phase 1: Canvas tool handler
# ---------------------------------------------------------------------------

def handle_init_diagram(
    state: DiagramState,
    grid: bool = False,
    axes: bool = False,
    xmin: float = -5,
    xmax: float = 5,
    ymin: float = -5,
    ymax: float = 5,
) -> str:
    """Tool handler for init_diagram. Sets state.canvas and returns JSON summary."""
    state._tool_call_count += 1
    state.canvas = ir.Canvas(
        kind="cartesian",
        xmin=xmin, xmax=xmax,
        ymin=ymin, ymax=ymax,
        grid=grid,
        axes=axes,
    )
    return json.dumps({
        "status": "ok",
        "canvas": {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax, "grid": grid, "axes": axes},
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
    state._tool_call_count += 1
    if err := _check_unique_id(state, id):
        return err
    state.defs.append(ir.PointFixed(id=id, x=x, y=y))
    return _registered(id)


def handle_add_point_free(
    state: DiagramState,
    id: str,
    hint_xy: list[float] | None = None,
) -> str:
    state._tool_call_count += 1
    if err := _check_unique_id(state, id):
        return err
    state.defs.append(ir.PointFree(id=id, hint_xy=hint_xy))
    return _registered(id)


def handle_add_point_on(state: DiagramState, id: str, on: str, how: dict) -> str:
    state._tool_call_count += 1
    if err := _check_unique_id(state, id):
        return err
    try:
        how_obj = TypeAdapter(ir.PointOnHow).validate_python(how)
    except Exception as e:
        return json.dumps({"error": f"Invalid 'how' argument: {e}"})
    state.defs.append(ir.PointOn(id=id, on=on, how=how_obj))
    return _registered(id)


def handle_add_point_midpoint(state: DiagramState, id: str, p: str, q: str) -> str:
    state._tool_call_count += 1
    if err := _check_unique_id(state, id):
        return err
    state.defs.append(ir.PointMidpoint(id=id, p=p, q=q))
    return _registered(id)


def handle_add_point_between(
    state: DiagramState, id: str, a: str, b: str, ratio: str | float
) -> str:
    state._tool_call_count += 1
    if err := _check_unique_id(state, id):
        return err
    state.defs.append(ir.PointBetween(id=id, a=a, b=b, ratio=ratio))
    return _registered(id)


def handle_add_point_foot(state: DiagramState, id: str, source: str, onto: str) -> str:
    state._tool_call_count += 1
    if err := _check_unique_id(state, id):
        return err
    state.defs.append(ir.PointFoot(id=id, source=source, onto=onto))
    return _registered(id)


def handle_add_point_rotate(
    state: DiagramState, id: str, center: str, source: str, angle: str | float
) -> str:
    state._tool_call_count += 1
    if err := _check_unique_id(state, id):
        return err
    state.defs.append(ir.PointRotate(id=id, center=center, source=source, angle=angle))
    return _registered(id)


def handle_add_point_reflect(
    state: DiagramState, id: str, source: str, across: str
) -> str:
    state._tool_call_count += 1
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
    state._tool_call_count += 1
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
    state._tool_call_count += 1
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
    state._tool_call_count += 1
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.Segment(id=id, a=a, b=b))
    return _registered(id)


def handle_add_ray(state: DiagramState, id: str, a: str, b: str) -> str:
    state._tool_call_count += 1
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.Ray(id=id, a=a, b=b))
    return _registered(id)


def handle_add_line_through(state: DiagramState, id: str, a: str, b: str) -> str:
    """Note: IR fields are p/q, not a/b."""
    state._tool_call_count += 1
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.LineThrough(id=id, p=a, q=b))
    return _registered(id)


def handle_add_line_parallel_through(
    state: DiagramState, id: str, through: str, parallel_to: str
) -> str:
    """parallel_to → IR field to_line."""
    state._tool_call_count += 1
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.LineParallelThrough(id=id, through=through, to_line=parallel_to))
    return _registered(id)


def handle_add_line_perp_through(
    state: DiagramState, id: str, through: str, perp_to: str
) -> str:
    """perp_to → IR field to_line."""
    state._tool_call_count += 1
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.LinePerpendicularThrough(id=id, through=through, to_line=perp_to))
    return _registered(id)


def handle_add_line_angle_bisector(
    state: DiagramState, id: str, a: str, vertex: str, b: str
) -> str:
    state._tool_call_count += 1
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
    state._tool_call_count += 1
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
    state._tool_call_count += 1
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.CircleCenterPoint(id=id, center=center, through=through))
    return _registered(id)


def handle_add_circle_center_radius(
    state: DiagramState, id: str, center: str, radius: str | float
) -> str:
    state._tool_call_count += 1
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.CircleCenterRadius(id=id, center=center, radius=radius))
    return _registered(id)


def handle_add_circle_through3(
    state: DiagramState, id: str, a: str, b: str, c: str
) -> str:
    state._tool_call_count += 1
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.CircleThrough3(id=id, a=a, b=b, c=c))
    return _registered(id)


# ---------------------------------------------------------------------------
# Phase 2: Construction tool handlers — composite shapes
# ---------------------------------------------------------------------------

def handle_add_triangle(state: DiagramState, id: str, a: str, b: str, c: str) -> str:
    state._tool_call_count += 1
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.Triangle(id=id, a=a, b=b, c=c))
    return _registered(id)


def handle_add_polygon(state: DiagramState, id: str, vertices: list[str]) -> str:
    state._tool_call_count += 1
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
    state._tool_call_count += 1
    if err := _check_unique_id(state, id): return err
    state.defs.append(ir.PolygonExterior(id=id, a=v1, b=v2, sides=sides, ref=ref_point))
    return _registered(id)


# ---------------------------------------------------------------------------
# Phase 2: Edit/control handlers
# ---------------------------------------------------------------------------

def handle_remove_definition(state: DiagramState, id: str) -> str:
    """Remove a definition and all transitively dependent definitions."""
    state._tool_call_count += 1
    if not any(d.id == id for d in state.defs):
        return json.dumps({"error": f"ID '{id}' not found in construction"})
    removed = cascade_remove(state, id)
    return json.dumps({"removed": removed})


# ---------------------------------------------------------------------------
# Phase 2: Finalize construction handler
# ---------------------------------------------------------------------------

def handle_finalize_construction(state: DiagramState) -> str:
    """Compile all accumulated defs via SymPy. Returns compiled object summary."""
    state._tool_call_count += 1
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


# ---------------------------------------------------------------------------
# Phase 4: Presentation tool filtering
# ---------------------------------------------------------------------------

def presentation_tool_names_for_state(state: DiagramState) -> list[str]:
    """Return presentation tool names applicable to the current construction."""
    kinds = [d.kind for d in state.defs]
    point_count = sum(1 for k in kinds if k in _POINT_KINDS)
    segment_count = sum(1 for k in kinds if k == "segment")
    has_closed = any(k in _CLOSED_SHAPE_KINDS for k in kinds)

    tools = ["draw", "draw_points", "finalize_render"]

    if has_closed:
        tools.append("fill")
    if segment_count >= 1:
        tools += ["mark_segments", "label_segment"]
    if point_count >= 3:
        tools += ["mark_angles", "mark_right_angles", "label_angle"]
    if point_count >= 1:
        tools.append("label_point")

    return tools


# ---------------------------------------------------------------------------
# Phase 4: Presentation tool handlers
# ---------------------------------------------------------------------------

def _render_op_registered(kind: str) -> str:
    return json.dumps({"status": "registered", "op": kind})


def handle_draw(state: DiagramState, obj_id: str) -> str:
    state._tool_call_count += 1
    state.render_ops.append(ir.Draw(obj=obj_id))
    return _render_op_registered("draw")


def handle_draw_points(state: DiagramState, ids: list[str]) -> str:
    state._tool_call_count += 1
    state.render_ops.append(ir.DrawPoints(points=ids))
    return _render_op_registered("draw_points")


def handle_fill(
    state: DiagramState, obj_id: str, opacity: float = 1.0
) -> str:
    state._tool_call_count += 1
    state.render_ops.append(ir.Fill(obj=obj_id, opacity=opacity))
    return _render_op_registered("fill")


def handle_mark_angles(
    state: DiagramState,
    a: str,
    vertex: str,
    b: str,
    which: str = "interior",
    group: str | None = None,
) -> str:
    state._tool_call_count += 1
    angle = ir.AnglePoints(a=a, o=vertex, b=b)
    state.render_ops.append(ir.MarkAngles(angles=[angle], which=which, group=group))
    return _render_op_registered("mark_angles")


def handle_mark_right_angles(
    state: DiagramState, a: str, vertex: str, b: str
) -> str:
    state._tool_call_count += 1
    angle = ir.AnglePoints(a=a, o=vertex, b=b)
    state.render_ops.append(ir.MarkRightAngles(angles=[angle]))
    return _render_op_registered("mark_right_angles")


def handle_mark_segments(
    state: DiagramState,
    seg_ids: list[str],
    group: str | None = None,
) -> str:
    state._tool_call_count += 1
    state.render_ops.append(ir.MarkSegments(segs=seg_ids, group=group))
    return _render_op_registered("mark_segments")


def handle_label_point(
    state: DiagramState,
    id: str,
    text: str | None = None,
    position: str = "auto",
) -> str:
    state._tool_call_count += 1
    state.render_ops.append(ir.LabelPoint(p=id, text=text or id, pos=position))
    return _render_op_registered("label_point")


def handle_label_angle(
    state: DiagramState,
    a: str, vertex: str, b: str,
    text: str,
    position: float = 0.5,
) -> str:
    state._tool_call_count += 1
    angle = ir.AnglePoints(a=a, o=vertex, b=b)
    state.render_ops.append(ir.LabelAngle(angle=angle, text=text))
    return _render_op_registered("label_angle")


def handle_label_segment(
    state: DiagramState,
    seg_id: str,
    text: str,
    pos: float = 0.5,
) -> str:
    state._tool_call_count += 1
    state.render_ops.append(ir.LabelSegment(seg=seg_id, text=text, pos=pos))
    return _render_op_registered("label_segment")



# ---------------------------------------------------------------------------
# Agent builders
# ---------------------------------------------------------------------------

def _build_canvas_agent(state: DiagramState, model: str) -> Agent:
    from strategies.instructions import PROGRESSIVE_TOOLS_PHASE1_INSTRUCTIONS
    agent = Agent(model, instructions=PROGRESSIVE_TOOLS_PHASE1_INSTRUCTIONS)

    @agent.tool_plain
    def init_diagram(
        grid: bool = False,
        axes: bool = False,
        xmin: float = -5, xmax: float = 5,
        ymin: float = -5, ymax: float = 5,
    ) -> str:
        """Initialize the diagram canvas. Call this once to set up the coordinate space. Use axes=True to draw coordinate axis lines."""
        return handle_init_diagram(state, grid=grid, axes=axes, xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax)

    return agent


def _build_construction_agent(
    state: DiagramState, model: str, repair_context: str = ""
) -> Agent:
    from strategies.instructions import (
        PROGRESSIVE_TOOLS_PHASE2_INSTRUCTIONS,
        PROGRESSIVE_TOOLS_PHASE2_REPAIR_PREFIX,
    )
    instructions = PROGRESSIVE_TOOLS_PHASE2_INSTRUCTIONS
    if repair_context:
        instructions = PROGRESSIVE_TOOLS_PHASE2_REPAIR_PREFIX + "\n\n" + instructions

    agent = Agent(model, instructions=instructions)

    @agent.tool_plain
    def add_point_fixed(id: str, x: str, y: str) -> str:
        """Add a point at fixed coordinates. x and y can be numbers or expressions like 'pi/2'."""
        return handle_add_point_fixed(state, id, x, y)

    @agent.tool_plain
    def add_point_free(id: str, hint_xy: list[float] | None = None) -> str:
        """Add an unconstrained free point. Optionally provide a [x,y] placement hint."""
        return handle_add_point_free(state, id, hint_xy)

    @agent.tool_plain
    def add_point_on(id: str, on: str, how: dict) -> str:
        """Add a point constrained to lie on object 'on'. how: {kind: random|param|intent}."""
        return handle_add_point_on(state, id, on, how)

    @agent.tool_plain
    def add_point_midpoint(id: str, p: str, q: str) -> str:
        """Add a point at the midpoint of p and q."""
        return handle_add_point_midpoint(state, id, p, q)

    @agent.tool_plain
    def add_point_between(id: str, a: str, b: str, ratio: str | float) -> str:
        """Add a point on segment ab at position ratio (0=a, 1=b, or 'm:n' string)."""
        return handle_add_point_between(state, id, a, b, ratio)

    @agent.tool_plain
    def add_point_foot(id: str, source: str, onto: str) -> str:
        """Add the perpendicular foot from point 'source' onto line/segment/ray 'onto'."""
        return handle_add_point_foot(state, id, source, onto)

    @agent.tool_plain
    def add_point_rotate(id: str, center: str, source: str, angle: str | float) -> str:
        """Add a point by rotating 'source' around 'center' by angle (radians or expression)."""
        return handle_add_point_rotate(state, id, center, source, angle)

    @agent.tool_plain
    def add_point_reflect(id: str, source: str, across: str) -> str:
        """Add a point by reflecting 'source' across point or line 'across'."""
        return handle_add_point_reflect(state, id, source, across)

    @agent.tool_plain
    def add_point_triangle_center(id: str, tri: str, which: str) -> str:
        """Add a named triangle center. which: circumcenter|incenter|centroid|orthocenter."""
        return handle_add_point_triangle_center(state, id, tri, which)

    @agent.tool_plain
    def add_point_intersection(
        id: str, obj1: str, obj2: str, pick: dict | None = None
    ) -> str:
        """Add the intersection of obj1 and obj2. pick: {kind: index|closest_to|on_object|same_side|inside_triangle}."""
        return handle_add_point_intersection(state, id, obj1, obj2, pick)

    @agent.tool_plain
    def add_segment(id: str, a: str, b: str) -> str:
        """Add a finite segment from point a to point b."""
        return handle_add_segment(state, id, a, b)

    @agent.tool_plain
    def add_ray(id: str, a: str, b: str) -> str:
        """Add a ray starting at a, passing through b."""
        return handle_add_ray(state, id, a, b)

    @agent.tool_plain
    def add_line_through(id: str, a: str, b: str) -> str:
        """Add an infinite line through points a and b."""
        return handle_add_line_through(state, id, a, b)

    @agent.tool_plain
    def add_line_parallel_through(id: str, through: str, parallel_to: str) -> str:
        """Add a line through 'through' parallel to object 'parallel_to'."""
        return handle_add_line_parallel_through(state, id, through, parallel_to)

    @agent.tool_plain
    def add_line_perp_through(id: str, through: str, perp_to: str) -> str:
        """Add a line through 'through' perpendicular to object 'perp_to'."""
        return handle_add_line_perp_through(state, id, through, perp_to)

    @agent.tool_plain
    def add_line_angle_bisector(id: str, a: str, vertex: str, b: str) -> str:
        """Add the angle bisector of angle a-vertex-b."""
        return handle_add_line_angle_bisector(state, id, a, vertex, b)

    @agent.tool_plain
    def add_line_tangent(
        id: str, from_point: str, to_circle: str, pick: dict | None = None
    ) -> str:
        """Add a tangent line from external point 'from_point' to circle 'to_circle'."""
        return handle_add_line_tangent(state, id, from_point, to_circle, pick)

    @agent.tool_plain
    def add_circle_center_point(id: str, center: str, through: str) -> str:
        """Add a circle with given center passing through point 'through'."""
        return handle_add_circle_center_point(state, id, center, through)

    @agent.tool_plain
    def add_circle_center_radius(id: str, center: str, radius: str | float) -> str:
        """Add a circle by center and radius (number or expression)."""
        return handle_add_circle_center_radius(state, id, center, radius)

    @agent.tool_plain
    def add_circle_through3(id: str, a: str, b: str, c: str) -> str:
        """Add the circumscribed circle through three points."""
        return handle_add_circle_through3(state, id, a, b, c)

    @agent.tool_plain
    def add_triangle(id: str, a: str, b: str, c: str) -> str:
        """Add a triangle from three points."""
        return handle_add_triangle(state, id, a, b, c)

    @agent.tool_plain
    def add_polygon(id: str, vertices: list[str]) -> str:
        """Add a polygon from an ordered list of point IDs."""
        return handle_add_polygon(state, id, vertices)

    @agent.tool_plain
    def add_polygon_exterior(
        id: str, v1: str, v2: str, sides: int, ref_point: str
    ) -> str:
        """Add a regular polygon with 'sides' sides, built on edge v1-v2, opposite ref_point."""
        return handle_add_polygon_exterior(state, id, v1, v2, sides, ref_point)

    @agent.tool_plain
    def remove_definition(id: str) -> str:
        """Remove a definition and all definitions that depend on it (cascade removal)."""
        return handle_remove_definition(state, id)

    @agent.tool_plain
    def finalize_construction() -> str:
        """Compile all definitions with SymPy. Call this when you are done adding objects."""
        return handle_finalize_construction(state)

    return agent


def _build_checks_agent(state: DiagramState, model: str) -> Agent:
    from strategies.instructions import PROGRESSIVE_TOOLS_PHASE3_INSTRUCTIONS
    agent = Agent(model, instructions=PROGRESSIVE_TOOLS_PHASE3_INSTRUCTIONS)

    available_tools = check_tool_names_for_state(state)

    if "add_distinct_points_check" in available_tools:
        @agent.tool_plain
        def add_distinct_points_check(p: str, q: str, level: str = "must") -> str:
            """Add a check that two points are distinct (not coincident)."""
            return handle_add_distinct_points_check(state, p, q, level)

    if "add_distinct_objects_check" in available_tools:
        @agent.tool_plain
        def add_distinct_objects_check(a: str, b: str, level: str = "must") -> str:
            """Add a check that two objects are not identical."""
            return handle_add_distinct_objects_check(state, a, b, level)

    if "add_collinear_check" in available_tools:
        @agent.tool_plain
        def add_collinear_check(points: list[str], level: str = "must") -> str:
            """Add a check that a list of 3+ points are collinear."""
            return handle_add_collinear_check(state, points, level)

    if "add_non_collinear_check" in available_tools:
        @agent.tool_plain
        def add_non_collinear_check(p: str, q: str, r: str, level: str = "must") -> str:
            """Add a check that three points are NOT collinear."""
            return handle_add_non_collinear_check(state, p, q, r, level)

    if "add_parallel_check" in available_tools:
        @agent.tool_plain
        def add_parallel_check(l1: str, l2: str, level: str = "must") -> str:
            """Add a check that two lines/segments are parallel."""
            return handle_add_parallel_check(state, l1, l2, level)

    if "add_not_parallel_check" in available_tools:
        @agent.tool_plain
        def add_not_parallel_check(l1: str, l2: str, level: str = "must") -> str:
            """Add a check that two lines/segments are NOT parallel."""
            return handle_add_not_parallel_check(state, l1, l2, level)

    if "add_perpendicular_check" in available_tools:
        @agent.tool_plain
        def add_perpendicular_check(l1: str, l2: str, level: str = "must") -> str:
            """Add a check that two lines/segments are perpendicular."""
            return handle_add_perpendicular_check(state, l1, l2, level)

    if "add_contains_check" in available_tools:
        @agent.tool_plain
        def add_contains_check(obj: str, point: str, level: str = "must") -> str:
            """Add a check that object 'obj' contains point 'point'."""
            return handle_add_contains_check(state, obj, point, level)

    if "add_not_contains_check" in available_tools:
        @agent.tool_plain
        def add_not_contains_check(obj: str, point: str, level: str = "must") -> str:
            """Add a check that object 'obj' does NOT contain point 'point'."""
            return handle_add_not_contains_check(state, obj, point, level)

    if "add_right_angle_check" in available_tools:
        @agent.tool_plain
        def add_right_angle_check(a: str, vertex: str, b: str, level: str = "must") -> str:
            """Add a check that the angle a-vertex-b is a right angle (90 degrees)."""
            return handle_add_right_angle_check(state, a, vertex, b, level)

    if "add_angle_equal_check" in available_tools:
        @agent.tool_plain
        def add_angle_equal_check(
            a1: str, v1: str, b1: str,
            a2: str, v2: str, b2: str,
            level: str = "must",
        ) -> str:
            """Add a check that angle a1-v1-b1 equals angle a2-v2-b2."""
            return handle_add_angle_equal_check(state, a1, v1, b1, a2, v2, b2, level)

    if "add_equal_length_check" in available_tools:
        @agent.tool_plain
        def add_equal_length_check(segments: list[str], level: str = "must") -> str:
            """Add a check that all listed segment IDs have equal length."""
            return handle_add_equal_length_check(state, segments, level)

    if "add_ratio_equal_check" in available_tools:
        @agent.tool_plain
        def add_ratio_equal_check(
            s1: str, s2: str, s3: str, s4: str, level: str = "must"
        ) -> str:
            """Add a check that |s1|/|s2| == |s3|/|s4|."""
            return handle_add_ratio_equal_check(state, s1, s2, s3, s4, level)

    if "add_similar_triangles_check" in available_tools:
        @agent.tool_plain
        def add_similar_triangles_check(tri1: str, tri2: str, level: str = "must") -> str:
            """Add a check that two triangles are similar."""
            return handle_add_similar_triangles_check(state, tri1, tri2, level)

    if "add_tangent_check" in available_tools:
        @agent.tool_plain
        def add_tangent_check(line: str, circle: str, level: str = "must") -> str:
            """Add a check that a line/segment is tangent to a circle."""
            return handle_add_tangent_check(state, line, circle, level)

    if "add_same_side_check" in available_tools:
        @agent.tool_plain
        def add_same_side_check(
            line_a: str, line_b: str, p: str, q: str, level: str = "must"
        ) -> str:
            """Add a check that p and q are on the same side of the line through line_a and line_b."""
            return handle_add_same_side_check(state, line_a, line_b, p, q, level)

    if "add_opposite_side_check" in available_tools:
        @agent.tool_plain
        def add_opposite_side_check(
            line_a: str, line_b: str, p: str, q: str, level: str = "must"
        ) -> str:
            """Add a check that p and q are on opposite sides of the line through line_a and line_b."""
            return handle_add_opposite_side_check(state, line_a, line_b, p, q, level)

    @agent.tool_plain
    def finalize_checks() -> str:
        """Run all accumulated checks. Call this when done adding checks."""
        return handle_finalize_checks(state)

    return agent


def _build_presentation_agent(state: DiagramState, model: str) -> Agent:
    from strategies.instructions import PROGRESSIVE_TOOLS_PHASE4_INSTRUCTIONS
    agent = Agent(model, instructions=PROGRESSIVE_TOOLS_PHASE4_INSTRUCTIONS)

    available_tools = presentation_tool_names_for_state(state)

    if "draw" in available_tools:
        @agent.tool_plain
        def draw(obj_id: str) -> str:
            """Draw an object (segment, line, ray, circle, polygon, triangle)."""
            return handle_draw(state, obj_id)

    if "draw_points" in available_tools:
        @agent.tool_plain
        def draw_points(ids: list[str]) -> str:
            """Draw point markers for a list of point IDs."""
            return handle_draw_points(state, ids)

    if "fill" in available_tools:
        @agent.tool_plain
        def fill(obj_id: str, opacity: float = 1.0) -> str:
            """Fill a closed shape (polygon, triangle, circle) with optional opacity (0-1)."""
            return handle_fill(state, obj_id, opacity)

    if "mark_angles" in available_tools:
        @agent.tool_plain
        def mark_angles(
            a: str, vertex: str, b: str,
            which: str = "interior",
            group: str | None = None,
        ) -> str:
            """Place an arc angle mark on angle a-vertex-b. which: interior|exterior|reflex."""
            return handle_mark_angles(state, a, vertex, b, which, group)

    if "mark_right_angles" in available_tools:
        @agent.tool_plain
        def mark_right_angles(a: str, vertex: str, b: str) -> str:
            """Place a right-angle square marker on angle a-vertex-b."""
            return handle_mark_right_angles(state, a, vertex, b)

    if "mark_segments" in available_tools:
        @agent.tool_plain
        def mark_segments(seg_ids: list[str], group: str | None = None) -> str:
            """Place tick marks on the listed segment IDs. Use group to share the same symbol."""
            return handle_mark_segments(state, seg_ids, group)

    if "label_point" in available_tools:
        @agent.tool_plain
        def label_point(id: str, text: str | None = None, position: str = "auto") -> str:
            """Label a point. position: auto|above|below|left|right|above left|above right|below left|below right."""
            return handle_label_point(state, id, text, position)

    if "label_angle" in available_tools:
        @agent.tool_plain
        def label_angle(
            a: str, vertex: str, b: str, text: str, position: float = 0.5
        ) -> str:
            """Label the angle a-vertex-b with text."""
            return handle_label_angle(state, a, vertex, b, text, position)

    if "label_segment" in available_tools:
        @agent.tool_plain
        def label_segment(seg_id: str, text: str, pos: float = 0.5) -> str:
            """Label segment seg_id with text. pos: fraction along segment (0-1)."""
            return handle_label_segment(state, seg_id, text, pos)

    @agent.tool_plain
    def finalize_render() -> str:
        """Generate TikZ and render to SVG. Call this when done adding presentation."""
        return handle_finalize_render(state)

    return agent


def _state_summary(state: DiagramState) -> str:
    """Return a brief human-readable summary of the current diagram state."""
    lines = []
    if state.canvas:
        lines.append(f"Canvas: xmin={state.canvas.xmin}, xmax={state.canvas.xmax}, "
                     f"ymin={state.canvas.ymin}, ymax={state.canvas.ymax}, grid={state.canvas.grid}, axes={state.canvas.axes}")
    if state.defs:
        lines.append(f"Defined objects ({len(state.defs)}):")
        for d in state.defs:
            if state.sym and d.id in state.sym:
                obj = state.sym[d.id]
                if isinstance(obj, spg.Point):
                    lines.append(f"  {d.id} ({d.kind}): ({float(obj.x):.3f}, {float(obj.y):.3f})")
                    continue
            lines.append(f"  {d.id} ({d.kind})")
    if state.checks:
        lines.append(f"Checks ({len(state.checks)}): " +
                     ", ".join(c.kind for c in state.checks))
    return "\n".join(lines) if lines else "(empty)"


# ---------------------------------------------------------------------------
# ProgressiveToolsStrategy
# ---------------------------------------------------------------------------

class ProgressiveToolsStrategy(SubstanceStrategy):
    """4-phase progressive tool-use strategy."""

    def build_agent(self, model: str = DEFAULT_AGENT_MODEL) -> Agent:
        """Return Phase 2 construction agent as the 'primary' agent."""
        return _build_construction_agent(DiagramState(), model)

    async def run(
        self, prompt: str, model: str = DEFAULT_AGENT_MODEL
    ) -> ProgressiveToolsRunResult:
        total_input = 0
        total_output = 0
        state = DiagramState()
        self._last_state = state  # expose for testing

        def _accumulate(response) -> None:
            nonlocal total_input, total_output
            usage = response.usage()
            total_input += usage.input_tokens or 0
            total_output += usage.output_tokens or 0

        # Phase 1: Canvas
        canvas_agent = _build_canvas_agent(state, model)
        canvas_prompt = f"Set up the canvas for this geometry diagram:\n{prompt}"
        resp = await canvas_agent.run(canvas_prompt)
        _accumulate(resp)
        if state.canvas is None:
            state.canvas = ir.Canvas(
                kind="cartesian", xmin=-5, xmax=5, ymin=-5, ymax=5
            )

        # Phase 2: Construction (with repair loop)
        repair_context = ""
        while True:
            construction_agent = _build_construction_agent(state, model, repair_context)
            construction_prompt = (
                f"{repair_context}\n\n" if repair_context else ""
            ) + (
                f"Build the geometry for this diagram.\n\n"
                f"Current state:\n{_state_summary(state)}\n\n"
                f"Request: {prompt}\n\n"
                f"When done adding all objects, call finalize_construction()."
            )
            resp = await construction_agent.run(construction_prompt)
            _accumulate(resp)

            if not state._construction_finalized:
                raise RuntimeError(
                    "Construction agent did not call finalize_construction(). Aborting."
                )

            # Phase 3: Checks
            state.checks = []  # clear from any previous repair cycle
            checks_agent = _build_checks_agent(state, model)
            checks_prompt = (
                f"Add geometric checks for the diagram you just constructed.\n\n"
                f"Current state:\n{_state_summary(state)}\n\n"
                f"Request: {prompt}\n\n"
                f"When done adding checks, call finalize_checks()."
            )
            resp = await checks_agent.run(checks_prompt)
            _accumulate(resp)

            if state._checks_finalized:
                break  # all must-checks passed, advance to phase 4

            # must-check failed → repair
            state.repair_count += 1
            if state.repair_count > MAX_REPAIR_CYCLES:
                raise RuntimeError(
                    f"ProgressiveToolsStrategy failed: check failures after "
                    f"{MAX_REPAIR_CYCLES} repair cycles."
                )
            failed_msgs = [
                r["message"]
                for r in (state._last_check_results or [])
                if not r["passed"] and r["level"] == "must"
            ]
            repair_context = (
                "The previous construction failed the following checks:\n"
                + "\n".join(f"  - {m}" for m in failed_msgs)
                + "\n\nThe existing definitions are still loaded. "
                + "Use remove_definition() to remove incorrect objects, then re-add corrected ones. "
                + "Do NOT rebuild everything from scratch — only fix what's broken."
            )
            # Reset for repair
            state._construction_finalized = False
            state._checks_finalized = False
            state.sym = None
            # NOTE: state.defs is preserved — agent uses remove_definition() to fix specific objects
            state.render_ops = []

        # Phase 4: Presentation
        presentation_agent = _build_presentation_agent(state, model)
        presentation_prompt = (
            f"Add drawing and labeling commands for the completed diagram.\n\n"
            f"Current state:\n{_state_summary(state)}\n\n"
            f"Request: {prompt}\n\n"
            f"When done, call finalize_render() to generate the SVG."
        )
        resp = await presentation_agent.run(presentation_prompt)
        _accumulate(resp)

        if not state._render_finalized:
            # Agent forgot to call finalize_render() — attempt auto-finalize
            auto_result = handle_finalize_render(state)
            data = json.loads(auto_result)
            if data.get("status") == "error":
                raise RuntimeError(f"Auto-finalize_render failed: {data['error']}")

        return ProgressiveToolsRunResult(
            tikz=state._tikz,
            svg=state._svg,
            input_tokens=total_input,
            output_tokens=total_output,
            repair_cycles=state.repair_count,
            tool_calls=state._tool_call_count,
        )


# ---------------------------------------------------------------------------
# Phase 4: finalize_render (kept after class to avoid forward-reference issues)
# ---------------------------------------------------------------------------

def handle_finalize_render(state: DiagramState) -> str:
    """Assemble DiagramIR, generate TikZ, render to SVG."""
    state._tool_call_count += 1
    if state.sym is None:
        return json.dumps({"status": "error", "error": "Construction not finalized. Call finalize_construction() first."})
    diagram = DiagramIR(
        canvas=state.canvas,
        define=state.defs,
        checks=state.checks,
        render=state.render_ops,
    )
    try:
        tikz = ir_to_tikz(diagram, state.sym)
    except Exception as e:
        return json.dumps({"status": "error", "error": f"TikZ generation failed: {e}"})
    try:
        svg = render_tikz(tikz)
    except RuntimeError as e:
        return json.dumps({"status": "error", "error": f"Render failed: {e}"})

    state._render_finalized = True
    state._tikz = tikz
    state._svg = svg
    return json.dumps({"status": "ok", "tikz_length": len(tikz), "svg_length": len(svg)})
