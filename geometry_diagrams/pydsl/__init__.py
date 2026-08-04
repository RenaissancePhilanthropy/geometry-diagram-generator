"""Python fluent API surface for the geometry construction pipeline (Phase 1a).

Re-exports handles and op functions so callers (and the stub generator) have
one place to introspect the public surface.
"""
from geometry_diagrams.pydsl.api import altitude, circumcircle, draw, draw_points, incircle, line_through, mark_angle, median, point, polygon, triangle
from geometry_diagrams.pydsl.handles import AngleRef, Altitude, Circle, Line, Median, Point, Polygon, Segment, Triangle

__all__ = [
    "point",
    "line_through",
    "triangle",
    "polygon",
    "circumcircle",
    "incircle",
    "median",
    "altitude",
    "mark_angle",
    "draw",
    "draw_points",
    "Point",
    "Line",
    "Segment",
    "Triangle",
    "Polygon",
    "Circle",
    "Median",
    "Altitude",
    "AngleRef",
]
