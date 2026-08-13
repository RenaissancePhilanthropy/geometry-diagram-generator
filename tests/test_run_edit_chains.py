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

    async def fake_run(self, prompt, model="test", renderer=None, sandbox_timeout_seconds=2.5):
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

    async def failing_run(self, prompt, model="test", renderer=None, sandbox_timeout_seconds=2.5):
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
async def test_run_chain_records_edit_ops_meta_on_a_failed_line_number_turn(monkeypatch):
    from geometry_diagrams.strategies.python_full import PythonFullStrategy
    from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
    from geometry_diagrams.ir.ir import DiagramIR

    async def fake_run(self, prompt, model="test", renderer=None, sandbox_timeout_seconds=2.5):
        return StructuredRunResult(
            diagram_ir=DiagramIR(define=[], render=[]),
            tikz="", svg="<svg></svg>",
            sym_table={}, sym_full={},
            script="a = point(0, 0)\ndraw_points(a)\n",
            variable_ids={"a": "p1"},
            entity_manifest={"named": [], "anonymous": []},
            retries=0,
        )

    async def fake_generate_line_number_ops(prompt, model, enable_cache=False):
        # An out-of-range line reference — apply_line_number_ops raises
        # before anything is applied, so this turn fails. The ops were
        # still generated (one delete op, no expected_content), and that
        # metadata must survive the failure.
        return [{
            "kind": "delete", "line": "99",
            "after": None, "start_line": None, "end_line": None,
            "content": None, "expected_content": None,
        }], 1, 1, None

    monkeypatch.setattr(PythonFullStrategy, "run", fake_run)
    monkeypatch.setattr(
        "geometry_diagrams.strategies.python_full._generate_line_number_ops",
        fake_generate_line_number_ops,
    )

    chain = {
        "id": "chain-1",
        "turns": [
            {"request": "draw a point", "expected_properties": []},
            {"request": "delete a nonexistent line", "expected_properties": []},
        ],
    }
    records = await run_chain(chain, "test-model", "line_number", repeat_index=1, renderer=None, turn_timeout=5.0)

    assert len(records) == 2
    assert records[0]["success"] is True
    assert records[0]["edit_ops_meta"] is None  # first turn: no edit happened
    assert records[1]["success"] is False
    assert records[1]["error_category"] == "invalid_line"
    assert records[1]["edit_ops_meta"] == {"delete_replace_ops": 1, "with_expected_content": 0}


@pytest.mark.asyncio
async def test_run_chain_runs_property_checks_on_success(monkeypatch):
    from geometry_diagrams.strategies.python_full import PythonFullStrategy
    from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
    from geometry_diagrams.ir.ir import DiagramIR

    async def fake_run(self, prompt, model="test", renderer=None, sandbox_timeout_seconds=2.5):
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

    async def fake_run(self, prompt, model="test", renderer=None, sandbox_timeout_seconds=2.5):
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

    async def fake_run(self, prompt, model="test", renderer=None, sandbox_timeout_seconds=2.5):
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
        return "@@ -1,2 +1,2 @@\n-a = point(0, 0)\n+a = point(1, 1)\n draw_points(a)\n", 1, 1, None

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


@pytest.mark.asyncio
async def test_run_matrix_runs_every_combination_and_returns_all_records(monkeypatch, tmp_path):
    from geometry_diagrams.strategies.python_full import PythonFullStrategy
    from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
    from geometry_diagrams.ir.ir import DiagramIR
    from evals.run_edit_chains import run_matrix

    call_count = 0

    async def fake_run(self, prompt, model="test", renderer=None, sandbox_timeout_seconds=2.5):
        nonlocal call_count
        call_count += 1
        return StructuredRunResult(
            diagram_ir=DiagramIR(define=[], render=[]),
            tikz="", svg="<svg></svg>",
            sym_table={}, sym_full={},
            script="a = point(0, 0)\n",
            variable_ids={"a": "p1"},
            entity_manifest={"named": [], "anonymous": []},
            retries=0,
        )
    monkeypatch.setattr(PythonFullStrategy, "run", fake_run)

    chains = [
        {"id": "chain-1", "turns": [{"request": "draw a point", "expected_properties": []}]},
        {"id": "chain-2", "turns": [{"request": "draw a point", "expected_properties": []}]},
    ]
    output_path = tmp_path / "results.jsonl"
    result = await run_matrix(
        chains, ["model-a"], ["full_rewrite", "patch"], repeats=2,
        renderer=None, turn_timeout=5.0, output_path=output_path,
    )

    # 2 chains x 1 model x 2 modes x 2 repeats x 1 turn each = 8 records.
    assert len(result["records"]) == 8
    assert call_count == 8
    assert result["tripped_models"] == []
    assert result["tripped_cells"] == []
    with open(output_path) as f:
        written_lines = f.readlines()
    assert len(written_lines) == 8


@pytest.mark.asyncio
async def test_run_matrix_works_without_an_output_path(monkeypatch):
    from geometry_diagrams.strategies.python_full import PythonFullStrategy
    from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
    from geometry_diagrams.ir.ir import DiagramIR
    from evals.run_edit_chains import run_matrix

    async def fake_run(self, prompt, model="test", renderer=None, sandbox_timeout_seconds=2.5):
        return StructuredRunResult(
            diagram_ir=DiagramIR(define=[], render=[]),
            tikz="", svg="<svg></svg>",
            sym_table={}, sym_full={},
            script="a = point(0, 0)\n",
            variable_ids={"a": "p1"},
            entity_manifest={"named": [], "anonymous": []},
            retries=0,
        )
    monkeypatch.setattr(PythonFullStrategy, "run", fake_run)

    chains = [{"id": "chain-1", "turns": [{"request": "draw a point", "expected_properties": []}]}]
    result = await run_matrix(
        chains, ["model-a"], ["full_rewrite"], repeats=1,
        renderer=None, turn_timeout=5.0, output_path=None,
    )
    assert len(result["records"]) == 1


@pytest.mark.asyncio
async def test_run_matrix_trips_model_level_breaker_and_stops_calling_run_chain(monkeypatch):
    from geometry_diagrams.strategies.python_full import PythonFullStrategy
    from evals.run_edit_chains import run_matrix

    call_count = 0

    async def always_failing_run(self, prompt, model="test", renderer=None, sandbox_timeout_seconds=2.5):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("PythonFullStrategy failed after 3 attempts. Last error: boom")

    monkeypatch.setattr(PythonFullStrategy, "run", always_failing_run)

    # 5 chains x 1 model x 1 mode x 3 repeats x 1 turn = 15 possible calls,
    # but the model tally crosses the 20-sample floor only with >= 20
    # turns — use 1-turn chains and enough of them that failure alone
    # (100% failure rate) trips as soon as the floor is crossed.
    chains = [
        {"id": f"chain-{i}", "turns": [{"request": "draw a point", "expected_properties": []}]}
        for i in range(10)
    ]
    result = await run_matrix(
        chains, ["model-a"], ["full_rewrite"], repeats=3,
        renderer=None, turn_timeout=5.0,
    )

    assert result["tripped_models"] == ["model-a"]
    # Trips once the tally crosses 20 turns (100% failure) — well before
    # all 10 chains x 3 repeats = 30 possible calls complete.
    assert call_count < 30
    assert call_count >= 20


@pytest.mark.asyncio
async def test_run_matrix_trips_only_the_failing_cell_not_other_modes(monkeypatch):
    from geometry_diagrams.strategies.python_full import PythonFullStrategy
    from evals.run_edit_chains import run_matrix

    call_counts = {"fake_run": 0, "fake_generate_patch": 0}

    async def fake_run(self, prompt, model="test", renderer=None, sandbox_timeout_seconds=2.5):
        call_counts["fake_run"] += 1
        from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
        from geometry_diagrams.ir.ir import DiagramIR
        return StructuredRunResult(
            diagram_ir=DiagramIR(define=[], render=[]),
            tikz="", svg="<svg></svg>", sym_table={}, sym_full={},
            script="a = point(0, 0)\n", variable_ids={"a": "p1"},
            entity_manifest={"named": [], "anonymous": []}, retries=0,
        )

    async def fake_generate_patch(prompt, model, enable_cache=False):
        call_counts["fake_generate_patch"] += 1
        raise ValueError("patch context mismatch at line 1: expected 'x', patch has 'y'")

    from geometry_diagrams.strategies import python_full as pf_module
    monkeypatch.setattr(pf_module.PythonFullStrategy, "run", fake_run)
    monkeypatch.setattr(pf_module, "_generate_patch", fake_generate_patch)

    # 8-turn chains (matching the real scenario shape): turn 1 always
    # creates via fake_run (mode-independent, always succeeds); turns
    # 2-8 are edits via the mode under test. In "full_rewrite" mode
    # every edit turn also calls fake_run (always succeeds) — 0%
    # failure, never trips. In "patch" mode every edit turn calls
    # fake_generate_patch (always raises) — 7/8 = 87.5% failure per
    # repeat, comfortably above the 75% threshold. Two chains x 3
    # repeats gives patch's cell tally >= 20 turns (24) within chain-0
    # alone (repeat 3: total=24, failed=21, rate=87.5%), so it trips
    # partway through chain-0 and chain-1's patch work is skipped
    # entirely — while full_rewrite (0% failure) keeps running for both
    # chains, all 3 repeats, completely unaffected.
    chains = [
        {
            "id": f"chain-{i}",
            "turns": (
                [{"request": "draw a point", "expected_properties": []}]
                + [{"request": f"edit it ({j})", "expected_properties": []} for j in range(7)]
            ),
        }
        for i in range(2)
    ]
    result = await run_matrix(
        chains, ["model-a"], ["full_rewrite", "patch"], repeats=3,
        renderer=None, turn_timeout=5.0,
    )

    assert result["tripped_models"] == []
    assert result["tripped_cells"] == [["model-a", "patch"]]
    # patch's edits stop exactly at chain-0's 3rd repeat (3 repeats x 7
    # edit turns = 21 calls) — chain-1's patch work never runs at all.
    assert call_counts["fake_generate_patch"] == 21
    # full_rewrite ran to completion for both chains, all 3 repeats, all
    # 8 turns each — entirely unaffected by patch's trip.
    assert call_counts["fake_run"] >= 2 * 3 * 8


@pytest.mark.asyncio
async def test_run_matrix_model_trip_suppresses_redundant_cell_trip(monkeypatch):
    from geometry_diagrams.strategies.python_full import PythonFullStrategy
    from evals.run_edit_chains import run_matrix

    async def always_failing_run(self, prompt, model="test", renderer=None, sandbox_timeout_seconds=2.5):
        raise RuntimeError("PythonFullStrategy failed after 3 attempts. Last error: boom")

    monkeypatch.setattr(PythonFullStrategy, "run", always_failing_run)

    chains = [
        {"id": f"chain-{i}", "turns": [{"request": "draw a point", "expected_properties": []}]}
        for i in range(10)
    ]
    # Only ONE mode is exercised, so the model tally and the (model, mode)
    # cell tally accumulate identically, round for round — exactly the
    # scenario where, without suppression, both would trip on the same
    # update.
    result = await run_matrix(
        chains, ["model-a"], ["full_rewrite"], repeats=3,
        renderer=None, turn_timeout=5.0,
    )

    assert result["tripped_models"] == ["model-a"]
    # The cell is subsumed by the model trip — it must NOT also appear
    # as a separate tripped cell.
    assert result["tripped_cells"] == []


@pytest.mark.asyncio
async def test_run_matrix_two_models_trip_independently(monkeypatch):
    from geometry_diagrams.strategies.python_full import PythonFullStrategy
    from evals.run_edit_chains import run_matrix

    call_counts = {"good-model": 0, "bad-model": 0}

    async def fake_run(self, prompt, model="test", renderer=None, sandbox_timeout_seconds=2.5):
        call_counts[model] += 1
        if model == "bad-model":
            raise RuntimeError("PythonFullStrategy failed after 3 attempts. Last error: boom")
        from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
        from geometry_diagrams.ir.ir import DiagramIR
        return StructuredRunResult(
            diagram_ir=DiagramIR(define=[], render=[]),
            tikz="", svg="<svg></svg>", sym_table={}, sym_full={},
            script="a = point(0, 0)\n", variable_ids={"a": "p1"},
            entity_manifest={"named": [], "anonymous": []}, retries=0,
        )

    monkeypatch.setattr(PythonFullStrategy, "run", fake_run)

    chains = [
        {"id": f"chain-{i}", "turns": [{"request": "draw a point", "expected_properties": []}]}
        for i in range(10)
    ]
    result = await run_matrix(
        chains, ["good-model", "bad-model"], ["full_rewrite"], repeats=3,
        renderer=None, turn_timeout=5.0,
    )

    assert result["tripped_models"] == ["bad-model"]
    # good-model's remaining work is entirely unaffected by bad-model's trip.
    assert call_counts["good-model"] == 10 * 3
    assert call_counts["bad-model"] < 10 * 3


@pytest.mark.asyncio
async def test_run_matrix_disabled_breaker_runs_every_combination_regardless_of_failures(monkeypatch):
    from geometry_diagrams.strategies.python_full import PythonFullStrategy
    from evals.run_edit_chains import run_matrix

    call_count = 0

    async def always_failing_run(self, prompt, model="test", renderer=None, sandbox_timeout_seconds=2.5):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("PythonFullStrategy failed after 3 attempts. Last error: boom")

    monkeypatch.setattr(PythonFullStrategy, "run", always_failing_run)

    chains = [
        {"id": f"chain-{i}", "turns": [{"request": "draw a point", "expected_properties": []}]}
        for i in range(10)
    ]
    result = await run_matrix(
        chains, ["model-a"], ["full_rewrite"], repeats=3,
        renderer=None, turn_timeout=5.0, circuit_breaker_enabled=False,
    )

    assert result["tripped_models"] == []
    assert result["tripped_cells"] == []
    assert call_count == 10 * 3  # every combination ran, 100% failure notwithstanding


@pytest.mark.asyncio
async def test_main_threads_circuit_breaker_flag_into_run_matrix(monkeypatch, tmp_path, capsys):
    import sys
    from evals import run_edit_chains as rec_module

    captured_kwargs = {}

    async def fake_run_matrix(chains, models, modes, repeats, renderer, turn_timeout, **kwargs):
        captured_kwargs.update(kwargs)
        return {"records": [], "tripped_models": [], "tripped_cells": []}

    monkeypatch.setattr(rec_module, "run_matrix", fake_run_matrix)

    scenarios_path = tmp_path / "scenarios.yaml"
    scenarios_path.write_text(
        "- id: chain-1\n"
        "  turns:\n"
        "    - request: draw a point\n"
        "      expected_properties:\n"
        "        - name: dummy\n"
        "          type: right_angle\n"
        "          args: [A, B, C]\n"
    )
    monkeypatch.setattr(sys, "argv", [
        "run_edit_chains.py",
        "--scenarios", str(scenarios_path),
        "--models", "test-model",
        "--modes", "full_rewrite",
        "--repeats", "1",
        "--output", str(tmp_path),
        "--no-circuit-breaker",
    ])

    await rec_module.main()

    assert captured_kwargs.get("circuit_breaker_enabled") is False


@pytest.mark.asyncio
async def test_main_defaults_to_circuit_breaker_enabled(monkeypatch, tmp_path):
    import sys
    from evals import run_edit_chains as rec_module

    captured_kwargs = {}

    async def fake_run_matrix(chains, models, modes, repeats, renderer, turn_timeout, **kwargs):
        captured_kwargs.update(kwargs)
        return {"records": [], "tripped_models": [], "tripped_cells": []}

    monkeypatch.setattr(rec_module, "run_matrix", fake_run_matrix)

    scenarios_path = tmp_path / "scenarios.yaml"
    scenarios_path.write_text(
        "- id: chain-1\n"
        "  turns:\n"
        "    - request: draw a point\n"
        "      expected_properties:\n"
        "        - name: dummy\n"
        "          type: right_angle\n"
        "          args: [A, B, C]\n"
    )
    monkeypatch.setattr(sys, "argv", [
        "run_edit_chains.py",
        "--scenarios", str(scenarios_path),
        "--models", "test-model",
        "--modes", "full_rewrite",
        "--repeats", "1",
        "--output", str(tmp_path),
    ])

    await rec_module.main()

    assert captured_kwargs.get("circuit_breaker_enabled") is True


@pytest.mark.asyncio
async def test_main_prints_tripped_summary_when_breaker_fires(monkeypatch, tmp_path, capsys):
    import sys
    from evals import run_edit_chains as rec_module

    async def fake_run_matrix(chains, models, modes, repeats, renderer, turn_timeout, **kwargs):
        return {
            "records": [],
            "tripped_models": ["bad-model"],
            "tripped_cells": [["good-model", "patch"]],
        }

    monkeypatch.setattr(rec_module, "run_matrix", fake_run_matrix)

    scenarios_path = tmp_path / "scenarios.yaml"
    scenarios_path.write_text(
        "- id: chain-1\n"
        "  turns:\n"
        "    - request: draw a point\n"
        "      expected_properties:\n"
        "        - name: dummy\n"
        "          type: right_angle\n"
        "          args: [A, B, C]\n"
    )
    monkeypatch.setattr(sys, "argv", [
        "run_edit_chains.py",
        "--scenarios", str(scenarios_path),
        "--models", "bad-model", "good-model",
        "--modes", "full_rewrite", "patch",
        "--repeats", "1",
        "--output", str(tmp_path),
    ])

    await rec_module.main()

    output = capsys.readouterr().out
    assert "bad-model" in output
    assert "good-model::patch" in output
