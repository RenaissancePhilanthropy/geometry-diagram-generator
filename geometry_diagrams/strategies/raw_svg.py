"""Raw SVG strategy: the LLM writes SVG directly, no TikZ or Docker required."""
import json
import logging

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from .base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from .llm import get_chat_model
from .stages import RawRunResult, extract_svg_from_messages, _extract_usage_from_messages

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


def make_svg_render_tool():
    """Return an SVG render_diagram tool."""

    @tool
    def render_diagram(svg: str) -> str:
        """Submit the completed SVG document for the geometry diagram.

        Args:
            svg: A complete, self-contained <svg> element.
        Returns:
            JSON with svg field on success, or error field on failure.
        """
        logger.debug("render_diagram called — svg=%d chars", len(svg))
        if not svg.strip().startswith("<svg"):
            return json.dumps({"error": "Output must be a valid <svg> element starting with <svg"})
        return json.dumps({"svg": svg})

    return render_diagram


class RawSVGStrategy(SubstanceStrategy):
    def build_agent(self, model: str = DEFAULT_AGENT_MODEL, renderer=None):
        llm = get_chat_model(model)
        return create_react_agent(llm, tools=[make_svg_render_tool()], prompt=DRAFT_INSTRUCTIONS)

    async def run(
        self,
        prompt: str,
        model: str = DEFAULT_AGENT_MODEL,
        renderer=None,
    ) -> RawRunResult:
        graph = self.build_agent(model=model)
        state = await graph.ainvoke({"messages": [("user", prompt)]}, config=self._run_config)
        messages = state["messages"]
        input_tokens, output_tokens = _extract_usage_from_messages(messages)
        return RawRunResult(
            svg=extract_svg_from_messages(messages),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
