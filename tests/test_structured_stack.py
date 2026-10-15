"""Structured-strategy surface for block stacks (block-stacks ticket 08): the
gated prompt guidance, the example IR it embeds, and the structured path end to
end with solids on (renders) and off (retryable rejection)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.stack import Stack
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.strategies import instructions_structured as ins
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline
from geometry_diagrams.strategies.structured import MAX_RETRIES, StructureStrategy

SOLIDS = frozenset({"solids"})
_PRE = json.loads((Path(__file__).parent / "structured_prompt_pre_solids.json").read_text())


# --- gated prompt ---------------------------------------------------------------

def test_solids_off_prompt_has_no_stack_text():
    assert ins.build_structured_instructions() == _PRE["system"]
    assert "block_stack" not in _PRE["system"] and "cube_count_equals" not in _PRE["system"]


def test_solids_on_prompt_describes_block_stack():
    on = ins.build_structured_instructions(SOLIDS)
    assert on.startswith(_PRE["system"])
    for needle in (
        "block_stack", "heights[z][x]", "rows front to back, columns left to right",
        "`cubes`", "[x, y, z]", "y = HEIGHT", "z = DEPTH", "not a height map",
        "[[0,0,0],[0,1,0],[2,0,0],[2,1,0],[1,1,0]]", "bridge cube",
        "Never draw individual cubes by hand", "at most 400 cubes", "at most 20 cells",
        "cube_count_equals", '"view": "isometric"', '{"kind": "draw", "obj": "<stack id>"}',
        "front_color", "side_color", "top_color", "is an error", "{id}_top_{x}_{z}",
    ):
        assert needle in on, needle
    # every field the guidance names is a real IR field
    assert {"heights", "cubes", "view", "front_color", "side_color", "top_color"} <= set(
        ir.BlockStack.model_fields)
    assert {"stack", "expected"} <= set(ir.CubeCountEquals.model_fields)


def test_prompt_embeds_the_example_verbatim():
    on = ins.build_structured_instructions(SOLIDS)
    assert json.dumps(ins.STACK_EXAMPLE_IR, indent=2) in on


# --- the example ------------------------------------------------------------------

def _example() -> ir.DiagramIR:
    return ir.DiagramIR.model_validate(ins.STACK_EXAMPLE_IR)


def test_example_cube_count_matches_the_real_count():
    d = _example()
    stack = next(s for s in d.define if isinstance(s, ir.BlockStack))
    check = next(c for c in d.checks if isinstance(c, ir.CubeCountEquals))
    sym = compile_defs(d)
    assert isinstance(sym[stack.id], Stack)
    assert check.stack == stack.id and check.expected == sym[stack.id].cube_count


def test_example_runs_through_the_shared_pipeline_with_no_warnings():
    res = asyncio.run(run_ir_pipeline(_example(), SVGRenderer()))
    assert res.warnings == [] and "<svg" in res.svg


def test_overhang_example_is_not_a_height_map():
    d = ir.DiagramIR.model_validate({
        "canvas": {"xmin": -1, "xmax": 6, "ymin": -1, "ymax": 4},
        "define": [{"kind": "point_fixed", "id": "O", "x": 0, "y": 0},
                   {"kind": "block_stack", "id": "S", "origin": "O",
                    "cubes": [[0, 0, 0], [0, 1, 0], [2, 0, 0], [2, 1, 0], [1, 1, 0]]}],
        "checks": [], "render": [{"kind": "draw", "obj": "S"}]})
    res = asyncio.run(run_ir_pipeline(d, SVGRenderer()))
    assert any("height map" in w for w in res.warnings)


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
async def test_structured_end_to_end_renders_a_stack_with_solids_on():
    llm, _ = _mock_llm([_raw(_example())])
    with patch("geometry_diagrams.strategies.structured.get_chat_model", return_value=llm):
        res = await StructureStrategy(features=SOLIDS).run("a block stack", renderer=SVGRenderer())
    assert res.retries == 0 and res.warnings == [] and "<svg" in res.svg


@pytest.mark.asyncio
async def test_structured_rejects_a_stack_with_solids_off_with_retryable_error():
    llm, structured = _mock_llm([_raw(_example())] * MAX_RETRIES)
    with patch("geometry_diagrams.strategies.structured.get_chat_model", return_value=llm):
        with pytest.raises(RuntimeError, match="solids"):
            await StructureStrategy().run("a block stack", renderer=SVGRenderer())
    assert structured.ainvoke.await_count == MAX_RETRIES
    retry_prompt = structured.ainvoke.call_args_list[1].args[0][1].content
    assert "block_stack" in retry_prompt and "GEOMETRY_FEATURES" in retry_prompt


@pytest.mark.asyncio
async def test_cube_count_check_without_a_stack_is_a_retryable_failure():
    bad = ir.DiagramIR.model_validate({
        "canvas": {"xmin": 0, "xmax": 4, "ymin": 0, "ymax": 4},
        "define": [{"kind": "point_fixed", "id": "O", "x": 0, "y": 0}],
        "checks": [{"kind": "cube_count_equals", "stack": "S", "expected": 3}],
        "render": []})
    llm, structured = _mock_llm([_raw(bad)] * MAX_RETRIES)
    with patch("geometry_diagrams.strategies.structured.get_chat_model", return_value=llm):
        with pytest.raises(RuntimeError):
            await StructureStrategy(features=SOLIDS).run("count", renderer=SVGRenderer())
    assert structured.ainvoke.await_count == MAX_RETRIES
    assert "S" in structured.ainvoke.call_args_list[1].args[0][1].content
