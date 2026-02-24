import json

from pydantic_ai import Agent, ModelRetry

from ir import PenroseEmitter, build_diagram_model, parse_domain
from util.roger import render_svg
from util.svg_checks import (
    CheckFn,
    check_elements_in_bounds,
    check_no_collapsed_points,
    checks_from_diagram,
    run_checks,
)
from .base import SubstanceStrategy
from .structured import INSTRUCTIONS_TEMPLATE

_MAX_VARIATIONS = 5
_GENERAL_CHECKS: list[CheckFn] = [check_no_collapsed_points, check_elements_in_bounds]


class   ValidatedStrategy(SubstanceStrategy):
    """Like StructuredStrategy, but runs roger server-side to validate the rendered SVG.

    Tries up to _MAX_VARIATIONS seeds. For each, runs general checks (collapsed
    points, out-of-bounds) plus predicate-driven checks generated from the diagram
    (e.g. Parallel). The first variation that passes all checks wins; if none pass,
    the last one is returned as best-effort.

    Returns JSON {"substance": "...", "variation": "..."} so the client can
    re-render with the exact same seed.
    """

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
            substance = emitter.emit(diagram)
            predicate_checks = checks_from_diagram(diagram)
            all_checks = _GENERAL_CHECKS + predicate_checks

            last_variation = f"v-0"
            last_failures: list[str] = []

            for i in range(_MAX_VARIATIONS):
                variation = f"v-{i}"
                try:
                    svg = render_svg(substance, variation=variation)
                except RuntimeError as e:
                    raise ModelRetry(str(e)) from e

                failures = run_checks(svg, diagram, all_checks)
                last_variation = variation
                last_failures = failures

                if not failures:
                    break

            if last_failures:
                print(
                    f"ValidatedStrategy: all {_MAX_VARIATIONS} variations failed checks "
                    f"({last_failures!r}), using last one ({last_variation})"
                )

            return json.dumps({"substance": substance, "variation": last_variation})

        return agent
