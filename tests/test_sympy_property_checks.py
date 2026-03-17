"""Tests for _check_sympy_property in evals/run.py.

Verifies flat-list arg format (as used in scenarios.yaml) works correctly for all check types.
"""

import math
import pytest

from evals.run import _check_sympy_property

TOL = 5e-3

# A right triangle: A=(0,0), B=(3,0), C=(3,4)
# Angle at B is 90 degrees (AB horizontal, BC vertical)
SYM_RIGHT_TRIANGLE = {
    "A": (0.0, 0.0),
    "B": (3.0, 0.0),
    "C": (3.0, 4.0),
}

# Collinear: A=(0,0), B=(1,0), C=(2,0)
SYM_COLLINEAR = {
    "A": (0.0, 0.0),
    "B": (1.0, 0.0),
    "C": (2.0, 0.0),
    "D": (0.0, 1.0),  # off the line
}

# Midpoint M of segment AB: A=(0,0), B=(4,0), M=(2,0)
SYM_MIDPOINT = {
    "A": (0.0, 0.0),
    "B": (4.0, 0.0),
    "M": (2.0, 0.0),
    "X": (1.5, 0.0),  # not the midpoint
}


class TestRightAngle:
    def test_right_angle_passes(self):
        # Angle ABC is 90 degrees: BA points left, BC points up
        passed, msg = _check_sympy_property("right_angle", ["A", "B", "C"], SYM_RIGHT_TRIANGLE, TOL)
        assert passed, f"Expected right angle at B to pass, got: {msg}"

    def test_right_angle_fails(self):
        # Angle BAC is not 90 degrees
        passed, msg = _check_sympy_property("right_angle", ["B", "A", "C"], SYM_RIGHT_TRIANGLE, TOL)
        assert not passed

    def test_right_angle_error_message_format(self):
        passed, msg = _check_sympy_property("right_angle", ["B", "A", "C"], SYM_RIGHT_TRIANGLE, TOL)
        assert not passed
        assert "°" in msg


class TestCollinear:
    def test_collinear_passes(self):
        passed, msg = _check_sympy_property("collinear", ["A", "B", "C"], SYM_COLLINEAR, TOL)
        assert passed, f"Expected A, B, C to be collinear, got: {msg}"

    def test_collinear_fails(self):
        passed, msg = _check_sympy_property("collinear", ["A", "B", "D"], SYM_COLLINEAR, TOL)
        assert not passed

    def test_collinear_error_message_contains_points(self):
        passed, msg = _check_sympy_property("collinear", ["A", "B", "D"], SYM_COLLINEAR, TOL)
        assert not passed
        assert "cross" in msg


class TestPointOnLine:
    def test_point_on_line_passes(self):
        # M=(2,0) lies on the line through A=(0,0) and B=(4,0)
        passed, msg = _check_sympy_property("point_on_line", ["M", "A", "B"], SYM_MIDPOINT, TOL)
        assert passed, f"Expected M on line AB to pass, got: {msg}"

    def test_point_on_line_fails(self):
        # D=(0,1) does not lie on the line through A=(0,0) and B=(4,0)
        sym = {**SYM_MIDPOINT, "D": (0.0, 1.0)}
        passed, msg = _check_sympy_property("point_on_line", ["D", "A", "B"], sym, TOL)
        assert not passed

    def test_point_on_segment_passes(self):
        passed, msg = _check_sympy_property("point_on_segment", ["M", "A", "B"], SYM_MIDPOINT, TOL)
        assert passed, f"Expected M on segment AB to pass, got: {msg}"

    def test_point_on_segment_fails(self):
        sym = {**SYM_MIDPOINT, "D": (0.0, 1.0)}
        passed, msg = _check_sympy_property("point_on_segment", ["D", "A", "B"], sym, TOL)
        assert not passed


class TestMidpoint:
    def test_midpoint_passes(self):
        passed, msg = _check_sympy_property("midpoint", ["M", "A", "B"], SYM_MIDPOINT, TOL)
        assert passed, f"Expected M to be midpoint of AB, got: {msg}"

    def test_midpoint_fails(self):
        passed, msg = _check_sympy_property("midpoint", ["X", "A", "B"], SYM_MIDPOINT, TOL)
        assert not passed


class TestEqualLengths:
    def test_equal_lengths_passes(self):
        # Equilateral triangle: A=(0,0), B=(1,0), C=(0.5, sqrt(3)/2)
        h = math.sqrt(3) / 2
        sym = {"A": (0.0, 0.0), "B": (1.0, 0.0), "C": (0.5, h)}
        passed, msg = _check_sympy_property("equal_lengths", [["A", "B"], ["B", "C"]], sym, TOL)
        assert passed, f"Expected |AB|=|BC|, got: {msg}"

    def test_equal_lengths_fails(self):
        sym = {"A": (0.0, 0.0), "B": (2.0, 0.0), "C": (0.5, 1.0)}
        passed, msg = _check_sympy_property("equal_lengths", [["A", "B"], ["B", "C"]], sym, TOL)
        assert not passed


class TestMissingPoint:
    def test_missing_point_raises(self):
        with pytest.raises(KeyError, match="not in symbol table"):
            _check_sympy_property("right_angle", ["A", "Z", "C"], SYM_RIGHT_TRIANGLE, TOL)
