"""
Utilities for extracting ID references from IR definition statements.

Used by compile_defs (to_sympy.py) for topological sorting, and by
progressive_tools (state.py) for dependency tracking.
"""
from __future__ import annotations

from . import ir

# Fields that hold point/object reference IDs in DefStmt models
_REF_FIELDS = {
    "p", "q", "a", "b", "c",               # geometric endpoints/vertices
    "on", "onto", "source", "across",       # point_on, point_foot, point_reflect
    "center", "through",                    # circles
    "start", "end",                         # arc_center_start_end
    "to_line",                              # line_parallel/perp
    "tri",                                  # point_triangle_center
    "obj1", "obj2",                         # point_intersection
    "circle", "point",                      # line_tangent
    "ref",                                  # polygon_exterior
    "vertex",                               # line_angle_bisector
    "corner1", "corner2",                   # ellipse_bbox
    "focus1", "focus2",                     # ellipse_foci
}
# Fields that are never IDs
_NON_REF_FIELDS = {"kind", "id", "x", "y", "hint_xy", "ratio", "angle",
                   "radius", "sides", "level", "tol", "which", "how", "k", "opacity",
                   "hradius", "vradius", "major_axis", "semi_major", "eccentricity", "orientation",
                   "reflex", "vertex_names"}


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


def compute_dependents(diagram: "ir.DiagramIR") -> dict[str, set[str]]:
    """Invert def_references(): id -> the set of ids that directly reference
    it. Same dependency edges compile_defs (to_sympy.py) uses for
    topological sorting, just inverted — used by the edit-locality
    diagnostic to compute which entities are downstream of an edit."""
    dependents: dict[str, set[str]] = {stmt.id: set() for stmt in diagram.define}
    for stmt in diagram.define:
        for ref_id in def_references(stmt):
            if ref_id in dependents:
                dependents[ref_id].add(stmt.id)
    return dependents


def downstream_of(dependents: dict[str, set[str]], changed_ids: set[str]) -> set[str]:
    """Transitive closure of `dependents` starting from `changed_ids`,
    inclusive of `changed_ids` themselves."""
    seen: set[str] = set()
    frontier = set(changed_ids)
    while frontier:
        seen.update(frontier)
        next_frontier: set[str] = set()
        for cid in frontier:
            next_frontier.update(dependents.get(cid, set()) - seen)
        frontier = next_frontier
    return seen
