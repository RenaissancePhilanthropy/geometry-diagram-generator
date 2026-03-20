from __future__ import annotations
from dataclasses import fields
import pytest
from strategies.progressive_tools import DiagramState, ProgressiveToolsRunResult


def test_diagram_state_defaults():
    s = DiagramState()
    assert s.canvas is None
    assert s.defs == []
    assert s.sym is None
    assert s.checks == []
    assert s.render_ops == []
    assert s.repair_count == 0


def test_progressive_tools_run_result_fields():
    r = ProgressiveToolsRunResult(
        tikz="\\tkzInit",
        svg="<svg/>",
        input_tokens=10,
        output_tokens=20,
        repair_cycles=1,
    )
    assert r.tikz == "\\tkzInit"
    assert r.repair_cycles == 1
