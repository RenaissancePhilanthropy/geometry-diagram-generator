"""Tests for the GEPA adapter, scoring, dataset, and prompt override integration."""
from __future__ import annotations

import re

import pytest

from gepa_adapter.scoring import ScenarioResult, compute_score, build_failure_feedback
from gepa_adapter.dataset import load_scenarios, ScenarioData
from strategies.recipe_hints import HINT_PATTERNS, HINT_TEXTS
from strategies.recipe import RecipeStrategy


# ---------------------------------------------------------------------------
# Scoring function tests
# ---------------------------------------------------------------------------


class TestComputeScore:
    """Tests for the composite scoring function."""

    def test_hard_failure_returns_zero(self):
        """No generation or SVG → 0.0."""
        r = ScenarioResult(
            scenario_id="test", gate_status="fail",
            generation_success=False, svg_rendered=False,
        )
        assert compute_score(r) == 0.0

    def test_gate_fail_with_generation_gives_partial_credit(self):
        """Generation + SVG but gate fail → partial credit (not 0.0)."""
        r = ScenarioResult(
            scenario_id="test", gate_status="fail",
            generation_success=True, svg_rendered=True,
        )
        score = compute_score(r)
        # Should get 0.35 (generation+render) + partial gate credit (0.02-0.09)
        # + neutral efficiency (0.12) = 0.49-0.56
        assert 0.49 <= score <= 0.56
        assert score > 0.0  # Must not be zero — GEPA needs gradient

    def test_gate_fail_fewer_failures_scores_higher(self):
        """Fewer gate failures should score higher within gate_fail band."""
        r_few = ScenarioResult(
            scenario_id="test", gate_status="fail",
            generation_success=True, svg_rendered=True,
            gate_failures=["svg:missing_label"],
        )
        r_many = ScenarioResult(
            scenario_id="test", gate_status="fail",
            generation_success=True, svg_rendered=True,
            gate_failures=["svg:missing_label", "tikz:collinear", "canvas:bounds", "labels:missing"],
        )
        assert compute_score(r_few) > compute_score(r_many)

    def test_soft_pass_no_checks(self):
        """Soft pass with no property checks → 0.60."""
        r = ScenarioResult(
            scenario_id="test", gate_status="soft_pass",
            generation_success=True, svg_rendered=True,
        )
        assert compute_score(r) == pytest.approx(0.60)

    def test_full_pass_no_checks(self):
        """Full pass with no property checks → 0.69."""
        r = ScenarioResult(
            scenario_id="test", gate_status="pass",
            generation_success=True, svg_rendered=True,
        )
        assert compute_score(r) == pytest.approx(0.69)

    def test_pass_with_property_checks(self):
        """Pass with 2/2 property checks → 0.87."""
        r = ScenarioResult(
            scenario_id="test", gate_status="pass",
            generation_success=True, svg_rendered=True,
            sympy_property_checks=[
                {"name": "right_angle", "passed": True},
                {"name": "midpoint", "passed": True},
            ],
        )
        assert compute_score(r) == pytest.approx(0.87)

    def test_pass_with_partial_property_checks(self):
        """Pass with 1/2 property checks → 0.78."""
        r = ScenarioResult(
            scenario_id="test", gate_status="pass",
            generation_success=True, svg_rendered=True,
            sympy_property_checks=[
                {"name": "right_angle", "passed": True},
                {"name": "midpoint", "passed": False},
            ],
        )
        assert compute_score(r) == pytest.approx(0.78)

    def test_pass_with_judge(self):
        """Pass with property checks and judge score 4/5 → 0.974."""
        r = ScenarioResult(
            scenario_id="test", gate_status="pass",
            generation_success=True, svg_rendered=True,
            sympy_property_checks=[
                {"name": "right_angle", "passed": True},
                {"name": "midpoint", "passed": True},
            ],
            llm_judge_score=4.0,
        )
        assert compute_score(r) == pytest.approx(0.974)

    def test_perfect_score(self):
        """Pass + all property checks + judge 5/5 → 1.0."""
        r = ScenarioResult(
            scenario_id="test", gate_status="pass",
            generation_success=True, svg_rendered=True,
            sympy_property_checks=[{"name": "right_angle", "passed": True}],
            llm_judge_score=5.0,
        )
        assert compute_score(r) == pytest.approx(1.0)

    def test_score_ordering(self):
        """Score increases with better results (gate_status progression)."""
        scores = [
            # 0: gate_fail with many failures → lowest non-zero
            compute_score(ScenarioResult(
                scenario_id="test", gate_status="fail",
                generation_success=True, svg_rendered=True,
                gate_failures=["a", "b", "c", "d"],
            )),
            # 1: gate_fail with few failures → slightly higher
            compute_score(ScenarioResult(
                scenario_id="test", gate_status="fail",
                generation_success=True, svg_rendered=True,
                gate_failures=["a"],
            )),
            # 2: soft_pass → 0.55
            compute_score(ScenarioResult(
                scenario_id="test", gate_status="soft_pass",
                generation_success=True, svg_rendered=True,
            )),
            # 3: pass → 0.65
            compute_score(ScenarioResult(
                scenario_id="test", gate_status="pass",
                generation_success=True, svg_rendered=True,
            )),
            # 4: pass + property checks → 0.85
            compute_score(ScenarioResult(
                scenario_id="test", gate_status="pass",
                generation_success=True, svg_rendered=True,
                sympy_property_checks=[{"name": "p1", "passed": True}, {"name": "p2", "passed": True}],
            )),
            # 5: pass + property checks + perfect judge → 1.0
            compute_score(ScenarioResult(
                scenario_id="test", gate_status="pass",
                generation_success=True, svg_rendered=True,
                sympy_property_checks=[{"name": "p1", "passed": True}, {"name": "p2", "passed": True}],
                llm_judge_score=5.0,
            )),
        ]
        for i in range(len(scores) - 1):
            assert scores[i] < scores[i + 1], f"Score {i} ({scores[i]:.4f}) >= Score {i+1} ({scores[i+1]:.4f})"

    def test_score_capped_at_one(self):
        """Score should never exceed 1.0."""
        r = ScenarioResult(
            scenario_id="test", gate_status="pass",
            generation_success=True, svg_rendered=True,
            sympy_property_checks=[{"name": "p1", "passed": True}, {"name": "p2", "passed": True}],
            llm_judge_score=5.0,
        )
        assert compute_score(r) <= 1.0


class TestEfficiencyScoring:
    """Tests for the efficiency component of compute_score (retries + duration)."""

    def _make_passing_result(self, **kwargs):
        """Helper to create a minimal passing ScenarioResult."""
        defaults = dict(
            scenario_id="test", gate_status="pass",
            generation_success=True, svg_rendered=True,
        )
        defaults.update(kwargs)
        return ScenarioResult(**defaults)

    def test_no_baseline_defaults_to_neutral(self):
        """Without a baseline, efficiency defaults to 1.0 (no bonus/penalty)."""
        # No baseline → retry_efficiency=1.0, duration_efficiency=1.0
        # efficiency = 0.08*1.0 + 0.04*1.0 = 0.12
        # gate pass (0.22) + gen+render (0.35) + neutral efficiency (0.12) = 0.69
        r = self._make_passing_result(attempts=1, duration_s=10.0)
        score = compute_score(r)
        assert score == pytest.approx(0.69)

    def test_retry_efficiency_bonus_fewer_attempts(self):
        """Fewer attempts than baseline should give a bonus (> neutral)."""
        # Use a gate_fail result so the total doesn't cap at 1.0
        r = ScenarioResult(
            scenario_id="test", gate_status="fail",
            generation_success=True, svg_rendered=True,
            gate_failures=["a"],
            attempts=1, duration_s=30.0,
        )
        score_fewer = compute_score(r, baseline_attempts=3, baseline_duration_s=30.0)
        score_neutral = compute_score(r, baseline_attempts=1, baseline_duration_s=30.0)
        assert score_fewer > score_neutral

    def test_retry_efficiency_penalty_more_attempts(self):
        """More attempts than baseline should give a penalty (< neutral)."""
        # Use a gate_fail result so the total doesn't cap at 1.0
        r = ScenarioResult(
            scenario_id="test", gate_status="fail",
            generation_success=True, svg_rendered=True,
            gate_failures=["a"],
            attempts=3, duration_s=30.0,
        )
        score_more = compute_score(r, baseline_attempts=1, baseline_duration_s=30.0)
        r2 = ScenarioResult(
            scenario_id="test", gate_status="fail",
            generation_success=True, svg_rendered=True,
            gate_failures=["a"],
            attempts=1, duration_s=30.0,
        )
        score_neutral = compute_score(r2, baseline_attempts=1, baseline_duration_s=30.0)
        assert score_more < score_neutral

    def test_retry_efficiency_ratio(self):
        """Verify the retry ratio formula: baseline/actual."""
        # baseline=3, actual=1 → ratio=3.0 → 0.08*3.0 = 0.24
        # With gate pass (0.22) + gen+render (0.35) + retry 0.24 + duration neutral 0.04 = 0.85
        r = self._make_passing_result(attempts=1, duration_s=30.0)
        score = compute_score(r, baseline_attempts=3, baseline_duration_s=30.0)
        # 0.35 + 0.22 + 0.08*3.0 + 0.04*1.0 = 0.35 + 0.22 + 0.24 + 0.04 = 0.85
        assert score == pytest.approx(0.85)

    def test_duration_efficiency_bonus_faster(self):
        """Faster than baseline should give a duration bonus."""
        # baseline=60s, actual=30s → ratio=2.0 → 0.04*2.0 = 0.08
        # baseline=60s, actual=60s → ratio=1.0 → 0.04*1.0 = 0.04
        r_fast = self._make_passing_result(attempts=1, duration_s=30.0)
        r_same = self._make_passing_result(attempts=1, duration_s=60.0)
        score_fast = compute_score(r_fast, baseline_attempts=1, baseline_duration_s=60.0)
        score_same = compute_score(r_same, baseline_attempts=1, baseline_duration_s=60.0)
        assert score_fast > score_same

    def test_duration_efficiency_penalty_slower(self):
        """Slower than baseline should give a duration penalty."""
        # baseline=30s, actual=60s → ratio=0.5 → 0.04*0.5 = 0.02
        r_slow = self._make_passing_result(attempts=1, duration_s=60.0)
        r_same = self._make_passing_result(attempts=1, duration_s=30.0)
        score_slow = compute_score(r_slow, baseline_attempts=1, baseline_duration_s=30.0)
        score_same = compute_score(r_same, baseline_attempts=1, baseline_duration_s=30.0)
        assert score_slow < score_same

    def test_duration_capped_at_bonus_for_faster(self):
        """Duration bonus is NOT capped — being faster gives proportional bonus."""
        # 3× faster: baseline=90, actual=30 → ratio=3.0 → 0.04*3.0 = 0.12
        r = self._make_passing_result(attempts=1, duration_s=30.0)
        score = compute_score(r, baseline_attempts=1, baseline_duration_s=90.0)
        # 0.35 + 0.22 + 0.08*1.0 + 0.04*3.0 = 0.35 + 0.22 + 0.08 + 0.12 = 0.77
        assert score == pytest.approx(0.77)

    def test_combined_efficiency_bonus(self):
        """Both fewer retries AND faster gives combined bonus."""
        # baseline: 3 attempts, 60s; actual: 1 attempt, 30s
        # retry: 3/1 = 3.0 → 0.24; duration: 60/30 = 2.0 → 0.08
        # total efficiency: 0.24 + 0.08 = 0.32
        r = self._make_passing_result(attempts=1, duration_s=30.0)
        score = compute_score(r, baseline_attempts=3, baseline_duration_s=60.0)
        # 0.35 + 0.22 + 0.24 + 0.08 = 0.89
        assert score == pytest.approx(0.89)

    def test_hard_failure_zero_even_with_baseline(self):
        """Hard failure (no diagram) → 0.0 regardless of baseline."""
        r = ScenarioResult(
            scenario_id="test", gate_status="fail",
            generation_success=False, svg_rendered=False,
            attempts=5, duration_s=300.0,
        )
        assert compute_score(r, baseline_attempts=1, baseline_duration_s=30.0) == 0.0

    def test_attempts_zero_guard(self):
        """attempts=0 should be treated as 1 (guard against division by zero)."""
        r = self._make_passing_result(attempts=0, duration_s=30.0)
        # Should not raise; should treat as 1 attempt
        score = compute_score(r, baseline_attempts=1, baseline_duration_s=30.0)
        assert score > 0

    def test_duration_zero_guard(self):
        """duration_s=0 should not cause division by zero."""
        r = self._make_passing_result(attempts=1, duration_s=0.0)
        # duration_s=0 → clamped to 0.001 by guard
        score = compute_score(r, baseline_attempts=1, baseline_duration_s=30.0)
        assert score > 0

    def test_backward_compat_no_baseline(self):
        """Calling compute_score without baselines is backward-compatible."""
        # No baseline → efficiency defaults to 1.0 for both dimensions
        # Explicit baseline=1 attempts, same duration → also neutral
        r = self._make_passing_result(attempts=1, duration_s=30.0)
        score_no_baseline = compute_score(r)
        score_with_neutral_baseline = compute_score(r, baseline_attempts=1, baseline_duration_s=30.0)
        assert score_no_baseline == pytest.approx(score_with_neutral_baseline)

    def test_new_weights_match_old_weights_without_efficiency(self):
        """Without efficiency bonus, the new weights sum correctly for common cases."""
        # gate pass + gen/render = 0.35 + 0.22 = 0.57 (was 0.65)
        # But with neutral efficiency: 0.57 + 0.12 = 0.69
        r = self._make_passing_result()
        assert compute_score(r) == pytest.approx(0.69)

    def test_efficiency_feedback_includes_attempts(self):
        """build_failure_feedback should include attempts info when > 1."""
        r = ScenarioResult(
            scenario_id="test", gate_status="fail",
            generation_success=True, svg_rendered=True,
            attempts=3, used_fallback=True,
        )
        feedback = build_failure_feedback(r)
        assert "3" in feedback
        assert "fallback" in feedback.lower()

    def test_efficiency_feedback_includes_duration(self):
        """build_failure_feedback should include duration when > 0."""
        r = ScenarioResult(
            scenario_id="test", gate_status="pass",
            generation_success=True, svg_rendered=True,
            duration_s=42.5,
        )
        feedback = build_failure_feedback(r)
        assert "42.5s" in feedback


class TestBuildFailureFeedback:
    """Tests for the feedback string builder."""

    def test_error_only(self):
        r = ScenarioResult(
            scenario_id="test", gate_status="fail",
            generation_success=False, svg_rendered=False,
            error="Lowering failed: something",
        )
        feedback = build_failure_feedback(r)
        assert "Lowering failed" in feedback

    def test_gate_failures(self):
        r = ScenarioResult(
            scenario_id="test", gate_status="fail",
            generation_success=True, svg_rendered=True,
            gate_failures=["svg:missing_label", "tikz:collinear"],
        )
        feedback = build_failure_feedback(r)
        assert "svg:missing_label" in feedback

    def test_property_check_failures(self):
        r = ScenarioResult(
            scenario_id="test", gate_status="pass",
            generation_success=True, svg_rendered=True,
            sympy_property_checks=[
                {"name": "right_angle", "passed": False, "message": "not 90 degrees"},
                {"name": "midpoint", "passed": True},
            ],
        )
        feedback = build_failure_feedback(r)
        assert "right_angle" in feedback
        assert "not 90 degrees" in feedback

    def test_no_failure_info(self):
        r = ScenarioResult(
            scenario_id="test", gate_status="pass",
            generation_success=True, svg_rendered=True,
        )
        feedback = build_failure_feedback(r)
        assert "pass" in feedback.lower()


# ---------------------------------------------------------------------------
# Hint pattern tests
# ---------------------------------------------------------------------------


class TestHintPatterns:
    """Tests that hint patterns match expected error messages."""

    def test_angle_equality_pattern(self):
        pattern = HINT_PATTERNS[0][0]
        assert pattern.search("Angle ABC = 45.0° but DEF = 30.0°")
        assert not pattern.search("Triangle 'ABC': ambiguous")

    def test_right_angle_pattern(self):
        pattern = HINT_PATTERNS[1][0]
        assert pattern.search("mark_right_angle(A, B, C) is not 90°")
        assert not pattern.search("Angle ABC = 45.0°")

    def test_circular_dep_pattern(self):
        pattern = HINT_PATTERNS[2][0]
        assert pattern.search("Circular dependency: nodes are in a cycle")
        assert pattern.search("circular dependency detected: nodes are in a cycle")
        assert not pattern.search("mark_right_angle")

    def test_between_selector_pattern(self):
        pattern = HINT_PATTERNS[3][0]
        assert pattern.search("intersection beyond segment, t≈1.5")
        assert pattern.search("point before .+, t≈-0.3")
        assert not pattern.search("Triangle 'ABC': ambiguous")

    def test_triangle_spec_pattern(self):
        pattern = HINT_PATTERNS[4][0]
        assert pattern.search("Triangle 'ABC': ambiguous SSA spec")
        assert pattern.search("Triangle 'DEF': cannot solve - triangle inequality")
        assert not pattern.search("mark_right_angle")

    def test_mark_angle_pattern(self):
        pattern = HINT_PATTERNS[5][0]
        assert pattern.search("mark_angle group=1: angle not equal")
        assert pattern.search("MarkAngle at O: expected 70.0°")
        assert not pattern.search("Angle ABC = 45.0° but DEF = 30.0°")

    def test_undefined_id_pattern(self):
        pattern = HINT_PATTERNS[6][0]
        assert pattern.search("references undefined id 'X'")
        assert not pattern.search("mark_right_angle")

    def test_all_hint_keys_in_text_map(self):
        """Every hint key in HINT_PATTERNS must have a corresponding entry in HINT_TEXTS."""
        for _, hint_key in HINT_PATTERNS:
            assert hint_key in HINT_TEXTS, f"Missing hint text for key: {hint_key}"

    def test_hint_texts_are_nonempty(self):
        for key, text in HINT_TEXTS.items():
            assert len(text.strip()) > 0, f"Hint text for {key} is empty"


# ---------------------------------------------------------------------------
# Dataset loading tests
# ---------------------------------------------------------------------------


class TestDatasetLoading:
    """Tests for scenario dataset loading."""

    def test_load_smoke_scenarios(self):
        scenarios = load_scenarios("evals/scenarios_smoke.yaml")
        assert len(scenarios) == 4
        assert all(isinstance(s, ScenarioData) for s in scenarios)

    def test_load_core_scenarios(self):
        scenarios = load_scenarios("evals/scenarios_core.yaml")
        assert len(scenarios) >= 10
        for s in scenarios:
            assert isinstance(s.id, str)
            assert len(s.id) > 0
            assert isinstance(s.prompt, str)
            assert len(s.prompt) > 0

    def test_scenario_has_expected_fields(self):
        scenarios = load_scenarios("evals/scenarios_smoke.yaml")
        s = scenarios[0]
        assert hasattr(s, "id")
        assert hasattr(s, "prompt")
        assert hasattr(s, "expected_properties")
        assert hasattr(s, "required_labels")
        assert hasattr(s, "expected_points")

    def test_invalid_path_raises(self):
        with pytest.raises(FileNotFoundError):
            load_scenarios("evals/nonexistent.yaml")


# ---------------------------------------------------------------------------
# Prompt override tests
# ---------------------------------------------------------------------------


class TestPromptOverrides:
    """Tests that RecipeStrategy accepts and uses prompt_overrides."""

    def test_default_overrides_empty(self):
        s = RecipeStrategy()
        assert s.prompt_overrides == {}

    def test_custom_overrides_stored(self):
        s = RecipeStrategy(prompt_overrides={"generation_system": "test prompt"})
        assert s.prompt_overrides == {"generation_system": "test prompt"}

    def test_no_recipes_subclass_inherits_overrides(self):
        from evals.run import _RecipeNoRecipesStrategy
        s = _RecipeNoRecipesStrategy()
        assert s.prompt_overrides == {}

    def test_override_preserved_in_no_recipes(self):
        from evals.run import _RecipeNoRecipesStrategy
        s = _RecipeNoRecipesStrategy.__new__(_RecipeNoRecipesStrategy)
        # Just verify the attribute exists and can be set
        s.prompt_overrides = {"hint_angle_equality": "custom hint"}
        assert s.prompt_overrides["hint_angle_equality"] == "custom hint"


# ---------------------------------------------------------------------------
# Seed candidate builder tests
# ---------------------------------------------------------------------------


class TestSeedCandidate:
    """Tests for the seed candidate builder."""

    def test_all_components_present(self):
        from optimize_recipe_prompts import build_seed_candidate
        seed = build_seed_candidate()
        assert "generation_system" in seed
        assert "selection_system" in seed
        assert "dsl_docs" in seed
        assert "hint_angle_equality" in seed
        assert "hint_right_angle" in seed
        assert "hint_circular_dep" in seed
        assert "hint_between_selector" in seed
        assert "hint_triangle_spec" in seed
        assert "hint_mark_angle" in seed
        assert "hint_undefined_id" in seed

    def test_component_filtering(self):
        from optimize_recipe_prompts import build_seed_candidate
        seed = build_seed_candidate(components=["generation_system", "dsl_docs"])
        assert set(seed.keys()) == {"generation_system", "dsl_docs"}

    def test_unknown_component_raises(self):
        from optimize_recipe_prompts import build_seed_candidate
        with pytest.raises(ValueError, match="Unknown component"):
            build_seed_candidate(components=["nonexistent_component"])

    def test_seed_values_are_nonempty(self):
        from optimize_recipe_prompts import build_seed_candidate
        seed = build_seed_candidate()
        for key, value in seed.items():
            assert len(value) > 0, f"Seed component {key} is empty"