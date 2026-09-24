"""Tests for geometry_diagrams/ir/render_util.py."""
import math

import pytest
import sympy.geometry as spg

from geometry_diagrams.ir.render_util import build_entity_manifest, centroid_of_obj, seg_endpoints, tick_values
from geometry_diagrams.ir.ir import DiagramIR, LineThrough, Ray, Segment, Triangle


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


# ---------------------------------------------------------------------------
# seg_endpoints — Segment/Ray endpoint resolution shared by both backends'
# MarkSegments handling
# ---------------------------------------------------------------------------

def test_seg_endpoints_returns_ab_for_segment():
    stmt_by_id = {"s1": Segment(id="s1", a="A", b="B")}
    assert seg_endpoints("s1", stmt_by_id) == ("A", "B")


def test_seg_endpoints_returns_ab_for_ray():
    """A Ray def has the same a/b point-id fields as a Segment — a ray
    handle marked via mark_equal()/mark_parallel()/mark_proportional() must
    resolve endpoints the same way a segment does, not raise. Before this
    fix, seg_endpoints() only recognized ir.Segment and raised ValueError
    for anything else, including a Ray, crashing uncaught deep in the
    renderer's MarkSegments handling."""
    stmt_by_id = {"r1": Ray(id="r1", a="A", b="B")}
    assert seg_endpoints("r1", stmt_by_id) == ("A", "B")


def test_seg_endpoints_rejects_a_non_segment_non_ray_def():
    stmt_by_id = {"t1": Triangle(id="t1", a="A", b="B", c="C")}
    with pytest.raises(ValueError, match="Expected Segment or Ray def"):
        seg_endpoints("t1", stmt_by_id)


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


# ---------------------------------------------------------------------------
# tick_mark_arcs — the arc-space counterpart of tick_mark_segments
# ---------------------------------------------------------------------------

def test_tick_mark_arcs_returns_one_stroke_per_tick():
    from geometry_diagrams.ir.render_util import tick_mark_arcs

    strokes = tick_mark_arcs(0, 0, 1, 0, 90, 4, 0.1, 0.05)
    assert len(strokes) == 4


def test_tick_mark_arcs_strokes_are_radial_and_straddle_the_curve():
    from geometry_diagrams.ir.render_util import tick_mark_arcs

    strokes = tick_mark_arcs(0, 0, 1.0, 0, 90, 3, 0.1, 0.05)
    for (x1, y1), (x2, y2) in strokes:
        r1 = math.hypot(x1, y1)
        r2 = math.hypot(x2, y2)
        assert r1 == pytest.approx(0.9)
        assert r2 == pytest.approx(1.1)
        # Stroke midpoint sits on the curve itself.
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        assert math.hypot(mx, my) == pytest.approx(1.0)


def test_tick_mark_arcs_centers_odd_count_on_the_midpoint_angle():
    from geometry_diagrams.ir.render_util import tick_mark_arcs

    strokes = tick_mark_arcs(0, 0, 1.0, 0, 90, 3, 0.1, 0.05)
    (mx1, my1), (mx2, my2) = strokes[1]  # middle stroke
    mx, my = (mx1 + mx2) / 2, (my1 + my2) / 2
    assert math.degrees(math.atan2(my, mx)) == pytest.approx(45.0, abs=1e-6)


def test_tick_mark_arcs_spacing_is_arc_length_not_angle():
    from geometry_diagrams.ir.render_util import tick_mark_arcs

    def angular_gap(r):
        strokes = tick_mark_arcs(0, 0, r, 0, 90, 3, 0.01, 0.1)
        angles = []
        for (x1, y1), (x2, y2) in strokes:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            angles.append(math.atan2(my, mx))
        return angles[1] - angles[0]

    gap_r1 = angular_gap(1.0)
    gap_r4 = angular_gap(4.0)
    assert gap_r4 == pytest.approx(gap_r1 / 4.0)


def test_tick_mark_arcs_returns_empty_for_degenerate_radius():
    from geometry_diagrams.ir.render_util import tick_mark_arcs

    assert tick_mark_arcs(0, 0, 0, 0, 90, 3, 0.1, 0.05) == []


def test_tick_mark_arcs_returns_empty_for_non_positive_ticks():
    from geometry_diagrams.ir.render_util import tick_mark_arcs

    assert tick_mark_arcs(0, 0, 1, 0, 90, 0, 0.1, 0.05) == []


def test_tick_mark_arcs_clamps_the_inner_endpoint_at_the_center():
    from geometry_diagrams.ir.render_util import tick_mark_arcs

    strokes = tick_mark_arcs(0, 0, 0.05, 0, 90, 1, 0.5, 0.05)
    (x1, y1), (x2, y2) = strokes[0]
    assert math.hypot(x1, y1) == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# arc_text_glyphs — per-character advances
# ---------------------------------------------------------------------------

def test_arc_text_glyphs_advances_sum_matches_estimate_text_width():
    from geometry_diagrams.ir.render_util import arc_text_glyphs
    from geometry_diagrams.ir.to_svg import _estimate_text_width

    for t in ["ABC", "x^2", r"\alpha b"]:
        glyphs = arc_text_glyphs(t, 14)
        total = sum(adv for _, adv in glyphs)
        assert total == pytest.approx(_estimate_text_width(t, 14))


def test_arc_text_glyphs_collapses_a_latex_command_to_one_glyph():
    from geometry_diagrams.ir.render_util import arc_text_glyphs

    glyphs = arc_text_glyphs(r"\alpha", 14)
    assert len(glyphs) == 1


def test_arc_text_glyphs_returns_one_entry_per_plain_character():
    from geometry_diagrams.ir.render_util import arc_text_glyphs

    glyphs = arc_text_glyphs("ABC", 14)
    assert [ch for ch, _ in glyphs] == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# arc_text_is_layoutable — the shared per-glyph-vs-fallback gate
# ---------------------------------------------------------------------------

def test_arc_text_is_layoutable_accepts_plain_ascii():
    from geometry_diagrams.ir.render_util import arc_text_is_layoutable

    assert arc_text_is_layoutable("ABC") is True
    assert arc_text_is_layoutable("major arc") is True


@pytest.mark.parametrize("text", [r"\frac{1}{2}", "$A$", "P_1", "x^2"])
def test_arc_text_is_layoutable_rejects_mathtext_and_scripts(text):
    from geometry_diagrams.ir.render_util import arc_text_is_layoutable

    assert arc_text_is_layoutable(text) is False


# ---------------------------------------------------------------------------
# arc_text_glyph_layout — per-glyph position + rotation along an arc
# ---------------------------------------------------------------------------

def test_arc_text_glyph_layout_returns_one_entry_per_advance():
    from geometry_diagrams.ir.render_util import arc_text_glyph_layout

    layout = arc_text_glyph_layout(0, 0, 1, 0, 180, [1.0, 1.0, 1.0])
    assert len(layout) == 3


def test_arc_text_glyph_layout_returns_empty_for_no_advances():
    from geometry_diagrams.ir.render_util import arc_text_glyph_layout

    assert arc_text_glyph_layout(0, 0, 1, 0, 180, []) == []


def test_arc_text_glyph_layout_centers_the_string_on_pos():
    from geometry_diagrams.ir.render_util import arc_text_glyph_layout

    layout = arc_text_glyph_layout(0, 0, 1, 0, 180, [0.05, 0.05, 0.05, 0.05], pos=0.25)
    angles = [math.atan2(y, x) for x, y, _ in layout]
    mean_angle = sum(angles) / len(angles)
    anchor_angle = math.radians(0.25 * 180)
    assert mean_angle == pytest.approx(anchor_angle, abs=1e-6)


def test_arc_text_glyph_layout_outside_is_beyond_the_radius_and_inside_is_within():
    from geometry_diagrams.ir.render_util import arc_text_glyph_layout

    outside = arc_text_glyph_layout(0, 0, 1.0, 0, 180, [0.1], offset=0.2, side="outside")
    inside = arc_text_glyph_layout(0, 0, 1.0, 0, 180, [0.1], offset=0.2, side="inside")
    x_out, y_out, _ = outside[0]
    x_in, y_in, _ = inside[0]
    assert math.hypot(x_out, y_out) == pytest.approx(1.2)
    assert math.hypot(x_in, y_in) == pytest.approx(0.8)


def test_arc_text_glyph_layout_auto_flip_is_upright_at_top_and_bottom():
    from geometry_diagrams.ir.render_util import arc_text_glyph_layout

    # A short arc straddling the top of the circle (90 deg): text should be
    # (near) horizontal, upright.
    top = arc_text_glyph_layout(0, 0, 1, 89, 91, [0.01])
    assert top[0][2] == pytest.approx(0.0, abs=1.0)

    # A short arc straddling the bottom of the circle (270 deg): auto-flip
    # must keep it upright too, not upside down (rotation within +/-90 deg
    # of horizontal, never near +/-180).
    bottom = arc_text_glyph_layout(0, 0, 1, 269, 271, [0.01])
    rot = bottom[0][2]
    assert abs(rot) <= 90.0


def test_arc_text_glyph_layout_reads_left_to_right_on_both_halves():
    from geometry_diagrams.ir.render_util import arc_text_glyph_layout

    for start, end in [(80, 100), (260, 280)]:
        layout = arc_text_glyph_layout(0, 0, 1, start, end, [0.05, 0.05, 0.05])
        xs = [x for x, _, _ in layout]
        assert xs == sorted(xs)


def test_arc_text_glyph_layout_forced_flip_inverts_rotation_sign():
    from geometry_diagrams.ir.render_util import arc_text_glyph_layout

    default = arc_text_glyph_layout(0, 0, 1, 89, 91, [0.01], flip=False)
    forced = arc_text_glyph_layout(0, 0, 1, 89, 91, [0.01], flip=True)
    # Forcing the opposite flip rotates the glyph by ~180 degrees.
    diff = abs(default[0][2] - forced[0][2])
    assert diff == pytest.approx(180.0, abs=1e-6)


def test_arc_label_anchor_pos_defaults_to_the_midpoint():
    from geometry_diagrams.ir.ir import DiagramIR, PointFixed, ArcCenterStartEnd
    from geometry_diagrams.ir.render_util import arc_label_anchor
    from geometry_diagrams.ir.to_sympy import compile_defs

    sym = compile_defs(DiagramIR(define=[
        PointFixed(id="O", x=0, y=0),
        PointFixed(id="S", x=1, y=0),
        PointFixed(id="E", x=0, y=1),
        ArcCenterStartEnd(id="arc1", center="O", start="S", end="E"),
    ]))
    cx, cy, px, py, r = arc_label_anchor("arc1", sym)
    assert math.degrees(math.atan2(py - cy, px - cx)) == pytest.approx(45.0, abs=1e-6)


def test_arc_label_anchor_honors_explicit_pos():
    from geometry_diagrams.ir.ir import DiagramIR, PointFixed, ArcCenterStartEnd
    from geometry_diagrams.ir.render_util import arc_label_anchor
    from geometry_diagrams.ir.to_sympy import compile_defs

    sym = compile_defs(DiagramIR(define=[
        PointFixed(id="O", x=0, y=0),
        PointFixed(id="S", x=1, y=0),
        PointFixed(id="E", x=0, y=1),
        ArcCenterStartEnd(id="arc1", center="O", start="S", end="E"),
    ]))
    cx, cy, px, py, r = arc_label_anchor("arc1", sym, pos=0.0)
    assert px == pytest.approx(1.0, abs=1e-6)
    assert py == pytest.approx(0.0, abs=1e-6)


def _elliptical_arc_sym(hr: float = 4.0, vr: float = 1.0):
    from geometry_diagrams.ir.ir import DiagramIR, PointFixed, EllipticalArcCenterStartEnd
    from geometry_diagrams.ir.to_sympy import compile_defs

    return compile_defs(DiagramIR(define=[
        PointFixed(id="O", x=0, y=0),
        PointFixed(id="S", x=hr, y=0),
        PointFixed(id="E", x=0, y=vr),
        EllipticalArcCenterStartEnd(id="ea1", center="O", hradius=hr, vradius=vr, start="S", end="E"),
    ]))


def test_elliptical_arc_label_anchor_pos_defaults_to_the_midpoint():
    """The elliptical analogue of test_arc_label_anchor_pos_defaults_to_the_
    midpoint above. Unlike a circle, the anchor point is NOT at the direction
    angle halfway between the endpoint directions (45deg here) -- it's at
    the ellipse's own parametric midpoint t=45deg, i.e.
    (hr*cos(45), vr*sin(45)), which for hr != vr points somewhere else
    entirely. A naive reuse of the circular arc_label_anchor() (a single
    radius r) would get this wrong for any hr != vr."""
    from geometry_diagrams.ir.render_util import elliptical_arc_label_anchor

    sym = _elliptical_arc_sym(hr=4.0, vr=1.0)
    cx, cy, px, py, r = elliptical_arc_label_anchor("ea1", sym)
    t = math.radians(45.0)
    assert px == pytest.approx(4.0 * math.cos(t), abs=1e-6)
    assert py == pytest.approx(1.0 * math.sin(t), abs=1e-6)
    # Sanity: this is NOT the same as the (wrong, circle-shaped) angle you'd
    # get from treating 45deg as the actual direction from the center.
    wrong_angle = math.degrees(math.atan2(py - cy, px - cx))
    assert wrong_angle != pytest.approx(45.0, abs=1.0)


def test_elliptical_arc_label_anchor_honors_explicit_pos():
    from geometry_diagrams.ir.render_util import elliptical_arc_label_anchor

    sym = _elliptical_arc_sym(hr=4.0, vr=1.0)
    cx, cy, px, py, r = elliptical_arc_label_anchor("ea1", sym, pos=0.0)
    assert px == pytest.approx(4.0, abs=1e-6)
    assert py == pytest.approx(0.0, abs=1e-6)


def test_centroid_of_obj_handles_compiled_open_polyline():
    """Regression test: a compiled PolylineOpen is a plain Python list of
    sympy Points (see to_sympy.py's ir.PolylineOpen case), not an object
    with a .vertices attribute like Polygon/Triangle -- centroid_of_obj used
    to raise AttributeError for it."""
    from geometry_diagrams.ir.ir import DiagramIR, PointFixed, PolylineOpen
    from geometry_diagrams.ir.to_sympy import compile_defs

    sym = compile_defs(DiagramIR(define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        PointFixed(id="C", x=4, y=4),
        PolylineOpen(id="poly", points=["A", "B", "C"]),
    ]))
    assert centroid_of_obj(sym["poly"]) == (8.0 / 3, 4.0 / 3)
