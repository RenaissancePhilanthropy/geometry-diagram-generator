from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from pydantic import TypeAdapter
from pydantic_ai import Agent

from ir import ir
from ir.to_sympy import SymTable
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
