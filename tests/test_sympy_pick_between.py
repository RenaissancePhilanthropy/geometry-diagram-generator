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
