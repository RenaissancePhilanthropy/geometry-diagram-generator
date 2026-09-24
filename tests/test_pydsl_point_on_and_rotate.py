# tests/test_pydsl_point_on_and_rotate.py
"""Tests for point_on(), rotate_point(), reflect_point(), and dilate_point() —
exposing the IR's existing PointOn/PointRotate/PointReflect constructs
(previously only reachable via the DSL), plus a brand-new PointDilate."""
import math

from geometry_diagrams.pydsl.api import (
    dilate_point, line_through, point, point_on, reflect_point, rotate_point,
)
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context
from geometry_diagrams.ir.ir import PointDilate, PointOn, PointOnParam, PointReflect, PointRotate
from geometry_diagrams.ir.to_sympy import compile_defs


def test_point_on_appends_point_on_def_with_param_t():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        line = line_through(a, b)
        p = point_on(line, 0.5)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, PointOn) and d.id == p.id]
    assert len(defs) == 1
    assert defs[0].on == line.id
    assert isinstance(defs[0].how, PointOnParam)
    assert defs[0].how.t == 0.5


def test_point_on_a_line_extends_beyond_the_defining_points():
    """t outside [0, 1] must extend past the two points used to define the
    line — this is the actual capability the transversal-angles/
    triangle-proportionality bugs needed and didn't have."""
    with new_builder_context() as builder:
        a, b = point(3, 3), point(5, 0)
        line = line_through(a, b)
        beyond = point_on(line, 1.5)
        before = point_on(line, -0.5)
        ir = builder.build()
    sym = compile_defs(ir)
    bx, by = float(sym[beyond.id].x), float(sym[beyond.id].y)
    px, py = float(sym[before.id].x), float(sym[before.id].y)
    # a=(3,3), b=(5,0): direction (2,-3). t=1.5 -> a + 1.5*(2,-3) = (6, -1.5)
    assert math.isclose(bx, 6.0, abs_tol=1e-9)
    assert math.isclose(by, -1.5, abs_tol=1e-9)
    # t=-0.5 -> a + (-0.5)*(2,-3) = (2, 4.5)
    assert math.isclose(px, 2.0, abs_tol=1e-9)
    assert math.isclose(py, 4.5, abs_tol=1e-9)


def test_point_on_a_segment_interpolates_between_its_endpoints():
    with new_builder_context() as builder:
        a, b, c = point(4, 8), point(0, 0), point(8, 0)
        from geometry_diagrams.pydsl.api import triangle
        t = triangle(a, b, c)
        seg_ab = t.side(a, b)
        d = point_on(seg_ab, 0.6)
        ir = builder.build()
    sym = compile_defs(ir)
    dx, dy = float(sym[d.id].x), float(sym[d.id].y)
    # a=(4,8), b=(0,0): a + 0.6*(b-a) = (4 - 2.4, 8 - 4.8) = (1.6, 3.2)
    assert math.isclose(dx, 1.6, abs_tol=1e-9)
    assert math.isclose(dy, 3.2, abs_tol=1e-9)


def test_rotate_point_appends_point_rotate_def():
    with new_builder_context() as builder:
        center = point(0, 0)
        source = point(1, 0)
        rotated = rotate_point(source, center, math.pi / 2)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, PointRotate) and d.id == rotated.id]
    assert len(defs) == 1
    assert defs[0].center == center.id
    assert defs[0].source == source.id
    assert defs[0].angle == math.pi / 2


def test_rotate_point_rotates_counterclockwise_by_a_positive_angle():
    with new_builder_context() as builder:
        center = point(0, 0)
        source = point(1, 0)
        rotated = rotate_point(source, center, math.pi / 2)
        ir = builder.build()
    sym = compile_defs(ir)
    rx, ry = float(sym[rotated.id].x), float(sym[rotated.id].y)
    assert math.isclose(rx, 0.0, abs_tol=1e-9)
    assert math.isclose(ry, 1.0, abs_tol=1e-9)


def test_reflect_point_across_a_point_appends_point_reflect_def():
    with new_builder_context() as builder:
        center = point(1, 1)
        source = point(3, 1)
        reflected = reflect_point(source, center)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, PointReflect) and d.id == reflected.id]
    assert len(defs) == 1
    assert defs[0].source == source.id
    assert defs[0].across == center.id


def test_reflect_point_across_a_point_is_point_symmetry():
    with new_builder_context() as builder:
        center = point(1, 1)
        source = point(3, 1)
        reflected = reflect_point(source, center)
        ir = builder.build()
    sym = compile_defs(ir)
    rx, ry = float(sym[reflected.id].x), float(sym[reflected.id].y)
    # 2*center - source = (2*1-3, 2*1-1) = (-1, 1)
    assert math.isclose(rx, -1.0, abs_tol=1e-9)
    assert math.isclose(ry, 1.0, abs_tol=1e-9)


def test_reflect_point_across_a_line_mirrors_it():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(0, 1)  # the y-axis
        mirror = line_through(a, b)
        source = point(3, 2)
        reflected = reflect_point(source, mirror)
        ir = builder.build()
    sym = compile_defs(ir)
    rx, ry = float(sym[reflected.id].x), float(sym[reflected.id].y)
    assert math.isclose(rx, -3.0, abs_tol=1e-9)
    assert math.isclose(ry, 2.0, abs_tol=1e-9)


def test_dilate_point_appends_point_dilate_def():
    with new_builder_context() as builder:
        center = point(1, 1)
        source = point(3, 1)
        dilated = dilate_point(source, center, 2.0)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, PointDilate) and d.id == dilated.id]
    assert len(defs) == 1
    assert defs[0].center == center.id
    assert defs[0].source == source.id
    assert defs[0].ratio == 2.0


def test_dilate_point_scales_about_center():
    with new_builder_context() as builder:
        center = point(1, 1)
        source = point(3, 1)
        dilated = dilate_point(source, center, 2.0)
        ir = builder.build()
    sym = compile_defs(ir)
    dx, dy = float(sym[dilated.id].x), float(sym[dilated.id].y)
    # center + 2*(source-center) = (1,1) + 2*(2,0) = (5, 1)
    assert math.isclose(dx, 5.0, abs_tol=1e-9)
    assert math.isclose(dy, 1.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# point_on_arc_between() -- the only pydsl authoring path to the IR's
# ArcBetweenConstraint / PointOnIntent mechanism.
# ---------------------------------------------------------------------------

def _arc_between_ir(from_t: float, to_t: float):
    from geometry_diagrams.pydsl.api import circle, point_on_arc_between

    with new_builder_context() as builder:
        c = circle(point(0, 0), 2)
        f = point_on(c, from_t)
        t = point_on(c, to_t)
        p = point_on_arc_between(c, f, t)
        ir = builder.build()
    return ir, c, f, t, p


def test_point_on_arc_between_records_a_point_on_intent_def():
    from geometry_diagrams.ir.ir import ArcBetweenConstraint, PointOnIntent

    ir, c, f, t, p = _arc_between_ir(0.0, math.pi / 2)
    defs = [d for d in ir.define if isinstance(d, PointOn) and d.id == p.id]
    assert len(defs) == 1
    assert defs[0].on == c.id
    assert isinstance(defs[0].how, PointOnIntent)
    assert defs[0].how.constraints == [
        ArcBetweenConstraint(from_point=f.id, to_point=t.id)
    ]


def test_point_on_arc_between_returns_an_unresolved_point_handle():
    """Same convention as point_on(): a handle whose coordinates only exist
    once the builder's IR is compiled."""
    from geometry_diagrams.pydsl.api import circle, point_on_arc_between
    from geometry_diagrams.pydsl.handles import Point

    with new_builder_context():
        c = circle(point(0, 0), 2)
        p = point_on_arc_between(c, point_on(c, 0.0), point_on(c, math.pi / 2))
        assert isinstance(p, Point)


def test_point_on_arc_between_resolves_inside_the_requested_arc():
    """The resolved angle must land in the requested quarter, not just
    anywhere on the circle -- checked across many RNG seeds so a lucky
    single draw can't pass this."""
    from random import Random

    ir, c, f, t, p = _arc_between_ir(0.0, math.pi / 2)
    angles = []
    for seed in range(20):
        sym = compile_defs(ir, rng=Random(seed))
        pt = sym[p.id]
        angles.append(math.degrees(math.atan2(float(pt.y), float(pt.x))) % 360.0)
        assert math.isclose(float(pt.x) ** 2 + float(pt.y) ** 2, 4.0, abs_tol=1e-9)
    assert all(0.0 <= a <= 90.0 for a in angles), angles
    # ...and it is genuinely sampled, not pinned to one convenient spot.
    assert len(set(round(a, 6) for a in angles)) > 1, angles


def test_point_on_arc_between_honours_the_counter_clockwise_sweep():
    """from=90 deg, to=0 deg is the 270 deg CCW sweep, not the short way."""
    from random import Random

    ir, c, f, t, p = _arc_between_ir(math.pi / 2, 0.0)
    for seed in range(20):
        pt = compile_defs(ir, rng=Random(seed))[p.id]
        a = math.degrees(math.atan2(float(pt.y), float(pt.x))) % 360.0
        assert 90.0 <= a <= 360.0 or math.isclose(a, 0.0, abs_tol=1e-9), a


def test_point_on_arc_between_reaches_the_rejection_sampling_compiler_path():
    """Guard against the result merely *looking* right: the compiler's
    _point_on_intent rejection sampler must actually be the code that
    produced it, with the ArcBetweenConstraint in hand."""
    from geometry_diagrams.ir import to_sympy
    from geometry_diagrams.ir.ir import ArcBetweenConstraint

    ir, c, f, t, p = _arc_between_ir(0.0, math.pi / 2)
    calls = []
    original = to_sympy._point_on_intent

    def spy(obj, constraints, sym, rng, def_id, **kwargs):
        calls.append((def_id, list(constraints)))
        return original(obj, constraints, sym, rng, def_id, **kwargs)

    to_sympy._point_on_intent = spy
    try:
        compile_defs(ir)
    finally:
        to_sympy._point_on_intent = original

    assert [def_id for def_id, _ in calls] == [p.id]
    assert calls[0][1] == [ArcBetweenConstraint(from_point=f.id, to_point=t.id)]


def test_point_on_arc_between_is_advertised_in_all_and_in_the_stub():
    """pydsl.__all__ is what the sandbox exposes as a tool name and what
    retry.py builds its did-you-mean suggestions from; the stub is what the
    model reads."""
    import geometry_diagrams.pydsl as pydsl_module
    from geometry_diagrams.pydsl.stub import generate_stub

    assert "point_on_arc_between" in pydsl_module.__all__
    assert "def point_on_arc_between(" in generate_stub()


def test_point_on_arc_between_runs_in_a_real_sandboxed_script():
    """The name being in __all__ is necessary but not sufficient -- actually
    execute a script through the sandbox, compile what it produced, and check
    the sampled point landed inside the requested arc."""
    from geometry_diagrams.ir.renderer import SVGRenderer
    from geometry_diagrams.ir.ir import ArcBetweenConstraint, PointOn, PointOnIntent
    from geometry_diagrams.pydsl.sandbox import run_script

    result = run_script(
        "c = circle(point(0, 0), 2)\n"
        "f = point_on(c, 0.0)\n"
        "t = point_on(c, 1.5707963267948966)\n"
        "p = point_on_arc_between(c, f, t)\n"
        "draw(c)\n"
        "p.label('P')\n"
    )
    assert result.error is None, result.error
    diagram = result.diagram_ir
    sampled = [
        d for d in diagram.define
        if isinstance(d, PointOn) and isinstance(d.how, PointOnIntent)
    ]
    assert len(sampled) == 1
    assert isinstance(sampled[0].how.constraints[0], ArcBetweenConstraint)

    sym = compile_defs(diagram)
    pt = sym[sampled[0].id]
    angle = math.degrees(math.atan2(float(pt.y), float(pt.x))) % 360.0
    assert 0.0 <= angle <= 90.0, angle
    # ...and the whole thing renders, so nothing downstream chokes on it.
    assert "<circle" in SVGRenderer().render(diagram, sym).output


def test_point_on_arc_between_mid_script_coordinates_match_the_final_compile():
    """point_on_arc_between() is the first rng-consuming def reachable from
    pydsl, so Builder._advance_sym()'s incremental compile and the final
    whole-diagram compile_defs() must draw from the SAME rng stream. They
    didn't: _advance_sym() built a fresh Random(42) per call, so a coordinate
    read between two sampled points rewound the stream and the second point
    silently resolved to one place mid-script and a different place in the
    rendered diagram."""
    from geometry_diagrams.pydsl.api import circle, label_text, point_on_arc_between

    with new_builder_context() as builder:
        c = circle(point(0, 0), 2)
        f = point_on(c, 0.0)
        t = point_on(c, math.pi)
        p1 = point_on_arc_between(c, f, t)
        label_text("x", at=(p1.x, p1.y))  # forces the incremental resolve
        p2 = point_on_arc_between(c, f, t)
        mid_p1 = (p1.x, p1.y)
        mid_p2 = (p2.x, p2.y)
        ir = builder.build()

    sym = compile_defs(ir)
    for pid, mid in ((p1.id, mid_p1), (p2.id, mid_p2)):
        final = (float(sym[pid].x), float(sym[pid].y))
        assert math.isclose(mid[0], final[0], abs_tol=1e-9), (pid, mid, final)
        assert math.isclose(mid[1], final[1], abs_tol=1e-9), (pid, mid, final)


def test_repeated_mid_script_reads_do_not_rewind_the_builders_rng():
    """Three sampled points with a forced resolve after each: every one must
    still agree with the final compile, and they must not all collapse onto
    the same coordinates (which is what a rewound stream produces)."""
    from geometry_diagrams.pydsl.api import circle, label_text, point_on_arc_between

    with new_builder_context() as builder:
        c = circle(point(0, 0), 2)
        f = point_on(c, 0.0)
        t = point_on(c, math.pi)
        sampled = []
        for _ in range(3):
            p = point_on_arc_between(c, f, t)
            label_text("x", at=(p.x, p.y))  # forces a resolve after each one
            sampled.append((p, (p.x, p.y)))
        ir = builder.build()

    sym = compile_defs(ir)
    for p, mid in sampled:
        final = (float(sym[p.id].x), float(sym[p.id].y))
        assert math.isclose(mid[0], final[0], abs_tol=1e-9), (p.id, mid, final)
        assert math.isclose(mid[1], final[1], abs_tol=1e-9), (p.id, mid, final)
    assert len({tuple(round(v, 9) for v in mid) for _, mid in sampled}) == 3
