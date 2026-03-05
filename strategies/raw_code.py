import json
import logging

from pydantic_ai import Agent, ModelRetry

from util.tikz_renderer import render_tikz
from .base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from .instructions import RAW_TIKZ_INSTRUCTIONS

logger = logging.getLogger(__name__)

INSTRUCTIONS = f"""\
You are a helpful geometry diagram assistant. When a user asks you to draw or \
create a geometry diagram, generate TikZ code using the tkz-euclide package \
and call the render_diagram tool. Then briefly explain what you drew.

{RAW_TIKZ_INSTRUCTIONS}
"""


class RawCodeStrategy(SubstanceStrategy):
    def build_agent(self, model: str = DEFAULT_AGENT_MODEL) -> Agent:
        agent = Agent(model, instructions=INSTRUCTIONS)

        @agent.tool_plain(retries=3)
        def render_diagram(tikz: str, tkzelements: str = "") -> str:
            """Render a geometry diagram using TikZ/tkz-euclide code."""
            logger.debug("render_diagram called — tikz=%d chars, tkzelements=%d chars",
                         len(tikz), len(tkzelements))
            logger.info("tikz code:\n%s", tikz)
            try:
                svg = render_tikz(tikz, tkzelements=tkzelements or None)
                logger.info("render_diagram succeeded — svg=%d chars", len(svg))
            except RuntimeError as e:
                logger.warning("render_diagram failed (will retry): %s", e)
                raise ModelRetry(str(e)) from e
            return json.dumps({"svg": svg})

        return agent
