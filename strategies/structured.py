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

logger = logging.getLogger(__name__)

MAX_RETRIES = 3

_BUILD_AGENT_INSTRUCTIONS = """\
You are a geometry diagram assistant. When the user asks you to draw a diagram, \
call the generate_diagram tool with their request, then briefly explain what was drawn.
"""


@dataclass
class StructuredRunResult:
    """Result of a StructuredStrategy run."""
    diagram_ir: DiagramIR
    tikz: str
    svg: str
    sym_table: dict | None = None  # SymPy symbol table float coords, runtime-only
    input_tokens: int = 0
    output_tokens: int = 0


class StructureStrategy(SubstanceStrategy):
    """
    IR-based geometry diagram strategy.

    Pipeline:
        LLM → DiagramIR (structured output)
        → compile_defs (SymPy resolution + coordinate extraction)
        → run_checks (geometric invariant validation)
        → ir_to_tikz (deterministic TikZ generation)
        → render_tikz (SVG rendering)

    On compilation, check, or render failures the LLM is re-prompted with the
    error description for up to MAX_RETRIES attempts.
    """

    def build_agent(self, model: str = DEFAULT_AGENT_MODEL) -> Agent:
        """Return a conversational agent with a generate_diagram tool.

        The tool runs the full IR pipeline internally, retrying on failures.
        """
        _renderer = TikZRenderer()  # build_agent always uses the default TikZ renderer
        agent = Agent(model, instructions=_BUILD_AGENT_INSTRUCTIONS)

        @agent.tool_plain(retries=MAX_RETRIES)
        async def generate_diagram(request: str) -> str:
            """Generate a geometry diagram from the user's request.

            Returns JSON with an SVG field on success.
            """
            return await _run_pipeline_once(request, model, renderer=_renderer)

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
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
            )

        raise RuntimeError(
            f"StructureStrategy failed after {MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        )


async def _run_ir_pipeline(
    diagram_ir: DiagramIR,
    renderer=None,
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
    return StructuredRunResult(diagram_ir=diagram_ir, tikz=tikz, svg=svg, sym_table=sym_float)


async def _run_pipeline_once(prompt: str, model: str, renderer: Renderer | None = None) -> str:
    """Run the full IR pipeline for a single attempt.

    Used by build_agent's generate_diagram tool. Raises ModelRetry on failure
    so the outer agent can retry with the error context.
    """
    ir_agent = Agent(
        model,
        instructions=STRUCTURED_STRATEGY_IR_INSTRUCTIONS,
        output_type=DiagramIR,
    )
    response = await ir_agent.run(prompt)
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

    return json.dumps({"svg": render_result.output})
