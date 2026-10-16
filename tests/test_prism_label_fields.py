"""Prism dimension and base-area label fields (solid-labels ticket 02).

``rectangular_prism`` carries optional ``length_label``, ``width_label``,
``height_label`` and ``base_area_label``. When the prism is DRAWN (a draw or
fill names its id or one of its faces/edges), the registry's ``lower_labels``
hook lowers them, once, to ordinary label operations: a ``label_segment`` on a
SILHOUETTE edge per dimension (chosen from the projection's hidden corner, not
a per-view table) and a ``label_free_text`` at the bottom face's centroid.
The existing ``label_away_from`` hook places the edge labels outside the
silhouette in both renderers. Asserted from the lowered operations and the
parsed SVG (label ``data-bbox`` against the corners read back from the
stroked face polygons), never from pixels.
"""
from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET

import pydantic
import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.derived import RenderTimeDiagram, effective_diagram, lower_render
from geometry_diagrams.ir.label_bounds import find_out_of_bounds_labels
from geometry_diagrams.ir.prism import projection_for
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_svg import ir_to_svg
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline
from tests.test_prism_shading_labels import (
    _bbox,
    _box_corners,
    _corners_px,
    _side,
    _silhouette_edges,
)

FIELDS = {
    "length_label": "L text",
    "width_label": "W text",
    "height_label": "H text",
    "base_area_label": "B text",
}
VIEWS = [("oblique", "right"), ("oblique", "left"), ("isometric", "right"), ("isometric", "left")]
DIMS = {
    "box_a": dict(length=3, width=11, height=6),
    "tall": dict(length=2, width=2, height=8),
}
# The documented edge per dimension and side (bits: length, height, width).
EXPECTED_EDGE = {
    "right": {"length_label": ("000", "100"), "height_label": ("000", "010"), "width_label": ("100", "101")},
    "left": {"length_label": ("000", "100"), "height_label": ("100", "110"), "width_label": ("000", "001")},
}
DIMENSION_FIELDS = ("length_label", "width_label", "height_label")


def _prism(**overrides) -> ir.RectangularPrism:
    fields = dict(id="P", origin="O", length=3, width=11, height=6)
    fields.update(overrides)
    return ir.RectangularPrism(**fields)


def _diagram(prism=None, render=None, **kw) -> ir.DiagramIR:
    return ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=0, y=0), prism or _prism(**FIELDS)],
        render=[ir.Draw(obj="P")] if render is None else list(render),
        **kw,
    )


def _lowered(d: ir.DiagramIR):
    return lower_render(effective_diagram(d), compile_defs(d))


def _label_ops(d: ir.DiagramIR) -> list:
    return [op for op in _lowered(d).render if op.kind in ("label_segment", "label_free_text")]


def _svg_label(root: ET.Element, text: str) -> ET.Element:
    (el,) = [e for e in root.iter() if e.get("data-label-text") == text and e.get("data-bbox")]
    return el


# --- the IR fields -------------------------------------------------------------------

def test_fields_default_to_none():
    p = _prism()
    assert (p.length_label, p.width_label, p.height_label, p.base_area_label) == (None,) * 4


@pytest.mark.parametrize("field", list(FIELDS))
@pytest.mark.parametrize("bad", ["", 5, 5.0, ["a"], {"a": 1}, True])
def test_empty_and_wrong_type_values_are_rejected(field, bad):
    with pytest.raises(pydantic.ValidationError):
        _prism(**{field: bad})
    # ... also through the DiagramIR document a model would emit.
    doc = {
        "define": [{"kind": "point_fixed", "id": "O", "x": 0, "y": 0},
                   {"kind": "rectangular_prism", "id": "P", "origin": "O",
                    "length": 3, "width": 2, "height": 1, field: bad}],
        "render": [],
    }
    with pytest.raises(pydantic.ValidationError):
        ir.DiagramIR.model_validate(doc)


def test_text_is_verbatim_through_a_json_round_trip():
    d = _diagram(_prism(length_label="6 feet", base_area_label="A = 33 ft^2"))
    again = ir.DiagramIR.model_validate_json(d.model_dump_json())
    assert again.define[1].length_label == "6 feet"
    texts = {op.text for op in _label_ops(again)}
    assert texts == {"6 feet", "A = 33 ft^2"}


# --- which edge, and where the label lands --------------------------------------------

@pytest.mark.parametrize("view,side", VIEWS)
@pytest.mark.parametrize("dims", list(DIMS))
def test_each_field_labels_its_silhouette_edge_outside_the_silhouette(view, side, dims):
    extra = DIMS[dims]
    d = _diagram(_prism(view=view, side=side, **extra, **FIELDS))
    ops = {op.text: op for op in _label_ops(d)}
    hidden = "".join(map(str, projection_for(view, side).hidden_corner))
    svg = ir_to_svg(d, compile_defs(d), warnings=[])
    root = ET.fromstring(svg)
    corners = _corners_px(root, side)
    silhouette = set(_silhouette_edges(corners))
    for field in DIMENSION_FIELDS:
        op = ops[FIELDS[field]]
        p, q = EXPECTED_EDGE[side][field]
        assert isinstance(op, ir.LabelSegment)
        assert op.seg == f"P_e_{p}_{q}", (field, op.seg)
        assert hidden not in (p, q), f"{field} edge {p}-{q} touches the hidden corner"
        assert (p, q) in silhouette, f"{field} edge {p}-{q} is not on the silhouette"
        a, b = corners[p], corners[q]
        inside = next(
            _side(corners[r], a, b) for r in corners
            if r not in (p, q) and abs(_side(corners[r], a, b)) > 1e-6
        )
        for c in _box_corners(_bbox(_svg_label(root, FIELDS[field]))):
            assert _side(c, a, b) * inside < 0, f"{field} label corner {c} is not outside edge {p}-{q}"
    assert find_out_of_bounds_labels(svg) == []


@pytest.mark.parametrize("view,side", VIEWS)
def test_base_area_label_sits_inside_the_base_of_a_wireframe_prism(view, side):
    d = _diagram(_prism(view=view, side=side, length=6, width=5, height=3, **FIELDS))
    (op,) = [o for o in _label_ops(d) if o.kind == "label_free_text"]
    assert (op.centroid_of, op.text) == ("P_bottom", "B text")
    root = ET.fromstring(ir_to_svg(d, compile_defs(d), warnings=[]))
    corners = _corners_px(root, side)
    # The bottom face is a parallelogram; three of its corners are visible.
    o, l = corners["000"], corners["100"]
    w = corners["101"] if side == "right" else corners["001"]
    if side == "right":
        quad = [o, l, w, (o[0] + w[0] - l[0], o[1] + w[1] - l[1])]
    else:
        quad = [o, l, (l[0] + w[0] - o[0], l[1] + w[1] - o[1]), w]
    x0, y0, x1, y1 = _bbox(_svg_label(root, "B text"))
    center = ((x0 + x1) / 2, (y0 + y1) / 2)
    signs = {_side(center, quad[i], quad[(i + 1) % 4]) > 0 for i in range(4)}
    assert len(signs) == 1, f"base label center {center} is outside the base {quad}"


def test_tikz_places_the_field_labels():
    d = _diagram(_prism(length_label="3", width_label="11", height_label="6", base_area_label="33"))
    tikz = ir_to_tikz(d, compile_defs(d), warnings=[])
    assert "(P_v000,P_v100){$3$}" in tikz
    assert "(P_v100,P_v101){$11$}" in tikz
    assert "(P_v000,P_v010){$6$}" in tikz
    assert "{33};" in tikz


# --- when labels are emitted ------------------------------------------------------------

FACES = ("front", "right", "top")
DRAWS = {
    "own_id": [ir.Draw(obj="P")],
    "faces_only": [*(ir.Fill(obj=f"P_{f}", style="lightgray") for f in FACES),
                   *(ir.Draw(obj=f"P_{f}") for f in FACES)],
    "both": [ir.Fill(obj="P_front", style="lightgray"), ir.Draw(obj="P")],
    "twice": [ir.Draw(obj="P"), ir.Draw(obj="P")],
    "one_edge": [ir.Draw(obj="P_e_000_100")],
}


@pytest.mark.parametrize("how", list(DRAWS))
def test_labels_are_emitted_once_whenever_the_prism_is_drawn(how):
    d = _diagram(render=DRAWS[how])
    texts = sorted(op.text for op in _label_ops(d))
    assert texts == sorted(FIELDS.values())
    svg = ir_to_svg(d, compile_defs(d), warnings=[])
    for text in FIELDS.values():
        assert svg.count(f'data-label-text="{text}"') == 1, (how, text)


@pytest.mark.parametrize("render", [
    [],
    [ir.LabelFreeText(text="V", centroid_of="P")],
    [ir.LabelSegment(seg="P_e_000_100", text="x"), ir.DrawPoints(points=["P_v000"])],
])
def test_no_field_labels_when_the_prism_is_not_drawn(render):
    d = _diagram(render=render)
    assert not {op.text for op in _label_ops(d)} & set(FIELDS.values())


def test_a_prism_without_fields_lowers_exactly_as_before():
    d = _diagram(_prism())
    assert _label_ops(d) == []


def test_labels_only_lowering_is_still_a_render_time_view():
    d = _diagram(render=[ir.Draw(obj="P_front")])
    lowered = _lowered(d)
    assert type(lowered) is RenderTimeDiagram
    with pytest.raises(TypeError, match="internal render-time view"):
        lowered.model_dump()
    # The authored IR keeps only its authored operation.
    assert d.render == [ir.Draw(obj="P_front")]


def test_two_prisms_each_get_their_own_labels():
    d = ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=0, y=0), ir.PointFixed(id="Q", x=20, y=0),
                _prism(length_label="a"), _prism(id="R", origin="Q", side="left", width_label="b")],
        render=[ir.Draw(obj="P"), ir.Draw(obj="R")],
    )
    segs = sorted((op.text, op.seg) for op in _label_ops(d))
    assert segs == [("a", "P_e_000_100"), ("b", "R_e_000_001")]


# --- unit cubes and expression dimensions -------------------------------------------------

def test_unit_cube_prism_with_labels():
    d = _diagram(_prism(length=3, width=2, height=4, unit_cubes=True, length_label="3", base_area_label="6"))
    result = asyncio.run(run_ir_pipeline(d, SVGRenderer()))
    assert result.warnings == []
    root = ET.fromstring(result.svg)
    assert _svg_label(root, "3") is not None and _svg_label(root, "6") is not None


def test_expression_dimensions_with_labels():
    d = ir.DiagramIR(
        params=ir.Params(assign={"k": 2}),
        define=[ir.PointFixed(id="O", x=0, y=0),
                _prism(length="2*k", width="k + 1", height="k", length_label="4", width_label="3",
                       height_label="2")],
        render=[ir.Draw(obj="P")],
    )
    result = asyncio.run(run_ir_pipeline(d, SVGRenderer()))
    assert result.warnings == []
    for text in ("4", "3", "2"):
        assert f'data-label-text="{text}"' in result.svg


# --- the label-dimension warning covers the fields ---------------------------------------

def _warnings(**fields) -> list[str]:
    d = _diagram(_prism(length=5, width=2, height=3, **fields))
    return asyncio.run(run_ir_pipeline(d, SVGRenderer())).warnings


def test_a_wrong_number_in_a_field_warns():
    (w,) = _warnings(length_label="7")
    assert "length_label '7'" in w and "'P'" in w
    assert "does not match its true length 5" in w


@pytest.mark.parametrize("field,text,true", [
    ("width_label", "9 cm", "2"), ("height_label", "h = 4", "3"),
])
def test_each_dimension_field_is_checked(field, text, true):
    (w,) = _warnings(**{field: text})
    # The same phrase as a manual edge label (the eval gate matches on it).
    assert f"{field} {text!r}" in w and f"does not match its true length {true}" in w
    assert f"its {field.split('_')[0]}" in w


@pytest.mark.parametrize("fields", [
    dict(length_label="5", width_label="2 m", height_label="3.0"),
    dict(length_label="l", width_label="w", height_label="h"),
    dict(base_area_label="99"),
])
def test_correct_or_non_numeric_fields_do_not_warn(fields):
    assert _warnings(**fields) == []
