"""Python fluent API surface for the geometry construction pipeline (Phase 1a).

Re-exports handles and op functions so callers (and the stub generator) have
one place to introspect the public surface.
"""
from geometry_diagrams.pydsl.api import altitude, circumcircle, dilate_point, draw, draw_points, incircle, label_text, line_through, mark_angle, median, point, point_on, polygon, reflect_point, rotate_point, segment, triangle
from geometry_diagrams.pydsl.handles import AngleRef, Altitude, Circle, Line, Median, Point, Polygon, Segment, Triangle

__all__ = [
    "point",
    "line_through",
    "triangle",
    "polygon",
    "segment",
    "circumcircle",
    "incircle",
    "median",
    "altitude",
    "mark_angle",
    "draw",
    "draw_points",
    "label_text",
    "point_on",
    "rotate_point",
    "reflect_point",
    "dilate_point",
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
