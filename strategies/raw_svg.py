"""Raw SVG strategy: the LLM writes SVG directly, no TikZ or Docker required."""
import json
import logging

from pydantic_ai import Agent, ModelRetry

from .base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from .stages import RawRunResult, extract_svg_from_messages

logger = logging.getLogger(__name__)

_SVG_GUIDELINES = """\
SVG guidelines:
- Output a self-contained <svg> element with explicit width and height (e.g. 400×400).
- Use a viewBox (e.g. viewBox="0 0 400 400") so the diagram scales cleanly.
- Draw geometry using standard SVG primitives: <line>, <circle>, <polygon>, \
<polyline>, <path>, <ellipse>, <rect>.
- Label points and lengths with <text> elements; use a readable font size (12–14px).
- Mark right angles with a small square using <rect> or <path>.
- Use stroke="black" fill="none" for lines and polygons unless colour is requested.
- Keep coordinates precise — compute them from the geometric constraints, don't guess.
- Do not include XML declarations, DOCTYPE, or any wrapper outside the <svg> tag."""

DRAFT_INSTRUCTIONS = f"""\
You are a helpful geometry diagram assistant. When a user asks you to draw or \
create a geometry diagram, generate a complete SVG document and call the \
render_diagram tool. Then briefly explain what you drew.

{_SVG_GUIDELINES}
"""

_REVISION_CHECKLIST = """\
- Are all requested points present and correctly labeled?
- Do the geometric relationships hold (angles, equal sides, perpendicularity, etc.)?
- Are all required marks present (right-angle squares, tick marks, arc marks)?
- Are labels positioned so they don't overlap with lines or each other?"""

REVISION_PROMPT = "Please review the SVG diagram you just drew and render a corrected version."

REVISION_FORCE_INSTRUCTIONS = f"""\
You are a geometry diagram reviewer. A draft SVG diagram has already been generated. \
Review it carefully against the original request and check:
{_REVISION_CHECKLIST}

You MUST call render_diagram with your reviewed/corrected SVG, even if no changes \
are needed — this confirms the final diagram.

{_SVG_GUIDELINES}
"""


def register_svg_render_tool(agent: Agent, retries: int = 3) -> None:
    """Attach an SVG render_diagram tool to agent."""

    @agent.tool_plain(retries=retries)
    def render_diagram(svg: str) -> str:
        """Submit the completed SVG document for the geometry diagram."""
        logger.debug("render_diagram called — svg=%d chars", len(svg))
        if not svg.strip().startswith("<svg"):
            raise ModelRetry("Output must be a valid <svg> element starting with <svg")
        return json.dumps({"svg": svg})


class RawSVGStrategy(SubstanceStrategy):
    def build_agent(self, model: str = DEFAULT_AGENT_MODEL) -> Agent:
        agent = Agent(model, instructions=DRAFT_INSTRUCTIONS, model_settings=self.model_settings)
        register_svg_render_tool(agent)
        return agent

    async def run(
        self,
        prompt: str,
        model: str = DEFAULT_AGENT_MODEL,
        renderer=None,
    ) -> RawRunResult:
        result = await self.build_agent(model=model).run(prompt)
        usage = result.usage()
        return RawRunResult(
            svg=extract_svg_from_messages(result.all_messages()),
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
        )
