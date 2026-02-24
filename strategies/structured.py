from pydantic_ai import Agent

from ir import PenroseEmitter, build_diagram_model, parse_domain
from .base import DEFAULT_AGENT_MODEL, SubstanceStrategy

INSTRUCTIONS_TEMPLATE = """\
You are a helpful geometry diagram assistant. When a user asks you to draw or \
create a geometry diagram, call the render_diagram tool with a structured \
description of the diagram. Then briefly explain what you drew.

Your diagrams are intended to educate about geometry concepts, so focus on clarity and correctness. \

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
- Use either Collinear or Between, not both, to express collinearity. Between implies a stricter ordering that may not always hold.
- Consider adding extra predicates to enforce implicit geometric relationships (e.g. using NonCollinear to enforce that three points are not collinear when they form a polygon).
- Use MinAngle and MaxAngle to constrain angles and improve layout, but avoid over-constraining which can make it impossible to find a valid rendering.
- MinLength and LengthClass are useful for constraining relative lengths.
- Parallel is for lines that should have some separation, Collinear is better for lines that should overlap.
- Consider using SetX, SetY, Anchor (use rarely!), Separation, and Orientation predicates to specify the layout of the diagram, so that it looks nice when rendered. They are not mandatory and should be used sparingly.
- You can also use MinAngle and MaxAngle predicates to constrain the range of angles in the diagram, which can help ensure a nice layout.
"""


class StructuredStrategy(SubstanceStrategy):
    def build_agent(self, domain: str, model: str = DEFAULT_AGENT_MODEL) -> Agent:
        domain_info = parse_domain(domain)
        DiagramModel = build_diagram_model(domain_info)
        emitter = PenroseEmitter()

        agent = Agent(
            model,
            instructions=INSTRUCTIONS_TEMPLATE.format(domain=domain),
        )

        @agent.tool_plain(retries=3)
        def render_diagram(diagram: DiagramModel) -> str:  # type: ignore[valid-type]
            """Render a geometry diagram on the frontend."""
            return emitter.emit(diagram)

        return agent
