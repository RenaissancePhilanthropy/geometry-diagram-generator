# tests/test_pydsl_point_ergonomics.py
"""Tests for Point.x/.y and arithmetic operators (+, -, *, __rmul__).

Motivation (found diagnosing real eval failures): models kept hand-deriving
coordinates via separate plain-float bookkeeping alongside point() calls,
because Point handles carried no coordinates at all — not even for literal
point(x, y) calls, where the model already knows the numbers. This let
models write natural, less error-prone code like `center + k * (source -
center)` for a dilation, directly on the handles they already have, instead
of re-deriving the same arithmetic with parallel float variables.
"""
import math

import pytest

from geometry_diagrams.pydsl.api import point, point_on, line_through
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context
from geometry_diagrams.ir.ir import PointFixed


def test_point_literal_exposes_its_own_coordinates():
    with new_builder_context():
        p = point(3, 4)
    assert p.x == 3.0
    assert p.y == 4.0


def test_add_two_literal_points_records_a_new_point_fixed():
    with new_builder_context() as builder:
        a = point(1, 2)
        b = point(3, 4)
        c = a + b
        ir = builder.build()
    assert c.x == 4.0
    assert c.y == 6.0
    defs = [d for d in ir.define if isinstance(d, PointFixed) and d.id == c.id]
    assert len(defs) == 1
    assert defs[0].x == 4.0 and defs[0].y == 6.0


def test_subtract_two_literal_points():
    with new_builder_context():
        a = point(5, 7)
        b = point(2, 1)
        c = a - b
    assert c.x == 3.0
    assert c.y == 6.0


def test_multiply_point_by_scalar_both_orders():
    with new_builder_context():
        a = point(2, 3)
        b = a * 2.5
        c = 2.5 * a
    assert (b.x, b.y) == (5.0, 7.5)
    assert (c.x, c.y) == (5.0, 7.5)


def test_dilation_via_plain_operators_matches_dilate_point():
    """The exact motivating case: for literal points, dilation should just
    work as ordinary arithmetic, no dedicated primitive required."""
    from geometry_diagrams.pydsl.api import dilate_point

    with new_builder_context() as builder:
        center = point(1, 1)
        source = point(3, 1)
        k = 2.0
        via_operators = center + (source - center) * k
        via_primitive = dilate_point(source, center, k)
        ir = builder.build()

    from geometry_diagrams.ir.to_sympy import compile_defs
    sym = compile_defs(ir)
    assert float(sym[via_operators.id].x) == pytest.approx(float(sym[via_primitive.id].x))
    assert float(sym[via_operators.id].y) == pytest.approx(float(sym[via_primitive.id].y))


def test_arithmetic_on_a_point_with_unknown_coordinates_raises_a_clear_error():
    with new_builder_context():
        a = point(0, 0)
        b = point(4, 0)
        line = line_through(a, b)
        unknown = point_on(line, 0.5)  # not known at script time
        with pytest.raises(ValueError, match="no known coordinates"):
            _ = a + unknown


def test_multiplying_a_point_with_unknown_coordinates_raises_a_clear_error():
    from geometry_diagrams.pydsl.api import rotate_point

    with new_builder_context():
        origin = point(0, 0)
        far = point(1, 0)
        rotated = rotate_point(far, origin, math.pi / 4)
        with pytest.raises(ValueError, match="no known coordinates"):
            _ = rotated * 2


def test_point_arithmetic_works_through_the_real_sandbox():
    """Regression test: Point.__add__ previously called get_builder(), which
    only succeeds inside a _bind_to_builder-wrapped top-level call — a
    script's own top-level `a + b` statement is not one, so this raised
    RuntimeError: no active Builder in the real sandbox despite passing
    every direct-new_builder_context() test above."""
    from geometry_diagrams.pydsl.sandbox import run_script

    script = "a = point(0, 0)\nb = point(4, 0)\nc = a + b\ndraw_points(a, b, c)\n"
    result = run_script(script, timeout_seconds=10.0)
    assert result.error is None, result.error
    assert result.diagram_ir is not None
