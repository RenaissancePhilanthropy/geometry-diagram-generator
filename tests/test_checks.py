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


# ---------------------------------------------------------------------------
# DistanceEquals checks
# ---------------------------------------------------------------------------

def test_distance_equals_passes_when_segment_has_expected_length():
    """DistanceEquals passes when the segment has the expected length."""
    import math
    from ir.ir import DistanceEquals, Segment, PointFixed, DiagramIR
    from ir.to_sympy import compile_defs

    sym = compile_defs(DiagramIR(define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=3, y=4),
        Segment(id="s", a="A", b="B"),
    ]))
    checks = [DistanceEquals(seg="s", expected=5.0)]
    results = run_checks(checks, sym)
    assert results[0].passed
    assert results[0].message == ""


def test_distance_equals_fails_when_segment_has_wrong_length():
    """DistanceEquals fails when the segment length differs from expected."""
    from ir.ir import DistanceEquals, Segment, PointFixed, DiagramIR
    from ir.to_sympy import compile_defs

    sym = compile_defs(DiagramIR(define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=3, y=4),
        Segment(id="s", a="A", b="B"),
    ]))
    checks = [DistanceEquals(seg="s", expected=10.0)]
    results = run_checks(checks, sym)
    assert not results[0].passed
    assert "s" in results[0].message


# ---------------------------------------------------------------------------
# Error reporting: traceback location should appear in the message
# ---------------------------------------------------------------------------

def test_check_error_includes_file_and_line_in_message(monkeypatch):
    """When a check body raises, the returned message should include the
    originating file:line of the failing frame so the strategy retry prompt
    (and human logs) can pinpoint the bug without rerunning with a debugger.

    Regression test for the altitude/parallel-marks scenario where we only
    had the bare 'Error in perpendicular: float has no attribute evalf'
    string and couldn't tell which check body actually failed.
    """
    import ir.checks as cm
    from ir.ir import Perpendicular, LineThrough, PointFixed, DiagramIR
    from ir.to_sympy import compile_defs

    def _raise(*_args, **_kwargs):
        raise ValueError("simulated failure for test")

    monkeypatch.setattr(cm, "_to_bool", _raise)

    sym = compile_defs(DiagramIR(define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=1, y=0),
        LineThrough(id="L1", p="A", q="B"),
        LineThrough(id="L2", p="A", q="B"),
    ]))
    checks = [Perpendicular(l1="L1", l2="L2")]
    results = run_checks(checks, sym)

    assert len(results) == 1
    assert not results[0].passed
    msg = results[0].message
    assert "Error in 'perpendicular'" in msg
    assert "simulated failure for test" in msg
    # New: location must be appended in the form "(at <file>:<line>)"
    import re
    m = re.search(r"\(at ([^:]+):(\d+)\)$", msg)
    assert m, f"expected trailing '(at <file>:<line>)' in message, got: {msg!r}"
    # The innermost frame is the monkey-patched _to_bool in this test file,
    # which is the correct location of the actual raise. In production this
    # will be a real check body inside ir/checks.py or one of its helpers.
