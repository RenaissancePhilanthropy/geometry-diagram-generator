# ir/queries.py
"""Geometric query functions over a compiled SymTable.

Each function takes a SymTable (dict[str, Any] mapping IDs to SymPy geometry
objects) and returns a dict with the computed result. Raises KeyError for
unknown IDs and TypeError for type mismatches.
"""
from __future__ import annotations

import math
from typing import Any

import sympy.geometry as spg

from .checks import _angle_at
from .derived import REGISTRY as DERIVED_REGISTRY
from .to_sympy import SymTable


def _get(sym: SymTable, obj_id: str) -> Any:
    if obj_id not in sym:
        raise KeyError(f"Unknown object ID: {obj_id!r}")
    return sym[obj_id]


def _require_point(sym: SymTable, obj_id: str) -> spg.Point:
    obj = _get(sym, obj_id)
    if not isinstance(obj, spg.Point):
        raise TypeError(f"{obj_id!r} is not a Point (got {type(obj).__name__})")
    return obj


def query_coordinate(sym: SymTable, point_id: str) -> dict:
    pt = _require_point(sym, point_id)
    return {"x": float(pt.x), "y": float(pt.y)}


def query_distance(sym: SymTable, id_a: str, id_b: str) -> dict:
    a = _require_point(sym, id_a)
    b = _require_point(sym, id_b)
    return {"distance": float(a.distance(b).evalf())}


def query_angle(sym: SymTable, a: str, vertex: str, b: str) -> dict:
    pa = _require_point(sym, a)
    pv = _require_point(sym, vertex)
    pb = _require_point(sym, b)
    radians = _angle_at(pa, pv, pb)
    return {"angle_degrees": math.degrees(radians)}


def query_length(sym: SymTable, segment_id: str) -> dict:
    """``length`` is the drawn (projected 2D) length. A segment a registered
    kind gives a true length (the registry's ``true_length`` hook: a segment
    joining two corners of one prism) also gets ``true_length``, its 3D
    length (an edge gives one dimension; a face diagonal or the space
    diagonal the Euclidean combination)."""
    obj = _get(sym, segment_id)
    if not isinstance(obj, spg.Segment):
        raise TypeError(f"{segment_id!r} is not a Segment (got {type(obj).__name__})")
    out = {"length": float(obj.length.evalf())}
    true = DERIVED_REGISTRY.true_length(sym, segment_id)
    if true is not None:
        out["true_length"] = float(true.evalf())
    return out


def query_radius(sym: SymTable, circle_id: str) -> dict:
    obj = _get(sym, circle_id)
    if not isinstance(obj, spg.Circle):
        raise TypeError(f"{circle_id!r} is not a Circle (got {type(obj).__name__})")
    return {"radius": float(obj.radius.evalf())}


def query_area(sym: SymTable, obj_id: str) -> dict:
    obj = _get(sym, obj_id)
    if not isinstance(obj, spg.Polygon):
        raise TypeError(f"{obj_id!r} is not a Polygon (got {type(obj).__name__})")
    return {"area": float(abs(obj.area.evalf()))}


def query_perimeter(sym: SymTable, obj_id: str) -> dict:
    obj = _get(sym, obj_id)
    if not isinstance(obj, spg.Polygon):
        raise TypeError(f"{obj_id!r} is not a Polygon (got {type(obj).__name__})")
    return {"perimeter": float(obj.perimeter.evalf())}


def query_registered(sym: SymTable, query_type: str, obj_id: str) -> dict:
    """The ``query_type`` query a registered kind answers (the registry's
    ``query_type``/``query`` hooks: ``prism``, ``stack``) on ``obj_id``.
    Raises KeyError for an unknown id or query type and TypeError for an
    object of another type."""
    entry = DERIVED_REGISTRY.query_entry(query_type)
    if entry is None:
        raise KeyError(f"Unknown query type: {query_type!r}")
    obj = _get(sym, obj_id)
    if type(obj) is not entry.object_type:
        raise TypeError(
            f"{obj_id!r} is not a {entry.object_type.__name__} (got {type(obj).__name__})"
        )
    return entry.query(obj)


def query_prism(sym: SymTable, prism_id: str) -> dict:
    """True dimensions and derived measures of a rectangular prism, plus its
    corner ids keyed by corner bits (length, height, width), e.g. "100" is
    the corner one length along from the origin."""
    return query_registered(sym, "prism", prism_id)


def query_stack(sym: SymTable, stack_id: str) -> dict:
    """Cube count, volume (cubes are unit cubes), bounding extents (length =
    columns, width = rows, height = tallest column) and whether the cube set is
    a height map."""
    return query_registered(sym, "stack", stack_id)


def list_objects(sym: SymTable) -> dict[str, str]:
    return {
        obj_id: type(obj).__name__.removesuffix("2D")
        for obj_id, obj in sym.items()
        if not obj_id.startswith("__")
    }
