from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

import pydantic
from pydantic_ai import Agent

from strategies.base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from strategies.structured import StructuredRunResult, _run_ir_pipeline, _dispatch_query
from strategies.instructions import RECIPE_SELECTION_SYSTEM, RECIPE_GENERATION_SYSTEM
from recipe.catalog import (
    load_catalog,
    load_recipe,
    build_selection_prompt,
    build_generation_prompt,
    DSL_DOCS,
    Recipe,
)
from recipe.dsl import RecipeDSL
from recipe.lower import lower_to_ir, LoweringError
from ir.renderer import TikZRenderer, Renderer

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
_SELECTOR_MODEL = "anthropic:claude-haiku-4-5-20251001"

_BUILD_AGENT_INSTRUCTIONS = """\
You are a geometry diagram assistant. When the user asks you to draw a diagram, \
call the render_diagram tool with their request, then briefly explain what was drawn.

After a diagram is rendered, you can answer questions about its geometric properties \
(coordinates, distances, angles, lengths, areas, etc.) by calling query_diagram with \
the appropriate query_type and args. To see available object IDs, call query_diagram \
with query_type="list_objects" and args={}.
"""


@dataclass
class RecipeAttemptTrace:
    attempt: int
    dsl_json: dict | None  # model_dump() of the RecipeDSL the LLM produced
    error: str | None       # error message if this attempt failed
    stage: str              # "lowering", "ir_pipeline", or "success"


@dataclass
class RecipeMetadata:
    selected_recipes: list[str] = field(default_factory=list)
    unmatched_concepts: list[str] = field(default_factory=list)
    selection_input_tokens: int = 0
    selection_output_tokens: int = 0
    attempt_traces: list[RecipeAttemptTrace] = field(default_factory=list)


class RecipeStrategy(SubstanceStrategy):
    """
    Recipe-based geometry diagram strategy.

    Pipeline:
        (Optional) cheap model selects relevant recipes from catalog
        → Main model generates RecipeDSL JSON using selected recipes + DSL docs
        → lower_to_ir(dsl) compiles RecipeDSL to DiagramIR
        → compile_defs → run_checks → Renderer.render()

    On lowering, check, or render failures the main model is re-prompted with
    the error description for up to MAX_RETRIES attempts.
    """

    def __init__(self, use_recipes: bool = True) -> None:
        super().__init__()
        self.use_recipes = use_recipes

    def build_agent(self, model: str = DEFAULT_AGENT_MODEL) -> Agent:
        """Return a conversational agent with render_diagram and query_diagram tools."""
        _renderer = TikZRenderer()
        _strategy = self
        _last_sym: dict | None = None

        agent = Agent(model, instructions=_BUILD_AGENT_INSTRUCTIONS)

        @agent.tool_plain(retries=MAX_RETRIES)
        async def render_diagram(request: str) -> str:
            """Generate a geometry diagram from the user's request.

            Returns JSON with an SVG field on success.
            """
            nonlocal _last_sym
            result = await _strategy.run(request, model, renderer=_renderer)
            _last_sym = result.sym_full
            return json.dumps({"svg": result.svg})

        @agent.tool_plain
        async def query_diagram(query_type: str, args: dict[str, str]) -> str:
            """Query a geometric property of the current diagram.

            query_type and args:
              coordinate  {"point": "A"}           → x, y coords
              distance    {"a": "A", "b": "B"}     → distance between points
              angle       {"a": "A", "vertex": "B", "b": "C"} → angle in degrees
              length      {"segment": "seg_AB"}    → segment length
              radius      {"circle": "c1"}         → circle radius
              area        {"object": "tri_ABC"}    → area
              perimeter   {"object": "tri_ABC"}    → perimeter
              list_objects {}                       → all objects and their types
            """
            if _last_sym is None:
                return json.dumps({"error": "No diagram has been rendered yet."})
            return _dispatch_query(_last_sym, query_type, args)

        return agent

    async def run(
        self,
        prompt: str,
        model: str = DEFAULT_AGENT_MODEL,
        renderer: Renderer | None = None,
    ) -> StructuredRunResult:
        """Run the full recipe pipeline with retry on failure."""
        _renderer = renderer if renderer is not None else TikZRenderer()

        # --- Step 1: Recipe selection (optional) ---
        recipe_metadata = RecipeMetadata()

        if self.use_recipes:
            catalog = load_catalog()
            selection_prompt = build_selection_prompt(prompt, catalog)
            selector_agent: Agent[None, str] = Agent(
                _SELECTOR_MODEL,
                instructions=RECIPE_SELECTION_SYSTEM,
                output_type=str,
            )
            sel_response = await selector_agent.run(selection_prompt)
            sel_usage = sel_response.usage()
            recipe_metadata.selection_input_tokens = sel_usage.input_tokens or 0
            recipe_metadata.selection_output_tokens = sel_usage.output_tokens or 0

            raw_text = sel_response.output
            selected_ids: list[str] = []
            unmatched_concepts: list[str] = []
            try:
                # Strip markdown code fences if the model wrapped its output
                text = raw_text.strip()
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                    text = text.strip()
                parsed = json.loads(text)
                selected_ids = parsed.get("selected_recipes", parsed.get("selected", []))
                unmatched_concepts = parsed.get("unmatched_concepts", [])
            except (json.JSONDecodeError, AttributeError):
                logger.warning("Recipe selection JSON parse failed; treating as empty selection. Raw: %r", raw_text[:200])

            recipes: list[Recipe] = []
            for rid in selected_ids:
                try:
                    recipes.append(load_recipe(rid))
                    recipe_metadata.selected_recipes.append(rid)
                except KeyError:
                    logger.warning("Selected recipe %r not found in catalog; skipping", rid)

            recipe_metadata.unmatched_concepts = unmatched_concepts
            generation_prompt = build_generation_prompt(prompt, recipes, DSL_DOCS)
        else:
            generation_prompt = build_generation_prompt(prompt, [], DSL_DOCS)

        # Expose partial metadata on self so the eval harness can access it even on failure
        self._partial_recipe_metadata = recipe_metadata

        # --- Step 2: Retry loop ---
        last_error: str = ""
        total_input_tokens: int = recipe_metadata.selection_input_tokens
        total_output_tokens: int = recipe_metadata.selection_output_tokens
        self._partial_input_tokens = total_input_tokens
        self._partial_output_tokens = total_output_tokens

        for attempt in range(MAX_RETRIES):
            user_message = generation_prompt
            if attempt > 0:
                user_message = (
                    f"{generation_prompt}\n\n"
                    f"Previous attempt failed: {last_error}\n"
                    f"Please produce a corrected RecipeDSL."
                )

            gen_agent: Agent[None, RecipeDSL] = Agent(
                model,
                instructions=RECIPE_GENERATION_SYSTEM,
                output_type=RecipeDSL,
            )
            response = await gen_agent.run(user_message)
            usage = response.usage()
            total_input_tokens += usage.input_tokens or 0
            total_output_tokens += usage.output_tokens or 0
            self._partial_input_tokens = total_input_tokens
            self._partial_output_tokens = total_output_tokens
            dsl = response.output
            logger.info(
                "Attempt %d: RecipeDSL has %d construction ops",
                attempt + 1,
                len(dsl.construction),
            )
            logger.debug("Attempt %d DSL: %s", attempt + 1, dsl.model_dump_json(indent=2))

            # Lowering
            try:
                diagram_ir = lower_to_ir(dsl)
            except (LoweringError, pydantic.ValidationError) as e:
                last_error = f"Lowering failed: {e}"
                logger.warning("Attempt %d lowering error: %s", attempt + 1, e)
                recipe_metadata.attempt_traces.append(RecipeAttemptTrace(
                    attempt=attempt + 1,
                    dsl_json=dsl.model_dump(),
                    error=last_error,
                    stage="lowering",
                ))
                continue

            logger.debug(
                "Attempt %d lowered IR: %d render ops, %d styles: %s",
                attempt + 1,
                len(diagram_ir.render),
                len(diagram_ir.styles),
                [op.kind for op in diagram_ir.render],
            )

            # IR pipeline
            try:
                result = await _run_ir_pipeline(diagram_ir, _renderer)
            except RuntimeError as e:
                last_error = str(e)
                logger.warning("Attempt %d IR pipeline error: %s", attempt + 1, e)
                recipe_metadata.attempt_traces.append(RecipeAttemptTrace(
                    attempt=attempt + 1,
                    dsl_json=dsl.model_dump(),
                    error=last_error,
                    stage="ir_pipeline",
                ))
                continue

            recipe_metadata.attempt_traces.append(RecipeAttemptTrace(
                attempt=attempt + 1,
                dsl_json=dsl.model_dump(),
                error=None,
                stage="success",
            ))
            return StructuredRunResult(
                diagram_ir=result.diagram_ir,
                tikz=result.tikz,
                svg=result.svg,
                sym_table=result.sym_table,
                sym_full=result.sym_full,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                recipe_metadata=recipe_metadata,
            )

        raise RuntimeError(
            f"RecipeStrategy failed after {MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        )
