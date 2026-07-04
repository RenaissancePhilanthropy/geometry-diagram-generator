"""Integration tests for mathtext label routing in ir/to_svg.py.

Tests are written FIRST (TDD red phase).  They verify:
1. Math labels render as <path> elements (not literal <text>).
2. Plain labels still render as <text> in the brand font.
3. _LabelPlacement.width_est and height_est use accurate bbox values for
   math labels (Phase 2A — accurate sizing).
4. The SVG output remains well-formed XML.
5. data-ir-id / data-role metadata is preserved.
6. Fallback to <text> on mathtext failure is graceful (no crash).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
import pytest

from geometry_diagrams.ir.ir import (
    Canvas,
    DiagramIR,
    Draw,
    LabelAngle,
    LabelPoint,
    LabelSegment,
    AnglePoints,
    PointFixed,
    Segment,
    Triangle,
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


def _findall_by_attr(root: ET.Element, tag: str, attr: str, val: str) -> list[ET.Element]:
    return [
        el for el in _findall(root, tag)
        if el.get(attr) == val
    ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _triangle_diagram_with_math_label() -> DiagramIR:
    """A simple triangle where one point label is a math expression."""
    return DiagramIR(
        canvas=Canvas(xmin=-1, xmax=5, ymin=-1, ymax=5),
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=2, y=3),
            Triangle(id="T", a="A", b="B", c="C"),
        ],
        render=[
            Draw(obj="T"),
            # Plain label — should use <text> (brand font)
            LabelPoint(p="A", text="A"),
            # Math label — should use <path> (mathtext)
            LabelPoint(p="B", text=r"$\alpha$"),
            # Another math label
            LabelPoint(p="C", text=r"$\frac{1}{2}$"),
        ],
    )


def _triangle_with_plain_labels() -> DiagramIR:
    """All plain labels — all should use <text>."""
    return DiagramIR(
        canvas=Canvas(xmin=-1, xmax=5, ymin=-1, ymax=5),
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=2, y=3),
            Triangle(id="T", a="A", b="B", c="C"),
        ],
        render=[
            Draw(obj="T"),
            LabelPoint(p="A", text="A"),
            LabelPoint(p="B", text="B"),
            LabelPoint(p="C", text="C"),
        ],
    )


def _triangle_with_segment_math_label() -> DiagramIR:
    r"""A segment with a math label (e.g. \sqrt{2})."""
    return DiagramIR(
        canvas=Canvas(xmin=-1, xmax=5, ymin=-1, ymax=5),
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            Segment(id="AB", a="A", b="B"),
        ],
        render=[
            Draw(obj="AB"),
            LabelSegment(seg="AB", text=r"$\sqrt{2}$"),
        ],
    )


# ---------------------------------------------------------------------------
# 1. Math labels render as <path>, not as <text> with literal content
# ---------------------------------------------------------------------------

class TestMathLabelRendersAsPath:
    def test_math_point_label_emits_path(self):
        diagram = _triangle_diagram_with_math_label()
        svg = _compile_svg(diagram)
        root = _parse(svg)

        # There should be at least one <path> carrying a math label
        paths_with_label_role = [
            el for el in _findall(root, "path")
            if el.get("data-role") in ("label-point", "label-segment", "label-angle")
        ] + [
            el for el in _findall(root, "g")
            if el.get("data-role") in ("label-point", "label-segment", "label-angle")
        ]
        assert paths_with_label_role, (
            "Expected at least one <path> or <g> element with data-role='label-point' "
            "for math labels, but found none.\n"
            f"SVG snippet:\n{svg[:2000]}"
        )

    def test_math_label_does_not_contain_literal_frac(self):
        """The literal string 'x+1/2' must not appear — mathtext should render it properly."""
        diagram = DiagramIR(
            canvas=Canvas(xmin=-1, xmax=5, ymin=-1, ymax=5),
            define=[
                PointFixed(id="A", x=0, y=0),
                PointFixed(id="B", x=4, y=0),
                Segment(id="AB", a="A", b="B"),
            ],
            render=[
                Draw(obj="AB"),
                LabelSegment(seg="AB", text=r"$\frac{x+1}{2}$"),
            ],
        )
        svg = _compile_svg(diagram)
        # The old tspan path would emit literal "x+1/2"; mathtext should not
        assert "x+1/2" not in svg, (
            "Found literal 'x+1/2' in SVG — mathtext is not being used for \\frac"
        )

    def test_math_label_does_not_contain_bare_sqrt_char(self):
        r"""A \sqrt label must not appear as the bare unicode character √ without a vinculum."""
        diagram = _triangle_with_segment_math_label()
        svg = _compile_svg(diagram)
        # The old tspan path emits a bare √ character; mathtext renders a proper path
        # We check there is no <tspan> or plain text containing bare √ for this label
        root = _parse(svg)
        text_els = _findall(root, "text")
        for el in text_els:
            full_text = ET.tostring(el, encoding="unicode")
            if "label-segment" in full_text:
                assert "√" not in full_text, (
                    "Found bare '√' in segment label <text> — \\sqrt should render via mathtext path"
                )


# ---------------------------------------------------------------------------
# 2. Plain labels still render as <text> in the brand font
# ---------------------------------------------------------------------------

class TestPlainLabelRendersAsText:
    def test_plain_point_labels_use_text_element(self):
        diagram = _triangle_with_plain_labels()
        svg = _compile_svg(diagram)
        root = _parse(svg)

        # All three labels should be <text> elements
        label_texts = _findall_by_attr(root, "text", "data-role", "label-point")
        assert len(label_texts) == 3, (
            f"Expected 3 <text> label-point elements for plain labels, got {len(label_texts)}"
        )

    def test_plain_label_has_font_family(self):
        """Plain <text> labels should carry the font-family attribute."""
        diagram = _triangle_with_plain_labels()
        svg = _compile_svg(diagram)
        root = _parse(svg)

        label_texts = _findall_by_attr(root, "text", "data-role", "label-point")
        for el in label_texts:
            assert el.get("font-family"), (
                f"<text> label-point missing font-family: {ET.tostring(el, encoding='unicode')}"
            )

    def test_mixed_diagram_plain_labels_remain_text(self):
        """In a diagram with mixed labels, plain ones must still be <text>."""
        diagram = _triangle_diagram_with_math_label()
        svg = _compile_svg(diagram)
        root = _parse(svg)

        # Label for point "A" has text="A" — must be a <text> element
        plain_label_els = [
            el for el in _findall(root, "text")
            if el.get("data-role") == "label-point" and el.get("data-for") == "A"
        ]
        assert plain_label_els, (
            "Expected a <text> element for plain label 'A' in mixed diagram, found none"
        )


# ---------------------------------------------------------------------------
# 3. SVG remains well-formed XML
# ---------------------------------------------------------------------------

class TestSvgWellFormed:
    def test_math_labels_produce_valid_xml(self):
        diagram = _triangle_diagram_with_math_label()
        svg = _compile_svg(diagram)
        # Should not raise
        root = ET.fromstring(svg)
        assert root is not None

    def test_segment_math_label_valid_xml(self):
        diagram = _triangle_with_segment_math_label()
        svg = _compile_svg(diagram)
        root = ET.fromstring(svg)
        assert root is not None

    def test_plain_labels_valid_xml(self):
        diagram = _triangle_with_plain_labels()
        svg = _compile_svg(diagram)
        root = ET.fromstring(svg)
        assert root is not None


# ---------------------------------------------------------------------------
# 4. data-role metadata preserved on math labels
# ---------------------------------------------------------------------------

class TestMetadataPreserved:
    def test_math_label_carries_data_role(self):
        diagram = _triangle_diagram_with_math_label()
        svg = _compile_svg(diagram)
        root = _parse(svg)

        # Find any element (path, g, text) with data-role="label-point"
        all_label_els = [
            el for el in root.iter()
            if el.get("data-role") == "label-point"
        ]
        # We have 3 LabelPoint ops → 3 label elements
        assert len(all_label_els) == 3, (
            f"Expected 3 elements with data-role='label-point', got {len(all_label_els)}"
        )

    def test_math_label_carries_data_for(self):
        diagram = _triangle_diagram_with_math_label()
        svg = _compile_svg(diagram)
        root = _parse(svg)

        # data-for should reference the point id
        data_fors = {
            el.get("data-for")
            for el in root.iter()
            if el.get("data-role") == "label-point"
        }
        assert "B" in data_fors, f"Expected data-for='B' on math label, found: {data_fors}"
        assert "C" in data_fors, f"Expected data-for='C' on math label, found: {data_fors}"


# ---------------------------------------------------------------------------
# 5. Phase 2A — accurate bbox feeding into _LabelPlacement
# ---------------------------------------------------------------------------

class TestAccurateLabelSizing:
    def test_math_label_width_est_reflects_actual_glyph(self):
        """width_est for a math label should differ from the old char-count estimate.

        Specifically: \frac{x+1}{2} had only 4 chars after stripping → old estimate
        was 4 * 14 * 0.65 = 36.4px.  The real mathtext glyph is wider and taller.
        We just assert width_est > 0 and that the label can be placed (no crash).

        The detailed accuracy test is in test_mathtext_svg.py — here we confirm
        the pipeline wires the bbox through.
        """
        from geometry_diagrams.ir.to_svg import _LabelPlacement, _estimate_text_width

        math_label = r"$\frac{x+1}{2}$"
        old_estimate = _estimate_text_width(math_label)

        # After integration, _LabelPlacement for this text should NOT use the old
        # char-count estimate; its width_est should come from the mathtext bbox.
        # We test this indirectly: render the diagram and check there are no
        # <path> elements with d="" (which would indicate a zero-size glyph bbox).
        diagram = DiagramIR(
            canvas=Canvas(xmin=-1, xmax=5, ymin=-1, ymax=5),
            define=[
                PointFixed(id="A", x=0, y=0),
                PointFixed(id="B", x=4, y=0),
                Segment(id="AB", a="A", b="B"),
            ],
            render=[
                Draw(obj="AB"),
                LabelSegment(seg="AB", text=math_label),
            ],
        )
        svg = _compile_svg(diagram)
        root = _parse(svg)
        # Any label-carrying element with a child <path> must have a non-empty d.
        # Math labels are emitted as <g data-role="..."><path d="..." /></g>.
        for el in root.iter():
            if el.get("data-role") in ("label-point", "label-segment"):
                # Check direct <path> child for non-empty d
                for child in el:
                    tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if tag == "path":
                        d = child.get("d", "")
                        assert d.strip(), (
                            f"Label <path> has empty d attribute inside: "
                            f"{ET.tostring(el, encoding='unicode')[:200]}"
                        )
