from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, TypedDict

from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END

from .base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from .llm import get_chat_model, is_gemini_model, extract_usage, make_system_message
from .instructions_python_full import build_python_full_instructions
from .ir_pipeline import StructuredRunResult, run_ir_pipeline
from ..ir.errors import IRCompileError
from ..ir.renderer import Renderer, TikZRenderer
from ..pydsl.sandbox import run_script

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
SANDBOX_TIMEOUT_SECONDS = 10.0  # vs. run_script's own 5.0 default — real LLM-generated
                                 # constructions may be larger than hand-authored test scripts.


class PydslScriptOutput(BaseModel):
    script: str = Field(description="A Python script using only the provided pydsl API.")


class PythonFullPipelineState(TypedDict):
    prompt: str
    model_id: str
    enable_cache: bool
    attempt: int
    last_error: str
    script: Optional[str]
    result: Optional[StructuredRunResult]
    input_tokens: int
    output_tokens: int
    renderer: Optional[Any]


async def _generate_script_node(state: PythonFullPipelineState) -> dict:
    """Call the LLM to generate a pydsl script from the prompt."""
    model_id = state["model_id"]
    enable_cache = state.get("enable_cache", False)
    attempt = state["attempt"]
    last_error = state.get("last_error", "")

    prompt = state["prompt"]
    if attempt > 0 and last_error:
        prompt = f"{prompt}\n\nPrevious attempt failed: {last_error}\nPlease produce a corrected script."

    from langchain_core.messages import HumanMessage
    messages = [
        make_system_message(build_python_full_instructions(), enable_cache=enable_cache),
        HumanMessage(content=prompt),
    ]

    try:
        llm = get_chat_model(model_id, enable_cache=enable_cache)
        if is_gemini_model(model_id):
            structured = llm.with_structured_output(PydslScriptOutput, method="json_mode", include_raw=True)
        else:
            structured = llm.with_structured_output(PydslScriptOutput, include_raw=True)

        response = await structured.ainvoke(messages)
        raw_msg = response.get("raw")
        parsed = response.get("parsed")
        in_tok, out_tok = extract_usage(raw_msg) if raw_msg else (0, 0)

        if parsed is None:
            parsing_error = response.get("parsing_error") or "Failed to parse script output"
            return {
                "script": None,
                "last_error": str(parsing_error),
                "attempt": attempt + 1,
                "input_tokens": state["input_tokens"] + in_tok,
                "output_tokens": state["output_tokens"] + out_tok,
            }

        return {
            "script": parsed.script,
            "last_error": "",
            "input_tokens": state["input_tokens"] + in_tok,
            "output_tokens": state["output_tokens"] + out_tok,
        }
    except Exception as exc:
        logger.warning(f"_generate_script_node attempt {attempt} failed: {exc}")
        return {
            "script": None,
            "last_error": str(exc),
            "attempt": attempt + 1,
        }


async def _run_script_node(state: PythonFullPipelineState) -> dict:
    """Run the sandboxed script, then the deterministic compile/check/render pipeline."""
    script = state["script"]
    renderer = state.get("renderer")

    if script is None:
        # _generate_script_node already incremented attempt on failure — don't double-count.
        return {"last_error": "No script available to run"}

    result = await asyncio.to_thread(run_script, script, timeout_seconds=SANDBOX_TIMEOUT_SECONDS)

    if result.error is not None:
        # retry_message is None for ExecutionTimeoutError (sandbox.py's timeout branch never
        # sets it) — fall back to result.error so last_error is never empty on that path.
        return {
            "last_error": result.retry_message or result.error,
            "attempt": state["attempt"] + 1,
            "result": None,
        }

    diagram_ir = result.diagram_ir
    if not diagram_ir.render:
        return {
            "last_error": (
                f"Diagram has {len(diagram_ir.define)} definitions but nothing was "
                "drawn — call draw()/draw_points() on what should be visible before finishing."
            ),
            "attempt": state["attempt"] + 1,
            "result": None,
        }

    try:
        pipeline_result = await run_ir_pipeline(diagram_ir, renderer)
        pipeline_result.retries = state["attempt"]
        return {"result": pipeline_result}
    except (IRCompileError, RuntimeError) as e:
        return {
            "last_error": str(e),
            "attempt": state["attempt"] + 1,
            "result": None,
        }


def _pipeline_router(state: PythonFullPipelineState) -> str:
    if state.get("result") is not None:
        return END
    if state["attempt"] < MAX_RETRIES:
        return "generate_script"
    return END


def _build_python_full_graph() -> StateGraph:
    builder = StateGraph(PythonFullPipelineState)
    builder.add_node("generate_script", _generate_script_node)
    builder.add_node("run_script", _run_script_node)
    builder.add_edge(START, "generate_script")
    builder.add_edge("generate_script", "run_script")
    builder.add_conditional_edges("run_script", _pipeline_router)
    return builder.compile()


class PythonFullStrategy(SubstanceStrategy):
    """pydsl-based strategy: LLM writes a sandboxed Python script, compiled + rendered deterministically."""

    async def run(
        self,
        prompt: str,
        model: str = DEFAULT_AGENT_MODEL,
        renderer: Renderer | None = None,
    ) -> StructuredRunResult:
        graph = _build_python_full_graph()
        initial_state: PythonFullPipelineState = {
            "prompt": prompt,
            "model_id": model,
            "enable_cache": self.enable_cache,
            "attempt": 0,
            "last_error": "",
            "script": None,
            "result": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "renderer": renderer,
        }
        final_state = await graph.ainvoke(initial_state, config=self._run_config)
        if final_state.get("result") is None:
            raise RuntimeError(
                f"PythonFullStrategy failed after {MAX_RETRIES} attempts. "
                f"Last error: {final_state.get('last_error', 'unknown')}"
            )
        return final_state["result"]

    def build_agent(self, model: str = DEFAULT_AGENT_MODEL, renderer=None):
        """Not implemented for this PoC — this strategy has no conversational-agent
        requirement yet. Real chat wiring (render_diagram/query_diagram tools, as
        structured.py provides) is deferred until this strategy actually needs it."""
        raise NotImplementedError(
            "PythonFullStrategy doesn't support build_agent() yet — use .run() directly."
        )
