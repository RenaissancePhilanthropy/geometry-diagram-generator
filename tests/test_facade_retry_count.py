"""DiagramResult.retry_count counts generation attempts for every strategy."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from geometry_diagrams.facade import render_geometry_diagram
from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
from geometry_diagrams.strategies.python_full import PythonFullStrategy
from geometry_diagrams.strategies.structured import StructureStrategy


def _result(retries: int) -> StructuredRunResult:
    ir = MagicMock()
    ir.model_dump = MagicMock(return_value={})
    return StructuredRunResult(
        diagram_ir=ir, tikz="", svg="<svg/>", sym_table={}, sym_full={}, retries=retries,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy,cls", [("structured", StructureStrategy), ("python_full", PythonFullStrategy)])
@pytest.mark.parametrize("retries", [0, 2])
async def test_retry_count_is_attempts_for_non_recipe_strategies(monkeypatch, strategy, cls, retries):
    async def fake_run(self, prompt, **kw):
        return _result(retries)

    monkeypatch.setattr(cls, "run", fake_run)
    out = await render_geometry_diagram("a triangle", strategy=strategy, renderer="svg")
    assert out.retry_count == retries + 1
