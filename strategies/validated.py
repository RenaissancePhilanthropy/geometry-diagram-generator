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
from .base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from .structured import INSTRUCTIONS_TEMPLATE

_MAX_VARIATIONS = 5
_GENERAL_CHECKS: list[CheckFn] = [check_no_collapsed_points, check_elements_in_bounds]


class ValidatedStrategy(SubstanceStrategy):
    """Like StructuredStrategy, but runs roger server-side to validate the rendered SVG.

    Tries up to _MAX_VARIATIONS seeds. For each, runs general checks (collapsed
    points, out-of-bounds) plus predicate-driven checks generated from the diagram
    (e.g. Parallel). The first variation that passes all checks wins; if none pass,
    the last one is returned as best-effort.

    Returns JSON {"substance": "...", "variation": "..."} so the client can
    re-render with the exact same seed.
    """

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
            substance = emitter.emit(diagram)
            predicate_checks = checks_from_diagram(diagram)
            all_checks = _GENERAL_CHECKS + predicate_checks

            last_variation = f"v-0"
            last_failures: list[str] = []

            failure_list = set()

            for i in range(_MAX_VARIATIONS):
                variation = f"v-{i}"
                try:
                    svg = render_svg(substance, variation=variation)
                except RuntimeError as e:
                    self.logger.debug(f"Rendering failed for variation '{variation}': {e}")
                    raise ModelRetry(str(e)) from e

                failures = run_checks(svg, diagram, all_checks)
                last_variation = variation
                last_failures = failures

                if failures: 
                    self.logger.debug(
                        f"Checks failed for variation '{variation}':\n{failure_list}"
                    )
                    failure_list.update(failures)
                if not failures:
                    # All checks passed, return this variation
                    self.logger.debug(
                        f"All checks passed for variation '{variation}'."
                    )
                    return json.dumps({"substance": substance, "variation": variation})

            if last_failures:
                failure_list = "\n".join(f"- {f}" for f in failure_list)
                self.logger.debug(
                    f"All {_MAX_VARIATIONS} variations failed checks for substance:\n{substance}"
                )
                self.logger.warning(
                    f"All {_MAX_VARIATIONS} variations failed checks. Last variation '{last_variation}' failures:\n{failure_list}"
                )
                raise ModelRetry(
                    f"All {_MAX_VARIATIONS} rendered variations failed visual checks. "
                    f"Please revise the diagram to fix these issues:\n{failure_list}"
                    f"\nNote that you will need to revise the substance to fix these issues. Rethink what constraints you have added and which you have not."
                )

        return agent
