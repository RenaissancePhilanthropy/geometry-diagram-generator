from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import sympy.geometry as spg

from pydantic_ai import Agent, ModelRetry

from strategies.base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from strategies.instructions import STRUCTURED_STRATEGY_IR_INSTRUCTIONS
from ir.ir import DiagramIR
from ir.to_sympy import compile_defs
from ir.checks import run_checks, check_render_angles, CheckResult
from ir.renderer import Renderer, TikZRenderer
from ir.errors import IRCompileError
from ir.queries import (
    query_coordinate, query_distance, query_angle,
    query_length, query_radius, query_area, query_perimeter, list_objects,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3

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
class StructuredRunResult:
    """Result of a StructuredStrategy run."""
    diagram_ir: DiagramIR
    tikz: str
    svg: str
    sym_table: dict | None = None  # SymPy symbol table float coords, runtime-only
    sym_full: dict | None = None   # full SymPy SymTable for querying
    input_tokens: int = 0
    output_tokens: int = 0
    recipe_metadata: "RecipeMetadata | None" = None


def _arg(args: dict[str, str], *keys: str) -> str:
    """Return the first value found among the given keys, or raise KeyError."""
    for k in keys:
        if k in args:
            return args[k]
    raise KeyError(f"Missing required arg — expected one of: {', '.join(keys)}")


def dispatch_query(sym: dict, query_type: str, args: dict[str, str]) -> str:
    """Dispatch a query_type + args to the appropriate ir.queries function."""
    try:
        match query_type:
            case "coordinate":
                result = query_coordinate(sym, args["point"])
            case "distance":
                result = query_distance(
                    sym,
                    _arg(args, "a", "point1", "from"),
                    _arg(args, "b", "point2", "to"),
                )
            case "angle":
                result = query_angle(
                    sym,
                    _arg(args, "ray1", "a", "point1", "from"),
                    args["vertex"],
                    _arg(args, "ray2", "b", "point2", "to"),
                )
            case "length":
                result = query_length(sym, args["segment"])
            case "radius":
                result = query_radius(sym, args["circle"])
            case "area":
                result = query_area(sym, args["object"])
            case "perimeter":
                result = query_perimeter(sym, args["object"])
            case "list_objects":
                result = list_objects(sym)
            case _:
                result = {"error": f"Unknown query type: {query_type!r}"}
        return json.dumps(result)
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        return json.dumps({"error": str(e)})


class StructureStrategy(SubstanceStrategy):
    """
    IR-based geometry diagram strategy.

    Pipeline:
        LLM → DiagramIR (structured output)
        → compile_defs (SymPy resolution + coordinate extraction)
        → run_checks (geometric invariant validation)
        → Renderer.render() (TikZ generation + SVG compilation)

    On compilation, check, or render failures the LLM is re-prompted with the
    error description for up to MAX_RETRIES attempts.
    """

    def build_agent(self, model: str = DEFAULT_AGENT_MODEL) -> Agent:
        """Return a conversational agent with render_diagram and query_diagram tools."""
        _renderer = TikZRenderer()  # build_agent always uses the default TikZ renderer
        _last_sym: dict | None = None  # persisted across tool calls within this agent
        _last_ir: DiagramIR | None = None  # last successful IR for edit context

        agent = Agent(model, instructions=_BUILD_AGENT_INSTRUCTIONS)

        @agent.tool_plain(retries=MAX_RETRIES)
        async def render_diagram(request: str) -> str:
            """Generate a geometry diagram from the user's request.

            Returns JSON with an SVG field on success.
            """
            nonlocal _last_sym, _last_ir
            result_json, sym, diagram_ir = await _run_pipeline_once(
                request, model, renderer=_renderer, previous_ir=_last_ir
            )
            _last_sym = sym
            _last_ir = diagram_ir
            return result_json

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
                return json.dumps({"error": "No diagram has been rendered yet. Please generate a diagram first."})
            return dispatch_query(_last_sym, query_type, args)

        return agent

    async def run(self, prompt: str, model: str = DEFAULT_AGENT_MODEL, renderer: Renderer | None = None) -> StructuredRunResult:
        """Run the full IR pipeline with retry on failure.

        Returns a StructuredRunResult with diagram_ir, tikz, and svg.
        """
        _renderer = renderer if renderer is not None else TikZRenderer()
        last_error: str = ""
        total_input_tokens: int = 0
        total_output_tokens: int = 0

        for attempt in range(MAX_RETRIES):
            user_prompt = prompt
            if attempt > 0:
                user_prompt = (
                    f"{prompt}\n\n"
                    f"Previous attempt failed: {last_error}\n"
                    f"Please produce a corrected DiagramIR."
                )

            # Step 1: LLM generates DiagramIR
            ir_agent = Agent(
                model,
                instructions=STRUCTURED_STRATEGY_IR_INSTRUCTIONS,
                output_type=DiagramIR,
            )
            response = await ir_agent.run(user_prompt)
            usage = response.usage()
            total_input_tokens += usage.input_tokens or 0
            total_output_tokens += usage.output_tokens or 0
            diagram_ir = response.output
            logger.info(
                "Attempt %d: DiagramIR has %d defs, %d checks, %d render ops",
                attempt + 1,
                len(diagram_ir.define),
                len(diagram_ir.checks),
                len(diagram_ir.render),
            )
            logger.debug("DiagramIR:\n%s", diagram_ir.model_dump_json(indent=2))

            # Step 2: Compile IR → SymPy symbol table
            try:
                sym = compile_defs(diagram_ir)
            except IRCompileError as e:
                last_error = f"IR compilation failed: {e}"
                logger.warning("Attempt %d compile error: %s", attempt + 1, e)
                continue

            # Step 3: Run geometric checks
            results: list[CheckResult] = run_checks(diagram_ir.checks, sym)
            must_failures = [r for r in results if not r.passed and r.check.level == "must"]
            if must_failures:
                msgs = "\n".join(f"  - {r.message}" for r in must_failures)
                last_error = f"Geometric checks failed:\n{msgs}"
                logger.warning("Attempt %d check failures:\n%s", attempt + 1, msgs)
                continue

            angle_errors = check_render_angles(diagram_ir)
            if angle_errors:
                msgs = "\n".join(f"  - {e}" for e in angle_errors)
                last_error = f"Invalid angle triples in render ops:\n{msgs}"
                logger.warning("Attempt %d angle triple errors:\n%s", attempt + 1, msgs)
                continue

            for r in results:
                if not r.passed and r.check.level == "prefer":
                    logger.warning("Preferred check not satisfied: %s", r.message)

            # Step 4+5: Render — code generation + compilation via renderer
            try:
                render_result = _renderer.render(diagram_ir, sym)
            except Exception as e:
                last_error = f"Rendering failed: {e}"
                logger.warning("Attempt %d render error: %s", attempt + 1, e)
                continue

            tikz = render_result.intermediate
            svg = render_result.output
            logger.info("Rendered %s (%d chars), intermediate=%d chars",
                        render_result.format, len(svg), len(tikz))
            logger.debug("Intermediate:\n%s", tikz)
            sym_float = {
                k: (float(v.x), float(v.y))
                for k, v in sym.items()
                if isinstance(v, spg.Point)
            }
            return StructuredRunResult(
                diagram_ir=diagram_ir,
                tikz=tikz,
                svg=svg,
                sym_table=sym_float,
                sym_full=sym,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
            )

        raise RuntimeError(
            f"StructureStrategy failed after {MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        )


async def _run_ir_pipeline(
    diagram_ir: DiagramIR,
    renderer: "Renderer | None" = None,
) -> StructuredRunResult:
    """Run the compile → check → tikz → render pipeline on a pre-built DiagramIR.

    Raises on failure so the caller can handle retries.
    """
    try:
        sym = compile_defs(diagram_ir)
    except IRCompileError as e:
        raise RuntimeError(f"IR compilation failed: {e}") from e

    results: list[CheckResult] = run_checks(diagram_ir.checks, sym)
    must_failures = [r for r in results if not r.passed and r.check.level == "must"]
    if must_failures:
        msgs = "\n".join(f"  - {r.message}" for r in must_failures)
        raise RuntimeError(f"Geometric checks failed:\n{msgs}")

    angle_errors = check_render_angles(diagram_ir)
    if angle_errors:
        msgs = "\n".join(f"  - {e}" for e in angle_errors)
        raise RuntimeError(f"Invalid angle triples in render ops:\n{msgs}")

    for r in results:
        if not r.passed and r.check.level == "prefer":
            logger.warning("Preferred check not satisfied: %s", r.message)

    _renderer = renderer if renderer is not None else TikZRenderer()
    try:
        render_result = _renderer.render(diagram_ir, sym)
    except Exception as e:
        raise RuntimeError(f"Rendering failed: {e}") from e

    tikz = render_result.intermediate
    svg = render_result.output
    sym_float = {
        k: (float(v.x), float(v.y))
        for k, v in sym.items()
        if isinstance(v, spg.Point)
    }
    return StructuredRunResult(diagram_ir=diagram_ir, tikz=tikz, svg=svg, sym_table=sym_float, sym_full=sym)


async def _run_pipeline_once(
    prompt: str,
    model: str,
    renderer: Renderer | None = None,
    previous_ir: DiagramIR | None = None,
) -> tuple[str, dict, DiagramIR]:
    """Run the full IR pipeline for a single attempt.

    Used by build_agent's render_diagram tool. Raises ModelRetry on failure
    so the outer agent can retry with the error context.
    Returns a tuple of (result_json, sym, diagram_ir).
    """
    if previous_ir is not None:
        full_prompt = (
            f"{prompt}\n\n"
            "---\n"
            "The user previously had this diagram rendered successfully. Use it as the "
            "starting point and apply the requested modifications. Preserve all properties "
            "(angles, lengths, positions, labels, etc.) that the user did not ask to change.\n\n"
            f"Previous DiagramIR:\n{previous_ir.model_dump_json(indent=2)}\n"
            "---"
        )
    else:
        full_prompt = prompt

    ir_agent = Agent(
        model,
        instructions=STRUCTURED_STRATEGY_IR_INSTRUCTIONS,
        output_type=DiagramIR,
    )
    response = await ir_agent.run(full_prompt)
    diagram_ir = response.output

    try:
        sym = compile_defs(diagram_ir)
    except IRCompileError as e:
        raise ModelRetry(f"IR compilation failed: {e}") from e

    results = run_checks(diagram_ir.checks, sym)
    must_failures = [r for r in results if not r.passed and r.check.level == "must"]
    if must_failures:
        msgs = "; ".join(r.message for r in must_failures)
        raise ModelRetry(f"Geometric checks failed: {msgs}")

    angle_errors = check_render_angles(diagram_ir)
    if angle_errors:
        raise ModelRetry(f"Invalid angle triples: {'; '.join(angle_errors)}")

    _renderer = renderer if renderer is not None else TikZRenderer()
    try:
        render_result = _renderer.render(diagram_ir, sym)
    except Exception as e:
        raise ModelRetry(f"Rendering failed: {e}") from e

    return json.dumps({"svg": render_result.output}), sym, diagram_ir
