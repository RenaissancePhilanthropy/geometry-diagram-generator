"""Tests for slash-style segment mark styles in ir/to_svg.py.

TikZ uses _MARK_SYMBOLS = ["|", "||", "|||", "s", "s|", "s||"] cycling by group index.
The SVG renderer previously only handled tick counts (groups 1-3).
Groups 4+ (corresponding to "s", "s|", "s||") need a diagonal slash glyph.

Tests are written FIRST (TDD red phase).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
import pytest

from geometry_diagrams.ir.ir import (
    Canvas,
    DiagramIR,
    Draw,
    MarkSegments,
    PointFixed,
    Segment,
)
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_svg import ir_to_svg

_SVG_NS = "http://www.w3.org/2000/svg"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compile_svg(diagram: DiagramIR) -> str:
    sym = compile_defs(diagram)
    return ir_to_svg(diagram, sym)


def _parse(svg_str: str) -> ET.Element:
    return ET.fromstring(svg_str)


def _findall(root: ET.Element, tag: str) -> list[ET.Element]:
    result = root.findall(f".//{{{_SVG_NS}}}{tag}")
    if not result:
        result = root.findall(f".//{tag}")
    return result


def _mark_elements(root: ET.Element) -> list[ET.Element]:
    """Return all elements with data-role='mark-segment'."""
    return [el for el in root.iter() if el.get("data-role") == "mark-segment"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _four_segments_diagram() -> DiagramIR:
    """Four segments each in a different group (groups 1-4).

    Groups 1-3 → "|", "||", "|||" (1/2/3 perpendicular ticks).
    Group 4    → "s"              (1 diagonal slash mark).
    """
    return DiagramIR(
        canvas=Canvas(xmin=-1, xmax=10, ymin=-1, ymax=6),
        define=[
            PointFixed(id="A1", x=0, y=0),
            PointFixed(id="B1", x=2, y=0),
            PointFixed(id="A2", x=3, y=0),
            PointFixed(id="B2", x=5, y=0),
            PointFixed(id="A3", x=6, y=0),
            PointFixed(id="B3", x=8, y=0),
            PointFixed(id="A4", x=0, y=3),
            PointFixed(id="B4", x=2, y=3),
            Segment(id="s1", a="A1", b="B1"),
            Segment(id="s2", a="A2", b="B2"),
            Segment(id="s3", a="A3", b="B3"),
            Segment(id="s4", a="A4", b="B4"),
        ],
        render=[
            Draw(obj="s1"), Draw(obj="s2"), Draw(obj="s3"), Draw(obj="s4"),
            MarkSegments(segs=["s1"], group="g1"),  # → "|"   (1 tick)
            MarkSegments(segs=["s2"], group="g2"),  # → "||"  (2 ticks)
            MarkSegments(segs=["s3"], group="g3"),  # → "|||" (3 ticks)
            MarkSegments(segs=["s4"], group="g4"),  # → "s"   (1 slash)
        ],
    )


def _six_segments_diagram() -> DiagramIR:
    """Six segments across six groups, cycling through all six mark symbols."""
    define = []
    render = []
    for i in range(6):
        aid = f"A{i}"
        bid = f"B{i}"
        sid = f"seg{i}"
        gid = f"grp{i}"
        define += [
            PointFixed(id=aid, x=i * 3, y=0),
            PointFixed(id=bid, x=i * 3 + 2, y=0),
            Segment(id=sid, a=aid, b=bid),
        ]
        render += [Draw(obj=sid), MarkSegments(segs=[sid], group=gid)]
    return DiagramIR(
        canvas=Canvas(xmin=-1, xmax=20, ymin=-1, ymax=3),
        define=define,
        render=render,
    )


# ---------------------------------------------------------------------------
# 1. Existing tick behaviour preserved (regression)
# ---------------------------------------------------------------------------

class TestTickMarksPreserved:
    def test_group1_emits_one_tick(self):
        """Group 1 ("|") must emit exactly 1 mark-segment <line> (perpendicular tick)."""
        d = DiagramIR(
            canvas=Canvas(xmin=-1, xmax=5, ymin=-1, ymax=3),
            define=[
                PointFixed(id="A", x=0, y=0),
                PointFixed(id="B", x=4, y=0),
                Segment(id="AB", a="A", b="B"),
            ],
            render=[Draw(obj="AB"), MarkSegments(segs=["AB"], group="g1")],
        )
        svg = _compile_svg(d)
        root = _parse(svg)
        marks = _mark_elements(root)
        assert len(marks) == 1, f"Expected 1 mark-segment element, got {len(marks)}"

    def test_group2_emits_two_ticks(self):
        """Group 2 ("||") must emit exactly 2 mark-segment <line> elements."""
        d = DiagramIR(
            canvas=Canvas(xmin=-1, xmax=5, ymin=-1, ymax=3),
            define=[
                PointFixed(id="A", x=0, y=0),
                PointFixed(id="B", x=4, y=0),
                PointFixed(id="C", x=0, y=2),
                PointFixed(id="E", x=4, y=2),
                Segment(id="AB", a="A", b="B"),
                Segment(id="CE", a="C", b="E"),
            ],
            render=[
                Draw(obj="AB"), Draw(obj="CE"),
                MarkSegments(segs=["AB"], group="g1"),  # group 1 → |
                MarkSegments(segs=["CE"], group="g2"),  # group 2 → ||
            ],
        )
        svg = _compile_svg(d)
        root = _parse(svg)
        marks_by_seg = {}
        for el in _mark_elements(root):
            seg = el.get("data-segment")
            marks_by_seg.setdefault(seg, []).append(el)
        assert len(marks_by_seg.get("CE", [])) == 2, (
            f"Expected 2 mark-segment elements for CE (group 2), "
            f"got {len(marks_by_seg.get('CE', []))}"
        )


# ---------------------------------------------------------------------------
# 2. Group 4 (slash "s") emits a diagonal mark element
# ---------------------------------------------------------------------------

class TestSlashMarkEmitted:
    def test_group4_emits_mark_segment_element(self):
        """Group 4 must produce at least one mark-segment element (slash)."""
        diagram = _four_segments_diagram()
        svg = _compile_svg(diagram)
        root = _parse(svg)

        # Collect mark-segment elements per segment
        marks_by_seg: dict[str, list] = {}
        for el in _mark_elements(root):
            seg = el.get("data-segment")
            marks_by_seg.setdefault(seg, []).append(el)

        assert "s4" in marks_by_seg, (
            "Group 4 (slash 's') produced no mark-segment elements for segment s4.\n"
            f"SVG:\n{svg[:3000]}"
        )

    def test_group4_slash_element_is_line_or_path(self):
        """The slash mark must be rendered as a <line> or <path> element."""
        diagram = _four_segments_diagram()
        svg = _compile_svg(diagram)
        root = _parse(svg)

        slash_marks = [
            el for el in _mark_elements(root)
            if el.get("data-segment") == "s4"
        ]
        assert slash_marks, "No mark-segment elements found for s4 (slash group)"

        for el in slash_marks:
            tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            assert tag in ("line", "path", "g"), (
                f"Unexpected tag {tag!r} for slash mark element"
            )

    def test_slash_mark_has_data_role(self):
        """Slash mark elements must carry data-role='mark-segment'."""
        diagram = _four_segments_diagram()
        svg = _compile_svg(diagram)
        root = _parse(svg)

        marks = _mark_elements(root)
        s4_marks = [m for m in marks if m.get("data-segment") == "s4"]
        assert s4_marks, f"No marks found for segment s4. All marks: {[m.attrib for m in marks]}"
        for m in s4_marks:
            assert m.get("data-role") == "mark-segment"


# ---------------------------------------------------------------------------
# 3. Slash mark is visually DIFFERENT from tick mark
# ---------------------------------------------------------------------------

class TestSlashDifferentFromTick:
    def test_slash_mark_geometry_differs_from_tick(self):
        """The slash mark line endpoints must be at a different angle than perpendicular ticks.

        A perpendicular tick on a horizontal segment has x1==x2 (vertical line).
        A slash mark must have x1 != x2 (diagonal line).
        """
        # Use a horizontal segment so the perpendicular tick is vertical (x1==x2)
        d = DiagramIR(
            canvas=Canvas(xmin=-1, xmax=12, ymin=-2, ymax=4),
            define=[
                PointFixed(id="A1", x=0, y=0),
                PointFixed(id="B1", x=3, y=0),
                PointFixed(id="A2", x=4, y=0),
                PointFixed(id="B2", x=7, y=0),
                PointFixed(id="A3", x=8, y=0),
                PointFixed(id="B3", x=11, y=0),
                PointFixed(id="C1", x=0, y=2),
                PointFixed(id="D1", x=3, y=2),
                Segment(id="seg1", a="A1", b="B1"),
                Segment(id="seg2", a="A2", b="B2"),
                Segment(id="seg3", a="A3", b="B3"),
                Segment(id="slash_seg", a="C1", b="D1"),
            ],
            render=[
                Draw(obj="seg1"), Draw(obj="seg2"), Draw(obj="seg3"), Draw(obj="slash_seg"),
                MarkSegments(segs=["seg1"], group="eq1"),   # "|"
                MarkSegments(segs=["seg2"], group="eq2"),   # "||"
                MarkSegments(segs=["seg3"], group="eq3"),   # "|||"
                MarkSegments(segs=["slash_seg"], group="eq4"),  # "s" — slash
            ],
        )
        svg = _compile_svg(d)
        root = _parse(svg)

        def get_lines_for_seg(seg_id: str) -> list[ET.Element]:
            return [
                el for el in _mark_elements(root)
                if el.get("data-segment") == seg_id
                and (el.tag.split("}")[-1] if "}" in el.tag else el.tag) == "line"
            ]

        tick_lines = get_lines_for_seg("seg1")
        slash_lines = get_lines_for_seg("slash_seg")

        if not tick_lines:
            pytest.skip("No <line> elements for tick mark seg1 — can't compare geometry")
        if not slash_lines:
            pytest.fail(
                "No <line> elements for slash mark (slash_seg / group eq4).\n"
                f"All mark elements: {[(el.get('data-segment'), el.attrib) for el in _mark_elements(root)]}"
            )

        # Tick: on a horizontal segment, perpendicular tick → x1 ≈ x2
        tick = tick_lines[0]
        tick_dx = abs(float(tick.get("x1", 0)) - float(tick.get("x2", 0)))
        # Tick should be nearly vertical (dx ≈ 0) for a horizontal segment
        assert tick_dx < 1.0, f"Tick mark is not vertical (dx={tick_dx:.2f}) on horizontal segment"

        # Slash: diagonal → x1 != x2 significantly
        slash = slash_lines[0]
        slash_dx = abs(float(slash.get("x1", 0)) - float(slash.get("x2", 0)))
        assert slash_dx > 2.0, (
            f"Slash mark is not diagonal (dx={slash_dx:.2f}); "
            "expected a significantly non-vertical line for a slash glyph"
        )


# ---------------------------------------------------------------------------
# 4. Groups 5 and 6 (s|, s||) emit both slash and extra ticks
# ---------------------------------------------------------------------------

class TestSlashPlusTicks:
    def test_group5_symbol_is_s_with_one_tick(self):
        """Group 5 ('s|') must emit elements for both a slash AND 1 extra tick."""
        diagram = _six_segments_diagram()
        svg = _compile_svg(diagram)
        root = _parse(svg)

        # seg4 = group 5 → "s|"
        # We expect > 1 mark-segment element (slash + 1 tick line)
        marks_g5 = [
            el for el in _mark_elements(root)
            if el.get("data-segment") == "seg4"
        ]
        assert len(marks_g5) >= 2, (
            f"Group 5 ('s|') should emit slash + tick (≥2 elements), "
            f"got {len(marks_g5)} for seg4"
        )

    def test_group6_symbol_is_s_with_two_ticks(self):
        """Group 6 ('s||') must emit elements for slash + 2 extra ticks (≥3 total)."""
        diagram = _six_segments_diagram()
        svg = _compile_svg(diagram)
        root = _parse(svg)

        # seg5 = group 6 → "s||"
        marks_g6 = [
            el for el in _mark_elements(root)
            if el.get("data-segment") == "seg5"
        ]
        assert len(marks_g6) >= 3, (
            f"Group 6 ('s||') should emit slash + 2 ticks (≥3 elements), "
            f"got {len(marks_g6)} for seg5"
        )


# ---------------------------------------------------------------------------
# 5. SVG remains well-formed after mark changes
# ---------------------------------------------------------------------------

class TestMarksSvgWellFormed:
    def test_four_groups_valid_xml(self):
        svg = _compile_svg(_four_segments_diagram())
        root = ET.fromstring(svg)
        assert root is not None

    def test_six_groups_valid_xml(self):
        svg = _compile_svg(_six_segments_diagram())
        root = ET.fromstring(svg)
        assert root is not None
