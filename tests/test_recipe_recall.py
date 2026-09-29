"""Live-API tests: does the recipe selector actually recall the catalog
recipes added for previously-uncovered DSL ops (rotation/angle_at_vertex,
point_along, point_external, regular_polygon)?

Catalog coverage alone doesn't help if the selector never picks the recipe
for the prompts it's meant to cover — this is the cheap half of "does the
new recipe help": it calls only the Haiku selector model, not full DSL
generation/rendering, so it stays fast/cheap enough to run routinely.

Requires: RUN_LLM_TESTS=true + ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import pytest

from tests.availability import api_key_available, llm_tests_enabled

pytestmark = pytest.mark.skipif(
    not (llm_tests_enabled() and api_key_available()),
    reason="Live tests disabled (set RUN_LLM_TESTS=true and ANTHROPIC_API_KEY)",
)


@pytest.mark.parametrize(
    "prompt,expected_recipe",
    [
        (
            "Draw a 60-degree angle with vertex B and rays to points A and C. "
            "Label the points A, B, and C.",
            "angle_at_vertex",
        ),
        (
            "Draw a ray from point A through point B. Mark point M on the ray "
            "such that AM = 3. Label points A, B, and M.",
            "point_at_distance_along_ray",
        ),
        (
            "Draw a circle centered at O with radius 2. Place an external point P "
            "at a specific direction and distance from O, then draw the two "
            "tangent lines from P to the circle.",
            "tangent_from_external_at_angle",
        ),
        (
            "Draw a regular hexagon with vertices A, B, C, D, E, and F in order.",
            "regular_polygon",
        ),
    ],
)
@pytest.mark.asyncio
async def test_selector_recalls_recipe_for_prompt(prompt, expected_recipe):
    from geometry_diagrams.strategies.recipe import select_recipes

    result = await select_recipes(prompt)
    assert result.is_geometry_request
    assert expected_recipe in result.selected_recipes, (
        f"Expected {expected_recipe!r} to be selected for prompt {prompt!r}, "
        f"got {result.selected_recipes!r} (unmatched: {result.unmatched_concepts!r})"
    )
