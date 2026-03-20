from __future__ import annotations
from dataclasses import fields
import json
import pytest
from strategies.progressive_tools import DiagramState, ProgressiveToolsRunResult
from ir.ir import PointFixed, Segment, Triangle
from strategies.progressive_tools import cascade_remove, def_references


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


def test_def_references_point_fixed():
    stmt = PointFixed(id="A", x="0", y="0")
    assert def_references(stmt) == set()


def test_def_references_segment():
    from ir.ir import Segment as Seg
    stmt = Seg(id="s1", a="A", b="B")
    assert def_references(stmt) == {"A", "B"}


def test_def_references_triangle():
    stmt = Triangle(id="T", a="A", b="B", c="C")
    assert def_references(stmt) == {"A", "B", "C"}


def test_cascade_remove_no_dependents():
    state = DiagramState()
    state.defs = [PointFixed(id="A", x="0", y="0"), PointFixed(id="B", x="1", y="1")]
    removed = cascade_remove(state, "A")
    assert removed == ["A"]
    assert len(state.defs) == 1
    assert state.defs[0].id == "B"


def test_cascade_remove_with_dependents():
    state = DiagramState()
    state.defs = [
        PointFixed(id="A", x="0", y="0"),
        PointFixed(id="B", x="2", y="0"),
        PointFixed(id="C", x="1", y="2"),
        Triangle(id="T", a="A", b="B", c="C"),
        Segment(id="sAC", a="A", b="C"),
    ]
    removed = cascade_remove(state, "C")
    assert set(removed) == {"C", "T", "sAC"}
    remaining_ids = {d.id for d in state.defs}
    assert remaining_ids == {"A", "B"}


def test_cascade_remove_clears_sym():
    state = DiagramState()
    state.defs = [PointFixed(id="A", x="0", y="0")]
    state.sym = {"A": object()}  # fake sym table
    cascade_remove(state, "A")
    assert state.sym is None


def test_cascade_remove_resets_all_phase_flags():
    state = DiagramState()
    state.defs = [PointFixed(id="A", x="0", y="0")]
    state.sym = {"A": object()}
    state._construction_finalized = True
    state._checks_finalized = True
    state._render_finalized = True
    cascade_remove(state, "A")
    assert state.sym is None
    assert state._construction_finalized is False
    assert state._checks_finalized is False
    assert state._render_finalized is False


# ---------------------------------------------------------------------------
# Phase 1: Canvas tool handler tests
# ---------------------------------------------------------------------------
from strategies.progressive_tools import handle_init_diagram


def test_handle_init_diagram_basic():
    state = DiagramState()
    result = json.loads(handle_init_diagram(state, grid=False, xmin=-5, xmax=5, ymin=-5, ymax=5))
    assert result["status"] == "ok"
    assert state.canvas is not None
    assert state.canvas.grid is False
    assert state.canvas.xmin == -5


def test_handle_init_diagram_defaults():
    state = DiagramState()
    result = json.loads(handle_init_diagram(state, grid=True))
    assert state.canvas.grid is True
    assert state.canvas.xmin == -5  # default


def test_handle_init_diagram_idempotent():
    state = DiagramState()
    handle_init_diagram(state, grid=False)
    result = json.loads(handle_init_diagram(state, grid=True))
    # Second call overwrites
    assert state.canvas.grid is True
