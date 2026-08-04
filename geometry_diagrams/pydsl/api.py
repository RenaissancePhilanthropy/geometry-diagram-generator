# geometry_diagrams/pydsl/api.py
"""Public builder-shim API. Every function here records an op against the
ambient Builder (see builder.py) and returns a handle."""
from __future__ import annotations

from geometry_diagrams.ir.ir import LineThrough, PointFixed
from geometry_diagrams.ir.ir import Polygon as PolygonDef
from geometry_diagrams.ir.ir import Triangle as TriangleDef
from geometry_diagrams.pydsl.builder import get_builder
from geometry_diagrams.pydsl.handles import Line, Point, Polygon, Triangle


def point(x: float, y: float) -> Point:
    """A point fixed at literal coordinates (x, y)."""
    builder = get_builder()
    pid = builder._fresh_hidden_id("pt")
    builder._add(PointFixed(id=pid, x=x, y=y))
    builder._coord_floats[pid] = (float(x), float(y))
    return Point(id=pid)


def line_through(p: Point, q: Point) -> Line:
    """The line through two points."""
    builder = get_builder()
    lid = builder._fresh_hidden_id("line")
    builder._add(LineThrough(id=lid, p=p.id, q=q.id))
    return Line(id=lid)


def triangle(a: Point, b: Point, c: Point) -> Triangle:
    """A triangle over three existing points."""
    builder = get_builder()
    tid = builder._fresh_hidden_id("tri")
    builder._add(TriangleDef(id=tid, a=a.id, b=b.id, c=c.id))
    return Triangle(id=tid, vertices=(a, b, c), _builder=builder)


def polygon(*vertices: Point) -> Polygon:
    """A closed polygon over 3 or more existing points, in perimeter order."""
    if len(vertices) < 3:
        raise ValueError(f"polygon requires at least 3 vertices, got {len(vertices)}")
    builder = get_builder()
    pid = builder._fresh_hidden_id("poly")
    builder._add(PolygonDef(id=pid, points=[v.id for v in vertices]))
    return Polygon(id=pid, vertices=tuple(vertices), _builder=builder)
