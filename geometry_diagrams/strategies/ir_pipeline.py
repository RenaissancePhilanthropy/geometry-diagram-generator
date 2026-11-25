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


from ..ir.ir import DiagramIR
from ..ir.to_sympy import compile_defs, float_point_table
from ..ir.checks import run_checks, check_render_angles
from ..ir.angle_audit import AnglePolicy, audit_angles
from ..ir.answer_audit import audit_answer_labels
from ..ir.angle_pairs import resolve_angle_pairs
from ..ir.derived import REGISTRY as DERIVED_REGISTRY
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
    # Non-fatal notes; never fails a run. Fed today by the renderer, by
    # failed `prefer`-level checks and by run_checks' optional `warnings`
    # collector (check-stage notes such as the prism projection warning),
    # which run_ir_pipeline passes. Extension point: a compile-stage producer
    # should add the same optional `warnings: list[str] | None = None`
    # argument to compile_defs and have run_ir_pipeline pass its collector.
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


@dataclass
class IRDiagnostics:
    """Everything the pipeline learns about a compiled diagram before rendering it."""
    check_results: list
    warnings: list[str]
    angle_findings: list
    answer_findings: list = field(default_factory=list)


def collect_diagnostics(
    diagram_ir: DiagramIR, sym: dict, angle_policy: "AnglePolicy | None" = None,
    answer_check: str = "warn", request_text: "str | None" = None,
) -> IRDiagnostics:
    """Run the diagram's checks and the warning producers against compiled geometry.

    The one place that decides what counts as a warning (check-stage notes, a registered
    kind's warnings, failed `prefer` checks, angle marks/labels contradicting the drawn
    angle), shared by run_ir_pipeline and verify_geometry_diagram so they cannot drift.
    CPU-bound; callers off the event loop thread use asyncio.to_thread."""
    warnings: list[str] = []
    results = run_checks(diagram_ir.checks, sym, warnings=warnings)
    # Registered kinds' warnings that need render ops and geometry (a prism's
    # dimension label contradicting its true length).
    warnings.extend(DERIVED_REGISTRY.pipeline_warnings(diagram_ir, sym))
    for r in results:
        if not r.passed and r.check.level == "prefer":
            logger.warning("Preferred check not satisfied: %s", r.message)
            warnings.append(f"Preferred check not satisfied: {r.message}")
    policy = angle_policy or AnglePolicy()
    angle_findings = [] if policy.mode == "off" else audit_angles(diagram_ir, sym, policy.tolerance_deg)
    warnings.extend(f.message for f in angle_findings)
    # Labels showing a number the request does not state (ir/answer_audit.py); needs the request.
    answer_findings = (
        audit_answer_labels(diagram_ir, request_text) if answer_check != "off" and request_text else []
    )
    warnings.extend(f.message for f in answer_findings)
    return IRDiagnostics(results, warnings, angle_findings, answer_findings)


async def run_ir_pipeline(
    diagram_ir: DiagramIR,
    renderer: Renderer | None = None,
    angle_policy: "AnglePolicy | None" = None,
    answer_check: str = "warn",
    request_text: "str | None" = None,
) -> StructuredRunResult:
    """Compile DiagramIR -> SymPy -> checks -> TikZ/SVG. Raises RuntimeError on failure.

    Collects a single `warnings` list (see StructuredRunResult.warnings for
    the stages that feed it and how to extend it); a PipelineError carries
    the warnings gathered before the failure.

    A right-angle mark or angle label that disagrees with the drawn angle
    (ir/angle_audit.py) is a warning, per `angle_policy` (default: warn above 1°; mode
    "off" skips the audit). With mode "retry" a mismatch above the policy's
    `fail_tolerance_deg` is a PipelineError instead, so the calling strategy retries; smaller
    ones stay warnings.

    Given the request's text, a label showing a number the request does not state is a
    warning too (ir/answer_audit.py); `answer_check` "off" skips that and "retry" makes it a
    PipelineError. Without `request_text` the answer audit does not run.
    """
    if renderer is None:
        renderer = TikZRenderer()

    # SymPy compilation and checks are CPU-bound — run off the event loop thread
    # so they don't block async timeouts or concurrent eval runs.
    sym = await asyncio.to_thread(compile_defs, diagram_ir)

    diagram_ir = await asyncio.to_thread(resolve_angle_pairs, diagram_ir, sym)

    diagnostics = await asyncio.to_thread(
        collect_diagnostics, diagram_ir, sym, angle_policy, answer_check, request_text,
    )
    warnings, results, angle_findings = diagnostics.warnings, diagnostics.check_results, diagnostics.angle_findings

    must_failures = [r for r in results if not r.passed and r.check.level == "must"]
    if must_failures:
        msgs = "; ".join(r.message for r in must_failures)
        raise PipelineError(f"Geometric checks failed: {msgs}", warnings)

    if angle_policy is not None and angle_policy.mode == "retry":
        gross = [f for f in angle_findings if f.error_deg > angle_policy.fail_tolerance_deg]
        if gross:
            raise PipelineError(
                "Angle marks or labels contradict the drawn angles: " + "; ".join(f.message for f in gross),
                warnings,
            )

    if answer_check == "retry" and diagnostics.answer_findings:
        raise PipelineError(
            "Labels show numbers the request does not state: "
            + "; ".join(f.message for f in diagnostics.answer_findings),
            warnings,
        )

    angle_failures = await asyncio.to_thread(check_render_angles, diagram_ir, sym)
    if angle_failures:
        triples = ", ".join(str(t) for t in angle_failures)
        raise PipelineError(
            f"Invalid angle triples (not three distinct points): {triples}", warnings
        )

    render_result = await asyncio.to_thread(
        renderer.render, diagram_ir, sym, warnings=warnings
    )

    sym_table = float_point_table(sym)

    return StructuredRunResult(
        diagram_ir=diagram_ir,
        tikz=render_result.intermediate,
        svg=render_result.output,
        sym_table=sym_table,
        sym_full=sym,
        warnings=warnings,
    )
