"""Plan-and-code strategy for geometry diagram generation.

Two-step pipeline:
1. A structured planning sub-agent determines coordinates and expected geometric
   properties for the diagram.
2. The main agent uses the plan to generate TikZ code, render it, and self-validate
   the geometry against the plan's expected properties.

build_agent() returns a single tool-based agent (plan_diagram + render_diagram)
              for use by AGUIApp (web app).
run()         orchestrates the two stages via run_plan → run_code_from_plan.
"""
from __future__ import annotations

import json
import logging

from pydantic_ai import Agent, ModelRetry

from util.tikz_renderer import render_tikz
from util.tikz_analysis import resolve_all_coordinates, validate_geometric_property
from .base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from .instructions import PLANNER_INSTRUCTIONS, PLAN_CODER_TIKZ_INSTRUCTIONS
from .stages import (
    GeometricPlan,
    COMPILE_RETRIES,
    GEOMETRY_RETRIES,
    run_plan,
    run_code_from_plan,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Single-agent coder instructions (used by build_agent for web app)
# ---------------------------------------------------------------------------

_CODER_INSTRUCTIONS = f"""\
You are a geometry diagram assistant. Follow this exact workflow:

1. Call plan_diagram with the user's geometry request to receive a structured plan \
containing explicit coordinates or constructions and expected geometric properties.

2. Using the plan's points and constructions, generate TikZ code using the tkz-euclide package.

3. Call render_diagram with your TikZ code. The tool will:
   - Compile the TikZ to SVG (retrying up to 3 times on compile errors)
   - Automatically check that the geometric properties from the plan hold
   - Return failure details if properties are not satisfied so you can revise

4. After a successful render, briefly explain what you drew.

{PLAN_CODER_TIKZ_INSTRUCTIONS}
"""


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class PlanAndCodeStrategy(SubstanceStrategy):
    def build_agent(self, model: str = DEFAULT_AGENT_MODEL) -> Agent:
        """Build a single tool-based agent for web app use.

        The agent calls plan_diagram (runs a planner sub-agent) and then
        render_diagram (with geometry self-check) in one conversation.
        """
        # Mutable closure state:
        #   plan_state — stores the plan from plan_diagram for use in render_diagram
        #   geometry_attempts — manual counter for geometry self-check retries,
        #     kept separate from the pydantic-ai compile retry budget
        plan_state: list[GeometricPlan] = []
        geometry_attempts: list[int] = [0]

        agent = Agent(model, instructions=_CODER_INSTRUCTIONS, model_settings=self.model_settings)

        @agent.tool_plain(retries=2)
        async def plan_diagram(prompt: str) -> str:
            """Plan the geometry diagram: determine coordinates and expected properties."""
            planner = Agent(
                model,
                output_type=GeometricPlan,
                instructions=PLANNER_INSTRUCTIONS,
                model_settings=self.model_settings,
            )
            result = await planner.run(prompt)
            plan = result.output
            plan_state.clear()
            plan_state.append(plan)
            geometry_attempts[0] = 0
            logger.info(
                "plan_diagram: %d points, %d constructions, %d expected_properties",
                len(plan.points), len(plan.constructions), len(plan.expected_properties),
            )
            return plan.model_dump_json(indent=2)

        @agent.tool_plain(retries=COMPILE_RETRIES + GEOMETRY_RETRIES)
        def render_diagram(tikz: str, tkzelements: str = "") -> str:
            """Render a geometry diagram and validate it against the geometric plan."""
            logger.debug(
                "render_diagram called — tikz=%d chars, tkzelements=%d chars",
                len(tikz), len(tkzelements),
            )
            logger.info("tikz code:\n%s", tikz)
            try:
                svg = render_tikz(tikz, tkzelements=tkzelements or None)
                logger.info("render_diagram succeeded — svg=%d chars", len(svg))
            except RuntimeError as e:
                logger.warning("render_diagram failed (will retry): %s", e)
                raise ModelRetry(str(e)) from e

            # Self-check: validate geometric properties from the plan.
            # validate_geometric_property returns True/False/None; only False is a failure.
            # Geometry retries are tracked with a manual counter independent of the
            # compile retry budget. Once GEOMETRY_RETRIES are exhausted, accept the
            # diagram with a warning rather than crashing the run.
            if plan_state:
                plan = plan_state[0]
                coords = resolve_all_coordinates(tikz)
                failures: list[str] = []
                for prop in plan.expected_properties:
                    check = validate_geometric_property(
                        coords, prop.type, prop.args, tikz=tikz,
                    )
                    if check is False:
                        failures.append(prop.name)
                if failures:
                    geometry_attempts[0] += 1
                    if geometry_attempts[0] <= GEOMETRY_RETRIES:
                        logger.warning(
                            "render_diagram: geometry self-check failures (attempt %d/%d): %s",
                            geometry_attempts[0], GEOMETRY_RETRIES, failures,
                        )
                        raise ModelRetry(
                            f"The diagram compiled successfully, but these geometric "
                            f"properties are not satisfied: {', '.join(failures)}. "
                            f"Review your point coordinates — they must match the plan exactly — "
                            f"and fix the TikZ code to satisfy these properties."
                        )
                    else:
                        logger.warning(
                            "render_diagram: geometry self-check still failing after %d retries "
                            "(%s) — accepting diagram",
                            GEOMETRY_RETRIES, failures,
                        )
                        return json.dumps({"svg": svg, "geometry_failures": failures})

            geometry_attempts[0] = 0
            return json.dumps({"svg": svg})

        return agent

    async def run(self, prompt: str, model: str = DEFAULT_AGENT_MODEL, renderer=None):
        """Run plan then code stages via programmatic agent hand-off."""
        plan, _ = await run_plan(prompt, model=model, model_settings=self.model_settings)
        return await run_code_from_plan(plan, prompt, model=model, model_settings=self.model_settings)
