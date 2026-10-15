"""Python scripting surface for block stacks: `stack`, the Stack handle
(.cube_count/.volume/.top), assert_cube_count, label_text(centroid_of=stack),
and the `solids` gating of the namespace (inside and outside the sandbox) and
the prompt text."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.pydsl import GROUPED_NAMES, api, asserts
from geometry_diagrams.pydsl.builder import GeometricAssertionError, new_builder_context
from geometry_diagrams.pydsl.handles import Polygon, Stack
from geometry_diagrams.pydsl.sandbox import run_script
from geometry_diagrams.pydsl.stub import generate_stub
from geometry_diagrams.strategies import instructions_python_full as ipf

SOLIDS = frozenset({"solids"})
_PRE = json.loads((Path(__file__).parent / "python_full_prompt_pre_solids.json").read_text())


def _stack(**kw):
    kw.setdefault("heights", [[1, 2], [3, 0]])
    return api.stack(api.point(0, 0), **kw)


# --- function and handle -------------------------------------------------------------------

def test_stack_records_one_def_and_returns_a_handle_with_the_stack_id():
    with new_builder_context() as b:
        s = _stack(view="isometric", side="left", top_color="#e6eefa")
        d = b.build()
    stmts = [x for x in d.define if isinstance(x, ir.BlockStack)]
    assert len(stmts) == 1 and stmts[0].id == s.id and s.id.startswith("__pydsl_stack_")
    assert stmts[0].heights == [[1, 2], [3, 0]] and stmts[0].view == "isometric"
    assert stmts[0].side == "left" and stmts[0].top_color == "#e6eefa"
    assert isinstance(s, Stack)


def test_cube_count_and_volume_are_readable_before_the_script_finishes():
    with new_builder_context():
        s = _stack()
        assert (s.cube_count, s.volume) == (6, 6)
        arch = api.stack(api.point(5, 0), cubes=[[0, 0, 0], [0, 1, 0], [2, 0, 0], [2, 1, 0], [1, 1, 0]])
        assert arch.cube_count == 5


def test_top_returns_a_polygon_over_the_column_top_face_id():
    with new_builder_context():
        s = _stack()
        t = s.top(1, 0)
        assert isinstance(t, Polygon) and t.id == f"{s.id}_top_1_0"
        assert len(t.vertices) == 4
        assert t.area > 0  # vertex coordinates resolve mid-script


def test_top_of_an_unoccupied_or_out_of_range_column_names_the_valid_columns():
    with new_builder_context():
        s = _stack()
        for xz in ((1, 1), (5, 0)):  # height-0 column; outside the grid
            with pytest.raises(ValueError, match=r"no occupied column.*\(0, 0\).*\(1, 0\).*\(0, 1\)"):
                s.top(*xz)


@pytest.mark.parametrize("kwargs,msg", [
    ({"heights": None}, "exactly one"),
    ({"cubes": [[0, 0, 0]]}, "exactly one"),
    ({"view": "top"}, "view must be"),
    ({"side": "up"}, "side must be"),
    ({"heights": [[1.5]]}, "integer"),
])
def test_misuse_is_the_scripts_error_with_a_usable_message(kwargs, msg):
    with new_builder_context():
        with pytest.raises(Exception, match=msg):
            _stack(**kwargs)


def test_origin_must_be_a_point():
    with new_builder_context():
        with pytest.raises(ValueError, match="origin must be a Point"):
            api.stack("O", heights=[[1]])


def test_label_text_centroid_of_stack_and_top_record_ops():
    with new_builder_context() as b:
        s = _stack()
        api.label_text("S", centroid_of=s)
        api.label_text("3", centroid_of=s.top(0, 1))
        s.label("hi")
        d = b.build()
    cents = [op.centroid_of for op in d.render if isinstance(op, ir.LabelFreeText)]
    assert cents == [s.id, f"{s.id}_top_0_1", s.id]


def test_stack_and_column_ids_are_hidden_from_list_objects():
    from geometry_diagrams.ir.derived import effective_diagram
    from geometry_diagrams.ir.queries import list_objects
    from geometry_diagrams.ir.to_sympy import compile_defs

    res = run_script("o = point(0, 0)\ns = stack(o, heights=[[1, 2], [3, 0]])\ndraw(s)\n",
                     timeout_seconds=60, features=SOLIDS)
    assert res.error is None, res.error
    d = res.diagram_ir
    sid = res.variable_ids["s"]
    assert sid.startswith("__pydsl_stack_")
    sym = compile_defs(d)
    assert any(k.startswith(f"{sid}_top_") for k in sym)  # the columns exist in the table, yet are not listed
    listed = list_objects(sym)
    assert not any("stack" in k or "_top_" in k for k in listed), listed


# --- assert_cube_count ---------------------------------------------------------------------

def test_assert_cube_count_passes_and_fails_with_actual_and_expected():
    with new_builder_context():
        s = _stack()
        asserts.assert_cube_count(s, 6)
        with pytest.raises(GeometricAssertionError, match=r"6 cubes != expected 7"):
            asserts.assert_cube_count(s, 7)


# --- gating --------------------------------------------------------------------------------

def test_grouped_names_are_real_attributes_and_include_the_stack_names():
    import geometry_diagrams.pydsl as pydsl
    assert set(GROUPED_NAMES["solids"]) == {
        "prism", "Prism", "assert_volume", "assert_true_length", "stack", "Stack", "assert_cube_count",
    }
    for name in GROUPED_NAMES["solids"]:
        assert hasattr(pydsl, name) and name not in pydsl.__all__


def test_build_tool_names_gates_the_stack_names():
    import geometry_diagrams.pydsl as pydsl
    from geometry_diagrams.pydsl._sandbox_child import _build_tool_names

    off = _build_tool_names(pydsl, False, frozenset())
    on = _build_tool_names(pydsl, False, SOLIDS)
    assert not {"stack", "assert_cube_count"} & set(off)
    assert {"stack", "assert_cube_count"} <= set(on)


def test_stub_documents_stack_only_when_enabled():
    off, on = generate_stub(), generate_stub(SOLIDS)
    for needle in ("def stack(", "class Stack:", "def assert_cube_count("):
        assert needle not in off and needle in on
    assert "cube_count" in on and "def top(" in on


def test_solids_off_prompt_is_byte_identical():
    assert ipf.build_python_full_instructions() == _PRE["default"]
    assert ipf.build_python_full_instructions(include_cookbook=True) == _PRE["cookbook"]
    off = ipf.build_python_full_instructions()
    assert "assert_cube_count" not in off and "def stack(" not in off and "class Stack" not in off


def test_solids_on_prompt_has_the_stack_guidance():
    text = ipf.build_python_full_instructions(features=SOLIDS)
    for needle in ("## Stacks of unit cubes", "heights[z][x]", "not a height map", "Never draw individual cubes",
                   "at most 400 cubes", "at most 20 cells", "assert_cube_count", 'view="isometric"', "s.top(x, z)"):
        assert needle in text, needle
    assert "## Stacks of unit cubes" not in ipf.build_python_full_instructions()


# --- real sandbox --------------------------------------------------------------------------

def _run(script, features=SOLIDS):
    res = run_script(script, timeout_seconds=90, features=features)
    assert res.error is None, res.error
    return res


def test_documented_examples_run_in_the_sandbox_and_render():
    import asyncio

    from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline

    for script in (ipf.STACK_EXAMPLE_SCRIPT, ipf.STACK_ISOMETRIC_EXAMPLE_SCRIPT, ipf.STACK_CUBES_EXAMPLE_SCRIPT):
        res = _run(script)
        stmts = [d for d in res.diagram_ir.define if isinstance(d, ir.BlockStack)]
        assert len(stmts) == 1
        out = asyncio.run(run_ir_pipeline(res.diagram_ir, SVGRenderer()))
        assert "<svg" in out.svg
        if script is not ipf.STACK_CUBES_EXAMPLE_SCRIPT:
            assert not out.warnings, out.warnings


def test_cubes_example_is_a_real_overhang_not_a_height_map():
    import asyncio

    from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline

    res = _run(ipf.STACK_CUBES_EXAMPLE_SCRIPT)
    out = asyncio.run(run_ir_pipeline(res.diagram_ir, SVGRenderer()))
    assert any("height map" in w for w in out.warnings), out.warnings


def test_example_yields_the_expected_ir_and_manifest_entry():
    from geometry_diagrams.ir.render_util import build_entity_manifest
    from geometry_diagrams.ir.to_sympy import compile_defs

    res = _run(ipf.STACK_EXAMPLE_SCRIPT)
    d = res.diagram_ir
    st = next(x for x in d.define if isinstance(x, ir.BlockStack))
    assert st.heights == [[1, 2], [3, 0]] and st.id == res.variable_ids["s"]
    manifest = build_entity_manifest(d, compile_defs(d), res.variable_ids)
    assert any(e["name"] == "s" and e["type"] == "block_stack" for e in manifest["named"])


def test_mid_script_count_read_in_the_sandbox():
    _run("o = point(0, 0)\ns = stack(o, heights=[[2, 2]])\nassert s.cube_count == 4\nassert s.volume == 4\ndraw(s)\n")


def test_names_absent_without_solids_inside_the_sandbox():
    script = "o = point(0, 0)\ns = stack(o, heights=[[1]])\ndraw(s)\n"
    res = run_script(script, timeout_seconds=60)
    assert res.diagram_ir is None and "stack" in (res.error or "")
    assert run_script(script, timeout_seconds=60, features=SOLIDS).error is None


def test_wrong_cube_count_fails_with_a_retryable_message():
    res = run_script("o = point(0, 0)\ns = stack(o, heights=[[1, 2]])\nassert_cube_count(s, 5)\ndraw(s)\n",
                     timeout_seconds=60, features=SOLIDS)
    assert res.error and "3 cubes" in res.error and "expected 5" in res.error
    assert res.retry_message and "3 cubes" in res.retry_message


@pytest.mark.parametrize("kw", [
    {"heights": [[1, 2], [3, 0]]},
    {"heights": None, "cubes": [[0, 0, 0], [0, 1, 0], [2, 0, 0], [1, 2, 0], [1, 0, 1]]},  # floating cube
])
def test_top_handle_vertices_equal_the_compiled_top_face_vertices_in_order(kw):
    from geometry_diagrams.ir.stack import synthesize_top_faces
    from geometry_diagrams.ir.to_sympy import compile_defs

    with new_builder_context() as b:
        s = api.stack(api.point(0, 0), **kw)
        handles = {(x, z): s.top(x, z) for x, z in s._tops}
        d = b.build()
    stmt = next(x for x in d.define if isinstance(x, ir.BlockStack))
    sym = compile_defs(d)
    polys = {p.id: p for p in synthesize_top_faces(stmt)}
    assert set(polys) == {h.id for h in handles.values()}
    for h in handles.values():
        assert [v.id for v in h.vertices] == list(polys[h.id].points)
        compiled = [(float(p.x), float(p.y)) for p in sym[h.id].vertices]
        assert [(v.x, v.y) for v in h.vertices] == pytest.approx(compiled)
