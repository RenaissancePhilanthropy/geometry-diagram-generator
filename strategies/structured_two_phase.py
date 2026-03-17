"""
Two-phase structured strategy:
  Phase 1: LLM produces a ConstructionPlan (natural-language construction recipe)
  Phase 2: LLM translates the plan into DiagramIR

Allows head-to-head comparison against the direct structured strategy.
"""
from __future__ import annotations

import logging

from pydantic_ai import Agent

from ir.ir import DiagramIR
from ir.plan import ConstructionPlan
from strategies.base import SubstanceStrategy
from strategies.structured import StructuredRunResult, _run_ir_pipeline
from strategies.instructions import (
    STRUCTURED_STRATEGY_IR_INSTRUCTIONS,
    TWO_PHASE_PLANNER_INSTRUCTIONS,
)

logger = logging.getLogger(__name__)

MAX_PHASE2_RETRIES = 3
MAX_PHASE1_RETRIES = 2


class StructuredTwoPhaseStrategy(SubstanceStrategy):
    """Two-phase strategy: plan then construct IR."""

    def build_agent(self, model: str = "anthropic:claude-sonnet-4-6"):
        raise NotImplementedError("StructuredTwoPhaseStrategy does not support build_agent; use run() directly.")

    async def run(
        self,
        prompt: str,
        model: str = "anthropic:claude-sonnet-4-6",
    ) -> StructuredRunResult:
        last_error: str | None = None

        for phase1_attempt in range(MAX_PHASE1_RETRIES):
            planner_prompt = prompt
            if phase1_attempt > 0 and last_error:
                planner_prompt += f"\n\nPrevious plan led to: {last_error}\nRevise your plan."

            plan = await self._generate_plan(planner_prompt, model)

            for phase2_attempt in range(MAX_PHASE2_RETRIES):
                constructor_prompt = self._build_constructor_prompt(prompt, plan)
                if phase2_attempt > 0 and last_error:
                    constructor_prompt += f"\n\nPrevious attempt failed: {last_error}\nCorrect the DiagramIR."

                try:
                    diagram = await self._generate_diagram(constructor_prompt, model)
                    result = await _run_ir_pipeline(diagram)
                    return result
                except Exception as exc:
                    last_error = str(exc)
                    logger.debug(f"Phase 2 attempt {phase2_attempt+1} failed: {exc}")
                    continue

        raise RuntimeError(
            f"Two-phase strategy exhausted all {MAX_PHASE1_RETRIES}x{MAX_PHASE2_RETRIES} attempts. "
            f"Last error: {last_error}"
        )

    async def _generate_plan(self, prompt: str, model: str) -> ConstructionPlan:
        agent = Agent(
            model=model,
            output_type=ConstructionPlan,
            instructions=TWO_PHASE_PLANNER_INSTRUCTIONS,
        )
        result = await agent.run(prompt)
        return result.output

    async def _generate_diagram(self, prompt: str, model: str) -> DiagramIR:
        agent = Agent(
            model=model,
            output_type=DiagramIR,
            instructions=STRUCTURED_STRATEGY_IR_INSTRUCTIONS,
        )
        result = await agent.run(prompt)
        return result.output

    def _build_constructor_prompt(self, original_prompt: str, plan: ConstructionPlan) -> str:
        plan_text = "\n".join(
            f"  {i+1}. {step.description}"
            for i, step in enumerate(plan.steps)
        )
        checks_text = "\n".join(f"  - {c}" for c in plan.geometric_checks)
        return (
            f"Original request: {original_prompt}\n\n"
            f"Construction plan:\n{plan_text}\n\n"
            f"Expected geometric properties:\n{checks_text}\n\n"
            f"Now produce a DiagramIR that implements this plan exactly."
        )
