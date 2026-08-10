"""Edit-locality diagnostic for pydsl multi-turn editing.

Compares two compiled turns of the same conversation (matched by script
variable name) and reports which named entities were downstream of the
edit vs. which moved unexpectedly. This is a DIAGNOSTIC ONLY — it never
gates whether an edit turn succeeds (see design doc, Component 4, and
this plan's Global Constraints). Under `full_rewrite` mode it is a soft,
trend-level signal; under `patch` mode it is a stronger per-turn signal,
since textual locality is true by construction there. That mode-aware
interpretation is the caller's responsibility — this module just computes
the raw comparison.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import sympy.geometry as spg

from . import ir
from .refs import compute_dependents, downstream_of
from .render_util import centroid_of_obj, sympy_to_float


def _position_of(obj: Any) -> tuple[float, float]:
    """Representative (x, y) for a compiled sympy object, for the purpose
    of a locality position-delta comparison. Mirrors the point/non-point
    split `build_entity_manifest` already uses (render_util.py) — plain
    `spg.Point`s have no `.vertices`, so `centroid_of_obj` (which is built
    for drawable shapes: Polygon/Circle/Ellipse/Arc/Sector) raises
    `AttributeError` on them; that would otherwise be swallowed by this
    module's broad except-and-skip and silently exempt every plain point
    (the majority of named entities) from the violation check."""
    if isinstance(obj, spg.Point):
        return (sympy_to_float(obj.x), sympy_to_float(obj.y))
    return centroid_of_obj(obj)


@dataclass
class LocalityDiagnostic:
    matched_names: set = field(default_factory=set)
    unmatched_old_names: set = field(default_factory=set)
    unmatched_new_names: set = field(default_factory=set)
    downstream_names: set = field(default_factory=set)
    violations: list = field(default_factory=list)


def check_edit_locality(
    old_manifest: dict,
    old_ir: "ir.DiagramIR",
    old_sym: dict,
    new_manifest: dict,
    new_ir: "ir.DiagramIR",
    new_sym: dict,
    *,
    epsilon: float = 1e-6,
) -> LocalityDiagnostic:
    old_by_name = {e["name"]: e for e in old_manifest["named"]}
    new_by_name = {e["name"]: e for e in new_manifest["named"]}

    old_names = set(old_by_name)
    new_names = set(new_by_name)
    matched_names = old_names & new_names
    unmatched_old_names = old_names - new_names
    unmatched_new_names = new_names - old_names

    old_stmts_by_id = {stmt.id: stmt for stmt in old_ir.define}
    new_stmts_by_id = {stmt.id: stmt for stmt in new_ir.define}

    changed_new_ids: set = set()
    for name in matched_names:
        old_id = old_by_name[name]["id"]
        new_id = new_by_name[name]["id"]
        old_stmt = old_stmts_by_id.get(old_id)
        new_stmt = new_stmts_by_id.get(new_id)
        if old_stmt is None or new_stmt is None:
            continue
        old_data = old_stmt.model_dump()
        new_data = new_stmt.model_dump()
        old_data.pop("id", None)
        new_data.pop("id", None)
        if old_data != new_data:
            changed_new_ids.add(new_id)

    dependents = compute_dependents(new_ir)
    # Only seed downstream propagation from changed entities that actually
    # have dependents in the new graph. A changed entity with no dependents
    # is indistinguishable from an unrelated/unexpected literal edit (e.g. a
    # free point whose coordinates drifted) — the whole point of this
    # diagnostic is to catch that case, so such entities must still be
    # checked positionally below rather than being treated as trivially
    # "downstream of itself." An entity that legitimately feeds other
    # entities (has dependents) is still included, so its own position is
    # correctly excluded from the check, same as its dependents.
    seed_ids = {cid for cid in changed_new_ids if dependents.get(cid)}
    downstream_ids = downstream_of(dependents, seed_ids)
    new_id_to_name = {e["id"]: e["name"] for e in new_manifest["named"]}
    downstream_names = {
        new_id_to_name[nid] for nid in downstream_ids if nid in new_id_to_name
    }

    violations = []
    for name in matched_names:
        if name in downstream_names:
            continue
        old_id = old_by_name[name]["id"]
        new_id = new_by_name[name]["id"]
        old_obj = old_sym.get(old_id)
        new_obj = new_sym.get(new_id)
        if old_obj is None or new_obj is None:
            continue
        try:
            old_pos = _position_of(old_obj)
            new_pos = _position_of(new_obj)
        except Exception:
            continue
        delta = ((old_pos[0] - new_pos[0]) ** 2 + (old_pos[1] - new_pos[1]) ** 2) ** 0.5
        if delta > epsilon:
            violations.append({
                "name": name,
                "old_position": list(old_pos),
                "new_position": list(new_pos),
            })

    return LocalityDiagnostic(
        matched_names=matched_names,
        unmatched_old_names=unmatched_old_names,
        unmatched_new_names=unmatched_new_names,
        downstream_names=downstream_names,
        violations=violations,
    )
