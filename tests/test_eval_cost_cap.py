"""``evals.run``: a timed-out scenario's record carries the cost of the calls that finished before
the timeout, and ``--max-cost`` stops starting scenarios once the recorded cost reaches the cap."""
from __future__ import annotations

import asyncio
import json
import sys

import pytest
from langchain_core.messages import AIMessage

from evals import run as run_mod
from geometry_diagrams.strategies import llm

SCENARIOS = "\n".join(
    f"- id: s{i}\n  tier: 1\n  prompt: draw a triangle\n  expected_properties: []" for i in range(6)
)


def _priced(cost: float) -> AIMessage:
    return AIMessage(content="x", response_metadata={"token_usage": {"cost": cost}})


def test_ledger_sums_priced_responses_and_ignores_unpriced():
    with llm.cost_ledger() as ledger:
        assert ledger.cost_usd is None
        llm.extract_cost(AIMessage(content="no price"))
        assert ledger.cost_usd is None
        assert llm.extract_cost(_priced(0.25)) == 0.25
        llm.extract_cost(_priced(0.5))
    assert ledger.cost_usd == pytest.approx(0.75)
    llm.extract_cost(_priced(9.0))  # outside the block: nothing records it
    assert ledger.cost_usd == pytest.approx(0.75)


def test_ledger_is_shared_with_tasks_started_inside_it():
    async def go():
        with llm.cost_ledger() as ledger:
            await asyncio.gather(*(asyncio.create_task(asyncio.to_thread(llm.extract_cost, _priced(0.1)))
                                   for _ in range(3)))
        return ledger.cost_usd
    assert asyncio.run(go()) == pytest.approx(0.3)


def _run_main(monkeypatch, tmp_path, fake, *extra):
    scen = tmp_path / "scen.yaml"
    scen.write_text(SCENARIOS)
    monkeypatch.setattr(run_mod, "run_scenario", fake)
    monkeypatch.setattr(sys, "argv", ["evals.run", "--scenarios", str(scen), "--strategies", "structured",
                                      "--model", "anthropic:x", "--renderer", "svg", "--output", str(tmp_path / "out"),
                                      "--max-concurrency", "1", *extra])
    asyncio.run(run_mod.main())
    (out,) = (tmp_path / "out").glob("*.jsonl")
    return [json.loads(line) for line in out.read_text().splitlines()]


def test_timeout_record_carries_the_cost_of_finished_calls(monkeypatch, tmp_path):
    async def slow(scenario, *a, **k):
        llm.extract_cost(_priced(0.4))   # one call finished...
        await asyncio.sleep(30)          # ...then the next hangs
    records = _run_main(monkeypatch, tmp_path, slow, "--scenario-ids", "s0", "--scenario-timeout", "1")
    (rec,) = records
    assert rec["gate_failures"] == ["timeout"]
    assert rec["cost_usd"] == pytest.approx(0.4) and rec["cost_partial"] is True


def test_max_cost_stops_starting_new_scenarios(monkeypatch, tmp_path, capsys):
    async def fake(scenario, strategy, model, repeat, *a, **k):
        return {"scenario_id": scenario["id"], "strategy": strategy, "model": model, "repeat_index": repeat,
                "gate_status": "pass", "gate_failures": [], "warnings": [], "cost_usd": 0.3,
                "generation_success": True, "svg_rendered": True, "input_tokens": 1, "output_tokens": 1,
                "tool_calls": 0, "retries": 0, "duration_s": 0.0}
    records = _run_main(monkeypatch, tmp_path, fake, "--max-cost", "0.5")
    assert len(records) == 2                       # 0.3, then 0.6 >= 0.5: the rest are not started
    assert "4 scenario(s) not started" in capsys.readouterr().out


def test_max_cost_must_be_positive(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="--max-cost"):
        _run_main(monkeypatch, tmp_path, None, "--max-cost", "0")
