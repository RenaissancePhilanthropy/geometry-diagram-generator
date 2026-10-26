"""Circular arcs/sectors with an explicit ``radius``: start and end are only
directions from the centre, and the compiled marker carries the explicit radius
plus a start (and end) that really lies on that circle. The elliptical kinds
likewise snap an off-curve start/end onto the ellipse.

Expectations are computed here from the geometry (centre, radius, direction),
never read back from the code under test; the renderers are read only through
their output (SVG path attributes, emitted TikZ source).
"""
from __future__ import annotations

import json
import math
import re

import pytest
import sympy as sp

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.checks import run_checks
from geometry_diagrams.ir.errors import ExprEvalError, IRCompileError
from geometry_diagrams.ir.queries import query_length, query_radius
from geometry_diagrams.ir.refs import def_references
from geometry_diagrams.ir.to_svg import ir_to_svg
from geometry_diagrams.ir.to_sympy import Arc, Sector, compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz
from geometry_diagrams.strategies.structured import dispatch_query

CANVAS = {"xmin": -8, "xmax": 8, "ymin": -8, "ymax": 8}


def _pt(pid, x, y):
    return {"id": pid, "kind": "point_fixed", "x": x, "y": y}


def _diagram(define, render=(), checks=()):
    return ir.DiagramIR.model_validate(
        {"canvas": CANVAS, "define": list(define), "render": list(render), "checks": list(checks)}
    )


def _arc(kind="arc_center_start_end", **kw):
    return {"id": "A", "kind": kind, "center": "O", "start": "S", "end": "E", **kw}


# O at origin; S far from radius 3 (distance 10 along +x); E at 60 deg, far out.
BASE = [_pt("O", 0, 0), _pt("S", 10, 0), _pt("E", 8, 8 * math.sqrt(3))]


def _xy(p):
    return float(p.x.evalf()), float(p.y.evalf())


# ---------------------------------------------------------------------------
# Compile semantics
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind,cls", [
    ("arc_center_start_end", Arc), ("sector_center_start_end", Sector),
])
def test_radius_makes_start_and_end_directions(kind, cls):
    sym = compile_defs(_diagram(BASE + [_arc(kind, radius=3)]))
    a = sym["A"]
    assert isinstance(a, cls)
    assert float(a.radius.evalf()) == pytest.approx(3.0)
    sx, sy = _xy(a.start)
    ex, ey = _xy(a.end)
    assert (sx, sy) == pytest.approx((3.0, 0.0))
    assert (ex, ey) == pytest.approx((3 * math.cos(math.pi / 3), 3 * math.sin(math.pi / 3)))


def test_exact_inputs_snap_exactly():
    sym = compile_defs(_diagram([_pt("O", 1, 1), _pt("S", 4, 5), _pt("E", 1, 9),
                                 _arc(radius=10)]))
    # |S - O| = 5, direction (3/5, 4/5) -> start O + 10*(3/5, 4/5) = (7, 9)
    assert sym["A"].start == sp.Point(7, 9)
    assert sym["A"].end == sp.Point(1, 11)


def test_start_on_circle_is_used_unchanged():
    d_with = _diagram([_pt("O", 0, 0), _pt("S", 3, 0), _pt("E", 0, 3), _arc(radius=3)])
    d_without = _diagram([_pt("O", 0, 0), _pt("S", 3, 0), _pt("E", 0, 3), _arc()])
    sym_with = compile_defs(d_with)
    with_r, without = sym_with["A"], compile_defs(d_without)["A"]
    assert with_r.start is sym_with["S"] and with_r.end is sym_with["E"]
    assert (with_r.start, with_r.end, with_r.radius, with_r.reflex) == (
        without.start, without.end, without.radius, without.reflex)


def test_start_on_circle_within_tolerance_keeps_the_original_object():
    d = _diagram([_pt("O", 0, 0), _pt("S", 3.0000000001, 0), _pt("E", 0, 3), _arc(radius=3)])
    sym = compile_defs(d)
    assert sym["A"].start is sym["S"]


@pytest.mark.parametrize("kind", ["arc_center_start_end", "sector_center_start_end"])
@pytest.mark.parametrize("radius", ["0", "1 - 3"])
def test_non_positive_radius_is_a_compile_error_naming_the_def(kind, radius):
    with pytest.raises(IRCompileError) as ei:
        compile_defs(_diagram(BASE + [_arc(kind, radius=radius)]))
    assert ei.value.def_id == "A"
    assert "radius" in str(ei.value)


@pytest.mark.parametrize("kind", ["arc_center_start_end", "sector_center_start_end"])
def test_start_at_centre_is_a_compile_error(kind):
    d = _diagram([_pt("O", 0, 0), _pt("S", 0, 0), _pt("E", 1, 1), _arc(kind, radius=2)])
    with pytest.raises(IRCompileError) as ei:
        compile_defs(d)
    assert ei.value.def_id == "A"
    assert "start" in str(ei.value)


def test_end_at_centre_is_a_compile_error():
    d = _diagram([_pt("O", 0, 0), _pt("S", 1, 0), _pt("E", 0, 0), _arc(radius=2)])
    with pytest.raises(IRCompileError) as ei:
        compile_defs(d)
    assert ei.value.def_id == "A"


def test_numeric_non_positive_radius_rejected_by_schema():
    with pytest.raises(ValueError):
        ir.ArcCenterStartEnd(id="A", center="O", start="S", end="E", radius=0)
    with pytest.raises(ValueError):
        ir.SectorCenterStartEnd(id="A", center="O", start="S", end="E", radius=-1)


# ---------------------------------------------------------------------------
# reflex / bulge_toward evaluated on the corrected circle
# ---------------------------------------------------------------------------

def test_reflex_selects_the_major_arc_on_the_corrected_circle():
    minor = compile_defs(_diagram(BASE + [_arc(radius=3)]))["A"]
    major = compile_defs(_diagram(BASE + [_arc(radius=3, reflex=True)]))["A"]
    assert not minor.reflex and major.reflex
    assert (major.start, major.end) == (minor.start, minor.end)


def test_bulge_toward_antipodal_picks_the_requested_side():
    # S and E are in opposite directions from O, so both arcs are 180 degrees.
    pts = [_pt("O", 0, 0), _pt("S", 9, 0), _pt("E", -7, 0), _pt("UP", 0, 1), _pt("DN", 0, -1)]
    up = compile_defs(_diagram(pts + [_arc(radius=2, bulge_toward="UP")]))["A"]
    dn = compile_defs(_diagram(pts + [_arc(radius=2, bulge_toward="DN")]))["A"]
    assert up.reflex != dn.reflex
    # Going CCW from (2, 0) to (-2, 0) passes through (0, 2): the "up" arc.
    assert up.reflex is False and dn.reflex is True


# ---------------------------------------------------------------------------
# Dependency ordering
# ---------------------------------------------------------------------------

def test_radius_expression_names_are_dependencies():
    stmt = ir.ArcCenterStartEnd(id="A", center="O", start="S", end="E", radius="radius(K) + 1")
    assert {"K", "O", "S", "E"} <= def_references(stmt)


@pytest.mark.parametrize("expr,expected", [
    ("radius(K)", 2.0),
    ("length(P, Q)", 5.0),
    ("2 * radius(K) + length(P, Q) / 5", 5.0),
])
def test_radius_expression_with_arc_listed_before_its_dependencies(expr, expected):
    defs = [
        _arc(radius=expr),
        {"id": "K", "kind": "circle_center_radius", "center": "O", "radius": 2},
        _pt("P", 0, 0), _pt("Q", 3, 4),
    ] + BASE
    sym = compile_defs(_diagram(defs))
    assert float(sym["A"].radius.evalf()) == pytest.approx(expected)
    assert math.hypot(*_xy(sym["A"].start)) == pytest.approx(expected)


def test_radius_referencing_something_undefined_is_the_usual_error():
    with pytest.raises(ExprEvalError) as ei:
        compile_defs(_diagram(BASE + [_arc(radius="radius(NOPE)")]))
    assert ei.value.def_id == "A" and "NOPE" in str(ei.value)


# ---------------------------------------------------------------------------
# Downstream consumers see one consistent circle
# ---------------------------------------------------------------------------

R = 3.0


def _consumer_diagram(extra_defs=(), checks=(), render=()):
    defs = BASE + [
        _arc(radius=R),
        # the same circle built the old way: start already on it
        _pt("S2", 3, 0),
        {"id": "OLD", "kind": "arc_center_start_end", "center": "O", "start": "S2", "end": "E"},
        {"id": "K", "kind": "circle_center_radius", "center": "O", "radius": 3},
        *extra_defs,
    ]
    return _diagram(defs, render=render, checks=checks)


def _point_on_arc(t):
    return {"id": f"P{int(t)}", "kind": "point_on", "on": "A",
            "how": {"kind": "param", "t": t}}


def test_point_on_param_ends_land_on_the_radius():
    sym = compile_defs(_consumer_diagram([_point_on_arc(0.0), _point_on_arc(1.0)]))
    p0, p1 = _xy(sym["P0"]), _xy(sym["P1"])
    assert math.hypot(*p0) == pytest.approx(R) and math.hypot(*p1) == pytest.approx(R)
    assert p0 == pytest.approx((R, 0.0))
    assert p1 == pytest.approx((R * math.cos(math.pi / 3), R * math.sin(math.pi / 3)))


def test_contains_accepts_on_circle_point_and_rejects_the_raw_start():
    mid = {"id": "M", "kind": "point_on", "on": "A", "how": {"kind": "param", "t": 0.5}}
    res = run_checks(
        [ir.Contains(p="M", obj="A"), ir.Contains(p="S", obj="A")],
        compile_defs(_consumer_diagram([mid])),
    )
    assert [r.passed for r in res] == [True, False]


def test_intersection_with_a_line_lies_on_the_corrected_circle():
    defs = [
        _pt("L1", 2, -5), _pt("L2", 2, 5),
        {"id": "LN", "kind": "line_through", "p": "L1", "q": "L2"},
        {"id": "X", "kind": "point_intersection", "obj1": "A", "obj2": "LN",
         "pick": {"kind": "closest_to", "p": "S2"}},
    ]
    sym = compile_defs(_consumer_diagram(defs))
    x, y = _xy(sym["X"])
    assert (x, y) == pytest.approx((2.0, math.sqrt(R * R - 4)))


def test_tangent_from_an_external_point_touches_the_corrected_circle():
    defs = [
        _pt("EXT", 6, 0),
        {"id": "T", "kind": "line_tangent", "point": "EXT", "circle": "A"},
    ]
    sym = compile_defs(_consumer_diagram(defs))
    line = sym["T"]
    # a tangent line is at distance r from the centre
    assert float(line.distance(sp.Point(0, 0)).evalf()) == pytest.approx(R)


def test_length_radius_queries_and_equal_radius_and_congruent_arcs():
    sym = compile_defs(_consumer_diagram())
    assert query_radius(sym, "A")["radius"] == pytest.approx(R)
    res = run_checks(
        [ir.EqualRadius(circles=["A", "OLD", "K"]), ir.CongruentArcs(arcs=["A", "OLD"])],
        sym,
    )
    assert [r.passed for r in res] == [True, True]


# ---------------------------------------------------------------------------
# Renderers: the emitted outline lies on the intended circle
# ---------------------------------------------------------------------------

def _svg_arc_paths(svg):
    return re.findall(r'<path[^>]*data-type="(?:arc|sector)"[^>]*\sd="([^"]+)"', svg)


def _svg_numbers(path):
    return [float(n) for n in re.findall(r"-?\d+\.?\d*", path)]


def test_svg_arc_outline_is_on_the_intended_circle():
    d = _diagram(BASE + [_arc(radius=3)], render=[{"kind": "draw", "obj": "A"}])
    (path,) = _svg_arc_paths(ir_to_svg(d, compile_defs(d)))
    sx, sy, rx, ry, _rot, _large, _sweep, ex, ey = _svg_numbers(path)
    assert rx == pytest.approx(ry)
    # The start is the circle point at angle 0, so the centre is rx to its left;
    # the end must then sit at 60 degrees on the same circle (SVG y points down).
    cx, cy = sx - rx, sy
    assert math.hypot(ex - cx, ey - cy) == pytest.approx(rx, abs=0.02)
    assert math.degrees(math.atan2(-(ey - cy), ex - cx)) == pytest.approx(60, abs=0.2)


def test_svg_sector_outline_is_on_the_intended_circle():
    d = _diagram(BASE + [_arc("sector_center_start_end", radius=3)],
                 render=[{"kind": "draw", "obj": "A"}])
    (path,) = _svg_arc_paths(ir_to_svg(d, compile_defs(d)))
    cx, cy, lx, ly, rx, ry, _rot, _large, _sweep, ex, ey, cx2, cy2 = _svg_numbers(path)
    assert (cx2, cy2) == (cx, cy)
    assert math.hypot(lx - cx, ly - cy) == pytest.approx(rx, abs=0.02)
    assert math.hypot(ex - cx, ey - cy) == pytest.approx(rx, abs=0.02)
    assert math.degrees(math.atan2(-(ly - cy), lx - cx)) == pytest.approx(0, abs=0.2)
    assert math.degrees(math.atan2(-(ey - cy), ex - cx)) == pytest.approx(60, abs=0.2)


TIKZ_ARC = re.compile(
    r"\(([-\d.]+),([-\d.]+)\) arc\[start angle=([-\d.]+),end angle=([-\d.]+),radius=([-\d.]+)\]")


def test_tikz_arc_starts_on_the_circle_with_the_explicit_radius():
    d = _diagram(BASE + [_arc(radius=3)], render=[{"kind": "draw", "obj": "A"}])
    tikz = ir_to_tikz(d, compile_defs(d))
    m = TIKZ_ARC.search(tikz)
    assert m, tikz
    sx, sy, s_deg, e_deg, r = (float(v) for v in m.groups())
    assert r == pytest.approx(3.0)
    assert (sx, sy) == pytest.approx((3.0, 0.0), abs=1e-4)
    assert (s_deg, e_deg) == pytest.approx((0.0, 60.0), abs=1e-3)


def test_tikz_sector_starts_on_the_circle_with_the_explicit_radius():
    d = _diagram(BASE + [_arc("sector_center_start_end", radius=3)],
                 render=[{"kind": "draw", "obj": "A"}])
    tikz = ir_to_tikz(d, compile_defs(d))
    m = re.search(r"-- \(([-\d.]+),([-\d.]+)\) arc\[start angle=([-\d.]+),end angle=([-\d.]+),radius=([-\d.]+)\]", tikz)
    assert m, tikz
    sx, sy, s_deg, e_deg, r = (float(v) for v in m.groups())
    assert r == pytest.approx(3.0) and (sx, sy) == pytest.approx((3.0, 0.0), abs=1e-4)
    assert (s_deg, e_deg) == pytest.approx((0.0, 60.0), abs=1e-3)


def test_reflex_arc_tikz_starts_on_the_circle_even_when_endpoints_swap():
    """reflex swaps start and end for the CCW sweep; the swapped-in point is the
    END, which must be on the circle too."""
    d = _diagram(BASE + [_arc(radius=3, reflex=True)], render=[{"kind": "draw", "obj": "A"}])
    tikz = ir_to_tikz(d, compile_defs(d))
    m = TIKZ_ARC.search(tikz)
    sx, sy, s_deg, e_deg, r = (float(v) for v in m.groups())
    assert math.hypot(sx, sy) == pytest.approx(3.0, abs=1e-3)
    assert (s_deg, e_deg) == pytest.approx((60.0, 360.0), abs=1e-3)


def test_arc_tick_and_text_along_arc_render_on_the_corrected_circle():
    ticks = {"kind": "mark_arcs", "arcs": ["A"], "ticks": 1}
    text = {"kind": "label_along_arc", "arc": "A", "text": "ab", "side": "outside"}
    d = _diagram(BASE + [_arc(radius=3)],
                 render=[{"kind": "draw", "obj": "A"}, ticks, text])
    d_ref = _diagram([_pt("O", 0, 0), _pt("S", 3, 0), _pt("E", 8, 8 * math.sqrt(3)), _arc()],
                     render=[{"kind": "draw", "obj": "A"}, ticks, text])
    # Same circle, same sweep: tick and glyph positions are those of the arc
    # built the old way (start already on the circle).
    svg, svg_ref = ir_to_svg(d, compile_defs(d)), ir_to_svg(d_ref, compile_defs(d_ref))
    assert _svg_arc_paths(svg) == _svg_arc_paths(svg_ref)
    tick_re = re.compile(r"<line[^>]*/>|<text[^>]*>[^<]*</text>")
    assert tick_re.findall(svg) == tick_re.findall(svg_ref)
    def body(tikz):  # the bounds (tkzInit) and point definitions differ by the far start
        return [ln for ln in tikz.splitlines() if not ln.startswith(("\\tkzInit", "\\tkzDefPoint"))]

    assert body(ir_to_tikz(d, compile_defs(d))) == body(ir_to_tikz(d_ref, compile_defs(d_ref)))


# ---------------------------------------------------------------------------
# Elliptical kinds: an off-curve start/end is snapped onto the ellipse
# ---------------------------------------------------------------------------

ELL = [_pt("O", 0, 0), _pt("S", 10, 0), _pt("E", 0, 9)]


@pytest.mark.parametrize("kind", [
    "elliptical_arc_center_start_end", "elliptical_sector_center_start_end"])
def test_elliptical_off_curve_start_and_end_land_on_the_ellipse(kind):
    d = _diagram(ELL + [_arc(kind, hradius=4, vradius=2)], render=[{"kind": "draw", "obj": "A"}])
    a = compile_defs(d)["A"]
    sx, sy = _xy(a.start)
    ex, ey = _xy(a.end)
    # parametric angle of S is 0, of E is 90 degrees
    assert (sx, sy) == pytest.approx((4.0, 0.0))
    assert (ex, ey) == pytest.approx((0.0, 2.0))


def test_elliptical_arc_draws_from_the_curve_in_both_renderers():
    d = _diagram(ELL + [_arc("elliptical_arc_center_start_end", hradius=4, vradius=2)],
                 render=[{"kind": "draw", "obj": "A"}])
    sym = compile_defs(d)
    tikz = ir_to_tikz(d, sym)
    assert r"\draw (4,0) arc[start angle=0,end angle=90,x radius=4,y radius=2];" in tikz
    (path,) = _svg_arc_paths(ir_to_svg(d, sym))
    sx, sy, rx, ry, _rot, _large, _sweep, ex, ey = _svg_numbers(path)
    # The start is the curve point at parametric angle 0 and the end the one at
    # 90 degrees, so the end is rx left of and ry above the start.
    assert (ex, ey) == pytest.approx((sx - rx, sy - ry), abs=0.02)


def test_elliptical_on_curve_start_is_unchanged():
    d = _diagram([_pt("O", 0, 0), _pt("S", 4, 0), _pt("E", 0, 2),
                  _arc("elliptical_arc_center_start_end", hradius=4, vradius=2)])
    sym = compile_defs(d)
    assert sym["A"].start is sym["S"] and sym["A"].end is sym["E"]


# ---------------------------------------------------------------------------
# Length queries (curved edge), through dispatch_query and query_length
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["arc_center_start_end", "sector_center_start_end"])
def test_length_query_is_the_curved_edge_of_the_corrected_circle(kind):
    sym = compile_defs(_diagram(BASE + [_arc(kind, radius=3)]))
    expected = 3 * math.pi / 3  # radius 3 times a 60 degree sweep
    assert json.loads(dispatch_query(sym, "length", {"segment": "A"}))["length"] == pytest.approx(expected)
    assert query_length(sym, "A")["length"] == pytest.approx(expected)


def test_reflex_length_query_is_the_major_arc():
    sym = compile_defs(_diagram(BASE + [_arc(radius=3, reflex=True)]))
    assert query_length(sym, "A")["length"] == pytest.approx(3 * (2 * math.pi - math.pi / 3))


# ---------------------------------------------------------------------------
# No radius: `end` is only a direction, even when the sweep swaps endpoints
# ---------------------------------------------------------------------------

# O=(0,0), S=(0,3) on the circle, E=(7,0) far off it: direction 0 degrees.
# The CCW sweep from S (90 deg) to E (0 deg) is 270, so the minor arc swaps
# the endpoints and the raw E used to be drawn from.
NO_RADIUS = [_pt("O", 0, 0), _pt("S", 0, 3), _pt("E", 7, 0)]


@pytest.mark.parametrize("kind", ["arc_center_start_end", "sector_center_start_end"])
def test_no_radius_off_circle_end_is_snapped_in_compile(kind):
    sym = compile_defs(_diagram(NO_RADIUS + [_arc(kind)]))
    assert _xy(sym["A"].end) == pytest.approx((3.0, 0.0))
    assert sym["A"].start is sym["S"]


@pytest.mark.parametrize("kind", ["arc_center_start_end", "sector_center_start_end"])
def test_no_radius_swapped_endpoints_draw_on_the_circle_in_tikz(kind):
    d = _diagram(NO_RADIUS + [_arc(kind)], render=[{"kind": "draw", "obj": "A"}])
    m = re.search(r"\(([-\d.]+),([-\d.]+)\) arc\[start angle=([-\d.]+),end angle=([-\d.]+),radius=([-\d.]+)\]",
                  ir_to_tikz(d, compile_defs(d)))
    sx, sy, s_deg, e_deg, r = (float(v) for v in m.groups())
    assert r == pytest.approx(3.0)
    assert (sx, sy) == pytest.approx((3.0, 0.0), abs=1e-4)  # the swapped-in end, on the circle
    assert (s_deg, e_deg) == pytest.approx((0.0, 90.0), abs=1e-3)


def test_no_radius_swapped_endpoints_draw_on_the_circle_in_svg():
    d = _diagram(NO_RADIUS + [_arc()], render=[{"kind": "draw", "obj": "A"}])
    (path,) = _svg_arc_paths(ir_to_svg(d, compile_defs(d)))
    sx, sy, rx, ry, _rot, _large, _sweep, ex, ey = _svg_numbers(path)
    # start is the circle point at angle 0, end the one at 90 degrees (y down)
    assert (ex, ey) == pytest.approx((sx - rx, sy - ry), abs=0.02)


# ---------------------------------------------------------------------------
# Centre-coincident and near-centre endpoints
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role,pts", [
    ("start", [_pt("O", 0, 0), _pt("S", 0, 0), _pt("E", 1, 1)]),
    ("end", [_pt("O", 0, 0), _pt("S", 1, 0), _pt("E", 0, 0)]),
])
@pytest.mark.parametrize("kind", [
    "elliptical_arc_center_start_end", "elliptical_sector_center_start_end"])
def test_elliptical_endpoint_at_centre_is_a_compile_error(kind, role, pts):
    with pytest.raises(IRCompileError) as ei:
        compile_defs(_diagram(pts + [_arc(kind, hradius=4, vradius=2)]))
    assert ei.value.def_id == "A" and role in str(ei.value)


def test_float_start_within_noise_of_the_centre_counts_as_the_centre():
    d = _diagram([_pt("O", 0, 0), _pt("S", 1e-13, -1e-13), _pt("E", 1, 1), _arc(radius=2)])
    with pytest.raises(IRCompileError) as ei:
        compile_defs(d)
    assert ei.value.def_id == "A" and "start" in str(ei.value)


def test_small_but_real_offset_from_the_centre_is_a_direction():
    d = _diagram([_pt("O", 0, 0), _pt("S", 1e-3, 0), _pt("E", 1, 1), _arc(radius=2)])
    assert _xy(compile_defs(d)["A"].start) == pytest.approx((2.0, 0.0))
