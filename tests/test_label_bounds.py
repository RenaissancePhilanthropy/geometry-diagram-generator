# tests/test_label_bounds.py
"""Tests for geometry_diagrams/ir/label_bounds.py's find_out_of_bounds_labels().

Two label kinds matter equally here: plain-text labels (rendered by
to_svg.py as <text> elements) and math/LaTeX labels (rendered as <g>-wrapped
MathGlyph path groups, no <text> element at all) -- see to_svg.py's
label_needs_mathtext()/MathGlyph. A checker that only looked at <text>
elements would silently miss every math label, which is exactly the
correctness bug this ticket exists to avoid, so every case below is tested
for both kinds.
"""
from __future__ import annotations

from geometry_diagrams.ir.label_bounds import find_out_of_bounds_labels
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.pydsl.api import canvas, label_text, point
from geometry_diagrams.pydsl.builder import new_builder_context


def _render(build_fn) -> str:
    with new_builder_context() as builder:
        build_fn()
        ir = builder.build()
    sym = compile_defs(ir)
    return SVGRenderer().render(ir, sym).output


def test_clean_plain_text_label_is_not_flagged():
    def build():
        canvas(x_range=(-5, 5), y_range=(-5, 5))
        point(0, 0)
        label_text("hello", at=(0, 0))

    svg = _render(build)
    assert "<text" in svg
    assert find_out_of_bounds_labels(svg) == []


def test_out_of_bounds_plain_text_label_is_flagged():
    def build():
        canvas(x_range=(-5, 5), y_range=(-5, 5))
        point(0, 0)
        # Far outside the declared canvas range -> maps well outside the
        # rendered viewBox in pixel space.
        label_text("way off canvas", at=(500, 0))

    svg = _render(build)
    assert "<text" in svg
    violations = find_out_of_bounds_labels(svg)
    assert len(violations) == 1
    v = violations[0]
    assert v.text == "way off canvas"
    assert v.overflow > 0


def test_clean_math_label_is_not_flagged():
    def build():
        canvas(x_range=(-5, 5), y_range=(-5, 5))
        point(0, 0)
        label_text(r"\frac{1}{2}", at=(0, 0))

    svg = _render(build)
    assert "<text" not in svg  # math label -> <g>-wrapped MathGlyph, not <text>
    assert find_out_of_bounds_labels(svg) == []


def test_out_of_bounds_math_label_is_flagged():
    def build():
        canvas(x_range=(-5, 5), y_range=(-5, 5))
        point(0, 0)
        label_text(r"\frac{1}{2}", at=(500, 0))

    svg = _render(build)
    assert "<text" not in svg  # confirms this exercises the MathGlyph <g> path
    violations = find_out_of_bounds_labels(svg)
    assert len(violations) == 1
    v = violations[0]
    assert r"\frac{1}{2}" in v.text
    assert v.overflow > 0


def test_svg_with_no_viewbox_returns_no_violations():
    assert find_out_of_bounds_labels("<svg></svg>") == []


def test_svg_with_no_labels_returns_no_violations():
    svg = '<svg viewBox="0 0 100 100"></svg>'
    assert find_out_of_bounds_labels(svg) == []


def test_rotated_arc_text_wrapper_bbox_is_reported():
    """LabelAlongArc's per-glyph <g> wrapper stamps one data-bbox for the
    whole run (the union of every rotated glyph's own AABB), not per glyph
    -- this is a direct regression test on that contract, independent of
    to_svg.py's own layout math: a hand-built wrapper whose stamped bbox
    sits outside the viewBox must be reported exactly once."""
    svg = (
        '<svg viewBox="0 0 100 100">'
        '<g data-role="label-along-arc" data-bbox="150,150,180,180" '
        'data-label-text="off canvas">'
        '<text x="160" y="165">o</text>'
        "</g>"
        "</svg>"
    )
    violations = find_out_of_bounds_labels(svg)
    assert len(violations) == 1
    assert violations[0].text == "off canvas"
    assert violations[0].overflow > 0


# ---------------------------------------------------------------------------
# Grow-to-fit: the renderer extends viewBox/size to contain overflowing labels
# ---------------------------------------------------------------------------

import xml.etree.ElementTree as ET


def _root_geometry(svg: str):
    root = ET.fromstring(svg)
    vx, vy, vw, vh = (float(v) for v in root.get("viewBox").split())
    return root, (vx, vy, vw, vh), float(root.get("width")), float(root.get("height"))


def _overflowing(at):
    def build():
        canvas(x_range=(-5, 5), y_range=(-5, 5))
        point(0, 0)
        label_text("5 units wide", at=at)

    return build


def test_clean_diagram_keeps_exact_viewbox_and_size():
    svg = _render(_overflowing((0, 0)))
    root, vb, w, h = _root_geometry(svg)
    assert vb == (0.0, 0.0, 500.0, 500.0)
    assert (w, h) == (500.0, 500.0)
    assert root.get("viewBox") == "0 0 500 500"
    bg = root.find("{http://www.w3.org/2000/svg}rect")
    assert (bg.get("x"), bg.get("y"), bg.get("width"), bg.get("height")) == ("0", "0", "500", "500")


def test_right_overflowing_label_grows_viewbox_to_contain_it():
    svg = _render(_overflowing((4.9, 0)))
    assert find_out_of_bounds_labels(svg) == []
    _, vb, w, h = _root_geometry(svg)
    assert vb[0] == 0.0 and vb[2] > 500.0
    assert (w, h) == (vb[2], vb[3])


def test_left_overflowing_label_grows_viewbox_to_contain_it():
    svg = _render(_overflowing((-4.9, 0)))
    assert find_out_of_bounds_labels(svg) == []
    _, vb, w, h = _root_geometry(svg)
    assert vb[0] < 0.0
    assert (w, h) == (vb[2], vb[3])


def test_top_overflowing_label_grows_viewbox_to_contain_it():
    svg = _render(_overflowing((0, 5.5)))
    assert find_out_of_bounds_labels(svg) == []
    _, vb, w, h = _root_geometry(svg)
    assert vb[1] < 0.0 and (w, h) == (vb[2], vb[3])


def test_bottom_overflowing_label_grows_viewbox_to_contain_it():
    svg = _render(_overflowing((0, -5.5)))
    assert find_out_of_bounds_labels(svg) == []
    _, vb, w, h = _root_geometry(svg)
    assert vb[3] > 500.0 and (w, h) == (vb[2], vb[3])


def test_growth_preserves_scale_and_content_coordinates():
    clean = ET.fromstring(_render(_overflowing((0, 0))))
    grown_svg = _render(_overflowing((-4.9, 5.5)))
    grown_root, vb, w, h = _root_geometry(grown_svg)
    # user units per pixel unchanged
    assert (vb[2] / w, vb[3] / h) == (1.0, 1.0)
    # the figure's own point is drawn at identical user coordinates
    def origin_point(root):
        for c in root.iter("{http://www.w3.org/2000/svg}circle"):
            if c.get("data-type") == "point":
                return c.get("cx"), c.get("cy")
    assert origin_point(grown_root) == origin_point(clean)
    # background still covers the whole grown viewBox
    bg = grown_root.find("{http://www.w3.org/2000/svg}rect")
    assert (float(bg.get("x")), float(bg.get("y"))) == (vb[0], vb[1])
    assert (float(bg.get("width")), float(bg.get("height"))) == (vb[2], vb[3])


def test_hopeless_overflow_is_not_fixed_and_still_flagged():
    """A label placed absurdly far off canvas is a mistake, not an outer-edge
    label: growth is capped, so the retry-path check still sees it."""
    svg = _render(_overflowing((500, 0)))
    assert len(find_out_of_bounds_labels(svg)) == 1
    _, vb, _, _ = _root_geometry(svg)
    assert vb[2] < 2000


def _arc_text_diagram(canvas_kwargs=None):
    from geometry_diagrams.ir.ir import (
        ArcCenterStartEnd, Canvas, DiagramIR, LabelAlongArc, PointFixed,
    )

    return DiagramIR(
        canvas=Canvas(xmin=-3, xmax=3, ymin=-3, ymax=3),
        define=[
            PointFixed(id="O", x=0, y=0),
            PointFixed(id="S", x=3, y=0),
            PointFixed(id="E", x=0, y=3),
            ArcCenterStartEnd(id="a", center="O", start="S", end="E"),
        ],
        render=[LabelAlongArc(arc="a", text="arc text", pos=0.5)],
    )


def _render_ir(diagram) -> str:
    from geometry_diagrams.ir.to_svg import ir_to_svg

    return ir_to_svg(diagram, compile_defs(diagram))


def test_clean_arc_text_diagram_keeps_exact_viewbox():
    svg = _render_ir(_arc_text_diagram())
    assert 'data-role="label-along-arc"' in svg
    assert ET.fromstring(svg).get("viewBox") == "0 0 500 500"
    assert find_out_of_bounds_labels(svg) == []


def test_overflowing_arc_text_is_contained_after_growth(monkeypatch):
    # Normal arc text sits well inside the canvas margin; push the glyph run
    # radially outward so its stamped bbox leaves the viewBox.
    monkeypatch.setattr("geometry_diagrams.ir.to_svg._ARC_TEXT_OFFSET", 150)
    svg = _render_ir(_arc_text_diagram())
    assert 'data-role="label-along-arc"' in svg
    assert find_out_of_bounds_labels(svg) == []
    _, vb, w, h = _root_geometry(svg)
    assert (vb[2], vb[3]) == (w, h) and (vb[2] > 500 or vb[3] > 500 or vb[0] < 0 or vb[1] < 0)


# --- growth cap boundary (_MAX_LABEL_GROWTH_PX = 200 per side) --------------
# A free-text label centred at x = 5 + k units sits k*~45 px past the right
# edge; its bbox right edge overflows by about that plus half its width.

def _right_overflow(svg: str) -> float:
    root = ET.fromstring(svg)
    vb = [float(v) for v in root.get("viewBox").split()]
    right = vb[0] + vb[2]
    return max(
        float(el.get("data-bbox").split(",")[2]) - right
        for el in root.iter() if el.get("data-bbox")
    )


def _label_right_edge_at_overflow(target: float) -> float:
    """x (user units) at which the label's right edge overflows the clean
    500px viewBox by exactly ``target`` px, found from the clean render."""
    clean = _render(_overflowing((0, 0)))
    # bbox width of the label, and px per user unit (500px / (10 units + margins)).
    bbox = next(
        [float(v) for v in el.get("data-bbox").split(",")]
        for el in ET.fromstring(clean).iter() if el.get("data-bbox")
    )
    half_w = (bbox[2] - bbox[0]) / 2
    at0 = _render(_overflowing((4.9, 0)))
    # label x-centre in px at x=4.9 vs 0 gives the px-per-unit scale
    c0 = (bbox[0] + bbox[2]) / 2
    b1 = next(
        [float(v) for v in el.get("data-bbox").split(",")]
        for el in ET.fromstring(at0).iter() if el.get("data-bbox")
    )
    c1 = (b1[0] + b1[2]) / 2
    px_per_unit = (c1 - c0) / 4.9
    return (500 + target - half_w - c0) / px_per_unit


def test_overflow_just_under_cap_grows_and_is_contained():
    x = _label_right_edge_at_overflow(190.0)
    svg = _render(_overflowing((x, 0)))
    assert find_out_of_bounds_labels(svg) == []
    _, vb, w, _ = _root_geometry(svg)
    assert 500 + 189 < w <= 500 + 200


def test_overflow_just_over_cap_is_not_grown_and_still_flagged():
    x = _label_right_edge_at_overflow(210.0)
    svg = _render(_overflowing((x, 0)))
    violations = find_out_of_bounds_labels(svg)
    assert len(violations) == 1
    # Growth stops at the cap: the viewBox did not follow the label out.
    _, vb, _, _ = _root_geometry(svg)
    assert vb[2] <= 500 + 200


def test_one_side_capped_while_another_side_grows():
    """Each side is capped independently: a hopeless right overflow does not
    stop an in-range left overflow from being fixed (the hopeless label stays
    flagged, the left one is contained)."""
    def build():
        canvas(x_range=(-5, 5), y_range=(-5, 5))
        point(0, 0)
        label_text("5 units wide", at=(-4.9, 0))
        label_text("way off canvas", at=(500, 0))

    svg = _render(build)
    _, vb, _, _ = _root_geometry(svg)
    assert vb[0] < 0 and vb[2] <= 500 + 30.01 + 200
    flagged = [v.text for v in find_out_of_bounds_labels(svg)]
    assert flagged == ["way off canvas"]
