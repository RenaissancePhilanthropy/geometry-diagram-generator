from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional, TypedDict

from pydantic import BaseModel, Field, ValidationError
from langgraph.graph import StateGraph, START, END

from .base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from .llm import (
    get_chat_model, is_gemini_model, requires_raw_text_generation,
    requires_forced_function_calling, extract_usage, extract_cost, make_system_message,
)
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


_CODE_FENCE_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def _extract_script_from_raw_text(text: "str | None") -> "str | None":
    """Salvage a usable script from a model's raw message text when
    with_structured_output failed to parse it as JSON — some models don't
    honor the structured-output/tool-calling contract and just write plain or
    markdown-fenced code instead. Prefers the contents of a ```python fenced
    block if present (stripping any surrounding prose); otherwise falls back
    to the raw text itself. Returns None if there's nothing usable at all."""
    if not text or not text.strip():
        return None
    match = _CODE_FENCE_RE.search(text)
    if match:
        fenced = match.group(1).strip()
        return fenced or None
    return text.strip()


def _unescape_literal_newlines(script: "str | None") -> "str | None":
    """Some models (observed: nvidia.nemotron-super-3-120b via Bedrock Mantle)
    intermittently emit every line break in their script field as a literal
    two-character "\\n" sequence instead of an actual newline, collapsing the
    whole script onto one line that fails to parse with "unexpected character
    after line continuation character". Verified against a corpus of 485 such
    failures from a 2026-08-06 curriculum run: 434/485 (89.5%) become valid,
    compilable Python after this exact substitution; the rest were separately
    truncated outputs (cut off mid-statement) that this doesn't and shouldn't
    touch. Gated on "zero real newlines AND at least one literal \\n" so this
    is a no-op on any already-well-formed script."""
    if script is None:
        return None
    if "\n" not in script and "\\n" in script:
        return script.replace("\\n", "\n")
    return script


@dataclass
class PythonFullAttemptTrace:
    attempt: int
    script: "str | None"
    error: "str | None"
    stage: str  # "generation" | "sandbox" | "nothing_drawn" | "ir_pipeline" | "success"


@dataclass
class PythonFullMetadata:
    attempt_traces: list[PythonFullAttemptTrace] = field(default_factory=list)


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
    cost_usd: float
    renderer: Optional[Any]
    metadata: PythonFullMetadata


async def _generate_script_node(state: PythonFullPipelineState) -> dict:
    """Call the LLM to generate a pydsl script from the prompt."""
    model_id = state["model_id"]
    enable_cache = state.get("enable_cache", False)
    attempt = state["attempt"]
    last_error = state.get("last_error", "")
    metadata = state["metadata"]

    prompt = state["prompt"]
    if attempt > 0 and last_error:
        prompt = f"{prompt}\n\nPrevious attempt failed: {last_error}\nPlease produce a corrected script."

    from langchain_core.messages import HumanMessage
    messages = [
        make_system_message(build_python_full_instructions(), enable_cache=enable_cache, model_id=model_id),
        HumanMessage(content=prompt),
    ]

    try:
        llm = get_chat_model(model_id, enable_cache=enable_cache)

        if requires_raw_text_generation(model_id):
            # This provider rejects both with_structured_output methods this
            # pipeline supports (see llm.py's _RAW_TEXT_ONLY_MODELS) — skip
            # structured output entirely and salvage from plain text, the
            # ONLY viable path here, not a fallback used only on parse failure.
            raw_msg = await llm.ainvoke(messages)
            in_tok, out_tok = extract_usage(raw_msg)
            cost = extract_cost(raw_msg)
            cost_usd = state["cost_usd"] + (cost or 0.0)
            raw_content = raw_msg.content if isinstance(raw_msg.content, str) else None
            salvaged = _unescape_literal_newlines(_extract_script_from_raw_text(raw_content))
            if salvaged is not None:
                metadata.attempt_traces.append(PythonFullAttemptTrace(
                    attempt=attempt + 1, script=salvaged, error=None, stage="generation",
                ))
                return {
                    "script": salvaged,
                    "last_error": "",
                    "input_tokens": state["input_tokens"] + in_tok,
                    "output_tokens": state["output_tokens"] + out_tok,
                    "cost_usd": cost_usd,
                }
            error_text = "No usable script in raw-text response"
            metadata.attempt_traces.append(PythonFullAttemptTrace(
                attempt=attempt + 1, script=None, error=error_text, stage="generation",
            ))
            return {
                "script": None,
                "last_error": error_text,
                "attempt": attempt + 1,
                "input_tokens": state["input_tokens"] + in_tok,
                "output_tokens": state["output_tokens"] + out_tok,
                "cost_usd": cost_usd,
            }

        if is_gemini_model(model_id):
            structured = llm.with_structured_output(PydslScriptOutput, method="json_mode", include_raw=True)
        elif requires_forced_function_calling(model_id):
            # Only for models confirmed to need it (see llm.py's
            # _FORCED_FUNCTION_CALLING_MODELS) — do NOT force this by default
            # for every model. Forcing it universally regressed
            # mantle-oa:google.gemma-4-31b from 84% to 57% pass rate
            # (2026-08-07): auto-detection is what most models, including
            # gemma, actually need; qwen3.7-flash is the confirmed exception.
            structured = llm.with_structured_output(
                PydslScriptOutput, method="function_calling", include_raw=True
            )
        else:
            structured = llm.with_structured_output(PydslScriptOutput, include_raw=True)

        response = await structured.ainvoke(messages)
        raw_msg = response.get("raw")
        parsed = response.get("parsed")
        in_tok, out_tok = extract_usage(raw_msg) if raw_msg else (0, 0)
        cost = extract_cost(raw_msg) if raw_msg else None
        cost_usd = state["cost_usd"] + (cost or 0.0)

        if parsed is None:
            # Some models don't honor the structured-output/tool-calling contract and
            # just write plain or markdown-fenced code instead of JSON — salvage that
            # rather than treating it as an unrecoverable parse failure.
            raw_content = getattr(raw_msg, "content", None) if raw_msg else None
            if not isinstance(raw_content, str):
                raw_content = None
            salvaged = _unescape_literal_newlines(_extract_script_from_raw_text(raw_content))
            if salvaged is not None:
                metadata.attempt_traces.append(PythonFullAttemptTrace(
                    attempt=attempt + 1, script=salvaged, error=None, stage="generation",
                ))
                return {
                    "script": salvaged,
                    "last_error": "",
                    "input_tokens": state["input_tokens"] + in_tok,
                    "output_tokens": state["output_tokens"] + out_tok,
                    "cost_usd": cost_usd,
                }

            parsing_error = response.get("parsing_error") or "Failed to parse script output"
            metadata.attempt_traces.append(PythonFullAttemptTrace(
                attempt=attempt + 1, script=None, error=str(parsing_error), stage="generation",
            ))
            return {
                "script": None,
                "last_error": str(parsing_error),
                "attempt": attempt + 1,
                "input_tokens": state["input_tokens"] + in_tok,
                "output_tokens": state["output_tokens"] + out_tok,
                "cost_usd": cost_usd,
            }

        fixed_script = _unescape_literal_newlines(parsed.script)
        metadata.attempt_traces.append(PythonFullAttemptTrace(
            attempt=attempt + 1, script=fixed_script, error=None, stage="generation",
        ))
        return {
            "script": fixed_script,
            "last_error": "",
            "input_tokens": state["input_tokens"] + in_tok,
            "output_tokens": state["output_tokens"] + out_tok,
            "cost_usd": cost_usd,
        }
    except Exception as exc:
        # For some models, with_structured_output doesn't gracefully return
        # parsed=None on a JSON-parse failure (the `if parsed is None` branch
        # above) — it raises a pydantic ValidationError directly instead. That
        # error's errors()[0]["input"] carries the full, untruncated raw text
        # that failed to parse as JSON (unlike str(exc), which pydantic
        # truncates for display) — salvage from it the same way.
        salvaged = None
        if isinstance(exc, ValidationError):
            for err in exc.errors():
                candidate = err.get("input")
                if isinstance(candidate, str):
                    salvaged = _unescape_literal_newlines(_extract_script_from_raw_text(candidate))
                    if salvaged is not None:
                        break
        if salvaged is not None:
            metadata.attempt_traces.append(PythonFullAttemptTrace(
                attempt=attempt + 1, script=salvaged, error=None, stage="generation",
            ))
            return {"script": salvaged, "last_error": ""}

        logger.warning(f"_generate_script_node attempt {attempt} failed: {exc}")
        metadata.attempt_traces.append(PythonFullAttemptTrace(
            attempt=attempt + 1, script=None, error=str(exc), stage="generation",
        ))
        return {
            "script": None,
            "last_error": str(exc),
            "attempt": attempt + 1,
        }


async def _run_script_node(state: PythonFullPipelineState) -> dict:
    """Run the sandboxed script, then the deterministic compile/check/render pipeline."""
    script = state["script"]
    renderer = state.get("renderer")
    metadata = state.get("metadata")

    if script is None:
        # _generate_script_node already incremented attempt on failure — don't double-count,
        # and don't touch the trace it already appended for this attempt.
        return {"last_error": "No script available to run"}

    result = await asyncio.to_thread(run_script, script, timeout_seconds=SANDBOX_TIMEOUT_SECONDS)

    if result.error is not None:
        # retry_message is None for ExecutionTimeoutError (sandbox.py's timeout branch never
        # sets it) — fall back to result.error so last_error is never empty on that path.
        error_text = result.retry_message or result.error
        if metadata is not None:
            metadata.attempt_traces[-1].stage = "sandbox"
            metadata.attempt_traces[-1].error = error_text
        return {
            "last_error": error_text,
            "attempt": state["attempt"] + 1,
            "result": None,
        }

    diagram_ir = result.diagram_ir
    if not diagram_ir.render:
        error_text = (
            f"Diagram has {len(diagram_ir.define)} definitions but nothing was "
            "drawn — call draw()/draw_points() on what should be visible before finishing."
        )
        if metadata is not None:
            metadata.attempt_traces[-1].stage = "nothing_drawn"
            metadata.attempt_traces[-1].error = error_text
        return {
            "last_error": error_text,
            "attempt": state["attempt"] + 1,
            "result": None,
        }

    try:
        pipeline_result = await run_ir_pipeline(diagram_ir, renderer)
        pipeline_result.retries = state["attempt"]
        if metadata is not None:
            metadata.attempt_traces[-1].stage = "success"
        return {"result": pipeline_result}
    except (IRCompileError, RuntimeError) as e:
        if metadata is not None:
            metadata.attempt_traces[-1].stage = "ir_pipeline"
            metadata.attempt_traces[-1].error = str(e)
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

    _partial_python_full_metadata: "PythonFullMetadata | None" = None
    _partial_input_tokens: int = 0
    _partial_output_tokens: int = 0
    _partial_cost_usd: "float | None" = None

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
            "cost_usd": 0.0,
            "renderer": renderer,
            "metadata": PythonFullMetadata(),
        }
        final_state = await graph.ainvoke(initial_state, config=self._run_config)

        # Expose partial metadata for the eval harness, before the possible raise below.
        self._partial_python_full_metadata = final_state.get("metadata")
        self._partial_input_tokens = final_state.get("input_tokens", 0)
        self._partial_output_tokens = final_state.get("output_tokens", 0)
        # cost_usd stays None (not 0.0) when the provider never reported cost
        # (e.g. Bedrock) — 0.0 accumulated tokens-side would misleadingly read
        # as "confirmed free" rather than "unknown."
        self._partial_cost_usd = final_state.get("cost_usd") or None

        if final_state.get("result") is None:
            raise RuntimeError(
                f"PythonFullStrategy failed after {MAX_RETRIES} attempts. "
                f"Last error: {final_state.get('last_error', 'unknown')}"
            )
        result = final_state["result"]
        result.python_full_metadata = final_state.get("metadata")
        result.input_tokens = final_state.get("input_tokens", 0)
        result.output_tokens = final_state.get("output_tokens", 0)
        result.cost_usd = self._partial_cost_usd
        return result

    def build_agent(self, model: str = DEFAULT_AGENT_MODEL, renderer=None):
        """Not implemented for this PoC — this strategy has no conversational-agent
        requirement yet. Real chat wiring (render_diagram/query_diagram tools, as
        structured.py provides) is deferred until this strategy actually needs it."""
        raise NotImplementedError(
            "PythonFullStrategy doesn't support build_agent() yet — use .run() directly."
        )
