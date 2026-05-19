import json
import logging

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from util.tikz_renderer import render_tikz
from .base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from .llm import get_chat_model
from .instructions import RAW_TIKZ_INSTRUCTIONS
from .stages import RawRunResult, extract_svg_from_messages, _extract_usage_from_messages

logger = logging.getLogger(__name__)

INSTRUCTIONS = f"""\
You are a helpful geometry diagram assistant. When a user asks you to draw or \
create a geometry diagram, generate TikZ code using the tkz-euclide package \
and call the render_diagram tool. Then briefly explain what you drew.

{RAW_TIKZ_INSTRUCTIONS}
"""


class RawCodeStrategy(SubstanceStrategy):
    def build_agent(self, model: str = DEFAULT_AGENT_MODEL, renderer=None):
        llm = get_chat_model(model)

        @tool
        def render_diagram(tikz: str, tkzelements: str = "") -> str:
            """Render a geometry diagram using TikZ/tkz-euclide code.

            Args:
                tikz: TikZ code for the diagram.
                tkzelements: Optional tkz-elements code.
            Returns:
                JSON with svg field on success, or error field on failure.
            """
            logger.debug("render_diagram called — tikz=%d chars", len(tikz))
            logger.info("tikz code:\n%s", tikz)
            try:
                svg = render_tikz(tikz, tkzelements=tkzelements or None)
                logger.info("render_diagram succeeded — svg=%d chars", len(svg))
                return json.dumps({"svg": svg})
            except RuntimeError as e:
                logger.warning("render_diagram failed: %s", e)
                return json.dumps({"error": str(e)})

        return create_react_agent(llm, tools=[render_diagram], prompt=INSTRUCTIONS)

    async def run(self, prompt: str, model: str = DEFAULT_AGENT_MODEL, renderer=None) -> RawRunResult:
        from util.message_helpers import count_tool_calls, extract_tool_call_args

        graph = self.build_agent(model=model)
        state = await graph.ainvoke({"messages": [("user", prompt)]})
        messages = state["messages"]
        input_tokens, output_tokens = _extract_usage_from_messages(messages)
        tool_args = extract_tool_call_args(messages, "render_diagram") or {}
        tool_calls = count_tool_calls(messages, "render_diagram")
        return RawRunResult(
            svg=extract_svg_from_messages(messages),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tikz=tool_args.get("tikz"),
            tkzelements=tool_args.get("tkzelements") or None,
            tool_calls=tool_calls,
            retries=max(0, tool_calls - 1),
        )
