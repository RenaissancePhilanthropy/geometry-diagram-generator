# tests/test_checks.py
"""Tests for ir/checks.py."""
import sympy.geometry as spg

from geometry_diagrams.ir.ir import AngleEqual, AnglePoints
from geometry_diagrams.ir.checks import run_checks, _check_one, DEFAULT_TOL


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
    from geometry_diagrams.ir.ir import Contains, PointFixed, EllipseCenterAxes, DiagramIR
    from geometry_diagrams.ir.to_sympy import compile_defs

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
    from geometry_diagrams.ir.ir import Contains, PointFixed, EllipseCenterAxes, DiagramIR
    from geometry_diagrams.ir.to_sympy import compile_defs

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
    from geometry_diagrams.ir.ir import DistanceEquals, Segment, PointFixed, DiagramIR
    from geometry_diagrams.ir.to_sympy import compile_defs

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
    from geometry_diagrams.ir.ir import DistanceEquals, Segment, PointFixed, DiagramIR
    from geometry_diagrams.ir.to_sympy import compile_defs

    sym = compile_defs(DiagramIR(define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=3, y=4),
        Segment(id="s", a="A", b="B"),
    ]))
    checks = [DistanceEquals(seg="s", expected=10.0)]
    results = run_checks(checks, sym)
    assert not results[0].passed
    assert "s" in results[0].message


def test_centroid_passes_for_average_of_vertices():
    """Centroid check passes when g is exactly the average of A, B, C."""
    sym = {
        "A": spg.Point2D(0, 0),
        "B": spg.Point2D(6, 0),
        "C": spg.Point2D(0, 6),
        "G": spg.Point2D(2, 2),
    }
    from geometry_diagrams.ir.ir import Centroid

    checks = [Centroid(g="G", a="A", b="B", c="C")]
    results = run_checks(checks, sym)
    assert results[0].passed
    assert results[0].message == ""


def test_centroid_fails_when_offset():
    """Centroid check fails when g is meaningfully off the (A+B+C)/3 point."""
    sym = {
        "A": spg.Point2D(0, 0),
        "B": spg.Point2D(6, 0),
        "C": spg.Point2D(0, 6),
        "G": spg.Point2D(3, 2),
    }
    from geometry_diagrams.ir.ir import Centroid

    checks = [Centroid(g="G", a="A", b="B", c="C")]
    results = run_checks(checks, sym)
    assert not results[0].passed
    assert "centroid" in results[0].message.lower()
    assert "2.0000" in results[0].message  # expected x = (0+6+0)/3 = 2


def test_centroid_irrational_equilateral():
    """Centroid passes for an equilateral triangle whose centroid has irrational coords."""
    import math

    sym = {
        "A": spg.Point2D(0, 0),
        "B": spg.Point2D(1, 0),
        "C": spg.Point2D(0.5, math.sqrt(3) / 2),
        "G": spg.Point2D(0.5, math.sqrt(3) / 6),
    }
    from geometry_diagrams.ir.ir import Centroid

    checks = [Centroid(g="G", a="A", b="B", c="C")]
    results = run_checks(checks, sym)
    assert results[0].passed


# ---------------------------------------------------------------------------
# Convex checks
# ---------------------------------------------------------------------------

def test_convex_passes_for_convex_polygon():
    """Convex check passes for a square (convex quadrilateral)."""
    from geometry_diagrams.ir.ir import Convex

    sym = {
        "sq": spg.Polygon(
            spg.Point2D(0, 0), spg.Point2D(4, 0), spg.Point2D(4, 4), spg.Point2D(0, 4)
        ),
    }
    check = Convex(polygon="sq")
    result = _check_one(check, sym, DEFAULT_TOL)
    assert result.passed
    assert result.message == ""


def test_convex_fails_for_non_convex_polygon():
    """Convex check fails for a non-convex (dart-shaped) polygon."""
    from geometry_diagrams.ir.ir import Convex

    sym = {
        # Dart shape: a reflex vertex at (2, 1) pulls the quadrilateral inward.
        "dart": spg.Polygon(
            spg.Point2D(0, 0), spg.Point2D(4, 0), spg.Point2D(2, 1), spg.Point2D(4, 4)
        ),
    }
    check = Convex(polygon="dart")
    result = _check_one(check, sym, DEFAULT_TOL)
    assert not result.passed
    assert "dart" in result.message
    assert "convex" in result.message.lower()


# ---------------------------------------------------------------------------
# CCW checks
# ---------------------------------------------------------------------------

def test_ccw_passes_for_counterclockwise_polygon():
    """CCW check passes for vertices wound counter-clockwise."""
    from geometry_diagrams.ir.ir import CCW

    sym = {
        "sq": spg.Polygon(
            spg.Point2D(0, 0), spg.Point2D(4, 0), spg.Point2D(4, 4), spg.Point2D(0, 4)
        ),
    }
    check = CCW(polygon="sq")
    result = _check_one(check, sym, DEFAULT_TOL)
    assert result.passed
    assert result.message == ""


def test_ccw_fails_for_clockwise_polygon():
    """CCW check fails for vertices wound clockwise."""
    from geometry_diagrams.ir.ir import CCW

    sym = {
        "sq": spg.Polygon(
            spg.Point2D(0, 0), spg.Point2D(0, 4), spg.Point2D(4, 4), spg.Point2D(4, 0)
        ),
    }
    check = CCW(polygon="sq")
    result = _check_one(check, sym, DEFAULT_TOL)
    assert not result.passed
    assert "sq" in result.message


# ---------------------------------------------------------------------------
# MinDistance checks
# ---------------------------------------------------------------------------

def test_min_distance_passes_when_far_enough():
    """MinDistance check passes when points are at least min_dist apart."""
    from geometry_diagrams.ir.ir import MinDistance

    sym = {
        "A": spg.Point2D(0, 0),
        "B": spg.Point2D(3, 4),  # distance 5
    }
    check = MinDistance(a="A", b="B", min_dist=5.0)
    result = _check_one(check, sym, DEFAULT_TOL)
    assert result.passed
    assert result.message == ""


def test_min_distance_fails_when_too_close():
    """MinDistance check fails when points are strictly closer than min_dist."""
    from geometry_diagrams.ir.ir import MinDistance

    sym = {
        "A": spg.Point2D(0, 0),
        "B": spg.Point2D(3, 4),  # distance 5
    }
    check = MinDistance(a="A", b="B", min_dist=6.0)
    result = _check_one(check, sym, DEFAULT_TOL)
    assert not result.passed
    assert "A" in result.message and "B" in result.message


# ---------------------------------------------------------------------------
# CongruentTriangles checks
# ---------------------------------------------------------------------------

def test_congruent_triangles_passes_correspondence_independent():
    """CongruentTriangles passes on matching sorted side lengths, different vertex order.

    Triangle 1 has sides (3, 4, 5). Triangle 2 is a rigid translation with vertices
    listed in a different order — proving SSS matching is correspondence-independent.
    """
    from geometry_diagrams.ir.ir import CongruentTriangles

    sym = {
        "T1": spg.Triangle(spg.Point2D(0, 0), spg.Point2D(4, 0), spg.Point2D(0, 3)),
        # Same triangle shape, translated, vertices listed in a different rotational order.
        "T2": spg.Triangle(spg.Point2D(10, 3), spg.Point2D(10, 0), spg.Point2D(14, 0)),
    }
    check = CongruentTriangles(t1="T1", t2="T2")
    result = _check_one(check, sym, DEFAULT_TOL)
    assert result.passed
    assert result.message == ""


def test_congruent_triangles_fails_for_different_size():
    """CongruentTriangles fails when side lengths don't match."""
    from geometry_diagrams.ir.ir import CongruentTriangles

    sym = {
        "T1": spg.Triangle(spg.Point2D(0, 0), spg.Point2D(4, 0), spg.Point2D(0, 3)),
        "T2": spg.Triangle(spg.Point2D(0, 0), spg.Point2D(8, 0), spg.Point2D(0, 6)),
    }
    check = CongruentTriangles(t1="T1", t2="T2")
    result = _check_one(check, sym, DEFAULT_TOL)
    assert not result.passed
    assert "T1" in result.message or "congruent" in result.message.lower()


def test_congruent_triangles_distinguishes_from_similar():
    """Same angles, different scale: SimilarTriangles passes but CongruentTriangles fails."""
    from geometry_diagrams.ir.ir import CongruentTriangles, SimilarTriangles

    sym = {
        "T1": spg.Triangle(spg.Point2D(0, 0), spg.Point2D(4, 0), spg.Point2D(0, 3)),
        # Same angles (scaled 2x) — similar, but not congruent.
        "T2": spg.Triangle(spg.Point2D(0, 0), spg.Point2D(8, 0), spg.Point2D(0, 6)),
    }
    similar_result = _check_one(SimilarTriangles(t1="T1", t2="T2"), sym, DEFAULT_TOL)
    congruent_result = _check_one(CongruentTriangles(t1="T1", t2="T2"), sym, DEFAULT_TOL)
    assert similar_result.passed
    assert not congruent_result.passed
