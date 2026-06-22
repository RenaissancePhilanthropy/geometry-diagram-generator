"""Scoring functions for GEPA adapter evaluation.

Composite score (0.0–1.0+) combining deterministic geometric checks,
generation/render success, optional LLM judge score, and efficiency.

Weighting rationale:
  - Generation + rendering (0.35): without a rendered diagram, nothing else matters.
  - Gate quality (0.22 pass / reduced for soft_pass/fail): deterministic
    correctness is the most reliable signal.
  - Property check pass rate (0–0.18): fine-grained geometric correctness gradient.
  - LLM judge (0–0.13): subjective quality signal, optional.
  - Efficiency (0.12): rewards fewer retries and faster generation relative to
    the seed baseline. This encourages prompts that produce correct output
    in fewer attempts and less wall-clock time.
      - Retry efficiency (0.08): baseline_attempts / actual_attempts.
        Rewards first-try success; penalizes retries and fallback usage.
      - Duration efficiency (0.04): baseline_duration_s / actual_duration_s.
        Rewards faster generation; penalizes slow generation. Both are
        bonuses — improvements over baseline score above 1.0, regressions
        score below 1.0 on this component.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScenarioResult:
    """Result of running a single scenario through the recipe pipeline.

    Mirrors the key fields from evals/run.py result records.
    """

    scenario_id: str
    gate_status: str  # "pass", "soft_pass", or "fail"
    generation_success: bool
    svg_rendered: bool
    svg_checks: dict | None = None
    tikz_checks: dict | None = None
    sympy_property_checks: list[dict] = field(default_factory=list)
    deterministic_pass: bool | None = None
    gate_failures: list[str] = field(default_factory=list)
    llm_judge_score: float | None = None
    llm_judge_reasoning: str | None = None
    duration_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    attempts: int = 1  # total generation attempts (1 = first-try success)
    used_fallback: bool = False  # whether StructuredStrategy fallback was used
    error: str | None = None


def compute_score(
    result: ScenarioResult,
    baseline_attempts: int | None = None,
    baseline_duration_s: float | None = None,
) -> float:
    """Compute a composite score from a scenario result.

    Higher is better. The scoring provides a gradient even for partial
    success, so GEPA can learn from improvements in individual dimensions.

    The efficiency component rewards improvements over the seed baseline:
    fewer retries and faster generation both contribute bonuses that can
    push the total above what the quality components alone would yield.

    Weighting:
      - Generation + rendering (0.35): binary — did we produce a diagram?
      - Gate quality (0.22 pass / reduced for soft_pass/fail):
          Even a gate-fail gives partial credit if the diagram rendered,
          because property checks may still pass.
      - Property check pass rate (0–0.18): fine-grained geometric correctness.
      - LLM judge (0–0.13): subjective quality, optional.
      - Efficiency (0.12): rewards fewer retries and faster generation
          relative to baseline. Both dimensions use ratio = baseline / actual,
          so improvements over baseline score > 1.0 on that sub-component.
      Without a baseline, efficiency defaults to 1.0 (neutral — no bonus/penalty).

    Args:
        result: The scenario result to score.
        baseline_attempts: Seed's attempt count for this scenario. If None,
            retry_efficiency defaults to 1.0 (no bonus/penalty).
        baseline_duration_s: Seed's wall-clock duration for this scenario.
            If None, duration_efficiency defaults to 1.0 (no bonus/penalty).
    """
    # Hard failure: no diagram produced or rendering failed
    if not result.generation_success or not result.svg_rendered:
        return 0.0

    score = 0.0

    # Generation + rendering (0.35): binary — we got a diagram
    score += 0.35

    # Gate quality: full pass gets the most, but even a fail gets partial credit
    # if the diagram rendered (some properties may still pass).
    if result.gate_status == "pass":
        score += 0.22
    elif result.gate_status == "soft_pass":
        score += 0.13
    elif result.gate_status == "fail":
        # Partial credit: the diagram exists but has some check failures.
        # The number of failures provides a gradient — fewer failures = better.
        n_failures = len(result.gate_failures) if result.gate_failures else 0
        # 0 failures with gate=fail shouldn't happen, but handle it:
        # 1 failure: 0.06, 2: 0.04, 3+: 0.02
        # This gives GEPA a gradient to climb even from gate=fail.
        score += max(0.02, 0.09 - 0.02 * min(n_failures, 4))

    # Property check pass rate (0–0.18)
    sympy_checks = result.sympy_property_checks
    if sympy_checks:
        passed = sum(1 for c in sympy_checks if c.get("passed") is True)
        rate = passed / len(sympy_checks)
        score += 0.18 * rate

    # LLM judge (0–0.13), optional
    if result.llm_judge_score is not None:
        score += 0.13 * (result.llm_judge_score / 5.0)

    # Efficiency: retries (0.08) + duration (0.04)
    # Both use ratio = baseline / actual, so improvements over baseline
    # score above 1.0 (bonus) and regressions score below 1.0 (penalty).
    # Without a baseline, both default to 1.0 (neutral).
    actual_attempts = max(result.attempts, 1)  # guard against 0
    if baseline_attempts is not None and baseline_attempts > 0:
        retry_efficiency = baseline_attempts / actual_attempts
    else:
        retry_efficiency = 1.0  # no baseline → neutral

    actual_duration = max(result.duration_s, 0.001)  # guard against 0
    if baseline_duration_s is not None and baseline_duration_s > 0:
        duration_efficiency = baseline_duration_s / actual_duration
    else:
        duration_efficiency = 1.0  # no baseline → neutral

    score += 0.08 * retry_efficiency
    score += 0.04 * duration_efficiency

    return min(score, 1.0)


def build_failure_feedback(result: ScenarioResult) -> str:
    """Build a human-readable feedback string from a scenario result.

    Used by make_reflective_dataset to provide diagnostic feedback
    for the GEPA reflection LLM.
    """
    parts: list[str] = []

    if result.error:
        parts.append(f"Error: {result.error[:500]}")

    if result.gate_failures:
        parts.append(f"Gate failures: {', '.join(result.gate_failures[:10])}")

    if result.sympy_property_checks:
        failed = [c for c in result.sympy_property_checks if c.get("passed") is not True]
        if failed:
            parts.append(f"Failed property checks ({len(failed)}/{len(result.sympy_property_checks)}):")
            for c in failed[:5]:
                parts.append(f"  - {c.get('name', 'unknown')}: {c.get('message', '')}")

    if result.llm_judge_reasoning:
        parts.append(f"LLM judge reasoning: {result.llm_judge_reasoning[:300]}")

    # Efficiency info (helps the reflection LLM understand retry/speed tradeoffs)
    if result.attempts > 1:
        parts.append(f"Attempts: {result.attempts}{' (fallback used)' if result.used_fallback else ''}")
    if result.duration_s > 0:
        parts.append(f"Duration: {result.duration_s:.1f}s")

    if not parts:
        parts.append(f"Gate status: {result.gate_status}")

    return "\n".join(parts)