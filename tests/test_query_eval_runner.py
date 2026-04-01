"""Integration test for query phase in run_scenario.

Requires LLM access — gated by RUN_LLM_TESTS env var.
Requires TikZ renderer running on localhost:8001.
"""
from __future__ import annotations

import os
import pytest
from evals.scenarios import _validate_scenarios

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_LLM_TESTS"),
    reason="Set RUN_LLM_TESTS=1 to run LLM integration tests",
)


@pytest.fixture
def scenario_with_query():
    """Build a normalized scenario dict via _validate_scenarios (matches real CLI path)."""
    raw = [{
        "id": "test-right-triangle-query",
        "tier": 1,
        "tags": ["triangle", "query"],
        "prompt": "Draw a right triangle ABC with the right angle at B. Label all three vertices A, B, and C.",
        "required_labels": ["A", "B", "C"],
        "expected_properties": [
            {"name": "right_angle_at_B", "type": "right_angle", "args": ["A", "B", "C"]},
        ],
        "queries": [
            {
                "question": "What is the angle at vertex B?",
                "expected_tool_call": {"query_type": "angle"},
            },
        ],
    }]
    return _validate_scenarios(raw)[0]


@pytest.mark.asyncio
async def test_run_scenario_with_queries(scenario_with_query, tmp_path):
    from evals.run import run_scenario

    record = await run_scenario(
        scenario=scenario_with_query,
        strategy_name="structured",
        model="anthropic:claude-sonnet-4-6",
        repeat_index=1,
        svg_output_dir=tmp_path,
        benchmark="test",
    )
    assert record["generation_success"] is True

    qr = record.get("query_results", [])
    assert len(qr) == 1
    assert qr[0]["tool_called"] is True
    assert qr[0]["query_type_match"] is True
