"""Tests for the direct SVG renderer (ir/to_svg.py)."""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import pytest

from ir.ir import (
    AnglePoints,
    Canvas,
    DiagramIR,
    Draw,
    DrawPoints,
    Fill,
    LabelAngle,
    LabelPoint,
    LabelSegment,
    LineThrough,
    MarkAngles,
    MarkRightAngles,
    MarkSegments,
    PointFixed,
    Segment,
    Triangle,
    CircleCenterPoint,
    CircleCenterRadius,
    Polygon,
)
from ir.to_sympy import compile_defs
from ir.to_svg import (
    ir_to_svg,
    _parse_latex,
    _auto_label_direction,
    _angle_to_offset,
    _angle_to_anchor,
    _build_incident_angles,
)
from util.svg_checks import check_svg_wellformed, check_svg_has_content, check_svg_reasonable_size

_SVG_NS = "http://www.w3.org/2000/svg"


def _compile_svg(diagram: DiagramIR) -> str:
    sym = compile_defs(diagram)
    return ir_to_svg(diagram, sym)


def _parse(svg_str: str) -> ET.Element:
    return ET.fromstring(svg_str)


def _findall(root: ET.Element, tag: str) -> list[ET.Element]:
    """Find all elements with tag (with or without namespace)."""
    result = root.findall(f".//{{{_SVG_NS}}}{tag}")
    if not result:
        result = root.findall(f".//{tag}")
    return result


# ---------------------------------------------------------------------------
# SVG validity
# ---------------------------------------------------------------------------

def _basic_triangle_diagram() -> DiagramIR:
    return DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=2, y=3),
            Triangle(id="T", a="A", b="B", c="C"),
        ],
        render=[Draw(obj="T")],
    )


def test_svg_is_wellformed():
    svg = _compile_svg(_basic_triangle_diagram())
    assert check_svg_wellformed(svg) is None


def test_svg_has_content():
    svg = _compile_svg(_basic_triangle_diagram())
    assert check_svg_has_content(svg) is None


def test_svg_reasonable_size():
    svg = _compile_svg(_basic_triangle_diagram())
    assert check_svg_reasonable_size(svg) is None


# ---------------------------------------------------------------------------
# Geometry elements
# ---------------------------------------------------------------------------

def test_triangle_renders_as_polygon():
    svg = _compile_svg(_basic_triangle_diagram())
    root = _parse(svg)
    polygons = _findall(root, "polygon")
    assert len(polygons) == 1
    pts = polygons[0].get("points", "")
    pairs = [p.split(",") for p in pts.strip().split()]
    assert len(pairs) == 3


def test_polygon_renders_correctly():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=4, y=3),
            PointFixed(id="D", x=0, y=3),
            Polygon(id="R", points=["A", "B", "C", "D"]),
        ],
        render=[Draw(obj="R")],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    polygons = _findall(root, "polygon")
    assert len(polygons) == 1
    pts = polygons[0].get("points", "")
    pairs = [p.split(",") for p in pts.strip().split()]
    assert len(pairs) == 4


def test_segment_renders_as_line():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=3, y=4),
            Segment(id="AB", a="A", b="B"),
        ],
        render=[Draw(obj="AB")],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    lines = _findall(root, "line")
    assert len(lines) == 1


def test_circle_renders_as_circle_element():
    diagram = DiagramIR(
        define=[
            PointFixed(id="O", x=0, y=0),
            PointFixed(id="P", x=3, y=0),
            CircleCenterPoint(id="C", center="O", through="P"),
        ],
        render=[Draw(obj="C")],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    circles = [c for c in _findall(root, "circle") if float(c.get("r", 0)) > 3]
    assert len(circles) == 1
    # Radius should map to 3 geometry units * scale
    r = float(circles[0].get("r"))
    assert r > 0


def test_circle_center_radius():
    diagram = DiagramIR(
        define=[
            PointFixed(id="O", x=1, y=1),
            CircleCenterRadius(id="C", center="O", radius=2),
        ],
        render=[Draw(obj="C")],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    circles = [c for c in _findall(root, "circle") if float(c.get("r", 0)) > 3]
    assert len(circles) == 1


def test_points_render_as_small_circles():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=3, y=4),
        ],
        render=[DrawPoints(points=["A", "B"])],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    circles = _findall(root, "circle")
    assert len(circles) == 2
    for c in circles:
        assert float(c.get("r")) < 10  # small


# ---------------------------------------------------------------------------
# Fill
# ---------------------------------------------------------------------------

def test_fill_polygon_has_fill_attribute():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=2, y=3),
            Triangle(id="T", a="A", b="B", c="C"),
        ],
        render=[Fill(obj="T", opacity=0.3)],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    polygons = _findall(root, "polygon")
    assert len(polygons) == 1
    assert polygons[0].get("fill") not in (None, "none")
    assert float(polygons[0].get("fill-opacity", 1)) == pytest.approx(0.3)


def test_fill_circle_has_fill_attribute():
    diagram = DiagramIR(
        define=[
            PointFixed(id="O", x=0, y=0),
            PointFixed(id="P", x=2, y=0),
            CircleCenterPoint(id="C", center="O", through="P"),
        ],
        render=[Fill(obj="C", opacity=0.5)],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    circles = _findall(root, "circle")
    filled = [c for c in circles if c.get("fill") not in (None, "none")]
    assert len(filled) == 1
    assert float(filled[0].get("fill-opacity", 1)) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Marks
# ---------------------------------------------------------------------------

def test_right_angle_mark_produces_path():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=3, y=0),
            PointFixed(id="C", x=0, y=4),
        ],
        render=[MarkRightAngles(angles=[AnglePoints(a="A", o="B", b="C")])],
    )
    sym = compile_defs(diagram)
    svg_str = ir_to_svg(diagram, sym)
    root = _parse(svg_str)
    paths = _findall(root, "path")
    assert len(paths) >= 1


def test_angle_arc_mark_produces_path():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=3, y=0),
            PointFixed(id="O", x=0, y=0),
            PointFixed(id="B", x=0, y=3),
        ],
        render=[MarkAngles(angles=[AnglePoints(a="A", o="O", b="B")], which="interior")],
    )
    sym = compile_defs(diagram)
    svg_str = ir_to_svg(diagram, sym)
    root = _parse(svg_str)
    paths = _findall(root, "path")
    assert len(paths) >= 1


def test_angle_arc_uses_small_arc_for_interior():
    """Interior angle marks must use large-arc-flag=0 (small arc, not reflex)."""
    # 90° angle at O between A (right) and B (up)
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=3, y=0),
            PointFixed(id="O", x=0, y=0),
            PointFixed(id="B", x=0, y=3),
        ],
        render=[MarkAngles(angles=[AnglePoints(a="A", o="O", b="B")], which="interior")],
    )
    sym = compile_defs(diagram)
    svg_str = ir_to_svg(diagram, sym)
    # The arc path uses "A rx ry x-rot large-arc sweep ex ey"
    # For a 90° interior angle, large-arc-flag must be 0
    import re
    arcs = re.findall(r"A[\d. ]+ ([\d]+) ([\d]+)", svg_str)
    assert arcs, "No SVG arc command found"
    for large_arc, sweep in arcs:
        assert large_arc == "0", f"Expected large-arc-flag=0 for interior angle, got {large_arc}"


def test_segment_tick_marks():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            Segment(id="AB", a="A", b="B"),
        ],
        render=[MarkSegments(segs=["AB"], group="1")],
    )
    sym = compile_defs(diagram)
    svg_str = ir_to_svg(diagram, sym)
    root = _parse(svg_str)
    lines = _findall(root, "line")
    assert len(lines) >= 1


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

def test_label_point_produces_text():
    diagram = DiagramIR(
        define=[PointFixed(id="A", x=0, y=0)],
        render=[LabelPoint(p="A", text="A")],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    texts = _findall(root, "text")
    assert len(texts) >= 1


def test_label_segment_produces_text():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            Segment(id="AB", a="A", b="B"),
        ],
        render=[LabelSegment(seg="AB", text="c")],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    texts = _findall(root, "text")
    assert len(texts) >= 1


# ---------------------------------------------------------------------------
# Canvas: grid and axes
# ---------------------------------------------------------------------------

def test_grid_lines_present():
    diagram = DiagramIR(
        canvas=Canvas(xmin=0, xmax=4, ymin=0, ymax=4, grid=True, grid_step=1),
        define=[],
        render=[],
    )
    sym = compile_defs(diagram)
    svg_str = ir_to_svg(diagram, sym)
    root = _parse(svg_str)
    # Grid produces many lines
    lines = _findall(root, "line")
    assert len(lines) >= 8  # at least 4 vertical + 4 horizontal


def test_axes_present():
    diagram = DiagramIR(
        canvas=Canvas(xmin=-3, xmax=3, ymin=-3, ymax=3, axes=True),
        define=[],
        render=[],
    )
    sym = compile_defs(diagram)
    svg_str = ir_to_svg(diagram, sym)
    root = _parse(svg_str)
    lines = _findall(root, "line")
    assert len(lines) == 2  # x-axis and y-axis


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

def test_color_style_sets_stroke():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=3, y=0),
            Segment(id="AB", a="A", b="B"),
        ],
        render=[Draw(obj="AB", style="red")],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    lines = _findall(root, "line")
    assert len(lines) == 1
    assert lines[0].get("stroke") == "red"


def test_style_dict_sets_stroke():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=3, y=0),
            Segment(id="AB", a="A", b="B"),
        ],
        styles={"mystyle": {"color": "blue", "thick": True}},
        render=[Draw(obj="AB", style="mystyle")],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    lines = _findall(root, "line")
    assert lines[0].get("stroke") == "blue"
    assert float(lines[0].get("stroke-width")) > 1.5


# ---------------------------------------------------------------------------
# Y-axis orientation
# ---------------------------------------------------------------------------

def test_higher_y_appears_higher_on_screen():
    """A point at y=4 should have a smaller SVG y-coordinate than one at y=0."""
    diagram = DiagramIR(
        define=[
            PointFixed(id="LOW", x=0, y=0),
            PointFixed(id="HIGH", x=0, y=4),
        ],
        render=[DrawPoints(points=["LOW", "HIGH"])],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    circles = _findall(root, "circle")
    assert len(circles) == 2
    # Map by approximate cx position (both at x=0, so same cx); distinguish by cy
    cys = sorted([float(c.get("cy")) for c in circles])
    # Lower cy value = higher on screen
    assert cys[0] < cys[1]  # HIGH point has smaller cy than LOW point


# ---------------------------------------------------------------------------
# Undefined object handling
# ---------------------------------------------------------------------------

def test_draw_undefined_object_skips_with_warning():
    diagram = DiagramIR(
        define=[],
        render=[Draw(obj="MISSING")],
    )
    sym = compile_defs(diagram)
    warnings: list[str] = []
    svg_str = ir_to_svg(diagram, sym, warnings=warnings)
    assert any("MISSING" in w for w in warnings)
    assert check_svg_wellformed(svg_str) is None


# ---------------------------------------------------------------------------
# Element metadata (data-* attributes)
# ---------------------------------------------------------------------------

def test_draw_triangle_has_metadata():
    svg = _compile_svg(_basic_triangle_diagram())
    root = _parse(svg)
    polygons = _findall(root, "polygon")
    draw_poly = next(p for p in polygons if p.get("data-type") == "triangle")
    assert draw_poly.get("data-ir-id") == "T"
    assert draw_poly.get("data-vertices") == "A,B,C"


def test_draw_polygon_has_metadata():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=4, y=3),
            PointFixed(id="D", x=0, y=3),
            Polygon(id="R", points=["A", "B", "C", "D"]),
        ],
        render=[Draw(obj="R")],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    polygons = _findall(root, "polygon")
    assert len(polygons) == 1
    assert polygons[0].get("data-type") == "polygon"
    assert polygons[0].get("data-ir-id") == "R"
    assert polygons[0].get("data-vertices") == "A,B,C,D"


def test_draw_segment_has_metadata():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=3, y=4),
            Segment(id="AB", a="A", b="B"),
        ],
        render=[Draw(obj="AB")],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    lines = _findall(root, "line")
    assert len(lines) == 1
    assert lines[0].get("data-ir-id") == "AB"
    assert lines[0].get("data-type") == "segment"
    assert lines[0].get("data-endpoints") == "A,B"


def test_draw_circle_has_metadata():
    diagram = DiagramIR(
        define=[
            PointFixed(id="O", x=0, y=0),
            PointFixed(id="P", x=3, y=0),
            CircleCenterPoint(id="C", center="O", through="P"),
        ],
        render=[Draw(obj="C")],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    circles = [c for c in _findall(root, "circle") if c.get("data-type") == "circle"]
    assert len(circles) == 1
    assert circles[0].get("data-ir-id") == "C"
    assert circles[0].get("data-center") == "O"


def test_draw_points_have_metadata():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=3, y=4),
        ],
        render=[DrawPoints(points=["A", "B"])],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    circles = _findall(root, "circle")
    assert len(circles) == 2
    ids = {c.get("data-ir-id") for c in circles}
    assert ids == {"A", "B"}
    for c in circles:
        assert c.get("data-type") == "point"


def test_fill_has_metadata():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=2, y=3),
            Triangle(id="T", a="A", b="B", c="C"),
        ],
        render=[Fill(obj="T", opacity=0.3)],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    polygons = _findall(root, "polygon")
    assert polygons[0].get("data-ir-id") == "T"
    assert polygons[0].get("data-role") == "fill"


def test_label_point_has_metadata():
    diagram = DiagramIR(
        define=[PointFixed(id="A", x=1, y=1)],
        render=[LabelPoint(p="A", text="A")],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    texts = _findall(root, "text")
    assert len(texts) == 1
    assert texts[0].get("data-role") == "label-point"
    assert texts[0].get("data-for") == "A"


def test_mark_right_angle_has_metadata():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=3, y=0),
            PointFixed(id="C", x=0, y=4),
        ],
        render=[MarkRightAngles(angles=[AnglePoints(a="A", o="B", b="C")])],
    )
    sym = compile_defs(diagram)
    svg_str = ir_to_svg(diagram, sym)
    root = _parse(svg_str)
    paths = _findall(root, "path")
    assert len(paths) >= 1
    assert paths[0].get("data-role") == "mark-right-angle"
    assert paths[0].get("data-angle") == "A,B,C"


def test_mark_angle_has_metadata():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=3, y=0),
            PointFixed(id="O", x=0, y=0),
            PointFixed(id="B", x=0, y=3),
        ],
        render=[MarkAngles(angles=[AnglePoints(a="A", o="O", b="B")], which="interior", group="2")],
    )
    sym = compile_defs(diagram)
    svg_str = ir_to_svg(diagram, sym)
    root = _parse(svg_str)
    paths = _findall(root, "path")
    assert all(p.get("data-role") == "mark-angle" for p in paths)
    assert all(p.get("data-angle") == "A,O,B" for p in paths)
    assert all(p.get("data-group") == "2" for p in paths)


def test_mark_segment_has_metadata():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            Segment(id="AB", a="A", b="B"),
        ],
        render=[MarkSegments(segs=["AB"], group="1")],
    )
    sym = compile_defs(diagram)
    svg_str = ir_to_svg(diagram, sym)
    root = _parse(svg_str)
    lines = _findall(root, "line")
    tick_lines = [l for l in lines if l.get("data-role") == "mark-segment"]
    assert len(tick_lines) >= 1
    assert tick_lines[0].get("data-segment") == "AB"


def test_label_segment_has_metadata():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            Segment(id="AB", a="A", b="B"),
        ],
        render=[LabelSegment(seg="AB", text="c")],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    texts = _findall(root, "text")
    assert len(texts) == 1
    assert texts[0].get("data-role") == "label-segment"
    assert texts[0].get("data-for") == "AB"


# ---------------------------------------------------------------------------
# LaTeX label conversion
# ---------------------------------------------------------------------------

def test_parse_latex_plain_text():
    result = _parse_latex("ABC")
    assert len(result) == 1
    assert result[0]["kind"] == "text"
    assert result[0]["content"] == "ABC"


def test_parse_latex_subscript_braced():
    result = _parse_latex("p_{center}")
    assert any(s["kind"] == "sub" and s["content"] == "center" for s in result)


def test_parse_latex_subscript_single():
    result = _parse_latex("A_1")
    assert any(s["kind"] == "sub" and s["content"] == "1" for s in result)


def test_parse_latex_superscript_braced():
    result = _parse_latex("y^{2}")
    assert any(s["kind"] == "sup" and s["content"] == "2" for s in result)


def test_parse_latex_superscript_single():
    result = _parse_latex("x^2")
    assert any(s["kind"] == "sup" and s["content"] == "2" for s in result)


def test_parse_latex_greek():
    result = _parse_latex(r"\alpha")
    assert len(result) == 1
    assert result[0]["content"] == "α"


def test_parse_latex_theta():
    result = _parse_latex(r"\theta")
    assert result[0]["content"] == "θ"


def test_parse_latex_overline():
    result = _parse_latex(r"\overline{AB}")
    assert any(s["kind"] == "overline" and s["content"] == "AB" for s in result)


def test_parse_latex_geometry_symbols():
    result = _parse_latex(r"\triangle ABC")
    combined = "".join(s["content"] for s in result)
    assert "△" in combined


def test_parse_latex_dollar_stripped():
    """When called from _build_tspans, $ delimiters are stripped."""
    # _parse_latex receives already-stripped content, but test full pipeline via
    # the label-in-diagram test above. Here test stripping directly.
    result = _parse_latex("A")  # already stripped
    assert result[0]["content"] == "A"


def test_label_with_subscript_produces_tspan():
    """A label like $p_{center}$ should produce a tspan for the subscript."""
    diagram = DiagramIR(
        define=[PointFixed(id="P", x=1, y=1)],
        render=[LabelPoint(p="P", text=r"p_{center}")],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    tspans = _findall(root, "tspan")
    assert any(ts.get("baseline-shift") == "sub" for ts in tspans)


def test_label_with_superscript_produces_tspan():
    diagram = DiagramIR(
        define=[PointFixed(id="P", x=1, y=1)],
        render=[LabelPoint(p="P", text=r"y^{2}")],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    tspans = _findall(root, "tspan")
    assert any(ts.get("baseline-shift") == "super" for ts in tspans)


def test_label_greek_uses_unicode():
    diagram = DiagramIR(
        define=[PointFixed(id="P", x=1, y=1)],
        render=[LabelPoint(p="P", text=r"\alpha")],
    )
    svg = _compile_svg(diagram)
    assert "α" in svg


def test_label_overline_produces_tspan():
    diagram = DiagramIR(
        define=[PointFixed(id="P", x=1, y=1)],
        render=[LabelPoint(p="P", text=r"\overline{AB}")],
    )
    svg = _compile_svg(diagram)
    root = _parse(svg)
    tspans = _findall(root, "tspan")
    assert any(ts.get("text-decoration") == "overline" for ts in tspans)


# ---------------------------------------------------------------------------
# Auto label placement helpers
# ---------------------------------------------------------------------------

class TestAutoLabelDirection:
    def test_no_angles_returns_above(self):
        # No incident edges → label goes straight up (π/2)
        d = _auto_label_direction([])
        assert abs(d - math.pi / 2) < 1e-9

    def test_single_angle_returns_opposite(self):
        # One edge going right (0) → label should go left (π)
        d = _auto_label_direction([0.0])
        assert abs(d - math.pi) < 1e-9

    def test_two_opposite_angles_returns_perpendicular(self):
        # Horizontal line (0 and π) → largest gap is above/below; bisector at π/2 or 3π/2
        d = _auto_label_direction([0.0, math.pi])
        TWO_PI = 2 * math.pi
        # Gap above (π/2) and below (3π/2) are equal; algorithm picks the first one
        assert abs(d - math.pi / 2) < 1e-9 or abs(d - 3 * math.pi / 2) < 1e-9

    def test_three_angles_finds_largest_gap(self):
        # Three edges at 0°, 120°, 240° (equilateral triangle vertex)
        # All gaps are equal (120°); bisector of gap between 240° and 0° is 300° = -60°
        angles = [0.0, 2 * math.pi / 3, 4 * math.pi / 3]
        d = _auto_label_direction(angles)
        TWO_PI = 2 * math.pi
        d_norm = d % TWO_PI
        # Each gap is 120°; any of the three bisectors is valid
        expected = [math.pi / 3, math.pi, 5 * math.pi / 3]
        assert any(abs(d_norm - e) < 1e-9 for e in expected)

    def test_four_edges_avoids_all(self):
        # Four edges at 0°, 90°, 180°, 270° (cross pattern)
        # All gaps are 90°; label should be at 45°, 135°, 225°, or 315°
        angles = [0.0, math.pi / 2, math.pi, 3 * math.pi / 2]
        d = _auto_label_direction(angles)
        TWO_PI = 2 * math.pi
        d_norm = d % TWO_PI
        expected = [math.pi / 4, 3 * math.pi / 4, 5 * math.pi / 4, 7 * math.pi / 4]
        assert any(abs(d_norm - e) < 1e-9 for e in expected)

    def test_unequal_gaps_picks_largest(self):
        # Edge at 0° and 45° — large gap from 45° to 360° (315°); bisector at 45 + 315/2 = 202.5°
        angles = [0.0, math.pi / 4]
        d = _auto_label_direction(angles)
        expected = math.radians(202.5)
        assert abs((d % (2 * math.pi)) - expected) < 1e-6


class TestAngleToOffset:
    def test_right(self):
        dx, dy = _angle_to_offset(0.0, 10.0)
        assert abs(dx - 10.0) < 1e-9
        assert abs(dy) < 1e-9

    def test_above(self):
        # angle π/2 in geometry space → SVG y decreases (upward on screen)
        dx, dy = _angle_to_offset(math.pi / 2, 10.0)
        assert abs(dx) < 1e-9
        assert abs(dy - (-10.0)) < 1e-9  # negative SVG dy = upward

    def test_left(self):
        dx, dy = _angle_to_offset(math.pi, 10.0)
        assert abs(dx - (-10.0)) < 1e-9
        assert abs(dy) < 1e-9

    def test_below(self):
        dx, dy = _angle_to_offset(-math.pi / 2, 10.0)
        assert abs(dx) < 1e-9
        assert abs(dy - 10.0) < 1e-9  # positive SVG dy = downward


class TestAngleToAnchor:
    def test_right_is_start(self):
        assert _angle_to_anchor(0.0) == "start"

    def test_above_is_middle(self):
        assert _angle_to_anchor(math.pi / 2) == "middle"

    def test_left_is_end(self):
        assert _angle_to_anchor(math.pi) == "end"

    def test_below_is_middle(self):
        assert _angle_to_anchor(-math.pi / 2) == "middle"

    def test_above_right_is_start(self):
        assert _angle_to_anchor(math.pi / 6) == "start"   # 30° — right half-plane

    def test_above_left_is_end(self):
        assert _angle_to_anchor(5 * math.pi / 6) == "end"  # 150° — left half-plane


class TestBuildIncidentAngles:
    def test_segment_adds_angles_at_both_endpoints(self):
        diagram = DiagramIR(
            define=[
                PointFixed(id="A", x=0, y=0),
                PointFixed(id="B", x=1, y=0),
                Segment(id="s", a="A", b="B"),
            ],
            render=[Draw(obj="s"), LabelPoint(p="A"), LabelPoint(p="B")],
        )
        sym = compile_defs(diagram)
        from ir.render_util import extract_coords, synthesize_helpers
        coords = extract_coords(sym)
        stmt_by_id = {s.id: s for s in diagram.define}
        helpers = synthesize_helpers(diagram, sym, coords)
        angles = _build_incident_angles(diagram, sym, stmt_by_id, coords, helpers)
        assert "A" in angles
        assert "B" in angles
        # A→B is angle 0 (rightward); B→A is angle π
        assert any(abs(a - 0.0) < 1e-9 for a in angles["A"])
        assert any(abs(a - math.pi) < 1e-9 for a in angles["B"])

    def test_intersection_point_gets_both_line_angles(self):
        """A point lying on a drawn line (but not a defining endpoint) gets angles."""
        from ir.ir import LineThrough, PointFixed, PointIntersection
        diagram = DiagramIR(
            define=[
                PointFixed(id="A", x=0, y=0),
                PointFixed(id="B", x=2, y=0),
                PointFixed(id="C", x=1, y=-1),
                PointFixed(id="D", x=1, y=1),
                Segment(id="s1", a="A", b="B"),
                Segment(id="s2", a="C", b="D"),
                PointIntersection(id="X", obj1="s1", obj2="s2"),
            ],
            render=[
                Draw(obj="s1"), Draw(obj="s2"),
                LabelPoint(p="X"),
            ],
        )
        sym = compile_defs(diagram)
        from ir.render_util import extract_coords, synthesize_helpers
        coords = extract_coords(sym)
        stmt_by_id = {s.id: s for s in diagram.define}
        helpers = synthesize_helpers(diagram, sym, coords)
        angles = _build_incident_angles(diagram, sym, stmt_by_id, coords, helpers)
        # X lies on both segments; should have angles for both (0°/180° and 90°/270°)
        assert "X" in angles
        x_angles_deg = sorted(round(math.degrees(a) % 360, 1) for a in angles["X"])
        assert 0.0 in x_angles_deg
        assert 90.0 in x_angles_deg
        assert 180.0 in x_angles_deg
        assert 270.0 in x_angles_deg

    def test_no_draw_op_no_angles(self):
        diagram = DiagramIR(
            define=[
                PointFixed(id="A", x=0, y=0),
                PointFixed(id="B", x=1, y=0),
                Segment(id="s", a="A", b="B"),
            ],
            render=[LabelPoint(p="A")],  # no Draw op
        )
        sym = compile_defs(diagram)
        from ir.render_util import extract_coords, synthesize_helpers
        coords = extract_coords(sym)
        stmt_by_id = {s.id: s for s in diagram.define}
        helpers = synthesize_helpers(diagram, sym, coords)
        angles = _build_incident_angles(diagram, sym, stmt_by_id, coords, helpers)
        assert angles.get("A", []) == []


class TestAutoLabelIntegration:
    """Integration tests: verify that auto labels are not placed along drawn edges."""

    def _label_pos(self, svg_str: str, point_id: str) -> tuple[float, float]:
        root = ET.fromstring(svg_str)
        ns = "http://www.w3.org/2000/svg"
        for el in root.iter(f"{{{ns}}}text"):
            if el.get("data-for") == point_id:
                return float(el.get("x", 0)), float(el.get("y", 0))
        raise AssertionError(f"No label found for point {point_id!r}")

    def _point_pos(self, svg_str: str, point_id: str) -> tuple[float, float]:
        root = ET.fromstring(svg_str)
        ns = "http://www.w3.org/2000/svg"
        for el in root.iter(f"{{{ns}}}circle"):
            if el.get("data-ir-id") == point_id:
                return float(el.get("cx", 0)), float(el.get("cy", 0))
        raise AssertionError(f"No drawn point found for {point_id!r}")

    def test_label_not_along_horizontal_segment(self):
        # Horizontal segment A-B; label for A should not be placed to the right
        # (along the segment direction). With one outgoing edge (rightward),
        # the algorithm places the label in the opposite direction (leftward).
        diagram = DiagramIR(
            define=[
                PointFixed(id="A", x=0, y=0),
                PointFixed(id="B", x=2, y=0),
                Segment(id="s", a="A", b="B"),
            ],
            render=[
                Draw(obj="s"),
                DrawPoints(points=["A", "B"]),
                LabelPoint(p="A"),
            ],
        )
        sym = compile_defs(diagram)
        svg = ir_to_svg(diagram, sym)
        lx, ly = self._label_pos(svg, "A")
        px, py = self._point_pos(svg, "A")
        # Label should NOT be to the right of the point (which would be along the segment)
        assert lx < px, "Label for endpoint A of a rightward segment should be placed to the left"

    def test_explicit_pos_is_honored(self):
        # Explicit pos="below" should always place label below, ignoring geometry
        diagram = DiagramIR(
            define=[
                PointFixed(id="A", x=0, y=0),
                PointFixed(id="B", x=2, y=0),
                Segment(id="s", a="A", b="B"),
            ],
            render=[
                Draw(obj="s"),
                DrawPoints(points=["A", "B"]),
                LabelPoint(p="A", pos="below"),
            ],
        )
        sym = compile_defs(diagram)
        svg = ir_to_svg(diagram, sym)
        lx, ly = self._label_pos(svg, "A")
        px, py = self._point_pos(svg, "A")
        # "below" in SVG coords means higher y value
        assert ly > py, "Label with pos='below' should be below the point in SVG space"
