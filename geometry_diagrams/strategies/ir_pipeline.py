# geometry_diagrams/strategies/ir_pipeline.py
"""Shared deterministic pipeline: compile a DiagramIR, resolve pending angle
pairs, run geometric checks, then render. Used by every strategy that
produces a DiagramIR by whatever means (LLM-authored JSON in structured.py,
sandboxed pydsl script in python_full.py, recipe-lowered IR in recipe.py) —
this stage is identical regardless of how the DiagramIR was produced.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import sympy.geometry as spg

from ..ir.ir import DiagramIR
from ..ir.to_sympy import compile_defs
from ..ir.checks import run_checks, check_render_angles
from ..ir.angle_pairs import resolve_angle_pairs
from ..ir.renderer import Renderer, TikZRenderer

logger = logging.getLogger(__name__)


@dataclass
class StructuredRunResult:
    diagram_ir: DiagramIR
    tikz: str
    svg: str
    sym_table: dict  # id -> (float, float) coords
    sym_full: dict   # id -> sympy object
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: "float | None" = None
    recipe_metadata: Any = None
    python_full_metadata: Any = None
    retries: int = 0
    script: str = ""
    variable_ids: dict = field(default_factory=dict)
    entity_manifest: dict = field(default_factory=dict)
    # Non-fatal notes from the check and render stages (failed `prefer`
    # checks, renderer "Skipping Draw ..." messages). Never fails a run.
    warnings: list[str] = field(default_factory=list)


class PipelineError(RuntimeError):
    """A pipeline failure that also carries the warnings collected before it."""

    def __init__(self, message: str, warnings: list[str] | None = None):
        super().__init__(message)
        self.warnings: list[str] = list(warnings or [])


def warnings_from_error(exc: BaseException) -> list[str]:
    """Warnings attached to a pipeline failure ([] for any other exception)."""
    return list(getattr(exc, "warnings", None) or [])


def format_warnings_for_retry(warnings: list[str]) -> str:
    """Prompt text listing warnings for a retry; "" when there are none."""
    if not warnings:
        return ""
    bullets = "\n".join(f"- {w}" for w in warnings)
    return f"Warnings from the previous attempt (not errors, but worth fixing):\n{bullets}"


async def run_ir_pipeline(
    diagram_ir: DiagramIR,
    renderer: Renderer | None = None,
) -> StructuredRunResult:
    """Compile DiagramIR -> SymPy -> checks -> TikZ/SVG. Raises RuntimeError on failure."""
    if renderer is None:
        renderer = TikZRenderer()

    # SymPy compilation and checks are CPU-bound — run off the event loop thread
    # so they don't block async timeouts or concurrent eval runs.
    sym = await asyncio.to_thread(compile_defs, diagram_ir)

    diagram_ir = await asyncio.to_thread(resolve_angle_pairs, diagram_ir, sym)

    results = await asyncio.to_thread(run_checks, diagram_ir.checks, sym)
    warnings: list[str] = []
    for r in results:
        if not r.passed and r.check.level == "prefer":
            logger.warning("Preferred check not satisfied: %s", r.message)
            warnings.append(f"Preferred check not satisfied: {r.message}")

    must_failures = [r for r in results if not r.passed and r.check.level == "must"]
    if must_failures:
        msgs = "; ".join(r.message for r in must_failures)
        raise PipelineError(f"Geometric checks failed: {msgs}", warnings)

    angle_failures = await asyncio.to_thread(check_render_angles, diagram_ir, sym)
    if angle_failures:
        triples = ", ".join(str(t) for t in angle_failures)
        raise PipelineError(
            f"Invalid angle triples (not three distinct points): {triples}", warnings
        )

    render_result = await asyncio.to_thread(
        renderer.render, diagram_ir, sym, warnings=warnings
    )

    sym_table = {k: (float(v.x), float(v.y)) for k, v in sym.items() if isinstance(v, spg.Point)}

    return StructuredRunResult(
        diagram_ir=diagram_ir,
        tikz=render_result.intermediate,
        svg=render_result.output,
        sym_table=sym_table,
        sym_full=sym,
        warnings=warnings,
    )
