"""Raw-code-with-revise strategy for geometry diagram generation.

Two-stage pipeline:
1. Draft agent generates TikZ and renders it.
2. Revision agent reviews the draft and MUST re-render (confirming or correcting it).

build_agent() returns the draft agent for use by AGUIApp (web app).
run()         orchestrates both stages programmatically via agent hand-off.
"""
import logging

from pydantic_ai import Agent

from .base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from .instructions import DRAFT_INSTRUCTIONS
from .stages import register_render_tool, run_draft, run_revision, RawRunResult, extract_svg_from_messages

logger = logging.getLogger(__name__)


class RawCodeWithReviseStrategy(SubstanceStrategy):
    def build_agent(self, model: str = DEFAULT_AGENT_MODEL) -> Agent:
        """Return the draft agent (single-pass) for web app use."""
        agent = Agent(model, instructions=DRAFT_INSTRUCTIONS, model_settings=self.model_settings)
        register_render_tool(agent)
        return agent

    async def run(self, prompt: str, model: str = DEFAULT_AGENT_MODEL, renderer=None) -> RawRunResult:  # noqa: ARG002
        """Run draft then mandatory revision via programmatic agent hand-off."""
        draft = await run_draft(prompt, model=model, model_settings=self.model_settings)
        result = await run_revision(
            model,
            message_history=draft.all_messages(),
            usage=draft.usage(),
            force_rerender=True,
            model_settings=self.model_settings,
        )
        usage = result.usage()
        return RawRunResult(
            svg=extract_svg_from_messages(result.all_messages()),
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
        )
