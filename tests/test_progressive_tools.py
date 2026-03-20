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


# ---------------------------------------------------------------------------
# Phase 2: Construction tool handlers — points
# ---------------------------------------------------------------------------
from strategies.progressive_tools import (
    handle_add_point_fixed,
    handle_add_point_free,
    handle_add_point_midpoint,
    handle_add_point_between,
    handle_add_point_foot,
    handle_add_point_rotate,
    handle_add_point_reflect,
    handle_add_point_triangle_center,
    handle_add_point_on,
    handle_add_point_intersection,
)


def _state_with_points():
    """Helper: state with A=(0,0) and B=(4,0)."""
    s = DiagramState()
    handle_add_point_fixed(s, "A", "0", "0")
    handle_add_point_fixed(s, "B", "4", "0")
    return s


def test_handle_add_point_fixed_registers():
    state = DiagramState()
    r = json.loads(handle_add_point_fixed(state, "A", "1", "2"))
    assert r["id"] == "A"
    assert r["status"] == "registered"
    assert len(state.defs) == 1
    assert state.defs[0].kind == "point_fixed"


def test_handle_add_point_fixed_duplicate_error():
    state = _state_with_points()
    r = json.loads(handle_add_point_fixed(state, "A", "0", "0"))
    assert "error" in r
    assert len(state.defs) == 2  # unchanged


def test_handle_add_point_free_no_hint():
    state = DiagramState()
    r = json.loads(handle_add_point_free(state, "P"))
    assert r["status"] == "registered"
    assert state.defs[0].hint_xy is None


def test_handle_add_point_free_with_hint():
    state = DiagramState()
    r = json.loads(handle_add_point_free(state, "P", hint_xy=[1.0, 2.0]))
    assert state.defs[0].hint_xy == [1.0, 2.0]


def test_handle_add_point_midpoint():
    state = _state_with_points()
    r = json.loads(handle_add_point_midpoint(state, "M", "A", "B"))
    assert r["status"] == "registered"
    assert state.defs[2].kind == "point_midpoint"


def test_handle_add_point_triangle_center():
    state = DiagramState()
    # add triangle dependency
    handle_add_point_fixed(state, "A", "0", "0")
    handle_add_point_fixed(state, "B", "4", "0")
    handle_add_point_fixed(state, "C", "2", "3")
    from strategies.progressive_tools import handle_add_triangle
    handle_add_triangle(state, "T", "A", "B", "C")
    r = json.loads(handle_add_point_triangle_center(state, "O", "T", "circumcenter"))
    assert r["status"] == "registered"
    assert state.defs[-1].kind == "point_triangle_center"
    assert state.defs[-1].which == "circumcenter"


def test_handle_add_point_intersection_no_pick():
    state = DiagramState()
    handle_add_point_fixed(state, "O1", "-1", "0")
    handle_add_point_fixed(state, "O2", "1", "0")
    from strategies.progressive_tools import handle_add_circle_center_radius
    handle_add_circle_center_radius(state, "c1", "O1", "2")
    handle_add_circle_center_radius(state, "c2", "O2", "2")
    r = json.loads(handle_add_point_intersection(state, "P", "c1", "c2"))
    assert r["status"] == "registered"
    assert state.defs[-1].kind == "point_intersection"
    assert state.defs[-1].pick is None


def test_handle_add_point_intersection_with_pick():
    state = DiagramState()
    handle_add_point_fixed(state, "O1", "-1", "0")
    handle_add_point_fixed(state, "O2", "1", "0")
    from strategies.progressive_tools import handle_add_circle_center_radius
    handle_add_circle_center_radius(state, "c1", "O1", "2")
    handle_add_circle_center_radius(state, "c2", "O2", "2")
    pick = {"kind": "closest_to", "p": "O1"}
    r = json.loads(handle_add_point_intersection(state, "P", "c1", "c2", pick=pick))
    assert r["status"] == "registered"
    assert state.defs[-1].pick.kind == "closest_to"
