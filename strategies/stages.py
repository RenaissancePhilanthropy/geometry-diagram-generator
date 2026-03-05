"""Reusable pipeline stages for geometry diagram generation.

Each stage is an async function that creates a pydantic-ai Agent, runs it, and
returns the RunResult. Stages accept message_history and usage for chaining.

Stage functions:
    run_draft            — generate TikZ and render (single pass)
    run_plan             — structured planner → GeometricPlan + coordinates
    run_code_from_plan   — translate plan to TikZ, render with geometry self-check
    run_revision         — review and optionally re-render (force_rerender=True by default)

Render tool helpers:
    register_render_tool                  — standard render_diagram (retries=3)
    register_render_tool_with_plan_check  — render_diagram + geometry self-check
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry

from util.tikz_renderer import render_tikz
from util.tikz_analysis import resolve_all_coordinates, validate_geometric_property
from .base import DEFAULT_AGENT_MODEL
from .instructions import (
    DRAFT_INSTRUCTIONS,
    REVISION_INSTRUCTIONS,
    REVISION_FORCE_INSTRUCTIONS,
    REVISION_PROMPT,
    CODE_FROM_PLAN_INSTRUCTIONS,
    PLANNER_INSTRUCTIONS,
)

logger = logging.getLogger(__name__)

# Default retry budgets used by register_render_tool_with_plan_check
COMPILE_RETRIES = 2
GEOMETRY_RETRIES = 2


# ---------------------------------------------------------------------------
# Geometric plan models
# ---------------------------------------------------------------------------

class PlannedPoint(BaseModel):
    name: str
    x: float
    y: float


class PlannedProperty(BaseModel):
    name: str
    type: str
    args: list[Any]


class GeometricPlan(BaseModel):
    reasoning: str
    points: list[PlannedPoint]
    constructions: list[str]
    expected_properties: list[PlannedProperty]


# ---------------------------------------------------------------------------
# Render tool helpers
# ---------------------------------------------------------------------------

def register_render_tool(agent: Agent, retries: int = 3) -> None:
    """Attach a standard render_diagram tool to agent."""

    @agent.tool_plain(retries=retries)
    def render_diagram(tikz: str, tkzelements: str = "") -> str:
        """Render a geometry diagram using TikZ/tkz-euclide code."""
        logger.debug("render_diagram called — tikz=%d chars, tkzelements=%d chars",
                     len(tikz), len(tkzelements))
        logger.info("tikz code:\n%s", tikz)
        try:
            svg = render_tikz(tikz, tkzelements=tkzelements or None)
            logger.info("render_diagram succeeded — svg=%d chars", len(svg))
        except RuntimeError as e:
            logger.warning("render_diagram failed (will retry): %s", e)
            raise ModelRetry(str(e)) from e
        return json.dumps({"svg": svg})


def register_render_tool_with_plan_check(
    agent: Agent,
    plan: GeometricPlan,
    compile_retries: int = COMPILE_RETRIES,
    geometry_retries: int = GEOMETRY_RETRIES,
) -> None:
    """Attach render_diagram with geometry self-check to agent.

    Compile errors consume the compile_retries budget (via pydantic-ai's built-in
    retry counter). Geometry self-check failures consume the geometry_retries budget
    via a separate manual counter; once exhausted, the diagram is accepted gracefully
    with a geometry_failures field rather than crashing.
    """
    geometry_attempts: list[int] = [0]

    @agent.tool_plain(retries=compile_retries + geometry_retries)
    def render_diagram(tikz: str, tkzelements: str = "") -> str:
        """Render a geometry diagram and validate it against the geometric plan."""
        logger.debug("render_diagram called — tikz=%d chars, tkzelements=%d chars",
                     len(tikz), len(tkzelements))
        logger.info("tikz code:\n%s", tikz)
        try:
            svg = render_tikz(tikz, tkzelements=tkzelements or None)
            logger.info("render_diagram succeeded — svg=%d chars", len(svg))
        except RuntimeError as e:
            logger.warning("render_diagram failed (will retry): %s", e)
            raise ModelRetry(str(e)) from e

        # Geometry self-check: validate expected properties from the plan.
        # validate_geometric_property returns True/False/None; only False is a failure.
        if plan.expected_properties:
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
                if geometry_attempts[0] <= geometry_retries:
                    logger.warning(
                        "render_diagram: geometry self-check failures (attempt %d/%d): %s",
                        geometry_attempts[0], geometry_retries, failures,
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
                        geometry_retries, failures,
                    )
                    return json.dumps({"svg": svg, "geometry_failures": failures})

        geometry_attempts[0] = 0
        return json.dumps({"svg": svg})


# ---------------------------------------------------------------------------
# Stage functions
# ---------------------------------------------------------------------------

async def run_draft(prompt: str, model: str = DEFAULT_AGENT_MODEL):
    """Draft stage: generate TikZ and render it.

    Returns an AgentRunResult whose .all_messages() and .usage() can be passed
    to run_revision for chaining.
    """
    agent = Agent(model, instructions=DRAFT_INSTRUCTIONS)
    register_render_tool(agent)
    return await agent.run(prompt)


async def run_plan(prompt: str, model: str = DEFAULT_AGENT_MODEL):
    """Plan stage: produce a GeometricPlan for the given prompt.

    Returns (GeometricPlan, AgentRunResult).
    """
    agent = Agent(model, output_type=GeometricPlan, instructions=PLANNER_INSTRUCTIONS)
    result = await agent.run(prompt)
    logger.info(
        "run_plan: %d points, %d constructions, %d expected_properties",
        len(result.output.points),
        len(result.output.constructions),
        len(result.output.expected_properties),
    )
    return result.output, result


async def run_code_from_plan(
    plan: GeometricPlan,
    prompt: str,
    model: str = DEFAULT_AGENT_MODEL,
):
    """Code stage: translate a GeometricPlan into TikZ and render it.

    Includes geometry self-check with separate retry budgets for compile errors
    and geometric constraint failures.
    """
    agent = Agent(model, instructions=CODE_FROM_PLAN_INSTRUCTIONS)
    register_render_tool_with_plan_check(agent, plan)
    user_message = (
        f"Original request: {prompt}\n\n"
        f"Geometric plan:\n{plan.model_dump_json(indent=2)}\n\n"
        f"Generate TikZ code for this diagram according to the plan, "
        f"then call render_diagram."
    )
    return await agent.run(user_message)


async def run_revision(
    model: str,
    message_history,
    usage,
    force_rerender: bool = True,
):
    """Revision stage: review and re-render the diagram.

    Args:
        model: LLM model identifier.
        message_history: Messages from the prior agent run (e.g. draft).
        usage: Accumulated token usage to carry forward into this run.
        force_rerender: If True (default), the revision agent MUST call
            render_diagram at least once, even if no changes are needed.
            If False, the agent may skip re-rendering if satisfied.
    """
    instructions = REVISION_FORCE_INSTRUCTIONS if force_rerender else REVISION_INSTRUCTIONS
    agent = Agent(model, instructions=instructions)
    register_render_tool(agent)
    return await agent.run(
        REVISION_PROMPT,
        message_history=message_history,
        usage=usage,
    )
