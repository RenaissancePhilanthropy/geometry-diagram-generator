"""GEPA adapter for the recipe strategy's prompts.

Implements the GEPAAdapter protocol to connect GEPA's evolutionary
optimization loop to the existing eval infrastructure.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import re
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gepa.core.adapter import EvaluationBatch

# Ensure project root is on sys.path
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from evals.run import _finalize_gate_status, _collect_check_outcomes
from evals.sympy_checks import _validate_properties_sympy
from gepa_adapter.dataset import ScenarioData
from gepa_adapter.scoring import ScenarioResult, compute_score, build_failure_feedback
from ir.renderer import TikZRenderer, Renderer
from strategies.base import DEFAULT_AGENT_MODEL
from strategies.recipe_hints import HINT_PATTERNS, HINT_TEXTS
from strategies.recipe import RecipeStrategy
from strategies.structured import StructuredRunResult

logger = logging.getLogger(__name__)


@dataclass
class ScenarioTrace:
    """Trajectory data for one scenario — captures what happened during the run.

    Used by make_reflective_dataset to build feedback for the reflection LLM.
    """

    dsl_json: dict | None = None
    attempt_traces: list[dict] = field(default_factory=list)
    gate_status: str = "fail"
    gate_failures: list[str] = field(default_factory=list)
    error: str | None = None
    lowering_error: str | None = None
    sympy_property_checks: list[dict] = field(default_factory=list)
    score: float = 0.0
    feedback: str = ""


class RecipeGEPAAdapter:
    """GEPA adapter for optimizing the recipe strategy's prompts.

    Type parameters (mapped to GEPAAdapter's generics):
        DataInst = ScenarioData
        Trajectory = ScenarioTrace
        RolloutOutput = ScenarioResult
    """

    # GEPA checks this attribute to see if the adapter provides custom
    # proposal logic. None means "use the default reflective mutation".
    propose_new_texts = None

    def __init__(
        self,
        model: str = DEFAULT_AGENT_MODEL,
        renderer: Renderer | None = None,
        llm_judge: bool = False,
        judge_model: str = DEFAULT_AGENT_MODEL,
        max_concurrency: int = 3,
        timeout_per_scenario: int = 300,
        use_recipes: bool = True,
        thinking: bool = True,
    ) -> None:
        self.model = model
        self.renderer = renderer or TikZRenderer()
        self.llm_judge = llm_judge
        self.judge_model = judge_model
        self._max_concurrency = max_concurrency
        self.timeout = timeout_per_scenario
        self.use_recipes = use_recipes
        self.thinking = thinking
        # Track the current batch for make_reflective_dataset
        self._current_batch: list[ScenarioData] = []
        # Per-scenario baselines from the seed evaluation, used for efficiency scoring.
        # Populated lazily from the first evaluate() call (which is always the seed).
        self._baselines: dict[str, dict] = {}  # scenario_id → {"attempts": int, "duration_s": float}

    def evaluate(
        self,
        batch: list[ScenarioData],
        candidate: dict[str, str],
        capture_traces: bool = False,
    ) -> EvaluationBatch:
        """Run the recipe strategy with candidate prompts on each scenario.

        GEPA calls this synchronously; we bridge to async internally.
        """
        self._current_batch = batch

        # Check if we're already in an event loop (e.g., Jupyter)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            # We're inside an existing event loop (Jupyter, etc.)
            # Create a new thread to run the async code
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    asyncio.run,
                    self._evaluate_async(batch, candidate, capture_traces),
                )
                return future.result()
        else:
            return asyncio.run(self._evaluate_async(batch, candidate, capture_traces))

    async def _evaluate_async(
        self,
        batch: list[ScenarioData],
        candidate: dict[str, str],
        capture_traces: bool,
    ) -> EvaluationBatch:
        """Async implementation of evaluate."""
        # Create a fresh semaphore bound to this event loop.
        # GEPA calls evaluate() via asyncio.run(), which creates a new
        # event loop each time, so a semaphore from a previous call would
        # be bound to a defunct loop and raise RuntimeError.
        semaphore = asyncio.Semaphore(self._max_concurrency)

        strategy = RecipeStrategy(
            use_recipes=self.use_recipes,
            prompt_overrides=candidate,
            thinking=self.thinking,
        )

        outputs: list[ScenarioResult] = []
        scores: list[float] = []
        trajectories: list[ScenarioTrace | None] = []

        tasks = [
            self._run_scenario(strategy, scenario, capture_traces, semaphore)
            for scenario in batch
        ]
        results = await asyncio.gather(*tasks)

        for result, trace in results:
            # Look up per-scenario baselines for efficiency scoring
            baseline = self._baselines.get(result.scenario_id)
            baseline_attempts = baseline["attempts"] if baseline else None
            baseline_duration_s = baseline["duration_s"] if baseline else None
            score = compute_score(
                result,
                baseline_attempts=baseline_attempts,
                baseline_duration_s=baseline_duration_s,
            )
            logger.info(
                "Scenario %s: gate=%s gen=%s svg=%s score=%.4f attempts=%d duration=%.1fs props=%d checks=%s",
                result.scenario_id, result.gate_status, result.generation_success,
                result.svg_rendered, score, result.attempts, result.duration_s,
                len(result.sympy_property_checks),
                {c["name"]: c.get("passed") for c in result.sympy_property_checks}
                if result.sympy_property_checks else "none",
            )
            if result.gate_status == "fail" and result.gate_failures:
                logger.info("  Gate failures: %s", result.gate_failures[:5])
            if result.error:
                logger.info("  Error: %s", result.error[:200])
            outputs.append(result)
            scores.append(score)
            trajectories.append(trace if capture_traces else None)

        # Capture baselines from the first evaluation (the seed candidate).
        # After this, all subsequent evaluations will use these baselines
        # for efficiency normalization.
        if not self._baselines:
            for result, trace in results:
                if result.duration_s > 0 or result.attempts > 0:
                    self._baselines[result.scenario_id] = {
                        "attempts": result.attempts,
                        "duration_s": result.duration_s,
                    }

        logger.info("Batch scores: %s (mean=%.4f)", scores, sum(scores) / max(len(scores), 1))

        return EvaluationBatch(
            outputs=outputs,
            scores=scores,
            trajectories=trajectories if capture_traces else None,
        )

    async def _run_scenario(
        self,
        strategy: RecipeStrategy,
        scenario: ScenarioData,
        capture_traces: bool,
        semaphore: asyncio.Semaphore,
    ) -> tuple[ScenarioResult, ScenarioTrace | None]:
        """Run a single scenario, catching exceptions gracefully."""
        trace = ScenarioTrace() if capture_traces else None
        start_time = time.monotonic()

        try:
            async with semaphore:
                result = await asyncio.wait_for(
                    strategy.run(scenario.prompt, model=self.model, renderer=self.renderer),
                    timeout=self.timeout,
                )
            elapsed = time.monotonic() - start_time
            logger.info(
                "Scenario %s: strategy returned type=%s, svg=%s in %.1fs",
                scenario.id, type(result).__name__,
                "yes" if hasattr(result, 'svg') and result.svg else "no",
                elapsed,
            )
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start_time
            logger.warning("Scenario %s: TIMEOUT after %ds", scenario.id, self.timeout)
            result_data = ScenarioResult(
                scenario_id=scenario.id,
                gate_status="fail",
                generation_success=False,
                svg_rendered=False,
                error=f"Timeout after {self.timeout}s",
                duration_s=elapsed,
                attempts=1,
            )
            if trace:
                trace.error = result_data.error
                trace.score = compute_score(result_data)
                trace.feedback = build_failure_feedback(result_data)
            return result_data, trace
        except Exception as e:
            elapsed = time.monotonic() - start_time
            logger.exception("Scenario %s failed", scenario.id)
            result_data = ScenarioResult(
                scenario_id=scenario.id,
                gate_status="fail",
                generation_success=False,
                svg_rendered=False,
                error=str(e)[:500],
                duration_s=elapsed,
                attempts=1,
            )
            if trace:
                trace.error = result_data.error
                trace.score = compute_score(result_data)
                trace.feedback = build_failure_feedback(result_data)
            return result_data, trace

        # Extract eval metrics from the result
        result_data = self._extract_result(scenario, result)
        # Set the wall-clock duration measured in _run_scenario
        result_data.duration_s = elapsed

        # LLM judge (optional, adds 0-0.13 score component)
        if self.llm_judge and result_data.svg_rendered and result_data.generation_success:
            result_data = await self._run_llm_judge(scenario, result, result_data)

        if trace:
            trace.dsl_json = None
            trace.gate_status = result_data.gate_status
            trace.gate_failures = result_data.gate_failures
            trace.sympy_property_checks = result_data.sympy_property_checks
            trace.score = compute_score(result_data)
            trace.feedback = build_failure_feedback(result_data)
            # Extract attempt traces if available
            recipe_meta = result.recipe_metadata if isinstance(result, StructuredRunResult) else None
            if recipe_meta:
                trace.attempt_traces = [
                    {"attempt": t.attempt, "error": t.error, "stage": t.stage}
                    for t in recipe_meta.attempt_traces
                ]
                # Get lowering errors from traces
                for t in recipe_meta.attempt_traces:
                    if t.error and t.stage == "lowering":
                        trace.lowering_error = t.error
                        break

        return result_data, trace

    def _extract_result(
        self,
        scenario: ScenarioData,
        result: StructuredRunResult,
    ) -> ScenarioResult:
        """Extract evaluation metrics from a StructuredRunResult into a ScenarioResult.

        Mirrors the logic in evals/run.py's run_scenario(), including
        SVG checks, TikZ static analysis, canvas/label/entity checks,
        and SymPy property validation.
        """
        from util.svg_checks import run_svg_checks
        from util.tikz_analysis import (
            resolve_all_coordinates,
            validate_geometric_property,
            validate_required_labels,
            validate_required_entities,
            validate_required_canvas,
            validate_expected_points,
        )

        # Build a record dict similar to evals/run.py
        record: dict[str, Any] = {
            "generation_success": True,
            "svg_rendered": True,
            "tikz_checks": None,
            "canvas_checks": None,
            "expected_point_checks": None,
            "structural_checks": None,
            "sympy_property_checks": [],
            "gate_status": "fail",
            "gate_failures": [],
            "svg_checks": None,
            "error": None,
            "query_results": [],
            "deterministic_pass": None,
        }

        # --- SVG quality checks ---
        svg = result.svg
        if svg:
            svg_failures = run_svg_checks(svg)
            record["svg_checks"] = {
                "passed": len(svg_failures) == 0,
                "failures": svg_failures,
            }

        # --- TikZ static analysis checks (when tikz_code is available) ---
        tikz_code = result.tikz
        if tikz_code:
            coords = resolve_all_coordinates(tikz_code)
            tikz_check_results: dict[str, Any] = {}

            for prop in scenario.expected_properties:
                try:
                    prop_result = validate_geometric_property(
                        coords,
                        prop["type"],
                        prop["args"],
                        tikz=tikz_code,
                        tolerance=0.01,  # _TIKZ_CHECK_TOLERANCE
                    )
                except (ValueError, KeyError, TypeError):
                    prop_result = None
                    tikz_check_results[prop["name"]] = {
                        "passed": None,
                        "type": prop["type"],
                        "skipped": True,
                    }
                    continue
                tikz_check_results[prop["name"]] = {
                    "passed": prop_result,
                    "type": prop["type"],
                    "skipped": prop_result is None,
                }

            required_labels = scenario.required_labels
            if required_labels:
                tikz_check_results["required_labels"] = validate_required_labels(
                    tikz_code, required_labels
                )

            required_entities = scenario.required_entities
            if required_entities:
                tikz_check_results["required_entities"] = validate_required_entities(
                    tikz_code, required_entities
                )

            record["tikz_checks"] = tikz_check_results if tikz_check_results else None

            required_canvas = scenario.required_canvas
            if required_canvas:
                record["canvas_checks"] = validate_required_canvas(tikz_code, required_canvas)

            expected_points = scenario.expected_points
            if expected_points:
                record["expected_point_checks"] = validate_expected_points(
                    coords,
                    expected_points,
                    tolerance=scenario.coordinate_tolerance,
                )

        # --- SymPy property checks (from the compiled IR) ---
        if result.sym_table is not None and scenario.expected_properties:
            record["sympy_property_checks"] = _validate_properties_sympy(
                scenario.expected_properties,
                result.sym_table,
            )

        # --- Finalize gate status ---
        _finalize_gate_status(record)

        # --- Extract efficiency metrics from RecipeMetadata ---
        attempts = 1
        used_fallback = False
        if isinstance(result, StructuredRunResult) and result.recipe_metadata:
            attempts = len(result.recipe_metadata.attempt_traces)
            for t in result.recipe_metadata.attempt_traces:
                if t.stage in ("fallback_structured_success", "fallback_structured_failure"):
                    used_fallback = True
                    break

        return ScenarioResult(
            scenario_id=scenario.id,
            gate_status=record["gate_status"],
            generation_success=True,
            svg_rendered=True,
            svg_checks=record.get("svg_checks"),
            tikz_checks=record.get("tikz_checks"),
            sympy_property_checks=record.get("sympy_property_checks", []),
            deterministic_pass=record.get("deterministic_pass"),
            gate_failures=record.get("gate_failures", []),
            llm_judge_score=None,
            llm_judge_reasoning=None,
            # duration_s is set by _run_scenario after this returns
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            attempts=attempts,
            used_fallback=used_fallback,
        )

    async def _run_llm_judge(
        self,
        scenario: ScenarioData,
        result: StructuredRunResult,
        result_data: ScenarioResult,
    ) -> ScenarioResult:
        """Run the LLM judge on the rendered diagram and update the result."""
        from util.llm_judge import judge_rendered_diagram

        svg = result.svg
        if not svg:
            logger.info("Scenario %s: skipping LLM judge (no SVG)", scenario.id)
            return result_data

        logger.info("Scenario %s: running LLM judge (model=%s)", scenario.id, self.judge_model)
        try:
            judge_result = await judge_rendered_diagram(
                prompt=scenario.prompt,
                svg=svg,
                tikz_code=result.tikz,
                model=self.judge_model,
            )
            result_data.llm_judge_score = judge_result.get("score")
            result_data.llm_judge_reasoning = judge_result.get("reasoning")
            logger.info("Scenario %s: LLM judge score=%.1f", scenario.id, result_data.llm_judge_score or 0)
        except Exception as e:
            logger.warning("LLM judge failed for scenario %s: %s", scenario.id, e)
            result_data.llm_judge_reasoning = f"Judge error: {e}"

        return result_data

    def make_reflective_dataset(
        self,
        candidate: dict[str, str],
        eval_batch: EvaluationBatch,
        components_to_update: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        """Build per-component feedback datasets for the reflection LLM.

        For the generation_system component: include the scenario prompt,
        the gate_status, gate_failures, and which properties failed.

        For hint components: only include scenarios where the corresponding
        error pattern was triggered, along with the error message and
        whether the retry succeeded.

        For dsl_docs: include the generated DSL and lowering/IR errors.
        """
        result: dict[str, list[dict[str, Any]]] = {}
        batch = self._current_batch

        for component in components_to_update:
            records: list[dict[str, Any]] = []

            for i, (score, output) in enumerate(
                zip(eval_batch.scores, eval_batch.outputs)
            ):
                scenario = batch[i] if i < len(batch) else None
                trace = (
                    eval_batch.trajectories[i]
                    if eval_batch.trajectories and i < len(eval_batch.trajectories)
                    else None
                )

                # Efficiency metrics included in all component feedback
                efficiency_info = {
                    "attempts": output.attempts,
                    "used_fallback": str(output.used_fallback),
                    "duration_s": f"{output.duration_s:.1f}",
                }

                if component == "generation_system":
                    records.append({
                        "Inputs": {
                            "scenario_prompt": scenario.prompt if scenario else "unknown",
                            "expected_properties": (
                                str(scenario.expected_properties)[:500]
                                if scenario and scenario.expected_properties
                                else "none"
                            ),
                        },
                        "Generated Outputs": {
                            "gate_status": output.gate_status,
                            "generation_success": str(output.generation_success),
                            "svg_rendered": str(output.svg_rendered),
                            "gate_failures": str(output.gate_failures[:5]) if output.gate_failures else "none",
                            **efficiency_info,
                        },
                        "Feedback": (
                            trace.feedback if trace and trace.feedback
                            else build_failure_feedback(output)
                        ),
                        "Score": score,
                    })

                elif component == "dsl_docs":
                    records.append({
                        "Inputs": {
                            "scenario_prompt": scenario.prompt[:300] if scenario else "unknown",
                        },
                        "Generated Outputs": {
                            "gate_status": output.gate_status,
                            "lowering_error": (
                                trace.lowering_error[:300] if trace and trace.lowering_error
                                else "none"
                            ),
                            **efficiency_info,
                        },
                        "Feedback": (
                            trace.feedback if trace and trace.feedback
                            else build_failure_feedback(output)
                        ),
                        "Score": score,
                    })

                elif component == "selection_system":
                    # Selection system affects which recipes are chosen —
                    # include all scenarios but note selection outcomes
                    records.append({
                        "Inputs": {
                            "scenario_prompt": scenario.prompt if scenario else "unknown",
                        },
                        "Generated Outputs": {
                            "gate_status": output.gate_status,
                            **efficiency_info,
                        },
                        "Feedback": (
                            trace.feedback if trace and trace.feedback
                            else build_failure_feedback(output)
                        ),
                        "Score": score,
                    })

                elif component.startswith("hint_"):
                    # Only include scenarios where this hint was triggered
                    hint_triggered = False
                    if trace and trace.attempt_traces:
                        for t in trace.attempt_traces:
                            error = t.get("error", "") or ""
                            if error:
                                # Find the matching hint pattern
                                for pattern, hint_key in HINT_PATTERNS:
                                    if hint_key == component and pattern.search(error):
                                        hint_triggered = True
                                        break
                            if hint_triggered:
                                break

                    if hint_triggered or score < 0.5:
                        # Include triggered scenarios + low-score scenarios (where hints might have helped)
                        records.append({
                            "Inputs": {
                                "scenario_prompt": scenario.prompt[:200] if scenario else "unknown",
                                "error_message": (
                                    trace.attempt_traces[0].get("error", "")[:300]
                                    if trace and trace.attempt_traces
                                    else ""
                                ),
                            },
                            "Generated Outputs": {
                                "hint_text_used": candidate.get(component, HINT_TEXTS.get(component, ""))[:500],
                                "retry_succeeded": str(output.gate_status == "pass"),
                                **efficiency_info,
                            },
                            "Feedback": (
                                trace.feedback if trace and trace.feedback
                                else build_failure_feedback(output)
                            ),
                            "Score": score,
                        })

            result[component] = records

        return result