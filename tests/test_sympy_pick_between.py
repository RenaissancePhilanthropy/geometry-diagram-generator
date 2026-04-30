"""Tests for PickBetween diagnostic messages in to_sympy."""
import pytest
from ir import ir
from ir.to_sympy import compile_defs


def _build_ir(define, checks=None):
    return ir.DiagramIR(
        canvas=ir.Canvas(),
        define=define,
        checks=checks or [],
        render=[],
    )


def test_pick_between_failure_mentions_outside_direction():
    """When intersection is outside [A,B], error message says 'beyond B' or 'before A'."""
    # Line AB is horizontal; line CD intersects the *extension* of AB beyond B.
    # A=(0,0), B=(2,0): segment from (0,0) to (2,0)
    # C=(3,1), D=(3,-1): vertical line x=3, intersects AB-extended at (3,0) → t=1.5
    defns = [
        ir.PointFixed(id="A", x=0, y=0),
        ir.PointFixed(id="B", x=2, y=0),
        ir.PointFixed(id="C", x=3, y=1),
        ir.PointFixed(id="D", x=3, y=-1),
        ir.LineThrough(id="line_AB", p="A", q="B"),
        ir.LineThrough(id="line_CD", p="C", q="D"),
        ir.PointIntersection(
            id="E",
            obj1="line_AB",
            obj2="line_CD",
            pick=ir.PickBetween(a="A", b="B"),
        ),
    ]
    diagram = _build_ir(defns)
    with pytest.raises(Exception, match="beyond 'B'"):
        compile_defs(diagram)


def test_pick_between_failure_before_a():
    """When intersection is before A (t < 0), error message says 'before A'."""
    # A=(2,0), B=(4,0): segment; vertical line at x=1 → t=-0.5
    defns = [
        ir.PointFixed(id="A", x=2, y=0),
        ir.PointFixed(id="B", x=4, y=0),
        ir.PointFixed(id="C", x=1, y=1),
        ir.PointFixed(id="D", x=1, y=-1),
        ir.LineThrough(id="line_AB", p="A", q="B"),
        ir.LineThrough(id="line_CD", p="C", q="D"),
        ir.PointIntersection(
            id="E",
            obj1="line_AB",
            obj2="line_CD",
            pick=ir.PickBetween(a="A", b="B"),
        ),
    ]
    diagram = _build_ir(defns)
    with pytest.raises(Exception, match="before 'A'"):
        compile_defs(diagram)


def test_pick_upper_of_line_error_includes_angle_and_distances():
    """PickUpperOfLine failure message includes directed angle and signed distances.

    Directed line A→B points east (angle 0°). The single intersection point
    is below the line (negative cross product), so PickUpperOfLine fails.
    Use two lines: vertical line x=2 crosses horizontal A→B at (2,0).
    Then ask for PickUpperOfLine on a *different* directed segment P→Q (pointing north)
    where the intersection point (2,0) has negative cross product.
    P=(2,-4), Q=(2,4) points north. PickUpperOfLine(P,Q) wants the point to the LEFT
    of P→Q (west side). The point (2,0) is exactly on the line, cross=0, not > 0.
    Instead: use a tilted directed line. D=(0,1)→C=(4,-1) tilts down-right.
    The intersection with vertical x=2 is at (2, 0). Cross of (C-D)×((2,0)-D):
    (4,-2)×(2,-1) = 4*(-1) - (-2)*2 = -4+4 = 0. Still on the line.
    Simplest: two circles intersecting, both intersection points on same side.
    Circles at (-1,0) r=2 and (1,0) r=2 intersect at (0, sqrt(3)) and (0,-sqrt(3)).
    PickUpperOfLine(A=(0,0),B=(2,0)): cross of (2,0)×(0,±sqrt(3)) - wait, using
    directed A→B east. Cross = (B-A)×(P-A) = (2,0)×(0,±√3) = 2*(±√3) - 0*0 = ±2√3.
    So (0,√3) is above, (0,-√3) is below. PickUpperOfLine succeeds here.
    For PickUpperOfLine to FAIL, both points must be below: reverse direction B→A.
    PickUpperOfLine(a="B", b="A") → directed west → left side = south.
    Points (0,√3) and (0,-√3): cross of (A-B)×(P-B) = (-2,0)×(-2,±√3):
    (-2)*(±√3) - 0*(-2) = ∓2√3. So (0,√3) → -2√3 < 0 (below), (0,-√3) → +2√3 > 0.
    Still one above. Need both below. Use PickUpperOfLine(a="A",b="B") with only
    below-the-line points. Put circle entirely below y=0 but tangent or intersecting
    a line at y=0 from below... Actually easiest: intersect two circles that only
    produce points with y < 0. Circle1: center (0,-3) r=2 → y in [-5,-1].
    Circle2: center (2,-3) r=2. Distance between centers = 2. Intersect at midpoint
    x=1, y = -3 ± sqrt(4-1) = -3 ± sqrt(3). Both y < 0.
    PickUpperOfLine(A=(0,0), B=(4,0)) → east → above = positive y. Both points y<0.
    """
    defns = [
        ir.PointFixed(id="A", x=0, y=0),
        ir.PointFixed(id="B", x=4, y=0),
        ir.PointFixed(id="O1", x=0, y=-3),
        ir.PointFixed(id="O2", x=2, y=-3),
        ir.CircleCenterRadius(id="c1", center="O1", radius=2),
        ir.CircleCenterRadius(id="c2", center="O2", radius=2),
        ir.PointIntersection(
            id="X",
            obj1="c1",
            obj2="c2",
            pick=ir.PickUpperOfLine(a="A", b="B"),
        ),
    ]
    diagram = _build_ir(defns)
    with pytest.raises(Exception) as exc_info:
        compile_defs(diagram)
    msg = str(exc_info.value)
    assert "above" in msg
    assert "directed angle" in msg
    assert "signed distances" in msg


def test_pick_lower_of_line_error_includes_angle_and_distances():
    """PickLowerOfLine failure message includes directed angle and signed distances.

    Horizontal directed line A→B pointing east. Circle above the x-axis whose
    two intersection points with another circle are both above y=0 (positive cross).
    PickLowerOfLine fails since no point has negative cross product.
    """
    defns = [
        ir.PointFixed(id="A", x=0, y=0),
        ir.PointFixed(id="B", x=4, y=0),
        ir.PointFixed(id="O1", x=0, y=3),
        ir.PointFixed(id="O2", x=2, y=3),
        ir.CircleCenterRadius(id="c1", center="O1", radius=2),
        ir.CircleCenterRadius(id="c2", center="O2", radius=2),
        ir.PointIntersection(
            id="X",
            obj1="c1",
            obj2="c2",
            pick=ir.PickLowerOfLine(a="A", b="B"),
        ),
    ]
    diagram = _build_ir(defns)
    with pytest.raises(Exception) as exc_info:
        compile_defs(diagram)
    msg = str(exc_info.value)
    assert "below" in msg
    assert "directed angle" in msg
    assert "signed distances" in msg


def test_pick_between_success_still_works():
    """Intersection inside [A,B] still compiles without error."""
    # A=(0,0), B=(4,0), vertical line at x=2 → t=0.5, inside [A,B]
    defns = [
        ir.PointFixed(id="A", x=0, y=0),
        ir.PointFixed(id="B", x=4, y=0),
        ir.PointFixed(id="C", x=2, y=1),
        ir.PointFixed(id="D", x=2, y=-1),
        ir.LineThrough(id="line_AB", p="A", q="B"),
        ir.LineThrough(id="line_CD", p="C", q="D"),
        ir.PointIntersection(
            id="E",
            obj1="line_AB",
            obj2="line_CD",
            pick=ir.PickBetween(a="A", b="B"),
        ),
    ]
    diagram = _build_ir(defns)
    sym = compile_defs(diagram)
    E = sym["E"]
    assert abs(float(E.x) - 2.0) < 1e-6
    assert abs(float(E.y) - 0.0) < 1e-6
