# geometry_diagrams/pydsl/__init__.py
"""Python fluent API surface for the geometry construction pipeline (Phase 1a).

Re-exports handles and op functions so callers (and the stub generator) have
one place to introspect the public surface.
"""
from geometry_diagrams.pydsl.api import line_through, point, triangle
from geometry_diagrams.pydsl.handles import Line, Point, Segment, Triangle

__all__ = ["point", "line_through", "triangle", "Point", "Line", "Segment", "Triangle"]
