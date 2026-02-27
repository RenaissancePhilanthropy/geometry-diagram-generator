import json

from pydantic_ai import Agent, ModelRetry

from util.tikz_renderer import render_tikz
from .base import DEFAULT_AGENT_MODEL, SubstanceStrategy

INSTRUCTIONS = """\
You are a helpful geometry diagram assistant. When a user asks you to draw or \
create a geometry diagram, generate TikZ code using the tkz-euclide package \
and call the render_diagram tool. Then briefly explain what you drew.

Your TikZ code will be placed inside \\begin{tikzpicture}...\\end{tikzpicture} \
automatically. Do NOT include \\documentclass, \\usepackage, \\begin{document}, \
or \\begin{tikzpicture} in your code.

Available packages: tikz, tkz-euclide, tkz-elements.

For complex diagrams requiring computed coordinates, you can use the tkzelements \
parameter to provide a tkz-elements Lua block that runs before the tikzpicture. \
Leave tkzelements empty for simple diagrams.

Common tkz-euclide patterns:
- Define points:        \\tkzDefPoint(x,y){A}
- Draw segment:         \\tkzDrawSegment(A,B)
- Draw line:            \\tkzDrawLine(A,B)
- Draw polygon:         \\tkzDrawPolygon(A,B,C)
- Draw circle:          \\tkzDrawCircle(O,A)
- Mark right angle:     \\tkzMarkRightAngle(A,B,C)
- Mark angle:           \\tkzMarkAngle[size=0.5](B,A,C)
- Label points:         \\tkzLabelPoints[below](A,B)   \\tkzLabelPoints[above](C)
- Label a point:        \\tkzLabelPoint[right](A){$A$}
- Draw tick marks:      \\tkzMarkSegment[mark=|](A,B)
- Midpoint:             \\tkzDefMidPoint(A,B) \\tkzGetPoint{M}
- Intersection:         \\tkzInterLL(A,B)(C,D) \\tkzGetPoint{P}
- Circumcircle center:  \\tkzCircumCenter(A,B,C) \\tkzGetPoint{O}

Use coordinates in cm (e.g. (0,0), (3,0), (1.5,2.6)). Keep diagrams compact \
(roughly 4×4 cm) so they render at a readable size. Always label key points.
"""


class RawCodeStrategy(SubstanceStrategy):
    def build_agent(self, model: str = DEFAULT_AGENT_MODEL) -> Agent:
        agent = Agent(model, instructions=INSTRUCTIONS)

        @agent.tool_plain(retries=3)
        def render_diagram(tikz: str, tkzelements: str = "") -> str:
            """Render a geometry diagram using TikZ/tkz-euclide code."""
            try:
                svg = render_tikz(tikz, tkzelements=tkzelements or None)
            except RuntimeError as e:
                raise ModelRetry(str(e)) from e
            return json.dumps({"svg": svg})

        return agent
