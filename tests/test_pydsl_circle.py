# tests/test_pydsl_circle.py
"""Tests for the Circle handle and circumcircle()/incircle() ops."""
import math

from geometry_diagrams.pydsl.api import circumcircle, incircle, point, triangle
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


def test_circumcircle_center_is_a_computed_point_triangle_center():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(0, 3)
        t = triangle(a, b, c)
        circ = circumcircle(t)
        center = circ.center
        ir = get_builder().build()
    center_defs = [d for d in ir.define if d.kind == "point_triangle_center"]
    assert len(center_defs) == 1
    assert center_defs[0].which == "circumcenter"
    assert center_defs[0].tri == t.id
    assert center.id == center_defs[0].id


def test_circumcircle_radius_is_numeric_for_concrete_vertices():
    with new_builder_context():
        # 3-4-5 right triangle: circumradius of a right triangle is half the
        # hypotenuse — hypotenuse is 5, so R = 2.5.
        a, b, c = point(0, 0), point(4, 0), point(0, 3)
        t = triangle(a, b, c)
        circ = circumcircle(t)
    assert math.isclose(circ.radius, 2.5, abs_tol=1e-9)


def test_incircle_radius_is_numeric_for_concrete_vertices():
    with new_builder_context():
        # 3-4-5 right triangle: inradius = (a + b - c) / 2 = (3 + 4 - 5) / 2 = 1.0
        a, b, c = point(0, 0), point(4, 0), point(0, 3)
        t = triangle(a, b, c)
        inc = incircle(t)
    assert math.isclose(inc.radius, 1.0, abs_tol=1e-9)


def test_incircle_center_is_a_computed_incenter_point():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(0, 3)
        t = triangle(a, b, c)
        inc = incircle(t)
        center = inc.center
        ir = get_builder().build()
    center_defs = [d for d in ir.define if d.kind == "point_triangle_center" and d.which == "incenter"]
    assert len(center_defs) == 1
    assert center.id == center_defs[0].id
