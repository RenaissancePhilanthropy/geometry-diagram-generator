"""Python fluent API surface for the geometry construction pipeline (Phase 1a).

Re-exports handles and op functions so callers (and the stub generator) have
one place to introspect the public surface.
"""
from geometry_diagrams.pydsl.api import altitude, angle, angle_bisector, arc, canvas, centroid, circle, circumcircle, dilate_point, distance, draw, draw_brace, draw_points, ellipse, equation_steps, fill, foot_of_perpendicular, incircle, intersection, label_text, line_through, mark_angle, mark_equal, mark_parallel, mark_proportional, mark_right_angle, median, parallel_through, perpendicular_bisector, perpendicular_through, point, point_on, polygon, polyline, ray, rectangle, reflect_point, regular_polygon, regular_sectors, rotate_point, sector, segment, tangent_line, triangle, walk
from geometry_diagrams.pydsl.asserts import assert_angle_equal, assert_ccw, assert_centroid, assert_collinear, assert_congruent_triangles, assert_convex, assert_distance, assert_distinct_objects, assert_distinct_points, assert_equal_length, assert_in_canvas, assert_min_distance, assert_not_collinear, assert_not_on, assert_not_parallel, assert_on, assert_opposite_side, assert_parallel, assert_perpendicular, assert_ratio_equal, assert_right_angle, assert_same_side, assert_similar_triangles, assert_tangent
from geometry_diagrams.pydsl.handles import AngleRef, Altitude, Arc, Circle, Ellipse, Line, Median, PerpendicularBisectorLine, Point, Polygon, Polyline, Ray, Sector, Segment, Triangle
from geometry_diagrams.pydsl.cookbook import array_of, bar, bars, table_grid, tick_marks, unit_grid

__all__ = [
    "point",
    "line_through",
    "ray",
    "triangle",
    "polygon",
    "polyline",
    "regular_polygon",
    "regular_sectors",
    "rectangle",
    "segment",
    "distance",
    "tangent_line",
    "circumcircle",
    "incircle",
    "circle",
    "ellipse",
    "arc",
    "sector",
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
    "angle",
    "mark_angle",
    "mark_equal",
    "mark_parallel",
    "mark_proportional",
    "mark_right_angle",
    "draw",
    "draw_brace",
    "draw_points",
    "fill",
    "label_text",
    "equation_steps",
    "point_on",
    "rotate_point",
    "reflect_point",
    "dilate_point",
    "walk",
    "Point",
    "Line",
    "Ray",
    "Segment",
    "Triangle",
    "Polygon",
    "Polyline",
    "Circle",
    "Ellipse",
    "Arc",
    "Sector",
    "Median",
    "PerpendicularBisectorLine",
    "Altitude",
    "AngleRef",
    "assert_distinct_points",
    "assert_distinct_objects",
    "assert_not_collinear",
    "assert_collinear",
    "assert_on",
    "assert_not_on",
    "assert_parallel",
    "assert_not_parallel",
    "assert_perpendicular",
    "assert_right_angle",
    "assert_angle_equal",
    "assert_equal_length",
    "assert_distance",
    "assert_ratio_equal",
    "assert_similar_triangles",
    "assert_tangent",
    "assert_opposite_side",
    "assert_same_side",
    "assert_centroid",
    "assert_convex",
    "assert_ccw",
    "assert_min_distance",
    "assert_congruent_triangles",
    "assert_in_canvas",
]

# Experimental diagram cookbook (ticket 08, diagram-kinds-poc): names of
# helper functions from geometry_diagrams.pydsl.cookbook, gated behind
# PythonFullStrategy.run()'s experimental_diagram_cookbook flag /
# sandbox.run_script()'s enable_cookbook flag. Deliberately kept OUT of
# __all__ above — these must never reach a sandboxed script unless the
# caller opts in (see cookbook.py's own docstring).
#
# Each name here must ALSO be importable as an attribute of this package
# (see the `from geometry_diagrams.pydsl.cookbook import ...` line above) —
# _sandbox_child.py's _build_tool_names does getattr(pydsl_module, name) for
# each of these, so a name added here without a matching import above
# raises AttributeError the moment enable_cookbook=True.
#
# Ticket 09 populates this with its grid/discrete-object helpers; later
# tickets (10-12) append further names as they add more cookbook.py
# functions.
#
# Ticket 10 appends "bar"/"bars" (rectangle bars for tape diagrams, bar
# graphs, area-model cells, and fill-level containers).
#
# Ticket 11 appends "table_grid" (a bordered grid of labeled cells,
# underlying attribute_chart, work_table, place_value_chart,
# column_arithmetic, and long_division).
COOKBOOK_NAMES: list[str] = ["unit_grid", "array_of", "tick_marks", "bar", "bars", "table_grid"]
