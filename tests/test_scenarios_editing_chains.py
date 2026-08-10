"""Tests for evals/scenarios_editing_chains.py's chain-scenario validator."""
from __future__ import annotations

import pytest

from evals.scenarios_editing_chains import _validate_chain_scenarios


def test_validates_a_well_formed_chain():
    raw = [
        {
            "id": "chain-1",
            "turns": [
                {"request": "Draw a triangle."},
                {"request": "Fill it red.", "expected_properties": [
                    {"name": "sanity", "type": "right_angle", "args": ["A", "B", "C"]},
                ]},
            ],
        }
    ]
    result = _validate_chain_scenarios(raw)
    assert result == [
        {
            "id": "chain-1",
            "turns": [
                {"request": "Draw a triangle.", "expected_properties": []},
                {"request": "Fill it red.", "expected_properties": [
                    {"name": "sanity", "type": "right_angle", "args": ["A", "B", "C"]},
                ]},
            ],
        }
    ]


def test_raises_on_duplicate_id():
    raw = [
        {"id": "dup", "turns": [{"request": "a", "expected_properties": [{"type": "x"}]}]},
        {"id": "dup", "turns": [{"request": "b", "expected_properties": [{"type": "x"}]}]},
    ]
    with pytest.raises(ValueError, match="duplicate id"):
        _validate_chain_scenarios(raw)


def test_raises_on_missing_turns():
    raw = [{"id": "chain-1", "turns": []}]
    with pytest.raises(ValueError, match="non-empty list"):
        _validate_chain_scenarios(raw)


def test_raises_on_turn_missing_request():
    raw = [{"id": "chain-1", "turns": [{"expected_properties": [{"type": "x"}]}]}]
    with pytest.raises(ValueError, match="'request'"):
        _validate_chain_scenarios(raw)


def test_raises_when_no_turn_defines_expected_properties():
    raw = [{"id": "chain-1", "turns": [{"request": "a"}, {"request": "b"}]}]
    with pytest.raises(ValueError, match="at least one turn must define"):
        _validate_chain_scenarios(raw)
