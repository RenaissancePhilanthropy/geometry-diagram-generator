# tests/test_pydsl_asserts.py
"""Tests for pydsl's 19 assert_* mirror predicates (geometry_diagrams/pydsl/asserts.py).

Each predicate mirrors an existing ir.Check kind via the shared _run_assertion
dispatch helper. Matches test_pydsl_marks_and_holes.py's structure: build
through a real Builder/new_builder_context(), exercise the real api.py
functions, then assert on the resulting pass/fail behavior."""
import math

import pytest

from geometry_diagrams.pydsl.api import (
    angle, canvas, circle, intersection, line_through, point, point_on,
    polygon, ray, rotate_point, segment, tangent_line, triangle,
)
from geometry_diagrams.pydsl.asserts import (
    assert_angle_equal, assert_ccw, assert_centroid, assert_collinear,
    assert_congruent_triangles, assert_convex, assert_distance,
    assert_distinct_objects, assert_distinct_points, assert_equal_length,
    assert_in_canvas, assert_min_distance, assert_not_collinear,
    assert_not_on, assert_not_parallel, assert_on, assert_opposite_side,
    assert_parallel, assert_perpendicular, assert_ratio_equal,
    assert_right_angle, assert_same_side, assert_similar_triangles,
    assert_tangent,
)
from geometry_diagrams.pydsl.builder import GeometricAssertionError, new_builder_context


# ---------------------------------------------------------------------------
# assert_distinct_points
# ---------------------------------------------------------------------------

def test_assert_distinct_points_pass():
    with new_builder_context():
        p, q = point(0, 0), point(1, 0)
        assert_distinct_points(p, q)  # should not raise


def test_assert_distinct_points_fail():
    with new_builder_context():
        p, q = point(2, 1), point(2, 1)
        with pytest.raises(GeometricAssertionError):
            assert_distinct_points(p, q)


# ---------------------------------------------------------------------------
# assert_distinct_objects
# ---------------------------------------------------------------------------

def test_assert_distinct_objects_pass():
    with new_builder_context():
        c1 = circle(point(0, 0), 1.0)
        c2 = circle(point(0, 0), 2.0)
        assert_distinct_objects(c1, c2)


def test_assert_distinct_objects_fail():
    with new_builder_context():
        center = point(0, 0)
        c1 = circle(center, 1.0)
        c2 = circle(center, 1.0)
        with pytest.raises(GeometricAssertionError):
            assert_distinct_objects(c1, c2)


# ---------------------------------------------------------------------------
# assert_not_collinear / assert_collinear
# ---------------------------------------------------------------------------

def test_assert_not_collinear_pass():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(0, 4)
        assert_not_collinear(a, b, c)


def test_assert_not_collinear_fail():
    with new_builder_context():
        a, b, c = point(0, 0), point(2, 0), point(4, 0)
        with pytest.raises(GeometricAssertionError):
            assert_not_collinear(a, b, c)


def test_assert_collinear_pass():
    with new_builder_context():
        a, b, c = point(0, 0), point(2, 0), point(4, 0)
        assert_collinear(a, b, c)


def test_assert_collinear_fail():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(0, 4)
        with pytest.raises(GeometricAssertionError):
            assert_collinear(a, b, c)


# ---------------------------------------------------------------------------
# assert_on / assert_not_on
# ---------------------------------------------------------------------------

def test_assert_on_pass():
    with new_builder_context():
        a, b = point(0, 0), point(4, 0)
        line = line_through(a, b)
        p = point_on(line, 0.5)
        assert_on(p, line)


def test_assert_on_fail():
    with new_builder_context():
        a, b = point(0, 0), point(4, 0)
        line = line_through(a, b)
        off = point(2, 5)
        with pytest.raises(GeometricAssertionError):
            assert_on(off, line)


def test_assert_not_on_pass():
    with new_builder_context():
        a, b = point(0, 0), point(4, 0)
        line = line_through(a, b)
        off = point(2, 5)
        assert_not_on(off, line)


def test_assert_not_on_fail():
    with new_builder_context():
        a, b = point(0, 0), point(4, 0)
        line = line_through(a, b)
        p = point_on(line, 0.5)
        with pytest.raises(GeometricAssertionError):
            assert_not_on(p, line)


# ---------------------------------------------------------------------------
# assert_parallel / assert_not_parallel
# ---------------------------------------------------------------------------

def test_assert_parallel_pass():
    with new_builder_context():
        l1 = line_through(point(0, 0), point(4, 0))
        l2 = line_through(point(0, 1), point(4, 1))
        assert_parallel(l1, l2)


def test_assert_parallel_fail():
    with new_builder_context():
        l1 = line_through(point(0, 0), point(4, 0))
        l2 = line_through(point(0, 0), point(0, 4))
        with pytest.raises(GeometricAssertionError):
            assert_parallel(l1, l2)


def test_assert_not_parallel_pass():
    with new_builder_context():
        l1 = line_through(point(0, 0), point(4, 0))
        l2 = line_through(point(0, 0), point(0, 4))
        assert_not_parallel(l1, l2)


def test_assert_not_parallel_fail():
    with new_builder_context():
        l1 = line_through(point(0, 0), point(4, 0))
        l2 = line_through(point(0, 1), point(4, 1))
        with pytest.raises(GeometricAssertionError):
            assert_not_parallel(l1, l2)


# ---------------------------------------------------------------------------
# assert_perpendicular
# ---------------------------------------------------------------------------

def test_assert_perpendicular_pass():
    with new_builder_context():
        l1 = line_through(point(0, 0), point(4, 0))
        l2 = line_through(point(0, 0), point(0, 4))
        assert_perpendicular(l1, l2)


def test_assert_perpendicular_fail():
    with new_builder_context():
        l1 = line_through(point(0, 0), point(4, 0))
        l2 = line_through(point(0, 1), point(4, 1))
        with pytest.raises(GeometricAssertionError):
            assert_perpendicular(l1, l2)


# ---------------------------------------------------------------------------
# assert_right_angle
# ---------------------------------------------------------------------------

def test_assert_right_angle_pass():
    with new_builder_context():
        o = point(0, 0)
        a = point(4, 0)
        b = point(0, 4)
        ref = angle(a, o, b)
        assert_right_angle(ref)


def test_assert_right_angle_fail():
    with new_builder_context():
        o = point(0, 0)
        a = point(4, 0)
        b = point(4, 4)
        ref = angle(a, o, b)
        with pytest.raises(GeometricAssertionError):
            assert_right_angle(ref)


def test_assert_right_angle_docstring_notes_hint_limitation():
    assert "hint" in assert_right_angle.__doc__.lower()


# ---------------------------------------------------------------------------
# assert_angle_equal
# ---------------------------------------------------------------------------

def test_assert_angle_equal_pass():
    with new_builder_context():
        o1 = point(0, 0)
        ref1 = angle(point(4, 0), o1, point(0, 4))
        o2 = point(10, 0)
        ref2 = angle(point(14, 0), o2, point(10, 4))
        assert_angle_equal(ref1, ref2)


def test_assert_angle_equal_fail():
    with new_builder_context():
        o1 = point(0, 0)
        ref1 = angle(point(4, 0), o1, point(0, 4))
        o2 = point(10, 0)
        ref2 = angle(point(14, 0), o2, point(11, 1))
        with pytest.raises(GeometricAssertionError):
            assert_angle_equal(ref1, ref2)


def test_assert_angle_equal_docstring_notes_hint_limitation():
    assert "hint" in assert_angle_equal.__doc__.lower()


# ---------------------------------------------------------------------------
# assert_equal_length
# ---------------------------------------------------------------------------

def test_assert_equal_length_pass():
    with new_builder_context():
        s1 = segment(point(0, 0), point(4, 0))
        s2 = segment(point(0, 1), point(4, 1))
        assert_equal_length(s1, s2)


def test_assert_equal_length_fail():
    with new_builder_context():
        s1 = segment(point(0, 0), point(4, 0))
        s2 = segment(point(0, 1), point(2, 1))
        with pytest.raises(GeometricAssertionError):
            assert_equal_length(s1, s2)


# ---------------------------------------------------------------------------
# assert_distance
# ---------------------------------------------------------------------------

def test_assert_distance_pass():
    with new_builder_context():
        s = segment(point(0, 0), point(4, 0))
        assert_distance(s, 4.0)


def test_assert_distance_fail():
    with new_builder_context():
        s = segment(point(0, 0), point(4, 0))
        with pytest.raises(GeometricAssertionError):
            assert_distance(s, 10.0)


# ---------------------------------------------------------------------------
# assert_ratio_equal
# ---------------------------------------------------------------------------

def test_assert_ratio_equal_pass():
    with new_builder_context():
        s1 = segment(point(0, 0), point(2, 0))
        s2 = segment(point(0, 0), point(4, 0))
        s3 = segment(point(0, 0), point(1, 0))
        s4 = segment(point(0, 0), point(2, 0))
        assert_ratio_equal(s1, s2, s3, s4)


def test_assert_ratio_equal_fail():
    with new_builder_context():
        s1 = segment(point(0, 0), point(2, 0))
        s2 = segment(point(0, 0), point(4, 0))
        s3 = segment(point(0, 0), point(1, 0))
        s4 = segment(point(0, 0), point(1, 0))
        with pytest.raises(GeometricAssertionError):
            assert_ratio_equal(s1, s2, s3, s4)


# ---------------------------------------------------------------------------
# assert_similar_triangles
# ---------------------------------------------------------------------------

def test_assert_similar_triangles_pass():
    with new_builder_context():
        t1 = triangle(point(0, 0), point(4, 0), point(0, 3))
        t2 = triangle(point(10, 0), point(18, 0), point(10, 6))
        assert_similar_triangles(t1, t2)


def test_assert_similar_triangles_fail():
    with new_builder_context():
        t1 = triangle(point(0, 0), point(4, 0), point(0, 3))
        t2 = triangle(point(10, 0), point(15, 0), point(10, 15))
        with pytest.raises(GeometricAssertionError):
            assert_similar_triangles(t1, t2)


# ---------------------------------------------------------------------------
# assert_tangent
# ---------------------------------------------------------------------------

def test_assert_tangent_pass():
    with new_builder_context():
        center = point(0, 0)
        c = circle(center, 3.0)
        touch = point_on(c, 0.0)
        line = tangent_line(c, at=touch)
        assert_tangent(line, c)


def test_assert_tangent_fail():
    with new_builder_context():
        center = point(0, 0)
        c = circle(center, 3.0)
        # a secant through the circle, not tangent
        line = line_through(point(-5, 0), point(5, 0))
        with pytest.raises(GeometricAssertionError):
            assert_tangent(line, c)


# ---------------------------------------------------------------------------
# assert_opposite_side / assert_same_side
# ---------------------------------------------------------------------------

def test_assert_opposite_side_pass():
    with new_builder_context():
        line_a, line_b = point(0, 0), point(0, 4)
        p, q = point(-2, 1), point(2, 1)
        assert_opposite_side(p, q, line_a, line_b)


def test_assert_opposite_side_fail():
    with new_builder_context():
        line_a, line_b = point(0, 0), point(0, 4)
        p, q = point(2, 1), point(3, 1)
        with pytest.raises(GeometricAssertionError):
            assert_opposite_side(p, q, line_a, line_b)


def test_assert_same_side_pass():
    with new_builder_context():
        line_a, line_b = point(0, 0), point(0, 4)
        p, q = point(2, 1), point(3, 1)
        assert_same_side(p, q, line_a, line_b)


def test_assert_same_side_fail():
    with new_builder_context():
        line_a, line_b = point(0, 0), point(0, 4)
        p, q = point(-2, 1), point(2, 1)
        with pytest.raises(GeometricAssertionError):
            assert_same_side(p, q, line_a, line_b)


# ---------------------------------------------------------------------------
# assert_centroid
# ---------------------------------------------------------------------------

def test_assert_centroid_pass():
    with new_builder_context():
        a, b, c = point(0, 0), point(6, 0), point(0, 6)
        g = point(2, 2)
        assert_centroid(g, a, b, c)


def test_assert_centroid_fail():
    with new_builder_context():
        a, b, c = point(0, 0), point(6, 0), point(0, 6)
        g = point(5, 5)
        with pytest.raises(GeometricAssertionError):
            assert_centroid(g, a, b, c)


# ---------------------------------------------------------------------------
# Deferred-point regression test (ticket's explicit acceptance criterion)
# ---------------------------------------------------------------------------

def test_assert_on_deferred_intersection_point_resolves():
    """An assert_* call must be able to be the very first thing that forces
    resolution of a point produced by intersection() — its .x/.y must never
    have been touched before the assert_* call."""
    with new_builder_context():
        l1 = line_through(point(0, 0), point(4, 4))
        l2 = line_through(point(0, 4), point(4, 0))
        p = intersection(l1, l2)
        # p._x/_y are still None here — no .x/.y access yet.
        assert p._x is None and p._y is None
        assert_on(p, l1)  # must resolve correctly, not raise "no known coordinates"


def test_assert_distinct_points_deferred_rotate_point_resolves():
    with new_builder_context():
        center = point(0, 0)
        source = point(2, 0)
        rotated = rotate_point(source, center, math.pi / 2)
        assert rotated._x is None and rotated._y is None
        assert_distinct_points(source, rotated)


# ---------------------------------------------------------------------------
# Message-content test (ticket's explicit acceptance criterion)
# ---------------------------------------------------------------------------

def test_fail_message_substitutes_coordinates_not_hidden_ids():
    with new_builder_context():
        p, q = point(2, 1), point(2, 1)
        with pytest.raises(GeometricAssertionError) as excinfo:
            assert_distinct_points(p, q)
        msg = str(excinfo.value)
        assert "(2.00, 1.00)" in msg
        assert "__pydsl_" not in msg


# ---------------------------------------------------------------------------
# tol override
# ---------------------------------------------------------------------------

def test_assert_distance_tol_override_permits_looser_match():
    with new_builder_context():
        s = segment(point(0, 0), point(4, 0))
        # default tol (relative ~5e-3) would fail at length 4.1; a looser
        # explicit tol should let it pass.
        assert_distance(s, 4.1, tol=0.5)


def test_assert_distance_tol_override_still_fails_outside_tol():
    with new_builder_context():
        s = segment(point(0, 0), point(4, 0))
        with pytest.raises(GeometricAssertionError):
            assert_distance(s, 4.1, tol=1e-6)


# ---------------------------------------------------------------------------
# assert_convex
# ---------------------------------------------------------------------------

def test_assert_convex_pass():
    with new_builder_context():
        sq = polygon(point(0, 0), point(4, 0), point(4, 4), point(0, 4))
        assert_convex(sq)


def test_assert_convex_fail():
    with new_builder_context():
        # dart-shaped (non-convex) quadrilateral
        dart = polygon(point(0, 0), point(4, 4), point(0, 2), point(-4, 4))
        with pytest.raises(GeometricAssertionError):
            assert_convex(dart)


# ---------------------------------------------------------------------------
# assert_ccw
# ---------------------------------------------------------------------------

def test_assert_ccw_pass():
    with new_builder_context():
        sq = polygon(point(0, 0), point(4, 0), point(4, 4), point(0, 4))
        assert_ccw(sq)


def test_assert_ccw_fail():
    with new_builder_context():
        # clockwise winding
        sq = polygon(point(0, 0), point(0, 4), point(4, 4), point(4, 0))
        with pytest.raises(GeometricAssertionError):
            assert_ccw(sq)


# ---------------------------------------------------------------------------
# assert_min_distance
# ---------------------------------------------------------------------------

def test_assert_min_distance_pass():
    with new_builder_context():
        p, q = point(0, 0), point(10, 0)
        assert_min_distance(p, q, 5.0)


def test_assert_min_distance_fail():
    with new_builder_context():
        p, q = point(0, 0), point(1, 0)
        with pytest.raises(GeometricAssertionError):
            assert_min_distance(p, q, 5.0)


# ---------------------------------------------------------------------------
# assert_congruent_triangles
# ---------------------------------------------------------------------------

def test_assert_congruent_triangles_pass():
    with new_builder_context():
        t1 = triangle(point(0, 0), point(4, 0), point(0, 3))
        # same side lengths (3-4-5), different vertex order/placement
        t2 = triangle(point(10, 0), point(10, 4), point(13, 4))
        assert_congruent_triangles(t1, t2)


def test_assert_congruent_triangles_fail():
    with new_builder_context():
        t1 = triangle(point(0, 0), point(4, 0), point(0, 3))
        t2 = triangle(point(10, 0), point(20, 0), point(10, 15))
        with pytest.raises(GeometricAssertionError):
            assert_congruent_triangles(t1, t2)


def test_assert_congruent_triangles_distinguishes_from_similar():
    """Same angles, different scale: similar passes, congruent fails."""
    with new_builder_context():
        t1 = triangle(point(0, 0), point(4, 0), point(0, 3))
        t2 = triangle(point(10, 0), point(18, 0), point(10, 6))  # 2x scale
        assert_similar_triangles(t1, t2)
        with pytest.raises(GeometricAssertionError):
            assert_congruent_triangles(t1, t2)


# ---------------------------------------------------------------------------
# assert_in_canvas (pydsl-only; not backed by an ir.Check kind)
# ---------------------------------------------------------------------------

def test_assert_in_canvas_pass_default_bounds():
    with new_builder_context():
        p = point(1, 1)  # within ir.Canvas()'s default [-5, 5] x [-5, 5]
        assert_in_canvas(p)


def test_assert_in_canvas_fail_default_bounds():
    with new_builder_context():
        p = point(100, 100)  # well outside default bounds
        with pytest.raises(GeometricAssertionError):
            assert_in_canvas(p)


def test_assert_in_canvas_after_canvas_call_uses_custom_bounds():
    """Calling assert_in_canvas() after canvas(...) validates against the
    custom bounds the script just set."""
    with new_builder_context():
        canvas((0, 20), (0, 20))
        p = point(10, 10)  # outside default [-5,5]x[-5,5], inside custom bounds
        assert_in_canvas(p)


def test_assert_in_canvas_before_canvas_call_uses_default_bounds():
    """Calling assert_in_canvas() before the script's own canvas(...) call
    sees ir.Canvas()'s default bounds, not the custom ones set afterward —
    the documented ordering hazard, locked in as a test."""
    with new_builder_context():
        p = point(10, 10)  # outside default [-5,5]x[-5,5]
        with pytest.raises(GeometricAssertionError):
            assert_in_canvas(p)  # canvas() hasn't been called yet
        canvas((0, 20), (0, 20))  # set custom bounds only after the assertion ran


def test_assert_in_canvas_docstring_notes_ordering_hazard():
    doc = assert_in_canvas.__doc__.lower()
    assert "order" in doc
    assert "canvas(" in doc
