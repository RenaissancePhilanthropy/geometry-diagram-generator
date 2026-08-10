"""Tests for evals/run_edit_chains.py's per-chain-run procedure."""
from __future__ import annotations

import json

import pytest

from evals.run_edit_chains import run_chain


@pytest.mark.asyncio
async def test_run_chain_records_a_successful_turn(monkeypatch):
    from geometry_diagrams.strategies.python_full import PythonFullStrategy
    from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
    from geometry_diagrams.ir.ir import DiagramIR

    async def fake_run(self, prompt, model="test", renderer=None):
        return StructuredRunResult(
            diagram_ir=DiagramIR(define=[], render=[]),
            tikz="", svg="<svg></svg>",
            sym_table={"__pydsl_pt_1": (0.0, 0.0)}, sym_full={},
            script="a = point(0, 0)\ndraw_points(a)\n",
            variable_ids={"a": "__pydsl_pt_1"},
            entity_manifest={"named": [], "anonymous": []},
            retries=0,
        )

    monkeypatch.setattr(PythonFullStrategy, "run", fake_run)

    chain = {"id": "chain-1", "turns": [{"request": "draw a point", "expected_properties": []}]}
    records = await run_chain(chain, "test-model", "full_rewrite", repeat_index=1, renderer=None, turn_timeout=5.0)

    assert len(records) == 1
    r = records[0]
    assert r["chain_id"] == "chain-1"
    assert r["turn_index"] == 1
    assert r["success"] is True
    assert r["error"] is None
    assert r["retries"] == 0
    assert r["prior_failure_count"] == 0
    assert r["script_chars_before"] == 0
    assert r["script_chars_after"] == len("a = point(0, 0)\ndraw_points(a)\n")


@pytest.mark.asyncio
async def test_run_chain_continues_past_a_failure_and_tracks_prior_failure_count(monkeypatch):
    from geometry_diagrams.strategies.python_full import PythonFullStrategy

    async def failing_run(self, prompt, model="test", renderer=None):
        raise RuntimeError("PythonFullStrategy failed after 3 attempts. Last error: boom")

    monkeypatch.setattr(PythonFullStrategy, "run", failing_run)

    chain = {
        "id": "chain-1",
        "turns": [
            {"request": "draw a point", "expected_properties": []},
            {"request": "move it up", "expected_properties": []},
        ],
    }
    records = await run_chain(chain, "test-model", "full_rewrite", repeat_index=1, renderer=None, turn_timeout=5.0)

    assert len(records) == 2
    assert records[0]["success"] is False
    assert records[0]["error_category"] == "exhausted_retries"
    assert records[0]["prior_failure_count"] == 0
    assert records[1]["success"] is False
    assert records[1]["prior_failure_count"] == 1


@pytest.mark.asyncio
async def test_run_chain_runs_property_checks_on_success(monkeypatch):
    from geometry_diagrams.strategies.python_full import PythonFullStrategy
    from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
    from geometry_diagrams.ir.ir import DiagramIR

    async def fake_run(self, prompt, model="test", renderer=None):
        return StructuredRunResult(
            diagram_ir=DiagramIR(define=[], render=[]),
            tikz="", svg="<svg></svg>",
            sym_table={
                "__pydsl_pt_1": (0.0, 0.0),
                "__pydsl_pt_2": (4.0, 0.0),
                "__pydsl_pt_3": (0.0, 3.0),
            },
            sym_full={},
            script="A = point(0, 0)\nB = point(4, 0)\nC = point(0, 3)\ndraw_points(A, B, C)\n",
            variable_ids={"A": "__pydsl_pt_1", "B": "__pydsl_pt_2", "C": "__pydsl_pt_3"},
            entity_manifest={"named": [], "anonymous": []},
            retries=0,
        )

    monkeypatch.setattr(PythonFullStrategy, "run", fake_run)

    chain = {
        "id": "chain-1",
        "turns": [{
            "request": "draw a right triangle A, B, C",
            "expected_properties": [
                {"name": "right angle at A", "type": "right_angle", "args": ["B", "A", "C"]},
            ],
        }],
    }
    records = await run_chain(chain, "test-model", "full_rewrite", repeat_index=1, renderer=None, turn_timeout=5.0)

    assert records[0]["sympy_property_checks"][0]["passed"] is True


@pytest.mark.asyncio
async def test_run_chain_threads_hash_algorithm_into_build_agent(monkeypatch):
    from geometry_diagrams.strategies import python_full as pf_module
    from evals.run_edit_chains import run_chain

    captured_kwargs = {}
    real_build_agent = pf_module.PythonFullStrategy.build_agent

    def spying_build_agent(self, **kwargs):
        captured_kwargs.update(kwargs)
        return real_build_agent(self, **kwargs)

    monkeypatch.setattr(pf_module.PythonFullStrategy, "build_agent", spying_build_agent)

    async def fake_run(self, prompt, model="test", renderer=None):
        from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
        from geometry_diagrams.ir.ir import DiagramIR
        return StructuredRunResult(
            diagram_ir=DiagramIR(define=[], render=[]),
            tikz="", svg="<svg></svg>",
            sym_table={}, sym_full={},
            script="a = point(0, 0)\n",
            variable_ids={"a": "p1"},
            entity_manifest={"named": [], "anonymous": []},
            retries=0,
        )
    monkeypatch.setattr(pf_module.PythonFullStrategy, "run", fake_run)

    chain = {"id": "chain-1", "turns": [{"request": "draw a point", "expected_properties": []}]}
    await run_chain(chain, "test-model", "hashline", repeat_index=1, renderer=None, turn_timeout=5.0, hash_algorithm="xxhash")

    assert captured_kwargs.get("hash_algorithm") == "xxhash"
    assert captured_kwargs.get("edit_generation_mode") == "hashline"


@pytest.mark.asyncio
async def test_run_chain_end_to_end_against_patch_mode(monkeypatch):
    """Exercises the actual build_agent()/render_diagram wiring (not a
    monkeypatched .run()) for both the create and patch-mode edit paths,
    confirming the harness's use of graph/closure introspection and the
    tool's real return shape stay correct as python_full.py evolves."""
    from geometry_diagrams.strategies import python_full as pf_module
    from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
    from geometry_diagrams.ir.ir import DiagramIR

    call_count = 0

    async def fake_run(self, prompt, model="test", renderer=None):
        nonlocal call_count
        call_count += 1
        return StructuredRunResult(
            diagram_ir=DiagramIR(define=[], render=[]),
            tikz="", svg=f"<svg>{call_count}</svg>",
            sym_table={"__pydsl_pt_1": (0.0, 0.0)}, sym_full={},
            script="a = point(0, 0)\ndraw_points(a)\n",
            variable_ids={"a": "__pydsl_pt_1"},
            entity_manifest={
                "named": [{"name": "a", "id": "__pydsl_pt_1", "type": "point_fixed", "approx_position": [0.0, 0.0]}],
                "anonymous": [],
            },
            retries=0,
        )

    async def fake_generate_patch(prompt, model, enable_cache=False):
        return "@@ -1,2 +1,2 @@\n-a = point(0, 0)\n+a = point(1, 1)\n draw_points(a)\n"

    monkeypatch.setattr(pf_module.PythonFullStrategy, "run", fake_run)
    monkeypatch.setattr(pf_module, "_generate_patch", fake_generate_patch)

    chain = {
        "id": "chain-e2e",
        "turns": [
            {"request": "draw a point", "expected_properties": []},
            {"request": "move it", "expected_properties": []},
        ],
    }

    from evals.run_edit_chains import run_chain

    records = await run_chain(chain, "test-model", "patch", repeat_index=1, renderer=None, turn_timeout=5.0)

    assert len(records) == 2
    assert records[0]["success"] is True
    assert records[1]["success"] is True
    # patch mode's _generate_patch is a single, unretried call — retries must be 0.
    assert records[1]["retries"] == 0
    assert records[1]["script_chars_before"] == len("a = point(0, 0)\ndraw_points(a)\n")
