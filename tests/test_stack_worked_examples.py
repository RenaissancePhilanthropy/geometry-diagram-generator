"""Worked block_stack examples (an IR plus its expected query result) run through
the real pipeline; the query result, top-face ids and warnings are compared
with what the code produces."""
from __future__ import annotations

import asyncio

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.queries import query_stack
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline

EXAMPLES = {'heights': ({'define': [{'kind': 'point_fixed', 'id': 'O', 'x': 0, 'y': 0},
                         {'kind': 'block_stack',
                          'id': 'S',
                          'origin': 'O',
                          'heights': [[1, 2], [3, 0]],
                          'top_color': '#e6eefa'}],
              'checks': [{'kind': 'cube_count_equals', 'stack': 'S', 'expected': 6}],
              'render': [{'kind': 'draw', 'obj': 'S'},
                         {'kind': 'label_free_text',
                          'text': '6 cubes',
                          'centroid_of': 'S_top_1_0'}]},
             {'cube_count': 6,
              'volume': 6,
              'length': 2,
              'width': 2,
              'height': 3,
              'is_height_map': True}),
 'arch': ({'define': [{'kind': 'point_fixed', 'id': 'O', 'x': 0, 'y': 0},
                      {'kind': 'block_stack',
                       'id': 'A',
                       'origin': 'O',
                       'view': 'isometric',
                       'cubes': [[0, 0, 0], [0, 1, 0], [2, 0, 0], [2, 1, 0], [1, 1, 0]]}],
           'checks': [{'kind': 'cube_count_equals', 'stack': 'A', 'expected': 5}],
           'render': [{'kind': 'draw', 'obj': 'A'}]},
          {'cube_count': 5,
           'volume': 5,
           'length': 3,
           'width': 1,
           'height': 2,
           'is_height_map': False})}

# name -> (stack id, public column ids, expects the height-map warning)
EXPECTED = {
    "heights": ("S", {"S_top_0_0", "S_top_1_0", "S_top_0_1"}, False),
    "arch": ("A", {"A_top_0_0", "A_top_1_0", "A_top_2_0"}, True),
}


def test_both_examples_are_present():
    assert set(EXAMPLES) == set(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_example_runs_and_matches_its_expected_results(name):
    raw, expected_query = EXAMPLES[name]
    sid, tops, warns = EXPECTED[name]
    diagram = ir.DiagramIR.model_validate(raw)
    result = asyncio.run(run_ir_pipeline(diagram, SVGRenderer()))  # checks included: raises on failure
    sym = compile_defs(diagram)
    assert query_stack(sym, sid) == expected_query
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


def test_arch_top_face_is_at_the_bridge_top_plane():
    raw, _ = EXAMPLES["arch"]
    sym = compile_defs(ir.DiagramIR.model_validate(raw))
    # the bridge column's top face sits on lattice plane y = 2 (the bridge's top)
    assert set(sym["A_top_1_0"].vertices) == {
        sym[f"__A_l{x}_2_{z}"] for x in (1, 2) for z in (0, 1)
    }
    assert set(sym["A_top_2_0"].vertices) == {
        sym[f"__A_l{x}_2_{z}"] for x in (2, 3) for z in (0, 1)
    }


def test_face_count_of_a_full_box_is_culled():
    from geometry_diagrams.ir.stack import painter_faces
    cubes = frozenset((x, y, z) for x in range(3) for y in range(3) for z in range(3))
    assert len(painter_faces(cubes, (1, 1, 1))) == 27
    assert len(painter_faces(cubes, (1, 1, 1), cull=False)) == 81
