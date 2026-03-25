# tests/test_recipe_apply_pick.py
import pytest
import sympy as sp
import sympy.geometry as spg
from ir.to_sympy import _apply_pick
from ir.ir import (
    PickBetween, PickBeyond, PickInterior, PickExterior,
    PickOppositeSide, PickUpperOfLine, PickLowerOfLine, PickChain,
    PickClosestTo,
)
from ir.errors import PickError

# Candidate points
O  = spg.Point(0, 0)
A  = spg.Point(4, 0)
B  = spg.Point(2, 0)   # between O and A
C  = spg.Point(6, 0)   # beyond A from O
HI = spg.Point(2, 3)   # above x-axis
LO = spg.Point(2, -3)  # below x-axis

SYM = {"O": O, "A": A, "B": B, "C": C, "Hi": HI, "Lo": LO}

# Simple square polygon for interior/exterior tests
POLY = spg.Polygon(spg.Point(0,0), spg.Point(4,0), spg.Point(4,4), spg.Point(0,4))
SYM2 = {**SYM, "sq": POLY}


def test_pick_between_selects_midpoint():
    # B(2,0) lies on segment O(0,0)-A(4,0)
    result = _apply_pick([B, C], PickBetween(a="O", b="A"), SYM, "test")
    assert result == B

def test_pick_between_rejects_exterior():
    # C(6,0) is NOT between O and A — only C in candidates, should raise
    with pytest.raises(PickError):
        _apply_pick([C], PickBetween(a="O", b="A"), SYM, "test")

def test_pick_beyond_selects_far_side():
    # Beyond A(4,0) from O(0,0): C(6,0) is on far side; B(2,0) is between
    result = _apply_pick([B, C], PickBeyond(from_point="O", past_point="A"), SYM, "test")
    assert result == C

def test_pick_interior_selects_inside():
    inside = spg.Point(2, 2)
    outside = spg.Point(5, 5)
    sym3 = {**SYM2, "inside": inside, "outside": outside}
    result = _apply_pick([inside, outside], PickInterior(polygon="sq"), sym3, "test")
    assert result == inside

def test_pick_exterior_selects_outside():
    inside = spg.Point(2, 2)
    outside = spg.Point(5, 5)
    sym3 = {**SYM2, "inside": inside, "outside": outside}
    result = _apply_pick([inside, outside], PickExterior(polygon="sq"), sym3, "test")
    assert result == outside

def test_pick_opposite_side():
    # Line is x-axis (O→A). Hi(2,3) is above, Lo(2,-3) is below.
    # ref_point is Hi → opposite side is Lo
    result = _apply_pick([HI, LO], PickOppositeSide(line_through=["O", "A"], ref_point="Hi"), SYM, "test")
    assert result == LO

def test_pick_upper_of_line():
    # Upper = above O→A (positive cross-product = positive y side)
    result = _apply_pick([HI, LO], PickUpperOfLine(a="O", b="A"), SYM, "test")
    assert result == HI

def test_pick_lower_of_line():
    # Lower = below O→A (negative cross-product = negative y side)
    result = _apply_pick([HI, LO], PickLowerOfLine(a="O", b="A"), SYM, "test")
    assert result == LO

def test_pick_chain_applies_rules_in_order():
    # First filter: upper of x-axis → Hi; second filter: closest to (3,3)
    near = spg.Point(3, 3)
    far  = spg.Point(3, 10)
    sym4 = {**SYM, "near": near, "far": far}
    chain = PickChain(rules=[
        PickUpperOfLine(a="O", b="A"),
        PickClosestTo(p="near"),
    ])
    result = _apply_pick([HI, LO, near, far], chain, sym4, "test")
    assert result == near  # near(3,3) is above x-axis and closest to (3,3)

def test_pick_chain_no_candidates_raises():
    # Chain that eliminates all candidates
    chain = PickChain(rules=[
        PickBetween(a="O", b="A"),   # B(2,0) passes
        PickUpperOfLine(a="O", b="A"),  # B is on x-axis, not strictly above → raises
    ])
    with pytest.raises(PickError):
        _apply_pick([B], chain, SYM, "test")
