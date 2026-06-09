# tests/test_queries.py
"""Tests for ir/queries.py — geometric query functions over a SymTable."""
from __future__ import annotations

import math
import pytest
import sympy.geometry as spg

from geometry_diagrams.ir.queries import (
    query_coordinate, query_distance, query_angle,
    query_length, query_radius, query_area, query_perimeter,
    list_objects,
)


# -- Fixtures: a right triangle A(0,0) B(3,0) C(3,4) with a circle --

@pytest.fixture
def right_triangle_sym():
    A = spg.Point(0, 0)
    B = spg.Point(3, 0)
    C = spg.Point(3, 4)
    return {
        "A": A,
        "B": B,
        "C": C,
        "seg_AB": spg.Segment(A, B),
        "seg_BC": spg.Segment(B, C),
        "seg_AC": spg.Segment(A, C),
        "tri_ABC": spg.Triangle(A, B, C),
        "circ": spg.Circle(A, 2),
        "line_AB": spg.Line(A, B),
    }


class TestQueryCoordinate:
    def test_returns_xy(self, right_triangle_sym):
        result = query_coordinate(right_triangle_sym, "B")
        assert result == {"x": 3.0, "y": 0.0}

    def test_unknown_id_raises(self, right_triangle_sym):
        with pytest.raises(KeyError, match="Z"):
            query_coordinate(right_triangle_sym, "Z")

    def test_non_point_raises(self, right_triangle_sym):
        with pytest.raises(TypeError, match="not a Point"):
            query_coordinate(right_triangle_sym, "seg_AB")


class TestQueryDistance:
    def test_distance(self, right_triangle_sym):
        result = query_distance(right_triangle_sym, "A", "B")
        assert result == {"distance": pytest.approx(3.0)}

    def test_hypotenuse(self, right_triangle_sym):
        result = query_distance(right_triangle_sym, "A", "C")
        assert result == {"distance": pytest.approx(5.0)}

    def test_unknown_id_raises(self, right_triangle_sym):
        with pytest.raises(KeyError, match="Z"):
            query_distance(right_triangle_sym, "A", "Z")

    def test_non_point_second_arg_raises(self, right_triangle_sym):
        with pytest.raises(TypeError, match="not a Point"):
            query_distance(right_triangle_sym, "A", "seg_AB")


class TestQueryAngle:
    def test_right_angle(self, right_triangle_sym):
        result = query_angle(right_triangle_sym, "A", "B", "C")
        assert result == {"angle_degrees": pytest.approx(90.0)}

    def test_other_angle(self, right_triangle_sym):
        # Angle at A: arctan(4/3) ≈ 53.13°
        result = query_angle(right_triangle_sym, "B", "A", "C")
        assert result == {"angle_degrees": pytest.approx(math.degrees(math.atan2(4, 3)))}

    def test_degenerate_raises(self, right_triangle_sym):
        with pytest.raises(ValueError, match="Degenerate"):
            query_angle(right_triangle_sym, "A", "A", "B")


class TestQueryLength:
    def test_segment_length(self, right_triangle_sym):
        result = query_length(right_triangle_sym, "seg_AB")
        assert result == {"length": pytest.approx(3.0)}

    def test_hypotenuse_length(self, right_triangle_sym):
        result = query_length(right_triangle_sym, "seg_AC")
        assert result == {"length": pytest.approx(5.0)}

    def test_non_segment_raises(self, right_triangle_sym):
        with pytest.raises(TypeError, match="Segment"):
            query_length(right_triangle_sym, "A")


class TestQueryRadius:
    def test_radius(self, right_triangle_sym):
        result = query_radius(right_triangle_sym, "circ")
        assert result == {"radius": pytest.approx(2.0)}

    def test_non_circle_raises(self, right_triangle_sym):
        with pytest.raises(TypeError, match="Circle"):
            query_radius(right_triangle_sym, "seg_AB")


class TestQueryArea:
    def test_triangle_area(self, right_triangle_sym):
        # 3*4/2 = 6
        result = query_area(right_triangle_sym, "tri_ABC")
        assert result == {"area": pytest.approx(6.0)}

    def test_non_polygon_raises(self, right_triangle_sym):
        with pytest.raises(TypeError, match="not a Polygon"):
            query_area(right_triangle_sym, "A")

    def test_polygon_area(self, right_triangle_sym):
        # A unit square has area 1.0
        sq = spg.Polygon(spg.Point(0,0), spg.Point(1,0), spg.Point(1,1), spg.Point(0,1))
        sym = {"sq": sq}
        result = query_area(sym, "sq")
        assert result == {"area": pytest.approx(1.0)}


class TestQueryPerimeter:
    def test_triangle_perimeter(self, right_triangle_sym):
        # 3 + 4 + 5 = 12
        result = query_perimeter(right_triangle_sym, "tri_ABC")
        assert result == {"perimeter": pytest.approx(12.0)}

    def test_non_polygon_raises(self, right_triangle_sym):
        with pytest.raises(TypeError, match="not a Polygon"):
            query_perimeter(right_triangle_sym, "circ")

    def test_polygon_perimeter(self, right_triangle_sym):
        # A unit square has perimeter 4.0
        sq = spg.Polygon(spg.Point(0,0), spg.Point(1,0), spg.Point(1,1), spg.Point(0,1))
        sym = {"sq": sq}
        result = query_perimeter(sym, "sq")
        assert result == {"perimeter": pytest.approx(4.0)}


class TestListObjects:
    def test_lists_all_with_types(self, right_triangle_sym):
        result = list_objects(right_triangle_sym)
        # SymPy uses Point2D, Segment2D, Line2D internally; list_objects normalizes by stripping "2D" suffix
        assert result["A"] == "Point"
        assert result["seg_AB"] == "Segment"
        assert result["tri_ABC"] == "Triangle"
        assert result["circ"] == "Circle"
        assert result["line_AB"] == "Line"
