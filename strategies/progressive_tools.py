from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from pydantic import TypeAdapter
from pydantic_ai import Agent

from ir import ir
from ir.to_sympy import SymTable
from strategies.base import DEFAULT_AGENT_MODEL, SubstanceStrategy

logger = logging.getLogger(__name__)

MAX_REPAIR_CYCLES = 3


@dataclass
class DiagramState:
    """Accumulated diagram state across all 4 phases."""
    canvas: ir.Canvas | None = None
    defs: list[ir.DefStmt] = field(default_factory=list)
    sym: SymTable | None = None          # populated by finalize_construction()
    checks: list[ir.Check] = field(default_factory=list)
    render_ops: list[ir.RenderOp] = field(default_factory=list)
    repair_count: int = 0
    # Internal phase completion flags
    _construction_finalized: bool = field(default=False, repr=False)
    _checks_finalized: bool = field(default=False, repr=False)
    _render_finalized: bool = field(default=False, repr=False)


@dataclass
class ProgressiveToolsRunResult:
    """Result of a ProgressiveToolsStrategy run."""
    tikz: str
    svg: str
    input_tokens: int = 0
    output_tokens: int = 0
    repair_cycles: int = 0
