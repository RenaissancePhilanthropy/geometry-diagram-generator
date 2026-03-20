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
    return removed_ordered


@dataclass
class ProgressiveToolsRunResult:
    """Result of a ProgressiveToolsStrategy run."""
    tikz: str
    svg: str
    input_tokens: int = 0
    output_tokens: int = 0
    repair_cycles: int = 0
