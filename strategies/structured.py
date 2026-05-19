from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional, TypedDict

import sympy.geometry as spg

from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent

from strategies.base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from strategies.llm import get_chat_model, is_gemini_model, extract_usage, make_system_message
from strategies.instructions import STRUCTURED_STRATEGY_IR_INSTRUCTIONS
from ir.ir import DiagramIR
from ir.to_sympy import compile_defs
from ir.checks import run_checks, check_render_angles, CheckResult
from ir.renderer import Renderer, TikZRenderer
from ir.errors import IRCompileError
from ir.queries import (
    query_coordinate, query_distance, query_angle,
    query_length, query_radius, query_area, query_perimeter, list_objects,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3

_BUILD_AGENT_INSTRUCTIONS = """\
You are a geometry diagram assistant. When the user asks you to draw a diagram, \
call the render_diagram tool with their request, then briefly explain what was drawn.

When modifying a previously rendered diagram, pass a complete, self-contained description \
of the desired diagram to render_diagram — not just the change. The system has the \
previous diagram's specification available, but your request should describe the full \
intended result (e.g. "right triangle with legs 3 and 4, now with the hypotenuse labeled" \
rather than just "label the hypotenuse").

After a diagram is rendered, you can answer questions about its geometric properties \
(coordinates, distances, angles, lengths, areas, etc.) by calling query_diagram with \
the appropriate query_type and params. To see available object IDs, call query_diagram \
with query_type="list_objects" and params={}.
"""


# ── result / output types ─────────────────────────────────────────────────────

@dataclass
class StructuredRunResult:
    diagram_ir: DiagramIR
    tikz: str
    svg: str
    sym_table: dict  # id -> (float, float) coords
    sym_full: dict   # id -> sympy object
    input_tokens: int = 0
    output_tokens: int = 0
    recipe_metadata: Any = None


# ── IR pipeline (deterministic, no LLM) ──────────────────────────────────────

async def _run_ir_pipeline(
    diagram_ir: DiagramIR,
    renderer: Renderer | None = None,
) -> StructuredRunResult:
    """Compile DiagramIR -> SymPy -> checks -> TikZ/SVG. Raises RuntimeError on failure."""
    if renderer is None:
        renderer = TikZRenderer()

    # SymPy compilation and checks are CPU-bound — run off the event loop thread
    # so they don't block async timeouts or concurrent eval runs.
    sym = await asyncio.to_thread(compile_defs, diagram_ir)

    results = await asyncio.to_thread(run_checks, diagram_ir.checks, sym)
    must_failures = [r for r in results if not r.passed and r.check.level == "must"]
    if must_failures:
        msgs = "; ".join(r.message for r in must_failures)
        raise RuntimeError(f"Geometric checks failed: {msgs}")

    angle_failures = await asyncio.to_thread(check_render_angles, diagram_ir, sym)
    if angle_failures:
        triples = ", ".join(str(t) for t in angle_failures)
        raise RuntimeError(f"Invalid angle triples (not three distinct points): {triples}")

    render_result = await asyncio.to_thread(renderer.render, diagram_ir, sym)

    sym_table = {k: (float(v.x), float(v.y)) for k, v in sym.items() if isinstance(v, spg.Point)}

    return StructuredRunResult(
        diagram_ir=diagram_ir,
        tikz=render_result.intermediate,
        svg=render_result.output,
        sym_table=sym_table,
        sym_full=sym,
    )


# ── query dispatch ────────────────────────────────────────────────────────────

def dispatch_query(sym: dict, query_type: str, args: dict) -> str:
    """Dispatch a query about the compiled geometry."""
    def _get(args: dict, *keys: str) -> str:
        for k in keys:
            if k in args:
                return args[k]
        raise KeyError(f"Expected one of {keys}, got {list(args)}")

    try:
        if query_type == "list_objects":
            return json.dumps(list_objects(sym))
        elif query_type == "coordinate":
            return json.dumps(query_coordinate(sym, _get(args, "point", "id")))
        elif query_type == "distance":
            a = _get(args, "a", "id1", "point1")
            b = _get(args, "b", "id2", "point2")
            return json.dumps(query_distance(sym, a, b))
        elif query_type == "angle":
            vertex = args["vertex"]
            a = _get(args, "a", "ray1")
            b = _get(args, "b", "ray2")
            return json.dumps(query_angle(sym, a, vertex, b))
        elif query_type == "length":
            return json.dumps(query_length(sym, _get(args, "segment", "id")))
        elif query_type == "radius":
            return json.dumps(query_radius(sym, _get(args, "circle", "id")))
        elif query_type == "area":
            return json.dumps(query_area(sym, _get(args, "object", "id")))
        elif query_type == "perimeter":
            return json.dumps(query_perimeter(sym, _get(args, "object", "id")))
        else:
            return json.dumps({"error": f"Unknown query_type: {query_type}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── inner pipeline graph ──────────────────────────────────────────────────────

class StructuredPipelineState(TypedDict):
    prompt: str
    model_id: str
    enable_cache: bool
    attempt: int
    last_error: str
    diagram_ir: Optional[DiagramIR]
    result: Optional[StructuredRunResult]
    input_tokens: int
    output_tokens: int
    renderer: Optional[Any]


async def _generate_ir_node(state: StructuredPipelineState) -> dict:
    """Call LLM to generate a DiagramIR from the prompt."""
    model_id = state["model_id"]
    enable_cache = state.get("enable_cache", False)
    attempt = state["attempt"]
    last_error = state.get("last_error", "")

    prompt = state["prompt"]
    if attempt > 0 and last_error:
        prompt = f"{prompt}\n\nPrevious attempt failed: {last_error}\nPlease produce a corrected DiagramIR."

    from langchain_core.messages import HumanMessage
    messages = [
        make_system_message(STRUCTURED_STRATEGY_IR_INSTRUCTIONS, enable_cache=enable_cache),
        HumanMessage(content=prompt),
    ]

    try:
        llm = get_chat_model(model_id, enable_cache=enable_cache)
        if is_gemini_model(model_id):
            structured = llm.with_structured_output(DiagramIR, method="json_mode", include_raw=True)
        else:
            structured = llm.with_structured_output(DiagramIR, include_raw=True)

        response = await structured.ainvoke(messages)
        # include_raw=True returns {"raw": AIMessage, "parsed": DiagramIR|None, "parsing_error": ...}
        raw_msg = response.get("raw")
        diagram_ir = response.get("parsed")
        in_tok, out_tok = extract_usage(raw_msg) if raw_msg else (0, 0)

        if diagram_ir is None:
            parsing_error = response.get("parsing_error") or "Failed to parse DiagramIR"
            return {
                "diagram_ir": None,
                "last_error": str(parsing_error),
                "attempt": attempt + 1,
                "input_tokens": state["input_tokens"] + in_tok,
                "output_tokens": state["output_tokens"] + out_tok,
            }

        return {
            "diagram_ir": diagram_ir,
            "last_error": "",
            "input_tokens": state["input_tokens"] + in_tok,
            "output_tokens": state["output_tokens"] + out_tok,
        }
    except Exception as exc:
        logger.warning(f"_generate_ir_node attempt {attempt} failed: {exc}")
        return {
            "diagram_ir": None,
            "last_error": str(exc),
            "attempt": attempt + 1,
        }


async def _run_pipeline_node(state: StructuredPipelineState) -> dict:
    """Run the deterministic IR pipeline (compile -> check -> render)."""
    diagram_ir = state["diagram_ir"]
    renderer = state.get("renderer")

    if diagram_ir is None:
        return {
            "last_error": "No DiagramIR available to run pipeline",
            "attempt": state["attempt"] + 1,
        }

    try:
        result = await _run_ir_pipeline(diagram_ir, renderer)
        return {"result": result}
    except (IRCompileError, RuntimeError) as e:
        return {
            "last_error": str(e),
            "attempt": state["attempt"] + 1,
            "result": None,
        }


def _pipeline_router(state: StructuredPipelineState) -> str:
    if state.get("result") is not None:
        return END
    if state["attempt"] < MAX_RETRIES:
        return "generate_ir"
    return END


def _build_structured_graph() -> StateGraph:
    builder = StateGraph(StructuredPipelineState)
    builder.add_node("generate_ir", _generate_ir_node)
    builder.add_node("run_pipeline", _run_pipeline_node)
    builder.add_edge(START, "generate_ir")
    builder.add_edge("generate_ir", "run_pipeline")
    builder.add_conditional_edges("run_pipeline", _pipeline_router)
    return builder.compile()


# ── strategy class ────────────────────────────────────────────────────────────

class StructureStrategy(SubstanceStrategy):
    """IR-based strategy: LLM generates DiagramIR, compiled + rendered deterministically."""

    async def run(
        self,
        prompt: str,
        model: str = DEFAULT_AGENT_MODEL,
        renderer: Renderer | None = None,
    ) -> StructuredRunResult:
        graph = _build_structured_graph()
        initial_state: StructuredPipelineState = {
            "prompt": prompt,
            "model_id": model,
            "enable_cache": self.enable_cache,
            "attempt": 0,
            "last_error": "",
            "diagram_ir": None,
            "result": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "renderer": renderer,
        }
        final_state = await graph.ainvoke(initial_state)
        if final_state.get("result") is None:
            raise RuntimeError(
                f"StructureStrategy failed after {MAX_RETRIES} attempts. "
                f"Last error: {final_state.get('last_error', 'unknown')}"
            )
        return final_state["result"]

    def build_agent(self, model: str = DEFAULT_AGENT_MODEL, renderer=None):
        """Return a conversational ReAct agent with render_diagram + query_diagram tools."""
        _last_sym: dict | None = None
        _last_ir: DiagramIR | None = None
        _renderer = renderer if renderer is not None else TikZRenderer()

        @tool
        async def render_diagram(request: str) -> str:
            """Render a geometry diagram from a natural language description.

            Args:
                request: Full description of the diagram to render.
            Returns:
                JSON with svg field on success, or error field on failure.
            """
            nonlocal _last_sym, _last_ir
            try:
                result = await self.run(request, model=model, renderer=_renderer)
                _last_sym = result.sym_full
                _last_ir = result.diagram_ir
                return json.dumps({"svg": result.svg})
            except Exception as e:
                return json.dumps({"error": str(e)})

        @tool
        def query_diagram(query_type: str, params: dict) -> str:
            """Query geometric properties of the most recently rendered diagram.

            Args:
                query_type: One of: list_objects, coordinate, distance, angle, length, radius, area, perimeter
                params: Query arguments (e.g. {"id": "A"} for coordinate)
            Returns:
                JSON with query result or error.
            """
            if _last_sym is None:
                return json.dumps({"error": "No diagram rendered yet"})
            return dispatch_query(_last_sym, query_type, params)

        llm = get_chat_model(model)
        return create_react_agent(llm, tools=[render_diagram, query_diagram], prompt=_BUILD_AGENT_INSTRUCTIONS)
