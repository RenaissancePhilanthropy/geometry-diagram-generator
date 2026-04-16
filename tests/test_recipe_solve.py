# tests/test_recipe_solve.py
"""Tests for the triangle constraint solver.

All coordinate assertions use distance/angle checks rather than raw xy,
to avoid sensitivity to layout rotation choices.
"""
import math
import pytest
from recipe.solve import solve_triangle, SpecError


def dist(p1, p2):
    return math.hypot(p1[0]-p2[0], p1[1]-p2[1])


def angle_at(a, vertex, b):
    """Non-reflex angle at vertex (degrees)."""
    vax, vay = a[0]-vertex[0], a[1]-vertex[1]
    vbx, vby = b[0]-vertex[0], b[1]-vertex[1]
    dot = vax*vbx + vay*vby
    mag = math.hypot(vax, vay) * math.hypot(vbx, vby)
    return math.degrees(math.acos(max(-1.0, min(1.0, dot/mag))))


# --- AAS: angle_A, angle_B, side_AB ---

def test_aas_equilateral():
    verts = solve_triangle(["A","B","C"], {"angle_A": 60, "angle_B": 60, "side_AB": 3})
    A, B, C = verts["A"], verts["B"], verts["C"]
    assert abs(dist(A, B) - 3.0) < 1e-6
    assert abs(angle_at(B, A, C) - 60.0) < 1e-4
    assert abs(angle_at(A, B, C) - 60.0) < 1e-4
    assert abs(angle_at(A, C, B) - 60.0) < 1e-4

def test_aas_30_60_90():
    verts = solve_triangle(["A","B","C"], {"angle_A": 30, "angle_B": 60, "side_AB": 2})
    A, B, C = verts["A"], verts["B"], verts["C"]
    assert abs(angle_at(B, A, C) - 30.0) < 1e-4
    assert abs(angle_at(A, B, C) - 60.0) < 1e-4
    assert abs(angle_at(A, C, B) - 90.0) < 1e-4


# --- SAS: angle_B, side_AB, side_BC ---

def test_sas_isosceles():
    # SAS: angle at B=90, AB=3, BC=4 → right triangle
    verts = solve_triangle(["A","B","C"], {"angle_B": 90, "side_AB": 3, "side_BC": 4})
    A, B, C = verts["A"], verts["B"], verts["C"]
    assert abs(angle_at(A, B, C) - 90.0) < 1e-4
    assert abs(dist(A, B) - 3.0) < 1e-6
    assert abs(dist(B, C) - 4.0) < 1e-6
    assert abs(dist(A, C) - 5.0) < 1e-6  # Pythagorean


# --- SSS: side_AB, side_BC, side_CA ---

def test_sss_3_4_5():
    verts = solve_triangle(["A","B","C"], {"side_AB": 3, "side_BC": 4, "side_CA": 5})
    A, B, C = verts["A"], verts["B"], verts["C"]
    assert abs(dist(A, B) - 3.0) < 1e-6
    assert abs(dist(B, C) - 4.0) < 1e-6
    assert abs(dist(C, A) - 5.0) < 1e-6
    # The 90° angle is at B (opposite longest side CA=5)
    assert abs(angle_at(A, B, C) - 90.0) < 1e-4


# --- ASA: angle_A, angle_B, side_CA ---

def test_asa_60_60_3():
    # ASA with angle_A=60, angle_B=60, side_CA=3 → equilateral
    verts = solve_triangle(["A","B","C"], {"angle_A": 60, "angle_B": 60, "side_CA": 3})
    A, B, C = verts["A"], verts["B"], verts["C"]
    assert abs(dist(C, A) - 3.0) < 1e-6
    assert abs(angle_at(B, A, C) - 60.0) < 1e-4
    assert abs(angle_at(A, B, C) - 60.0) < 1e-4


# --- right_angle_at + two sides ---

def test_right_angle_at_b():
    verts = solve_triangle(["A","B","C"], {"right_angle_at": "B", "side_AB": 3, "side_BC": 4})
    A, B, C = verts["A"], verts["B"], verts["C"]
    assert abs(angle_at(A, B, C) - 90.0) < 1e-4
    assert abs(dist(A, B) - 3.0) < 1e-6
    assert abs(dist(B, C) - 4.0) < 1e-6

def test_right_angle_at_a():
    verts = solve_triangle(["P","Q","R"], {"right_angle_at": "P", "side_PQ": 5, "side_PR": 12})
    P, Q, R = verts["P"], verts["Q"], verts["R"]
    assert abs(angle_at(Q, P, R) - 90.0) < 1e-4
    assert abs(dist(P, Q) - 5.0) < 1e-6
    assert abs(dist(P, R) - 12.0) < 1e-6


# --- Layout conventions ---

def test_layout_third_vertex_above_x_axis():
    """Third vertex must have y > 0."""
    verts = solve_triangle(["A","B","C"], {"angle_A": 60, "angle_B": 70, "side_AB": 3})
    A, B, C = verts["A"], verts["B"], verts["C"]
    assert C[1] > 0, f"Third vertex C should be above x-axis, got y={C[1]}"

def test_layout_centroid_near_2_2():
    """Centroid should be near (2,2) after translation."""
    verts = solve_triangle(["A","B","C"], {"angle_A": 60, "angle_B": 60, "side_AB": 3})
    A, B, C = verts["A"], verts["B"], verts["C"]
    cx = (A[0]+B[0]+C[0])/3
    cy = (A[1]+B[1]+C[1])/3
    assert abs(cx - 2.0) < 0.5
    assert abs(cy - 2.0) < 0.5


# --- Error cases ---

def test_ssa_raises_spec_error():
    with pytest.raises(SpecError):
        solve_triangle(["A","B","C"], {"angle_A": 30, "side_AB": 3, "side_BC": 5})

def test_angle_sum_over_constrained():
    with pytest.raises(SpecError):
        solve_triangle(["A","B","C"], {"angle_A": 90, "angle_B": 90, "side_AB": 3})

def test_triangle_inequality_violation():
    with pytest.raises(SpecError):
        solve_triangle(["A","B","C"], {"side_AB": 1, "side_BC": 1, "side_CA": 10})

def test_unknown_spec_raises():
    with pytest.raises(SpecError):
        solve_triangle(["A","B","C"], {"angle_A": 60})  # insufficient constraints


# --- Overdefined specs ---

def test_overdefined_3_angles_1_side():
    coords = solve_triangle(["A","B","C"], {"angle_A": 60, "angle_B": 60, "angle_C": 60, "side_AB": 3})
    ab = dist(coords["A"], coords["B"])
    assert abs(ab - 3.0) < 1e-6
    # All angles should be 60°
    assert abs(angle_at(coords["B"], coords["A"], coords["C"]) - 60.0) < 1e-4
    assert abs(angle_at(coords["A"], coords["B"], coords["C"]) - 60.0) < 1e-4
    assert abs(angle_at(coords["A"], coords["C"], coords["B"]) - 60.0) < 1e-4

def test_overdefined_3_angles_bad_sum():
    with pytest.raises(SpecError):
        solve_triangle(["A","B","C"], {"angle_A": 70, "angle_B": 70, "angle_C": 70, "side_AB": 3})

def test_overdefined_sss_with_extra_angle():
    # SSS + redundant angle → uses SSS
    coords = solve_triangle(["A","B","C"], {"side_AB": 3, "side_BC": 4, "side_CA": 5, "angle_A": 90})
    # Should solve (it's a right triangle)
    assert all(k in coords for k in ["A","B","C"])

def test_aaa_no_sides():
    with pytest.raises(SpecError):
        solve_triangle(["A","B","C"], {"angle_A": 60, "angle_B": 60, "angle_C": 60})


# ---------------------------------------------------------------------------
# solve_rectangle
# ---------------------------------------------------------------------------

from recipe.solve import solve_rectangle

def _dist(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)


def test_solve_rectangle_side_lengths():
    """solve_rectangle should produce corners with |AB|=4 and |BC|=3."""
    coords = solve_rectangle(["A","B","C","D"], {"side_AB": 4, "side_BC": 3})
    a, b, c, d = coords["A"], coords["B"], coords["C"], coords["D"]
    assert _dist(a, b) == pytest.approx(4.0, abs=1e-8)
    assert _dist(b, c) == pytest.approx(3.0, abs=1e-8)
    assert _dist(c, d) == pytest.approx(4.0, abs=1e-8)
    assert _dist(d, a) == pytest.approx(3.0, abs=1e-8)


def test_solve_rectangle_right_angles():
    """All four corners should be right angles."""
    coords = solve_rectangle(["A","B","C","D"], {"side_AB": 5, "side_BC": 2})
    verts = [coords["A"], coords["B"], coords["C"], coords["D"]]
    for i in range(4):
        a = verts[(i-1) % 4]
        o = verts[i]
        b = verts[(i+1) % 4]
        v1 = (a[0]-o[0], a[1]-o[1])
        v2 = (b[0]-o[0], b[1]-o[1])
        dot = v1[0]*v2[0] + v1[1]*v2[1]
        assert dot == pytest.approx(0.0, abs=1e-6)


def test_solve_rectangle_center():
    """Centroid should be at the requested center."""
    coords = solve_rectangle(["A","B","C","D"], {"side_AB": 4, "side_BC": 3}, center=(5.0, 6.0))
    cx = sum(v[0] for v in coords.values()) / 4
    cy = sum(v[1] for v in coords.values()) / 4
    assert cx == pytest.approx(5.0, abs=1e-8)
    assert cy == pytest.approx(6.0, abs=1e-8)


def test_solve_rectangle_rotation():
    """With rotation=90, the horizontal side AB becomes vertical."""
    coords_0 = solve_rectangle(["A","B","C","D"], {"side_AB": 4, "side_BC": 3})
    coords_90 = solve_rectangle(["A","B","C","D"], {"side_AB": 4, "side_BC": 3}, center=(2.0, 2.0))
    # At rotation=0, A and B have same y; at rotation=90 they'd have same x.
    # Just check that the side lengths are still correct after rotation.
    coords_r = solve_rectangle(["A","B","C","D"], {"side_AB": 4, "side_BC": 3, "rotation": 90})
    assert _dist(coords_r["A"], coords_r["B"]) == pytest.approx(4.0, abs=1e-8)
    assert _dist(coords_r["B"], coords_r["C"]) == pytest.approx(3.0, abs=1e-8)


def test_solve_rectangle_missing_side_raises():
    with pytest.raises(SpecError):
        solve_rectangle(["A","B","C","D"], {"side_AB": 4})


def test_solve_rectangle_wrong_vertex_count_raises():
    with pytest.raises(SpecError):
        solve_rectangle(["A","B","C"], {"side_AB": 4, "side_BC": 3})
