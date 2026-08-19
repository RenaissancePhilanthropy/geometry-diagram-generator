"""Tests for geometry_diagrams/ir/render_util.py."""
import math

import pytest
import sympy.geometry as spg

from geometry_diagrams.ir.render_util import build_entity_manifest, centroid_of_obj, tick_values
from geometry_diagrams.ir.ir import DiagramIR, LineThrough


def test_centroid_of_obj_returns_midpoint_for_line():
    line = spg.Line(spg.Point(0, 0), spg.Point(4, 0))
    assert centroid_of_obj(line) == (2.0, 0.0)


def test_centroid_of_obj_returns_midpoint_for_segment():
    seg = spg.Segment(spg.Point(0, 0), spg.Point(2, 2))
    assert centroid_of_obj(seg) == (1.0, 1.0)


def test_centroid_of_obj_returns_midpoint_for_ray():
    ray = spg.Ray(spg.Point(1, 1), spg.Point(3, 1))
    assert centroid_of_obj(ray) == (2.0, 1.0)


def test_build_entity_manifest_includes_a_named_line():
    # Before this fix: a bare sympy Line has no .vertices, centroid_of_obj
    # raised AttributeError, and build_entity_manifest's except-and-skip
    # silently dropped it from "named" entirely — check_edit_locality could
    # never see a named Line/Segment/Ray variable appear, disappear, or
    # move (confirmed directly against sympy's Line2D/Segment/Ray, and via
    # evals/scenarios_locality_judgment.yaml's legitimate-remove-angle-bisector
    # fixture failing identically across three unrelated models for this
    # exact reason).
    diagram_ir = DiagramIR(define=[LineThrough(id="l1", p="p1", q="p2")], render=[])
    sym = {"l1": spg.Line(spg.Point(0, 0), spg.Point(4, 0))}
    variable_ids = {"my_line": "l1"}

    manifest = build_entity_manifest(diagram_ir, sym, variable_ids)

    names = {e["name"] for e in manifest["named"]}
    assert "my_line" in names


def test_build_entity_manifest_logs_a_warning_for_a_still_unhandled_sympy_type(caplog):
    # This is the general-case regression test for the Line/Segment/Ray gap
    # above: any FUTURE sympy type that isn't Point, doesn't match one of
    # centroid_of_obj's isinstance branches, and has no .vertices will hit
    # the same except-and-skip. The fix isn't to handle every type in
    # advance (impossible) — it's to make the swallow loud enough that the
    # next gap surfaces as a log line instead of another live-debugging
    # session finding it by accident.
    import logging

    from geometry_diagrams.ir.ir import DiagramIR, LineThrough

    class UnknownGeometryType:
        pass

    diagram_ir = DiagramIR(define=[LineThrough(id="x1", p="p1", q="p2")], render=[])
    sym = {"x1": UnknownGeometryType()}
    variable_ids = {"mystery": "x1"}

    with caplog.at_level(logging.WARNING):
        manifest = build_entity_manifest(diagram_ir, sym, variable_ids)

    assert not any(e["name"] == "mystery" for e in manifest["named"])
    assert any(
        "mystery" in record.getMessage() and "UnknownGeometryType" in record.getMessage()
        for record in caplog.records
    )


def test_tick_values_excludes_zero():
    assert 0 not in tick_values(-4, 4, 1)


def test_tick_values_excludes_endpoints_when_on_step():
    # Canvas boundary 0..7000 at step 1000: 7000 is the axis arrowhead's own
    # endpoint — a tick there overlaps the arrowhead and must be excluded.
    values = tick_values(0, 7000, 1000)
    assert 7000 not in values
    assert 0 not in values
    assert values == [1000, 2000, 3000, 4000, 5000, 6000]


def test_tick_values_excludes_negative_endpoint():
    values = tick_values(-3000, 3000, 1000)
    assert -3000 not in values
    assert 3000 not in values
    assert values == [-2000, -1000, 1000, 2000]


def test_tick_values_keeps_interior_values_when_endpoints_not_on_step():
    # Endpoints not exact multiples of step -> nothing to exclude beyond 0.
    values = tick_values(-3.5, 3.5, 1)
    assert values == [-3, -2, -1, 1, 2, 3]


def test_elliptical_arc_params_recovers_correct_angle_not_plain_atan2():
    """The exact Fable-verified worked example: hradius=4, vradius=1, t=60deg.

    Point on the ellipse at parametric angle t=60 degrees is
    (4*cos(60), 1*sin(60)) = (2.0, 0.8660...). The correct parametric-angle
    recovery formula atan2((y-cy)/vr, (x-cx)/hr) gives back 60.0 degrees.
    Plain atan2(y-cy, x-cx) gives 23.413 degrees -- a ~36.6 degree error --
    and feeding that wrong angle back into the parametric form
    (cx + hr*cos(t), cy + vr*sin(t)) lands nowhere near the original point.
    """
    from geometry_diagrams.ir.ir import DiagramIR, EllipticalArcCenterStartEnd, PointFixed
    from geometry_diagrams.ir.render_util import elliptical_arc_params
    from geometry_diagrams.ir.to_sympy import compile_defs

    t = math.radians(60.0)
    hr, vr = 4.0, 1.0
    sx, sy = hr * math.cos(t), vr * math.sin(t)
    assert sx == pytest.approx(2.0, abs=1e-3)
    assert sy == pytest.approx(0.8660, abs=1e-3)

    sym = compile_defs(DiagramIR(define=[
        PointFixed(id="c", x=0, y=0),
        PointFixed(id="s", x=sx, y=sy),
        PointFixed(id="e", x=0, y=vr),  # t=90deg
        EllipticalArcCenterStartEnd(id="ea1", center="c", hradius=hr, vradius=vr, start="s", end="e"),
    ]))
    cx, cy, hr_out, vr_out, s_deg, e_deg, sx_out, sy_out = elliptical_arc_params("ea1", sym)

    # Correct formula recovers the true start angle:
    assert s_deg == pytest.approx(60.0, abs=0.01)

    # Sanity: the WRONG plain-atan2 formula would have given ~23.413 degrees,
    # a completely different and incorrect angle -- assert the two disagree
    # by roughly the expected error margin, pinning the bug this fixes.
    wrong_deg = math.degrees(math.atan2(sy_out - cy, sx_out - cx)) % 360.0
    assert wrong_deg == pytest.approx(23.413, abs=0.01)
    assert abs(s_deg - wrong_deg) == pytest.approx(36.587, abs=0.01)


def test_expand_bounds_for_geometry_includes_elliptical_arc():
    from geometry_diagrams.ir.ir import DiagramIR, EllipticalArcCenterStartEnd, PointFixed
    from geometry_diagrams.ir.render_util import BOUNDS_PADDING, expand_bounds_for_geometry
    from geometry_diagrams.ir.to_sympy import compile_defs

    sym = compile_defs(DiagramIR(define=[
        PointFixed(id="c", x=0, y=0),
        PointFixed(id="s", x=4, y=0),
        PointFixed(id="e", x=0, y=1),
        EllipticalArcCenterStartEnd(id="ea1", center="c", hradius=4, vradius=1, start="s", end="e"),
    ]))
    xmin, xmax, ymin, ymax = expand_bounds_for_geometry(0.0, 0.0, 0.0, 0.0, sym)
    assert xmin == pytest.approx(-4.0 - BOUNDS_PADDING)
    assert xmax == pytest.approx(4.0 + BOUNDS_PADDING)
    assert ymin == pytest.approx(-1.0 - BOUNDS_PADDING)
    assert ymax == pytest.approx(1.0 + BOUNDS_PADDING)


def test_build_entity_manifest_includes_named_and_anonymous_entries():
    from geometry_diagrams.ir.ir import DiagramIR, PointFixed, Segment, Triangle, LabelPoint, Fill
    from geometry_diagrams.ir.to_sympy import compile_defs
    from geometry_diagrams.ir.render_util import build_entity_manifest

    diagram = DiagramIR(
        define=[
            PointFixed(id="p_a", x=0.0, y=0.0),
            PointFixed(id="p_b", x=4.0, y=0.0),
            PointFixed(id="p_c", x=0.0, y=3.0),
            Triangle(id="tri1", a="p_a", b="p_b", c="p_c"),
        ],
        render=[
            LabelPoint(p="p_a", text="A"),
            Fill(obj="tri1"),
        ],
    )
    sym = compile_defs(diagram)
    variable_ids = {"a": "p_a", "b": "p_b", "c": "p_c", "t": "tri1"}

    manifest = build_entity_manifest(diagram, sym, variable_ids)

    named_by_name = {e["name"]: e for e in manifest["named"]}
    assert named_by_name["t"]["type"] == "triangle"
    assert named_by_name["t"]["id"] == "tri1"
    assert named_by_name["a"]["approx_position"] == [0.0, 0.0]

    anon_types = {e["type"] for e in manifest["anonymous"]}
    assert anon_types == {"label_point", "fill"}
    label_entry = next(e for e in manifest["anonymous"] if e["type"] == "label_point")
    assert label_entry["text"] == "A"
    assert label_entry["approx_position"] == [0.0, 0.0]
