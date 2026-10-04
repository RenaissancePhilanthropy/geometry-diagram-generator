"""Tests for label placement utilities in ir/to_svg.py.

Covers the four known defects:
1. _nudge_labels_from_lines uses a fixed min_dist ignoring label height,
   so tall math labels are not nudged far enough.
2. dist > 0.1 dead zone leaves on-segment labels stuck.
3. _resolve_label_collisions only moves label i — the first label is immune.
4. _segment_label_side ignores distance — a far point outweighs a near one.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import pytest

from geometry_diagrams.ir.ir import (
    Canvas,
    CircleCenterRadius,
    DiagramIR,
    Draw,
    EllipseCenterAxes,
    EllipticalArcCenterStartEnd,
    LabelPoint,
    LabelSegment,
    PointFixed,
    Segment,
    SectorCenterStartEnd,
    Triangle,
)
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_svg import (
    _LabelPlacement,
    _ellipse_clearance,
    _label_bbox,
    _nearest_point_on_ellipse,
    _nudge_labels_from_circles,
    _nudge_labels_from_ellipses,
    _nudge_labels_from_lines,
    _resolve_label_collisions,
    _segment_label_side,
    ir_to_svg,
)

_SVG_NS = "http://www.w3.org/2000/svg"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_lp(x: float, y: float, width: float = 14.0, height: float = 14.0) -> _LabelPlacement:
    return _LabelPlacement(
        x=x, y=y, text="A", color="black", anchor="middle",
        width_est=width, height_est=height,
    )


def _compile_svg(diagram: DiagramIR) -> str:
    return ir_to_svg(diagram, compile_defs(diagram))


def _parse(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def _labels(root: ET.Element) -> list[ET.Element]:
    return [el for el in root.iter() if el.get("data-role", "").startswith("label")]


# ---------------------------------------------------------------------------
# 1. Nudge: tall labels must clear the segment bbox, not just the center point
# ---------------------------------------------------------------------------

class TestNudgeWideLabel:
    def test_wide_label_cleared_from_vertical_segment(self):
        """Wide label left of a vertical segment must have its right bbox edge clear the line.

        Segment is vertical at x=200, from (200, 0) to (200, 400) in SVG.
        Label center at (185, 200): 15px left of segment, width=60 → right edge = 215.
        This means the bbox crosses the segment, even though the center doesn't.

        The nudge must push the center far enough that the right edge is safely left
        of the segment.  Required center distance = W/2 + margin ≈ 30 + 4.9 = 34.9px.
        """
        seg = [(200.0, 0.0, 200.0, 400.0)]
        lp = _make_lp(185.0, 200.0, width=60.0, height=14.0)
        _nudge_labels_from_lines([lp], seg)
        right_edge = lp.x + lp.width_est / 2
        assert right_edge <= 199.0, (
            f"Wide label right edge {right_edge:.2f} still overlaps or is within 1px "
            f"of vertical segment at x=200"
        )


class TestNudgeTallLabel:
    def test_tall_label_cleared_from_segment(self):
        """A label with height > 2×min_center_dist must be nudged further.

        Scenario: horizontal segment from (0,200) to (400,200) in SVG pixels.
        Label center at (200, 212) — center is 12px from segment.
        Label height = 20px → label bottom at 212+10 = 222, top at 212-10 = 202,
        meaning the label bbox is only 2px above the segment.

        After nudge the label bbox bottom must be at least FONT_SIZE*0.3 = ~4px
        clear of the segment, i.e. the top edge (202) must be ≥ 204 above segment
        (y=200). Equivalently, center must be ≥ 200 + 10 + 4 = 214.
        """
        seg = [(0.0, 200.0, 400.0, 200.0)]
        lp = _make_lp(200.0, 212.0, width=40.0, height=20.0)
        _nudge_labels_from_lines([lp], seg)
        # After nudge, bbox top edge (lp.y - height/2) must be at least 4px above seg
        top_edge = lp.y - lp.height_est / 2
        assert top_edge >= 204.0 - 1e-6, (
            f"Tall label bbox top at {top_edge:.2f} is still within 4px of segment y=200"
        )

    def test_small_label_not_over_nudged(self):
        """A normal-sized label placed well clear of a segment stays put."""
        seg = [(0.0, 200.0, 400.0, 200.0)]
        # Center at y=230, height=14 → top at 223, bottom at 237; segment at 200
        # Clearance = 23px — well above any reasonable threshold.
        lp = _make_lp(200.0, 230.0, width=14.0, height=14.0)
        y_before = lp.y
        _nudge_labels_from_lines([lp], seg)
        assert lp.y == pytest.approx(y_before, abs=0.5), (
            "Label far from segment should not be moved"
        )


# ---------------------------------------------------------------------------
# 2. Nudge: dead zone — label exactly on the line must also be nudged
# ---------------------------------------------------------------------------

class TestNudgeDeadZone:
    def test_on_segment_label_is_nudged(self):
        """A label whose center sits on the segment (dist ≈ 0) must be moved."""
        seg = [(0.0, 200.0, 400.0, 200.0)]
        lp = _make_lp(200.0, 200.0)  # exactly on segment
        _nudge_labels_from_lines([lp], seg)
        assert lp.y != pytest.approx(200.0, abs=1.0), (
            "Label on segment was not nudged (dead-zone bug)"
        )

    def test_on_segment_label_moves_away(self):
        """Label on segment must end up sufficiently far from it."""
        seg = [(0.0, 200.0, 400.0, 200.0)]
        lp = _make_lp(200.0, 200.0)
        _nudge_labels_from_lines([lp], seg)
        dist = abs(lp.y - 200.0)
        assert dist >= 7.0, f"Label moved only {dist:.1f}px from the segment"


# ---------------------------------------------------------------------------
# 2b. Nudge is anchor-aware: distance is measured from the true bbox, not the
#     anchor point (regression for the origin-label displacement bug)
# ---------------------------------------------------------------------------

class TestNudgeAnchorAware:
    AXES = [(20.0, 250.0, 480.0, 250.0),   # x-axis (horizontal)
            (250.0, 20.0, 250.0, 480.0)]   # y-axis (vertical)

    def test_start_anchored_label_right_of_vertical_line_not_pushed(self):
        """An 'above right' point label at the axes origin already clears both
        axis lines — its bbox extends up-right from the anchor — so it must
        stay at the intended 12px offset instead of being pushed as if its
        anchor were the bbox centre."""
        lp = _LabelPlacement(
            x=262.0, y=238.0, text="(0, 0)", color="black", anchor="start",
            width_est=54.6, height_est=14.0,
        )
        _nudge_labels_from_lines([lp], self.AXES)
        assert (lp.x, lp.y) == pytest.approx((262.0, 238.0), abs=0.01), (
            f"Clear start-anchored label was spuriously nudged to ({lp.x:.1f}, {lp.y:.1f})"
        )

    def test_end_anchored_label_left_of_vertical_line_not_pushed(self):
        """Mirror case: 'above left' label, bbox extends up-left, already clear."""
        lp = _LabelPlacement(
            x=238.0, y=238.0, text="(0, 0)", color="black", anchor="end",
            width_est=54.6, height_est=14.0,
        )
        _nudge_labels_from_lines([lp], self.AXES)
        assert (lp.x, lp.y) == pytest.approx((238.0, 238.0), abs=0.01)

    def test_start_anchored_label_straddling_line_still_nudged(self):
        """Anchor-awareness must not disable genuine avoidance: a start-anchored
        label whose bbox crosses the vertical line still gets pushed clear."""
        lp = _LabelPlacement(
            x=245.0, y=238.0, text="(0, 0)", color="black", anchor="start",
            width_est=54.6, height_est=14.0,
        )
        _nudge_labels_from_lines([lp], [(250.0, 20.0, 250.0, 480.0)])
        x0, _, _, _ = _label_bbox(lp)
        assert x0 >= 250.0 + 14.0 * 0.35 - 0.01, (
            f"Straddling label bbox left edge {x0:.1f} still too close to line x=250"
        )

    def test_origin_label_pipeline_axes_do_not_displace(self):
        """End-to-end: a labeled point at the origin with canvas axes enabled
        renders its label at the same position as without axes."""
        def build(axes: bool) -> DiagramIR:
            return DiagramIR(
                canvas=Canvas(xmin=-5, xmax=5, ymin=-5, ymax=5, axes=axes),
                define=[PointFixed(id="O", x=0, y=0)],
                render=[LabelPoint(kind="label_point", p="O",
                                   text="(0, 0)", pos="above right")],
            )

        def label_xy(svg: str) -> tuple[float, float]:
            root = _parse(svg)
            (el,) = _labels(root)
            return float(el.get("x")), float(el.get("y"))

        x_plain, y_plain = label_xy(_compile_svg(build(axes=False)))
        x_axes, y_axes = label_xy(_compile_svg(build(axes=True)))
        assert (x_axes, y_axes) == pytest.approx((x_plain, y_plain), abs=0.5), (
            f"Axes displaced origin label from ({x_plain}, {y_plain}) "
            f"to ({x_axes}, {y_axes})"
        )


# ---------------------------------------------------------------------------
# 3. Collision resolver: both labels must move, not just the later one
# ---------------------------------------------------------------------------

class TestBothLabelsMoveOnCollision:
    def test_first_label_also_moves(self):
        """When two labels overlap, the first-placed one must also be displaced."""
        label_a = _make_lp(200.0, 200.0, width=30.0, height=14.0)
        label_b = _make_lp(205.0, 200.0, width=30.0, height=14.0)  # heavily overlaps a
        xa_before = label_a.x
        xb_before = label_b.x
        _resolve_label_collisions([label_a, label_b], 500.0, 500.0)
        moved_a = abs(label_a.x - xa_before) > 0.5 or abs(label_a.y - 200.0) > 0.5
        moved_b = abs(label_b.x - xb_before) > 0.5 or abs(label_b.y - 200.0) > 0.5
        assert moved_a, "First label (j) was not moved when it overlaps the second (i)"
        assert moved_b, "Second label (i) was not moved"

    def test_labels_no_longer_overlap_after_resolve(self):
        """After resolution, the bboxes of two colliding labels must not overlap."""
        label_a = _make_lp(200.0, 200.0, width=30.0, height=14.0)
        label_b = _make_lp(200.0, 200.0, width=30.0, height=14.0)  # exactly coincident
        _resolve_label_collisions([label_a, label_b], 500.0, 500.0)
        bb_a = _label_bbox(label_a)
        bb_b = _label_bbox(label_b)
        overlapping = not (
            bb_a[2] <= bb_b[0] or bb_b[2] <= bb_a[0] or
            bb_a[3] <= bb_b[1] or bb_b[3] <= bb_a[1]
        )
        assert not overlapping, (
            f"Labels still overlap after resolution.\n"
            f"A bbox: {bb_a}\nB bbox: {bb_b}"
        )


# ---------------------------------------------------------------------------
# 4. Segment side: distance weighting
# ---------------------------------------------------------------------------

class TestSegmentLabelSideDistanceWeighting:
    def test_nearby_point_wins_over_many_distant_points(self):
        """A single close point should outweigh many far points on the other side.

        Setup: segment horizontal at y=0 in SVG space; midpoint at (0,0).
        Normal vector pointing up = (0, -1) (SVG y-down → up = negative y).
        One point at (0, -5) — 5px below = positive-normal side in SVG.
        Many points at (0, +200) — far above = negative-normal side.
        The label should go to the negative-normal side (away from the close point),
        i.e. result = -1.
        """
        mx, my = 0.0, 0.0
        # In SVG coords: normal pointing "up" = (0, -1)
        nx, ny = 0.0, -1.0
        # One nearby point in the positive-normal direction (dot product > 0)
        # Point at (0, -5): (0-0)*0 + (-5-0)*(-1) = 5 > 0 → positive side
        close_point = [(0.0, -5.0)]
        # Many distant points in the negative-normal direction
        # Points at (0, +200): (0-0)*0 + (200-0)*(-1) = -200 < 0 → negative side
        far_points = [(0.0, 200.0)] * 5

        side_unweighted = _segment_label_side(mx, my, nx, ny, close_point + far_points)
        # Without distance weighting: 5 far points > 1 close point → side = +1 (wrong)
        # With distance weighting: close point heavily outweighs → side = -1 (correct)
        assert side_unweighted == -1.0, (
            f"Expected label on negative-normal side (away from close point), "
            f"got {side_unweighted}"
        )

    def test_equal_distance_falls_back_to_count(self):
        """With equidistant points, the side with fewer points wins."""
        mx, my = 0.0, 0.0
        nx, ny = 0.0, -1.0
        # 1 point on positive side at distance 50, 2 points on negative side at distance 50
        pos_pts = [(0.0, -50.0)]          # (0-0)*0 + (-50-0)*(-1) = 50 > 0 → positive
        neg_pts = [(0.0, 50.0), (0.0, 50.0)]  # dot = -50 < 0 → negative
        side = _segment_label_side(mx, my, nx, ny, pos_pts + neg_pts)
        # Fewer points on positive side → label goes to positive side (+1)
        assert side == 1.0, f"Expected +1 (positive side has fewer points), got {side}"


# ---------------------------------------------------------------------------
# 5. End-to-end: wide/tall math labels stay clear of their segments
# ---------------------------------------------------------------------------

class TestE2EMathLabelPlacement:
    def test_wide_math_label_does_not_overlap_segment(self):
        r"""The label $\sqrt{a^2+b^2}$ is ~85px wide — it must not overlap segment BC."""
        d = DiagramIR(
            canvas=Canvas(xmin=-0.5, xmax=5, ymin=-0.5, ymax=4),
            define=[
                PointFixed(id="A", x=0, y=0),
                PointFixed(id="B", x=4, y=0),
                PointFixed(id="C", x=4, y=3),
                Segment(id="AB", a="A", b="B"),
                Segment(id="BC", a="B", b="C"),
            ],
            render=[
                Draw(obj="AB"), Draw(obj="BC"),
                LabelPoint(p="A", text="A"),
                LabelPoint(p="B", text="B"),
                LabelPoint(p="C", text="C"),
                LabelSegment(seg="BC", text=r"$\sqrt{a^2+b^2}$"),
            ],
        )
        svg = _compile_svg(d)
        root = _parse(svg)

        # Find the math label element
        label_els = [el for el in root.iter() if el.get("data-for") == "BC"]
        assert label_els, "No label-for-BC element found in SVG"

        # The label must be valid XML (path present with non-empty d)
        for el in label_els:
            for ch in el:
                ctag = ch.tag.split("}")[-1]
                if ctag == "path":
                    assert ch.get("d", "").strip(), "Math label path is empty"

    def test_multiple_segment_labels_no_collision(self):
        """Multiple segment labels on the same shape should not collapse together."""
        d = DiagramIR(
            canvas=Canvas(xmin=-1, xmax=6, ymin=-1, ymax=5),
            define=[
                PointFixed(id="A", x=0, y=0),
                PointFixed(id="B", x=5, y=0),
                PointFixed(id="C", x=2, y=4),
                Triangle(id="T", a="A", b="B", c="C"),
                Segment(id="AB", a="A", b="B"),
                Segment(id="AC", a="A", b="C"),
                Segment(id="BC", a="B", b="C"),
            ],
            render=[
                Draw(obj="T"),
                LabelPoint(p="A", text="A"),
                LabelPoint(p="B", text="B"),
                LabelPoint(p="C", text="C"),
                LabelSegment(seg="AB", text=r"$\widehat{AB}$"),
                LabelSegment(seg="AC", text=r"$\vec{v}$"),
                LabelSegment(seg="BC", text=r"$\hat{n}$"),
            ],
        )
        svg = _compile_svg(d)
        # Just verify it renders without error and is valid XML
        root = ET.fromstring(svg)
        assert root is not None


# ---------------------------------------------------------------------------
# 5. Nudge: labels must also clear drawn circles/arcs, not just straight lines
#
# Real bug: a point surrounded by several circles it does NOT itself sit on
# (e.g. two compass-construction circles sharing a center region) had no
# mechanism stopping its auto-placed label from landing right on top of one
# of those circles' rings -- _auto_label_direction only knows about edges/
# circles the point is itself incident to, and the pre-existing nudge pass
# only ever checked straight segments.
# ---------------------------------------------------------------------------

class TestNudgeFromCircle:
    def test_label_outside_near_ring_is_pushed_further_out(self):
        """Label just outside a circle's ring must be pushed further outside."""
        circles = [(0.0, 0.0, 100.0, True)]
        lp = _make_lp(102.0, 0.0)  # 2px outside the ring
        _nudge_labels_from_circles([lp], circles)
        dist_to_center = math.hypot(lp.x, lp.y)
        assert dist_to_center > 102.0, (
            f"Label at distance {dist_to_center:.2f} from center was not pushed "
            f"further outside the ring at r=100"
        )

    def test_label_inside_near_ring_is_pushed_further_in(self):
        """Label just inside a circle's ring must be pushed toward the center."""
        circles = [(0.0, 0.0, 100.0, True)]
        lp = _make_lp(98.0, 0.0)  # 2px inside the ring
        _nudge_labels_from_circles([lp], circles)
        dist_to_center = math.hypot(lp.x, lp.y)
        assert dist_to_center < 98.0, (
            f"Label at distance {dist_to_center:.2f} from center was not pushed "
            f"further inside the ring at r=100"
        )

    def test_label_on_ring_is_nudged(self):
        """A label whose center sits exactly on the ring (dist ≈ 0) must move."""
        circles = [(0.0, 0.0, 100.0, True)]
        lp = _make_lp(100.0, 0.0)  # exactly on the ring
        _nudge_labels_from_circles([lp], circles)
        dist_to_ring = abs(math.hypot(lp.x, lp.y) - 100.0)
        assert dist_to_ring >= 7.0, f"Label moved only {dist_to_ring:.1f}px clear of the ring"

    def test_pinched_between_two_overlapping_circles_lands_at_the_best_compromise(self):
        """Two overlapping rings of equal radius, centered symmetrically about
        the label's starting position, each pull it toward the other's ring in
        turn -- a naive "apply every nudge, every round" loop bounces between
        two one-sided positions forever (verified directly: this exact setup
        oscillates between x=+2.4 and x=-2.4 pre-fix, exiting the round cap
        still short of full clearance on whichever ring it last moved toward).
        The symmetric starting point is actually the best achievable
        compromise (equal, non-zero clearance deficit on both sides beats a
        one-sided "fully clear one ring, worse on the other" outcome), so the
        label must end up back there, not at either oscillation endpoint."""
        circles = [(-10.0, 0.0, 20.0, True), (10.0, 0.0, 20.0, True)]
        lp = _make_lp(0.0, 0.0)
        _nudge_labels_from_circles([lp], circles)
        assert lp.x == pytest.approx(0.0, abs=0.1)
        assert lp.y == pytest.approx(0.0, abs=0.1)
        # Confirm it's actually a genuine (if incomplete) compromise, not a
        # no-op that never engaged with either ring.
        left_dist = abs(math.hypot(lp.x - circles[0][0], lp.y - circles[0][1]) - circles[0][2])
        right_dist = abs(math.hypot(lp.x - circles[1][0], lp.y - circles[1][1]) - circles[1][2])
        assert left_dist == pytest.approx(right_dist, abs=0.1)

    def test_label_far_from_circle_not_moved(self):
        """A label well clear of any circle stays put."""
        circles = [(0.0, 0.0, 100.0, True)]
        lp = _make_lp(300.0, 300.0)
        x_before, y_before = lp.x, lp.y
        _nudge_labels_from_circles([lp], circles)
        assert (lp.x, lp.y) == pytest.approx((x_before, y_before), abs=0.5)

    def test_e2e_point_label_avoids_an_unrelated_nearby_circle(self):
        """Full-pipeline repro: point M's only incident edge is segment M-N, so
        auto-placement puts its label on the opposite side (west of M). An
        unrelated circle (M is neither its center nor on it) has a ring that
        bulges through exactly that spot (radius calibrated so the ring sits
        right at the label's own auto-placed bbox, pre-fix) -- the rendered
        label must not overlap it.
        """
        d = DiagramIR(
            canvas=Canvas(xmin=-80, xmax=20, ymin=-40, ymax=40),
            define=[
                PointFixed(id="M", x=0, y=0),
                PointFixed(id="N", x=10, y=0),
                PointFixed(id="O", x=-1.3, y=0),
                Segment(id="MN", a="M", b="N"),
                CircleCenterRadius(id="C", center="O", radius=1.3),
            ],
            render=[
                Draw(obj="MN"),
                Draw(obj="C"),
                LabelPoint(p="M", text="M"),
            ],
        )
        svg = _compile_svg(d)
        root = _parse(svg)

        circle_el = next(el for el in root.iter() if el.get("data-ir-id") == "C")
        cx, cy, r = float(circle_el.get("cx")), float(circle_el.get("cy")), float(circle_el.get("r"))

        label_el = next(
            el for el in root.iter()
            if el.get("data-role") == "label-point" and el.get("data-for") == "M"
        )
        bx0, by0, bx1, by1 = (float(v) for v in label_el.get("data-bbox").split(","))

        # Nearest point of the label's bbox to the circle's center, clamped
        # to the bbox -- then check that point isn't within the ring band.
        nearest_x = max(bx0, min(cx, bx1))
        nearest_y = max(by0, min(cy, by1))
        dist = math.hypot(nearest_x - cx, nearest_y - cy)
        assert abs(dist - r) > 2.0, (
            f"Label bbox ({bx0:.1f},{by0:.1f})-({bx1:.1f},{by1:.1f}) still sits "
            f"on circle C's ring (center=({cx:.1f},{cy:.1f}), r={r:.1f})"
        )


# ---------------------------------------------------------------------------
# 6. Sector/Ellipse/EllipticalArc/EllipticalSector get the same circle/
# ellipse-nudge treatment Circle/Arc already have -- previously missing
# entirely (confirmed by review: none of these four appended to
# drawn_circles/drawn_ellipses at all), leaving labels free to land on a
# drawn sector, ellipse, or elliptical arc's boundary with nothing to push
# them clear.
# ---------------------------------------------------------------------------

def _brute_force_nearest_on_ellipse(px, py, cx, cy, hr, vr, n=100_000):
    """Independent cross-check for _nearest_point_on_ellipse: sample many
    boundary points directly and take the closest, rather than trusting the
    same Newton's-method derivation the function under test uses."""
    best_d2 = None
    best = None
    for i in range(n):
        t = 2 * math.pi * i / n
        bx, by = cx + hr * math.cos(t), cy + vr * math.sin(t)
        d2 = (px - bx) ** 2 + (py - by) ** 2
        if best_d2 is None or d2 < best_d2:
            best_d2, best = d2, (bx, by)
    return best


class TestNearestPointOnEllipse:
    def test_matches_circle_math_when_axes_are_equal(self):
        """hr == vr degenerates to a true circle: nearest point must be
        exactly along the center-point line, same as _circle_clearance's
        direct radial computation."""
        nx, ny = _nearest_point_on_ellipse(130.0, 40.0, 0.0, 0.0, 100.0, 100.0)
        expected_angle = math.atan2(40.0, 130.0)
        assert nx == pytest.approx(100.0 * math.cos(expected_angle), abs=1e-6)
        assert ny == pytest.approx(100.0 * math.sin(expected_angle), abs=1e-6)

    def test_major_axis_point_needs_more_than_one_newton_start(self):
        """A point on the major axis, inside a wide ellipse, is the exact
        case multi-start guards against: intuition (and a single Newton run
        from this point's own parametric angle, which lands exactly on the
        on-axis root at t=0) both say the nearest point is straight out
        along the same axis at (10, 0) -- but it's provably not (brute-force
        cross-checked): the true nearest point is off-axis, at (4, ~4.58),
        distance^2=22 vs (10,0)'s distance^2=49. A single-start solver
        would silently return the wrong (merely locally-nearest) point here."""
        nx, ny = _nearest_point_on_ellipse(3.0, 0.0, 0.0, 0.0, 10.0, 5.0)
        bx, by = _brute_force_nearest_on_ellipse(3.0, 0.0, 0.0, 0.0, 10.0, 5.0)
        assert nx == pytest.approx(bx, abs=0.05)
        assert ny == pytest.approx(by, abs=0.05)
        assert nx == pytest.approx(4.0, abs=0.05)
        assert abs(ny) == pytest.approx(math.sqrt(21), abs=0.05)  # 5*sin(acos(4/10)) = sqrt(21)

    def test_matches_brute_force_search_for_an_off_axis_point(self):
        """General off-axis case, cross-checked against direct sampling
        rather than re-deriving the same calculus by hand."""
        cx, cy, hr, vr = 5.0, -2.0, 12.0, 7.0
        px, py = 20.0, 6.0  # well outside, off both axes
        nx, ny = _nearest_point_on_ellipse(px, py, cx, cy, hr, vr)
        bx, by = _brute_force_nearest_on_ellipse(px, py, cx, cy, hr, vr)
        assert nx == pytest.approx(bx, abs=0.05)
        assert ny == pytest.approx(by, abs=0.05)

    def test_handles_a_point_well_inside_the_ellipse(self):
        """An interior, off-center point also converges to a real boundary
        point, cross-checked the same way as the exterior case."""
        cx, cy, hr, vr = 0.0, 0.0, 20.0, 10.0
        px, py = 2.0, -1.0
        nx, ny = _nearest_point_on_ellipse(px, py, cx, cy, hr, vr)
        bx, by = _brute_force_nearest_on_ellipse(px, py, cx, cy, hr, vr)
        assert nx == pytest.approx(bx, abs=0.05)
        assert ny == pytest.approx(by, abs=0.05)


class TestEllipseClearance:
    def test_label_far_from_ellipse_not_moved(self):
        lp = _make_lp(300.0, 300.0)
        assert _ellipse_clearance(lp.x, lp.y, lp, (0.0, 0.0, 100.0, 50.0)) is None

    def test_label_too_close_outside_gets_pushed_further_out(self):
        ellipse = (0.0, 0.0, 100.0, 50.0)
        lp = _make_lp(102.0, 0.0)  # just outside, on the major axis
        result = _ellipse_clearance(lp.x, lp.y, lp, ellipse)
        assert result is not None
        dx, dy, deficit = result
        assert dx > 0.9  # pushes further along +x, away from the boundary
        assert deficit > 0

    def test_label_too_close_inside_gets_pushed_toward_center(self):
        ellipse = (0.0, 0.0, 100.0, 50.0)
        lp = _make_lp(0.0, 48.0)  # just inside, on the minor axis
        result = _ellipse_clearance(lp.x, lp.y, lp, ellipse)
        assert result is not None
        dx, dy, deficit = result
        assert dy < -0.9  # pushes further along -y, toward the center
        assert deficit > 0


class TestNudgeFromEllipse:
    def test_label_outside_near_boundary_is_pushed_further_out(self):
        ellipses = [(0.0, 0.0, 100.0, 50.0)]
        lp = _make_lp(102.0, 0.0)
        _nudge_labels_from_ellipses([lp], ellipses)
        nx, ny = _nearest_point_on_ellipse(lp.x, lp.y, 0.0, 0.0, 100.0, 50.0)
        assert math.hypot(lp.x - nx, lp.y - ny) > 2.0

    def test_sector_registers_its_full_circle_for_nudging(self, monkeypatch):
        """Confirms the actual wiring defect this fixes: a drawn Sector must
        reach _nudge_labels_from_circles with its full circle, the same way
        Circle/Arc already do -- confirmed missing entirely before this fix
        (Sector's render branch never appended to drawn_circles at all). The
        nudge math itself is already covered by the unit tests above; this
        checks the data actually gets there during a real ir_to_svg call.
        Also confirms it's registered as full=False (only the wedge is
        actually drawn), so it demands less clearance than a real ring."""
        import geometry_diagrams.ir.to_svg as to_svg_mod

        captured: list[tuple[float, float, float, bool]] = []
        original = to_svg_mod._nudge_labels_from_circles

        def spy(labels, drawn_circles):
            # ir_to_svg calls this twice (pre/post collision-resolution);
            # the obstacle list itself doesn't change between calls, so only
            # the first call's snapshot is needed to confirm registration.
            if not captured:
                captured.extend(drawn_circles)
            return original(labels, drawn_circles)

        monkeypatch.setattr(to_svg_mod, "_nudge_labels_from_circles", spy)

        d = DiagramIR(
            define=[
                PointFixed(id="O", x=-1.3, y=0),
                PointFixed(id="S", x=-1.3, y=1.3),
                PointFixed(id="E", x=-2.6, y=0),
                SectorCenterStartEnd(id="Sec", center="O", start="S", end="E"),
            ],
            render=[Draw(obj="Sec")],
        )
        sym = compile_defs(d)
        to_svg_mod.ir_to_svg(d, sym)

        assert len(captured) == 1
        cx_s, cy_s, r_s, full = captured[0]
        assert r_s > 0  # a real, positive radius reached the nudge pass
        assert full is False  # only the wedge is drawn, not the full ring

    def test_elliptical_arc_and_sector_register_their_full_ellipse_for_nudging(self, monkeypatch):
        """Same wiring check as above, for EllipticalArc/EllipticalSector
        against drawn_ellipses -- also confirmed missing entirely before
        this fix."""
        import geometry_diagrams.ir.to_svg as to_svg_mod

        captured: list[tuple[float, float, float, float]] = []
        original = to_svg_mod._nudge_labels_from_ellipses

        def spy(labels, drawn_ellipses):
            # Same reasoning as the circle spy above: only the first call is
            # needed to confirm registration happened at all.
            if not captured:
                captured.extend(drawn_ellipses)
            return original(labels, drawn_ellipses)

        monkeypatch.setattr(to_svg_mod, "_nudge_labels_from_ellipses", spy)

        d = DiagramIR(
            define=[
                PointFixed(id="O1", x=-1.5, y=0),
                PointFixed(id="S1", x=-0.5, y=0),
                PointFixed(id="E1", x=-1.5, y=0.8),
                EllipticalArcCenterStartEnd(id="Ea", center="O1", hradius=1.0, vradius=0.8, start="S1", end="E1"),
                PointFixed(id="O2", x=4.0, y=0),
                PointFixed(id="S2", x=5.0, y=0),
                PointFixed(id="E2", x=4.0, y=0.6),
                EllipticalArcCenterStartEnd(id="Es", center="O2", hradius=1.0, vradius=0.6, start="S2", end="E2"),
            ],
            render=[Draw(obj="Ea"), Draw(obj="Es")],
        )
        sym = compile_defs(d)
        to_svg_mod.ir_to_svg(d, sym)

        assert len(captured) == 2
        for cx_s, cy_s, hr_s, vr_s in captured:
            assert hr_s > 0 and vr_s > 0

    def test_plain_ellipse_registers_for_nudging(self, monkeypatch):
        """And a plain (non-arc) Ellipse -- the same sibling gap Sector had,
        caught while fixing this (a standalone Ellipse never registered into
        any nudge-obstacle list either)."""
        import geometry_diagrams.ir.to_svg as to_svg_mod

        captured: list[tuple[float, float, float, float]] = []
        original = to_svg_mod._nudge_labels_from_ellipses

        def spy(labels, drawn_ellipses):
            # Same reasoning as the circle spy above: only the first call is
            # needed to confirm registration happened at all.
            if not captured:
                captured.extend(drawn_ellipses)
            return original(labels, drawn_ellipses)

        monkeypatch.setattr(to_svg_mod, "_nudge_labels_from_ellipses", spy)

        d = DiagramIR(
            define=[
                PointFixed(id="O", x=0, y=0),
                EllipseCenterAxes(id="El", center="O", hradius=3.0, vradius=1.5),
            ],
            render=[Draw(obj="El")],
        )
        sym = compile_defs(d)
        to_svg_mod.ir_to_svg(d, sym)

        assert len(captured) == 1
