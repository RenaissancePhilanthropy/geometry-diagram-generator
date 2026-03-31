# tests/test_query_eval_scenarios.py
"""Tests for the optional 'queries' field in scenario validation."""
from __future__ import annotations

import pytest
from evals.scenarios import _validate_scenarios


def test_scenario_with_queries_validates():
    """A scenario with a valid queries field should normalize correctly."""
    raw = [{
        "id": "test-query",
        "prompt": "Draw a right triangle ABC with the right angle at B.",
        "queries": [
            {
                "question": "What is the angle at vertex A?",
                "expected_tool_call": {"query_type": "angle"},
                "expected_answer": {"key": "angle_degrees", "tolerance": 1.0},
            },
        ],
    }]
    result = _validate_scenarios(raw)
    assert len(result) == 1
    assert len(result[0]["queries"]) == 1
    q = result[0]["queries"][0]
    assert q["question"] == "What is the angle at vertex A?"
    assert q["expected_tool_call"]["query_type"] == "angle"


def test_scenario_without_queries_defaults_empty():
    """Scenarios without queries should get an empty list."""
    raw = [{"id": "no-query", "prompt": "Draw a triangle."}]
    result = _validate_scenarios(raw)
    assert result[0]["queries"] == []


def test_queries_must_be_list():
    raw = [{"id": "bad", "prompt": "Draw.", "queries": "not a list"}]
    with pytest.raises(ValueError, match="queries.*list"):
        _validate_scenarios(raw)


def test_query_missing_question_raises():
    raw = [{
        "id": "bad",
        "prompt": "Draw.",
        "queries": [{"expected_tool_call": {"query_type": "angle"}}],
    }]
    with pytest.raises(ValueError, match="question"):
        _validate_scenarios(raw)


def test_query_with_only_question_validates():
    """A query with just a question (no expected_tool_call or expected_answer) is valid."""
    raw = [{
        "id": "minimal",
        "prompt": "Draw a triangle.",
        "queries": [{"question": "What is the angle?"}],
    }]
    result = _validate_scenarios(raw)
    assert len(result[0]["queries"]) == 1
    assert result[0]["queries"][0]["expected_tool_call"] is None
    assert result[0]["queries"][0]["expected_answer"] is None
