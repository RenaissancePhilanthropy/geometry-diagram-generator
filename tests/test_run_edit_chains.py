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
