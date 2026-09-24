"""Tests for slash-style segment mark styles in ir/to_svg.py.

TikZ uses _MARK_SYMBOLS = ["|", "||", "|||", "s", "s|", "s||"] cycling by group index.
The SVG renderer previously only handled tick counts (groups 1-3).
Groups 4+ (corresponding to "s", "s|", "s||") need a diagonal slash glyph.

Tests are written FIRST (TDD red phase).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
import pytest

import math

from geometry_diagrams.ir.ir import (
    ArcCenterStartEnd,
    Canvas,
    DiagramIR,
    Draw,
    EllipticalArcCenterStartEnd,
    LabelAlongArc,
    MarkArcs,
    MarkSegments,
    PointFixed,
    Ray,
    Segment,
    SectorCenterStartEnd,
)
from geometry_diagrams.ir.label_bounds import find_out_of_bounds_labels
from geometry_diagrams.ir.render_util import arc_params
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


def _arc_mark_elements(root: ET.Element) -> list[ET.Element]:
    """Return all elements with data-role='mark-arc'."""
    return [el for el in root.iter() if el.get("data-role") == "mark-arc"]


def _arc_text_wrappers(root: ET.Element) -> list[ET.Element]:
    """Return the per-glyph <g data-role='label-along-arc'> wrapper(s), i.e.
    one <g> holding one <text> per curved glyph.

    Deliberately excludes the single-label fallback (used when a label
    can't be laid out glyph-by-glyph), which carries the same data-role but
    is either a bare <text> (plain string) or a <g><path/></g> (mathtext) —
    see _arc_text_fallback_labels(). A wrapper is identified by containing
    at least one <text> CHILD; the mathtext fallback's <g> wraps a <path>
    instead.
    """
    return [
        el for el in root.iter()
        if el.tag.endswith("g") and el.get("data-role") == "label-along-arc"
        and any(child.tag.endswith("text") for child in el)
    ]


def _arc_text_fallback_labels(root: ET.Element) -> list[ET.Element]:
    """Return the single-label fallback element(s) for LabelAlongArc: either
    a bare <text> (plain string) or a <g><path/></g> (mathtext)."""
    return [
        el for el in root.iter()
        if el.get("data-role") == "label-along-arc"
        and (el.tag.endswith("text") or (el.tag.endswith("g") and el not in _arc_text_wrappers(root)))
    ]


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


# ---------------------------------------------------------------------------
# 6. Explicit MarkSegments.ticks — arbitrary count, no palette cap
# ---------------------------------------------------------------------------

class TestExplicitTicksCount:
    def _one_segment_diagram(self, **mark_kwargs) -> DiagramIR:
        return DiagramIR(
            canvas=Canvas(xmin=-1, xmax=5, ymin=-1, ymax=3),
            define=[
                PointFixed(id="A", x=0, y=0),
                PointFixed(id="B", x=4, y=0),
                Segment(id="AB", a="A", b="B"),
            ],
            render=[Draw(obj="AB"), MarkSegments(segs=["AB"], **mark_kwargs)],
        )

    def test_explicit_ticks_beyond_palette_emits_exact_count(self):
        """ticks=7 exceeds the 6-entry mark-symbol palette but must still
        emit exactly 7 tick strokes — no cap for the explicit-count path."""
        svg = _compile_svg(self._one_segment_diagram(ticks=7))
        root = _parse(svg)
        marks = _mark_elements(root)
        assert len(marks) == 7, f"Expected 7 mark-segment elements, got {len(marks)}"

    def test_explicit_ticks_overrides_group_derived_count(self):
        """An explicit `ticks` count wins over whatever the group name would
        otherwise imply."""
        svg = _compile_svg(self._one_segment_diagram(group="g1", ticks=5))
        root = _parse(svg)
        marks = _mark_elements(root)
        assert len(marks) == 5

    def test_explicit_ticks_does_not_consume_a_group_slot(self):
        """An op carrying an explicit `ticks` count must not shift the
        auto-assigned symbol given to other (implicit) groups."""
        diagram = DiagramIR(
            canvas=Canvas(xmin=-1, xmax=10, ymin=-1, ymax=3),
            define=[
                PointFixed(id="A", x=0, y=0),
                PointFixed(id="B", x=2, y=0),
                PointFixed(id="C", x=3, y=0),
                PointFixed(id="D", x=5, y=0),
                Segment(id="s1", a="A", b="B"),
                Segment(id="s2", a="C", b="D"),
            ],
            render=[
                Draw(obj="s1"), Draw(obj="s2"),
                MarkSegments(segs=["s1"], group="explicit_group", ticks=6),
                MarkSegments(segs=["s2"], group="alpha"),
            ],
        )
        svg = _compile_svg(diagram)
        root = _parse(svg)
        alpha_marks = [el for el in _mark_elements(root) if el.get("data-segment") == "s2"]
        assert len(alpha_marks) == 1, (
            "alpha is the first implicit group encountered and should get the "
            f"first auto-assigned symbol (a single tick), got {len(alpha_marks)}"
        )


# ---------------------------------------------------------------------------
# 7. MarkArcs — radial ticks on circular arcs and sectors
# ---------------------------------------------------------------------------

def _arc_diagram(def_cls=ArcCenterStartEnd, **mark_kwargs) -> DiagramIR:
    return DiagramIR(
        canvas=Canvas(xmin=-3, xmax=3, ymin=-3, ymax=3),
        define=[
            PointFixed(id="O", x=0, y=0),
            PointFixed(id="S", x=2, y=0),
            PointFixed(id="E", x=0, y=2),
            def_cls(id="arc1", center="O", start="S", end="E"),
        ],
        render=[MarkArcs(arcs=["arc1"], **mark_kwargs)],
    )


class TestMarkArcs:
    def test_explicit_ticks_emits_exact_count(self):
        svg = _compile_svg(_arc_diagram(ticks=4))
        root = _parse(svg)
        marks = _arc_mark_elements(root)
        assert len(marks) == 4

    def test_ticks_straddle_the_curve_radially(self):
        """Each stroke's two endpoints sit just inside and just outside the
        arc's own radius (in pixel space) -- proves these are curved-edge
        ticks, not a radius, and that they're centered on the curve."""
        from geometry_diagrams.ir.to_svg import _TICK_LEN, px_per_construction_unit

        diagram = _arc_diagram(ticks=3)
        sym = compile_defs(diagram)
        svg = ir_to_svg(diagram, sym)
        root = _parse(svg)
        cx, cy, r, _s, _e, _sx, _sy = arc_params("arc1", sym)
        scale = px_per_construction_unit(6.0, 6.0)  # Canvas(-3..3) on both axes
        px_center = (250.0, 250.0)  # canvas is symmetric about the origin
        marks = _arc_mark_elements(root)
        assert len(marks) == 3
        for el in marks:
            x1, y1 = float(el.get("x1")), float(el.get("y1"))
            x2, y2 = float(el.get("x2")), float(el.get("y2"))
            d1 = math.hypot(x1 - px_center[0], y1 - px_center[1])
            d2 = math.hypot(x2 - px_center[0], y2 - px_center[1])
            inner, outer = sorted((d1, d2))
            assert inner == pytest.approx(r * scale - _TICK_LEN, abs=0.5)
            assert outer == pytest.approx(r * scale + _TICK_LEN, abs=0.5)

    def test_sector_gets_ticks_on_its_curved_edge_only(self):
        svg = _compile_svg(_arc_diagram(def_cls=SectorCenterStartEnd, ticks=2))
        root = _parse(svg)
        marks = _arc_mark_elements(root)
        assert len(marks) == 2

    def test_shared_group_gives_a_segment_and_an_arc_the_same_count(self):
        diagram = DiagramIR(
            canvas=Canvas(xmin=-3, xmax=5, ymin=-3, ymax=3),
            define=[
                PointFixed(id="A", x=0, y=0),
                PointFixed(id="B", x=4, y=0),
                Segment(id="AB", a="A", b="B"),
                PointFixed(id="O", x=0, y=0),
                PointFixed(id="S", x=2, y=0),
                PointFixed(id="E", x=0, y=2),
                ArcCenterStartEnd(id="arc1", center="O", start="S", end="E"),
            ],
            render=[
                MarkSegments(segs=["AB"], group="tick2"),
                MarkArcs(arcs=["arc1"], group="tick2"),
            ],
        )
        svg = _compile_svg(diagram)
        root = _parse(svg)
        assert len(_mark_elements(root)) == 2
        assert len(_arc_mark_elements(root)) == 2

    def test_mark_arcs_group_participates_in_encounter_order_with_segments(self):
        """An unnamed group on a MarkArcs op, encountered first, should
        claim the first auto-assigned symbol -- ahead of a MarkSegments
        group encountered later."""
        diagram = DiagramIR(
            canvas=Canvas(xmin=-3, xmax=5, ymin=-3, ymax=3),
            define=[
                PointFixed(id="A", x=0, y=0),
                PointFixed(id="B", x=4, y=0),
                Segment(id="AB", a="A", b="B"),
                PointFixed(id="O", x=0, y=0),
                PointFixed(id="S", x=2, y=0),
                PointFixed(id="E", x=0, y=2),
                ArcCenterStartEnd(id="arc1", center="O", start="S", end="E"),
            ],
            render=[
                MarkArcs(arcs=["arc1"], group="alpha"),
                MarkSegments(segs=["AB"], group="beta"),
            ],
        )
        svg = _compile_svg(diagram)
        root = _parse(svg)
        # alpha is encountered first -> index 1 -> 1 arc tick.
        assert len(_arc_mark_elements(root)) == 1
        # beta is encountered second -> index 2 -> "||" -> 2 segment ticks.
        assert len(_mark_elements(root)) == 2

    def test_elliptical_arc_is_skipped_with_a_warning(self):
        diagram = DiagramIR(
            canvas=Canvas(xmin=-5, xmax=5, ymin=-2, ymax=2),
            define=[
                PointFixed(id="O", x=0, y=0),
                PointFixed(id="S", x=4, y=0),
                PointFixed(id="E", x=0, y=1),
                EllipticalArcCenterStartEnd(id="ea1", center="O", hradius=4, vradius=1, start="S", end="E"),
            ],
            render=[MarkArcs(arcs=["ea1"], ticks=2)],
        )
        sym = compile_defs(diagram)
        warnings: list[str] = []
        svg = ir_to_svg(diagram, sym, warnings=warnings)
        root = _parse(svg)
        assert any("is not a circular arc/sector" in w for w in warnings)
        assert len(_arc_mark_elements(root)) == 0

    def test_undefined_arc_is_skipped_with_a_warning(self):
        diagram = DiagramIR(define=[], render=[MarkArcs(arcs=["missing"])])
        sym = compile_defs(diagram)
        warnings: list[str] = []
        svg = ir_to_svg(diagram, sym, warnings=warnings)
        assert any("missing" in w for w in warnings)


# ---------------------------------------------------------------------------
# 7.5. MarkSegments on a Ray — render_util.seg_endpoints() widened to
# recognize ir.Ray (same a/b point-id fields as ir.Segment), not just
# ir.Segment. Ticket 06: a ray marked equal to a segment previously
# compiled fine but crashed uncaught inside seg_endpoints() at render time.
# ---------------------------------------------------------------------------

def test_mark_segments_on_a_ray_renders_without_crashing():
    diagram = DiagramIR(
        canvas=Canvas(xmin=-1, xmax=10, ymin=-1, ymax=6),
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=2, y=0),
            PointFixed(id="C", x=0, y=3),
            PointFixed(id="D", x=2, y=3),
            Segment(id="seg1", a="A", b="B"),
            Ray(id="ray1", a="C", b="D"),
        ],
        render=[
            Draw(obj="seg1"), Draw(obj="ray1"),
            MarkSegments(segs=["seg1", "ray1"], group="g1"),
        ],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    marks_by_seg = {}
    for el in _mark_elements(root):
        marks_by_seg.setdefault(el.get("data-segment"), []).append(el)
    assert len(marks_by_seg.get("seg1", [])) == 1
    assert len(marks_by_seg.get("ray1", [])) == 1


# ---------------------------------------------------------------------------
# 8. LabelAlongArc — per-glyph rotated text
# ---------------------------------------------------------------------------

class TestLabelAlongArc:
    def _diagram(self, text="ABC", **kwargs) -> DiagramIR:
        return DiagramIR(
            canvas=Canvas(xmin=-3, xmax=3, ymin=-3, ymax=3),
            define=[
                PointFixed(id="O", x=0, y=0),
                PointFixed(id="S", x=2, y=0),
                PointFixed(id="E", x=0, y=2),
                ArcCenterStartEnd(id="arc1", center="O", start="S", end="E"),
            ],
            render=[LabelAlongArc(arc="arc1", text=text, **kwargs)],
        )

    def test_emits_one_rotated_text_per_glyph(self):
        svg = _compile_svg(self._diagram("ABC"))
        root = _parse(svg)
        wrapper = _arc_text_wrappers(root)[0]
        texts = _findall(wrapper, "text")
        assert len(texts) == 3
        for el in texts:
            assert el.get("transform", "").startswith("rotate(")

    def test_wrapper_carries_data_bbox_and_label_text(self):
        svg = _compile_svg(self._diagram("ABC"))
        root = _parse(svg)
        wrapper = _arc_text_wrappers(root)[0]
        assert wrapper.get("data-bbox") is not None
        assert wrapper.get("data-label-text") == "ABC"

    def test_wrapper_is_the_only_element_with_data_bbox(self):
        svg = _compile_svg(self._diagram("ABC"))
        root = _parse(svg)
        wrapper = _arc_text_wrappers(root)[0]
        stamped = [el for el in wrapper.iter() if el.get("data-bbox")]
        assert stamped == [wrapper]

    def test_bbox_contains_every_glyph_anchor(self):
        svg = _compile_svg(self._diagram("ABC"))
        root = _parse(svg)
        wrapper = _arc_text_wrappers(root)[0]
        x0, y0, x1, y1 = (float(v) for v in wrapper.get("data-bbox").split(","))
        for el in _findall(wrapper, "text"):
            x, y = float(el.get("x")), float(el.get("y"))
            assert x0 <= x <= x1
            assert y0 <= y <= y1

    def test_bbox_is_accepted_by_label_bounds(self):
        svg = _compile_svg(self._diagram("ABC"))
        assert find_out_of_bounds_labels(svg) == []

    def test_rotation_is_negated_versus_geometry_space(self):
        """SVG's rotate() must be the negation of the geometry-space angle
        arc_text_glyph_layout() computes -- to_svg.py's y-flip requires it."""
        from geometry_diagrams.ir.render_util import arc_text_glyph_layout

        diagram = self._diagram("x")  # arc1: O=(0,0), S=(2,0), E=(0,2)
        sym = compile_defs(diagram)
        cx, cy, r, s_deg, e_deg, _sx, _sy = arc_params("arc1", sym)
        expected_rot_geo = arc_text_glyph_layout(cx, cy, r, s_deg, e_deg, [1.0])[0][2]

        svg = ir_to_svg(diagram, sym)
        root = _parse(svg)
        el = _findall(_arc_text_wrappers(root)[0], "text")[0]
        transform = el.get("transform")
        angle = float(transform[len("rotate("):].split(",")[0])
        assert angle == pytest.approx(-expected_rot_geo, abs=0.5)

    def test_lower_half_text_is_not_upside_down(self):
        diagram = DiagramIR(
            canvas=Canvas(xmin=-3, xmax=3, ymin=-3, ymax=3),
            define=[
                PointFixed(id="O", x=0, y=0),
                PointFixed(id="S", x=-0.01, y=-1),
                PointFixed(id="E", x=0.01, y=-1),
                ArcCenterStartEnd(id="arc1", center="O", start="S", end="E"),
            ],
            render=[LabelAlongArc(arc="arc1", text="abc")],
        )
        svg = _compile_svg(diagram)
        root = _parse(svg)
        for el in _findall(_arc_text_wrappers(root)[0], "text"):
            transform = el.get("transform")
            angle = float(transform[len("rotate("):].split(",")[0])
            assert abs((angle + 180) % 360 - 180) <= 90.0

    def test_inside_places_glyphs_closer_to_the_center_than_outside(self):
        svg_out = _compile_svg(self._diagram("x", side="outside"))
        svg_in = _compile_svg(self._diagram("x", side="inside"))
        root_out = _parse(svg_out)
        root_in = _parse(svg_in)
        el_out = _findall(_arc_text_wrappers(root_out)[0], "text")[0]
        el_in = _findall(_arc_text_wrappers(root_in)[0], "text")[0]
        cx, cy = 250.0, 250.0  # canvas is symmetric about the origin -> center of SVG
        d_out = math.hypot(float(el_out.get("x")) - cx, float(el_out.get("y")) - cy)
        d_in = math.hypot(float(el_in.get("x")) - cx, float(el_in.get("y")) - cy)
        assert d_in < d_out

    def test_sector_text_follows_the_curved_edge(self):
        diagram = DiagramIR(
            canvas=Canvas(xmin=-3, xmax=3, ymin=-3, ymax=3),
            define=[
                PointFixed(id="O", x=0, y=0),
                PointFixed(id="S", x=2, y=0),
                PointFixed(id="E", x=0, y=2),
                SectorCenterStartEnd(id="sec1", center="O", start="S", end="E"),
            ],
            render=[LabelAlongArc(arc="sec1", text="abc")],
        )
        svg = _compile_svg(diagram)
        root = _parse(svg)
        assert len(_arc_text_wrappers(root)) == 1
        assert len(_findall(_arc_text_wrappers(root)[0], "text")) == 3

    def test_math_text_falls_back_to_a_single_label_with_a_warning(self):
        diagram = self._diagram(text=r"\frac{1}{2}")
        sym = compile_defs(diagram)
        warnings: list[str] = []
        svg = ir_to_svg(diagram, sym, warnings=warnings)
        assert any("cannot be laid out per glyph" in w for w in warnings)
        root = _parse(svg)
        assert _arc_text_wrappers(root) == []
        assert len(_arc_text_fallback_labels(root)) == 1

    def test_subscript_text_falls_back_rather_than_dropping_the_subscript(self):
        diagram = self._diagram(text="P_1")
        sym = compile_defs(diagram)
        warnings: list[str] = []
        svg = ir_to_svg(diagram, sym, warnings=warnings)
        assert any("cannot be laid out per glyph" in w for w in warnings)
        root = _parse(svg)
        assert _arc_text_wrappers(root) == []
        assert len(_arc_text_fallback_labels(root)) == 1

    def test_elliptical_arc_is_skipped_with_a_warning(self):
        diagram = DiagramIR(
            canvas=Canvas(xmin=-5, xmax=5, ymin=-2, ymax=2),
            define=[
                PointFixed(id="O", x=0, y=0),
                PointFixed(id="S", x=4, y=0),
                PointFixed(id="E", x=0, y=1),
                EllipticalArcCenterStartEnd(id="ea1", center="O", hradius=4, vradius=1, start="S", end="E"),
            ],
            render=[LabelAlongArc(arc="ea1", text="abc")],
        )
        sym = compile_defs(diagram)
        warnings: list[str] = []
        svg = ir_to_svg(diagram, sym, warnings=warnings)
        assert any("is not a circular arc/sector" in w for w in warnings)
        root = _parse(svg)
        assert _arc_text_wrappers(root) == []
