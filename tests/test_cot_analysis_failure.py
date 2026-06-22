"""
Tests for the CoT-persistence / CoT-analysis failure path in evals/run.py.

Verifies that when a recipe generation fails AFTER the LLM produced a CoT (e.g.
an IR-pipeline crash such as "Line2D.__new__ requires two unique Points."), the
captured CoT is preserved in the record, the CoT-analysis judge fires against
the last attempt's best-effort DSL, and confidence_calibration is computed
(e.g. a confident score on a gate-failure -> 'overconfident').

No real LLM or Docker: the strategy and analyze_cot are mocked.

The CoT analyzer is the deterministic `util.cot_analyzer.analyze_cot`
(synchronous, pure text) — mocked here so we can force a specific score and
check the calibration logic in evals/run.py.
"""
from __future__ import annotations

import pytest

from strategies.recipe import RecipeStrategy, RecipeMetadata, RecipeAttemptTrace
from evals.run import run_scenario, _STRATEGY_MAP


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

_COT = "First I will construct triangle ABC, then locate the midpoints of AA' and BB'..."
_DSL = {"mode": "abstract", "construction": [{"op": "triangle", "id": "t", "vertices": ["A", "B", "C"]}]}


class _FailingRecipeStrategy(RecipeStrategy):
    """A RecipeStrategy whose run() raises, but which has already recorded a
    failed IR-pipeline attempt trace with a captured CoT (mimicking the
    'Line2D.__new__ requires two unique Points.' failure after generation)."""

    def __init__(self, enable_cache: bool = False, thinking: bool = False):
        # Bypass the real init; just populate the partial metadata the eval
        # harness reads on failure.
        meta = RecipeMetadata()
        meta.attempt_traces.append(RecipeAttemptTrace(
            attempt=1,
            dsl_json=_DSL,
            error="Line2D.__new__ requires two unique Points.",
            stage="ir_pipeline",
            cot=_COT,
        ))
        self._partial_recipe_metadata = meta
        self._partial_input_tokens = 100
        self._partial_output_tokens = 2000

    async def run(self, prompt, model=None, renderer=None):
        raise RuntimeError("RecipeStrategy failed after N attempts.")


class _TimeoutRecipeStrategy(RecipeStrategy):
    """A strategy that raises with NO attempt traces / CoT (a 300s timeout
    style failure) — CoT-analysis must skip gracefully."""

    def __init__(self, enable_cache: bool = False, thinking: bool = False):
        self._partial_recipe_metadata = RecipeMetadata()  # empty attempt_traces
        self._partial_input_tokens = 50
        self._partial_output_tokens = 0

    async def run(self, prompt, model=None, renderer=None):
        raise RuntimeError("Timeout after 300s")


def _scenario() -> dict:
    return {"id": "s1", "prompt": "Draw triangle ABC and its rotated image.", "tier": 1, "tags": []}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cot_analysis_fires_on_failure_path_overconfident(monkeypatch, tmp_path):
    """A confident CoT (score 5) on a gate-failure -> 'overconfident'."""
    monkeypatch.setitem(_STRATEGY_MAP, "recipe", _FailingRecipeStrategy)

    captured: dict = {}

    def fake_analyze_cot(prompt, dsl_json, cot, model, enable_cache):
        captured["dsl_json"] = dsl_json
        captured["cot"] = cot
        return {"score": 5, "reasoning": "confident", "signals": {"hedging": 0}}

    monkeypatch.setattr("util.cot_analyzer.analyze_cot", fake_analyze_cot)

    rec = await run_scenario(
        _scenario(), "recipe", model="m", repeat_index=0,
        svg_output_dir=tmp_path, benchmark="b", renderer=None,
        cot_analysis=True, judge_model="ollama:gemma4:31b-cloud",
    )

    assert rec["gate_status"] == "fail"
    # CoT preserved from the failed attempt trace (top-level + serialized trace)
    assert rec["cot"] == _COT
    assert rec["recipe_metadata"]["attempt_traces"][0]["cot"] == _COT
    # CoT-analysis fired against the last attempt's best-effort DSL
    assert captured["dsl_json"] == _DSL
    assert captured["cot"] == _COT
    assert rec["cot_analysis_score"] == 5
    assert rec["confidence_calibration"] == "overconfident"


@pytest.mark.asyncio
async def test_cot_analysis_failure_path_low_confidence_agree(monkeypatch, tmp_path):
    """A low-confidence CoT (score 2) on a gate-failure -> 'agree'."""
    monkeypatch.setitem(_STRATEGY_MAP, "recipe", _FailingRecipeStrategy)

    def fake_analyze_cot(prompt, dsl_json, cot, model, enable_cache):
        return {"score": 2, "reasoning": "hedging", "signals": {"hedging": 3}}

    monkeypatch.setattr("util.cot_analyzer.analyze_cot", fake_analyze_cot)

    rec = await run_scenario(
        _scenario(), "recipe", model="m", repeat_index=0,
        svg_output_dir=tmp_path, benchmark="b", renderer=None,
        cot_analysis=True, judge_model="ollama:gemma4:31b-cloud",
    )

    assert rec["gate_status"] == "fail"
    assert rec["cot_analysis_score"] == 2
    assert rec["confidence_calibration"] == "agree"


@pytest.mark.asyncio
async def test_cot_analysis_skips_when_no_cot(monkeypatch, tmp_path):
    """A timeout-style failure with no CoT -> judge skipped, no score, no
    calibration (does not crash)."""
    monkeypatch.setitem(_STRATEGY_MAP, "recipe", _TimeoutRecipeStrategy)

    def fake_analyze_cot(*args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("analyze_cot should not run without a CoT")

    monkeypatch.setattr("util.cot_analyzer.analyze_cot", fake_analyze_cot)

    rec = await run_scenario(
        _scenario(), "recipe", model="m", repeat_index=0,
        svg_output_dir=tmp_path, benchmark="b", renderer=None,
        cot_analysis=True, judge_model="ollama:gemma4:31b-cloud",
    )

    assert rec["gate_status"] == "fail"
    assert rec["cot"] is None
    assert rec["cot_analysis_score"] is None
    assert rec["confidence_calibration"] is None
    assert rec["cot_analysis_reasoning"] == "(skipped: no CoT — run with --thinking)"