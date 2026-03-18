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


# ---------------------------------------------------------------------------
# New check types (Phase 1 + 2)
# ---------------------------------------------------------------------------

# Circle: center O=(0,0), radius 5, so A=(5,0), B=(0,5), C=(3,4) all on circle
SYM_CIRCLE = {
    "O": (0.0, 0.0),
    "A": (5.0, 0.0),  # on circle
    "B": (0.0, 5.0),  # on circle
    "C": (3.0, 4.0),  # on circle (3^2+4^2=25)
    "P": (1.0, 1.0),  # inside circle, not on it
}

# Tangent: circle center O=(0,0) radius 5, tangent at T=(5,0), line is vertical x=5
SYM_TANGENT = {
    "O": (0.0, 0.0),
    "T": (5.0, 0.0),  # tangent point on circle
    "L1": (5.0, -3.0),  # on tangent line x=5
    "L2": (5.0, 3.0),   # on tangent line x=5
    "L_bad1": (0.0, -3.0),  # on non-tangent line through circle
    "L_bad2": (0.0, 3.0),
}

# Angle bisector: A at origin, B and C equidistant on rays at +30 and -30 degrees
# The bisector ray goes along x-axis (0 degrees), so D=(1,0) is on bisector
_r = 4.0
_ang = math.radians(30)
SYM_BISECTOR = {
    "A": (0.0, 0.0),
    "B": (_r * math.cos(_ang), _r * math.sin(_ang)),   # 30 degrees from x-axis
    "C": (_r * math.cos(-_ang), _r * math.sin(-_ang)), # -30 degrees from x-axis
    "D": (2.0, 0.0),   # on the bisector (x-axis)
    "D_bad": (2.0, 1.0),  # off bisector
}

# Equidistant: incenter of 3-4-5 right triangle A=(0,0), B=(4,0), C=(0,3)
# Inradius r = (a+b-c)/2 = (4+3-5)/2 = 1, incenter = (1, 1)
SYM_INCIRCLE = {
    "A": (0.0, 0.0),
    "B": (4.0, 0.0),
    "C": (0.0, 3.0),
    "I": (1.0, 1.0),      # correct incenter
    "I_bad": (2.0, 0.5),  # wrong
}

# Centroid
SYM_CENTROID = {
    "A": (0.0, 0.0),
    "B": (6.0, 0.0),
    "C": (0.0, 6.0),
    "G": (2.0, 2.0),       # correct centroid
    "G_bad": (3.0, 3.0),   # wrong
}

# Sidedness: points relative to line AB along x-axis
# A=(0,0), B=(4,0) — line is x-axis
# P=(1,1) above, Q=(2,-1) below → opposite sides
# R=(3,2) above → same side as P
SYM_SIDES = {
    "A": (0.0, 0.0),
    "B": (4.0, 0.0),
    "P": (1.0, 1.0),   # above x-axis
    "Q": (2.0, -1.0),  # below x-axis
    "R": (3.0, 2.0),   # above x-axis (same side as P)
}

# Not-between: B=(0,0), C=(4,0), D=(6,0) is beyond C (not between)
SYM_BETWEEN = {
    "B": (0.0, 0.0),
    "C": (4.0, 0.0),
    "D": (6.0, 0.0),   # beyond C, not between
    "M": (2.0, 0.0),   # midpoint, is between
}


class TestPointOnCircle:
    def test_point_on_circle_passes(self):
        passed, msg = _check_sympy_property("point_on_circle", ["A", "O", "B"], SYM_CIRCLE, TOL)
        assert passed, f"Expected A on circle, got: {msg}"

    def test_point_on_circle_third_point_on_circle(self):
        # C=(3,4) is also on the circle
        passed, msg = _check_sympy_property("point_on_circle", ["C", "O", "A"], SYM_CIRCLE, TOL)
        assert passed, f"Expected C on circle, got: {msg}"

    def test_point_not_on_circle_fails(self):
        passed, msg = _check_sympy_property("point_on_circle", ["P", "O", "A"], SYM_CIRCLE, TOL)
        assert not passed


class TestTangent:
    def test_tangent_passes(self):
        # Vertical line at x=5 is tangent to unit circle at T=(5,0)
        passed, msg = _check_sympy_property("tangent", [["L1", "L2"], "O", "T"], SYM_TANGENT, TOL)
        assert passed, f"Expected tangent to pass, got: {msg}"

    def test_non_tangent_fails(self):
        # Vertical line through origin is not tangent — it passes through center
        passed, msg = _check_sympy_property("tangent", [["L_bad1", "L_bad2"], "O", "T"], SYM_TANGENT, TOL)
        assert not passed


class TestAngleBisector:
    def test_angle_bisector_passes(self):
        passed, msg = _check_sympy_property("angle_bisector", ["D", "A", "B", "C"], SYM_BISECTOR, TOL)
        assert passed, f"Expected D on bisector, got: {msg}"

    def test_angle_bisector_fails(self):
        passed, msg = _check_sympy_property("angle_bisector", ["D_bad", "A", "B", "C"], SYM_BISECTOR, TOL)
        assert not passed


class TestIntersects:
    def test_intersects_passes(self):
        # P=(2,1) should be at intersection of line AB (y=x/2) and CD (y=1 horizontal)
        sym = {
            "A": (0.0, 0.0), "B": (4.0, 2.0),  # line: y = x/2
            "C": (0.0, 1.0), "D": (4.0, 1.0),  # horizontal y=1
            "P": (2.0, 1.0),  # intersection
        }
        passed, msg = _check_sympy_property("intersects", [["A", "B"], ["C", "D"], "P"], sym, TOL)
        assert passed, f"Expected P at intersection, got: {msg}"

    def test_intersects_fails(self):
        sym = {
            "A": (0.0, 0.0), "B": (4.0, 0.0),
            "C": (0.0, 1.0), "D": (4.0, 1.0),
            "P": (2.0, 0.5),  # not on either line
        }
        passed, msg = _check_sympy_property("intersects", [["A", "B"], ["C", "D"], "P"], sym, TOL)
        assert not passed


class TestEquidistantFromSides:
    def test_equidistant_passes(self):
        passed, msg = _check_sympy_property(
            "equidistant_from_sides", ["I", "A", "B", "C"], SYM_INCIRCLE, TOL
        )
        assert passed, f"Expected I equidistant from sides, got: {msg}"

    def test_equidistant_fails(self):
        passed, msg = _check_sympy_property(
            "equidistant_from_sides", ["I_bad", "A", "B", "C"], SYM_INCIRCLE, TOL
        )
        assert not passed


class TestCentroid:
    def test_centroid_passes(self):
        passed, msg = _check_sympy_property("centroid", ["G", "A", "B", "C"], SYM_CENTROID, TOL)
        assert passed, f"Expected G at centroid, got: {msg}"

    def test_centroid_fails(self):
        passed, msg = _check_sympy_property("centroid", ["G_bad", "A", "B", "C"], SYM_CENTROID, TOL)
        assert not passed


class TestOppositeSide:
    def test_opposite_side_passes(self):
        passed, msg = _check_sympy_property("opposite_side", ["P", "Q", "A", "B"], SYM_SIDES, TOL)
        assert passed, f"Expected P and Q on opposite sides, got: {msg}"

    def test_opposite_side_fails_same_side(self):
        # P and R are both above x-axis
        passed, msg = _check_sympy_property("opposite_side", ["P", "R", "A", "B"], SYM_SIDES, TOL)
        assert not passed


class TestSameSide:
    def test_same_side_passes(self):
        # P and R both above x-axis
        passed, msg = _check_sympy_property("same_side", ["P", "R", "A", "B"], SYM_SIDES, TOL)
        assert passed, f"Expected P and R on same side, got: {msg}"

    def test_same_side_fails_opposite_side(self):
        # P above, Q below
        passed, msg = _check_sympy_property("same_side", ["P", "Q", "A", "B"], SYM_SIDES, TOL)
        assert not passed


class TestNotBetween:
    def test_not_between_passes(self):
        # D=(6,0) is beyond C=(4,0), not between B=(0,0) and C=(4,0)
        passed, msg = _check_sympy_property("not_between", ["D", "B", "C"], SYM_BETWEEN, TOL)
        assert passed, f"Expected D not between B and C, got: {msg}"

    def test_not_between_fails_when_between(self):
        # M=(2,0) is between B=(0,0) and C=(4,0)
        passed, msg = _check_sympy_property("not_between", ["M", "B", "C"], SYM_BETWEEN, TOL)
        assert not passed
