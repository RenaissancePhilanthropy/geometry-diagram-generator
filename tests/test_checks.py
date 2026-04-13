# tests/test_checks.py
"""Tests for ir/checks.py."""
import sympy.geometry as spg

from ir.ir import AngleEqual, AnglePoints
from ir.checks import run_checks


def test_angle_equal_failure_shows_candidates():
    """AngleEqual failure message includes candidate angles at each vertex."""
    # Right triangle: A=(0,0), B=(3,0), C=(0,4)
    # D=(3,1) added so that angle A-B-D at B equals 90°, providing a candidate hint
    sym = {
        "A": spg.Point2D(0, 0),
        "B": spg.Point2D(3, 0),
        "C": spg.Point2D(0, 4),
        "D": spg.Point2D(3, 1),
    }
    # Angle A-B-C (at B) ≈ 53.1°, angle B-A-C (at A) = 90°
    # False check: claim angle A-B-C equals angle B-A-C (they differ)
    checks = [AngleEqual(
        a1=AnglePoints(a="A", o="B", b="C"),
        a2=AnglePoints(a="B", o="A", b="C"),
        source="test",
    )]
    results = run_checks(checks, sym)
    assert len(results) == 1
    assert not results[0].passed
    msg = results[0].message
    # Should contain both angle values
    assert "53" in msg or "36" in msg
    assert "90" in msg
    # Should contain candidate suggestions (A-B-D at B = 90°)
    assert "try:" in msg


def test_angle_equal_pass_produces_empty_message():
    """AngleEqual pass leaves message empty."""
    # Isosceles triangle: A=(0,0), B=(4,0), C=(2,3)
    sym = {
        "A": spg.Point2D(0, 0),
        "B": spg.Point2D(4, 0),
        "C": spg.Point2D(2, 3),
    }
    # Angle C-A-B equals angle C-B-A for an isosceles triangle
    checks = [AngleEqual(
        a1=AnglePoints(a="C", o="A", b="B"),
        a2=AnglePoints(a="C", o="B", b="A"),
        source="test",
    )]
    results = run_checks(checks, sym)
    assert len(results) == 1
    assert results[0].passed
    assert results[0].message == ""


def test_contains_ellipse_point_on_boundary():
    """Contains check passes for a point on the ellipse boundary."""
    import math
    from ir.ir import Contains, PointFixed, EllipseCenterAxes, DiagramIR
    from ir.to_sympy import compile_defs

    # Ellipse centered at (1,3), hradius=1.5, vradius=2
    # Point at (1 + 1.5, 3) = (2.5, 3) is on the boundary
    sym = compile_defs(DiagramIR(define=[
        PointFixed(id="O", x=1, y=3),
        EllipseCenterAxes(id="E", center="O", hradius=1.5, vradius=2),
        PointFixed(id="P", x=2.5, y=3),
    ]))
    checks = [Contains(obj="E", p="P")]
    results = run_checks(checks, sym)
    assert results[0].passed


def test_contains_ellipse_point_outside():
    """Contains check fails for a point clearly outside the ellipse."""
    from ir.ir import Contains, PointFixed, EllipseCenterAxes, DiagramIR
    from ir.to_sympy import compile_defs

    sym = compile_defs(DiagramIR(define=[
        PointFixed(id="O", x=0, y=0),
        EllipseCenterAxes(id="E", center="O", hradius=1.5, vradius=2),
        PointFixed(id="P", x=5, y=5),
    ]))
    checks = [Contains(obj="E", p="P")]
    results = run_checks(checks, sym)
    assert not results[0].passed
