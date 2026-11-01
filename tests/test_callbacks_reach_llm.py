"""Callbacks passed to render_geometry_diagram / edit_geometry_diagram reach every
LLM call, for recipe, python_full and structured.

A real BaseChatModel subclass stands in for the provider so the LangChain callback
machinery runs: the recording handler counts on_chat_model_start events, one per
model invocation, and only sees them if the run config actually reached the call.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda

from geometry_diagrams import GeometryConfig, edit_geometry_diagram, render_geometry_diagram
from geometry_diagrams.ir.ir import DiagramIR
from geometry_diagrams.recipe.dsl import RecipeDSL
from geometry_diagrams.strategies import python_full as pf
from geometry_diagrams.strategies import recipe as recipe_mod
from geometry_diagrams.strategies import structured as structured_mod
from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
from geometry_diagrams.strategies.python_full import PydslScriptOutput

SCRIPT = "a = point(0, 0)\nb = point(4, 0)\nc = point(0, 3)\nt = triangle(a, b, c)\ndraw(t)\n"
EDIT_REPLY = "<<<<<<< SEARCH\nc = point(0, 3)\n=======\nc = point(0, 5)\n>>>>>>> REPLACE"


class Recorder(BaseCallbackHandler):
    def __init__(self) -> None:
        self.model_calls = 0

    def on_chat_model_start(self, serialized, messages, **kwargs: Any) -> None:
        self.model_calls += 1


class StubChat(BaseChatModel):
    """Plain calls return `text`; structured output returns `payload` as `parsed`."""

    text: str = ""
    payload: Any = None

    @property
    def _llm_type(self) -> str:
        return "stub"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.text))])

    def with_structured_output(self, schema, *, include_raw=False, **kwargs):
        payload = self.payload
        return self | RunnableLambda(
            lambda msg: {"raw": msg, "parsed": payload, "parsing_error": None}
        )


@pytest.fixture(autouse=True)
def no_env_tracing(monkeypatch):
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    from geometry_diagrams.util import tracing

    tracing._reset()
    yield
    tracing._reset()


def _pipeline_result() -> StructuredRunResult:
    return StructuredRunResult(
        diagram_ir=DiagramIR(define=[], checks=[], render=[]),
        tikz="", svg="<svg/>", sym_table={}, sym_full={},
    )


def _patched(strategy: str, stub: StubChat):
    """Patches for one strategy: the model factory, plus the IR pipeline where the
    payload is an empty construction (recipe/structured)."""
    if strategy == "recipe":
        return [
            patch.object(recipe_mod, "get_chat_model", return_value=stub),
            patch.object(recipe_mod, "load_catalog", return_value=[]),
            patch.object(recipe_mod, "lower_to_ir", return_value=MagicMock()),
            patch.object(recipe_mod, "require_features"),
            patch.object(recipe_mod, "_run_ir_pipeline", new=AsyncMock(return_value=_pipeline_result())),
        ]
    if strategy == "structured":
        return [
            patch.object(structured_mod, "get_chat_model", return_value=stub),
            patch.object(structured_mod, "_run_ir_pipeline", new=AsyncMock(return_value=_pipeline_result())),
        ]
    return [patch.object(pf, "get_chat_model", return_value=stub)]


def _stub(strategy: str, *, edit: bool) -> StubChat:
    if strategy == "recipe":
        return StubChat(
            text='{"selected_recipes": [], "unmatched_concepts": []}',
            payload=RecipeDSL(construction=[]),
        )
    if strategy == "structured":
        return StubChat(payload=DiagramIR(define=[], checks=[], render=[]))
    return StubChat(text=EDIT_REPLY if edit else "", payload=PydslScriptOutput(script=SCRIPT))


# LLM invocations per call: recipe = selector + generation; the others one.
_EXPECTED_CALLS = {"recipe": 2, "python_full": 1, "structured": 1}


def _prior(strategy: str) -> dict:
    if strategy == "recipe":
        return {"previous_dsl": RecipeDSL(construction=[]).model_dump()}
    if strategy == "structured":
        return {"previous_ir": DiagramIR(define=[], checks=[], render=[]).model_dump()}
    return {"previous_script": SCRIPT}


def _config(strategy: str) -> GeometryConfig:
    return GeometryConfig(strategy=strategy, renderer="svg", edit_generation_mode="search_replace")


async def _enter(patches):
    for p in patches:
        p.start()


def _exit(patches):
    for p in patches:
        p.stop()


@pytest.mark.asyncio
async def test_graph_nodes_pass_their_run_config_to_the_llm_call_explicitly():
    """Independent of context propagation: the node's own config is handed to ainvoke."""
    seen: list = []

    class Spy(StubChat):
        def with_structured_output(self, schema, *, include_raw=False, **kwargs):
            outer = self

            class _Chain:
                async def ainvoke(self, messages, config=None, **kw):
                    seen.append(config)
                    return {"raw": AIMessage(content=""), "parsed": outer.payload, "parsing_error": None}

            return _Chain()

    spy = Spy(payload=DiagramIR(define=[], checks=[], render=[]))
    node_config = {"callbacks": [Recorder()], "tags": ["t"]}
    state = {
        "prompt": "p", "model_id": "anthropic:claude-sonnet-4-6", "enable_cache": False,
        "attempt": 0, "last_error": "", "warnings": [], "input_tokens": 0, "output_tokens": 0,
        "cost_usd": 0.0,
    }
    with patch.object(structured_mod, "get_chat_model", return_value=spy):
        await structured_mod._generate_ir_node(state, node_config)
    assert seen == [node_config]


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["recipe", "python_full", "structured"])
@pytest.mark.parametrize("via", ["callbacks", "run_config"])
async def test_render_callbacks_reach_llm_calls(strategy, via):
    recorder = Recorder()
    kwargs = {"callbacks": [recorder]} if via == "callbacks" else {"run_config": {"callbacks": [recorder]}}
    patches = _patched(strategy, _stub(strategy, edit=False))
    await _enter(patches)
    try:
        await render_geometry_diagram("a triangle", config=_config(strategy), **kwargs)
    finally:
        _exit(patches)
    assert recorder.model_calls == _EXPECTED_CALLS[strategy]


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["recipe", "python_full", "structured"])
@pytest.mark.parametrize("via", ["callbacks", "run_config"])
async def test_edit_callbacks_reach_llm_calls(strategy, via):
    recorder = Recorder()
    kwargs = {"callbacks": [recorder]} if via == "callbacks" else {"run_config": {"callbacks": [recorder]}}
    patches = _patched(strategy, _stub(strategy, edit=True))
    await _enter(patches)
    try:
        await edit_geometry_diagram(
            "move c up", config=_config(strategy), **_prior(strategy), **kwargs,
        )
    finally:
        _exit(patches)
    assert recorder.model_calls == _EXPECTED_CALLS[strategy]
