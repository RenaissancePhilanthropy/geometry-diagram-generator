"""Regression test: is_parallel with float-coordinate segments (Math_52 case)."""
import math
import sympy.geometry as spg
from ir.checks import _is_parallel


def test_parallel_float_coords_turtle_walk():
    """Float coords from turtle walk should be detected as parallel even if SymPy's
    symbolic is_parallel returns False due to rational approximation mismatch."""
    # Parallelogram ADCB from polygon_from_angles_and_sides with 70°/110° angles
    # Turtle walk produces floats for B and C that differ by 1 ULP in x
    heading = 0.0
    x, y = 0.0, 0.0
    coords = {}
    verts = ['A', 'D', 'C', 'B']
    sides = [4.0, 2.5, 4.0, 2.5]
    angs = [70.0, 110.0, 70.0, 110.0]
    for i in range(4):
        coords[verts[i]] = (x, y)
        dx = sides[i] * math.cos(math.radians(heading))
        dy = sides[i] * math.sin(math.radians(heading))
        x += dx; y += dy
        exterior = 180.0 - angs[(i+1) % 4]
        heading += exterior

    A = spg.Point2D(*coords['A'])
    B = spg.Point2D(*coords['B'])
    D = spg.Point2D(*coords['D'])
    C = spg.Point2D(*coords['C'])

    seg_AB = spg.Segment(A, B)
    seg_DC = spg.Segment(D, C)

    # Confirm symbolic check fails (this is the bug being worked around)
    assert not seg_AB.is_parallel(seg_DC), \
        "If this now passes, the workaround may be unnecessary — remove _is_parallel fallback"

    # Our helper must return True
    from ir.checks import _is_parallel as ip
    assert ip(seg_AB, seg_DC), "Numerical fallback must detect parallelism"
