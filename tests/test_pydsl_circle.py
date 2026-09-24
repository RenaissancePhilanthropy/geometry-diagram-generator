# tests/test_pydsl_circle.py
"""Tests for the Circle handle and circumcircle()/incircle() ops."""
import math

import pytest

from geometry_diagrams.pydsl.api import circle, circumcircle, ellipse, incircle, point, point_on, tangent_circle, triangle
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


def test_circumcircle_center_is_a_computed_point_triangle_center():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(0, 3)
        t = triangle(a, b, c)
        circ = circumcircle(t)
        center = circ.center
        ir = get_builder().build()
    center_defs = [d for d in ir.define if d.kind == "point_triangle_center"]
    assert len(center_defs) == 1
    assert center_defs[0].which == "circumcenter"
    assert center_defs[0].tri == t.id
    assert center.id == center_defs[0].id


def test_circumcircle_radius_is_numeric_for_concrete_vertices():
    with new_builder_context():
        # 3-4-5 right triangle: circumradius of a right triangle is half the
        # hypotenuse — hypotenuse is 5, so R = 2.5.
        a, b, c = point(0, 0), point(4, 0), point(0, 3)
        t = triangle(a, b, c)
        circ = circumcircle(t)
    assert math.isclose(circ.radius, 2.5, abs_tol=1e-9)


def test_incircle_radius_is_numeric_for_concrete_vertices():
    with new_builder_context():
        # 3-4-5 right triangle: inradius = (a + b - c) / 2 = (3 + 4 - 5) / 2 = 1.0
        a, b, c = point(0, 0), point(4, 0), point(0, 3)
        t = triangle(a, b, c)
        inc = incircle(t)
    assert math.isclose(inc.radius, 1.0, abs_tol=1e-9)


def test_incircle_center_is_a_computed_incenter_point():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(0, 3)
        t = triangle(a, b, c)
        inc = incircle(t)
        center = inc.center
        ir = get_builder().build()
    center_defs = [d for d in ir.define if d.kind == "point_triangle_center" and d.which == "incenter"]
    assert len(center_defs) == 1
    assert center.id == center_defs[0].id


# ---------------------------------------------------------------------------
# tangent_circle()
# ---------------------------------------------------------------------------


def test_tangent_circle_records_circle_tangent_at_def_with_external_default():
    from geometry_diagrams.ir.ir import CircleTangentAt

    with new_builder_context():
        c0 = point(0, 0)
        circ = circle(c0, 2.0)
        touch = point_on(circ, 0.0)  # (2, 0), on the boundary
        new_circ = tangent_circle(circ, touch, 1.0)
        ir = get_builder().build()

    defs = [d for d in ir.define if isinstance(d, CircleTangentAt) and d.id == new_circ.id]
    assert len(defs) == 1
    d = defs[0]
    assert d.circle == circ.id
    assert d.point == touch.id
    assert d.radius == 1.0
    assert d.tangency == "external"


def test_tangent_circle_internal_flag_sets_tangency_internal():
    from geometry_diagrams.ir.ir import CircleTangentAt

    with new_builder_context():
        c0 = point(0, 0)
        circ = circle(c0, 2.0)
        touch = point_on(circ, 0.0)
        new_circ = tangent_circle(circ, touch, 1.0, internal=True)
        ir = get_builder().build()

    defs = [d for d in ir.define if isinstance(d, CircleTangentAt) and d.id == new_circ.id]
    assert len(defs) == 1
    assert defs[0].tangency == "internal"


def test_tangent_circle_center_is_reachable_as_a_point_handle():
    """Mirrors circumcircle()'s precedent: the returned Circle.center is an
    ordinary, lazily-resolving Point handle, addressable under ticket 03's
    derived id (tangent_circle_center_id), not a placeholder."""
    from geometry_diagrams.ir.ir import tangent_circle_center_id
    from geometry_diagrams.ir.to_sympy import compile_defs

    with new_builder_context():
        c0 = point(0, 0)
        circ = circle(c0, 2.0)
        touch = point_on(circ, 0.0)  # (2, 0)
        new_circ = tangent_circle(circ, touch, 1.0)  # external: center at (3, 0)
        center = new_circ.center
        ir = get_builder().build()

    assert center.id == tangent_circle_center_id(new_circ.id)
    sym = compile_defs(ir)
    resolved_center = sym[center.id]
    assert float(resolved_center.x.evalf()) == pytest.approx(3.0)
    assert float(resolved_center.y.evalf()) == pytest.approx(0.0)


def test_tangent_circle_end_to_end_draw_and_render():
    """Builder script -> compiled diagram -> rendered SVG, including drawing
    the new circle and a segment referencing its center."""
    from geometry_diagrams.ir.renderer import SVGRenderer
    from geometry_diagrams.ir.to_sympy import compile_defs
    from geometry_diagrams.pydsl.api import draw, segment

    with new_builder_context():
        c0 = point(0, 0)
        circ = circle(c0, 2.0)
        touch = point_on(circ, 0.0)
        new_circ = tangent_circle(circ, touch, 1.0)
        draw(circ)
        draw(new_circ)
        segment(c0, new_circ.center)
        ir = get_builder().build()

    sym = compile_defs(ir)
    svg = SVGRenderer().render(ir, sym).output
    assert svg.count("<circle") == 2
    assert "<line" in svg or "<path" in svg


def test_tangent_circle_point_not_on_reference_circle_raises_at_compile_time():
    from geometry_diagrams.ir.errors import IRCompileError
    from geometry_diagrams.ir.to_sympy import compile_defs

    with new_builder_context():
        c0 = point(0, 0)
        circ = circle(c0, 2.0)
        off_circle = point(5, 5)  # not on the reference circle's boundary
        tangent_circle(circ, off_circle, 1.0)
        ir = get_builder().build()

    with pytest.raises(IRCompileError, match="not on circle"):
        compile_defs(ir)


def test_tangent_circle_nonpositive_radius_raises_immediately():
    with new_builder_context():
        c0 = point(0, 0)
        circ = circle(c0, 2.0)
        touch = point_on(circ, 0.0)
        with pytest.raises(ValueError, match="positive"):
            tangent_circle(circ, touch, 0.0)
        with pytest.raises(ValueError, match="positive"):
            tangent_circle(circ, touch, -1.0)


def test_tangent_circle_elliptical_reference_raises_at_compile_time():
    from geometry_diagrams.ir.errors import IRCompileError
    from geometry_diagrams.ir.to_sympy import compile_defs

    with new_builder_context():
        ec = point(0, 0)
        ell = ellipse(center=ec, hradius=3.0, vradius=2.0)
        touch = point_on(ell, 0.0)
        tangent_circle(ell, touch, 1.0)
        ir = get_builder().build()

    with pytest.raises(IRCompileError, match="genuine circle"):
        compile_defs(ir)


def test_tangent_circle_internal_identical_radius_raises_at_compile_time():
    from geometry_diagrams.ir.errors import IRCompileError
    from geometry_diagrams.ir.to_sympy import compile_defs

    with new_builder_context():
        c0 = point(0, 0)
        circ = circle(c0, 2.0)
        touch = point_on(circ, 0.0)
        tangent_circle(circ, touch, 2.0, internal=True)  # same radius as circ
        ir = get_builder().build()

    with pytest.raises(IRCompileError, match="identical"):
        compile_defs(ir)
