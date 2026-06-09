"""Raw SVG with revision strategy: draft SVG then mandatory revision pass."""
import logging

from langgraph.prebuilt import create_react_agent

from .base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from .llm import get_chat_model
from .raw_svg import DRAFT_INSTRUCTIONS, REVISION_FORCE_INSTRUCTIONS, REVISION_PROMPT, make_svg_render_tool
from .stages import RawRunResult, extract_svg_from_messages, _extract_usage_from_messages

logger = logging.getLogger(__name__)


class RawSVGWithReviseStrategy(SubstanceStrategy):
    def build_agent(self, model: str = DEFAULT_AGENT_MODEL, renderer=None):
        """Return the draft agent for web app use."""
        llm = get_chat_model(model)
        return create_react_agent(llm, tools=[make_svg_render_tool()], prompt=DRAFT_INSTRUCTIONS)

    async def run(
        self,
        prompt: str,
        model: str = DEFAULT_AGENT_MODEL,
        renderer=None,
    ) -> RawRunResult:
        # Draft pass
        draft_graph = self.build_agent(model=model)
        draft_state = await draft_graph.ainvoke({"messages": [("user", prompt)]})
        draft_messages = draft_state["messages"]

        # Revision pass — must re-render
        llm = get_chat_model(model)
        revision_graph = create_react_agent(
            llm, tools=[make_svg_render_tool()], prompt=REVISION_FORCE_INSTRUCTIONS
        )
        revision_state = await revision_graph.ainvoke({
            "messages": list(draft_messages) + [("user", REVISION_PROMPT)]
        })
        all_messages = revision_state["messages"]

        input_tokens, output_tokens = _extract_usage_from_messages(all_messages)
        return RawRunResult(
            svg=extract_svg_from_messages(all_messages),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
