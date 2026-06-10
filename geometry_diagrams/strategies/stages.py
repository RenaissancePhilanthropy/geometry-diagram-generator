"""Reusable pipeline stages for geometry diagram generation.

Each stage is an async function that creates a LangGraph ReAct agent, runs it,
and returns the result. Stages accept message_history for chaining.

Stage functions:
    run_draft            — generate TikZ and render (single pass)
    run_plan             — structured planner → GeometricPlan + coordinates
    run_code_from_plan   — translate plan to TikZ, render with geometry self-check
    run_revision         — review and optionally re-render (force_rerender=True by default)

Render tool helpers:
    make_render_tool                  — standard render_diagram tool
    make_render_tool_with_plan_check  — render_diagram tool + geometry self-check
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, AIMessage, ToolMessage

from geometry_diagrams.util.tikz_renderer import render_tikz
from geometry_diagrams.util.tikz_analysis import resolve_all_coordinates, validate_geometric_property
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


# ---------------------------------------------------------------------------
# Shared result type for raw (non-IR) strategies
# ---------------------------------------------------------------------------

@dataclass
class RawRunResult:
    """Minimal run result compatible with evals/run.py expectations."""
    svg: str
    input_tokens: int = 0
    output_tokens: int = 0
    tikz: str | None = None
    tkzelements: str | None = None
    tool_calls: int = 0
    retries: int = 0


def extract_svg_from_messages(messages: list[BaseMessage]) -> str:
    """Return the SVG string from the last successful render_diagram tool return."""
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and msg.name == "render_diagram":
            try:
                return json.loads(msg.content)["svg"]
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
    return ""


def _extract_usage_from_messages(messages: list[BaseMessage]) -> tuple[int, int]:
    """Sum token usage from all AIMessage responses in the message list."""
    input_tokens = 0
    output_tokens = 0
    for msg in messages:
        if isinstance(msg, AIMessage):
            meta = msg.response_metadata.get("usage", {})
            input_tokens += meta.get("input_tokens", meta.get("prompt_tokens", 0))
            output_tokens += meta.get("output_tokens", meta.get("completion_tokens", 0))
    return input_tokens, output_tokens


# Default retry budgets
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
# Render tool factories
# ---------------------------------------------------------------------------

def make_render_tool():
    """Return a standard render_diagram tool (errors returned as JSON error strings)."""

    @tool
    def render_diagram(tikz: str, tkzelements: str = "") -> str:
        """Render a geometry diagram using TikZ/tkz-euclide code.

        Args:
            tikz: TikZ code for the diagram.
            tkzelements: Optional tkz-elements code.
        Returns:
            JSON with svg field on success, or error field on failure.
        """
        logger.debug("render_diagram called — tikz=%d chars", len(tikz))
        logger.info("tikz code:\n%s", tikz)
        try:
            svg = render_tikz(tikz, tkzelements=tkzelements or None)
            logger.info("render_diagram succeeded — svg=%d chars", len(svg))
            return json.dumps({"svg": svg})
        except RuntimeError as e:
            logger.warning("render_diagram failed: %s", e)
            return json.dumps({"error": str(e)})

    return render_diagram


def make_render_tool_with_plan_check(
    plan: GeometricPlan,
    compile_retries: int = COMPILE_RETRIES,
    geometry_retries: int = GEOMETRY_RETRIES,
):
    """Return a render_diagram tool with geometry self-check.

    Compile errors and geometry failures are returned as JSON error strings
    so the LLM can see them and retry via the ReAct loop.
    """
    geometry_attempts: list[int] = [0]

    @tool
    def render_diagram(tikz: str, tkzelements: str = "") -> str:
        """Render a geometry diagram and validate it against the geometric plan.

        Args:
            tikz: TikZ code for the diagram.
            tkzelements: Optional tkz-elements code.
        Returns:
            JSON with svg field on success, or error/geometry_failures on failure.
        """
        logger.debug("render_diagram called — tikz=%d chars", len(tikz))
        try:
            svg = render_tikz(tikz, tkzelements=tkzelements or None)
        except RuntimeError as e:
            logger.warning("render_diagram compile failed: %s", e)
            return json.dumps({"error": str(e)})

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
                        "render_diagram: geometry failures (attempt %d/%d): %s",
                        geometry_attempts[0], geometry_retries, failures,
                    )
                    return json.dumps({
                        "error": (
                            f"The diagram compiled but these geometric properties are not "
                            f"satisfied: {', '.join(failures)}. Fix your TikZ coordinates."
                        )
                    })
                else:
                    logger.warning(
                        "render_diagram: geometry still failing after %d retries (%s) — accepting",
                        geometry_retries, failures,
                    )
                    return json.dumps({"svg": svg, "geometry_failures": failures})

            geometry_attempts[0] = 0

        return json.dumps({"svg": svg})

    return render_diagram


# ---------------------------------------------------------------------------
# Stage functions
# ---------------------------------------------------------------------------

async def run_draft(
    prompt: str,
    model: str = DEFAULT_AGENT_MODEL,
    model_settings: dict | None = None,
    run_config: dict | None = None,
):
    """Draft stage: generate TikZ and render it. Returns final graph state."""
    from .llm import get_chat_model
    from langgraph.prebuilt import create_react_agent

    llm = get_chat_model(model)
    render_tool = make_render_tool()
    graph = create_react_agent(llm, tools=[render_tool], prompt=DRAFT_INSTRUCTIONS)
    return await graph.ainvoke({"messages": [("user", prompt)]}, config=run_config or {})


async def run_plan(
    prompt: str,
    model: str = DEFAULT_AGENT_MODEL,
    model_settings: dict | None = None,
) -> tuple[GeometricPlan, dict]:
    """Plan stage: produce a GeometricPlan. Returns (GeometricPlan, final_state)."""
    from .llm import get_chat_model
    from langchain_core.messages import SystemMessage, HumanMessage

    llm = get_chat_model(model)
    structured = llm.with_structured_output(GeometricPlan)
    messages = [
        SystemMessage(content=PLANNER_INSTRUCTIONS),
        HumanMessage(content=prompt),
    ]
    plan = await structured.ainvoke(messages)
    logger.info(
        "run_plan: %d points, %d constructions, %d expected_properties",
        len(plan.points), len(plan.constructions), len(plan.expected_properties),
    )
    return plan, {"plan": plan}


async def run_code_from_plan(
    plan: GeometricPlan,
    prompt: str,
    model: str = DEFAULT_AGENT_MODEL,
    model_settings: dict | None = None,
):
    """Code stage: translate a GeometricPlan into TikZ and render it."""
    from .llm import get_chat_model
    from langgraph.prebuilt import create_react_agent

    llm = get_chat_model(model)
    render_tool = make_render_tool_with_plan_check(plan)
    graph = create_react_agent(llm, tools=[render_tool], prompt=CODE_FROM_PLAN_INSTRUCTIONS)
    user_message = (
        f"Original request: {prompt}\n\n"
        f"Geometric plan:\n{plan.model_dump_json(indent=2)}\n\n"
        f"Generate TikZ code for this diagram according to the plan, "
        f"then call render_diagram."
    )
    return await graph.ainvoke({"messages": [("user", user_message)]})


async def run_revision(
    model: str,
    message_history: list[BaseMessage],
    force_rerender: bool = True,
    model_settings: dict | None = None,
    run_config: dict | None = None,
):
    """Revision stage: review and re-render the diagram.

    Args:
        model: LLM model identifier.
        message_history: Messages from the prior agent run (e.g. draft).
        force_rerender: If True (default), the revision agent MUST call render_diagram.
    """
    from .llm import get_chat_model
    from langgraph.prebuilt import create_react_agent

    instructions = REVISION_FORCE_INSTRUCTIONS if force_rerender else REVISION_INSTRUCTIONS
    llm = get_chat_model(model)
    render_tool = make_render_tool()
    graph = create_react_agent(llm, tools=[render_tool], prompt=instructions)
    messages = list(message_history) + [("user", REVISION_PROMPT)]
    return await graph.ainvoke({"messages": messages}, config=run_config or {})
