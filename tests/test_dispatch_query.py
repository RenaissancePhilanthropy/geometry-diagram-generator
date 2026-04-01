# tests/test_dispatch_query.py
"""Tests for dispatch_query — the query_diagram tool dispatcher."""
from __future__ import annotations

import json
import pytest
import sympy.geometry as spg

from strategies.structured import dispatch_query


@pytest.fixture
def simple_sym():
    A = spg.Point(0, 0)
    B = spg.Point(3, 0)
    C = spg.Point(3, 4)
    return {
        "A": A,
        "B": B,
        "C": C,
        "seg_AB": spg.Segment(A, B),
        "tri_ABC": spg.Triangle(A, B, C),
        "circ": spg.Circle(A, 2),
    }


class TestDispatchQuery:
    def test_coordinate(self, simple_sym):
        result = json.loads(dispatch_query(simple_sym, "coordinate", {"point": "A"}))
        assert result == {"x": 0.0, "y": 0.0}

    def test_distance(self, simple_sym):
        result = json.loads(dispatch_query(simple_sym, "distance", {"a": "A", "b": "B"}))
        assert result["distance"] == pytest.approx(3.0)

    def test_angle(self, simple_sym):
        result = json.loads(dispatch_query(simple_sym, "angle", {"a": "A", "vertex": "B", "b": "C"}))
        assert result["angle_degrees"] == pytest.approx(90.0)

    def test_length(self, simple_sym):
        result = json.loads(dispatch_query(simple_sym, "length", {"segment": "seg_AB"}))
        assert result["length"] == pytest.approx(3.0)

    def test_radius(self, simple_sym):
        result = json.loads(dispatch_query(simple_sym, "radius", {"circle": "circ"}))
        assert result["radius"] == pytest.approx(2.0)

    def test_area(self, simple_sym):
        result = json.loads(dispatch_query(simple_sym, "area", {"object": "tri_ABC"}))
        assert result["area"] == pytest.approx(6.0)

    def test_perimeter(self, simple_sym):
        result = json.loads(dispatch_query(simple_sym, "perimeter", {"object": "tri_ABC"}))
        assert result["perimeter"] == pytest.approx(12.0)

    def test_angle_ray_keys(self, simple_sym):
        result = json.loads(dispatch_query(simple_sym, "angle", {"ray1": "A", "vertex": "B", "ray2": "C"}))
        assert result["angle_degrees"] == pytest.approx(90.0)

    def test_distance_point_keys(self, simple_sym):
        result = json.loads(dispatch_query(simple_sym, "distance", {"point1": "A", "point2": "B"}))
        assert result["distance"] == pytest.approx(3.0)

    def test_list_objects(self, simple_sym):
        result = json.loads(dispatch_query(simple_sym, "list_objects", {}))
        assert result["A"] == "Point"
        assert result["seg_AB"] == "Segment"

    def test_list_objects_hides_internal(self, simple_sym):
        sym = dict(simple_sym)
        sym["__mark_seg_A_B"] = spg.Segment(sym["A"], sym["B"])
        result = json.loads(dispatch_query(sym, "list_objects", {}))
        assert "__mark_seg_A_B" not in result
        assert "A" in result  # normal objects still present

    def test_unknown_query_type(self, simple_sym):
        result = json.loads(dispatch_query(simple_sym, "foobar", {}))
        assert "error" in result

    def test_missing_object_returns_error(self, simple_sym):
        result = json.loads(dispatch_query(simple_sym, "coordinate", {"point": "Z"}))
        assert "error" in result

    def test_type_mismatch_returns_error(self, simple_sym):
        result = json.loads(dispatch_query(simple_sym, "radius", {"circle": "A"}))
        assert "error" in result
