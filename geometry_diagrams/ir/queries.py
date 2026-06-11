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
    obj = _get(sym, segment_id)
    if not isinstance(obj, spg.Segment):
        raise TypeError(f"{segment_id!r} is not a Segment (got {type(obj).__name__})")
    return {"length": float(obj.length.evalf())}


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


def list_objects(sym: SymTable) -> dict[str, str]:
    return {
        obj_id: type(obj).__name__.removesuffix("2D")
        for obj_id, obj in sym.items()
        if not obj_id.startswith("__")
    }
