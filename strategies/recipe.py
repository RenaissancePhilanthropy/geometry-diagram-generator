from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field

import pydantic
from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior, ToolRetryError
from pydantic_ai.messages import ModelResponse, ModelRequest, ToolCallPart, TextPart, RetryPromptPart, ThinkingPart

from strategies.base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from strategies.structured import StructureStrategy, StructuredRunResult, _run_ir_pipeline, dispatch_query
from strategies.instructions import RECIPE_SELECTION_SYSTEM, RECIPE_GENERATION_SYSTEM
from strategies.recipe_hints import HINT_PATTERNS, HINT_TEXTS
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
_SELECTOR_MODEL = "ollama:gemma4:31b-cloud"

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
the appropriate query_type and args. To see available object IDs, call query_diagram \
with query_type="list_objects" and args={}.
"""


@dataclass
class RecipeAttemptTrace:
    attempt: int
    dsl_json: dict | None  # model_dump() of the RecipeDSL the LLM produced
    error: str | None       # error message if this attempt failed
    stage: str              # "lowering", "ir_pipeline", "output_validation", or "success"
    raw_output: str | None = None  # raw payload from model on output_validation failure
    cot: str | None = None  # chain-of-thought (ThinkingPart content) captured for this attempt


def _extract_cot(messages: list) -> str | None:
    """Join all ThinkingPart contents from the captured agent messages.

    Returns the concatenated chain-of-thought, or None if no thinking was
    produced (e.g. thinking disabled, or a model/provider that doesn't emit it).
    Used for downstream confidence analysis of the produced answer.
    """
    parts: list[str] = []
    for msg in messages:
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ThinkingPart) and part.content:
                    parts.append(part.content)
    return "\n\n".join(parts) if parts else None


def _extract_failure_diagnostics(
    exc: UnexpectedModelBehavior,
    messages: list,
) -> tuple[str, str | None]:
    """Extract a human-readable error summary and raw model payload from a failed agent run.

    Returns (summary_str, raw_payload_or_None).
    """
    # --- Raw payload: last ModelResponse's ToolCallPart or TextPart ---
    raw_payload: str | None = None
    for msg in reversed(messages):
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    raw_payload = part.args_as_json_str()
                    break
                if isinstance(part, TextPart):
                    raw_payload = part.content
                    break
            if raw_payload is not None:
                break

    # --- Validation errors: walk exception chain first ---
    error_lines: list[str] = []
    cause = exc.__cause__
    while cause is not None:
        if isinstance(cause, pydantic.ValidationError):
            raw_errors = cause.errors(include_url=False)
            from recipe.dsl import enrich_extra_forbidden_errors
            enriched_errors = enrich_extra_forbidden_errors(raw_errors)
            for err in enriched_errors:
                loc = ".".join(str(x) for x in err.get("loc", ()))
                error_lines.append(f"  loc={loc!r} type={err.get('type')!r} msg={err.get('msg')!r}")
            break
        cause = getattr(cause, "__cause__", None)

    # --- Fallback: scan RetryPromptPart in message history ---
    if not error_lines:
        for msg in reversed(messages):
            if isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if isinstance(part, RetryPromptPart) and isinstance(part.content, list):
                        from recipe.dsl import enrich_extra_forbidden_errors
                        enriched_content = enrich_extra_forbidden_errors(part.content)
                        for err_detail in enriched_content:
                            loc = ".".join(str(x) for x in err_detail.get("loc", ()))
                            error_lines.append(
                                f"  loc={loc!r} type={err_detail.get('type')!r} msg={err_detail.get('msg')!r}"
                            )
                        break
                if error_lines:
                    break

    if error_lines:
        summary = "Output validation failed:\n" + "\n".join(error_lines)
    else:
        summary = f"Output validation failed: {exc}"

    return summary, raw_payload


@dataclass
class RecipeMetadata:
    selected_recipes: list[str] = field(default_factory=list)
    unmatched_concepts: list[str] = field(default_factory=list)
    selection_input_tokens: int = 0
    selection_output_tokens: int = 0
    attempt_traces: list[RecipeAttemptTrace] = field(default_factory=list)
    cot: str | None = None  # chain-of-thought of the successful attempt (the answer's reasoning)


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

    def __init__(self, use_recipes: bool = True, enable_cache: bool = False, catalog: str = "default", renderer: Renderer | None = None, thinking: bool = False, prompt_overrides: dict[str, str] | None = None) -> None:
        super().__init__(enable_cache=enable_cache, thinking=thinking)
        self.use_recipes = use_recipes
        self.catalog = catalog
        self.renderer = renderer
        self.prompt_overrides = prompt_overrides or {}

    def build_agent(self, model: str = DEFAULT_AGENT_MODEL) -> Agent:
        """Return a conversational agent with render_diagram and query_diagram tools."""
        _renderer = self.renderer if self.renderer is not None else TikZRenderer()
        _strategy = self
        _last_sym: dict | None = None
        _last_dsl_json: dict | None = None  # last successful DSL for edit context

        agent = Agent(model, instructions=_BUILD_AGENT_INSTRUCTIONS, model_settings=self.model_settings)

        @agent.tool_plain(retries=MAX_RETRIES)
        async def render_diagram(request: str) -> str:
            """Generate a geometry diagram from the user's request.

            Returns JSON with an SVG field on success.
            """
            nonlocal _last_sym, _last_dsl_json
            result = await _strategy.run(request, model, renderer=_renderer, previous_dsl_json=_last_dsl_json)
            _last_sym = result.sym_full
            traces = result.recipe_metadata.attempt_traces if result.recipe_metadata else []
            successful = [t for t in traces if t.stage == "success"]
            _last_dsl_json = successful[-1].dsl_json if successful else _last_dsl_json
            return json.dumps({"svg": result.svg})

        @agent.tool_plain
        async def query_diagram(query_type: str, args: dict[str, str]) -> str:
            """Query a geometric property of the current diagram.

            query_type and args:
              coordinate  {"point": "A"}           → x, y coords
              distance    {"a": "A", "b": "B"}     → distance between points (use for side lengths too)
              angle       {"ray1": "A", "vertex": "B", "ray2": "C"} → angle in degrees
              length      {"segment": "seg_AB"}    → segment length
              radius      {"circle": "c1"}         → circle radius
              area        {"object": "tri_ABC"}    → area
              perimeter   {"object": "tri_ABC"}    → perimeter
              list_objects {}                       → all objects and their types
            """
            if _last_sym is None:
                return json.dumps({"error": "No diagram has been rendered yet."})
            return dispatch_query(_last_sym, query_type, args)

        return agent

    async def run(
        self,
        prompt: str,
        model: str = DEFAULT_AGENT_MODEL,
        renderer: Renderer | None = None,
        previous_dsl_json: dict | None = None,
    ) -> StructuredRunResult:
        """Run the full recipe pipeline with retry on failure."""
        _renderer = renderer if renderer is not None else TikZRenderer()

        # --- Step 1: Recipe selection (optional) ---
        recipe_metadata = RecipeMetadata()

        if self.use_recipes:
            catalog = load_catalog(self.catalog)
            selection_prompt = build_selection_prompt(prompt, catalog)
            selector_agent: Agent[None, str] = Agent(
                _SELECTOR_MODEL,
                instructions=self.prompt_overrides.get("selection_system", RECIPE_SELECTION_SYSTEM),
                output_type=str,
                model_settings=self.model_settings,
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
                    recipes.append(load_recipe(rid, catalog=self.catalog))
                    recipe_metadata.selected_recipes.append(rid)
                except KeyError:
                    logger.warning("Selected recipe %r not found in catalog; skipping", rid)

            recipe_metadata.unmatched_concepts = unmatched_concepts
            generation_prompt = build_generation_prompt(prompt, recipes, self.prompt_overrides.get("dsl_docs", DSL_DOCS))
        else:
            generation_prompt = build_generation_prompt(prompt, [], self.prompt_overrides.get("dsl_docs", DSL_DOCS))

        if previous_dsl_json is not None:
            generation_prompt = (
                f"{generation_prompt}\n\n"
                "---\n"
                "The user previously had this diagram rendered successfully. Use it as the "
                "starting point and apply the requested modifications. Preserve all properties "
                "(angles, lengths, positions, labels, etc.) that the user did not ask to change.\n\n"
                f"Previous RecipeDSL:\n{json.dumps(previous_dsl_json, indent=2)}\n"
                "---"
            )

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
                retry_msg = f"{generation_prompt}\n\nPrevious attempt failed: {last_error}\n"

                # Append targeted hints based on error patterns
                for pattern, hint_key in HINT_PATTERNS:
                    if pattern.search(last_error):
                        hint_text = self.prompt_overrides.get(hint_key, HINT_TEXTS[hint_key])
                        retry_msg += f"\nHINT: {hint_text}\n"

                        # Dynamic context for specific hint types
                        if hint_key == "hint_right_angle":
                            # Extract candidate right-angle triples from the error message.
                            candidates = re.findall(
                                r"right angles at (\S+): ((?:\S+=90\.0°(?:, )?)+)",
                                last_error,
                            )
                            if candidates:
                                retry_msg += (
                                    " The checker found right angles at the same vertex using"
                                    " DIFFERENT point triples — use one of these instead:\n"
                                )
                                for vertex, cands in candidates:
                                    retry_msg += f"    At {vertex}: {cands}\n"
                                retry_msg += (
                                    " Change your mark_right_angle to use one of these triples"
                                    " (a, vertex, b) that actually measure 90°.\n"
                                )
                            else:
                                retry_msg += (
                                    " Use point_foot to project the point onto the line:"
                                    " `{op: 'point_foot', id: 'X', source: 'P', onto: 'seg_AB'}`"
                                    " guarantees angle P-X-endpoint = 90°. Do not place the foot"
                                    " manually with point_along or fixed coordinates — only"
                                    " point_foot guarantees the right angle.\n"
                                )

                        elif hint_key == "hint_mark_angle":
                            # Extract candidates from both lowering and geometric-check formats
                            lowering_cands = re.findall(
                                r"MarkAngle at (\S+):.*?candidates: ((?:\S+=\S+?°(?:, )?)+)",
                                last_error,
                            )
                            geo_cands = re.findall(
                                r"at (\S+) try: ((?:\S+=\S+?°(?:; )?)+)",
                                last_error,
                            )
                            all_cands = lowering_cands + geo_cands
                            if all_cands:
                                retry_msg += (
                                    " The checker found angle pairs that ARE"
                                    " equal at the same vertex(es) — use one of these instead:\n"
                                )
                                for vertex, cands in all_cands:
                                    retry_msg += f"    At {vertex}: {cands}\n"
                                retry_msg += (
                                    " Change your mark_angle to use point triples that actually"
                                    " produce equal angles. If using two separate triangles, ensure"
                                    " they are geometrically similar (same angles or proportional sides).\n"
                                )

                        elif hint_key == "hint_undefined_id":
                            undef_ids = re.findall(r"references undefined id '([^']+)'", last_error)
                            retry_msg += (
                                " Your DSL references id(s) that are not defined in the"
                                " construction list: " + ", ".join(repr(i) for i in set(undef_ids)) + ".\n"
                            )

                retry_msg += "Please produce a corrected RecipeDSL."
                user_message = retry_msg

            gen_agent: Agent[None, RecipeDSL] = Agent(
                model,
                instructions=self.prompt_overrides.get("generation_system", RECIPE_GENERATION_SYSTEM),
                output_type=RecipeDSL,
                model_settings=self.model_settings,
            )
            with capture_run_messages() as agent_messages:
                try:
                    response = await gen_agent.run(user_message)
                except UnexpectedModelBehavior as exc:
                    diag_summary, raw_payload = _extract_failure_diagnostics(exc, agent_messages)
                    last_error = diag_summary
                    logger.warning("Attempt %d output validation failure:\n%s", attempt + 1, diag_summary)
                    if raw_payload:
                        logger.debug("Attempt %d failed payload: %s", attempt + 1, raw_payload[:2000])
                    recipe_metadata.attempt_traces.append(RecipeAttemptTrace(
                        attempt=attempt + 1,
                        dsl_json=None,
                        error=last_error,
                        stage="output_validation",
                        raw_output=raw_payload,
                        cot=_extract_cot(agent_messages),
                    ))
                    continue
            cot = _extract_cot(agent_messages)
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
            except Exception as e:
                # Broadened from (LoweringError, pydantic.ValidationError): SymPy
                # and other lowering-stage errors (e.g. ValueError, AttributeError)
                # must also be caught so the already-captured CoT is preserved in
                # the attempt trace and the loop can retry, rather than propagating
                # and discarding both the trace and the CoT.
                last_error = f"Lowering failed: {e}"
                logger.warning("Attempt %d lowering error: %s", attempt + 1, e)
                recipe_metadata.attempt_traces.append(RecipeAttemptTrace(
                    attempt=attempt + 1,
                    dsl_json=dsl.model_dump(),
                    error=last_error,
                    stage="lowering",
                    cot=cot,
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
            except Exception as e:
                # Broadened from RuntimeError: the IR pipeline compiles to SymPy,
                # which can raise ValueError/AttributeError (e.g.
                # "Line2D.__new__ requires two unique Points.", "Point2D has no
                # attribute 'perpendicular_line'") on degenerate geometry. Catching
                # these preserves the captured CoT in the attempt trace and lets
                # the loop retry / fall back instead of propagating.
                last_error = str(e)
                logger.warning("Attempt %d IR pipeline error: %s", attempt + 1, e)
                recipe_metadata.attempt_traces.append(RecipeAttemptTrace(
                    attempt=attempt + 1,
                    dsl_json=dsl.model_dump(),
                    error=last_error,
                    stage="ir_pipeline",
                    cot=cot,
                ))
                continue

            recipe_metadata.attempt_traces.append(RecipeAttemptTrace(
                attempt=attempt + 1,
                dsl_json=dsl.model_dump(),
                error=None,
                stage="success",
                cot=cot,
            ))
            recipe_metadata.cot = cot
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

        # --- Fallback: try Structured strategy (with one retry for transient API errors) ---
        logger.info(
            "RecipeStrategy exhausted %d retries, falling back to StructuredStrategy",
            MAX_RETRIES,
        )
        fallback_strategy = StructureStrategy(enable_cache=False, thinking=self.thinking)
        fallback_exc: Exception | None = None
        for fallback_attempt in range(2):  # 2 attempts to handle transient API errors
            try:
                fallback_result = await fallback_strategy.run(
                    prompt, model=model, renderer=_renderer,
                )
                fallback_result.input_tokens += total_input_tokens
                fallback_result.output_tokens += total_output_tokens
                recipe_metadata.attempt_traces.append(RecipeAttemptTrace(
                    attempt=MAX_RETRIES + 1 + fallback_attempt,
                    dsl_json=None,
                    error=None,
                    stage="fallback_structured_success",
                ))
                # When every recipe attempt failed (so `recipe_metadata.cot`
                # was never set on a success), fall back to the last attempt
                # that *did* capture thinking. The failing recipe attempts'
                # CoT is the informative signal for the confidence judge and
                # for diagnosing *where* generation went wrong — the
                # StructuredStrategy fallback does not collect CoT, so without
                # this the record's top-level `cot` would be None and
                # cot-analysis would skip it entirely.
                if recipe_metadata.cot is None:
                    recipe_metadata.cot = next(
                        (t.cot for t in reversed(recipe_metadata.attempt_traces) if t.cot),
                        None,
                    )
                fallback_result.recipe_metadata = recipe_metadata
                return fallback_result
            except Exception as exc:
                fallback_exc = exc
                # Log the request body that triggered the error for debugging
                if isinstance(exc, ModelHTTPError) and exc.status_code == 400:
                    cause = exc.__cause__
                    if cause is not None and hasattr(cause, 'response') and hasattr(cause.response, 'request'):
                        try:
                            req_body = cause.response.request.content.decode('utf-8')[:5000]
                            logger.warning(
                                "StructuredStrategy fallback attempt %d failed with 400: %s\nRequest body:\n%s",
                                fallback_attempt + 1,
                                exc,
                                req_body,
                            )
                        except Exception:
                            logger.warning(
                                "StructuredStrategy fallback attempt %d failed: %s",
                                fallback_attempt + 1,
                                exc,
                            )
                    else:
                        logger.warning(
                            "StructuredStrategy fallback attempt %d failed: %s",
                            fallback_attempt + 1,
                            exc,
                        )
                else:
                    logger.warning(
                        "StructuredStrategy fallback attempt %d failed: %s",
                        fallback_attempt + 1,
                        exc,
                    )
                recipe_metadata.attempt_traces.append(RecipeAttemptTrace(
                    attempt=MAX_RETRIES + 1 + fallback_attempt,
                    dsl_json=None,
                    error=str(exc),
                    stage="fallback_structured_failure",
                ))
        # Both fallback attempts failed
        self._partial_recipe_metadata = recipe_metadata
        raise RuntimeError(
            f"RecipeStrategy failed after {MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        ) from fallback_exc
