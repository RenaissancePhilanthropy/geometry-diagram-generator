from pydantic_ai import Agent

from .base import SubstanceStrategy

INSTRUCTIONS_TEMPLATE = """\
You are a helpful geometry diagram assistant. When a user asks you to draw or \
create a geometry diagram, generate valid Penrose substance code and call the \
render_diagram tool. Then briefly explain what you drew.

The following is the Penrose domain file that defines all available types, \
constructors, functions, and predicates you can use in substance code:

--- BEGIN DOMAIN ---
{domain}
--- END DOMAIN ---

Rules for generating substance code:
- Only use types, constructors, functions, and predicates defined in the domain above.
- Declare all objects before using them in predicates.
- Group bare declarations by type (e.g. "Point A, B, C").
- Use constructor syntax for derived objects (e.g. "Line L := Line(A, B)").
- Include a final AutoLabel directive for all points you create.
- Do not include markdown formatting or code fences in the substance string passed \
to render_diagram — pass raw Penrose substance syntax only.
- NEVER use dot notation (e.g. "obj.field") — substance has no property access syntax. \
Predicate arguments must be declared object names, numeric literals, or quoted string literals only.
- Do not invent predicates, types, or constructors that are not in the domain file.
- Remember to use radians, not degrees, for any angle measures.
"""


class RawCodeStrategy(SubstanceStrategy):
    def build_agent(self, domain: str) -> Agent:
        agent = Agent(
            'anthropic:claude-sonnet-4-6',
            instructions=INSTRUCTIONS_TEMPLATE.format(domain=domain),
        )

        @agent.tool_plain
        def render_diagram(substance: str) -> str:
            """Render a Penrose diagram with the given substance code on the frontend."""
            return substance

        return agent
