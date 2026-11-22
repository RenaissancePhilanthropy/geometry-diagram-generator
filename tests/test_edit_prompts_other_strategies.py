"""A structured (previous_ir) or recipe (previous_dsl) edit sends the same feature-group
documentation as a fresh render, so a prism edit is not written blind (the python_full edit
modes had this gap; these two share the generation node and never did)."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.strategies import instructions as ins
from geometry_diagrams.strategies.recipe import RecipeStrategy
from geometry_diagrams.strategies.structured import StructureStrategy
from tests.test_structured_prism import _example, _mock_llm, _raw

SOLIDS = frozenset({"solids"})


def _system_text(structured) -> str:
    system = structured.ainvoke.call_args_list[0].args[0][0]
    return system.content if isinstance(system.content, str) else "".join(
        block.get("text", "") for block in system.content)


@pytest.mark.parametrize("features", [frozenset(), SOLIDS])
def test_structured_edit_sends_the_same_system_prompt_as_a_render(features):
    previous = _example().model_dump()
    llm, structured = _mock_llm([_raw(_example())])
    with patch("geometry_diagrams.strategies.structured.get_chat_model", return_value=llm):
        try:
            asyncio.run(StructureStrategy(features=features).run(
                "make it taller", previous_ir=previous, renderer=SVGRenderer()))
        except RuntimeError:
            assert not features  # a disabled prism is rejected after generation; the prompt was still sent
    assert _system_text(structured) == ins.build_structured_instructions(features)
    assert ("Rectangular prisms" in _system_text(structured)) is bool(features)


@pytest.mark.asyncio
@pytest.mark.parametrize("features", [frozenset(), SOLIDS])
async def test_recipe_edit_builds_its_docs_for_the_enabled_features(features):
    from tests.test_recipe_prism import _dsl
    from tests.test_recipe_retry import _common_patches, _make_mock_llm, _wrap_dsl

    mock_llm = _make_mock_llm([_wrap_dsl(_dsl())])
    p = _common_patches(mock_llm)
    seen = []

    def spy(feats):
        seen.append(frozenset(feats))
        return "DOCS"

    with p[0], p[1], p[2], p[3], p[4], p[5], patch(
            "geometry_diagrams.strategies.recipe.dsl_docs_for", new=spy):
        try:
            await RecipeStrategy(features=features).run("make it taller", previous_dsl=_dsl().model_dump())
        except RuntimeError:
            assert not features  # a disabled prism op is rejected after generation; the docs were built
    assert seen and set(seen) == {features}
