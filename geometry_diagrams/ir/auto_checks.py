"""
Auto-check generation: implicit checks derived from definition types.

These complement LLM-specified checks by automatically verifying that
construction steps produced correct geometry (e.g., intersection points
actually lie on both parent objects).
"""
from __future__ import annotations

import ir.ir as ir
from ir.checks import CheckResult, run_checks
from ir.to_sympy import SymTable


def generate_auto_checks(diagram: ir.DiagramIR) -> list[ir.Check]:
    """Generate implicit checks for each definition that has a testable invariant."""
    checks: list[ir.Check] = []

    for stmt in diagram.define:
        match stmt:
            case ir.PointIntersection(id=pid, obj1=o1, obj2=o2):
                # Intersection must lie on both parent objects
                checks.append(ir.Contains(p=pid, obj=o1, level="must"))
                checks.append(ir.Contains(p=pid, obj=o2, level="must"))

            case ir.PointMidpoint(id=pid, p=p, q=q):
                # Midpoint must lie on the connecting segment if one is defined
                seg_id = _find_segment(diagram, p, q)
                if seg_id:
                    checks.append(ir.Contains(p=pid, obj=seg_id, level="must"))

            case ir.PointFoot(id=pid, source=src, onto=onto_id):
                # Foot must lie on the target object
                checks.append(ir.Contains(p=pid, obj=onto_id, level="must"))

    return checks


def run_auto_checks(diagram: ir.DiagramIR, sym: SymTable, tol: float = 5e-3) -> list[CheckResult]:
    """Run auto-generated checks against the compiled symbol table."""
    checks = generate_auto_checks(diagram)
    return run_checks(checks, sym, tol)


def _find_segment(diagram: ir.DiagramIR, p: str, q: str) -> str | None:
    """Find a segment definition connecting points p and q."""
    for stmt in diagram.define:
        if isinstance(stmt, ir.Segment):
            if (stmt.a == p and stmt.b == q) or (stmt.a == q and stmt.b == p):
                return stmt.id
    return None
