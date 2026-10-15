"""The cube-triple axis convention is stated identically on all three gated
guidance surfaces (block-stacks ticket 11): y is HEIGHT, z is DEPTH, the arch
is annotated cube by cube, and swapping y and z is called out."""
from __future__ import annotations

import pytest

from geometry_diagrams.recipe.catalog import dsl_docs_for
from geometry_diagrams.strategies import instructions_python_full as ipf
from geometry_diagrams.strategies import instructions_structured as ins

SOLIDS = frozenset({"solids"})

AXIS_PHRASES = (
    "x along the front (left to right)",
    "y = HEIGHT (up; the layer number, 0 is the bottom layer)",
    "z = DEPTH (front to back, 0 = front row)",
    "[0,0,0] and [0,1,0]: left pillar, two cubes high",
    "[2,0,0] and [2,1,0]: right pillar",
    "[1,1,0]: the bridge, at height y=1 above the empty cell [1,0,0]",
    "swapping y and z draws the stack lying flat instead of standing up",
)

SURFACES = {
    "recipe": lambda: dsl_docs_for(SOLIDS),
    "python_full": lambda: ipf.build_python_full_instructions(features=SOLIDS),
    "structured": lambda: ins.build_structured_instructions(SOLIDS),
}


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_axis_convention_and_arch_annotation_on_every_gated_surface(surface):
    text = " ".join(SURFACES[surface]().split())
    for phrase in AXIS_PHRASES:
        assert phrase in text, (surface, phrase)


def test_axis_text_absent_when_solids_off():
    off = [dsl_docs_for(frozenset()), ipf.build_python_full_instructions(),
           ins.build_structured_instructions()]
    for text in off:
        assert "HEIGHT" not in text and "lying flat" not in text
