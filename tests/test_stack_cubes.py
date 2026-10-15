"""Block stack cube-set input (block-stacks ticket 03): ``cubes`` as an
alternative to ``heights``, the not-a-height-map warning through the registry
``render_warnings`` hook and the pipeline, typed errors, and the painter-order
property on random cube sets including overhangs."""
from __future__ import annotations

import asyncio
import random
import re

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.errors import IRCompileError
from geometry_diagrams.ir.queries import query_stack
from geometry_diagrams.ir.render_util import centroid_of_obj
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.stack import MAX_CUBES, MAX_CELLS_PER_AXIS
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.strategies.ir_pipeline import format_warnings_for_retry, run_ir_pipeline
from tests.test_stack_draw import (
    SVG_ORDERED, _assert_painter_order, _corners3d, _faces, _View,
)

HEIGHTS = [[2, 1], [1, 3]]
# the same stack as HEIGHTS, as a cube set ([x, y, z])
SAME_CUBES = [[0, 0, 0], [0, 1, 0], [1, 0, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [1, 2, 1]]
# a 3-wide arch: two pillars, one cube spanning the gap (floating over (1, 0, 0))
ARCH = [[0, 0, 0], [0, 1, 0], [2, 0, 0], [2, 1, 0], [0, 2, 0], [1, 2, 0], [2, 2, 0]]


def _diagram(heights=None, cubes=None, render=None, **kw) -> ir.DiagramIR:
    return ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=0, y=0),
                ir.BlockStack(id="S", origin="O", heights=heights, cubes=cubes, **kw)],
        render=render if render is not None else [ir.Draw(obj="S")],
    )


def _pipeline(d):
    return asyncio.run(run_ir_pipeline(d, SVGRenderer()))


def _structure(svg: str) -> list[str]:
    return SVG_ORDERED.findall(svg)


# --- equals a height map ------------------------------------------------------------

def test_cube_set_equal_to_height_map_matches_count_extents_and_structure():
    h, c = _diagram(heights=HEIGHTS), _diagram(cubes=SAME_CUBES)
    assert query_stack(compile_defs(c), "S") == query_stack(compile_defs(h), "S")
    assert query_stack(compile_defs(c), "S")["is_height_map"] is True
    sh, sc = _pipeline(h), _pipeline(c)
    assert _structure(sh.svg) == _structure(sc.svg)
    assert not sc.warnings


def test_cube_set_column_top_faces_and_position_hook():
    sym = compile_defs(_diagram(cubes=SAME_CUBES))
    ref = compile_defs(_diagram(heights=HEIGHTS))
    tops = {k for k in sym if k.startswith("S_top_")}
    assert tops == {k for k in ref if k.startswith("S_top_")} == {
        "S_top_0_0", "S_top_1_0", "S_top_0_1", "S_top_1_1"}
    assert centroid_of_obj(sym["S"]) == centroid_of_obj(ref["S"])
    assert sym["S_top_1_1"].vertices == ref["S_top_1_1"].vertices


def test_extents_follow_the_cubes_bounding_box():
    got = query_stack(compile_defs(_diagram(cubes=[[0, 0, 0], [3, 0, 0], [3, 1, 2]])), "S")
    assert (got["length"], got["height"], got["width"], got["cube_count"]) == (4, 2, 3, 3)


# --- overhang ---------------------------------------------------------------------------

def test_arch_renders_is_not_a_height_map_and_warns_through_the_pipeline():
    d = _diagram(cubes=ARCH)
    q = query_stack(compile_defs(d), "S")
    assert q["is_height_map"] is False and q["cube_count"] == 7
    result = _pipeline(d)
    assert _structure(result.svg)
    assert any("'S'" in w and "not a height map" in w and "float above empty cells" in w
               for w in result.warnings)
    assert "not a height map" in format_warnings_for_retry(result.warnings)


def test_floating_cube_top_face_is_the_topmost_cubes_top():
    sym = compile_defs(_diagram(cubes=[[0, 0, 0], [0, 2, 0]]))
    ys = {sym["S_top_0_0"].vertices[i].y for i in range(4)}
    ref = compile_defs(_diagram(heights=[[3]]))
    assert ys == {ref["S_top_0_0"].vertices[i].y for i in range(4)}


@pytest.mark.parametrize("kw", [
    dict(view="isometric"), dict(view="oblique", side="left"), dict(view="isometric", side="left"),
])
def test_overhang_renders_in_every_view(kw):
    assert _structure(_pipeline(_diagram(cubes=ARCH, **kw)).svg)


def test_height_map_never_warns():
    assert not _pipeline(_diagram(heights=HEIGHTS)).warnings
    # a gap in the base row is still a height map
    assert not _pipeline(_diagram(cubes=[[0, 0, 0], [2, 0, 0]])).warnings


# --- typed errors -----------------------------------------------------------------------

@pytest.mark.parametrize("cubes,match", [
    ([[0, 0, 0], [0, 0, 0]], "duplicate"),
    ([[0, 0, 0], [-1, 0, 0]], "non-negative"),
    ([[0, 0, 0.5]], "integer"),
    ([], "empty"),
    ([[0, 0]], "exactly 3|three|\\[x, y, z\\]"),
    ([[0, 0, 0, 0]], "exactly 3|three|\\[x, y, z\\]"),
    ([[0, 0, MAX_CELLS_PER_AXIS]], "at most 20 cells"),
    ([[0, MAX_CELLS_PER_AXIS, 0]], "at most 20 cells"),
    ([[x, 0, z] for x in range(20) for z in range(20)] + [[0, 1, 0]], "at most 400 cubes"),
])
def test_invalid_cube_sets_are_typed_errors(cubes, match):
    with pytest.raises(IRCompileError, match=match) as e:
        compile_defs(_diagram(cubes=cubes))
    assert e.value.def_id == "S"


def test_both_or_neither_input_is_still_a_typed_error():
    for kw in (dict(heights=HEIGHTS, cubes=SAME_CUBES), {}):
        with pytest.raises(IRCompileError, match="exactly one"):
            compile_defs(_diagram(**kw))


def test_float_integer_valued_cubes_are_accepted():
    assert query_stack(compile_defs(_diagram(cubes=[[0.0, 0, 0]])), "S")["cube_count"] == 1


# --- painter order on random cube sets, overhangs included --------------------------------

def _random_cube_set(rng: random.Random) -> list[list[int]]:
    n = rng.randint(1, 4)
    cells = {(rng.randint(0, n), rng.randint(0, n), rng.randint(0, n)) for _ in range(rng.randint(1, 18))}
    return [list(c) for c in sorted(cells)]


@pytest.mark.parametrize("view,side,angle,scale", [
    ("oblique", "right", None, None), ("oblique", "left", None, None),
    ("oblique", "right", 30, 0.8), ("oblique", "left", 60, 1),
    ("isometric", "right", None, None), ("isometric", "left", None, None),
])
def test_property_painter_order_on_random_cube_sets(view, side, angle, scale):
    rng = random.Random(f"cubes-{view}-{side}-{angle}")
    v = _View(view, side, angle, scale)
    overlaps = overhangs = 0
    for _ in range(40):
        cubes = _random_cube_set(rng)
        d = _diagram(cubes=cubes, view=view, side=side, depth_angle=angle, depth_scale=scale)
        overhangs += not query_stack(compile_defs(d), "S")["is_height_map"]
        overlaps += _assert_painter_order(v, [_corners3d(f) for f in _faces(d)])
    assert overlaps > 0 and overhangs > 0
