"""Prism shading, labels, misuse errors and the canvas-skew warning (solids
ticket 10), at the primary seam: an authored DiagramIR (a point, a prism,
fills and labels) through the shared IR pipeline and both renderers' entry
functions.

- Shading is the existing Fill on derived face ids, with colors through the
  color layer: an opaque rgb(...) tint paints the same color in SVG and TikZ.
- Labels: a segment label on an edge id, a free-text label centered on a face
  (``centroid_of=<face id>``) and one centered on the prism itself
  (``centroid_of=<prism id>``, the projected center of the box).
- Dimension-label placement rule: a label on a segment joining two corners of
  one prism goes on the side of the segment away from the prism's projected
  center, offset so the whole label box clears the segment's line; on a
  silhouette edge that puts it fully outside the drawn silhouette. Asserted
  from the parsed SVG (label ``data-bbox`` against the silhouette corners read
  back from the stroked face polygons), never from pixels.
- Render operations that would silently do nothing (or crash) on the prism id
  raise a typed IRCompileError naming the alternative; ``Draw`` and
  ``LabelFreeText(centroid_of=...)`` on the prism id stay valid.
- A prism on a canvas with unequal axis scales adds a warning to the pipeline
  result; the render still succeeds.
"""
from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.errors import IRCompileError
from geometry_diagrams.ir.label_bounds import find_out_of_bounds_labels
from geometry_diagrams.ir.renderer import SVGRenderer, TikZRenderer
from geometry_diagrams.ir.render_util import svg_color, tikz_color
from geometry_diagrams.ir.to_svg import ir_to_svg
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline
from tests.availability import renderer_available

VIEWS = {
    "oblique": dict(view="oblique"),
    "oblique_left": dict(view="oblique", side="left"),
    "isometric": dict(view="isometric"),
    "isometric_left": dict(view="isometric", side="left"),
}
# Visible faces per side (documented rule, see tests/test_prism_draw.py).
VISIBLE = {"right": ("front", "right", "top"), "left": ("front", "left", "top")}
# A face polygon's points are listed in this corner order (bits are length,
# height, width), the documented boundary order of the derived face.
FACE_ORDER = {
    "front": ("000", "100", "110", "010"),
    "left": ("000", "010", "011", "001"),
    "right": ("100", "110", "111", "101"),
    "top": ("010", "110", "111", "011"),
}
TINTS = {"front": "rgb(230,159,0)", "right": "rgb(86,180,233)", "top": "rgb(0,158,115)"}


def _prism(**overrides) -> ir.RectangularPrism:
    fields = dict(id="P", origin="O", length=3, width=11, height=6)
    fields.update(overrides)
    return ir.RectangularPrism(**fields)


def _diagram(prism=None, render=(), styles=None, canvas=None, extra=()) -> ir.DiagramIR:
    return ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=0, y=0), prism or _prism(), *extra],
        render=list(render),
        styles=styles or {},
        canvas=canvas,
    )


def _solid_render(side: str = "right") -> list:
    """The documented solid look: fill and draw the visible face ids."""
    faces = VISIBLE[side]
    return [ir.Fill(obj=f"P_{f}", style=f"tint_{f}") for f in faces if f in TINTS] + [
        ir.Draw(obj=f"P_{f}") for f in faces
    ]


def _tint_styles() -> dict:
    return {f"tint_{face}": {"fill": color} for face, color in TINTS.items()} | {
        "tint_left": {"fill": TINTS["right"]}
    }


def _svg(d: ir.DiagramIR, warnings: list[str] | None = None) -> str:
    return ir_to_svg(d, compile_defs(d), warnings=warnings)


def _tikz(d: ir.DiagramIR, warnings: list[str] | None = None) -> str:
    return ir_to_tikz(d, compile_defs(d), warnings=warnings)


def _points(attr: str) -> list[tuple[float, float]]:
    return [tuple(float(v) for v in p.split(",")) for p in attr.split()]  # type: ignore[misc]


def _corners_px(root: ET.Element, side: str = "right") -> dict[str, tuple[float, float]]:
    """Pixel position of each visible corner, read back from the stroked
    face polygons of a drawn prism."""
    out: dict[str, tuple[float, float]] = {}
    for el in root.iter():
        fid = el.get("data-ir-id") or ""
        if el.tag.endswith("polygon") and el.get("data-role") != "fill" and fid.startswith("P_"):
            face = fid[2:]
            if face in FACE_ORDER and face in VISIBLE[side]:
                for bits, xy in zip(FACE_ORDER[face], _points(el.get("points"))):
                    out[bits] = xy
    return out


def _labels(root: ET.Element, role: str) -> list[ET.Element]:
    return [el for el in root.iter() if el.get("data-role") == role and el.get("data-bbox")]


def _bbox(el: ET.Element) -> tuple[float, float, float, float]:
    return tuple(float(v) for v in el.get("data-bbox").split(","))  # type: ignore[return-value]


def _side(p, a, b) -> float:
    """Signed area: which side of line a->b point p lies on."""
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def _box_corners(box):
    x0, y0, x1, y1 = box
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _silhouette_edges(corners: dict[str, tuple[float, float]]) -> list[tuple[str, str]]:
    """Prism edges (one differing bit) whose line has every visible corner on
    one side: the edges of the drawn silhouette."""
    bits = sorted(corners)
    out = []
    for i, p in enumerate(bits):
        for q in bits[i + 1:]:
            if sum(x != y for x, y in zip(p, q)) != 1:
                continue
            signs = {
                (s > 1e-6) - (s < -1e-6)
                for r in bits if r not in (p, q)
                for s in [_side(corners[r], corners[p], corners[q])]
            } - {0}
            if len(signs) == 1:
                out.append((p, q))
    return out


# --- (1) face shading through the color layer ------------------------------------

def test_three_tone_shaded_prism_paints_the_same_colors_in_svg_and_tikz():
    d = _diagram(render=_solid_render(), styles=_tint_styles())
    root = ET.fromstring(_svg(d))
    fills = {
        el.get("data-ir-id"): el.get("fill")
        for el in root.iter()
        if el.get("data-role") == "fill"
    }
    assert fills == {f"P_{face}": svg_color(color) for face, color in TINTS.items()}
    assert len(set(fills.values())) == 3

    warnings: list[str] = []
    tikz = _tikz(d, warnings)
    assert warnings == []
    lines = tikz.splitlines()
    for face, color in TINTS.items():
        name, definition = tikz_color(color)
        assert definition is not None
        r, g, b = (int(v) for v in re.findall(r"\d+", color))
        assert definition == f"\\definecolor{{{name}}}{{RGB}}{{{r},{g},{b}}}"
        # The SVG paint and the TikZ definition carry the same RGB value.
        assert svg_color(color) == "#{:02x}{:02x}{:02x}".format(r, g, b)
        fill_line = next(i for i, line in enumerate(lines) if line.startswith("\\tkzFillPolygon") and f"fill={name}" in line)
        def_line = lines.index(definition)
        assert def_line < fill_line, "color defined before use"


def test_face_fill_opacity_is_kept_on_the_named_face():
    d = _diagram(
        render=[ir.Fill(obj="P_bottom", style="rgb(120,120,120)", opacity=0.4), ir.Draw(obj="P")],
    )
    root = ET.fromstring(_svg(d))
    (fill,) = [el for el in root.iter() if el.get("data-role") == "fill"]
    assert fill.get("data-ir-id") == "P_bottom"
    assert fill.get("fill") == "#787878"
    assert float(fill.get("fill-opacity")) == pytest.approx(0.4)
    tikz = _tikz(d)
    assert re.search(r"\\tkzFillPolygon\[fill=gdrgb787878,opacity=0\.4\]\(P_v000,P_v100,P_v101,P_v001\)", tikz)


# --- (2) labels: edge, face centroid, prism centroid -------------------------------

def test_edge_face_and_prism_labels_are_all_placed_in_both_renderers():
    d = _diagram(
        prism=_prism(depth_scale=2 / 3),
        render=[
            ir.Fill(obj="P_bottom", style="lightgray"),
            ir.Draw(obj="P"),
            ir.LabelSegment(seg="P_e_100_110", text="5 units"),
            ir.LabelFreeText(text="60 square units", centroid_of="P_bottom"),
            ir.LabelFreeText(text="V = 198", centroid_of="P"),
        ],
    )
    warnings: list[str] = []
    svg = _svg(d, warnings)
    assert warnings == []
    root = ET.fromstring(svg)
    texts = {el.get("data-label-text") for el in root.iter() if el.get("data-label-text")}
    assert {"5 units", "60 square units", "V = 198"} <= texts
    assert find_out_of_bounds_labels(svg) == []

    tikz_warnings: list[str] = []
    tikz = _tikz(d, tikz_warnings)
    assert tikz_warnings == []
    assert re.search(r"\\tkzLabelSegment\[[^\]]*\]\(P_v100,P_v110\)\{\$5 units\$\}", tikz)
    assert "{60 square units};" in tikz
    assert "{V = 198};" in tikz


@pytest.mark.parametrize("view", list(VIEWS))
def test_label_centered_on_the_prism_sits_at_the_silhouette_center(view):
    kwargs = VIEWS[view]
    side = kwargs.get("side", "right")
    d = _diagram(
        prism=_prism(**kwargs),
        render=[*_solid_render(side), ir.LabelFreeText(text="X", centroid_of="P")],
        styles=_tint_styles(),
    )
    sym = compile_defs(d)
    root = ET.fromstring(ir_to_svg(d, sym))
    corners = _corners_px(root, side)
    xs = [x for x, _ in corners.values()]
    ys = [y for _, y in corners.values()]
    (label,) = _labels(root, "label-free-text")
    x0, y0, x1, y1 = _bbox(label)
    # The silhouette is centrally symmetric about the projected box center,
    # so that center is the middle of its bounding box.
    assert (x0 + x1) / 2 == pytest.approx((min(xs) + max(xs)) / 2, abs=0.05)
    assert (y0 + y1) / 2 == pytest.approx((min(ys) + max(ys)) / 2, abs=0.05)

    tikz = ir_to_tikz(d, sym)
    center = sym["P"].center
    cx, cy = float(center.x), float(center.y)
    corners_geo = [sym[f"P_v{a}{b}{c}"] for a in "01" for b in "01" for c in "01"]
    assert cx == pytest.approx(sum(float(p.x) for p in corners_geo) / 8)
    assert cy == pytest.approx(sum(float(p.y) for p in corners_geo) / 8)
    m = re.search(r"\\node at \(([-\d.]+),([-\d.]+)\) \{X\};", tikz)
    assert m is not None
    assert float(m.group(1)) == pytest.approx(cx, abs=1e-3)
    assert float(m.group(2)) == pytest.approx(cy, abs=1e-3)


def test_label_centered_on_the_prism_is_valid_through_the_pipeline():
    d = _diagram(render=[ir.Draw(obj="P"), ir.LabelFreeText(text="198 cubic units", centroid_of="P")])
    result = asyncio.run(run_ir_pipeline(d, SVGRenderer()))
    assert "198 cubic units" in result.svg
    assert result.warnings == []


def test_face_label_sits_at_the_face_centroid():
    d = _diagram(render=[ir.Draw(obj="P"), ir.LabelFreeText(text="A", centroid_of="P_bottom")])
    sym = compile_defs(d)
    tikz = ir_to_tikz(d, sym)
    base = [sym[n] for n in ("P_v000", "P_v100", "P_v101", "P_v001")]
    cx = sum(float(p.x) for p in base) / 4
    cy = sum(float(p.y) for p in base) / 4
    m = re.search(r"\\node at \(([-\d.]+),([-\d.]+)\) \{A\};", tikz)
    assert m is not None
    assert (float(m.group(1)), float(m.group(2))) == pytest.approx((cx, cy), abs=1e-3)


# --- (3) dimension-label placement rule --------------------------------------------

# Dimension sets: box A (length 3, 11 deep, 6 tall), box B at the wireframe
# depth scale, and a tall thin box.
DIMS = {
    "box_a": dict(length=3, width=11, height=6),
    "box_b": dict(length=10, width=6, height=5, depth_scale=2 / 3),
    "tall": dict(length=2, width=2, height=8),
}


def _prism_for(view: str, dims: str) -> ir.RectangularPrism:
    fields = {**VIEWS[view], **DIMS[dims]}
    if fields.get("view") == "isometric":
        fields.pop("depth_scale", None)
    return _prism(**fields)


def _edge_cases():
    """Every silhouette edge of every view and dimension set (found by a
    supporting-line test on the corners read back from the SVG, not by the
    renderer's own rule)."""
    cases = []
    for view, kwargs in VIEWS.items():
        side = kwargs.get("side", "right")
        for dims in DIMS:
            d = _diagram(prism=_prism_for(view, dims), render=[ir.Draw(obj="P")])
            root = ET.fromstring(_svg(d))
            for p, q in _silhouette_edges(_corners_px(root, side)):
                cases.append((view, dims, p, q))
    return cases


EDGE_CASES = _edge_cases()


def test_every_view_has_a_six_edge_silhouette():
    for view in VIEWS:
        for dims in DIMS:
            assert sum(1 for v, d, _, _ in EDGE_CASES if (v, d) == (view, dims)) == 6, (view, dims)


@pytest.mark.parametrize("view,dims,p,q", EDGE_CASES)
def test_dimension_label_on_a_silhouette_edge_sits_wholly_outside(view, dims, p, q):
    side = VIEWS[view].get("side", "right")
    d = _diagram(
        prism=_prism_for(view, dims),
        render=[ir.Draw(obj="P"), ir.LabelSegment(seg=f"P_e_{p}_{q}", text="11 units")],
    )
    svg = _svg(d)
    root = ET.fromstring(svg)
    corners = _corners_px(root, side)
    (label,) = _labels(root, "label-segment")
    a, b = corners[p], corners[q]
    inside = next(_side(corners[r], a, b) for r in corners if r not in (p, q) and abs(_side(corners[r], a, b)) > 1e-6)
    for c in _box_corners(_bbox(label)):
        s = _side(c, a, b)
        assert s * inside < 0, f"label corner {c} is not outside edge {p}-{q}"
    assert find_out_of_bounds_labels(svg) == []


def test_reference_box_a_labels_land_where_the_reference_puts_them():
    """Box A: '6 units' left of the front-left vertical edge, '3 units'
    below the front bottom edge, '11 units' right of the receding right
    side (the bottom-right depth edge)."""
    d = _diagram(
        prism=_prism(length=3, height=6, width=11),
        render=[
            *_solid_render(),
            ir.LabelSegment(seg="P_e_000_010", text="6 units"),
            ir.LabelSegment(seg="P_e_000_100", text="3 units"),
            ir.LabelSegment(seg="P_e_100_101", text="11 units"),
        ],
        styles=_tint_styles(),
    )
    svg = _svg(d)
    root = ET.fromstring(svg)
    corners = _corners_px(root)
    xs = [x for x, _ in corners.values()]
    ys = [y for _, y in corners.values()]
    boxes = {el.get("data-label-text"): _bbox(el) for el in _labels(root, "label-segment")}
    assert boxes["6 units"][2] <= min(xs)          # wholly left of the silhouette
    assert boxes["3 units"][1] >= max(ys)          # wholly below it
    bx0, by0, bx1, by1 = boxes["11 units"]
    a, b = corners["100"], corners["101"]
    assert bx0 >= min(a[0], b[0])                   # to the right of the receding edge
    assert all(_side(c, a, b) * _side(corners["000"], a, b) < 0 for c in _box_corners(boxes["11 units"]))
    assert find_out_of_bounds_labels(svg) == []


def test_reference_box_b_label_right_of_the_right_vertical_edge():
    d = _diagram(
        prism=_prism(length=10, width=6, height=5, depth_scale=2 / 3),
        render=[
            ir.Fill(obj="P_bottom", style="lightgray"),
            ir.Draw(obj="P"),
            ir.LabelSegment(seg="P_e_101_111", text="5 units"),
            ir.LabelFreeText(text="60 square units", centroid_of="P_bottom"),
        ],
    )
    svg = _svg(d)
    root = ET.fromstring(svg)
    corners = _corners_px(root)
    (label,) = _labels(root, "label-segment")
    assert _bbox(label)[0] >= max(x for x, _ in corners.values())
    assert find_out_of_bounds_labels(svg) == []


def test_unit_cube_edge_labels_stay_off_the_gridlines():
    d = _diagram(
        prism=_prism(view="isometric", length=2, width=4, height=5, unit_cubes=True),
        render=[
            ir.Draw(obj="P"),
            ir.LabelSegment(seg="P_e_000_100", text="2 units"),
            ir.LabelSegment(seg="P_e_100_101", text="4 units"),
            ir.LabelSegment(seg="P_e_000_010", text="5 units"),
        ],
    )
    svg = _svg(d)
    root = ET.fromstring(svg)
    corners = _corners_px(root)
    for el in _labels(root, "label-segment"):
        p, q = {"2 units": ("000", "100"), "4 units": ("100", "101"), "5 units": ("000", "010")}[el.get("data-label-text")]
        a, b = corners[p], corners[q]
        inside = _side(corners["111"], a, b)
        assert all(_side(c, a, b) * inside < 0 for c in _box_corners(_bbox(el)))
    assert find_out_of_bounds_labels(svg) == []


def test_face_diagonal_label_goes_away_from_the_prism_center():
    """A face diagonal is not on the silhouette: its label goes on the side of
    the diagonal away from the projected box center, clear of the line."""
    d = _diagram(
        render=[ir.Draw(obj="P"), ir.LabelSegment(seg="D", text="d")],
        extra=[ir.Segment(id="D", a="P_v000", b="P_v110")],
    )
    sym = compile_defs(d)
    root = ET.fromstring(ir_to_svg(d, sym))
    corners = _corners_px(root)
    a, b = corners["000"], corners["110"]
    # The projected center is the midpoint of the 010-101 diagonal's ends.
    c010, c101 = corners["010"], corners["101"]
    center = ((c010[0] + c101[0]) / 2, (c010[1] + c101[1]) / 2)
    (label,) = _labels(root, "label-segment")
    assert all(_side(c, a, b) * _side(center, a, b) < 0 for c in _box_corners(_bbox(label)))


def test_space_diagonal_label_is_placed_by_the_generic_rule():
    """The space diagonal passes through the projected center, so there is
    no 'away' side: the generic segment-label placement decides. It is still
    placed and fully inside the canvas."""
    d = _diagram(
        render=[ir.Draw(obj="P"), ir.LabelSegment(seg="D", text="d")],
        extra=[ir.Segment(id="D", a="P_v000", b="P_v111")],
    )
    svg = _svg(d)
    (label,) = _labels(ET.fromstring(svg), "label-segment")
    assert label.get("data-label-text") == "d"
    assert find_out_of_bounds_labels(svg) == []


def test_tikz_prism_edge_label_gets_an_outward_anchor():
    d = _diagram(
        render=[
            ir.Draw(obj="P"),
            ir.LabelSegment(seg="P_e_000_010", text="6 units"),
            ir.LabelSegment(seg="P_e_000_100", text="3 units"),
            ir.LabelSegment(seg="P_e_101_111", text="5 units"),
        ],
    )
    tikz = _tikz(d)
    assert "\\tkzLabelSegment[left](P_v000,P_v010){$6 units$}" in tikz
    assert "\\tkzLabelSegment[below](P_v000,P_v100){$3 units$}" in tikz
    assert "\\tkzLabelSegment[right](P_v101,P_v111){$5 units$}" in tikz


def test_non_prism_segment_label_tikz_is_unchanged():
    d = ir.DiagramIR(
        define=[
            ir.PointFixed(id="A", x=0, y=0), ir.PointFixed(id="B", x=4, y=0),
            ir.Segment(id="AB", a="A", b="B"),
        ],
        render=[ir.Draw(obj="AB"), ir.LabelSegment(seg="AB", text="4"), ir.LabelSegment(seg="AB", text="m", pos=0.3)],
    )
    tikz = _tikz(d)
    assert "\\tkzLabelSegment(A,B){$4$}" in tikz
    assert "\\tkzLabelSegment[pos=0.3](A,B){$m$}" in tikz


# --- (4) misuse of render operations on the prism id -------------------------------

A = ir.AngleSpec
MISUSES = {
    "fill": (ir.Fill(obj="P"), "P_bottom"),
    "fill_hole": (ir.Fill(obj="P_front", holes=["P"]), "P_bottom"),
    "draw_points": (ir.DrawPoints(points=["P"]), "P_v000"),
    "label_point": (ir.LabelPoint(p="P"), "P_v000"),
    "mark_segments": (ir.MarkSegments(segs=["P"]), "P_e_000_100"),
    "label_segment": (ir.LabelSegment(seg="P", text="x"), "P_e_000_100"),
    "mark_angles": (ir.MarkAngles(angles=[A(a="P_v100", o="P", b="P_v010")]), "P_v000"),
    "mark_right_angles": (ir.MarkRightAngles(angles=[A(a="P", o="P_v000", b="P_v010")]), "P_v000"),
    "label_angle": (ir.LabelAngle(angle=A(a="P_v100", o="P_v000", b="P"), text="x"), "P_v000"),
    "mark_arcs": (ir.MarkArcs(arcs=["P"]), "P_e_000_100"),
    "label_along_arc": (ir.LabelAlongArc(arc="P", text="x"), "label_free_text"),
}


@pytest.mark.parametrize("name", list(MISUSES))
@pytest.mark.parametrize("entry", ["compile", "svg", "tikz"])
def test_render_op_misuse_on_the_prism_id_is_a_typed_error(name, entry):
    op, alternative = MISUSES[name]
    d = _diagram(render=[ir.Draw(obj="P"), op])
    # The renderer entries get a table compiled from the valid diagram, so
    # each entry point is exercised on its own.
    sym = compile_defs(_diagram(render=[ir.Draw(obj="P")]))
    with pytest.raises(IRCompileError) as exc:
        if entry == "compile":
            compile_defs(d)
        elif entry == "svg":
            ir_to_svg(d, sym)
        else:
            ir_to_tikz(d, sym)
    msg = str(exc.value)
    assert "'P'" in msg and "rectangular_prism" in msg
    assert alternative in msg


def test_misuse_message_names_renamed_corners():
    d = _diagram(prism=_prism(vertex_names=list("ABCDEFGH")), render=[ir.LabelPoint(p="P")])
    with pytest.raises(IRCompileError, match="'A'"):
        compile_defs(d)


def test_fill_on_the_prism_id_fails_the_pipeline_with_the_alternative():
    d = _diagram(render=[ir.Fill(obj="P"), ir.Draw(obj="P")])
    with pytest.raises(IRCompileError, match="fill a face id such as 'P_bottom'"):
        asyncio.run(run_ir_pipeline(d, SVGRenderer()))


def test_renderer_entry_rejects_misuse_even_with_a_precompiled_table():
    """Tooling that compiles a valid diagram and renders another (or an
    edited) one still hits the check at the lowering point."""
    sym = compile_defs(_diagram(render=[ir.Draw(obj="P")]))
    bad = _diagram(render=[ir.Fill(obj="P")])
    for render in (ir_to_svg, ir_to_tikz):
        with pytest.raises(IRCompileError, match="P_bottom"):
            render(bad, sym)


def test_valid_prism_ops_raise_nothing():
    d = _diagram(render=[
        ir.Fill(obj="P_bottom"), ir.Draw(obj="P"),
        ir.LabelFreeText(text="c", centroid_of="P"),
        ir.LabelSegment(seg="P_e_000_100", text="6"),
        ir.MarkSegments(segs=["P_e_000_100", "P_e_010_110"]),
        ir.LabelPoint(p="P_v000", text="A"),
        ir.MarkRightAngles(angles=[A(a="P_v100", o="P_v000", b="P_v010")]),
    ])
    warnings: list[str] = []
    result = asyncio.run(run_ir_pipeline(d, SVGRenderer()))
    assert result.warnings == []
    _tikz(d, warnings)
    assert warnings == []


# --- (5) canvas skew warning --------------------------------------------------------

def test_prism_on_a_skewed_canvas_warns_and_still_renders():
    d = _diagram(
        render=[ir.Draw(obj="P")],
        canvas=ir.Canvas(xmin=-1, xmax=12, ymin=-1, ymax=10, aspect=2),
    )
    result = asyncio.run(run_ir_pipeline(d, SVGRenderer()))
    assert "<svg" in result.svg
    skew = [w for w in result.warnings if "aspect" in w]
    assert len(skew) == 1
    assert "'P'" in skew[0] and "skew" in skew[0]


def test_no_skew_warning_without_aspect_or_without_a_prism():
    plain = _diagram(render=[ir.Draw(obj="P")], canvas=ir.Canvas(xmin=-1, xmax=12, ymin=-1, ymax=10))
    assert asyncio.run(run_ir_pipeline(plain, SVGRenderer())).warnings == []
    no_prism = ir.DiagramIR(
        define=[ir.PointFixed(id="A", x=0, y=0), ir.PointFixed(id="B", x=3, y=1), ir.Segment(id="s", a="A", b="B")],
        render=[ir.Draw(obj="s")],
        canvas=ir.Canvas(aspect=2),
    )
    assert asyncio.run(run_ir_pipeline(no_prism, SVGRenderer())).warnings == []


# --- TikZ compile smoke (renderer container) -------------------------------------

@pytest.mark.skipif(not renderer_available(), reason="TikZ renderer container not running")
@pytest.mark.parametrize("view", list(VIEWS))
def test_tikz_compile_smoke_shaded_labeled_prism(view):
    kwargs = VIEWS[view]
    side = kwargs.get("side", "right")
    d = _diagram(
        prism=_prism(**kwargs),
        render=[
            *_solid_render(side),
            ir.LabelSegment(seg="P_e_000_010", text="6 units"),
            ir.LabelSegment(seg="P_e_000_100", text="3 units"),
            ir.LabelFreeText(text="33 square units", centroid_of="P_bottom"),
            ir.LabelFreeText(text="V", centroid_of="P"),
        ],
        styles=_tint_styles(),
    )
    warnings: list[str] = []
    result = TikZRenderer().render(d, compile_defs(d), warnings=warnings)
    assert "<svg" in result.output
    assert warnings == []
