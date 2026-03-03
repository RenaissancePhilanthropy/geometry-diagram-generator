"""
Unit tests for evals/compare.py.

All pure logic — no LLM, no Docker, no network calls.
Tests use synthetic JSONL record dicts.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from evals.compare import (
    _avg_judge_score,
    _avg_retries,
    _success_rate,
    _svg_check_rate,
    _tikz_check_pass_rate,
    compare_runs,
    detect_regressions,
    load_results,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _record(
    scenario_id="right-triangle",
    strategy="raw_code",
    repeat_index=1,
    generation_success=True,
    svg_rendered=True,
    svg_checks_passed=True,
    tikz_checks=None,
    llm_judge_score=None,
    retries=0,
    duration_s=5.0,
) -> dict:
    """Build a minimal synthetic result record."""
    return {
        "scenario_id": scenario_id,
        "strategy": strategy,
        "repeat_index": repeat_index,
        "generation_success": generation_success,
        "svg_rendered": svg_rendered,
        "svg_checks": {"passed": svg_checks_passed, "failures": []} if svg_rendered else None,
        "tikz_checks": tikz_checks,
        "llm_judge_score": llm_judge_score,
        "retries": retries,
        "duration_s": duration_s,
    }


# ---------------------------------------------------------------------------
# _success_rate
# ---------------------------------------------------------------------------

def test_success_rate_partial():
    records = [
        _record(generation_success=True),
        _record(generation_success=True),
        _record(generation_success=False),
        _record(generation_success=True),
    ]
    assert _success_rate(records) == 0.75


def test_success_rate_empty():
    assert _success_rate([]) == 0.0


def test_success_rate_all_fail():
    records = [_record(generation_success=False)] * 3
    assert _success_rate(records) == 0.0


# ---------------------------------------------------------------------------
# _svg_check_rate
# ---------------------------------------------------------------------------

def test_svg_check_rate_mixed():
    records = [
        _record(svg_checks_passed=True),
        _record(svg_checks_passed=True),
        _record(svg_checks_passed=False),
    ]
    assert abs(_svg_check_rate(records) - 2 / 3) < 1e-9


def test_svg_check_rate_no_checks():
    records = [_record(svg_rendered=False), _record(svg_rendered=False)]
    result = _svg_check_rate(records)
    assert math.isnan(result)


# ---------------------------------------------------------------------------
# _avg_judge_score
# ---------------------------------------------------------------------------

def test_avg_judge_score():
    records = [
        _record(llm_judge_score=4),
        _record(llm_judge_score=3),
        _record(llm_judge_score=5),
    ]
    assert abs(_avg_judge_score(records) - 4.0) < 1e-9


def test_avg_judge_score_ignores_none():
    records = [
        _record(llm_judge_score=4),
        _record(llm_judge_score=None),
        _record(llm_judge_score=2),
    ]
    assert abs(_avg_judge_score(records) - 3.0) < 1e-9


def test_avg_judge_score_all_none():
    records = [_record(llm_judge_score=None)] * 3
    assert _avg_judge_score(records) is None


# ---------------------------------------------------------------------------
# _tikz_check_pass_rate
# ---------------------------------------------------------------------------

def test_tikz_check_pass_rate():
    records = [
        _record(tikz_checks={
            "right_angle": {"passed": True, "type": "right_angle"},
            "midpoint": {"passed": False, "type": "midpoint"},
        }),
        _record(tikz_checks={
            "right_angle": {"passed": True, "type": "right_angle"},
        }),
    ]
    # 2 passed out of 3 total checks
    assert abs(_tikz_check_pass_rate(records) - 2 / 3) < 1e-9


def test_tikz_check_pass_rate_no_checks():
    records = [_record(tikz_checks=None), _record(tikz_checks={})]
    assert _tikz_check_pass_rate(records) is None


# ---------------------------------------------------------------------------
# compare_runs
# ---------------------------------------------------------------------------

def test_compare_runs_overall_success_rate():
    baseline = [
        _record(generation_success=True),
        _record(generation_success=False),
    ]
    candidate = [
        _record(generation_success=True),
        _record(generation_success=True),
    ]
    comparison = compare_runs(baseline, candidate)
    assert comparison["overall"]["baseline_success"] == 0.5
    assert comparison["overall"]["candidate_success"] == 1.0


def test_compare_runs_per_scenario_judge_delta():
    baseline = [
        _record(scenario_id="right-triangle", llm_judge_score=4),
        _record(scenario_id="midpoint", llm_judge_score=5),
    ]
    candidate = [
        _record(scenario_id="right-triangle", llm_judge_score=3),
        _record(scenario_id="midpoint", llm_judge_score=5),
    ]
    comparison = compare_runs(baseline, candidate)
    rt = comparison["scenarios"]["right-triangle"]
    assert rt["judge_delta"] == pytest.approx(-1.0)
    mid = comparison["scenarios"]["midpoint"]
    assert mid["judge_delta"] == pytest.approx(0.0)


def test_compare_runs_scenario_missing_in_candidate():
    baseline = [
        _record(scenario_id="right-triangle", llm_judge_score=4),
        _record(scenario_id="midpoint", llm_judge_score=5),
    ]
    candidate = [
        _record(scenario_id="right-triangle", llm_judge_score=3),
    ]
    comparison = compare_runs(baseline, candidate)
    # midpoint only in baseline — no delta possible
    mid = comparison["scenarios"]["midpoint"]
    assert mid["judge_delta"] is None
    assert mid["candidate_judge"] is None


# ---------------------------------------------------------------------------
# detect_regressions
# ---------------------------------------------------------------------------

def test_detect_regressions_flags_large_drop():
    baseline = [_record(scenario_id="right-triangle", llm_judge_score=5)]
    candidate = [_record(scenario_id="right-triangle", llm_judge_score=3)]
    comparison = compare_runs(baseline, candidate)
    regressions = detect_regressions(comparison, threshold=0.5)
    assert "right-triangle" in regressions


def test_detect_regressions_ignores_small_drop():
    baseline = [_record(scenario_id="right-triangle", llm_judge_score=4)]
    candidate = [_record(scenario_id="right-triangle", llm_judge_score=3.6)]
    comparison = compare_runs(baseline, candidate)
    regressions = detect_regressions(comparison, threshold=0.5)
    assert "right-triangle" not in regressions


def test_detect_regressions_ignores_improvement():
    baseline = [_record(scenario_id="midpoint", llm_judge_score=3)]
    candidate = [_record(scenario_id="midpoint", llm_judge_score=5)]
    comparison = compare_runs(baseline, candidate)
    regressions = detect_regressions(comparison, threshold=0.5)
    assert regressions == []


def test_detect_regressions_no_judge_scores():
    baseline = [_record(scenario_id="midpoint", llm_judge_score=None)]
    candidate = [_record(scenario_id="midpoint", llm_judge_score=None)]
    comparison = compare_runs(baseline, candidate)
    regressions = detect_regressions(comparison, threshold=0.5)
    assert regressions == []


# ---------------------------------------------------------------------------
# load_results
# ---------------------------------------------------------------------------

def test_load_results_reads_jsonl(tmp_path: Path):
    records = [
        {"scenario_id": "right-triangle", "strategy": "raw_code", "generation_success": True},
        {"scenario_id": "midpoint", "strategy": "raw_code", "generation_success": False},
    ]
    jsonl_path = tmp_path / "results.jsonl"
    jsonl_path.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    loaded = load_results(jsonl_path)
    assert len(loaded) == 2
    assert loaded[0]["scenario_id"] == "right-triangle"
    assert loaded[1]["generation_success"] is False


def test_load_results_skips_blank_lines(tmp_path: Path):
    jsonl_path = tmp_path / "results.jsonl"
    jsonl_path.write_text(
        '{"scenario_id": "a"}\n\n{"scenario_id": "b"}\n'
    )
    loaded = load_results(jsonl_path)
    assert len(loaded) == 2
