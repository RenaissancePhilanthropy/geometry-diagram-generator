"""Stage 2 of the rotated-ellipses design: tangents and intersections on a tilted
full ellipse, built on the numeric conic kernel (ir/conic_kernel.py), and the
float-radius axis-aligned ellipse x ellipse pairs that used to be a SymPy limit.

Expected values come from hand derivations (the 3 x 1 ellipse at 30 degrees has
half-height sqrt(3), so y = 2 +- sqrt(3) is tangent to it about (1, 2)) and from
brute-force checks written here, not from the code under test."""
from __future__ import annotations

import math

import numpy as np
import pytest
import sympy as sp

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.checks import run_checks
from geometry_diagrams.ir.errors import IntersectionError, PickError
from geometry_diagrams.ir.to_sympy import compile_defs

CX, CY, HR, VR, DEG = 1.0, 2.0, 3.0, 1.0, 30.0
C30, S30 = math.cos(math.radians(DEG)), math.sin(math.radians(DEG))
SQ3 = math.sqrt(3.0)


def curve(t, cx=CX, cy=CY, hr=HR, vr=VR, deg=DEG):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    u, v = hr * np.cos(t), vr * np.sin(t)
    return cx + u * c - v * s, cy + u * s + v * c


def implicit(x, y, cx=CX, cy=CY, hr=HR, vr=VR, deg=DEG):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    dx, dy = x - cx, y - cy
    return ((dx * c + dy * s) / hr) ** 2 + ((-dx * s + dy * c) / vr) ** 2 - 1.0


def base(extra=(), rotation=DEG, **ell):
    return [
        ir.PointFixed(id="O", x=CX, y=CY),
        ir.EllipseCenterAxes(id="E", center="O", hradius=HR, vradius=VR, rotation_deg=rotation, **ell),
        *extra,
    ]


def compile_(*stmts):
    return compile_defs(ir.DiagramIR(define=list(stmts)))


def xy(p):
    return float(p.x), float(p.y)


def all_points(defs, obj1, obj2, limit=8):
    """Every intersection candidate, in order, through PickIndex k = 0, 1, ..."""
    out = []
    for k in range(limit):
        try:
            sym = compile_(*defs, ir.PointIntersection(id="X", obj1=obj1, obj2=obj2, pick=ir.PickIndex(k=k)))
        except PickError:
            break
        out.append(xy(sym["X"]))
    return out


def horizontal(y, id_="L"):
    return [ir.PointFixed(id=id_ + "1", x=-9, y=y), ir.PointFixed(id=id_ + "2", x=9, y=y),
            ir.LineThrough(id=id_, p=id_ + "1", q=id_ + "2")]


# --- line, segment, ray x tilted ellipse --------------------------------------------

def test_line_through_the_center_crosses_at_the_hand_derived_points():
    defs = base(horizontal(CY))
    pts = all_points(defs, "L", "E")
    assert len(pts) == 2
    assert sorted(pts)[0] == pytest.approx((CX - SQ3, CY), abs=1e-9)
    assert sorted(pts)[1] == pytest.approx((CX + SQ3, CY), abs=1e-9)


def test_segment_and_ray_through_a_tilted_ellipse_give_its_two_crossings():
    extra = [ir.PointFixed(id="A", x=-5, y=CY), ir.PointFixed(id="B", x=7, y=CY),
             ir.Segment(id="S", a="A", b="B"), ir.Ray(id="R", a="A", b="B")]
    assert len(all_points(base(extra), "S", "E")) == 2
    assert len(all_points(base(extra), "R", "E")) == 2


def test_a_segment_that_stops_short_has_no_intersection():
    extra = [ir.PointFixed(id="A", x=-5, y=CY), ir.PointFixed(id="B", x=-2, y=CY), ir.Segment(id="S", a="A", b="B")]
    with pytest.raises(IntersectionError, match="no intersection points"):
        compile_(*base(extra), ir.PointIntersection(id="X", obj1="S", obj2="E"))


def test_a_segment_ending_on_the_curve_keeps_that_end():
    extra = [ir.PointFixed(id="A", x=-5, y=CY), ir.PointFixed(id="B", x=CX - SQ3, y=CY), ir.Segment(id="S", a="A", b="B")]
    (pt,) = all_points(base(extra), "S", "E")
    assert pt == pytest.approx((CX - SQ3, CY), abs=1e-8)


@pytest.mark.parametrize("sign", [1, -1])
def test_an_exactly_tangent_line_snaps_to_one_point(sign):
    # y = cy +- sqrt(3) touches the 3 x 1 ellipse at 30 degrees; the touch point is
    # (cx +- 2, cy +- sqrt(3)) by hand: du = (a^2 - b^2) sin cos / half_height = 2.
    (pt,) = all_points(base(horizontal(CY + sign * SQ3)), "L", "E")
    assert pt == pytest.approx((CX + sign * 2.0, CY + sign * SQ3), abs=1e-7)
    assert abs(implicit(*pt)) < 1e-7


def test_a_disjoint_line_names_the_miss():
    with pytest.raises(IntersectionError, match=r"the line misses the ellipse \(disjoint\)"):
        compile_(*base(horizontal(CY + 5)), ir.PointIntersection(id="X", obj1="L", obj2="E"))


# --- circle, ellipse x tilted ellipse -------------------------------------------------

def _check_on_both(pts, circle=None, ell2=None):
    for x, y in pts:
        assert abs(implicit(*(x, y))) < 1e-7
        if circle:
            assert math.hypot(x - circle[0], y - circle[1]) == pytest.approx(circle[2], abs=1e-7)
        if ell2:
            assert abs(implicit(x, y, **ell2)) < 1e-7


def test_circle_through_a_tilted_ellipse_in_both_operand_orders():
    defs = base([ir.CircleCenterRadius(id="C", center="O", radius=2)])
    for o1, o2 in (("C", "E"), ("E", "C")):
        pts = all_points(defs, o1, o2)
        assert len(pts) == 4
        _check_on_both(pts, circle=(CX, CY, 2.0))


def test_circle_x_tilted_ellipse_matches_the_hand_derived_points():
    # Circle r = 2 about the center: x^2 (cos^2/9 + sin^2) ... on the ellipse,
    # (u/3)^2 + v^2 = 1 with u^2 + v^2 = 4, so u^2 = 9/8 * 3 = 27/8 * ... solved by hand:
    # v^2 = (4 - 9)/(1 - 9) ... u^2 (1/9 - 1) = 1 - 4  ->  u^2 = 27/8, v^2 = 5/8.
    u, v = math.sqrt(27 / 8), math.sqrt(5 / 8)
    expected = [(CX + su * u * C30 - sv * v * S30, CY + su * u * S30 + sv * v * C30)
                for su in (1, -1) for sv in (1, -1)]
    pts = all_points(base([ir.CircleCenterRadius(id="C", center="O", radius=2)]), "C", "E")
    for e in expected:
        assert min(math.dist(e, p) for p in pts) < 1e-8


def test_tilted_ellipse_x_axis_aligned_ellipse_and_x_tilted_ellipse():
    defs = base([
        ir.PointFixed(id="P", x=2.0, y=2.5),
        ir.EllipseCenterAxes(id="F", center="P", hradius=2.0, vradius=2.6),
        ir.EllipseCenterAxes(id="G", center="P", hradius=2.5, vradius=1.2, rotation_deg=-40),
    ])
    pts_f = all_points(defs, "E", "F")
    pts_g = all_points(defs, "G", "E")
    _check_on_both(pts_f, ell2=dict(cx=2.0, cy=2.5, hr=2.0, vr=2.6, deg=0))
    _check_on_both(pts_g, ell2=dict(cx=2.0, cy=2.5, hr=2.5, vr=1.2, deg=-40))
    # the counts agree with a brute-force sign-change count
    t = np.linspace(0, 2 * math.pi, 200_000, endpoint=False)
    for pts, other in ((pts_f, dict(cx=2.0, cy=2.5, hr=2.0, vr=2.6, deg=0)), (pts_g, dict(cx=2.0, cy=2.5, hr=2.5, vr=1.2, deg=-40))):
        f = implicit(*curve(t), **other)
        assert len(pts) == int(np.sum(f * np.roll(f, -1) < 0)) > 0


def test_circle_externally_tangent_at_a_tilted_tip_gives_one_point():
    tip = curve(0.0)
    nx, ny = C30, S30
    extra = [ir.PointFixed(id="K", x=float(tip[0]) + nx * 1.5, y=float(tip[1]) + ny * 1.5),
             ir.CircleCenterRadius(id="C", center="K", radius=1.5)]
    for o1, o2 in (("C", "E"), ("E", "C")):
        (pt,) = all_points(base(extra), o1, o2)
        assert pt == pytest.approx((float(tip[0]), float(tip[1])), abs=1e-7)


def test_coincident_ellipses_name_both_ids():
    defs = base([ir.EllipseCenterAxes(id="F", center="O", hradius=HR, vradius=VR, rotation_deg=DEG + 180)])
    with pytest.raises(IntersectionError, match=r"'E' and 'F'.*same curve"):
        compile_(*defs, ir.PointIntersection(id="X", obj1="E", obj2="F"))


def test_tilted_ellipse_that_misses_a_circle_names_the_miss():
    defs = base([ir.PointFixed(id="K", x=20, y=2), ir.CircleCenterRadius(id="C", center="K", radius=1)])
    with pytest.raises(IntersectionError, match="no intersection points between 'C' and 'E'"):
        compile_(*defs, ir.PointIntersection(id="X", obj1="C", obj2="E"))


# --- arc operands: the sweep filter runs after the snap -------------------------------

def _arc_defs(start_deg, end_deg, rc=2.0):
    # Arc of the circle about O from angle start to end (counter-clockwise).
    return base([
        ir.PointFixed(id="S", x=CX + rc * math.cos(math.radians(start_deg)), y=CY + rc * math.sin(math.radians(start_deg))),
        ir.PointFixed(id="T", x=CX + rc * math.cos(math.radians(end_deg)), y=CY + rc * math.sin(math.radians(end_deg))),
        ir.ArcCenterStartEnd(id="A", center="O", start="S", end="T"),
    ])


def test_arc_operand_is_filtered_by_its_sweep():
    full = all_points(base([ir.CircleCenterRadius(id="C", center="O", radius=2)]), "C", "E")
    # By hand the circle meets the ellipse at 6.7, 53.3, 156.7 and 203.3 degrees about O.
    pts = all_points(_arc_defs(20, 90), "A", "E")
    assert len(full) == 4
    assert len(pts) == 1
    assert math.degrees(math.atan2(pts[0][1] - CY, pts[0][0] - CX)) == pytest.approx(53.3, abs=0.1)


def test_arc_ending_exactly_at_a_touch_point_keeps_it():
    tip = curve(0.0)
    tx, ty = float(tip[0]), float(tip[1])
    r = 1.5
    kx, ky = tx + C30 * r, ty + S30 * r
    start = math.degrees(math.atan2(ty - ky, tx - kx))
    defs = base([
        ir.PointFixed(id="K", x=kx, y=ky),
        ir.PointFixed(id="S", x=tx, y=ty),  # the arc starts at the touch point
        ir.PointFixed(id="T", x=kx + r * math.cos(math.radians(start + 60)), y=ky + r * math.sin(math.radians(start + 60))),
        ir.ArcCenterStartEnd(id="A", center="K", start="S", end="T"),
    ])
    (pt,) = all_points(defs, "A", "E")
    assert pt == pytest.approx((tx, ty), abs=1e-7)


def test_arc_whose_sweep_misses_every_crossing_says_so():
    # The circle meets the ellipse at 6.7, 53.3, 156.7 and 203.3 degrees; the arc from
    # 70 to 130 degrees holds none of them.
    with pytest.raises(IntersectionError, match="meet outside the sweep of 'A'"):
        compile_(*_arc_defs(70, 130), ir.PointIntersection(id="X", obj1="A", obj2="E"))


# --- float-radius axis-aligned pairs (the retired SymPy limit) ---------------------------

def _plain_ellipses(h1, v1, c2, h2, v2):
    return [
        ir.PointFixed(id="C1", x=0, y=0), ir.PointFixed(id="C2", x=c2[0], y=c2[1]),
        ir.EllipseCenterAxes(id="e1", center="C1", hradius=h1, vradius=v1),
        ir.EllipseCenterAxes(id="e2", center="C2", hradius=h2, vradius=v2),
    ]


def test_float_radius_axis_aligned_ellipses_that_cross_four_times_return_their_points():
    defs = _plain_ellipses(5.0, 2.0, (1.3, 0.7), 2.1, 4.7)
    pts = all_points(defs, "e1", "e2")
    assert len(pts) == 4
    for x, y in pts:
        assert (x / 5.0) ** 2 + (y / 2.0) ** 2 == pytest.approx(1.0, abs=1e-9)
        assert ((x - 1.3) / 2.1) ** 2 + ((y - 0.7) / 4.7) ** 2 == pytest.approx(1.0, abs=1e-9)


def test_exact_radius_axis_aligned_pairs_keep_the_exact_sympy_path():
    defs = _plain_ellipses(3, 1, (0, 0), 2, 2)  # circle r = 2 x ellipse 3 x 1, integer radii
    sym = compile_(*defs, ir.PointIntersection(id="X", obj1="e1", obj2="e2", pick=ir.PickIndex(k=0)))
    assert not sym["X"].has(sp.Float)  # exact coordinates, not kernel floats
    assert float(sym["X"].x) ** 2 + float(sym["X"].y) ** 2 == pytest.approx(4.0)


# --- tangents from a point ---------------------------------------------------------------

def _tangent_defs(px=8.0, py=3.0, pick=None):
    return base([ir.PointFixed(id="P", x=px, y=py), ir.LineTangent(id="t", point="P", circle="E", pick=pick)])


def _is_tangent(line, tol=1e-6):
    """Independent test of tangency: the line touches the curve and no sampled
    curve point lies strictly across it."""
    a, b, c = (float(v) for v in line.coefficients)
    n = math.hypot(a, b)
    x, y = curve(np.linspace(0, 2 * math.pi, 40_000, endpoint=False))
    side = (a * x + b * y + c) / n
    touches = np.abs(side).min() < tol
    return bool(touches and (side.min() > -tol or side.max() < tol))


@pytest.mark.parametrize("k", [0, 1])
def test_external_point_gives_two_tangents_touching_the_curve(k):
    sym = compile_(*_tangent_defs(pick=ir.PickIndex(k=k)))
    line = sym["t"]
    assert line.contains(sym["P"]) or abs(float(line.distance(sym["P"]))) < 1e-9
    assert _is_tangent(line)


def test_the_two_tangents_are_different_lines():
    a = compile_(*_tangent_defs(pick=ir.PickIndex(k=0)))["t"]
    b = compile_(*_tangent_defs(pick=ir.PickIndex(k=1)))["t"]
    assert not a.is_parallel(b) or a != b
    with pytest.raises(PickError):
        compile_(*_tangent_defs(pick=ir.PickIndex(k=2)))


def test_point_inside_the_ellipse_has_no_tangent_lines():
    with pytest.raises(IntersectionError, match="no tangent lines from 'P' to 'E'"):
        compile_(*_tangent_defs(px=CX + 0.5, py=CY + 0.1, pick=ir.PickIndex(k=0)))


def test_point_on_the_curve_gives_exactly_one_tangent():
    on = curve(0.7)
    defs = _tangent_defs(px=float(on[0]), py=float(on[1]))
    sym = compile_(*defs)  # no pick needed: one candidate
    assert _is_tangent(sym["t"])
    with pytest.raises(PickError):
        compile_(*_tangent_defs(px=float(on[0]), py=float(on[1]), pick=ir.PickIndex(k=1)))


def test_upper_lower_and_closest_picks_choose_by_the_touch_point():
    # P far to the right of O: one tangent touches above the line O-P, one below.
    # The touch points are found by sampling, independent of the kernel.
    def touch_y(line):
        a, b, c = (float(v) for v in line.coefficients)
        t = np.linspace(0, 2 * math.pi, 400_000, endpoint=False)
        x, y = curve(t)
        d = np.abs(a * x + b * y + c) / math.hypot(a, b)
        return float(y[int(d.argmin())])

    upper = compile_(*_tangent_defs(py=CY, pick=ir.PickUpperOfLine(a="O", b="P")))["t"]
    lower = compile_(*_tangent_defs(py=CY, pick=ir.PickLowerOfLine(a="O", b="P")))["t"]
    assert touch_y(upper) > CY + 0.1 and touch_y(lower) < CY - 0.1
    defs = _tangent_defs(py=CY, pick=ir.PickClosestTo(p="Q"))
    near_top = compile_(*defs, ir.PointFixed(id="Q", x=CX, y=CY + 5))["t"]
    near_bottom = compile_(*defs, ir.PointFixed(id="Q", x=CX, y=CY - 5))["t"]
    assert touch_y(near_top) > CY and touch_y(near_bottom) < CY


# --- the tangent check ------------------------------------------------------------------------

def test_tangent_check_passes_for_a_tangent_line_and_fails_for_a_missing_one():
    diagram = ir.DiagramIR(
        define=_tangent_defs(pick=ir.PickIndex(k=0)) + horizontal(CY + 5, "M") + horizontal(CY + SQ3, "H"),
        checks=[ir.Tangent(line="t", circle="E"), ir.Tangent(line="H", circle="E"), ir.Tangent(line="M", circle="E")],
    )
    ok_t, ok_h, miss = run_checks(diagram.checks, compile_defs(diagram))
    assert ok_t.passed and ok_h.passed
    assert not miss.passed and "dist=" in miss.message and "'E'" in miss.message


def test_contains_check_tolerance_is_a_length_on_a_long_thin_ellipse():
    defs = [
        ir.PointFixed(id="O", x=0, y=0),
        ir.EllipseCenterAxes(id="E", center="O", hradius=1000, vradius=0.01, rotation_deg=30),
        ir.PointOn(id="A", on="E", how=ir.PointOnParam(t=0.3)),
    ]
    t = 0.3
    nu, nv = math.cos(t) / 1000, math.sin(t) / 0.01
    n = math.hypot(nu, nv)
    sym0 = compile_(*defs)
    ax, ay = xy(sym0["A"])
    nx, ny = (nu * C30 - nv * S30) / n, (nu * S30 + nv * C30) / n
    diagram = ir.DiagramIR(
        define=defs + [ir.PointFixed(id="B", x=ax + 1e-3 * nx, y=ay + 1e-3 * ny)],
        checks=[ir.Contains(p="A", obj="E", tol=1e-4), ir.Contains(p="B", obj="E", tol=1e-4)],
    )
    on, off = run_checks(diagram.checks, compile_defs(diagram))
    assert on.passed and not off.passed


# --- the frame is the one home of the parametric-angle math ------------------------------

def test_arc_sites_read_the_parametric_angle_through_the_frame():
    import inspect

    from geometry_diagrams.ir import render_util, to_sympy

    sites = [
        to_sympy._invert_param, to_sympy._point_in_arc_sweep, to_sympy._eval_param,
        to_sympy._reflex_for_bulge_toward, to_sympy.arc_param_frame, render_util.elliptical_arc_params,
    ]
    for fn in sites:
        assert "math.atan2(" not in inspect.getsource(fn), fn.__name__


# --- end to end: one figure through both renderers ------------------------------------------

def _figure():
    return ir.DiagramIR(
        define=[
            ir.PointFixed(id="O", x=CX, y=CY),
            ir.EllipseCenterAxes(id="E", center="O", hradius=HR, vradius=VR, rotation_deg=DEG),
            ir.PointFixed(id="L1", x=-4, y=0.5), ir.PointFixed(id="L2", x=6, y=3),
            ir.LineThrough(id="L", p="L1", q="L2"),
            ir.PointIntersection(id="X", obj1="L", obj2="E", pick=ir.PickIndex(k=0)),
            ir.CircleCenterRadius(id="C", center="O", radius=2),
            ir.PointIntersection(id="Y", obj1="C", obj2="E", pick=ir.PickIndex(k=0)),
            ir.PointFixed(id="P", x=7, y=5),
            ir.LineTangent(id="T", point="P", circle="E", pick=ir.PickIndex(k=0)),
            ir.PointIntersection(id="Z", obj1="T", obj2="E", pick=ir.PickIndex(k=0)),
        ],
        render=[ir.Draw(obj="E"), ir.Draw(obj="L"), ir.Draw(obj="C"), ir.Draw(obj="T"),
                ir.DrawPoints(points=["X", "Y", "Z", "P"]),
                ir.LabelPoint(p="X", text="X"), ir.LabelPoint(p="Y", text="Y"), ir.LabelPoint(p="Z", text="Z")],
        checks=[ir.Tangent(line="T", circle="E"), ir.Contains(p="X", obj="E"), ir.Contains(p="Y", obj="E"),
                ir.Contains(p="Z", obj="E")],
    )


def test_figure_passes_its_checks_and_the_touch_point_is_on_the_tangent():
    d = _figure()
    sym = compile_defs(d)
    assert all(r.passed for r in run_checks(d.checks, sym)), [r.message for r in run_checks(d.checks, sym)]
    for pid in ("X", "Y", "Z"):
        assert abs(implicit(*xy(sym[pid]))) < 1e-9


def test_figure_svg_dots_sit_on_the_drawn_tilted_outline():
    import re
    import xml.etree.ElementTree as ET

    from geometry_diagrams.ir.to_svg import ir_to_svg

    d = _figure()
    root = ET.fromstring(ir_to_svg(d, compile_defs(d)))
    (outline,) = [e for e in root.iter() if e.get("data-ir-id") == "E" and e.get("data-type") == "ellipse"]
    dots = {e.get("data-ir-id"): (float(e.get("cx")), float(e.get("cy"))) for e in root.iter() if e.get("data-type") == "point"}
    phi, ox, oy = (float(v) for v in re.fullmatch(r"rotate\(([-\d.]+) ([-\d.]+) ([-\d.]+)\)", outline.get("transform")).groups())
    rx, ry = float(outline.get("rx")), float(outline.get("ry"))
    c, s = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    for pid in ("X", "Y", "Z"):
        dx, dy = dots[pid][0] - ox, dots[pid][1] - oy
        u, v = dx * c + dy * s, -dx * s + dy * c  # the element's own frame (SVG rotate is clockwise on screen)
        assert (u / rx) ** 2 + (v / ry) ** 2 == pytest.approx(1.0, abs=2e-3), pid


def test_figure_tikz_points_sit_on_the_tilted_outline_at_equal_units():
    import re

    from geometry_diagrams.ir.to_tikz import ir_to_tikz

    d = _figure()
    tikz = ir_to_tikz(d, compile_defs(d))
    assert "\\draw[rotate around={30:(1,2)}] (1,2) ellipse (3 and 1);" in tikz
    pts = {m[2]: (float(m[0]), float(m[1])) for m in re.findall(r"\\tkzDefPoint\(([-\d.e]+),([-\d.e]+)\)\{([^}]+)\}", tikz)}
    for pid in ("X", "Y", "Z"):  # Z is where the tangent line T touches the ellipse
        assert abs(implicit(*pts[pid])) < 1e-4, pid
    # the drawn tangent line (P to its helper point) passes through the touch point Z
    (px, py), (qx, qy), (zx, zy) = pts["P"], pts["_lp_T"], pts["Z"]
    assert abs((qx - px) * (zy - py) - (qy - py) * (zx - px)) < 1e-3
