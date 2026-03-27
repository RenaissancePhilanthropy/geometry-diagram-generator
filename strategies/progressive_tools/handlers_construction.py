"""Phase 1 (canvas) and Phase 2 (construction) tool handlers."""
from __future__ import annotations

import json

import sympy.geometry as spg
from pydantic import TypeAdapter

from ir import ir
from ir.errors import IRCompileError
from ir.ir import DiagramIR
from ir.to_sympy import compile_defs
from .state import DiagramState, cascade_remove


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
