"""Agent builders and ProgressiveToolsStrategy orchestrating all 4 phases."""
from __future__ import annotations

import json
import logging

import sympy.geometry as spg
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from ir.renderer import Renderer
from strategies.base import DEFAULT_AGENT_MODEL, SubstanceStrategy

from .state import DiagramState, ProgressiveToolsRunResult, MAX_REPAIR_CYCLES
from .handlers_construction import (
    handle_init_diagram,
    handle_add_point_fixed, handle_add_point_free, handle_add_point_on,
    handle_add_point_midpoint, handle_add_point_between, handle_add_point_foot,
    handle_add_point_rotate, handle_add_point_reflect, handle_add_point_triangle_center,
    handle_add_point_intersection,
    handle_add_segment, handle_add_ray, handle_add_line_through,
    handle_add_line_parallel_through, handle_add_line_perp_through,
    handle_add_line_angle_bisector, handle_add_line_tangent,
    handle_add_circle_center_point, handle_add_circle_center_radius, handle_add_circle_through3,
    handle_add_triangle, handle_add_polygon, handle_add_polygon_exterior,
    handle_remove_definition, handle_finalize_construction,
)
from .handlers_checks import (
    check_tool_names_for_state,
    handle_add_distinct_points_check, handle_add_distinct_objects_check,
    handle_add_collinear_check, handle_add_non_collinear_check,
    handle_add_parallel_check, handle_add_not_parallel_check,
    handle_add_perpendicular_check, handle_add_contains_check, handle_add_not_contains_check,
    handle_add_right_angle_check, handle_add_angle_equal_check,
    handle_add_equal_length_check, handle_add_ratio_equal_check,
    handle_add_similar_triangles_check, handle_add_tangent_check,
    handle_add_same_side_check, handle_add_opposite_side_check,
    handle_finalize_checks,
)
from .handlers_presentation import (
    presentation_tool_names_for_state,
    handle_draw, handle_draw_points, handle_fill,
    handle_mark_angles, handle_mark_right_angles, handle_mark_segments,
    handle_label_point, handle_label_angle, handle_label_segment,
    handle_finalize_render,
)

logger = logging.getLogger(__name__)


def _state_summary(state: DiagramState) -> str:
    """Return a brief human-readable summary of the current diagram state."""
    lines = []
    if state.canvas:
        lines.append(f"Canvas: xmin={state.canvas.xmin}, xmax={state.canvas.xmax}, "
                     f"ymin={state.canvas.ymin}, ymax={state.canvas.ymax}, grid={state.canvas.grid}, axes={state.canvas.axes}")
    if state.defs:
        lines.append(f"Defined objects ({len(state.defs)}):")
        for d in state.defs:
            if state.sym and d.id in state.sym:
                obj = state.sym[d.id]
                if isinstance(obj, spg.Point):
                    lines.append(f"  {d.id} ({d.kind}): ({float(obj.x):.3f}, {float(obj.y):.3f})")
                    continue
            lines.append(f"  {d.id} ({d.kind})")
    if state.checks:
        lines.append(f"Checks ({len(state.checks)}): " +
                     ", ".join(c.kind for c in state.checks))
    return "\n".join(lines) if lines else "(empty)"


def _build_canvas_agent(state: DiagramState, model: str) -> Agent:
    from strategies.instructions import PROGRESSIVE_TOOLS_PHASE1_INSTRUCTIONS
    agent = Agent(model, instructions=PROGRESSIVE_TOOLS_PHASE1_INSTRUCTIONS)

    @agent.tool_plain
    def init_diagram(
        grid: bool = False,
        axes: bool = False,
        xmin: float = -5, xmax: float = 5,
        ymin: float = -5, ymax: float = 5,
    ) -> str:
        """Initialize the diagram canvas. Call this once to set up the coordinate space. Use axes=True to draw coordinate axis lines."""
        return handle_init_diagram(state, grid=grid, axes=axes, xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax)

    return agent


def _build_construction_agent(
    state: DiagramState, model: str, repair_context: str = ""
) -> Agent:
    from strategies.instructions import (
        PROGRESSIVE_TOOLS_PHASE2_INSTRUCTIONS,
        PROGRESSIVE_TOOLS_PHASE2_REPAIR_PREFIX,
    )
    instructions = PROGRESSIVE_TOOLS_PHASE2_INSTRUCTIONS
    if repair_context:
        instructions = PROGRESSIVE_TOOLS_PHASE2_REPAIR_PREFIX + "\n\n" + instructions

    agent = Agent(
        model,
        instructions=instructions,
        model_settings=ModelSettings(parallel_tool_calls=True),
    )

    @agent.tool_plain
    def add_point_fixed(id: str, x: str, y: str) -> str:
        """Add a point at fixed coordinates. x and y can be numbers or expressions like 'pi/2'."""
        return handle_add_point_fixed(state, id, x, y)

    @agent.tool_plain
    def add_point_free(id: str, hint_xy: list[float] | None = None) -> str:
        """Add an unconstrained free point. Optionally provide a [x,y] placement hint."""
        return handle_add_point_free(state, id, hint_xy)

    @agent.tool_plain
    def add_point_on(id: str, on: str, how: dict) -> str:
        """Add a point constrained to lie on object 'on'. how: {kind: random|param|intent}."""
        return handle_add_point_on(state, id, on, how)

    @agent.tool_plain
    def add_point_midpoint(id: str, p: str, q: str) -> str:
        """Add a point at the midpoint of p and q."""
        return handle_add_point_midpoint(state, id, p, q)

    @agent.tool_plain
    def add_point_between(id: str, a: str, b: str, ratio: str | float) -> str:
        """Add a point on segment ab at position ratio (0=a, 1=b, or 'm:n' string)."""
        return handle_add_point_between(state, id, a, b, ratio)

    @agent.tool_plain
    def add_point_foot(id: str, source: str, onto: str) -> str:
        """Add the perpendicular foot from point 'source' onto line/segment/ray 'onto'."""
        return handle_add_point_foot(state, id, source, onto)

    @agent.tool_plain
    def add_point_rotate(id: str, center: str, source: str, angle: str | float) -> str:
        """Add a point by rotating 'source' around 'center' by angle (radians or expression)."""
        return handle_add_point_rotate(state, id, center, source, angle)

    @agent.tool_plain
    def add_point_reflect(id: str, source: str, across: str) -> str:
        """Add a point by reflecting 'source' across point or line 'across'."""
        return handle_add_point_reflect(state, id, source, across)

    @agent.tool_plain
    def add_point_triangle_center(id: str, tri: str, which: str) -> str:
        """Add a named triangle center. which: circumcenter|incenter|centroid|orthocenter."""
        return handle_add_point_triangle_center(state, id, tri, which)

    @agent.tool_plain
    def add_point_intersection(
        id: str, obj1: str, obj2: str, pick: dict | None = None
    ) -> str:
        """Add the intersection of obj1 and obj2. pick: {kind: index|closest_to|on_object|same_side|inside_triangle}."""
        return handle_add_point_intersection(state, id, obj1, obj2, pick)

    @agent.tool_plain
    def add_segment(id: str, a: str, b: str) -> str:
        """Add a finite segment from point a to point b."""
        return handle_add_segment(state, id, a, b)

    @agent.tool_plain
    def add_ray(id: str, a: str, b: str) -> str:
        """Add a ray starting at a, passing through b."""
        return handle_add_ray(state, id, a, b)

    @agent.tool_plain
    def add_line_through(id: str, a: str, b: str) -> str:
        """Add an infinite line through points a and b."""
        return handle_add_line_through(state, id, a, b)

    @agent.tool_plain
    def add_line_parallel_through(id: str, through: str, parallel_to: str) -> str:
        """Add a line through 'through' parallel to object 'parallel_to'."""
        return handle_add_line_parallel_through(state, id, through, parallel_to)

    @agent.tool_plain
    def add_line_perp_through(id: str, through: str, perp_to: str) -> str:
        """Add a line through 'through' perpendicular to object 'perp_to'."""
        return handle_add_line_perp_through(state, id, through, perp_to)

    @agent.tool_plain
    def add_line_angle_bisector(id: str, a: str, vertex: str, b: str) -> str:
        """Add the angle bisector of angle a-vertex-b."""
        return handle_add_line_angle_bisector(state, id, a, vertex, b)

    @agent.tool_plain
    def add_line_tangent(
        id: str, from_point: str, to_circle: str, pick: dict | None = None
    ) -> str:
        """Add a tangent line from external point 'from_point' to circle 'to_circle'."""
        return handle_add_line_tangent(state, id, from_point, to_circle, pick)

    @agent.tool_plain
    def add_circle_center_point(id: str, center: str, through: str) -> str:
        """Add a circle with given center passing through point 'through'."""
        return handle_add_circle_center_point(state, id, center, through)

    @agent.tool_plain
    def add_circle_center_radius(id: str, center: str, radius: str | float) -> str:
        """Add a circle by center and radius (number or expression)."""
        return handle_add_circle_center_radius(state, id, center, radius)

    @agent.tool_plain
    def add_circle_through3(id: str, a: str, b: str, c: str) -> str:
        """Add the circumscribed circle through three points."""
        return handle_add_circle_through3(state, id, a, b, c)

    @agent.tool_plain
    def add_triangle(id: str, a: str, b: str, c: str) -> str:
        """Add a triangle from three points."""
        return handle_add_triangle(state, id, a, b, c)

    @agent.tool_plain
    def add_polygon(id: str, vertices: list[str]) -> str:
        """Add a polygon from an ordered list of point IDs."""
        return handle_add_polygon(state, id, vertices)

    @agent.tool_plain
    def add_polygon_exterior(
        id: str, v1: str, v2: str, sides: int, ref_point: str
    ) -> str:
        """Add a regular polygon with 'sides' sides, built on edge v1-v2, opposite ref_point."""
        return handle_add_polygon_exterior(state, id, v1, v2, sides, ref_point)

    @agent.tool_plain
    def remove_definition(id: str) -> str:
        """Remove a definition and all definitions that depend on it (cascade removal)."""
        return handle_remove_definition(state, id)

    @agent.tool_plain
    def finalize_construction() -> str:
        """Compile all definitions with SymPy. Call this when you are done adding objects."""
        return handle_finalize_construction(state)

    return agent


def _build_checks_agent(state: DiagramState, model: str) -> Agent:
    from strategies.instructions import PROGRESSIVE_TOOLS_PHASE3_INSTRUCTIONS
    agent = Agent(model, instructions=PROGRESSIVE_TOOLS_PHASE3_INSTRUCTIONS)

    available_tools = check_tool_names_for_state(state)

    if "add_distinct_points_check" in available_tools:
        @agent.tool_plain
        def add_distinct_points_check(p: str, q: str, level: str = "must") -> str:
            """Add a check that two points are distinct (not coincident)."""
            return handle_add_distinct_points_check(state, p, q, level)

    if "add_distinct_objects_check" in available_tools:
        @agent.tool_plain
        def add_distinct_objects_check(a: str, b: str, level: str = "must") -> str:
            """Add a check that two objects are not identical."""
            return handle_add_distinct_objects_check(state, a, b, level)

    if "add_collinear_check" in available_tools:
        @agent.tool_plain
        def add_collinear_check(points: list[str], level: str = "must") -> str:
            """Add a check that a list of 3+ points are collinear."""
            return handle_add_collinear_check(state, points, level)

    if "add_non_collinear_check" in available_tools:
        @agent.tool_plain
        def add_non_collinear_check(p: str, q: str, r: str, level: str = "must") -> str:
            """Add a check that three points are NOT collinear."""
            return handle_add_non_collinear_check(state, p, q, r, level)

    if "add_parallel_check" in available_tools:
        @agent.tool_plain
        def add_parallel_check(l1: str, l2: str, level: str = "must") -> str:
            """Add a check that two lines/segments are parallel."""
            return handle_add_parallel_check(state, l1, l2, level)

    if "add_not_parallel_check" in available_tools:
        @agent.tool_plain
        def add_not_parallel_check(l1: str, l2: str, level: str = "must") -> str:
            """Add a check that two lines/segments are NOT parallel."""
            return handle_add_not_parallel_check(state, l1, l2, level)

    if "add_perpendicular_check" in available_tools:
        @agent.tool_plain
        def add_perpendicular_check(l1: str, l2: str, level: str = "must") -> str:
            """Add a check that two lines/segments are perpendicular."""
            return handle_add_perpendicular_check(state, l1, l2, level)

    if "add_contains_check" in available_tools:
        @agent.tool_plain
        def add_contains_check(obj: str, point: str, level: str = "must") -> str:
            """Add a check that object 'obj' contains point 'point'."""
            return handle_add_contains_check(state, obj, point, level)

    if "add_not_contains_check" in available_tools:
        @agent.tool_plain
        def add_not_contains_check(obj: str, point: str, level: str = "must") -> str:
            """Add a check that object 'obj' does NOT contain point 'point'."""
            return handle_add_not_contains_check(state, obj, point, level)

    if "add_right_angle_check" in available_tools:
        @agent.tool_plain
        def add_right_angle_check(a: str, vertex: str, b: str, level: str = "must") -> str:
            """Add a check that the angle a-vertex-b is a right angle (90 degrees)."""
            return handle_add_right_angle_check(state, a, vertex, b, level)

    if "add_angle_equal_check" in available_tools:
        @agent.tool_plain
        def add_angle_equal_check(
            a1: str, v1: str, b1: str,
            a2: str, v2: str, b2: str,
            level: str = "must",
        ) -> str:
            """Add a check that angle a1-v1-b1 equals angle a2-v2-b2."""
            return handle_add_angle_equal_check(state, a1, v1, b1, a2, v2, b2, level)

    if "add_equal_length_check" in available_tools:
        @agent.tool_plain
        def add_equal_length_check(segments: list[str], level: str = "must") -> str:
            """Add a check that all listed segment IDs have equal length."""
            return handle_add_equal_length_check(state, segments, level)

    if "add_ratio_equal_check" in available_tools:
        @agent.tool_plain
        def add_ratio_equal_check(
            s1: str, s2: str, s3: str, s4: str, level: str = "must"
        ) -> str:
            """Add a check that |s1|/|s2| == |s3|/|s4|."""
            return handle_add_ratio_equal_check(state, s1, s2, s3, s4, level)

    if "add_similar_triangles_check" in available_tools:
        @agent.tool_plain
        def add_similar_triangles_check(tri1: str, tri2: str, level: str = "must") -> str:
            """Add a check that two triangles are similar."""
            return handle_add_similar_triangles_check(state, tri1, tri2, level)

    if "add_tangent_check" in available_tools:
        @agent.tool_plain
        def add_tangent_check(line: str, circle: str, level: str = "must") -> str:
            """Add a check that a line/segment is tangent to a circle."""
            return handle_add_tangent_check(state, line, circle, level)

    if "add_same_side_check" in available_tools:
        @agent.tool_plain
        def add_same_side_check(
            line_a: str, line_b: str, p: str, q: str, level: str = "must"
        ) -> str:
            """Add a check that p and q are on the same side of the line through line_a and line_b."""
            return handle_add_same_side_check(state, line_a, line_b, p, q, level)

    if "add_opposite_side_check" in available_tools:
        @agent.tool_plain
        def add_opposite_side_check(
            line_a: str, line_b: str, p: str, q: str, level: str = "must"
        ) -> str:
            """Add a check that p and q are on opposite sides of the line through line_a and line_b."""
            return handle_add_opposite_side_check(state, line_a, line_b, p, q, level)

    @agent.tool_plain
    def finalize_checks() -> str:
        """Run all accumulated checks. Call this when done adding checks."""
        return handle_finalize_checks(state)

    return agent


def _build_presentation_agent(state: DiagramState, model: str, renderer: Renderer | None = None) -> Agent:
    from strategies.instructions import PROGRESSIVE_TOOLS_PHASE4_INSTRUCTIONS
    agent = Agent(
        model,
        instructions=PROGRESSIVE_TOOLS_PHASE4_INSTRUCTIONS,
        model_settings=ModelSettings(parallel_tool_calls=True),
    )

    available_tools = presentation_tool_names_for_state(state)

    if "draw" in available_tools:
        @agent.tool_plain
        def draw(obj_id: str) -> str:
            """Draw an object (segment, line, ray, circle, polygon, triangle)."""
            return handle_draw(state, obj_id)

    if "draw_points" in available_tools:
        @agent.tool_plain
        def draw_points(ids: list[str]) -> str:
            """Draw point markers for a list of point IDs."""
            return handle_draw_points(state, ids)

    if "fill" in available_tools:
        @agent.tool_plain
        def fill(obj_id: str, opacity: float = 1.0) -> str:
            """Fill a closed shape (polygon, triangle, circle) with optional opacity (0-1)."""
            return handle_fill(state, obj_id, opacity)

    if "mark_angles" in available_tools:
        @agent.tool_plain
        def mark_angles(
            a: str, vertex: str, b: str,
            which: str = "interior",
            group: str | None = None,
        ) -> str:
            """Place an arc angle mark on angle a-vertex-b. which: interior|exterior|reflex."""
            return handle_mark_angles(state, a, vertex, b, which, group)

    if "mark_right_angles" in available_tools:
        @agent.tool_plain
        def mark_right_angles(a: str, vertex: str, b: str) -> str:
            """Place a right-angle square marker on angle a-vertex-b."""
            return handle_mark_right_angles(state, a, vertex, b)

    if "mark_segments" in available_tools:
        @agent.tool_plain
        def mark_segments(seg_ids: list[str], group: str | None = None) -> str:
            """Place tick marks on the listed segment IDs. Use group to share the same symbol."""
            return handle_mark_segments(state, seg_ids, group)

    if "label_point" in available_tools:
        @agent.tool_plain
        def label_point(id: str, text: str | None = None, position: str = "auto") -> str:
            """Label a point. position: auto|above|below|left|right|above left|above right|below left|below right."""
            return handle_label_point(state, id, text, position)

    if "label_angle" in available_tools:
        @agent.tool_plain
        def label_angle(
            a: str, vertex: str, b: str, text: str, position: float = 0.5
        ) -> str:
            """Label the angle a-vertex-b with text."""
            return handle_label_angle(state, a, vertex, b, text, position)

    if "label_segment" in available_tools:
        @agent.tool_plain
        def label_segment(seg_id: str, text: str, pos: float = 0.5) -> str:
            """Label segment seg_id with text. pos: fraction along segment (0-1)."""
            return handle_label_segment(state, seg_id, text, pos)

    @agent.tool_plain
    def finalize_render() -> str:
        """Generate TikZ and render to SVG. Call this when done adding presentation."""
        return handle_finalize_render(state, renderer=renderer)

    return agent


class ProgressiveToolsStrategy(SubstanceStrategy):
    """4-phase progressive tool-use strategy."""

    def build_agent(self, model: str = DEFAULT_AGENT_MODEL) -> Agent:
        """Return Phase 2 construction agent as the 'primary' agent."""
        return _build_construction_agent(DiagramState(), model)

    async def run(
        self, prompt: str, model: str = DEFAULT_AGENT_MODEL, renderer: Renderer | None = None
    ) -> ProgressiveToolsRunResult:
        total_input = 0
        total_output = 0
        phase_traces: dict = {}
        phase_usage: dict = {}
        state = DiagramState()
        self._last_state = state  # expose for testing

        from ir import ir as ir_module

        def _capture(response, phase_name: str) -> None:
            nonlocal total_input, total_output
            u = response.usage()
            total_input += u.input_tokens or 0
            total_output += u.output_tokens or 0
            raw = response.all_messages_json()
            phase_traces[phase_name] = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
            phase_usage[phase_name] = {
                "input_tokens": u.input_tokens or 0,
                "output_tokens": u.output_tokens or 0,
                "requests": u.requests or 0,
            }
            # Update partial metrics so they're available on failure
            self._partial_input_tokens = total_input
            self._partial_output_tokens = total_output
            self._partial_tool_calls = state._tool_call_count
            self._partial_phase_traces = phase_traces
            self._partial_phase_usage = phase_usage
            self._partial_repair_cycles = state.repair_count

        # Phase 1: Canvas
        canvas_agent = _build_canvas_agent(state, model)
        canvas_prompt = f"Set up the canvas for this geometry diagram:\n{prompt}"
        resp = await canvas_agent.run(canvas_prompt)
        _capture(resp, "canvas")
        if state.canvas is None:
            state.canvas = ir_module.Canvas(
                kind="cartesian", xmin=-5, xmax=5, ymin=-5, ymax=5
            )

        # Phase 2: Construction (with repair loop)
        repair_context = ""
        while True:
            construction_agent = _build_construction_agent(state, model, repair_context)
            construction_prompt = (
                f"{repair_context}\n\n" if repair_context else ""
            ) + (
                f"Build the geometry for this diagram.\n\n"
                f"Current state:\n{_state_summary(state)}\n\n"
                f"Request: {prompt}\n\n"
                f"When done adding all objects, call finalize_construction()."
            )
            resp = await construction_agent.run(construction_prompt)
            construction_key = "construction" if state.repair_count == 0 else f"construction_r{state.repair_count}"
            _capture(resp, construction_key)

            if not state._construction_finalized:
                logger.warning("Construction agent did not call finalize_construction(); auto-finalizing.")
                auto_result = json.loads(handle_finalize_construction(state))
                if auto_result.get("status") == "error":
                    raise RuntimeError(f"Auto-finalize_construction failed: {auto_result.get('error')}")

            # Phase 3: Checks
            state.checks = []  # clear from any previous repair cycle
            checks_agent = _build_checks_agent(state, model)
            checks_prompt = (
                f"Add geometric checks for the diagram you just constructed.\n\n"
                f"Current state:\n{_state_summary(state)}\n\n"
                f"Request: {prompt}\n\n"
                f"When done adding checks, call finalize_checks()."
            )
            resp = await checks_agent.run(checks_prompt)
            checks_key = "checks" if state.repair_count == 0 else f"checks_r{state.repair_count}"
            _capture(resp, checks_key)

            if not state._checks_finalized and not state._last_check_results:
                # Agent didn't call finalize_checks at all — auto-finalize
                logger.warning("Checks agent did not call finalize_checks(); auto-finalizing.")
                handle_finalize_checks(state)

            if state._checks_finalized:
                break  # all must-checks passed, advance to phase 4

            # must-check failed → repair
            state.repair_count += 1
            if state.repair_count > MAX_REPAIR_CYCLES:
                raise RuntimeError(
                    f"ProgressiveToolsStrategy failed: check failures after "
                    f"{MAX_REPAIR_CYCLES} repair cycles."
                )
            failed_msgs = [
                r["message"]
                for r in (state._last_check_results or [])
                if not r["passed"] and r["level"] == "must"
            ]
            # Repair instructions appear in both repair_context (user prompt) and
            # PROGRESSIVE_TOOLS_PHASE2_REPAIR_PREFIX (system prompt) for emphasis.
            # Keep both in sync if changing repair guidance.
            repair_context = (
                "The previous construction failed the following checks:\n"
                + "\n".join(f"  - {m}" for m in failed_msgs)
                + "\n\nThe existing definitions are still loaded. "
                + "Use remove_definition() to remove incorrect objects, then re-add corrected ones. "
                + "Do NOT rebuild everything from scratch — only fix what's broken."
            )
            # Reset for repair
            state._construction_finalized = False
            state._checks_finalized = False
            state.sym = None
            # NOTE: state.defs is preserved — agent uses remove_definition() to fix specific objects
            state.render_ops = []

        # Phase 4: Presentation
        presentation_agent = _build_presentation_agent(state, model, renderer=renderer)
        presentation_prompt = (
            f"Add drawing and labeling commands for the completed diagram.\n\n"
            f"Current state:\n{_state_summary(state)}\n\n"
            f"Request: {prompt}\n\n"
            f"When done, call finalize_render() to generate the SVG."
        )
        resp = await presentation_agent.run(presentation_prompt)
        _capture(resp, "presentation")

        if not state._render_finalized:
            # Agent forgot to call finalize_render() — attempt auto-finalize
            auto_result = handle_finalize_render(state, renderer=renderer)
            logger.warning(
                "Presentation agent did not call finalize_render(); auto-finalizing. "
                "tool_calls count is inflated by 1 for this run."
            )
            data = json.loads(auto_result)
            if data.get("status") == "error":
                raise RuntimeError(f"Auto-finalize_render failed: {data['error']}")

        return ProgressiveToolsRunResult(
            tikz=state._tikz,
            svg=state._svg,
            input_tokens=total_input,
            output_tokens=total_output,
            repair_cycles=state.repair_count,
            tool_calls=state._tool_call_count,
            skipped_render_ids=state._render_warnings,
            phase_traces=phase_traces,
            phase_usage=phase_usage,
        )
