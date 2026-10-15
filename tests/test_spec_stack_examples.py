"""The block_stack worked examples in docs/geometry-dsl-spec.md are executed:
each example IR block is parsed, run through the real pipeline, and its
documented query result (the `stack-example-result` block) and warnings are
compared with what the code produces. A stale doc example fails here."""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.queries import query_stack
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline

SPEC = (Path(__file__).resolve().parent.parent / "docs" / "geometry-dsl-spec.md").read_text()
_BLOCK = re.compile(
    r"```json\n(?P<ir>(?:(?!```).)*?)\n```\n\n<!-- stack-example-result: (?P<name>\w+) -->\n```json\n(?P<res>.*?)\n```",
    re.S,
)
EXAMPLES = {m["name"]: (json.loads(m["ir"]), json.loads(m["res"])) for m in _BLOCK.finditer(SPEC)}

# name -> (stack id, public column ids documented in the prose, expects the height-map warning)
EXPECTED = {
    "heights": ("S", {"S_top_0_0", "S_top_1_0", "S_top_0_1"}, False),
    "arch": ("A", {"A_top_0_0", "A_top_1_0", "A_top_2_0"}, True),
}


def test_the_spec_documents_both_examples():
    assert set(EXAMPLES) == set(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_documented_example_runs_and_matches_its_documented_results(name):
    raw, documented = EXAMPLES[name]
    sid, tops, warns = EXPECTED[name]
    diagram = ir.DiagramIR.model_validate(raw)
    result = asyncio.run(run_ir_pipeline(diagram, SVGRenderer()))  # checks included: raises on failure
    sym = compile_defs(diagram)
    assert query_stack(sym, sid) == documented
    assert {k for k in sym if k.startswith(f"{sid}_top_")} == tops
    heightmap_warning = [w for w in result.warnings if "not a height map" in w]
    assert bool(heightmap_warning) is warns
    if warns:
        assert heightmap_warning == [
            f"block_stack {sid!r}: cube set is not a height map: cubes float above empty cells"
        ]
    else:
        assert not result.warnings
    assert "ordered-polygon" in result.svg


def test_documented_arch_top_face_is_at_the_bridge_top_plane():
    raw, _ = EXAMPLES["arch"]
    sym = compile_defs(ir.DiagramIR.model_validate(raw))
    # the bridge column's top face sits on lattice plane y = 2 (the bridge's top)
    assert set(sym["A_top_1_0"].vertices) == {
        sym[f"__A_l{x}_2_{z}"] for x in (1, 2) for z in (0, 1)
    }
    assert set(sym["A_top_2_0"].vertices) == {
        sym[f"__A_l{x}_2_{z}"] for x in (2, 3) for z in (0, 1)
    }


def test_documented_face_count_of_a_full_box_is_culled():
    from geometry_diagrams.ir.stack import painter_faces
    cubes = frozenset((x, y, z) for x in range(3) for y in range(3) for z in range(3))
    assert len(painter_faces(cubes, (1, 1, 1))) == 27
    assert len(painter_faces(cubes, (1, 1, 1), cull=False)) == 81
