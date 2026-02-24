from pydantic_ai import Agent

from ir import PenroseEmitter, build_diagram_model, parse_domain
from .base import SubstanceStrategy

INSTRUCTIONS_TEMPLATE = """\
You are a helpful geometry diagram assistant. When a user asks you to draw or \
create a geometry diagram, call the render_diagram tool with a structured \
description of the diagram. Then briefly explain what you drew.

The following is the Penrose domain file that defines all available types, \
constructors, functions, and predicates you can use:

--- BEGIN DOMAIN ---
{domain}
--- END DOMAIN ---

Guidelines for building diagrams:
- Declare bare objects (no constructor) as GeoObject entries with only type and name.
- Use constructor entries for derived objects (e.g. Line L1 from points A, B).
- Only reference names that have been declared in the objects list.
- Include auto_label for all points you create so they appear labelled.
- Remember to use radians, not degrees, for any angle measures.
- Consider adding extra predicates to enforce implicit geometric relationships (e.g. using NonCollinear to enforce that three points are not collinear when they form a polygon).
- Consider using SetX, SetY, Anchor (use rarely!), Separation, and Orientation predicates to specify the layout of the diagram, so that it looks nice when rendered. They are not mandatory and should be used sparingly.
- You can also use MinAngle and MaxAngle predicates to constrain the range of angles in the diagram, which can help ensure a nice layout.
"""


class StructuredStrategy(SubstanceStrategy):
    def build_agent(self, domain: str) -> Agent:
        domain_info = parse_domain(domain)
        DiagramModel = build_diagram_model(domain_info)
        emitter = PenroseEmitter()

        agent = Agent(
            'anthropic:claude-sonnet-4-6',
            instructions=INSTRUCTIONS_TEMPLATE.format(domain=domain),
        )

        @agent.tool_plain(retries=3)
        def render_diagram(diagram: DiagramModel) -> str:  # type: ignore[valid-type]
            """Render a geometry diagram on the frontend."""
            return emitter.emit(diagram)

        return agent
