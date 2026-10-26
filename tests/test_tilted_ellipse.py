"""Tilted (rotated) full ellipses, stage 1 of the rotated-ellipses design
(docs/specs/2026-10-25-rotated-ellipses-design.md): the ``rotation_deg`` field,
the ``RotatedEllipse`` compiled marker and its frame, placement, containment,
the radius checks and measures, canvas bounds, and both renderers (SVG
under a non-unit aspect: test_tilted_ellipse_svg_aspect.py). Tangents and intersections are in
test_tilted_ellipse_intersections.py.

Expected values are derived by hand from the rotation matrix, not from the
code under test."""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from random import Random

import pytest
import sympy as sp
import sympy.geometry as spg

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.checks import run_checks
from geometry_diagrams.ir.curve_measures import curve_length
from geometry_diagrams.ir.errors import IRCompileError, PickError
from geometry_diagrams.ir.queries import query_area, query_length, query_perimeter, query_radius
from geometry_diagrams.ir.refs import def_references
from geometry_diagrams.ir.render_util import BOUNDS_PADDING, centroid_of_obj, expand_bounds_for_geometry
from geometry_diagrams.ir.to_sympy import (
    RotatedEllipse,
    _apply_pick,
    _eval_param,
    _invert_param,
    _sample_param,
    compile_defs,
)
from geometry_diagrams.ir.to_svg import ir_to_svg
from geometry_diagrams.ir.to_tikz import ir_to_tikz

CX, CY, HR, VR, DEG = 1.0, 2.0, 3.0, 1.0, 30.0
C30, S30 = math.cos(math.radians(DEG)), math.sin(math.radians(DEG))


def _defs(rotation=DEG, *, extra=()):
    return [
        ir.PointFixed(id="O", x=CX, y=CY),
        ir.EllipseCenterAxes(id="E", center="O", hradius=HR, vradius=VR, rotation_deg=rotation),
        *extra,
    ]


def _diagram(rotation=DEG, *, extra=(), render=(), checks=(), canvas=None) -> ir.DiagramIR:
    return ir.DiagramIR(
        canvas=canvas, define=_defs(rotation, extra=extra), render=list(render), checks=list(checks)
    )


def _xy(p) -> tuple[float, float]:
    return float(p.x), float(p.y)


def _on_tilted_curve(x: float, y: float) -> float:
    """Implicit value of the hand-written tilted equation (0 on the curve)."""
    dx, dy = x - CX, y - CY
    u = dx * C30 + dy * S30
    v = -dx * S30 + dy * C30
    return (u / HR) ** 2 + (v / VR) ** 2 - 1.0


# --- IR ------------------------------------------------------------------------

def test_rotation_deg_defaults_to_zero_and_is_dumped():
    stmt = ir.EllipseCenterAxes(id="E", center="O", hradius=3, vradius=1)
    assert stmt.rotation_deg == 0
    assert stmt.model_dump()["rotation_deg"] == 0
    ecc = ir.EllipseCenterEccentricity(id="F", center="O", semi_major=2, eccentricity=0.5)
    assert ecc.model_dump()["rotation_deg"] == 0


def test_rotation_expression_names_are_dependencies_and_order_after_points():
    stmt = ir.EllipseCenterAxes(id="E", center="O", hradius=3, vradius=1, rotation_deg="angle(X, O, F)")
    assert {"X", "O", "F"} <= def_references(stmt)
    # The ellipse comes first in the list; the topological sort still places
    # it after the points its rotation expression names.
    diagram = ir.DiagramIR(define=[
        stmt,
        ir.PointFixed(id="O", x=0, y=0),
        ir.PointFixed(id="X", x=1, y=0),
        ir.PointFixed(id="F", x=1, y=1),
    ])
    e = compile_defs(diagram)["E"]
    assert isinstance(e, RotatedEllipse)
    assert e.rotation == pytest.approx(math.pi / 4, abs=1e-12)


# --- compile -------------------------------------------------------------------

@pytest.mark.parametrize("rotation", [0, 0.0, 360, "0", "360 - 360"])
def test_zero_rotation_compiles_to_todays_sympy_ellipse(rotation):
    sym = compile_defs(_diagram(rotation))
    untilted = compile_defs(ir.DiagramIR(define=[
        ir.PointFixed(id="O", x=CX, y=CY), ir.EllipseCenterAxes(id="E", center="O", hradius=HR, vradius=VR),
    ]))
    assert type(sym["E"]) is spg.Ellipse
    assert sym["E"] == untilted["E"]


def test_nonzero_rotation_compiles_to_marker_with_float_radians():
    e = compile_defs(_diagram(30))["E"]
    assert isinstance(e, RotatedEllipse)
    assert not isinstance(e, spg.Ellipse)
    assert type(e.rotation) is float
    assert e.rotation == pytest.approx(math.pi / 6, abs=1e-15)
    assert _xy(e.center) == (CX, CY)
    assert float(e.hradius) == HR and float(e.vradius) == VR


def test_rotation_is_reduced_mod_360_and_never_symbolic():
    e = compile_defs(_diagram(390))["E"]
    assert e.rotation == pytest.approx(math.pi / 6, abs=1e-12)
    e = compile_defs(_diagram("37"))["E"]
    assert type(e.rotation) is float
    assert e.rotation == pytest.approx(math.radians(37), abs=1e-15)


def test_equal_radii_with_rotation_stays_a_marker():
    diagram = ir.DiagramIR(define=[
        ir.PointFixed(id="O", x=0, y=0),
        ir.EllipseCenterAxes(id="E", center="O", hradius=2, vradius=2, rotation_deg=45),
    ])
    assert isinstance(compile_defs(diagram)["E"], RotatedEllipse)


def test_eccentricity_rotation_rotates_todays_figure():
    # semi_major 2, e = 0.6 -> b = 1.6. Vertical today has hradius = b along x;
    # tilted by 30 degrees it keeps that naming and turns the whole figure.
    for orientation, (hr, vr) in (("horizontal", (2.0, 1.6)), ("vertical", (1.6, 2.0))):
        diagram = ir.DiagramIR(define=[
            ir.PointFixed(id="O", x=0, y=0),
            ir.EllipseCenterEccentricity(id="E", center="O", semi_major=2, eccentricity=0.6,
                                         orientation=orientation, rotation_deg=30),
        ])
        e = compile_defs(diagram)["E"]
        assert isinstance(e, RotatedEllipse)
        assert float(e.hradius) == pytest.approx(hr) and float(e.vradius) == pytest.approx(vr)
        assert e.rotation == pytest.approx(math.pi / 6)


def test_tilted_foci_still_raise_the_axis_aligned_error():
    diagram = ir.DiagramIR(define=[
        ir.PointFixed(id="F1", x=0, y=0),
        ir.PointFixed(id="F2", x=2, y=1),
        ir.EllipseFoci(id="E", focus1="F1", focus2="F2", major_axis=6),
    ])
    with pytest.raises(IRCompileError, match="axis-aligned"):
        compile_defs(diagram)


# --- point_on, random placement, pinning ---------------------------------------

def test_point_on_param_lands_at_the_tilted_axis_ends():
    sym = compile_defs(_diagram(extra=[
        ir.PointOn(id="A", on="E", how=ir.PointOnParam(t=0)),
        ir.PointOn(id="B", on="E", how=ir.PointOnParam(t="pi/2")),
    ]))
    ax, ay = _xy(sym["A"])
    bx, by = _xy(sym["B"])
    assert (ax, ay) == pytest.approx((CX + HR * C30, CY + HR * S30), abs=1e-12)
    assert (bx, by) == pytest.approx((CX - VR * S30, CY + VR * C30), abs=1e-12)


def test_random_placement_samples_the_full_turn_and_lands_on_the_curve():
    e = compile_defs(_diagram())["E"]
    rng = Random(7)
    ts = [_sample_param(e, rng) for _ in range(200)]
    assert max(ts) > math.pi  # the full-ellipse range, not [0, 1)
    sym = compile_defs(_diagram(extra=[
        ir.PointOn(id=f"P{i}", on="E", how=ir.PointOnRandom()) for i in range(10)
    ]))
    for i in range(10):
        assert abs(_on_tilted_curve(*_xy(sym[f"P{i}"]))) < 1e-12


def test_sampled_point_round_trips_through_the_pinning_path():
    from geometry_diagrams.pydsl.builder import Builder

    diagram = _diagram(extra=[ir.PointOn(id="P", on="E", how=ir.PointOnIntent(constraints=[]))])
    sym = compile_defs(diagram)
    p = sym["P"]
    e = sym["E"]
    t = _invert_param(e, float(p.x), float(p.y), "P")
    assert _xy(_eval_param(e, t, "P")) == pytest.approx(_xy(p), abs=1e-12)

    builder = Builder()
    builder._sym = dict(sym)
    stmt = diagram.define[-1].model_copy()
    builder._pin_point_on(stmt, p)
    assert isinstance(stmt.how, ir.PointOnParam)
    pinned = compile_defs(diagram.model_copy(update={"define": [*diagram.define[:-1], stmt]}))["P"]
    assert _xy(pinned) == pytest.approx(_xy(p), abs=1e-12)


# --- containment and pick_on_object --------------------------------------------

def _twin_point() -> tuple[float, float]:
    """The untilted twin's t = 0 point: on the axis-aligned ellipse, off the tilted one."""
    return CX + HR, CY


def test_contains_accepts_tilted_curve_points_and_rejects_the_untilted_twins():
    tx, ty = _twin_point()
    assert abs(_on_tilted_curve(tx, ty)) > 0.1
    diagram = _diagram(
        extra=[ir.PointOn(id="A", on="E", how=ir.PointOnParam(t=1.1)), ir.PointFixed(id="T", x=tx, y=ty)],
        checks=[ir.Contains(p="A", obj="E"), ir.NotContains(p="T", obj="E")],
    )
    results = run_checks(diagram.checks, compile_defs(diagram))
    assert [r.passed for r in results] == [True, True], [r.message for r in results]


def test_pick_on_object_picks_the_on_curve_candidate():
    sym = compile_defs(_diagram(extra=[ir.PointOn(id="A", on="E", how=ir.PointOnParam(t=2.0))]))
    twin = spg.Point(sp.Float(_twin_point()[0]), sp.Float(_twin_point()[1]))
    on = sym["A"]
    assert _apply_pick([twin, on], ir.PickOnObject(obj="E"), sym, "X") is on
    with pytest.raises(PickError, match="no candidate lies on 'E'"):
        _apply_pick([twin], ir.PickOnObject(obj="E"), sym, "X")


def test_pick_on_object_tolerance_is_a_length():
    # A long, thin tilted ellipse: a point 1e-3 off the curve along its normal is
    # rejected, a point on the curve is accepted (a dimensionless implicit test
    # would get this wrong by a factor of about a / b).
    diagram = ir.DiagramIR(define=[
        ir.PointFixed(id="O", x=0, y=0),
        ir.EllipseCenterAxes(id="E", center="O", hradius=1000, vradius=0.01, rotation_deg=30),
        ir.PointOn(id="A", on="E", how=ir.PointOnParam(t=0.3)),
    ])
    sym = compile_defs(diagram)
    a = sym["A"]
    on = _apply_pick([a], ir.PickOnObject(obj="E"), sym, "X")
    assert on is a
    # normal at t: local (cos t / a, sin t / b) direction, rotated by 30 degrees
    t = 0.3
    nu, nv = math.cos(t) / 1000, math.sin(t) / 0.01
    n = math.hypot(nu, nv)
    nx, ny = (nu * C30 - nv * S30) / n, (nu * S30 + nv * C30) / n
    off = spg.Point(sp.Float(float(a.x) + 1e-3 * nx), sp.Float(float(a.y) + 1e-3 * ny))
    with pytest.raises(PickError, match="no candidate lies on"):
        _apply_pick([off], ir.PickOnObject(obj="E"), sym, "X")


# --- radius checks and measures ------------------------------------------------

def _tilted_and_twin(hr=HR, vr=VR):
    diagram = ir.DiagramIR(define=[
        ir.PointFixed(id="O", x=CX, y=CY),
        ir.EllipseCenterAxes(id="T", center="O", hradius=hr, vradius=vr, rotation_deg=DEG),
        ir.EllipseCenterAxes(id="U", center="O", hradius=hr, vradius=vr),
    ])
    return compile_defs(diagram)


def test_radius_checks_match_the_untilted_twin():
    sym = _tilted_and_twin()
    for ok_check, expected in (
        (ir.EqualRadius(circles=["T", "U"]), True),
        (ir.RadiusEquals(circle="T", expected=3), False),
        (ir.RadiusEquals(circle="U", expected=3), False),
    ):
        (res,) = run_checks([ok_check], sym)
        assert res.passed is expected, res.message
    t_msg = run_checks([ir.RadiusEquals(circle="T", expected=3)], sym)[0].message
    u_msg = run_checks([ir.RadiusEquals(circle="U", expected=3)], sym)[0].message
    assert t_msg == u_msg.replace("'U'", "'T'")
    assert "two radii" in t_msg
    # a tilted ellipse with equal radii is circular for the radius checks
    circ = _tilted_and_twin(2, 2)
    assert run_checks([ir.RadiusEquals(circle="T", expected=2)], circ)[0].passed


def test_queries_and_curve_length_match_the_untilted_twin():
    sym = _tilted_and_twin()
    assert query_radius(sym, "T") == query_radius(sym, "U") == {"hradius": 3.0, "vradius": 1.0}
    assert query_area(sym, "T") == query_area(sym, "U")
    assert query_area(sym, "T")["area"] == pytest.approx(3 * math.pi)
    assert query_perimeter(sym, "T") == query_perimeter(sym, "U")
    assert curve_length(sym["T"]) == curve_length(sym["U"])
    with pytest.raises(TypeError, match="full ellipse"):
        query_length(sym, "T")


def test_length_check_rejects_a_full_tilted_ellipse_like_the_twin():
    sym = _tilted_and_twin()
    t = run_checks([ir.DistanceEquals(seg="T", expected=1)], sym)[0]
    u = run_checks([ir.DistanceEquals(seg="U", expected=1)], sym)[0]
    assert not t.passed and t.message == u.message.replace("'U'", "'T'")


def test_centroid_of_a_tilted_ellipse_is_its_center():
    sym = compile_defs(_diagram())
    assert centroid_of_obj(sym["E"]) == pytest.approx((CX, CY))


# --- canvas bounds -------------------------------------------------------------

def test_bounds_cover_the_rotated_extremes_and_no_more():
    sym = compile_defs(_diagram())
    # hand-derived: wx = sqrt(9 cos^2 30 + sin^2 30) = sqrt(7), wy = sqrt(9 sin^2 30 + cos^2 30) = sqrt(3)
    wx, wy = math.sqrt(7), math.sqrt(3)
    xmin, xmax, ymin, ymax = expand_bounds_for_geometry(CX, CX, CY, CY, sym)
    assert xmin == pytest.approx(CX - wx - BOUNDS_PADDING)
    assert xmax == pytest.approx(CX + wx + BOUNDS_PADDING)
    assert ymin == pytest.approx(CY - wy - BOUNDS_PADDING)
    assert ymax == pytest.approx(CY + wy + BOUNDS_PADDING)
    assert xmax - xmin < 2 * (HR + BOUNDS_PADDING)  # narrower than the untilted box


# --- SVG -----------------------------------------------------------------------

def _svg_root(diagram):
    return ET.fromstring(ir_to_svg(diagram, compile_defs(diagram)))


def _by(root, **attrs):
    return [e for e in root.iter() if all(e.get(k) == v for k, v in attrs.items())]


_ROTATE = re.compile(r"rotate\(([-\d.]+) ([-\d.]+) ([-\d.]+)\)")


def test_svg_draws_and_fills_the_tilted_ellipse_at_the_right_angle():
    diagram = _diagram(
        extra=[ir.PointOn(id="A", on="E", how=ir.PointOnParam(t=0)),
               ir.PointOn(id="B", on="E", how=ir.PointOnParam(t="pi/2"))],
        render=[ir.Fill(obj="E", opacity=0.3), ir.Draw(obj="E"), ir.DrawPoints(points=["O", "A", "B"]),
                ir.LabelPoint(p="O", text="O"), ir.LabelPoint(p="A", text="A")],
    )
    root = _svg_root(diagram)
    (outline,) = _by(root, **{"data-ir-id": "E", "data-type": "ellipse"})
    (fill,) = _by(root, **{"data-ir-id": "E", "data-role": "fill"})
    dots = {e.get("data-ir-id"): (float(e.get("cx")), float(e.get("cy"))) for e in _by(root, **{"data-type": "point"})}
    ox, oy = dots["O"]
    for el in (outline, fill):
        assert el.tag.endswith("ellipse")
        phi, rcx, rcy = (float(v) for v in _ROTATE.fullmatch(el.get("transform")).groups())
        assert phi == pytest.approx(-30)  # y-down flips the sign
        assert (float(el.get("cx")), float(el.get("cy"))) == pytest.approx((ox, oy), abs=0.01)
        assert (rcx, rcy) == pytest.approx((ox, oy), abs=0.01)
        rx, ry = float(el.get("rx")), float(el.get("ry"))
        assert rx / ry == pytest.approx(HR / VR, rel=1e-3)
        # The element's own axis ends (+x and, y being down, -y), mapped through
        # its SVG rotate(), land on the compiled t = 0 and t = pi/2 points.
        c, s = math.cos(math.radians(phi)), math.sin(math.radians(phi))
        assert (ox + rx * c, oy + rx * s) == pytest.approx(dots["A"], abs=0.02)
        assert (ox + ry * s, oy - ry * c) == pytest.approx(dots["B"], abs=0.02)


def test_svg_fill_with_holes_uses_the_rotation_in_the_arc_commands():
    diagram = _diagram(
        extra=[ir.PointFixed(id="P", x=CX - 0.3, y=CY - 0.2), ir.PointFixed(id="Q", x=CX + 0.3, y=CY - 0.2),
               ir.PointFixed(id="R", x=CX, y=CY + 0.3), ir.Triangle(id="H", a="P", b="Q", c="R")],
        render=[ir.Fill(obj="E", holes=["H"]), ir.DrawPoints(points=["O"])],
    )
    root = _svg_root(diagram)
    (path,) = _by(root, **{"data-ir-id": "E", "data-role": "fill"})
    d = path.get("d")
    arcs = re.findall(r"A ([-\d.]+) ([-\d.]+) ([-\d.]+) 1 0 ([-\d.]+) ([-\d.]+)", d)
    assert len(arcs) == 2
    (ox, oy), = [(float(e.get("cx")), float(e.get("cy"))) for e in _by(root, **{"data-type": "point"})]
    start = re.match(r"M ([-\d.]+) ([-\d.]+)", d).groups()
    rx = float(arcs[0][0])
    for rx_s, ry_s, phi, *_ in arcs:
        assert float(phi) == pytest.approx(-30)
        assert float(rx_s) / float(ry_s) == pytest.approx(HR / VR, rel=1e-3)
    # the subpath runs between the two ends of the tilted major axis
    c, s = math.cos(math.radians(-30)), math.sin(math.radians(-30))
    assert (float(start[0]), float(start[1])) == pytest.approx((ox - rx * c, oy - rx * s), abs=0.02)
    assert (float(arcs[0][3]), float(arcs[0][4])) == pytest.approx((ox + rx * c, oy + rx * s), abs=0.02)
    assert path.get("fill-rule") == "evenodd"


def test_svg_untilted_ellipse_has_no_transform():
    root = _svg_root(_diagram(0, render=[ir.Draw(obj="E"), ir.Fill(obj="E")]))
    assert all(e.get("transform") is None for e in _by(root, **{"data-ir-id": "E"}))


def test_svg_aspect_one_draws_the_tilted_ellipse():
    diagram = _diagram(render=[ir.Draw(obj="E")], canvas=ir.Canvas(xmin=-3, xmax=5, ymin=-2, ymax=6, aspect=1))
    (el,) = _by(_svg_root(diagram), **{"data-ir-id": "E"})
    assert el.get("transform", "").startswith("rotate(-30")


# --- TikZ ----------------------------------------------------------------------

def test_tikz_draws_and_fills_with_rotate_around():
    diagram = _diagram(render=[ir.Fill(obj="E", opacity=0.3), ir.Draw(obj="E")])
    tikz = ir_to_tikz(diagram, compile_defs(diagram))
    draw = [l for l in tikz.splitlines() if l.startswith("\\draw") and "ellipse" in l]
    fill = [l for l in tikz.splitlines() if l.startswith("\\fill") and "ellipse" in l]
    assert len(draw) == 1 and len(fill) == 1
    for line in draw + fill:
        assert "rotate around={30:(1,2)}" in line
        assert line.endswith("(1,2) ellipse (3 and 1);")


def test_tikz_fill_with_holes_rotates_the_ellipse_path():
    diagram = _diagram(
        extra=[ir.CircleCenterRadius(id="X", center="O", radius=5)],
        render=[ir.Fill(obj="X", holes=["E"])],
    )
    tikz = ir_to_tikz(diagram, compile_defs(diagram))
    (line,) = [l for l in tikz.splitlines() if "even odd rule" in l]
    assert "(1,2) ellipse[x radius=3,y radius=1,rotate=30]" in line


def test_tikz_untilted_ellipse_is_unchanged():
    diagram = _diagram(0, render=[ir.Draw(obj="E")])
    tikz = ir_to_tikz(diagram, compile_defs(diagram))
    assert "\\draw (1,2) ellipse (3 and 1);" in tikz
    assert "rotate" not in tikz


# --- end to end through the shared pipeline -------------------------------------

@pytest.mark.asyncio
async def test_stored_tilted_ir_renders_through_the_svg_pipeline_with_the_group_off():
    from geometry_diagrams.ir.renderer import SVGRenderer
    from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline

    stored = _diagram(
        extra=[ir.PointOn(id="A", on="E", how=ir.PointOnParam(t=0.5))],
        render=[ir.Fill(obj="E", opacity=0.2), ir.Draw(obj="E"), ir.DrawPoints(points=["O", "A"]),
                ir.LabelPoint(p="O", text="O"), ir.LabelPoint(p="A", text="A")],
        checks=[ir.Contains(p="A", obj="E")],
    ).model_dump_json()
    diagram = ir.DiagramIR.model_validate_json(stored)
    result = await run_ir_pipeline(diagram, SVGRenderer())
    assert "rotate(-30" in result.svg
    tikz = ir_to_tikz(diagram, compile_defs(diagram))
    assert "rotate around={30:(1,2)}" in tikz


# --- prompt text -----------------------------------------------------------------

def test_structured_prompt_gets_tilted_guidance_only_with_the_group_on():
    from geometry_diagrams.strategies.instructions_structured import build_structured_instructions

    off = build_structured_instructions()
    on = build_structured_instructions(frozenset({"tilted_ellipses"}))
    assert "rotation_deg" not in off
    assert on.startswith(off) and "rotation_deg" in on and "Tilted ellipses" in on


def test_tilted_prompt_fragment_states_the_true_limits():
    """The gated fragment must not call supported operations errors, and must
    name what is still unsupported (stale text came back once)."""
    from geometry_diagrams.strategies.instructions_structured import _TILTED_ELLIPSES_FRAGMENT as frag

    flat = " ".join(frag.split())
    assert "Not supported on a tilted ellipse yet" not in flat
    # The four operations tickets 02 and 03 built are not listed as errors.
    for op in ("line_tangent", "point_intersection", "`tangent`"):
        for line in frag.splitlines():
            if "not supported" in line.lower() or "error" in line.lower():
                assert op not in line, (op, line)
    assert "all work on a tilted ellipse" in flat
    assert "Build those diagrams with an axis-aligned ellipse" not in flat
    # The real limits are named.
    assert "arcs" in flat and "sectors" in flat
    assert "ellipse_foci" in flat and "ellipse_bbox" in flat
    assert "TikZ" in flat and "aspect" in flat
    # to_tikz rejects any non-None aspect, including 1.
    assert "rejects any canvas `aspect` for every diagram" in flat
    assert "other than 1" not in flat


# --- rotation guards -------------------------------------------------------------

@pytest.mark.parametrize("rotation", ["sqrt(-1)", "1/0", float("inf"), float("nan")])
def test_non_real_or_non_finite_rotation_is_a_compile_error_naming_the_definition(rotation):
    with pytest.raises(IRCompileError) as exc:
        compile_defs(_diagram(rotation))
    assert exc.value.def_id == "E"
    assert "rotation" in str(exc.value)


@pytest.mark.parametrize("rotation", [-1e-20, 360, 360.0, -360, "720", "-1e-20"])
def test_rotation_that_snaps_to_a_full_turn_takes_the_axis_aligned_path(rotation):
    sym = compile_defs(_diagram(rotation))
    assert not isinstance(sym["E"], RotatedEllipse)
    assert isinstance(sym["E"], spg.Ellipse)


def test_equal_radii_tilted_ellipse_answers_like_its_circle_twin():
    sym = _tilted_and_twin(2, 2)
    assert query_radius(sym, "U") == {"radius": 2.0}  # the untilted twin is a circle
    assert query_radius(sym, "T") == {"radius": 2.0}
    t = run_checks([ir.DistanceEquals(seg="T", expected=1)], sym)[0]
    u = run_checks([ir.DistanceEquals(seg="U", expected=1)], sym)[0]
    assert not t.passed and t.message == u.message.replace("'U'", "'T'")
    assert "radii differ" not in t.message


def test_differing_radii_tilted_ellipse_still_reports_two_radii():
    sym = _tilted_and_twin()
    assert query_radius(sym, "T") == {"hradius": 3.0, "vradius": 1.0}
    t = run_checks([ir.DistanceEquals(seg="T", expected=1)], sym)[0]
    assert "radii differ" in t.message
