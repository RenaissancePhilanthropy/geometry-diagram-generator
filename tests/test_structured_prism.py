"""Structured-strategy surface for prisms (solids ticket 16): the prompt's prism
guidance (gated by the solids group, byte-identical with it off), the example
IR the guidance is derived from, and the structured path end to end."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz
from geometry_diagrams.strategies import instructions_structured as ins
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline
from geometry_diagrams.strategies.structured import (
    MAX_RETRIES, StructureStrategy, dispatch_query,
)

SOLIDS = frozenset({"solids"})
_PRE = json.loads((Path(__file__).parent / "structured_prompt_pre_solids.json").read_text())


# --- gated prompt ---------------------------------------------------------------

def test_solids_off_prompt_is_byte_identical_to_pre_solids():
    assert ins.STRUCTURED_STRATEGY_IR_INSTRUCTIONS == _PRE["system"]
    assert ins.build_structured_instructions() == _PRE["system"]
    assert ins.build_structured_instructions(frozenset()) == _PRE["system"]
    assert "prism" not in _PRE["system"]


def test_solids_on_prompt_extends_the_base_with_the_guidance():
    on = ins.build_structured_instructions(SOLIDS)
    assert on.startswith(_PRE["system"]) and on != _PRE["system"]
    for needle in (
        "rectangular_prism", "unit_cubes", "vertex_names", "depth_scale", "isometric",
        "{id}_v{abc}", "{id}_e_{abc}_{abc}", "_front", "_back", "_left", "_right", "_top", "_bottom",
        "volume_equals", "true_length_equals", "distance_equals", "label_free_text",
        "centroid_of", "math mode", "10 x 6", "base area", "rgb(", "#rrggbb",
    ):
        assert needle in on, needle


def test_prompt_states_fill_style_and_label_field_lists():
    on = ins.build_structured_instructions(SOLIDS)
    assert "`fill` takes its color from its `style`" in on
    assert "`styles`" in on
    assert "`label_free_text`: `text` and exactly one of `at` ([x, y]) or `centroid_of`" in on
    assert "`label_segment`: `seg`, `text`, optional `pos`" in on
    # the field names it documents are real IR fields
    assert {"text", "at", "centroid_of"} <= set(ir.LabelFreeText.model_fields)
    assert {"seg", "text", "pos"} <= set(ir.LabelSegment.model_fields)
    assert "style" in ir.Fill.model_fields


def test_prompt_example_is_embedded_verbatim():
    on = ins.build_structured_instructions(SOLIDS)
    assert json.dumps(ins.PRISM_EXAMPLE_IR, indent=2) in on


def test_generate_node_sends_the_gated_prompt():
    llm, structured = _mock_llm([_raw(_example())])
    for feats, expected in ((frozenset(), _PRE["system"]), (SOLIDS, ins.build_structured_instructions(SOLIDS))):
        structured.ainvoke.reset_mock()
        structured.ainvoke.side_effect = [_raw(_example())]
        with patch("geometry_diagrams.strategies.structured.get_chat_model", return_value=llm):
            coro = StructureStrategy(features=feats).run("a box", renderer=SVGRenderer())
            if feats:
                asyncio.run(coro)  # solids on: any error must fail the test
            else:
                with pytest.raises(RuntimeError):  # disabled prism is rejected
                    asyncio.run(coro)
        system = structured.ainvoke.call_args_list[0].args[0][0]
        text = system.content if isinstance(system.content, str) else "".join(
            b.get("text", "") for b in system.content)
        assert text == expected


# --- the example ------------------------------------------------------------------

def _example() -> ir.DiagramIR:
    return ir.DiagramIR.model_validate(ins.PRISM_EXAMPLE_IR)


def test_example_uses_a_prism_fill_edge_label_and_volume_check():
    d = _example()
    assert any(isinstance(s, ir.RectangularPrism) for s in d.define)
    assert any(isinstance(r, ir.Fill) for r in d.render)
    prism = next(s for s in d.define if isinstance(s, ir.RectangularPrism))
    assert (prism.length_label, prism.width_label, prism.height_label) == ("4 ft", "3 ft", "2 ft")
    assert not any(isinstance(r, ir.LabelSegment) for r in d.render)  # fields, not manual labels
    assert any(isinstance(c, ir.VolumeEquals) for c in d.checks)
    assert any(isinstance(c, ir.TrueLengthEquals) for c in d.checks)


def test_example_runs_through_the_shared_pipeline_with_no_warnings():
    res = asyncio.run(run_ir_pipeline(_example(), SVGRenderer()))
    assert res.warnings == []
    assert "<svg" in res.svg


def test_example_colors_work_in_tikz_too():
    d = _example()
    tikz = ir_to_tikz(d, compile_defs(d))
    for name, rgb in (("gdrgbbcd6ee", "188,214,238"), ("gdrgb96bee6", "150,190,230"),
                      ("gdrgbdbe9f6", "219,233,246")):
        assert f"\\definecolor{{{name}}}{{RGB}}{{{rgb}}}" in tikz
    assert "\\tkzFillPolygon[fill=gdrgbbcd6ee,opacity=1.0](P_v000,P_v100,P_v110,P_v010)" in tikz


# --- end to end through the structured strategy -----------------------------------

def _raw(diagram) -> dict:
    raw = MagicMock()
    raw.response_metadata = {"usage": {"input_tokens": 1, "output_tokens": 1}}
    return {"raw": raw, "parsed": diagram, "parsing_error": None}


def _mock_llm(responses):
    structured = MagicMock()
    structured.ainvoke = AsyncMock(side_effect=responses)
    llm = MagicMock()
    llm.with_structured_output = MagicMock(return_value=structured)
    return llm, structured


@pytest.mark.asyncio
async def test_structured_end_to_end_renders_the_example_with_solids_on():
    llm, _ = _mock_llm([_raw(_example())])
    with patch("geometry_diagrams.strategies.structured.get_chat_model", return_value=llm):
        res = await StructureStrategy(features=SOLIDS).run("a 4x3x2 box", renderer=SVGRenderer())
    assert res.retries == 0 and res.warnings == [] and "<svg" in res.svg
    assert "P_v111" in res.sym_table


@pytest.mark.asyncio
async def test_structured_rejects_the_example_with_solids_off_with_retryable_error():
    llm, structured = _mock_llm([_raw(_example())] * MAX_RETRIES)
    with patch("geometry_diagrams.strategies.structured.get_chat_model", return_value=llm):
        with pytest.raises(RuntimeError, match="solids"):
            await StructureStrategy().run("a box", renderer=SVGRenderer())
    retry_prompt = structured.ainvoke.call_args_list[1].args[0][1].content
    assert "rectangular_prism" in retry_prompt and "GEOMETRY_FEATURES" in retry_prompt


def test_structured_query_tool_answers_prism_and_true_length_queries():
    sym = compile_defs(_example())
    prism = json.loads(dispatch_query(sym, "prism", {"prism": "P"}))
    assert prism["volume"] == pytest.approx(24)
    length = json.loads(dispatch_query(sym, "length", {"segment": "s_diag"}))
    assert length["true_length"] == pytest.approx(5)
