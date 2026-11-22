"""The "label the givens, not the answer" rule is in every strategy's base system
prompt (2D figures included), with or without the solids group."""
import pytest

from geometry_diagrams.strategies.instructions import RECIPE_GENERATION_SYSTEM, build_structured_instructions
from geometry_diagrams.strategies.instructions_common import ANSWER_LABEL_RULE
from geometry_diagrams.strategies.instructions_python_full import build_python_full_instructions

SOLIDS = frozenset({"solids"})


@pytest.mark.parametrize("features", [frozenset(), SOLIDS])
def test_rule_is_in_the_python_full_and_structured_prompts(features):
    assert ANSWER_LABEL_RULE in build_python_full_instructions(features=features)
    assert ANSWER_LABEL_RULE in build_structured_instructions(features)


def test_rule_is_in_the_recipe_generation_prompt():
    assert ANSWER_LABEL_RULE in RECIPE_GENERATION_SYSTEM


def test_rule_names_what_is_allowed_and_what_is_not():
    # The unknown may still be named (x, ?); only the solved value is withheld.
    assert "a variable such as x" in ANSWER_LABEL_RULE and "Never write the solved value" in ANSWER_LABEL_RULE
