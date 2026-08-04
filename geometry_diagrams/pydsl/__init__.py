# geometry_diagrams/pydsl/__init__.py
"""Python fluent API surface for the geometry construction pipeline (Phase 1a).

Re-exports handles and op functions so callers (and the stub generator) have
one place to introspect the public surface.
"""
from geometry_diagrams.pydsl.api import circumcircle, incircle, line_through, point, polygon, triangle
from geometry_diagrams.pydsl.handles import Circle, Line, Point, Polygon, Segment, Triangle

__all__ = [
    "point",
    "line_through",
    "triangle",
    "polygon",
    "circumcircle",
    "incircle",
    "Point",
    "Line",
    "Segment",
    "Triangle",
    "Polygon",
    "Circle",
]
