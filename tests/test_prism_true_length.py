"""Prism true 3D length, volume and true-length checks (solids ticket 11).

Authored DiagramIR (a point, a prism, segments, checks) through the shared
pipeline: the ``length`` query on a segment joining two corners of one prism
also answers the true 3D length, whoever created the segment; the new
``volume_equals`` / ``true_length_equals`` checks are near-exact by default;
a generic 2D length check on such a segment keeps its 2D meaning but adds a
projection warning naming ``true_length_equals``.
"""
from __future__ import annotations

import asyncio
import json
import math
import re
from pathlib import Path

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.checks import run_checks
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.pydsl import api
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context
from geometry_diagrams.pydsl.handles import Point
from geometry_diagrams.strategies.ir_pipeline import PipelineError, run_ir_pipeline
from geometry_diagrams.strategies.structured import dispatch_query

L, W, H = 4, 3, 2  # default prism: length, width (depth), height


def _diagram(*extra, checks=(), prism=None) -> ir.DiagramIR:
    return ir.DiagramIR(
        define=[
            ir.PointFixed(id="O", x=1, y=2),
            prism or ir.RectangularPrism(id="P", origin="O", length=L, width=W, height=H),
            *extra,
        ],
        render=[ir.Draw(obj="P")],
        checks=list(checks),
    )


def _length(sym, seg_id) -> dict:
    return json.loads(dispatch_query(sym, "length", {"segment": seg_id}))


def _run(diagram):
    return asyncio.run(run_ir_pipeline(diagram, SVGRenderer()))


# --- true length through the length query ------------------------------------

@pytest.mark.parametrize("a, b, expected", [
    ("P_v000", "P_v100", L),                                  # edge: length
    ("P_v000", "P_v001", W),                                  # edge: depth
    ("P_v000", "P_v010", H),                                  # edge: height
    ("P_v000", "P_v110", math.sqrt(L**2 + H**2)),             # front face diagonal
    ("P_v010", "P_v111", math.sqrt(L**2 + W**2)),             # top face diagonal
    ("P_v101", "P_v011", math.sqrt(L**2 + H**2)),             # back face diagonal
    ("P_v000", "P_v111", math.sqrt(L**2 + W**2 + H**2)),      # space diagonal
    ("P_v111", "P_v000", math.sqrt(L**2 + W**2 + H**2)),      # endpoint order irrelevant
])
def test_hand_authored_segment_with_any_id_answers_true_length(a, b, expected):
    sym = compile_defs(_diagram(ir.Segment(id="my_seg", a=a, b=b)))
    out = _length(sym, "my_seg")
    assert out["true_length"] == pytest.approx(expected, rel=1e-12)
    pa, pb = sym[a], sym[b]
    assert out["length"] == pytest.approx(float(pa.distance(pb)), rel=1e-12)  # still the 2D length


def test_depth_edge_projects_shorter_than_its_true_length():
    out = _length(compile_defs(_diagram()), "P_e_000_001")
    assert out["true_length"] == pytest.approx(W)
    assert out["length"] == pytest.approx(W / 2)  # oblique default draws depth at half scale


@pytest.mark.parametrize("edge, expected", [
    ("P_e_000_100", L), ("P_e_000_001", W), ("P_e_000_010", H),
    ("P_e_011_111", L), ("P_e_110_111", W), ("P_e_101_111", H),
])
def test_prisms_own_derived_edges_answer_true_length(edge, expected):
    out = _length(compile_defs(_diagram()), edge)
    assert out["true_length"] == pytest.approx(expected, rel=1e-12)


def test_renamed_corners_answer_true_length():
    prism = ir.RectangularPrism(
        id="P", origin="O", length=L, width=W, height=H, vertex_names=list("ABCDEFGH"),
    )
    # product order: A=000 B=001 C=010 D=011 E=100 F=101 G=110 H=111
    sym = compile_defs(_diagram(ir.Segment(id="AH", a="A", b="H"), prism=prism))
    assert _length(sym, "AH")["true_length"] == pytest.approx(math.sqrt(L**2 + W**2 + H**2))
    assert _length(sym, "P_e_000_001")["true_length"] == pytest.approx(W)


def test_segment_not_joining_two_corners_of_one_prism_has_no_true_length():
    d = _diagram(
        ir.PointFixed(id="X", x=20, y=20),
        ir.Segment(id="corner_to_point", a="P_v000", b="X"),
        ir.PointFixed(id="Y", x=30, y=20),
        ir.Segment(id="plain", a="X", b="Y"),
    )
    sym = compile_defs(d)
    assert set(_length(sym, "corner_to_point")) == {"length"}
    assert _length(sym, "plain") == {"length": pytest.approx(10.0)}


def test_segment_joining_corners_of_two_different_prisms_has_no_true_length():
    d = _diagram(
        ir.PointFixed(id="O2", x=20, y=0),
        ir.RectangularPrism(id="Q", origin="O2", length=1, width=1, height=1),
        ir.Segment(id="across", a="P_v111", b="Q_v000"),
    )
    assert set(_length(compile_defs(d), "across")) == {"length"}


def test_corners_projecting_to_the_same_2d_point_do_not_confuse_true_length():
    # Oblique default depth vector is width * (sqrt2/4, sqrt2/4). With
    # length = height = sqrt(2)/4 * width, corner 110 (at (L, H)) and corner
    # 001 (at the depth vector) project to the same 2D point.
    prism = ir.RectangularPrism(id="P", origin="O", length="sqrt(2)", width=4, height="sqrt(2)")
    d = _diagram(
        ir.Segment(id="S_from_110", a="P_v110", b="P_v100"),   # height edge
        ir.Segment(id="S_from_001", a="P_v001", b="P_v100"),   # bottom face diagonal
        prism=prism,
    )
    sym = compile_defs(d)
    assert (float(sym["P_v110"].x), float(sym["P_v110"].y)) == pytest.approx(
        (float(sym["P_v001"].x), float(sym["P_v001"].y)))
    a, b = _length(sym, "S_from_110"), _length(sym, "S_from_001")
    assert a["length"] == pytest.approx(b["length"])            # same 2D segment
    assert a["true_length"] == pytest.approx(math.sqrt(2))      # H
    assert b["true_length"] == pytest.approx(math.sqrt(2 + 16))  # sqrt(L^2 + W^2)
    # The prism's own edges at those corners agree.
    assert _length(sym, "P_e_100_110")["true_length"] == pytest.approx(math.sqrt(2))
    assert _length(sym, "P_e_000_001")["true_length"] == pytest.approx(4)


def test_pipeline_result_answers_true_length():
    result = _run(_diagram(ir.Segment(id="diag", a="P_v000", b="P_v111")))
    assert _length(result.sym_full, "diag")["true_length"] == pytest.approx(math.sqrt(29))


# --- segments made by the builders ---------------------------------------------

def test_python_builder_segment_helper_answers_true_length_mid_script_and_after():
    with new_builder_context():
        b = get_builder()
        b._add(ir.PointFixed(id="O", x=1, y=2))
        b._add(ir.RectangularPrism(id="P", origin="O", length=L, width=W, height=H))
        seg = api.segment(Point(id="P_v000", _builder=b), Point(id="P_v111", _builder=b))
        b._resolve_point("P_v000")  # incremental compile up to here
        mid_script = _length(b._sym, seg.id)
        diagram = b.build()
    assert not seg.id.startswith("P_e_")  # not the prism's own id
    assert mid_script["true_length"] == pytest.approx(math.sqrt(29))
    assert _length(compile_defs(diagram), seg.id)["true_length"] == pytest.approx(math.sqrt(29))


def test_python_builder_incremental_table_indexes_derived_edges():
    with new_builder_context():
        b = get_builder()
        b._add(ir.PointFixed(id="O", x=1, y=2))
        b._add(ir.RectangularPrism(id="P", origin="O", length=L, width=W, height=H))
        b._resolve_point("P_v111")
        assert _length(b._sym, "P_e_000_001")["true_length"] == pytest.approx(W)


def test_recipe_lowering_segment_helper_answers_true_length():
    from geometry_diagrams.recipe.lower import _Lowerer

    lowerer = _Lowerer()
    seg_id = lowerer._ensure_segment("P_v000", "P_v011")
    seg_defs = [d for d in lowerer._defs if getattr(d, "id", None) == seg_id]
    sym = compile_defs(_diagram(*seg_defs))
    assert _length(sym, seg_id)["true_length"] == pytest.approx(math.sqrt(W**2 + H**2))


# --- volume_equals / true_length_equals -----------------------------------------

def test_volume_equals_passes_for_the_right_volume():
    result = _run(_diagram(checks=[ir.VolumeEquals(prism="P", expected=24)]))
    assert result.warnings == []


def test_volume_equals_fails_for_an_off_by_one_volume_on_literal_dimensions():
    # 10 x 10 x 3 = 300; the old 0.5% default would have passed 299.
    prism = ir.RectangularPrism(id="P", origin="O", length=10, width=10, height=3)
    with pytest.raises(PipelineError) as exc:
        _run(_diagram(prism=prism, checks=[ir.VolumeEquals(prism="P", expected=299)]))
    assert "Prism 'P' volume 300 != expected 299" in str(exc.value)


def test_explicit_tolerance_overrides_the_near_exact_default():
    prism = ir.RectangularPrism(id="P", origin="O", length=10, width=10, height=3)
    _run(_diagram(prism=prism, checks=[ir.VolumeEquals(prism="P", expected=299, tol=0.01)]))
    sym = compile_defs(_diagram())
    [r] = run_checks([ir.TrueLengthEquals(seg="P_e_000_001", expected=3.01, tol=0.01)], sym)
    assert r.passed


def test_true_length_equals_is_near_exact_by_default():
    sym = compile_defs(_diagram(ir.Segment(id="diag", a="P_v000", b="P_v111")))
    ok, near, off = run_checks([
        ir.TrueLengthEquals(seg="diag", expected=math.sqrt(29)),
        ir.TrueLengthEquals(seg="diag", expected=math.sqrt(29) * (1 + 1e-6)),
        ir.TrueLengthEquals(seg="P_e_000_001", expected=1.5),  # the projected length
    ], sym)
    assert ok.passed and ok.message == ""
    assert not near.passed
    assert not off.passed
    assert off.message == "Segment 'P_e_000_001' true length 3 != expected 1.5"


def test_true_length_equals_on_a_segment_not_joining_prism_corners_says_why():
    d = _diagram(ir.PointFixed(id="X", x=20, y=20), ir.Segment(id="s", a="P_v000", b="X"))
    [r] = run_checks([ir.TrueLengthEquals(seg="s", expected=1)], compile_defs(d))
    assert not r.passed
    assert "'s'" in r.message and "two corners of one prism" in r.message
    assert "distance_equals" in r.message


def test_volume_equals_on_a_non_prism_says_why():
    [r] = run_checks([ir.VolumeEquals(prism="O", expected=1)], compile_defs(_diagram()))
    assert not r.passed and "'O'" in r.message and "not a prism" in r.message


def test_new_check_failure_carries_its_source_tag():
    [r] = run_checks(
        [ir.VolumeEquals(prism="P", expected=25, source="explicit check: volume(P)")],
        compile_defs(_diagram()),
    )
    assert r.message == "[explicit check: volume(P)] Prism 'P' volume 24 != expected 25"


def test_other_checks_keep_the_loose_default_tolerance():
    d = ir.DiagramIR(define=[
        ir.PointFixed(id="A", x=0, y=0), ir.PointFixed(id="B", x=300, y=0),
        ir.Segment(id="AB", a="A", b="B"),
    ])
    [r] = run_checks([ir.DistanceEquals(seg="AB", expected=299)], compile_defs(d))
    assert r.passed


def test_new_checks_round_trip_through_the_check_union():
    d = _diagram(checks=[
        ir.VolumeEquals(prism="P", expected=24),
        ir.TrueLengthEquals(seg="P_e_000_100", expected=4, tol=1e-6),
    ])
    rebuilt = ir.DiagramIR.model_validate(json.loads(d.model_dump_json()))
    assert isinstance(rebuilt.checks[0], ir.VolumeEquals)
    assert isinstance(rebuilt.checks[1], ir.TrueLengthEquals) and rebuilt.checks[1].tol == 1e-6


# --- projection warning on generic 2D length checks -----------------------------

def test_distance_equals_on_a_depth_edge_still_fails_and_warns():
    with pytest.raises(PipelineError) as exc:
        _run(_diagram(checks=[ir.DistanceEquals(seg="P_e_000_001", expected=W)]))
    assert "P_e_000_001" in str(exc.value)  # the 2D failure, as before
    [w] = exc.value.warnings
    assert "P_e_000_001" in w and "projected" in w and "true_length_equals" in w


def test_passing_2d_check_on_a_prism_segment_warns_without_failing():
    result = _run(_diagram(checks=[ir.DistanceEquals(seg="P_e_000_001", expected=W / 2)]))
    [w] = result.warnings
    assert "true_length_equals" in w


def test_equal_length_and_ratio_equal_on_prism_segments_warn():
    sym = compile_defs(_diagram(ir.Segment(id="d", a="P_v000", b="P_v111")))
    warnings: list[str] = []
    results = run_checks([
        ir.EqualLength(segs=["P_e_000_100", "P_e_000_001"]),
        ir.RatioEqual(s1="P_e_000_100", s2="P_e_000_010", s3="P_e_000_100", s4="P_e_000_010"),
    ], sym, warnings=warnings)
    assert [r.passed for r in results] == [False, True]  # 2D meaning unchanged
    assert len(warnings) == 2 and all("true_length_equals" in w for w in warnings)
    assert "equal_length" in warnings[0] and "ratio_equal" in warnings[1]


def test_no_warning_for_length_checks_on_ordinary_segments_or_without_a_collector():
    d = _diagram(
        ir.PointFixed(id="X", x=20, y=20), ir.PointFixed(id="Y", x=30, y=20),
        ir.Segment(id="XY", a="X", b="Y"),
        checks=[ir.DistanceEquals(seg="XY", expected=10)],
    )
    assert _run(d).warnings == []
    sym = compile_defs(_diagram())
    # The collector is optional: without one, results are unchanged.
    [r] = run_checks([ir.DistanceEquals(seg="P_e_000_001", expected=W)], sym)
    assert not r.passed


# --- query tool descriptions (gated on the solids feature group) ----------------
#
# With solids OFF (the default) every query-tool description is byte-identical
# to its pre-ticket-11 text (pinned in query_tool_descriptions_pre_solids.json,
# captured from commit 1aa49ab); with solids ON it lists the prism query and
# the true_length note. Queries answer either way: only the advertising is gated.

_PRE_SOLIDS = json.loads(
    (Path(__file__).parent / "query_tool_descriptions_pre_solids.json").read_text()
)
SOLIDS = frozenset({"solids"})


def _agent_query_tool_description(strategy_cls, features) -> str:
    graph = strategy_cls(features=features).build_agent(model="anthropic:claude-haiku-4-5-20251001")
    return graph.nodes["tools"].bound.tools_by_name["query_diagram"].description


def _assert_mentions_new_behavior(text: str) -> None:
    # the "prism" query type is listed (quoted, or as a table row)
    assert '"prism"' in text or re.search(r"^\s*prism\s+\{", text, re.MULTILINE)
    for word in ("volume", "base area", "surface area", "true_length"):
        assert word in text, word


def _strategy_classes():
    from geometry_diagrams.strategies.python_full import PythonFullStrategy
    from geometry_diagrams.strategies.recipe import RecipeStrategy
    from geometry_diagrams.strategies.structured import StructureStrategy

    return (StructureStrategy, RecipeStrategy, PythonFullStrategy)


def test_strategy_query_tools_are_unchanged_with_solids_off():
    for cls in _strategy_classes():
        assert _agent_query_tool_description(cls, frozenset()) == _PRE_SOLIDS[cls.__name__], cls


def test_strategy_query_tools_describe_the_new_behavior_with_solids_on():
    for cls in _strategy_classes():
        _assert_mentions_new_behavior(_agent_query_tool_description(cls, SOLIDS))


def test_facade_query_tool_description_is_gated():
    from geometry_diagrams import facade

    assert facade.query_diagram_description(frozenset()).strip() == _PRE_SOLIDS["facade"]
    _assert_mentions_new_behavior(facade.query_diagram_description(SOLIDS))
    # The module-level tool is built at import from the environment's set
    # (GEOMETRY_FEATURES), unset in the test environment.
    assert facade.query_diagram.description == _PRE_SOLIDS["facade"]


def test_eval_harness_query_tool_description_is_gated():
    from evals.run import _make_query_tool

    assert _make_query_tool({}, frozenset()).description == _PRE_SOLIDS["eval"]
    on = _make_query_tool({}, SOLIDS)
    _assert_mentions_new_behavior(on.description)


def test_gated_query_tool_still_answers_prism_queries_with_solids_off():
    from evals.run import _make_query_tool

    sym = compile_defs(_diagram())
    tool = _make_query_tool(sym, frozenset())
    out = json.loads(tool.invoke({"query_type": "length", "params": {"id": "P_e_000_001"}}))
    assert out["true_length"] == pytest.approx(W)
