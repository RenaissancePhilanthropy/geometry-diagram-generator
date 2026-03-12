from __future__ import annotations

import json
import logging

from pydantic_ai import Agent

from strategies.base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from strategies.instructions import STRUCTURED_REFINE_INSTRUCTIONS, STRUCTURED_REFINE_PROMPT
from strategies.stages import register_render_tool
from strategies.structured import StructureStrategy, StructuredRunResult
from util.message_helpers import extract_tool_call_args, extract_tool_return
from util.tikz_analysis import (
    extract_canvas_features,
    extract_labels,
    resolve_all_coordinates,
    validate_expected_points,
    validate_required_canvas,
    validate_required_labels,
)

logger = logging.getLogger(__name__)

_REFINE_COORD_TOLERANCE = 1e-4


def _labeled_points(tikz: str) -> set[str]:
    labeled: set[str] = set()
    for label in extract_labels(tikz):
        if label["type"] == "label_points":
            labeled.update(label["points"])
        elif label["type"] == "label_point":
            labeled.add(label["point"])
    return labeled


def _refinement_constraints_satisfied(
    original_tikz: str,
    refined_tikz: str,
    tolerance: float = _REFINE_COORD_TOLERANCE,
) -> bool:
    """Return True if refinement preserves point coordinates, labels, and grid/axes."""
    original_coords = {
        name: [xy[0], xy[1]]
        for name, xy in resolve_all_coordinates(original_tikz).items()
        if not name.startswith("_")
    }
    refined_coords = resolve_all_coordinates(refined_tikz)
    if original_coords:
        coord_check = validate_expected_points(refined_coords, original_coords, tolerance=tolerance)
        if not coord_check["passed"]:
            return False

    required_canvas = {
        feature: True
        for feature, present in extract_canvas_features(original_tikz).items()
        if present
    }
    if required_canvas:
        canvas_check = validate_required_canvas(refined_tikz, required_canvas)
        if not canvas_check["passed"]:
            return False

    required_labels = sorted(_labeled_points(original_tikz))
    if required_labels:
        label_check = validate_required_labels(refined_tikz, required_labels)
        if not label_check["passed"]:
            return False

    return True


class StructuredPlusRefineStrategy(SubstanceStrategy):
    """
    Run the structured pipeline first, then refine the deterministic TikZ draft.

    The refinement pass is accepted only if it preserves the original point
    coordinates, labels, and any visible grid/axes features.
    """

    def build_agent(self, model: str = DEFAULT_AGENT_MODEL) -> Agent:
        # For single-agent UI use, fall back to the verified structured agent.
        return StructureStrategy().build_agent(model=model)

    async def _run_refinement(
        self,
        prompt: str,
        tikz: str,
        model: str,
    ) -> tuple[str, str] | None:
        agent = Agent(model, instructions=STRUCTURED_REFINE_INSTRUCTIONS)
        register_render_tool(agent, retries=2)
        user_message = (
            f"Original request: {prompt}\n\n"
            f"Deterministic TikZ draft:\n```tikz\n{tikz}\n```\n\n"
            f"Review the draft, improve presentation while preserving the exact point "
            f"coordinates and visible canvas features, then call render_diagram."
        )
        result = await agent.run(STRUCTURED_REFINE_PROMPT + "\n\n" + user_message)

        tool_args = extract_tool_call_args(result.all_messages(), "render_diagram")
        if tool_args is None or not tool_args.get("tikz"):
            return None

        tool_return = extract_tool_return(result.all_messages(), "render_diagram")
        if tool_return is None:
            return None

        try:
            payload = json.loads(tool_return)
        except (json.JSONDecodeError, TypeError):
            return None

        svg = payload.get("svg")
        if not svg:
            return None

        return tool_args["tikz"], svg

    async def run(self, prompt: str, model: str = DEFAULT_AGENT_MODEL) -> StructuredRunResult:
        base_result = await StructureStrategy().run(prompt, model=model)

        try:
            refined = await self._run_refinement(prompt, base_result.tikz, model)
        except Exception as exc:
            logger.warning("Structured refinement failed; keeping deterministic draft: %s", exc)
            return base_result

        if refined is None:
            return base_result

        refined_tikz, refined_svg = refined
        if not _refinement_constraints_satisfied(base_result.tikz, refined_tikz):
            logger.warning("Refined TikZ violated preservation constraints; keeping deterministic draft")
            return base_result

        return StructuredRunResult(
            diagram_ir=base_result.diagram_ir,
            tikz=refined_tikz,
            svg=refined_svg,
        )
