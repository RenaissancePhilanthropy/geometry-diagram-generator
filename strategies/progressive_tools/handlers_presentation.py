"""Phase 4 (presentation) tool handlers, tool filtering, and finalize_render."""
from __future__ import annotations

import json

from ir import ir
from ir.ir import DiagramIR
from ir.renderer import Renderer, TikZRenderer
from .state import DiagramState
from .handlers_checks import _POINT_KINDS, _CIRCLE_KINDS

_CLOSED_SHAPE_KINDS = {"triangle", "polygon", "polygon_exterior"} | _CIRCLE_KINDS


def presentation_tool_names_for_state(state: DiagramState) -> list[str]:
    """Return presentation tool names applicable to the current construction."""
    kinds = [d.kind for d in state.defs]
    point_count = sum(1 for k in kinds if k in _POINT_KINDS)
    segment_count = sum(1 for k in kinds if k == "segment")
    has_closed = any(k in _CLOSED_SHAPE_KINDS for k in kinds)

    tools = ["draw", "draw_points", "finalize_render"]

    if has_closed:
        tools.append("fill")
    if segment_count >= 1:
        tools += ["mark_segments", "label_segment"]
    if point_count >= 3:
        tools += ["mark_angles", "mark_right_angles", "label_angle"]
    if point_count >= 1:
        tools.append("label_point")

    return tools


def _render_op_registered(kind: str) -> str:
    return json.dumps({"status": "registered", "op": kind})


def handle_draw(state: DiagramState, obj_id: str) -> str:
    state._tool_call_count += 1
    state.render_ops.append(ir.Draw(obj=obj_id))
    return _render_op_registered("draw")


def handle_draw_points(state: DiagramState, ids: list[str]) -> str:
    state._tool_call_count += 1
    state.render_ops.append(ir.DrawPoints(points=ids))
    return _render_op_registered("draw_points")


def handle_fill(
    state: DiagramState, obj_id: str, opacity: float = 1.0
) -> str:
    state._tool_call_count += 1
    state.render_ops.append(ir.Fill(obj=obj_id, opacity=opacity))
    return _render_op_registered("fill")


def handle_mark_angles(
    state: DiagramState,
    a: str,
    vertex: str,
    b: str,
    which: str = "interior",
    group: str | None = None,
) -> str:
    state._tool_call_count += 1
    angle = ir.AnglePoints(a=a, o=vertex, b=b)
    state.render_ops.append(ir.MarkAngles(angles=[angle], which=which, group=group))
    return _render_op_registered("mark_angles")


def handle_mark_right_angles(
    state: DiagramState, a: str, vertex: str, b: str
) -> str:
    state._tool_call_count += 1
    angle = ir.AnglePoints(a=a, o=vertex, b=b)
    state.render_ops.append(ir.MarkRightAngles(angles=[angle]))
    return _render_op_registered("mark_right_angles")


def handle_mark_segments(
    state: DiagramState,
    seg_ids: list[str],
    group: str | None = None,
) -> str:
    state._tool_call_count += 1
    state.render_ops.append(ir.MarkSegments(segs=seg_ids, group=group))
    return _render_op_registered("mark_segments")


def handle_label_point(
    state: DiagramState,
    id: str,
    text: str | None = None,
    position: str = "auto",
) -> str:
    state._tool_call_count += 1
    state.render_ops.append(ir.LabelPoint(p=id, text=text or id, pos=position))
    return _render_op_registered("label_point")


def handle_label_angle(
    state: DiagramState,
    a: str, vertex: str, b: str,
    text: str,
    position: float = 0.5,
) -> str:
    state._tool_call_count += 1
    angle = ir.AnglePoints(a=a, o=vertex, b=b)
    state.render_ops.append(ir.LabelAngle(angle=angle, text=text))
    return _render_op_registered("label_angle")


def handle_label_segment(
    state: DiagramState,
    seg_id: str,
    text: str,
    pos: float = 0.5,
) -> str:
    state._tool_call_count += 1
    state.render_ops.append(ir.LabelSegment(seg=seg_id, text=text, pos=pos))
    return _render_op_registered("label_segment")


def handle_finalize_render(state: DiagramState, renderer: Renderer | None = None) -> str:
    """Assemble DiagramIR, generate TikZ, render to SVG."""
    state._tool_call_count += 1
    if state.sym is None:
        return json.dumps({"status": "error", "error": "Construction not finalized. Call finalize_construction() first."})
    diagram = DiagramIR(
        canvas=state.canvas,
        define=state.defs,
        checks=state.checks,
        render=state.render_ops,
    )
    _renderer = renderer if renderer is not None else TikZRenderer()
    try:
        render_warnings: list[str] = []
        render_result = _renderer.render(diagram, state.sym, warnings=render_warnings)
        state._render_warnings = render_warnings
    except Exception as e:
        return json.dumps({"status": "error", "error": f"Render failed: {e}"})
    tikz = render_result.intermediate
    svg = render_result.output

    state._render_finalized = True
    state._tikz = tikz
    state._svg = svg
    return json.dumps({"status": "ok", "tikz_length": len(tikz), "svg_length": len(svg)})
