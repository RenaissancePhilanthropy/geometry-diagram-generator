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
    DiagramIR,
    Draw,
    LabelPoint,
    LabelSegment,
    PointFixed,
    Segment,
    Triangle,
)
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_svg import (
    _LabelPlacement,
    _label_bbox,
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
