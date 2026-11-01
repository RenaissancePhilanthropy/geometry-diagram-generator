"""build_agent's turn history is bounded; only the top frame is ever read."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from geometry_diagrams.ir.ir import DiagramIR
from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
from geometry_diagrams.strategies.python_full import _MAX_STACK_DEPTH, PythonFullStrategy


def _closure_stack(render_tool):
    fn = render_tool.coroutine
    idx = fn.__code__.co_freevars.index("_stack")
    return fn.__closure__[idx].cell_contents


@pytest.mark.asyncio
async def test_agent_stack_keeps_only_the_last_turns():
    calls = 0

    async def fake_run(self, prompt, model="test", renderer=None, sandbox_timeout_seconds=2.5, **kw):
        nonlocal calls
        calls += 1
        return StructuredRunResult(
            diagram_ir=DiagramIR(define=[], render=[]), tikz="", svg=f"<svg>{calls}</svg>",
            sym_table={}, sym_full={}, script="a = point(0,0)\ndraw_points(a)\n",
            variable_ids={"a": "p1"},
            entity_manifest={"named": [{"name": "a", "id": "p1", "type": "point_fixed",
                                        "approx_position": [0.0, 0.0]}], "anonymous": []},
        )

    total = _MAX_STACK_DEPTH + 3
    with patch.object(PythonFullStrategy, "run", fake_run):
        graph = PythonFullStrategy().build_agent(model="test", edit_generation_mode="full_rewrite")
        tools = {t.name: t for t in graph.nodes["tools"].bound.tools_by_name.values()}
        render_tool = tools["render_diagram"]
        for i in range(total):
            out = json.loads(await render_tool.ainvoke({"request": f"turn {i}"}))
            assert "error" not in out

    stack = _closure_stack(render_tool)
    assert len(stack) == _MAX_STACK_DEPTH
    assert stack[-1]["result"].svg == f"<svg>{total}</svg>"
