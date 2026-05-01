"""Raw SVG with revision strategy: draft SVG then mandatory revision pass."""
import logging

from pydantic_ai import Agent

from .base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from .raw_svg import REVISION_FORCE_INSTRUCTIONS, REVISION_PROMPT, register_svg_render_tool
from .stages import RawRunResult, extract_svg_from_messages

logger = logging.getLogger(__name__)


class RawSVGWithReviseStrategy(SubstanceStrategy):
    def build_agent(self, model: str = DEFAULT_AGENT_MODEL) -> Agent:
        """Return the draft agent for web app use."""
        from .raw_svg import DRAFT_INSTRUCTIONS
        agent = Agent(model, instructions=DRAFT_INSTRUCTIONS, model_settings=self.model_settings)
        register_svg_render_tool(agent)
        return agent

    async def run(
        self,
        prompt: str,
        model: str = DEFAULT_AGENT_MODEL,
        renderer=None,
    ) -> RawRunResult:
        # Draft pass
        draft_agent = self.build_agent(model=model)
        draft = await draft_agent.run(prompt)

        # Revision pass — must re-render
        revision_agent = Agent(model, instructions=REVISION_FORCE_INSTRUCTIONS, model_settings=self.model_settings)
        register_svg_render_tool(revision_agent)
        result = await revision_agent.run(
            REVISION_PROMPT,
            message_history=draft.all_messages(),
            usage=draft.usage(),
        )

        usage = result.usage()
        return RawRunResult(
            svg=extract_svg_from_messages(result.all_messages()),
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
        )
