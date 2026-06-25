"""
Ground-truth geometry extraction — the bridge that makes non-trivial probing
possible.

Given a model's parsed RecipeDSL construction, run it through the real pipeline
(validate -> lower -> compile) and pull out the spatial FACTS we want to probe
for, sourced from the geometry itself (not the output token strings):

  entity_relations : {id -> relation_type}   from the DEFS that introduce each
                     entity (PointMidpoint -> "midpoint", LinePerpendicularThrough
                     -> "perpendicular", ...). The probe asks: at the token where
                     the model writes this id, does the residual stream encode the
                     relation — even though the token itself is just a name?
  point_coords     : {id -> [x, y]}          exact compiled SymPy coordinates.
  relation_facts   : [(relation, [ids...])]  from the DiagramIR.checks (assertions
                     like Perpendicular(l1,l2), Tangent(line,circle)).

Robust to partial failures: returns whatever stage was reached, so a construction
that lowers but fails a check still yields relations (coords need a clean compile).

This module only needs sympy/pydantic + the project's ir/recipe code — it runs
locally with no model or GPU, and is unit-tested against real catalog examples.
"""
from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# DefStmt class name -> the geometric relation that entity embodies.
# (Structural defs — Triangle, Polygon, Segment, Ray, LineThrough, plain Point —
#  carry no relation and are intentionally omitted.)
DEF_RELATION = {
    "PointMidpoint": "midpoint",
    "PointIntersection": "intersection",
    "PointFoot": "perpendicular_foot",
    "PointBetween": "between",
    "PointOn": "on_object",
    "LinePerpendicularThrough": "perpendicular",
    "LineParallelThrough": "parallel",
    "LineAngleBisector": "angle_bisector",
    "LineTangent": "tangent",
}

# Check class name -> relation label (the asserted invariants).
CHECK_RELATION = {
    "Parallel": "parallel",
    "Perpendicular": "perpendicular",
    "RightAngle": "right_angle",
    "Tangent": "tangent",
    "AngleEqual": "angle_equal",
    "EqualLength": "equal_length",
    "Collinear": "collinear",
    "SimilarTriangles": "similar",
    "Centroid": "centroid",
}


def id_positions(completion: str, offsets, entity_id: str) -> list[int]:
    """Token positions where ``entity_id`` is written as a quoted JSON value.

    Maps every occurrence of "<id>" in the completion back to the covering
    token(s) via the saved char offsets. Quoting avoids matching the id as a
    substring of another name ("A" inside "AB"). Shared by capture (to decide
    which positions to keep) and probe (to place labels) so they stay aligned.
    """
    if offsets is None or not completion:
        return []
    needle = f'"{entity_id}"'
    spans, start = [], 0
    while True:
        j = completion.find(needle, start)
        if j == -1:
            break
        spans.append((j + 1, j + 1 + len(entity_id)))   # id chars, inside quotes
        start = j + 1
    return [pos for pos, (s, e) in enumerate(offsets)
            if any(s < ce and e > cs for (cs, ce) in spans)]


def entity_ids(gt: dict) -> set[str]:
    """All ids referenced by any ground-truth target (points, relations, angles)
    — the union of token positions a probe could ever use."""
    ids: set[str] = set()
    ids |= set((gt.get("entity_relations") or {}).keys())
    ids |= set((gt.get("point_coords") or {}).keys())
    ids |= set((gt.get("vertex_angles") or {}).keys())
    return ids


def ground_truth(construction_obj: dict | None) -> dict:
    """Extract spatial ground truth from a parsed RecipeDSL object.

    construction_obj: the dict that grade.extract_recipe_json returns (has a
    "construction" key), or None. Returns a dict with keys: ok, stage,
    entity_relations, point_coords, relation_facts.
    """
    result = {"ok": False, "stage": "parse", "entity_relations": {},
              "point_coords": {}, "relation_facts": []}
    if not isinstance(construction_obj, dict):
        return result

    import pydantic

    from recipe.dsl import RecipeDSL
    from recipe.lower import lower_to_ir, LoweringError
    from ir.to_sympy import compile_defs
    from ir.errors import IRCompileError

    try:
        dsl = RecipeDSL.model_validate(construction_obj)
    except pydantic.ValidationError:
        result["stage"] = "validate"
        return result

    try:
        diagram_ir = lower_to_ir(dsl)
    except (LoweringError, pydantic.ValidationError):
        result["stage"] = "lower"
        return result

    # relations are available from the lowered IR even if compile/checks fail
    result["entity_relations"] = _entity_relations(diagram_ir)
    result["relation_facts"] = _relation_facts(diagram_ir)
    result["stage"] = "lower"

    try:
        sym = compile_defs(diagram_ir)
    except IRCompileError:
        result["stage"] = "compile"
        return result

    result["point_coords"] = _point_coords(sym)
    result["vertex_angles"] = _vertex_angles(diagram_ir, sym)
    result["stage"] = "compiled"
    result["ok"] = True
    return result


def _entity_relations(diagram_ir) -> dict[str, str]:
    out: dict[str, str] = {}
    for d in diagram_ir.define:          # DiagramIR.define holds the DefStmt list
        rel = DEF_RELATION.get(type(d).__name__)
        oid = getattr(d, "id", None)
        if rel and oid:
            out[oid] = rel
    return out


def _relation_facts(diagram_ir) -> list[dict]:
    out: list[dict] = []
    for c in getattr(diagram_ir, "checks", []):
        rel = CHECK_RELATION.get(type(c).__name__)
        if not rel:
            continue
        ids = []
        for k, v in vars(c).items():
            if k in ("kind", "level"):
                continue
            vals = v if isinstance(v, list) else [v]
            # real object ids have no spaces/colons (filters annotation descriptions)
            ids += [x for x in vals if isinstance(x, str) and " " not in x and ":" not in x]
        out.append({"relation": rel, "ids": ids})
    return out


def _vertex_angles(diagram_ir, sym) -> dict[str, float]:
    """Interior angle (degrees) at each triangle vertex, from the compiled
    geometry. Non-trivial probe target: a vertex name doesn't encode its angle."""
    from ir.queries import query_angle

    out: dict[str, float] = {}
    for d in diagram_ir.define:
        if type(d).__name__ != "Triangle":
            continue
        try:
            a, b, c = d.a, d.b, d.c
        except AttributeError:
            continue
        for v, p, q in ((a, b, c), (b, a, c), (c, a, b)):   # angle at v
            try:
                out[v] = query_angle(sym, p, v, q)["angle_degrees"]
            except Exception:  # noqa: BLE001
                pass
    return out


def _point_coords(sym) -> dict[str, list[float]]:
    from ir.queries import list_objects, query_coordinate

    out: dict[str, list[float]] = {}
    for oid in list_objects(sym):
        try:
            c = query_coordinate(sym, oid)
        except Exception:  # noqa: BLE001 — non-point object
            continue
        x, y = c.get("x"), c.get("y")
        if x is not None and y is not None:
            out[oid] = [float(x), float(y)]
    return out
