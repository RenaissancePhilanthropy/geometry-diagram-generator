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
from .curve_measures import CurveMeasureError, curve_length
from .derived import REGISTRY as DERIVED_REGISTRY
from .to_sympy import Arc, EllipticalArc, EllipticalSector, Sector, SymTable, arc_param_frame


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


_ARCS = (Arc, EllipticalArc)
_SECTORS = (Sector, EllipticalSector)
_CURVED = _ARCS + _SECTORS


def _kind(obj_id: str, obj: Any) -> str:
    return f"{obj_id!r} (a {type(obj).__name__})"


def _radii(obj: Any) -> tuple[float, float]:
    """(hradius, vradius) of a circle/ellipse or an arc/sector of one."""
    if isinstance(obj, (Arc, Sector, spg.Circle)):
        r = float(obj.radius.evalf())
        return r, r
    return float(obj.hradius.evalf()), float(obj.vradius.evalf())


def _sector_frame(obj_id: str, obj: Any) -> tuple[float, float, float, float, float, float]:
    """``arc_param_frame`` of a sector, with a zero-radius sector reported as a
    degenerate radius (like ``curve_length`` does) instead of a bare
    ZeroDivisionError."""
    try:
        return arc_param_frame(obj)
    except ZeroDivisionError:
        raise CurveMeasureError(f"{_kind(obj_id, obj)} has a degenerate radius") from None


def query_length(sym: SymTable, segment_id: str) -> dict:
    """``length`` is the drawn (projected 2D) length. A segment a registered
    kind gives a true length (the registry's ``true_length`` hook: a segment
    joining two corners of one prism) also gets ``true_length``, its 3D
    length (an edge gives one dimension; a face diagonal or the space
    diagonal the Euclidean combination). An arc or sector (circular or
    elliptical) gives its curved edge's length; a full circle or ellipse is
    a ``perimeter``, not a length."""
    obj = _get(sym, segment_id)
    if isinstance(obj, _CURVED):
        return {"length": curve_length(obj)}
    if isinstance(obj, spg.Ellipse):
        raise TypeError(
            f"{_kind(segment_id, obj)} is a full {'circle' if isinstance(obj, spg.Circle) else 'ellipse'}, "
            "which has no length; use perimeter"
        )
    if not isinstance(obj, spg.Segment):
        raise TypeError(f"{segment_id!r} is not a Segment, arc or sector (got {type(obj).__name__})")
    out = {"length": float(obj.length.evalf())}
    true = DERIVED_REGISTRY.true_length(sym, segment_id)
    if true is not None:
        out["true_length"] = float(true.evalf())
    return out


def query_radius(sym: SymTable, circle_id: str) -> dict:
    """``radius`` of a circle or a circular arc/sector; an ellipse or an
    elliptical arc/sector has two radii, returned as ``hradius`` and
    ``vradius``."""
    obj = _get(sym, circle_id)
    if not isinstance(obj, (spg.Ellipse,) + _CURVED):
        raise TypeError(
            f"{circle_id!r} is not a Circle, Ellipse, arc or sector (got {type(obj).__name__})"
        )
    hr, vr = _radii(obj)
    if isinstance(obj, (spg.Circle, Arc, Sector)):
        return {"radius": hr}
    return {"hradius": hr, "vradius": vr}


def query_area(sym: SymTable, obj_id: str) -> dict:
    """Area of a polygon, circle, ellipse or sector (the enclosed region). An
    open arc encloses nothing."""
    obj = _get(sym, obj_id)
    if isinstance(obj, spg.Polygon):
        return {"area": float(abs(obj.area.evalf()))}
    if isinstance(obj, spg.Ellipse):
        hr, vr = _radii(obj)
        return {"area": math.pi * hr * vr}
    if isinstance(obj, _SECTORS):
        _, _, hr, vr, start, end = _sector_frame(obj_id, obj)
        # the region swept from the centre is hr*vr/2 per radian of parametric angle
        return {"area": hr * vr / 2 * (end - start)}
    if isinstance(obj, _ARCS):
        raise TypeError(f"{_kind(obj_id, obj)} is open: an open arc has no area; use a sector")
    raise TypeError(f"{obj_id!r} is not a Polygon, circle, ellipse or sector (got {type(obj).__name__})")


def query_perimeter(sym: SymTable, obj_id: str) -> dict:
    """Perimeter of a polygon, circumference of a circle/ellipse, or a sector's
    boundary (its two straight edges from the centre plus the curved edge).
    An open arc's only measure is its length."""
    obj = _get(sym, obj_id)
    if isinstance(obj, spg.Polygon):
        return {"perimeter": float(obj.perimeter.evalf())}
    if isinstance(obj, spg.Ellipse):
        return {"perimeter": curve_length(obj)}
    if isinstance(obj, _SECTORS):
        _, _, hr, vr, start, end = _sector_frame(obj_id, obj)
        # straight edges run to the curve's endpoints (for an ellipse, not the axes)
        edges = sum(math.hypot(hr * math.cos(t), vr * math.sin(t)) for t in (start, end))
        return {"perimeter": edges + curve_length(obj)}
    if isinstance(obj, _ARCS):
        raise TypeError(f"{_kind(obj_id, obj)} is open, so it has no perimeter distinct from its length; use length")
    raise TypeError(f"{obj_id!r} is not a Polygon, circle, ellipse or sector (got {type(obj).__name__})")


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
