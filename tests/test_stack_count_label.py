"""Stack ``count_label`` (solid-labels ticket 03).

``block_stack`` carries an optional ``count_label``. When the stack is DRAWN (a
draw or fill names its id or an id it owns), the registry's ``lower_labels``
hook lowers it, once, to a middle-anchored ``label_free_text`` at the
horizontal center of the stack's ``screen_bounds`` box, 0.5 construction units
above the box's top edge. Asserted from the lowered ops and the parsed SVG
(label ``data-bbox`` against the stack's polygon points), never from pixels.
"""
from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET

import pydantic
import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.derived import RenderTimeDiagram, effective_diagram, lower_render
from geometry_diagrams.ir.label_bounds import find_out_of_bounds_labels
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.stack import screen_bounds
from geometry_diagrams.ir.to_svg import ir_to_svg
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline

VIEWS = [("oblique", "right"), ("oblique", "left"), ("isometric", "right"), ("isometric", "left")]
HEIGHT_MAP = [[3, 2, 1, 2], [2, 1, 2, 1], [4, 2, 1, 1]]
CUBES = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [2, 0, 1], [2, 1, 1], [2, 2, 1], [1, 2, 0]]  # overhang at (1,2,0)
TEXT = "22 cubes"
POINT = ir.PointFixed(id="O", x=0, y=0)


def _stack(**kw) -> ir.BlockStack:
    f = dict(id="S", origin="O", heights=HEIGHT_MAP, count_label=TEXT)
    f.update(kw)
    return ir.BlockStack(**f)


def _diagram(stack=None, render=None, extra=(), **kw) -> ir.DiagramIR:
    return ir.DiagramIR(
        define=[POINT, stack or _stack(), *extra],
        render=[ir.Draw(obj="S")] if render is None else list(render),
        **kw,
    )


def _lowered(d):
    return lower_render(effective_diagram(d), compile_defs(d))


def _free_texts(d, text=TEXT):
    return [op for op in _lowered(d).render if op.kind == "label_free_text" and op.text == text]


def _svg(d):
    return ir_to_svg(d, compile_defs(d), [])


# --- the IR field ----------------------------------------------------------------------

def test_default_is_none():
    assert ir.BlockStack(id="S", origin="O", heights=[[1]]).count_label is None


@pytest.mark.parametrize("bad", ["", 5, 5.0, ["a"], {"a": 1}, True])
def test_empty_and_wrong_type_are_rejected(bad):
    with pytest.raises(pydantic.ValidationError):
        ir.BlockStack(id="S", origin="O", heights=[[1]], count_label=bad)
    doc = {
        "define": [{"kind": "point_fixed", "id": "O", "x": 0, "y": 0},
                   {"kind": "block_stack", "id": "S", "origin": "O", "heights": [[1]], "count_label": bad}],
        "render": [],
    }
    with pytest.raises(pydantic.ValidationError):
        ir.DiagramIR.model_validate(doc)


def test_text_is_verbatim_through_json():
    d = _diagram(_stack(count_label="Total: 22 cubes"))
    again = ir.DiagramIR.model_validate_json(d.model_dump_json())
    assert again.define[1].count_label == "Total: 22 cubes"


# --- position: the lowered op ------------------------------------------------------------

@pytest.mark.parametrize("view,side", VIEWS)
def test_op_is_above_the_screen_box_center(view, side):
    d = _diagram(_stack(view=view, side=side))
    (op,) = _free_texts(d)
    x0, y0, x1, y1 = screen_bounds(compile_defs(d)["S"])
    assert op.centroid_of is None
    assert op.at == pytest.approx([(x0 + x1) / 2, y1 + 0.5])


# --- rendered SVG: the label lies fully above the silhouette ---------------------------------

def _polygon_ys(root) -> tuple[float, float]:
    ys = []
    for el in root.iter():
        if el.tag.endswith("polygon") and el.get("data-role") == "ordered-polygon":
            nums = [float(v) for v in re.split(r"[ ,]+", el.get("points").strip())]
            ys.extend(nums[1::2])
    return min(ys), max(ys)


def _label_bbox(root, text=TEXT):
    (el,) = [e for e in root.iter() if e.get("data-label-text") == text and e.get("data-bbox")]
    return tuple(float(v) for v in el.get("data-bbox").split(","))


CASES = {
    "height_map": dict(heights=HEIGHT_MAP),
    "cube_set": dict(heights=None, cubes=CUBES),
    "flat_20x20": dict(heights=[[1] * 20 for _ in range(20)]),
    "tall_thin": dict(heights=[[20]]),
}


@pytest.mark.parametrize("view,side", VIEWS)
@pytest.mark.parametrize("case", list(CASES))
def test_label_box_lies_above_the_silhouette(case, view, side):
    stack = ir.BlockStack(id="S", origin="O", count_label=TEXT, view=view, side=side, **CASES[case])
    root = ET.fromstring(_svg(_diagram(stack)))
    top, _ = _polygon_ys(root)
    _, _, _, label_bottom = _label_bbox(root)
    assert label_bottom <= top, f"{case} {view}/{side}: label bottom {label_bottom} below silhouette top {top}"


def test_label_stays_inside_viewbox_near_canvas_top():
    # A canvas whose top edge sits just below the label: the SVG renderer grows
    # the viewBox (scale preserved) instead of clipping the label.
    d = _diagram(_stack(heights=[[3, 2], [1, 1]], view="isometric"),
                 canvas=ir.Canvas(xmin=-1, xmax=6, ymin=-1, ymax=2.5))
    svg = _svg(d)
    root = ET.fromstring(svg)
    view_y = float(root.get("viewBox").split()[1])
    _, label_top, _, label_bottom = _label_bbox(root)
    assert view_y < 0, "the case no longer exercises viewBox growth"
    assert label_top >= view_y
    assert find_out_of_bounds_labels(svg) == []
    top, _ = _polygon_ys(root)
    assert label_bottom <= top


def test_recipe_canvas_keeps_label_inside_viewbox():
    for view, side in VIEWS:
        d = _diagram(_stack(view=view, side=side))
        svg = _svg(d)
        assert find_out_of_bounds_labels(svg) == []


# --- emitted once, whatever the draw shape ------------------------------------------------------

TOP = "S_top_0_0"


@pytest.mark.parametrize("render", [
    [ir.Draw(obj="S")],
    [ir.Draw(obj="S"), ir.Draw(obj="S")],
    [ir.Fill(obj=TOP, style="lightgray")],
    [ir.Draw(obj=TOP)],
    [ir.Fill(obj=TOP, style="lightgray"), ir.Draw(obj=TOP)],
    [ir.Draw(obj="S"), ir.Fill(obj=TOP, style="lightgray"), ir.Draw(obj=TOP)],
], ids=["own_id", "two_draws", "fill_top", "draw_top", "fill_and_draw_top", "both"])
def test_emitted_exactly_once(render):
    d = _diagram(render=render)
    assert len(_free_texts(d)) == 1
    svg = _svg(d)
    assert svg.count(f'data-label-text="{TEXT}"') == 1


def test_none_when_undrawn():
    for render in ([], [ir.LabelFreeText(text="x", at=[0, 0])], [ir.DrawPoints(points=["O"])]):
        d = _diagram(render=render)
        assert _free_texts(d) == []
        assert TEXT not in _svg(d)


def test_no_label_ops_without_the_field():
    d = _diagram(_stack(count_label=None))
    assert not [op for op in _lowered(d).render if op.kind == "label_free_text"]


def test_tikz_emits_the_label():
    d = _diagram()
    assert TEXT in ir_to_tikz(d, compile_defs(d), warnings=[])


# --- interaction with prisms, warnings -----------------------------------------------------------

def test_prism_and_stack_each_get_their_labels_once():
    prism = ir.RectangularPrism(id="P", origin="Q", length=3, width=2, height=2,
                                length_label="P-LEN", base_area_label="P-AREA")
    d = ir.DiagramIR(
        define=[POINT, ir.PointFixed(id="Q", x=12, y=0), _stack(), prism],
        render=[ir.Draw(obj="S"), ir.Draw(obj="P")],
    )
    svg = _svg(d)
    for text in (TEXT, "P-LEN", "P-AREA"):
        assert svg.count(f'data-label-text="{text}"') == 1, text


def test_overlap_warning_is_unaffected():
    near = ir.PointFixed(id="N", x=1, y=0)

    def warns(count_label):
        d = ir.DiagramIR(
            define=[POINT, near, _stack(count_label=count_label),
                    ir.BlockStack(id="T", origin="N", heights=[[2]])],
            render=[ir.Draw(obj="S"), ir.Draw(obj="T")],
        )
        r = asyncio.run(run_ir_pipeline(d, SVGRenderer()))
        return list(r.warnings)

    assert warns(TEXT) == warns(None)
