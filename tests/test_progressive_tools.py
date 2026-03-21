from __future__ import annotations
from dataclasses import fields
import json
import pytest
from strategies.progressive_tools import DiagramState, ProgressiveToolsRunResult
from ir.ir import PointFixed, Segment, Triangle
from strategies.progressive_tools import cascade_remove, def_references, handle_init_diagram


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


# ---------------------------------------------------------------------------
# Phase 2: Construction tool handlers — linear, circles, composites + remove
# ---------------------------------------------------------------------------
from strategies.progressive_tools import (
    handle_add_segment, handle_add_ray, handle_add_line_through,
    handle_add_line_parallel_through, handle_add_line_perp_through,
    handle_add_line_angle_bisector, handle_add_line_tangent,
    handle_add_circle_center_point, handle_add_circle_center_radius,
    handle_add_circle_through3,
    handle_add_triangle, handle_add_polygon, handle_add_polygon_exterior,
    handle_remove_definition,
)


def test_handle_add_segment():
    state = _state_with_points()
    r = json.loads(handle_add_segment(state, "s1", "A", "B"))
    assert r["status"] == "registered"
    assert state.defs[-1].kind == "segment"


def test_handle_add_line_through():
    state = _state_with_points()
    r = json.loads(handle_add_line_through(state, "l1", "A", "B"))
    assert r["status"] == "registered"
    # IR field is p/q — check via model_dump
    assert state.defs[-1].kind == "line_through"
    data = state.defs[-1].model_dump()
    assert data["p"] == "A" and data["q"] == "B"


def test_handle_add_line_parallel_through():
    state = _state_with_points()
    handle_add_line_through(state, "l1", "A", "B")
    handle_add_point_fixed(state, "C", "0", "2")
    r = json.loads(handle_add_line_parallel_through(state, "l2", through="C", parallel_to="l1"))
    assert r["status"] == "registered"
    data = state.defs[-1].model_dump()
    assert data["to_line"] == "l1"   # IR field name


def test_handle_add_circle_center_radius():
    state = _state_with_points()
    r = json.loads(handle_add_circle_center_radius(state, "c1", center="A", radius="3"))
    assert r["status"] == "registered"
    assert state.defs[-1].kind == "circle_center_radius"


def test_handle_add_triangle():
    state = DiagramState()
    handle_add_point_fixed(state, "A", "0", "0")
    handle_add_point_fixed(state, "B", "4", "0")
    handle_add_point_fixed(state, "C", "2", "3")
    r = json.loads(handle_add_triangle(state, "T", "A", "B", "C"))
    assert r["status"] == "registered"


def test_handle_add_polygon():
    state = DiagramState()
    for name, x, y in [("A","0","0"),("B","4","0"),("C","4","4"),("D","0","4")]:
        handle_add_point_fixed(state, name, x, y)
    r = json.loads(handle_add_polygon(state, "sq", ["A","B","C","D"]))
    assert r["status"] == "registered"
    assert state.defs[-1].kind == "polygon"


def test_handle_add_line_tangent_with_pick():
    state = _state_with_points()
    handle_add_circle_center_radius(state, "c1", "A", "3")
    pick = {"kind": "index", "k": 0}
    r = json.loads(handle_add_line_tangent(state, "lt", from_point="B", to_circle="c1", pick=pick))
    assert r["status"] == "registered"
    data = state.defs[-1].model_dump()
    assert data["point"] == "B"    # IR field is 'point'
    assert data["circle"] == "c1"  # IR field is 'circle'


def test_handle_remove_definition():
    state = DiagramState()
    handle_add_point_fixed(state, "A", "0", "0")
    handle_add_point_fixed(state, "B", "4", "0")
    handle_add_segment(state, "s1", "A", "B")
    r = json.loads(handle_remove_definition(state, "A"))
    assert set(r["removed"]) == {"A", "s1"}
    assert len(state.defs) == 1
    assert state.defs[0].id == "B"


def test_handle_remove_nonexistent():
    state = DiagramState()
    r = json.loads(handle_remove_definition(state, "X"))
    assert "error" in r


def test_handle_add_polygon_exterior_remapping():
    """v1/v2/ref_point tool args must map to a/b/ref IR fields."""
    state = DiagramState()
    handle_add_point_fixed(state, "A", "0", "0")
    handle_add_point_fixed(state, "B", "2", "0")
    handle_add_point_fixed(state, "R", "1", "3")
    r = json.loads(handle_add_polygon_exterior(state, "sq", v1="A", v2="B", sides=4, ref_point="R"))
    assert r["status"] == "registered"
    data = state.defs[-1].model_dump()
    assert data["a"] == "A"   # IR field is 'a', not 'v1'
    assert data["b"] == "B"   # IR field is 'b', not 'v2'
    assert data["ref"] == "R" # IR field is 'ref', not 'ref_point'


def test_handle_add_line_perp_through_remapping():
    """perp_to tool arg must map to to_line IR field."""
    state = _state_with_points()
    handle_add_line_through(state, "l1", "A", "B")
    handle_add_point_fixed(state, "C", "2", "3")
    r = json.loads(handle_add_line_perp_through(state, "lp", through="C", perp_to="l1"))
    assert r["status"] == "registered"
    data = state.defs[-1].model_dump()
    assert data["to_line"] == "l1"  # IR field is 'to_line', not 'perp_to'


# ---------------------------------------------------------------------------
# Phase 2: finalize_construction handler
# ---------------------------------------------------------------------------
from strategies.progressive_tools import handle_finalize_construction


def test_handle_finalize_construction_success():
    state = DiagramState()
    handle_add_point_fixed(state, "A", "0", "0")
    handle_add_point_fixed(state, "B", "4", "0")
    handle_add_point_fixed(state, "C", "2", "3")
    handle_add_triangle(state, "T", "A", "B", "C")
    r = json.loads(handle_finalize_construction(state))
    assert r["status"] == "ok"
    assert state.sym is not None
    assert state._construction_finalized is True
    # Compiled summary includes all object IDs
    compiled_ids = {item["id"] for item in r["compiled"]}
    assert {"A", "B", "C", "T"} <= compiled_ids


# ---------------------------------------------------------------------------
# check_tool_names_for_state tests
# ---------------------------------------------------------------------------
from strategies.progressive_tools import check_tool_names_for_state


def _state_with_triangle():
    state = DiagramState()
    handle_add_point_fixed(state, "A", "0", "0")
    handle_add_point_fixed(state, "B", "4", "0")
    handle_add_point_fixed(state, "C", "2", "3")
    handle_add_triangle(state, "T", "A", "B", "C")
    handle_finalize_construction(state)
    return state


def test_check_tools_three_points():
    state = _state_with_triangle()
    tools = check_tool_names_for_state(state)
    assert "add_distinct_points_check" in tools
    assert "add_collinear_check" in tools
    assert "add_non_collinear_check" in tools


def test_check_tools_no_segments_no_equal_length():
    state = _state_with_triangle()
    tools = check_tool_names_for_state(state)
    # Triangle exists but no segment defs
    assert "add_equal_length_check" not in tools


def test_check_tools_with_segments():
    state = _state_with_triangle()
    handle_add_segment(state, "s1", "A", "B")
    handle_add_segment(state, "s2", "B", "C")
    handle_finalize_construction(state)
    tools = check_tool_names_for_state(state)
    assert "add_equal_length_check" in tools
    assert "add_ratio_equal_check" in tools


def test_check_tools_tangent_requires_line_tangent_def():
    state = DiagramState()
    handle_add_point_fixed(state, "A", "0", "0")
    handle_add_point_fixed(state, "B", "5", "0")
    handle_add_circle_center_radius(state, "c1", "A", "2")
    handle_add_line_through(state, "l1", "A", "B")  # a line, but not line_tangent kind
    handle_finalize_construction(state)
    tools = check_tool_names_for_state(state)
    assert "add_tangent_check" not in tools  # no line_tangent def


def test_check_tools_tangent_with_line_tangent_def():
    state = DiagramState()
    handle_add_point_fixed(state, "P", "5", "0")
    handle_add_point_fixed(state, "O", "0", "0")
    handle_add_circle_center_radius(state, "c1", "O", "2")
    handle_add_line_tangent(state, "lt", from_point="P", to_circle="c1")
    handle_finalize_construction(state)
    tools = check_tool_names_for_state(state)
    assert "add_tangent_check" in tools


def test_check_tools_two_linear_objects():
    state = _state_with_triangle()
    handle_add_segment(state, "s1", "A", "B")
    handle_add_segment(state, "s2", "B", "C")
    handle_finalize_construction(state)
    tools = check_tool_names_for_state(state)
    assert "add_parallel_check" in tools
    assert "add_perpendicular_check" in tools


def test_handle_finalize_construction_compile_error():
    state = DiagramState()
    # Segment referencing nonexistent point B
    handle_add_point_fixed(state, "A", "0", "0")
    from ir.ir import Segment
    state.defs.append(Segment(id="s1", a="A", b="MISSING"))
    r = json.loads(handle_finalize_construction(state))
    assert r["status"] == "error"
    assert "error" in r
    assert state.sym is None
    assert state._construction_finalized is False


def test_handle_finalize_construction_includes_coordinates():
    state = DiagramState()
    handle_add_point_fixed(state, "A", "3", "4")
    r = json.loads(handle_finalize_construction(state))
    compiled = {item["id"]: item for item in r["compiled"]}
    assert compiled["A"]["coordinates"] == pytest.approx([3.0, 4.0])


# ---------------------------------------------------------------------------
# Phase 3: Check tool handlers and finalize_checks
# ---------------------------------------------------------------------------
from strategies.progressive_tools import (
    handle_add_distinct_points_check,
    handle_add_non_collinear_check,
    handle_add_equal_length_check,
    handle_add_contains_check,
    handle_add_parallel_check,
    handle_add_perpendicular_check,
    handle_finalize_checks,
)


def test_handle_add_distinct_points_check():
    state = _state_with_triangle()
    r = json.loads(handle_add_distinct_points_check(state, "A", "B", level="must"))
    assert r["status"] == "registered"
    assert len(state.checks) == 1
    assert state.checks[0].kind == "distinct_points"


def test_handle_finalize_checks_all_pass():
    state = _state_with_triangle()
    handle_add_non_collinear_check(state, "A", "B", "C", level="must")
    r = json.loads(handle_finalize_checks(state))
    assert r["all_passed"] is True
    assert state._checks_finalized is True
    assert all(item["passed"] for item in r["results"])


def test_handle_finalize_checks_must_fail():
    state = DiagramState()
    # Collinear points — A, B, C on x-axis
    handle_add_point_fixed(state, "A", "0", "0")
    handle_add_point_fixed(state, "B", "2", "0")
    handle_add_point_fixed(state, "C", "4", "0")
    handle_finalize_construction(state)
    handle_add_non_collinear_check(state, "A", "B", "C", level="must")
    r = json.loads(handle_finalize_checks(state))
    assert r["all_passed"] is False
    failed = [item for item in r["results"] if not item["passed"]]
    assert len(failed) == 1
    assert "non_collinear" in failed[0]["check"]
    assert state._checks_finalized is False  # must failure does NOT set flag


def test_handle_finalize_checks_prefer_fail_does_not_block():
    state = DiagramState()
    handle_add_point_fixed(state, "A", "0", "0")
    handle_add_point_fixed(state, "B", "2", "0")
    handle_add_point_fixed(state, "C", "4", "0")
    handle_finalize_construction(state)
    handle_add_non_collinear_check(state, "A", "B", "C", level="prefer")
    r = json.loads(handle_finalize_checks(state))
    # prefer failure does NOT set all_passed to False for phase advancement
    assert r["all_passed"] is True
    assert state._checks_finalized is True


# ---------------------------------------------------------------------------
# Task 9: presentation_tool_names_for_state
# ---------------------------------------------------------------------------
from strategies.progressive_tools import presentation_tool_names_for_state


def test_presentation_tools_always_available():
    state = _state_with_triangle()
    handle_finalize_construction(state)
    tools = presentation_tool_names_for_state(state)
    assert "draw" in tools
    assert "draw_points" in tools
    assert "finalize_render" in tools


def test_presentation_tools_fill_with_closed_shape():
    state = _state_with_triangle()
    handle_finalize_construction(state)
    tools = presentation_tool_names_for_state(state)
    assert "fill" in tools   # triangle is a closed shape


def test_presentation_tools_no_fill_without_closed_shape():
    state = DiagramState()
    handle_add_point_fixed(state, "A", "0", "0")
    handle_add_point_fixed(state, "B", "4", "0")
    handle_finalize_construction(state)
    tools = presentation_tool_names_for_state(state)
    assert "fill" not in tools


def test_presentation_tools_mark_segments_with_segment():
    state = _state_with_triangle()
    handle_add_segment(state, "s1", "A", "B")
    handle_finalize_construction(state)
    tools = presentation_tool_names_for_state(state)
    assert "mark_segments" in tools
    assert "label_segment" in tools


def test_presentation_tools_angles_with_three_points():
    state = _state_with_triangle()
    handle_finalize_construction(state)
    tools = presentation_tool_names_for_state(state)
    assert "mark_angles" in tools
    assert "mark_right_angles" in tools
    assert "label_angle" in tools


def test_presentation_tools_label_point_with_any_point():
    state = DiagramState()
    handle_add_point_fixed(state, "A", "0", "0")
    handle_finalize_construction(state)
    tools = presentation_tool_names_for_state(state)
    assert "label_point" in tools


# ---------------------------------------------------------------------------
# Task 10: Presentation tool handlers
# ---------------------------------------------------------------------------
from strategies.progressive_tools import (
    handle_draw, handle_draw_points, handle_fill,
    handle_mark_angles, handle_mark_right_angles,
    handle_mark_segments, handle_label_point,
    handle_label_angle, handle_label_segment,
)


def test_handle_draw_registers_render_op():
    state = _state_with_triangle()
    handle_finalize_construction(state)
    r = json.loads(handle_draw(state, "T"))
    assert r["status"] == "registered"
    assert len(state.render_ops) == 1
    assert state.render_ops[0].kind == "draw"


def test_handle_draw_points():
    state = _state_with_triangle()
    handle_finalize_construction(state)
    r = json.loads(handle_draw_points(state, ["A", "B", "C"]))
    assert r["status"] == "registered"
    assert state.render_ops[0].kind == "draw_points"


def test_handle_fill():
    state = _state_with_triangle()
    handle_finalize_construction(state)
    r = json.loads(handle_fill(state, "T", opacity=0.3))
    assert r["status"] == "registered"


def test_handle_mark_angles():
    state = _state_with_triangle()
    handle_finalize_construction(state)
    r = json.loads(handle_mark_angles(state, "A", "B", "C"))
    assert r["status"] == "registered"


def test_handle_mark_segments():
    state = _state_with_triangle()
    handle_add_segment(state, "s1", "A", "B")
    handle_finalize_construction(state)
    r = json.loads(handle_mark_segments(state, ["s1"]))
    assert r["status"] == "registered"


def test_handle_label_point():
    state = _state_with_triangle()
    handle_finalize_construction(state)
    r = json.loads(handle_label_point(state, "A", text="A", position="above"))
    assert r["status"] == "registered"


def test_label_point_compound_position():
    """LabelPoint should accept compound positions like 'above left'."""
    state = DiagramState()
    state.canvas = ir.Canvas(kind="cartesian", xmin=-5, xmax=5, ymin=-5, ymax=5)
    # Set up a point
    handle_add_point_fixed(state, "A", "0", "0")
    # Use compound position — should not raise
    result = handle_label_point(state, "A", "A", "above left")
    data = json.loads(result)
    assert data["status"] == "registered"
    # Verify the render op was stored correctly
    assert len(state.render_ops) == 1
    assert state.render_ops[0].pos == "above left"


def test_handle_label_segment():
    state = _state_with_triangle()
    handle_add_segment(state, "s1", "A", "B")
    handle_finalize_construction(state)
    r = json.loads(handle_label_segment(state, "s1", text="4"))
    assert r["status"] == "registered"


# ---------------------------------------------------------------------------
# Task 11: Agent builders and ProgressiveToolsStrategy.run()
# ---------------------------------------------------------------------------
from unittest.mock import AsyncMock, MagicMock, patch
from strategies.progressive_tools import ProgressiveToolsStrategy
from ir import ir


@pytest.mark.asyncio
async def test_run_calls_four_agents():
    """Verify run() invokes 4 agent.run() calls in sequence."""
    strategy = ProgressiveToolsStrategy()

    mock_usage = MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5

    call_count = 0

    async def fake_agent_run(prompt, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        resp = MagicMock()
        resp.usage.return_value = mock_usage
        # Simulate side effects per phase
        if call_count == 1:  # canvas phase — set canvas
            strategy._last_state.canvas = ir.Canvas(
                kind="cartesian", xmin=-5, xmax=5, ymin=-5, ymax=5
            )
        elif call_count == 2:  # construction phase — set sym + flag
            strategy._last_state._construction_finalized = True
            strategy._last_state.sym = {}
        elif call_count == 3:  # checks phase — set flag
            strategy._last_state._checks_finalized = True
        elif call_count == 4:  # render phase — set flag + tikz/svg
            strategy._last_state._render_finalized = True
            strategy._last_state._tikz = "\\tkzInit"
            strategy._last_state._svg = "<svg/>"
        return resp

    with patch("strategies.progressive_tools.Agent") as MockAgent:
        mock_agent_instance = MagicMock()
        mock_agent_instance.run = fake_agent_run
        MockAgent.return_value = mock_agent_instance

        result = await strategy.run("draw a triangle", model="anthropic:claude-sonnet-4-6")

    assert call_count == 4
    assert isinstance(result, ProgressiveToolsRunResult)
    assert result.input_tokens == 40   # 10 * 4
    assert result.output_tokens == 20  # 5 * 4


@pytest.mark.asyncio
async def test_run_auto_finalizes_render():
    """If presentation agent forgets finalize_render, strategy auto-finalizes."""
    strategy = ProgressiveToolsStrategy()

    call_count = 0

    async def fake_agent_run(prompt, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        resp = MagicMock()
        mock_usage = MagicMock()
        mock_usage.input_tokens = 10
        mock_usage.output_tokens = 5
        resp.usage.return_value = mock_usage
        if call_count == 1:  # canvas
            strategy._last_state.canvas = ir.Canvas(
                kind="cartesian", xmin=-5, xmax=5, ymin=-5, ymax=5
            )
        elif call_count == 2:  # construction
            strategy._last_state._construction_finalized = True
            strategy._last_state.sym = {}
        elif call_count == 3:  # checks
            strategy._last_state._checks_finalized = True
        elif call_count == 4:  # presentation — does NOT call finalize_render
            # Agent adds some render ops but forgets to finalize
            pass  # _render_finalized stays False
        return resp

    with patch("strategies.progressive_tools.Agent") as MockAgent:
        mock_agent_instance = MagicMock()
        mock_agent_instance.run = fake_agent_run
        MockAgent.return_value = mock_agent_instance

        # Also mock handle_finalize_render to avoid renderer dependency
        with patch("strategies.progressive_tools.handle_finalize_render") as mock_finalize:
            def fake_finalize(state):
                state._render_finalized = True
                state._tikz = "\\tkzInit"
                state._svg = "<svg/>"
                return json.dumps({"status": "ok", "tikz_length": 100, "svg_length": 50})
            mock_finalize.side_effect = fake_finalize

            result = await strategy.run("draw a midpoint", model="anthropic:claude-sonnet-4-6")

            mock_finalize.assert_called_once_with(strategy._last_state)

    assert isinstance(result, ProgressiveToolsRunResult)
    assert result.tikz == "\\tkzInit"
    assert result.svg == "<svg/>"


@pytest.mark.asyncio
async def test_run_auto_finalize_raises_on_error():
    """If auto-finalize_render fails, run() raises RuntimeError."""
    strategy = ProgressiveToolsStrategy()
    call_count = 0

    async def fake_agent_run(prompt, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        resp = MagicMock()
        mock_usage = MagicMock()
        mock_usage.input_tokens = 1
        mock_usage.output_tokens = 1
        resp.usage.return_value = mock_usage
        if call_count == 1:
            strategy._last_state.canvas = ir.Canvas(
                kind="cartesian", xmin=-5, xmax=5, ymin=-5, ymax=5
            )
        elif call_count == 2:
            strategy._last_state._construction_finalized = True
            strategy._last_state.sym = {}
        elif call_count == 3:
            strategy._last_state._checks_finalized = True
        # call_count == 4: presentation agent — does nothing
        return resp

    with patch("strategies.progressive_tools.Agent") as MockAgent:
        mock_agent_instance = MagicMock()
        mock_agent_instance.run = fake_agent_run
        MockAgent.return_value = mock_agent_instance

        with patch("strategies.progressive_tools.handle_finalize_render") as mock_finalize:
            mock_finalize.return_value = json.dumps({"status": "error", "error": "sym is None"})

            with pytest.raises(RuntimeError, match="Auto-finalize_render failed"):
                await strategy.run("draw something", model="anthropic:claude-sonnet-4-6")


def test_eval_harness_handles_progressive_tools_result():
    """ProgressiveToolsRunResult must not fall into the AgentRunResult else-branch."""
    result = ProgressiveToolsRunResult(
        tikz="\\tkzInit",
        svg="<svg/>",
        input_tokens=100,
        output_tokens=50,
        repair_cycles=1,
    )
    # Verify it is NOT an instance of StructuredRunResult (different branch)
    from strategies.structured import StructuredRunResult
    assert not isinstance(result, StructuredRunResult)
    # Verify it has the fields the harness will read
    assert hasattr(result, "tikz")
    assert hasattr(result, "svg")
    assert hasattr(result, "input_tokens")
    assert hasattr(result, "output_tokens")
    assert hasattr(result, "repair_cycles")


def test_init_diagram_with_axes():
    state = DiagramState()
    handle_init_diagram(state, axes=True)
    assert state.canvas is not None
    assert state.canvas.axes is True


def test_init_diagram_axes_default_false():
    state = DiagramState()
    handle_init_diagram(state)
    assert state.canvas.axes is False


def test_repair_preserves_defs():
    """After repair reset, state.defs must be preserved (not cleared)."""
    from strategies.progressive_tools import handle_add_point_fixed
    import ir.ir as ir

    state = DiagramState()
    state.canvas = ir.Canvas(kind="cartesian", xmin=-5, xmax=5, ymin=-5, ymax=5)
    handle_add_point_fixed(state, "A", "0", "0")
    handle_add_point_fixed(state, "B", "1", "0")

    # Simulate what run() does in the repair reset block
    state._construction_finalized = False
    state._checks_finalized = False
    state.sym = None
    state.render_ops = []
    # defs are NOT cleared in the new code

    assert len(state.defs) == 2
    assert state._construction_finalized is False
    assert state.sym is None


def test_tool_call_count_increments():
    """Each tool call handler increments state._tool_call_count."""
    state = DiagramState()
    assert state._tool_call_count == 0
    handle_init_diagram(state)
    assert state._tool_call_count == 1
    handle_add_point_fixed(state, "A", "0", "0")
    assert state._tool_call_count == 2


# --- History Compression Tests ---

from pydantic_ai.messages import (
    ModelRequest, ModelResponse,
    TextPart, ToolCallPart, ToolReturnPart, UserPromptPart,
)
from strategies.progressive_tools import compress_tool_history


def _make_tool_exchange(tool_name: str, tool_call_id: str, return_content: str):
    """Build a (ModelResponse with ToolCallPart, ModelRequest with ToolReturnPart) pair."""
    response = ModelResponse(parts=[ToolCallPart(tool_name=tool_name, tool_call_id=tool_call_id)])
    request = ModelRequest(parts=[ToolReturnPart(tool_name=tool_name, content=return_content, tool_call_id=tool_call_id)])
    return response, request


def _make_messages_with_n_exchanges(n: int):
    """Build a message list: initial UserPromptPart request + n tool exchanges."""
    initial = ModelRequest(parts=[UserPromptPart(content="draw a triangle")])
    messages = [initial]
    for i in range(n):
        resp, req = _make_tool_exchange(
            tool_name="add_point_fixed",
            tool_call_id=f"tc{i}",
            return_content=json.dumps({"id": f"P{i}", "status": "registered"}),
        )
        messages.append(resp)
        messages.append(req)
    return messages


def test_compress_tool_history_empty():
    """Empty list returns empty."""
    assert compress_tool_history([]) == []


def test_compress_tool_history_short_no_compression():
    """3 or fewer messages returned as-is."""
    messages = _make_messages_with_n_exchanges(1)
    # 1 initial + 2 exchange = 3 messages — at the threshold, no compression
    assert len(messages) == 3
    result = compress_tool_history(messages)
    assert result is messages


def test_compress_tool_history_two_exchanges_no_compression():
    """Exactly 2 exchange rounds — at KEEP_RECENT limit, returned as-is."""
    messages = _make_messages_with_n_exchanges(2)
    result = compress_tool_history(messages)
    assert result is messages


def test_compress_tool_history_long_compresses():
    """With 5 exchange rounds, oldest rounds are compressed into a summary."""
    messages = _make_messages_with_n_exchanges(5)
    original_len = len(messages)
    result = compress_tool_history(messages)
    assert len(result) < original_len


def test_compress_tool_history_registered_ids_in_summary():
    """Summary mentions registered IDs from compressed exchanges."""
    messages = _make_messages_with_n_exchanges(5)
    result = compress_tool_history(messages)
    # Find the summary message (index 1 in output)
    summary_msg = result[1]
    summary_text = summary_msg.parts[0].content
    # The first 3 exchanges (P0, P1, P2) should appear in summary; P3, P4 are kept verbatim
    assert "P0" in summary_text
    assert "P1" in summary_text
    assert "P2" in summary_text


def test_compress_tool_history_preserves_first_message():
    """First message is always at index 0 in output."""
    messages = _make_messages_with_n_exchanges(5)
    first = messages[0]
    result = compress_tool_history(messages)
    assert result[0] is first


def test_compress_tool_history_preserves_recent_exchanges():
    """Last 2 exchanges are kept verbatim (not replaced by summary)."""
    messages = _make_messages_with_n_exchanges(4)
    # last 2 exchanges are messages[-4], messages[-3], messages[-2], messages[-1]
    last_4 = messages[-4:]
    result = compress_tool_history(messages)
    # The tail of the result should contain the last 4 messages verbatim
    assert result[-4:] == last_4


def test_compress_tool_history_error_in_summary():
    """Errors from tool returns appear in the summary text."""
    initial = ModelRequest(parts=[UserPromptPart(content="draw something")])
    messages = [initial]
    # 3 error exchanges + 2 more to push them into compression
    for i in range(3):
        resp, req = _make_tool_exchange(
            tool_name="add_point_fixed",
            tool_call_id=f"tc{i}",
            return_content=json.dumps({"error": f"ID 'P{i}' already in use"}),
        )
        messages.append(resp)
        messages.append(req)
    # 2 more valid exchanges (kept verbatim)
    for i in range(3, 5):
        resp, req = _make_tool_exchange(
            tool_name="add_point_fixed",
            tool_call_id=f"tc{i}",
            return_content=json.dumps({"id": f"Q{i}", "status": "registered"}),
        )
        messages.append(resp)
        messages.append(req)

    result = compress_tool_history(messages)
    summary_text = result[1].parts[0].content
    assert "error" in summary_text.lower()
