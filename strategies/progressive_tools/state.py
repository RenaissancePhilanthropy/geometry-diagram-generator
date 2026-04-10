"""Shared state types and utilities for the progressive tools strategy."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart, UserPromptPart

from ir import ir
from ir.refs import def_references
from ir.to_sympy import SymTable

MAX_REPAIR_CYCLES = 2
KEEP_RECENT = 2


# ---------------------------------------------------------------------------
# History compression
# ---------------------------------------------------------------------------

def compress_tool_history(messages: list) -> list:
    """Compress old tool call/response pairs into a summary to reduce O(N²) token cost.

    Keeps: first user message, last 2 exchange rounds, summary of all older rounds.
    Called by pydantic-ai as a history_processor before each API request.
    """
    if len(messages) <= 3:
        return messages

    first = messages[0]
    rest = messages[1:]

    # Identify (response_index, request_index) exchange pairs in rest[]
    exchanges = []
    i = 0
    while i < len(rest):
        msg = rest[i]
        if (isinstance(msg, ModelResponse)
                and any(isinstance(p, ToolCallPart) for p in msg.parts)):
            if i + 1 < len(rest) and isinstance(rest[i + 1], ModelRequest):
                exchanges.append((i, i + 1))
            i += 2
        else:
            i += 1

    if len(exchanges) <= KEEP_RECENT:
        return messages

    to_compress = exchanges[:-KEEP_RECENT]
    compress_indices = set()
    for resp_i, req_i in to_compress:
        compress_indices.add(resp_i)
        compress_indices.add(req_i)

    registered_ids: list[str] = []
    errors: list[str] = []
    ok_count = 0

    for _resp_i, req_i in to_compress:
        req_msg = rest[req_i]
        for part in req_msg.parts:
            if isinstance(part, ToolReturnPart):
                try:
                    data = json.loads(part.content)
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        if item.get("status") == "registered" and "id" in item:
                            registered_ids.append(item["id"])
                        elif item.get("status") == "ok":
                            ok_count += 1
                        elif "error" in item:
                            errors.append(item["error"])
                except Exception:
                    pass

    parts = []
    if registered_ids:
        parts.append(f"Registered: {', '.join(registered_ids)}")
    if ok_count:
        parts.append(f"{ok_count} operation(s) succeeded")
    if errors:
        parts.append(f"{len(errors)} error(s): {'; '.join(errors[:3])}")

    summary_text = "Previously completed: " + (". ".join(parts) if parts else "no tracked operations") + "."
    summary_msg = ModelRequest(parts=[UserPromptPart(content=summary_text)])

    kept_rest = [msg for idx, msg in enumerate(rest) if idx not in compress_indices]
    return [first, summary_msg] + kept_rest


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
    _last_check_results: list[dict] = field(default_factory=list, repr=False)
    _tikz: str = field(default="", repr=False)
    _svg: str = field(default="", repr=False)
    _tool_call_count: int = field(default=0, repr=False)
    _render_warnings: list[str] = field(default_factory=list, repr=False)


# ---------------------------------------------------------------------------
# Dependency graph utilities
# ---------------------------------------------------------------------------


def cascade_remove(state: DiagramState, target_id: str) -> list[str]:
    """Remove target_id and all transitively dependent definitions from state.defs.

    Also clears state.sym since the symbol table is now stale.
    Returns the list of removed IDs.
    """
    # BFS: find all IDs that transitively depend on target_id
    to_remove: set[str] = {target_id}
    changed = True
    while changed:
        changed = False
        for stmt in state.defs:
            if stmt.id not in to_remove and def_references(stmt) & to_remove:
                to_remove.add(stmt.id)
                changed = True

    removed_ordered = [d.id for d in state.defs if d.id in to_remove]
    state.defs = [d for d in state.defs if d.id not in to_remove]
    state.sym = None  # symbol table is now stale
    state._construction_finalized = False
    state._checks_finalized = False
    state._render_finalized = False
    return removed_ordered


@dataclass
class ProgressiveToolsRunResult:
    """Result of a ProgressiveToolsStrategy run."""
    tikz: str
    svg: str
    input_tokens: int = 0
    output_tokens: int = 0
    repair_cycles: int = 0
    tool_calls: int = 0  # total handler invocations, including auto-finalize if triggered
    skipped_render_ids: list[str] = field(default_factory=list)  # render ops skipped due to undefined IDs
    # per-phase observability
    phase_traces: dict = field(default_factory=dict)   # phase_name → all_messages_json()
    phase_usage: dict = field(default_factory=dict)    # phase_name → {"input_tokens": N, "output_tokens": N}
