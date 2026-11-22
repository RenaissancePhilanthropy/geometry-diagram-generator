"""The SVG data-* contract (docs/geometry-dsl-spec.md, "SVG data attributes"): the roles,
types and attributes tools read from rendered SVG. Bump SVG_DATA_CONTRACT_VERSION when
one of these changes meaning."""
from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET

import pytest

from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_svg import SVG_DATA_CONTRACT_VERSION
from geometry_diagrams.pydsl.sandbox import run_script
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline

SCRIPT = """
canvas((-8, 8), (-8, 8))
a = point(-4, -2); b = point(3, -2); c = point(-4, 3)
t = triangle(a, b, c); draw(t); fill(t, color="#e6eefa")
a.label("A"); b.label("B"); c.label("C")
mark_right_angle(t.angle_at(a))
mark_angle(t.angle_at(b), group=1); t.angle_at(b).label("35°")
ab = segment(a, b)
mark_equal(segment(a, c), segment(b, c))
o = point(0, 4); circ = circle(o, 1.5); draw(circ)
d = segment(point(-1.5, 4), point(1.5, 4)); draw(d); d.label("3 ft")
p = point(5, 5); q = point(6, 5); draw(ray(p, q)); draw(line_through(point(5, 0), point(6, 1)))
draw_points(p)
label_text("note", at=(2, 6))
"""


@pytest.fixture(scope="module")
def root() -> ET.Element:
    result = run_script(SCRIPT, timeout_seconds=60)
    assert result.error is None, result.error
    svg = asyncio.run(run_ir_pipeline(result.diagram_ir, SVGRenderer())).svg
    return ET.fromstring(svg)


def _find(root, **attrs):
    return [el for el in root.iter() if all(el.get(k) == v for k, v in attrs.items())]


def _tag(el) -> str:
    return el.tag.split("}")[-1]


def test_root_carries_the_contract_version(root):
    assert root.get("data-contract") == str(SVG_DATA_CONTRACT_VERSION) == "1"


def test_triangle_lists_its_vertices_in_order(root):
    (tri,) = _find(root, **{"data-type": "triangle"})
    assert _tag(tri) == "polygon"
    assert len(tri.get("data-vertices").split(",")) == 3 and tri.get("data-ir-id")


@pytest.mark.parametrize("kind", ["segment", "ray", "line"])
def test_linear_objects_carry_endpoints(root, kind):
    (el,) = _find(root, **{"data-type": kind})
    assert el.get("data-ir-id") and len(el.get("data-endpoints").split(",")) == 2


def test_circle_names_its_center_and_a_point_is_a_circle_typed_point(root):
    (circ,) = [e for e in _find(root, **{"data-type": "circle"})]
    assert circ.get("data-center")
    (pt,) = _find(root, **{"data-type": "point"})
    assert _tag(pt) == "circle" and pt.get("data-ir-id")


def test_marks_name_their_angle_or_segment(root):
    (ra,) = _find(root, **{"data-role": "mark-right-angle"})
    assert len(ra.get("data-angle").split(",")) == 3
    (ma,) = _find(root, **{"data-role": "mark-angle"})
    assert len(ma.get("data-angle").split(",")) == 3 and ma.get("data-group") == "1"
    segs = _find(root, **{"data-role": "mark-segment"})
    assert segs and all(s.get("data-segment") for s in segs)


def test_fill_names_its_object(root):
    (fill,) = _find(root, **{"data-role": "fill"})
    assert fill.get("data-ir-id")


@pytest.mark.parametrize("role,for_", [
    ("label-point", True), ("label-angle", True), ("label-segment", True), ("label-free-text", False),
])
def test_labels_carry_text_and_box(root, role, for_):
    labels = _find(root, **{"data-role": role})
    assert labels
    for el in labels:
        assert el.get("data-label-text")
        x0, y0, x1, y1 = (float(v) for v in el.get("data-bbox").split(","))
        assert x0 < x1 and y0 < y1
        assert (el.get("data-for") is not None) == for_


def test_label_text_is_the_authored_text(root):
    texts = {el.get("data-label-text") for el in root.iter() if el.get("data-label-text")}
    assert {"A", "B", "C", "35°", "3 ft", "note"} <= texts


CURVES = """
canvas((-8, 8), (-8, 8))
o = point(0, 0); circ = circle(o, 3); draw(circ)
p1 = point_on(circ, 0); p2 = point_on(circ, 90); p3 = point_on(circ, 200)
ar = arc(circ, p1, p2); draw(ar)
mark_equal(ar, arc(circ, p2, point_on(circ, 180)))
sc = sector(circ, p2, p3); draw(sc)
draw(ellipse(center=point(5, 5), hradius=2, vradius=1))
draw_brace((0, -4), (4, -4), direction="down", label="4")
"""


@pytest.fixture(scope="module")
def curve_root() -> ET.Element:
    result = run_script(CURVES, timeout_seconds=60)
    assert result.error is None, result.error
    return ET.fromstring(asyncio.run(run_ir_pipeline(result.diagram_ir, SVGRenderer())).svg)


@pytest.mark.parametrize("kind,tag", [("arc", "path"), ("sector", "path"), ("ellipse", "ellipse")])
def test_curves_carry_their_type(curve_root, kind, tag):
    (el,) = _find(curve_root, **{"data-type": kind})
    assert _tag(el) == tag and el.get("data-ir-id")


def test_arc_ticks_and_brace(curve_root):
    marks = _find(curve_root, **{"data-role": "mark-arc"})
    assert marks and all(m.get("data-arc") for m in marks)
    assert _find(curve_root, **{"data-role": "brace"})
    (lab,) = _find(curve_root, **{"data-role": "label-brace"})
    assert lab.get("data-label-text") == "4" and lab.get("data-for") is None
