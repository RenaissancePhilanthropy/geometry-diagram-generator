from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional, TypedDict

import pydantic
from langchain_core.tools import tool
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.exceptions import OutputParserException
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent

from geometry_diagrams.strategies.base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from geometry_diagrams.strategies.structured import StructuredRunResult, _run_ir_pipeline, dispatch_query
from geometry_diagrams.strategies.llm import get_chat_model, extract_usage, make_system_message
from geometry_diagrams.strategies.instructions import RECIPE_SELECTION_SYSTEM, RECIPE_GENERATION_SYSTEM
from geometry_diagrams.recipe.catalog import (
    load_catalog,
    load_recipe,
    build_selection_prompt,
    build_generation_prompt,
    DSL_DOCS,
    Recipe,
)
from geometry_diagrams.recipe.dsl import RecipeDSL
from geometry_diagrams.recipe.lower import lower_to_ir, LoweringError
from geometry_diagrams.ir.errors import IRCompileError
from geometry_diagrams.ir.renderer import TikZRenderer, Renderer

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
_SELECTOR_MODEL = "anthropic:claude-haiku-4-5-20251001"

_BUILD_AGENT_INSTRUCTIONS = """\
You are a geometry diagram assistant. When the user asks you to draw a diagram, \
call the render_diagram tool with their request, then briefly explain what was drawn.

When modifying a previously rendered diagram, pass a complete, self-contained description \
of the desired diagram to render_diagram — not just the change. The system has the \
previous diagram's specification available, but your request should describe the full \
intended result (e.g. "right triangle with legs 3 and 4, now with the hypotenuse labeled" \
rather than just "label the hypotenuse").

After a diagram is rendered, you can answer questions about its geometric properties \
(coordinates, distances, angles, lengths, areas, etc.) by calling query_diagram with \
the appropriate query_type and params. To see available object IDs, call query_diagram \
with query_type="list_objects" and params={}.
"""


# ── metadata types ────────────────────────────────────────────────────────────

@dataclass
class RecipeAttemptTrace:
    attempt: int
    dsl_json: dict | None
    error: str | None
    stage: str  # "output_validation" | "lowering" | "ir_pipeline" | "success"
    raw_output: str | None = None


@dataclass
class RecipeMetadata:
    selected_recipes: list[str] = field(default_factory=list)
    unmatched_concepts: list[str] = field(default_factory=list)
    selection_input_tokens: int = 0
    selection_output_tokens: int = 0
    attempt_traces: list[RecipeAttemptTrace] = field(default_factory=list)


# ── error hint helpers ────────────────────────────────────────────────────────

def _build_retry_hints(last_error: str) -> str:
    """Return contextual hints to append on retry based on the error message."""
    hints = []
    if re.search(r"AngleEqual|angle.*equal", last_error, re.IGNORECASE):
        hints.append(
            "Hint: AngleEqual checks require three distinct points forming each angle. "
            "Ensure the vertex and both rays are separate, named points."
        )
    if re.search(r"mark_right_angle|right.?angle", last_error, re.IGNORECASE):
        hints.append(
            "Hint: mark_right_angle requires exactly three distinct points. "
            "Do not use the same point for vertex and ray endpoint."
        )
    if re.search(r"circular|depends on itself|cycle", last_error, re.IGNORECASE):
        hints.append(
            "Hint: Circular dependency detected. Ensure definitions do not form cycles. "
            "Each object should depend only on previously defined objects."
        )
    if re.search(r"intersection.*outside|outside.*segment|beyond", last_error, re.IGNORECASE):
        hints.append(
            "Hint: An intersection point is outside the expected range. "
            "Check that intersecting objects actually cross within the diagram bounds."
        )
    if re.search(r"point_along.*from.*toward.*same|from.*toward.*same point|direction is undefined", last_error, re.IGNORECASE):
        hints.append(
            "Hint: A point_along op has 'from' and 'toward' pointing to the same point, making direction undefined. "
            "Choose a distinct point for 'toward' that is not the same as 'from'. "
            "For a perpendicular bisector, use a point on the original segment (like A or B) as 'toward', "
            "not the midpoint M."
        )
    return "\n".join(hints)


def _prepare_recipe_modification_prompt(request: str, previous_dsl: Optional[RecipeDSL]) -> str:
    """Append the previous RecipeDSL to *request* when one is available.

    Used by build_agent's render_diagram tool so modification requests carry
    the full context of the prior construction rather than generating from scratch.
    """
    if previous_dsl is None:
        return request
    return (
        f"{request}\n\n"
        "---\n"
        "The user previously had this diagram rendered successfully. Use it as the "
        "starting point and apply the requested modifications. Preserve all properties "
        "(angles, lengths, positions, labels, etc.) that the user did not ask to change.\n\n"
        f"Previous RecipeDSL:\n{previous_dsl.model_dump_json(indent=2)}\n"
        "---"
    )


# ── inner pipeline graph ──────────────────────────────────────────────────────

class RecipePipelineState(TypedDict):
    prompt: str
    model_id: str
    selector_model: str
    enable_cache: bool
    generation_prompt: str
    attempt: int
    last_error: str
    dsl: Optional[RecipeDSL]
    diagram_ir: Optional[Any]
    result: Optional[StructuredRunResult]
    input_tokens: int
    output_tokens: int
    recipe_metadata: RecipeMetadata
    renderer: Optional[Any]
    selection_done: bool


async def _select_recipes_node(state: RecipePipelineState) -> dict:
    """Run the cheap selector model to pick relevant recipes."""
    catalog = load_catalog()
    selection_prompt = build_selection_prompt(state["prompt"], catalog)

    llm = get_chat_model(state.get("selector_model") or _SELECTOR_MODEL)
    from langchain_core.messages import SystemMessage, HumanMessage
    messages = [
        SystemMessage(content=RECIPE_SELECTION_SYSTEM),
        HumanMessage(content=selection_prompt),
    ]
    response = await llm.ainvoke(messages)
    raw_text = response.content if hasattr(response, "content") else str(response)

    in_tok, out_tok = extract_usage(response)

    # Parse JSON response
    selected_recipes = []
    unmatched_concepts = []
    try:
        # Try to find JSON in the response
        json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            selected_recipes = parsed.get("selected_recipes", parsed.get("selected", []))
            unmatched_concepts = parsed.get("unmatched_concepts", [])
    except (json.JSONDecodeError, AttributeError):
        logger.warning(f"Failed to parse selector response as JSON: {raw_text[:200]}")

    # Load selected recipes and build generation prompt
    recipes = []
    valid_recipe_ids = []
    for recipe_id in selected_recipes:
        try:
            recipe = load_recipe(recipe_id)
            recipes.append(recipe)
            valid_recipe_ids.append(recipe_id)
        except Exception:
            pass

    generation_prompt = build_generation_prompt(state["prompt"], recipes, DSL_DOCS)

    metadata = RecipeMetadata(
        selected_recipes=valid_recipe_ids,
        unmatched_concepts=unmatched_concepts,
        selection_input_tokens=in_tok,
        selection_output_tokens=out_tok,
    )

    return {
        "generation_prompt": generation_prompt,
        "recipe_metadata": metadata,
        "input_tokens": state.get("input_tokens", 0) + in_tok,
        "output_tokens": state.get("output_tokens", 0) + out_tok,
        "selection_done": True,
    }


async def _generate_dsl_node(state: RecipePipelineState) -> dict:
    """Call main LLM to generate RecipeDSL structured output."""
    model_id = state["model_id"]
    enable_cache = state.get("enable_cache", False)
    attempt = state["attempt"]
    last_error = state.get("last_error", "")

    user_message = state["generation_prompt"]
    if attempt > 0 and last_error:
        hints = _build_retry_hints(last_error)
        user_message = (
            f"{user_message}\n\n"
            f"Previous attempt failed at stage: {last_error}\n"
            f"Please correct the issue and try again.\n"
            f"{hints}"
        )

    from langchain_core.messages import HumanMessage
    messages = [
        make_system_message(RECIPE_GENERATION_SYSTEM, enable_cache=enable_cache),
        HumanMessage(content=user_message),
    ]

    llm = get_chat_model(model_id, enable_cache=enable_cache)
    structured = llm.with_structured_output(RecipeDSL, include_raw=True)

    raw_content: str | None = None
    in_tok = out_tok = 0
    try:
        # include_raw=True makes ainvoke return a dict at runtime, not BaseModel
        response: Any = await structured.ainvoke(messages)
        raw_msg = response.get("raw")
        dsl = response.get("parsed")
        in_tok, out_tok = extract_usage(raw_msg) if raw_msg else (0, 0)

        # Capture raw content for failure diagnostics
        if raw_msg is not None:
            raw_content = raw_msg.content if isinstance(raw_msg.content, str) else str(raw_msg.content)

        if dsl is None:
            parsing_error = response.get("parsing_error") or "Failed to parse RecipeDSL"
            raise OutputParserException(str(parsing_error))

        metadata = state["recipe_metadata"]
        metadata.attempt_traces.append(RecipeAttemptTrace(
            attempt=attempt + 1,
            dsl_json=dsl.model_dump(),
            error=None,
            stage="success",
        ))
        # Always increment attempt so the retry budget counts DSL gen calls uniformly
        return {
            "dsl": dsl,
            "attempt": attempt + 1,
            "input_tokens": state.get("input_tokens", 0) + in_tok,
            "output_tokens": state.get("output_tokens", 0) + out_tok,
        }
    except (OutputParserException, pydantic.ValidationError) as exc:
        error_msg = str(exc)
        if hasattr(exc, "__cause__") and isinstance(exc.__cause__, pydantic.ValidationError):
            error_msg = f"Output validation error: {exc.__cause__}"
        metadata = state["recipe_metadata"]
        metadata.attempt_traces.append(RecipeAttemptTrace(
            attempt=attempt + 1,
            dsl_json=None,
            error=error_msg,
            stage="output_validation",
            raw_output=raw_content,
        ))
        return {
            "dsl": None,
            "last_error": error_msg,
            "attempt": attempt + 1,
            "input_tokens": state.get("input_tokens", 0) + in_tok,
            "output_tokens": state.get("output_tokens", 0) + out_tok,
        }
    except Exception as exc:
        error_msg = str(exc)
        metadata = state["recipe_metadata"]
        metadata.attempt_traces.append(RecipeAttemptTrace(
            attempt=attempt + 1,
            dsl_json=None,
            error=error_msg,
            stage="output_validation",
            raw_output=raw_content,
        ))
        return {
            "dsl": None,
            "last_error": error_msg,
            "attempt": attempt + 1,
            "input_tokens": state.get("input_tokens", 0) + in_tok,
            "output_tokens": state.get("output_tokens", 0) + out_tok,
        }


async def _run_recipe_pipeline_node(state: RecipePipelineState) -> dict:
    """Lower DSL to IR and run the deterministic pipeline."""
    dsl = state["dsl"]
    assert dsl is not None  # router only sends here when dsl is set
    renderer = state.get("renderer")

    # Lower DSL -> DiagramIR
    try:
        diagram_ir = await asyncio.to_thread(lower_to_ir, dsl)
    except (LoweringError, pydantic.ValidationError, Exception) as e:
        error_msg = f"DSL lowering failed: {e}"
        metadata = state["recipe_metadata"]
        if metadata.attempt_traces:
            metadata.attempt_traces[-1].stage = "lowering"
            metadata.attempt_traces[-1].error = error_msg
        # attempt already incremented by _generate_dsl_node on success
        return {
            "last_error": error_msg,
            "result": None,
            "dsl": None,  # Reset DSL so generate_dsl re-runs
        }

    # Run IR pipeline
    try:
        result = await _run_ir_pipeline(diagram_ir, renderer)
        metadata = state["recipe_metadata"]
        if metadata.attempt_traces:
            metadata.attempt_traces[-1].stage = "success"
        return {
            "result": result,
            "diagram_ir": diagram_ir,
        }
    except (IRCompileError, RuntimeError) as e:
        error_msg = str(e)
        metadata = state["recipe_metadata"]
        if metadata.attempt_traces:
            metadata.attempt_traces[-1].stage = "ir_pipeline"
            metadata.attempt_traces[-1].error = error_msg
        # attempt already incremented by _generate_dsl_node on success
        return {
            "last_error": error_msg,
            "result": None,
            "dsl": None,  # Reset so generate_dsl re-runs
        }


def _after_generate_dsl_router(state: RecipePipelineState) -> str:
    """Route after DSL generation: to pipeline if success, retry or end if failure."""
    if state.get("dsl") is not None:
        return "run_recipe_pipeline"
    if state["attempt"] < MAX_RETRIES:
        return "generate_dsl"
    return END


def _after_pipeline_router(state: RecipePipelineState) -> str:
    """Route after pipeline: end if success, retry or end if failure."""
    if state.get("result") is not None:
        return END
    if state["attempt"] < MAX_RETRIES:
        return "generate_dsl"
    return END


def _build_recipe_graph():
    builder = StateGraph(RecipePipelineState)
    builder.add_node("select_recipes", _select_recipes_node)
    builder.add_node("generate_dsl", _generate_dsl_node)
    builder.add_node("run_recipe_pipeline", _run_recipe_pipeline_node)
    builder.add_edge(START, "select_recipes")
    builder.add_edge("select_recipes", "generate_dsl")
    builder.add_conditional_edges("generate_dsl", _after_generate_dsl_router)
    builder.add_conditional_edges("run_recipe_pipeline", _after_pipeline_router)
    return builder.compile()


# ── strategy class ────────────────────────────────────────────────────────────

class RecipeStrategy(SubstanceStrategy):
    """Recipe-based strategy: selector -> DSL generation -> lower -> IR pipeline."""

    _partial_recipe_metadata: RecipeMetadata | None = None
    _partial_input_tokens: int = 0
    _partial_output_tokens: int = 0

    def __init__(self, enable_cache: bool = False, selector_model: str = _SELECTOR_MODEL):
        super().__init__(enable_cache)
        self.selector_model = selector_model

    async def run(
        self,
        prompt: str,
        model: str = DEFAULT_AGENT_MODEL,
        renderer: Renderer | None = None,
    ) -> StructuredRunResult:
        graph = _build_recipe_graph()
        initial_state: RecipePipelineState = {
            "prompt": prompt,
            "model_id": model,
            "selector_model": self.selector_model,
            "enable_cache": self.enable_cache,
            "generation_prompt": "",
            "attempt": 0,
            "last_error": "",
            "dsl": None,
            "diagram_ir": None,
            "result": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "recipe_metadata": RecipeMetadata(),
            "renderer": renderer,
            "selection_done": False,
        }
        final_state = await graph.ainvoke(initial_state)

        # Expose partial metadata for eval harness
        self._partial_recipe_metadata = final_state.get("recipe_metadata")
        self._partial_input_tokens = final_state.get("input_tokens", 0)
        self._partial_output_tokens = final_state.get("output_tokens", 0)

        if final_state.get("result") is None:
            raise RuntimeError(
                f"RecipeStrategy failed after {MAX_RETRIES} attempts. "
                f"Last error: {final_state.get('last_error', 'unknown')}"
            )
        result = final_state["result"]
        result.recipe_metadata = final_state.get("recipe_metadata")
        result.input_tokens = final_state.get("input_tokens", 0)
        result.output_tokens = final_state.get("output_tokens", 0)
        return result

    def build_agent(self, model: str = DEFAULT_AGENT_MODEL, renderer=None):
        """Return a conversational ReAct agent with render_diagram + query_diagram tools."""
        _last_sym: dict | None = None
        _last_dsl: RecipeDSL | None = None
        _renderer = renderer if renderer is not None else TikZRenderer()

        @tool
        async def render_diagram(request: str) -> str:
            """Render a geometry diagram from a natural language description.

            Args:
                request: Full description of the diagram to render.
            Returns:
                JSON with svg field on success, or error field on failure.
            """
            nonlocal _last_sym, _last_dsl
            try:
                full_request = _prepare_recipe_modification_prompt(request, _last_dsl)
                result = await self.run(full_request, model=model, renderer=_renderer)
                _last_sym = result.sym_full
                if result.recipe_metadata and result.recipe_metadata.attempt_traces:
                    last_trace = result.recipe_metadata.attempt_traces[-1]
                    if last_trace.stage == "success" and last_trace.dsl_json:
                        _last_dsl = RecipeDSL.model_validate(last_trace.dsl_json)
                return json.dumps({"svg": result.svg})
            except Exception as e:
                return json.dumps({"error": str(e)})

        @tool
        def query_diagram(query_type: str, params: Optional[dict[str, Any]] = None) -> str:
            """Query geometric properties of the most recently rendered diagram.

            Args:
                query_type: One of: list_objects, coordinate, distance, angle, length, radius, area, perimeter
                params: Query arguments (e.g. {"id": "A"} for coordinate). Omit or pass {} for list_objects.
            Returns:
                JSON with query result or error.
            """
            if _last_sym is None:
                return json.dumps({"error": "No diagram rendered yet"})
            return dispatch_query(_last_sym, query_type, params or {})

        llm = get_chat_model(model)
        return create_react_agent(llm, tools=[render_diagram, query_diagram], prompt=_BUILD_AGENT_INSTRUCTIONS)
