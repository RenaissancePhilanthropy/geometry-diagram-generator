from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import sympy.geometry as spg

from pydantic_ai import Agent, ModelRetry

from strategies.base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from strategies.instructions import STRUCTURED_STRATEGY_IR_INSTRUCTIONS
from strategies.prompt_hints import augment_structured_prompt
from ir.ir import DiagramIR
from ir.to_sympy import compile_defs
from ir.checks import run_checks, check_render_angles, CheckResult
from ir.to_tikz import ir_to_tikz
from ir.errors import IRCompileError
from util.tikz_renderer import render_tikz

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
        agent = Agent(model, instructions=_BUILD_AGENT_INSTRUCTIONS)

        @agent.tool_plain(retries=MAX_RETRIES)
        async def generate_diagram(request: str) -> str:
            """Generate a geometry diagram from the user's request.

            Returns JSON with an SVG field on success.
            """
            return await _run_pipeline_once(request, model)

        return agent

    async def run(self, prompt: str, model: str = DEFAULT_AGENT_MODEL) -> StructuredRunResult:
        """Run the full IR pipeline with retry on failure.

        Returns a StructuredRunResult with diagram_ir, tikz, and svg.
        """
        last_error: str = ""
        hint_prompt = augment_structured_prompt(prompt)

        for attempt in range(MAX_RETRIES):
            user_prompt = hint_prompt
            if attempt > 0:
                user_prompt = (
                    f"{hint_prompt}\n\n"
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

            # Step 4: Generate TikZ deterministically
            try:
                tikz = ir_to_tikz(diagram_ir, sym)
            except Exception as e:
                last_error = f"TikZ generation failed: {e}"
                logger.warning("Attempt %d tikz generation error: %s", attempt + 1, e)
                continue

            logger.info("Generated TikZ (%d chars)", len(tikz))
            logger.debug("TikZ:\n%s", tikz)

            # Step 5: Render to SVG
            try:
                svg = render_tikz(tikz)
            except RuntimeError as e:
                last_error = f"TikZ rendering failed: {e}"
                logger.warning("Attempt %d render error: %s", attempt + 1, e)
                continue

            logger.info("Rendered SVG (%d chars)", len(svg))
            sym_float = {
                k: (float(v.x), float(v.y))
                for k, v in sym.items()
                if isinstance(v, spg.Point)
            }
            return StructuredRunResult(diagram_ir=diagram_ir, tikz=tikz, svg=svg, sym_table=sym_float)

        raise RuntimeError(
            f"StructureStrategy failed after {MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        )


async def _run_pipeline_once(prompt: str, model: str) -> str:
    """Run the full IR pipeline for a single attempt.

    Used by build_agent's generate_diagram tool. Raises ModelRetry on failure
    so the outer agent can retry with the error context.
    """
    ir_agent = Agent(
        model,
        instructions=STRUCTURED_STRATEGY_IR_INSTRUCTIONS,
        output_type=DiagramIR,
    )
    response = await ir_agent.run(augment_structured_prompt(prompt))
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

    try:
        tikz = ir_to_tikz(diagram_ir, sym)
    except Exception as e:
        raise ModelRetry(f"TikZ generation failed: {e}") from e

    try:
        svg = render_tikz(tikz)
    except RuntimeError as e:
        raise ModelRetry(f"TikZ rendering failed: {e}") from e

    return json.dumps({"svg": svg})
