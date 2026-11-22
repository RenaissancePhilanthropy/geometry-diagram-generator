"""Every python_full edit-mode generation call sends the same system prompt as
full generation, including the API docs of the enabled feature groups, so a
prism or cube-stack edit is not written blind."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from geometry_diagrams import GeometryConfig, edit_geometry_diagram
from geometry_diagrams.strategies import python_full as pf
from geometry_diagrams.strategies.instructions_python_full import build_python_full_instructions
from tests.test_strategy_robustness import VALID_SCRIPT

MODEL = "anthropic:claude-sonnet-4-6"
GENERATORS = {
    "search_replace": "generate_search_replace",
    "patch": "_generate_patch",
    "hashline": "_generate_hashline_ops",
    "line_number": "_generate_line_number_ops",
}


class _StopAfterPrompt(Exception):
    pass


def _capturing_llm(seen: list):
    async def ainvoke(messages, **kwargs):
        seen.append(messages)
        raise _StopAfterPrompt

    llm = MagicMock()
    llm.ainvoke = ainvoke
    return llm


def _system_text(messages) -> str:
    content = messages[0].content
    return content if isinstance(content, str) else "".join(
        block.get("text", "") for block in content if isinstance(block, dict)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", GENERATORS)
@pytest.mark.parametrize("features", [frozenset(), frozenset({"solids"})])
async def test_edit_system_prompt_matches_generation_prompt(mode, features):
    seen: list = []
    llm = _capturing_llm(seen)
    config = GeometryConfig(
        strategy="python_full", renderer="svg", model=MODEL,
        edit_generation_mode=mode, features=features,
    )
    with patch.object(pf, "get_chat_model", return_value=llm), \
            patch.object(pf, "bind_structured_output_for_model", return_value=llm):
        with pytest.raises(_StopAfterPrompt):
            await edit_geometry_diagram("move c", previous_script=VALID_SCRIPT, config=config)
    assert _system_text(seen[0]) == build_python_full_instructions(features=features)


def test_solids_prompt_differs_from_default():
    # Guards the test above: it only proves something if the prompts differ.
    assert build_python_full_instructions(features=frozenset({"solids"})) != build_python_full_instructions()
