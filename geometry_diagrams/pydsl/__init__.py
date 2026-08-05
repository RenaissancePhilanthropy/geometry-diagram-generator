"""Python fluent API surface for the geometry construction pipeline (Phase 1a).

Re-exports handles and op functions so callers (and the stub generator) have
one place to introspect the public surface.
"""
from geometry_diagrams.pydsl.api import altitude, angle_bisector, canvas, centroid, circumcircle, dilate_point, draw, draw_points, foot_of_perpendicular, incircle, intersection, label_text, line_through, mark_angle, median, parallel_through, perpendicular_bisector, perpendicular_through, point, point_on, polygon, ray, reflect_point, rotate_point, segment, tangent_line, triangle
from geometry_diagrams.pydsl.handles import AngleRef, Altitude, Circle, Line, Median, PerpendicularBisectorLine, Point, Polygon, Ray, Segment, Triangle

__all__ = [
    "point",
    "line_through",
    "ray",
    "triangle",
    "polygon",
    "segment",
    "tangent_line",
    "circumcircle",
    "incircle",
    "intersection",
    "median",
    "altitude",
    "angle_bisector",
    "centroid",
    "foot_of_perpendicular",
    "parallel_through",
    "perpendicular_bisector",
    "perpendicular_through",
    "canvas",
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
    "Ray",
    "Segment",
    "Triangle",
    "Polygon",
    "Circle",
    "Median",
    "PerpendicularBisectorLine",
    "Altitude",
    "AngleRef",
]
