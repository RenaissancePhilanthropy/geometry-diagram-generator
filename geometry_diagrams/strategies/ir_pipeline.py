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
from dataclasses import dataclass
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
    recipe_metadata: Any = None
    python_full_metadata: Any = None
    retries: int = 0


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
    must_failures = [r for r in results if not r.passed and r.check.level == "must"]
    if must_failures:
        msgs = "; ".join(r.message for r in must_failures)
        raise RuntimeError(f"Geometric checks failed: {msgs}")

    for r in results:
        if not r.passed and r.check.level == "prefer":
            logger.warning("Preferred check not satisfied: %s", r.message)

    angle_failures = await asyncio.to_thread(check_render_angles, diagram_ir, sym)
    if angle_failures:
        triples = ", ".join(str(t) for t in angle_failures)
        raise RuntimeError(f"Invalid angle triples (not three distinct points): {triples}")

    render_result = await asyncio.to_thread(renderer.render, diagram_ir, sym)

    sym_table = {k: (float(v.x), float(v.y)) for k, v in sym.items() if isinstance(v, spg.Point)}

    return StructuredRunResult(
        diagram_ir=diagram_ir,
        tikz=render_result.intermediate,
        svg=render_result.output,
        sym_table=sym_table,
        sym_full=sym,
    )
