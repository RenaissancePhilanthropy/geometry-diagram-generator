# tests/test_analyze_confidence.py
"""Smoke tests for evals/analyze_confidence.py against synthetic JSONL.

Verifies the analyzer loads records, computes AUC, applies the strict-pass
label (dropping soft_pass), counts the soft coverage gap, and handles
contradictions + baselines — all in pure stdlib (no network/models).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from evals.analyze_confidence import (
    analyze,
    auc_roc,
    bootstrap_auc_ci,
    extract_observations,
)
from strategies.confidence import geo_correctness_score


def _meta(geo: int, contradictions: bool = False) -> dict:
    return {
        "geometric_correctness": {"confidence_score": geo, "flags": []},
        "request_ambiguity": {"confidence_score": geo, "flags": []},
        "end_to_end": {"confidence_score": geo, "flags": []},
        "contradictions_found": contradictions,
        "contradiction_detail": [],
    }


def _record(
    *,
    model: str = "m1",
    tier: int = 3,
    gate: str,
    hard_geo: int | None,
    soft_attempts: list[tuple[int | None, str]],  # (soft_geo_or_None, stage)
    cot: int | None = None,
    judge: int | None = None,
    contradictions: bool = False,
) -> dict:
    traces = []
    for i, (soft_geo, stage) in enumerate(soft_attempts, start=1):
        traces.append({
            "attempt": i,
            "stage": stage,
            "dsl_json": None,
            "error": None,
            "cot": None,
            "evaluation_metadata_hard": _meta(hard_geo, contradictions) if hard_geo is not None else None,
            "evaluation_metadata_soft": _meta(soft_geo) if soft_geo is not None else None,
        })
    return {
        "model": model,
        "tier": tier,
        "gate_status": gate,
        "cot_analysis_score": cot,
        "llm_judge_score": judge,
        "recipe_metadata": {
            "evaluation_metadata_hard": _meta(hard_geo, contradictions) if hard_geo is not None else None,
            "evaluation_metadata_soft": None,
            "attempt_traces": traces,
        },
    }


# ---------------------------------------------------------------------------
# Stats primitives
# ---------------------------------------------------------------------------

def test_auc_perfect_and_useless():
    # Perfect separation: pass=90, fail=20 -> AUC 1.0
    assert auc_roc([90, 90, 90, 20, 20, 20], [1, 1, 1, 0, 0, 0]) == 1.0
    # Inverted: pass=20, fail=90 -> AUC 0.0
    assert auc_roc([20, 20, 20, 90, 90, 90], [1, 1, 1, 0, 0, 0]) == 0.0
    # All tied -> AUC 0.5
    assert auc_roc([50, 50, 50, 50], [1, 1, 0, 0]) == 0.5
    # One class empty -> None
    assert auc_roc([1, 2, 3], [1, 1, 1]) is None


def test_auc_tie_handling():
    # Ties should not error and should land in (0,1).
    auc = auc_roc([50, 50, 60, 60], [1, 0, 1, 0])
    assert 0.0 <= auc <= 1.0


def test_bootstrap_ci_basic():
    auc, lo, hi = bootstrap_auc_ci([90, 90, 90, 20, 20, 20], [1, 1, 1, 0, 0, 0],
                                   n_boot=200, seed=42)
    assert auc == 1.0
    assert lo is not None and hi is not None
    assert lo <= auc <= hi


# ---------------------------------------------------------------------------
# Extraction / label logic
# ---------------------------------------------------------------------------

def test_strict_pass_drops_soft_pass():
    recs = [
        _record(gate="pass", hard_geo=80, soft_attempts=[(80, "success")]),
        _record(gate="soft_pass", hard_geo=70, soft_attempts=[(70, "success")]),
        _record(gate="fail", hard_geo=30, soft_attempts=[(30, "lowering")]),
    ]
    obs = extract_observations(recs)
    # hard obs: pass + fail = 2 (soft_pass dropped)
    assert len(obs["hard"]) == 2
    assert len(obs["soft"]) == 2  # soft_pass record's trace also dropped (record excluded)


def test_coverage_gap_counts_unparseable_attempts():
    # A fail record whose only attempt produced no soft (output_validation).
    recs = [
        _record(gate="fail", hard_geo=40, soft_attempts=[(None, "output_validation")]),
        _record(gate="pass", hard_geo=85, soft_attempts=[(85, "success")]),
    ]
    obs = extract_observations(recs)
    assert obs["coverage"]["total"] == 2
    assert obs["coverage"]["no_soft"] == 1
    assert obs["coverage"]["no_soft_fail"] == 1  # that no-soft attempt was a failure
    assert len(obs["soft"]) == 1  # only the pass record's attempt has a soft score


def test_contradictions_precision_for_fail():
    recs = [
        _record(gate="fail", hard_geo=40, soft_attempts=[(40, "lowering")], contradictions=True),
        _record(gate="pass", hard_geo=80, soft_attempts=[(80, "success")], contradictions=True),
    ]
    obs = extract_observations(recs)
    assert obs["contradictions"]["total_true"] == 2
    assert obs["contradictions"]["fail_given_true"] == 1


def test_baselines_collected():
    recs = [
        _record(gate="pass", hard_geo=80, soft_attempts=[(80, "success")], cot=5, judge=4),
        _record(gate="fail", hard_geo=30, soft_attempts=[(30, "lowering")], cot=1, judge=2),
    ]
    obs = extract_observations(recs)
    assert len(obs["cot"]) == 2
    assert len(obs["judge"]) == 2


def test_attempt_level_soft_uses_stage_label():
    # One record that retried: attempt 1 failed (soft 60), attempt 2 succeeded (soft 90).
    recs = [
        _record(gate="pass", hard_geo=70,
                 soft_attempts=[(60, "lowering"), (90, "success")]),
    ]
    obs = extract_observations(recs)
    # Two soft observations (both attempts), labels False then True.
    labels = [o["label"] for o in obs["soft"]]
    assert labels == [False, True]


# ---------------------------------------------------------------------------
# End-to-end analyze()
# ---------------------------------------------------------------------------

def test_analyze_perfect_separation_soft_auc_one():
    recs = []
    for _ in range(12):
        recs.append(_record(gate="pass", hard_geo=90, soft_attempts=[(90, "success")]))
    for _ in range(8):
        recs.append(_record(gate="fail", hard_geo=20, soft_attempts=[(20, "lowering")]))
    summary = analyze(recs, n_boot=200, seed=0)
    cell = summary["cells"]["m1|3"]
    assert cell["hard"]["auc"] == 1.0
    assert cell["soft"]["auc"] == 1.0
    assert cell["hard"]["n_pass"] == 12 and cell["hard"]["n_fail"] == 8
    # No silently-overconfident failures (all fails scored 20).
    assert cell["hard"]["silently_overconf"] == 0
    assert "text" in summary and "coverage gap" in summary["text"]


def test_analyze_silently_overconfident_detected():
    # Failures scored high (>=80) should be counted as silently overconfident.
    recs = [
        *[_record(gate="pass", hard_geo=85, soft_attempts=[(85, "success")]) for _ in range(5)],
        *[_record(gate="fail", hard_geo=82, soft_attempts=[(82, "lowering")]) for _ in range(5)],
    ]
    summary = analyze(recs, n_boot=200, seed=0)
    cell = summary["cells"]["m1|3"]
    assert cell["hard"]["silently_overconf"] == 5
    assert cell["hard"]["silently_overconf_rate"] == 1.0


def test_cli_runs_on_tmp_jsonl(tmp_path):
    recs = [
        *[_record(gate="pass", hard_geo=80, soft_attempts=[(80, "success")], cot=4) for _ in range(6)],
        *[_record(gate="fail", hard_geo=35, soft_attempts=[(35, "lowering")], cot=2) for _ in range(4)],
    ]
    p = tmp_path / "run.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in recs))
    out = tmp_path / "report.json"
    result = subprocess.run(
        [sys.executable, "-m", "evals.analyze_confidence",
         "--results", str(p), "--out", str(out), "--n-boot", "100"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "AUC=" in result.stdout
    assert out.exists()
    report = json.loads(out.read_text())
    assert "m1|3" in report["cells"]