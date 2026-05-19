"""Raw-code-with-revise strategy for geometry diagram generation.

Two-stage pipeline:
1. Draft agent generates TikZ and renders it.
2. Revision agent reviews the draft and MUST re-render (confirming or correcting it).

build_agent() returns the draft agent for use by the web app.
run()         orchestrates both stages programmatically via message history.
"""
import logging

from langgraph.prebuilt import create_react_agent

from .base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from .llm import get_chat_model
from .instructions import DRAFT_INSTRUCTIONS
from .stages import (
    make_render_tool, run_draft, run_revision,
    RawRunResult, extract_svg_from_messages, _extract_usage_from_messages,
)

logger = logging.getLogger(__name__)


class RawCodeWithReviseStrategy(SubstanceStrategy):
    def build_agent(self, model: str = DEFAULT_AGENT_MODEL):
        """Return the draft agent (single-pass) for web app use."""
        llm = get_chat_model(model)
        return create_react_agent(llm, tools=[make_render_tool()], prompt=DRAFT_INSTRUCTIONS)

    async def run(self, prompt: str, model: str = DEFAULT_AGENT_MODEL, renderer=None) -> RawRunResult:
        """Run draft then mandatory revision via message history chaining."""
        draft_state = await run_draft(prompt, model=model)
        draft_messages = draft_state["messages"]

        revision_state = await run_revision(model, message_history=draft_messages, force_rerender=True)
        all_messages = revision_state["messages"]

        input_tokens, output_tokens = _extract_usage_from_messages(all_messages)
        return RawRunResult(
            svg=extract_svg_from_messages(all_messages),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
