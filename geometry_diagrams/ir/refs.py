"""
Utilities for extracting ID references from IR definition statements.

Used by compile_defs (to_sympy.py) for topological sorting, and by
progressive_tools (state.py) for dependency tracking.
"""
from __future__ import annotations

import ast

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
                   "reflex", "vertex_names", "tangency"}
# Fields compiled via to_sympy's ev(); a string value is an expression whose
# bare names (e.g. the "c" in "radius(c)") may reference other defs.
_EXPR_FIELDS = {"x", "y", "angle", "ratio", "radius", "hradius", "vradius",
                "major_axis", "semi_major", "eccentricity"}


def _expr_names(raw: str) -> set[str]:
    """Identifier names an expression string reads, excluding called function
    names. Unparseable strings (e.g. a "2:1" ratio) yield no names; the
    evaluator reports those errors itself."""
    try:
        tree = ast.parse(raw, mode="eval")
    except SyntaxError:
        return set()
    names: set[str] = set()

    def walk(node: ast.AST) -> None:
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Call):
            for arg in node.args:
                walk(arg)
        else:
            for child in ast.iter_child_nodes(node):
                walk(child)

    walk(tree.body)
    return names


def def_references(stmt: ir.DefStmt) -> set[str]:
    """Return the set of names this DefStmt directly references: reference
    fields plus bare names inside string expression fields. Expression names
    also include params and constants (pi, E); callers filter to def ids."""
    refs: set[str] = set()
    data = stmt.model_dump()
    for key, value in data.items():
        if key in _EXPR_FIELDS:
            if isinstance(value, str):
                refs |= _expr_names(value)
            continue
        if key == "how" and isinstance(value, dict):
            # PointOnIntent's spatial constraints reference other points
            # (ArcBetweenConstraint's from_point/to_point, NotNear's point,
            # SameSide's line/ref, ...). Those are genuine dependency edges:
            # the constraint is evaluated while this statement compiles, so
            # each referenced id must already be in the symbol table.
            for constraint in value.get("constraints") or ():
                if not isinstance(constraint, dict):
                    continue
                for ck, cv in constraint.items():
                    if ck == "kind":
                        continue
                    if isinstance(cv, str):
                        refs.add(cv)
                    elif isinstance(cv, list):
                        refs.update(v for v in cv if isinstance(v, str))
            continue
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
