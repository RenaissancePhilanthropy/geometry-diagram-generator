"""Python scripting surface for prisms (solids ticket 15): the `prism` function,
its Prism handle (corner/edge/face accessors, volume/base_area), builder edge
reuse, assert_volume/assert_true_length, and the `solids` gating of the
namespace (inside and outside the sandbox) and the prompt text."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.pydsl import GROUPED_NAMES, api, asserts
from geometry_diagrams.pydsl.builder import GeometricAssertionError, new_builder_context
from geometry_diagrams.pydsl.handles import Point, Polygon, Prism, Segment
from geometry_diagrams.pydsl.sandbox import run_script
from geometry_diagrams.pydsl.stub import generate_stub
from geometry_diagrams.strategies import instructions_python_full as ipf

SOLIDS = frozenset({"solids"})
_PRE = json.loads((Path(__file__).parent / "python_full_prompt_pre_solids.json").read_text())


def _box(length=4, width=3, height=2, **kw):
    return api.prism(api.point(0, 0), length, width, height, **kw)


# --- the function and handle ---------------------------------------------------------------

def test_prism_records_one_def_and_returns_a_handle_with_the_prism_id():
    with new_builder_context() as b:
        box = _box(vertex_names=None, side="left", depth_scale=0.667)
        d = b.build()
    stmts = [s for s in d.define if isinstance(s, ir.RectangularPrism)]
    assert len(stmts) == 1 and stmts[0].id == box.id
    assert (stmts[0].length, stmts[0].width, stmts[0].height) == (4, 3, 2)
    assert stmts[0].side == "left" and stmts[0].depth_scale == 0.667
    assert isinstance(box, Prism) and (box.volume, box.base_area) == (24, 12)


def test_corner_reads_position_mid_script():
    with new_builder_context():
        box = _box()
        c000, c100, c010 = box.corner(0, 0, 0), box.corner(1, 0, 0), box.corner(0, 1, 0)
        assert isinstance(c100, Point)
        assert (c000.x, c000.y) == (0, 0)
        assert (c100.x, c100.y) == (4, 0)          # length is the front bottom edge
        assert (c010.x, c010.y) == (0, 2)          # height is vertical
        c001 = box.corner(0, 0, 1)                 # width recedes (45 deg, scale 1/2)
        assert c001.x == pytest.approx(3 * 0.5 * 2 ** -0.5) and c001.y == pytest.approx(3 * 0.5 * 2 ** -0.5)


def test_edge_accessor_returns_the_prisms_own_edge_segment():
    with new_builder_context():
        box = _box()
        e = box.edge(box.corner(0, 0, 0), box.corner(1, 0, 0))
        assert isinstance(e, Segment) and e.id == f"{box.id}_e_000_100"
        assert box.edge((1, 0, 0), (0, 0, 0)).id == e.id
        with pytest.raises(ValueError, match="not the ends of one edge"):
            box.edge(box.corner(0, 0, 0), box.corner(1, 0, 1))
        with pytest.raises(ValueError, match="not a corner"):
            box.edge(api.point(9, 9), box.corner(1, 0, 0))


def test_face_accessor_returns_polygon_handles_and_base_is_the_bottom_face():
    with new_builder_context() as b:
        box = _box()
        front = box.face("front")
        assert isinstance(front, Polygon) and front.id == f"{box.id}_front"
        assert sorted(v.id for v in front.vertices) == sorted(
            box.corner(a, b, 0).id for a in (0, 1) for b in (0, 1))
        assert box.face("base").id == box.face("bottom").id == f"{box.id}_bottom"
        with pytest.raises(ValueError, match="unknown face"):
            box.face("side")
        n_defs = len(b.build().define)
        box.face("base")
        assert len(b.build().define) == n_defs  # no duplicate polygon


def test_drawing_filling_and_labeling_record_ops_over_derived_ids():
    with new_builder_context() as b:
        box = _box()
        api.draw(box)
        api.fill(box.face("top"), color="rgb(1, 2, 3)")
        box.edge(box.corner(0, 0, 0), box.corner(1, 0, 0)).label("4")
        api.label_text("V", centroid_of=box)
        box.label("box")
        d = b.build()
    assert any(isinstance(r, ir.Draw) and r.obj == box.id for r in d.render)
    assert any(isinstance(r, ir.Fill) and r.obj == f"{box.id}_top" for r in d.render)
    assert any(isinstance(r, ir.LabelSegment) and r.seg == f"{box.id}_e_000_100" for r in d.render)
    assert [r.centroid_of for r in d.render if isinstance(r, ir.LabelFreeText)] == [box.id, box.id]


def test_vertex_names_rename_corners():
    names = list("ABCDEFGH")
    with new_builder_context():
        box = _box(vertex_names=names)
        assert box.corner(0, 0, 0).id == "A" and box.corner(1, 1, 1).id == "H"
        assert box.corner(1, 0, 0).x == 4


@pytest.mark.parametrize("kwargs,msg", [
    ({"vertex_names": ["A", "B"]}, "vertex_names"),
    ({"unit_cubes": True, "length": 2.5}, "integer"),
    ({"length": -1}, "positive"),
    ({"view": "top"}, "view"),
    ({"side": "up"}, "side"),
    ({"view": "isometric", "depth_scale": 0.5}, "isometric"),
])
def test_misuse_is_the_scripts_error_with_a_usable_message(kwargs, msg):
    with new_builder_context():
        with pytest.raises(Exception, match=msg):
            _box(**{"length": 4, **kwargs})


# --- builder edge reuse ----------------------------------------------------------------------

def test_segment_between_two_corners_of_one_edge_is_the_prisms_own_edge():
    with new_builder_context() as b:
        box = _box()
        s = api.segment(box.corner(0, 0, 0), box.corner(1, 0, 0))
        again = api.segment(box.corner(1, 0, 0), box.corner(0, 0, 0))
        d = b.build()
    assert s.id == again.id == f"{box.id}_e_000_100"
    assert not [x for x in d.define if isinstance(x, ir.Segment)]  # no duplicate stroke


def test_diagonals_get_a_normal_segment_and_non_prism_segments_are_unchanged():
    with new_builder_context() as b:
        box = _box()
        diag = api.segment(box.corner(0, 0, 0), box.corner(1, 0, 1))
        p, q = api.point(5, 5), api.point(6, 6)
        plain = api.segment(p, q)
        d = b.build()
    segs = {x.id: x for x in d.define if isinstance(x, ir.Segment)}
    assert diag.id.startswith("__pydsl_seg_") and segs[diag.id].a == box.corner(0, 0, 0).id
    assert plain.id in segs and plain.id != diag.id


def test_face_side_reuses_the_edge_too():
    with new_builder_context():
        box = _box()
        side = box.face("front").side(box.corner(0, 0, 0), box.corner(0, 1, 0))
        assert side.id == f"{box.id}_e_000_010"


# --- assertion helpers ----------------------------------------------------------------------

def test_assert_volume_passes_and_fails():
    with new_builder_context():
        box = _box()
        asserts.assert_volume(box, 24)
        with pytest.raises(GeometricAssertionError, match="24|25"):
            asserts.assert_volume(box, 25)
        with pytest.raises(GeometricAssertionError):
            asserts.assert_volume(box, 24.01)
        asserts.assert_volume(box, 24.01, tol=1e-3)


def test_assert_true_length_is_3d_not_the_drawn_length():
    with new_builder_context():
        box = _box()
        diag = api.segment(box.corner(0, 0, 0), box.corner(1, 0, 1))   # sqrt(4^2 + 3^2)
        asserts.assert_true_length(diag, 5)
        with pytest.raises(GeometricAssertionError):
            asserts.assert_true_length(diag, 4.5)
        with pytest.raises(GeometricAssertionError):
            asserts.assert_distance(diag, 5)                           # drawn 2D length differs
        asserts.assert_true_length(api.segment(box.corner(0, 0, 0), box.corner(1, 1, 1)), 29 ** 0.5)


# --- gating: namespace, stub, prompt ---------------------------------------------------------

def test_grouped_names_are_real_attributes_of_the_package():
    import geometry_diagrams.pydsl as pydsl

    assert {"prism", "Prism", "assert_volume", "assert_true_length"} <= set(GROUPED_NAMES["solids"])
    for n in GROUPED_NAMES["solids"]:
        assert hasattr(pydsl, n)
        assert n not in pydsl.__all__          # never in the ungated surface


def test_build_tool_names_gates_the_real_names():
    import geometry_diagrams.pydsl as pydsl
    from geometry_diagrams.pydsl._sandbox_child import _build_tool_names

    off = _build_tool_names(pydsl, False, frozenset())
    on = _build_tool_names(pydsl, False, SOLIDS)
    assert "prism" not in off and "assert_volume" not in off and "assert_true_length" not in off
    assert {"prism", "assert_volume", "assert_true_length"} <= set(on)


def test_stub_excludes_the_names_unless_enabled():
    off, on = generate_stub(), generate_stub(SOLIDS)
    for needle in ("def prism(", "class Prism", "assert_volume", "assert_true_length"):
        assert needle not in off and needle in on
    assert on.startswith(off)


def test_solids_off_prompt_is_byte_identical_to_before_this_ticket():
    assert ipf.build_python_full_instructions() == _PRE["default"]
    assert ipf.build_python_full_instructions(features=frozenset()) == _PRE["default"]
    assert ipf.build_python_full_instructions(include_cookbook=True) == _PRE["cookbook"]
    off = ipf.build_python_full_instructions()
    for needle in ("prism", "Prism", "assert_volume", "assert_true_length"):
        assert needle not in off


def test_solids_on_prompt_has_the_stub_and_the_guidance():
    on = ipf.build_python_full_instructions(features=SOLIDS)
    assert on.endswith(ipf._SOLIDS_FRAGMENT)
    for needle in ("def prism(", "def assert_volume(", "assert_true_length", "depth_scale=2/3",
                   "do NOT `draw(box)`", "isometric", "10 x 6", "rgb(r, g, b)", "assert_distance"):
        assert needle in on
    assert ipf.PRISM_EXAMPLE_SCRIPT.splitlines()[1] in on


# --- real sandbox ---------------------------------------------------------------------------

def test_documented_example_runs_in_the_sandbox_and_renders():
    import asyncio

    from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline

    res = run_script(ipf.PRISM_EXAMPLE_SCRIPT, timeout_seconds=60, features=SOLIDS)
    assert res.error is None, res.error
    d = res.diagram_ir
    box_id = res.variable_ids["box"]
    assert next(s for s in d.define if s.id == box_id).kind == "rectangular_prism"
    # the manifest binds a variable to the prism (position hook)
    from geometry_diagrams.ir.render_util import build_entity_manifest
    from geometry_diagrams.ir.to_sympy import compile_defs

    manifest = build_entity_manifest(d, compile_defs(d), res.variable_ids)
    assert any(e["name"] == "box" and e["type"] == "rectangular_prism" for e in manifest["named"])
    assert {n for n in res.variable_ids if n in ("front", "right", "top")} == {"front", "right", "top"}
    # the labelled edges reuse the prism's own edges; only the diagonal needs a helper segment
    assert len([x for x in d.define if isinstance(x, ir.Segment)]) == 1
    out = asyncio.run(run_ir_pipeline(d, SVGRenderer()))
    assert out.svg and "<svg" in out.svg
    assert not out.warnings, out.warnings   # e.g. no unrecognized-color warning from the example


def test_names_absent_without_solids_inside_the_sandbox():
    res = run_script("o = point(0, 0)\nbox = prism(o, 4, 3, 2)\ndraw(box)\n", timeout_seconds=60)
    assert res.diagram_ir is None
    assert "prism" in (res.error or "")
    res = run_script("o = point(0, 0)\nbox = prism(o, 4, 3, 2)\ndraw(box)\n", timeout_seconds=60,
                     features=SOLIDS)
    assert res.error is None, res.error


def test_misuse_message_reaches_the_retry_message():
    res = run_script("box = prism(point(0, 0), 4, 3, 2, vertex_names=['A'])\n",
                     timeout_seconds=60, features=SOLIDS)
    assert res.error and "vertex_names" in res.error
    assert res.retry_message and "vertex_names" in res.retry_message
