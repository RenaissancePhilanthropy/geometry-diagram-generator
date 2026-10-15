"""Block stack core (block-stacks ticket 01): a height-map stack definition
compiled through the shared pipeline -- query results, typed errors, the
object listing, owned lattice ids, the position hook, feature gating and the
incremental builder."""
from __future__ import annotations

import pytest

from geometry_diagrams import features
from geometry_diagrams.ir import ir
from geometry_diagrams.ir.derived import REGISTRY, effective_defs
from geometry_diagrams.ir.errors import IRCompileError
from geometry_diagrams.ir.queries import list_objects, query_stack
from geometry_diagrams.ir.refs import def_references
from geometry_diagrams.ir.render_util import centroid_of_obj
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.pydsl.builder import new_builder_context
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline

# The painter prototype's grid (heights 3,2,4 / 2,1,2 / 1,2,1 / 2,1,1 indexed
# [x][depth]) transposed to the spec's heights[z][x] layout: 22 cubes.
PROTOTYPE = [[3, 2, 1, 2], [2, 1, 2, 1], [4, 2, 1, 1]]


def _stack(**overrides) -> ir.BlockStack:
    fields = dict(id="S", origin="O", heights=[[2, 1], [1, 3]])
    fields.update(overrides)
    return ir.BlockStack(**fields)


def _diagram(*stack_defs, render=None, **kw) -> ir.DiagramIR:
    return ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=1, y=2), *stack_defs],
        render=render if render is not None else [ir.Draw(obj="O")],
        **kw,
    )


def _compile(*stack_defs, **kw):
    return compile_defs(_diagram(*stack_defs, **kw))


# --- compile + query ------------------------------------------------------------

def test_height_map_query_reports_count_volume_extents():
    sym = _compile(_stack())
    assert query_stack(sym, "S") == {
        "cube_count": 7, "volume": 7, "length": 2, "width": 2, "height": 3,
        "is_height_map": True,
    }


def test_extents_are_columns_by_rows_by_tallest_column():
    got = query_stack(_compile(_stack(heights=[[1, 0, 2, 0, 0], [0, 4, 0, 0, 0]])), "S")
    assert (got["length"], got["width"], got["height"]) == (5, 2, 4)
    assert got["cube_count"] == 7


def test_painter_prototype_grid_has_22_cubes():
    got = query_stack(_compile(_stack(heights=PROTOTYPE)), "S")
    assert got["cube_count"] == 22 and got["volume"] == 22
    assert (got["length"], got["width"], got["height"]) == (4, 3, 4)


def test_integral_floats_are_accepted_as_integers():
    assert query_stack(_compile(_stack(heights=[[2.0, 1.0]])), "S")["cube_count"] == 3


def test_query_on_a_non_stack_fails_clearly():
    sym = _compile(_stack())
    with pytest.raises(TypeError, match="not a Stack"):
        query_stack(sym, "O")
    with pytest.raises(KeyError):
        query_stack(sym, "nope")


# --- typed errors ---------------------------------------------------------------

@pytest.mark.parametrize("overrides, fragment", [
    (dict(heights=None), "exactly one of"),
    (dict(cubes=[[0, 0, 0]]), "exactly one of"),
    (dict(heights=None, cubes=[[0, 0, 0]]), "not yet supported"),
    (dict(heights=[[1, 2], [1]]), "ragged"),
    (dict(heights=[[1, 2.5]]), "integer"),
    (dict(heights=[[1, -1]]), "non-negative"),
    (dict(heights=[]), "empty"),
    (dict(heights=[[]]), "empty"),
    (dict(heights=[[0, 0], [0, 0]]), "empty"),
    (dict(heights=[[1] * 21]), "20"),
    (dict(heights=[[1]] * 21), "20"),
    (dict(heights=[[21]]), "20"),
    (dict(heights=[[3] * 18] * 8), "400"),
    (dict(view="isometric", depth_angle=30), "oblique"),
    (dict(view="oblique", depth_scale=-1), "depth_scale"),
    (dict(side="up"), None),
])
def test_validation_errors_are_typed(overrides, fragment):
    if overrides.get("side") == "up":
        with pytest.raises(ValueError):
            _stack(**overrides)
        return
    with pytest.raises(IRCompileError, match=fragment) as e:
        _compile(_stack(**overrides))
    assert e.value.def_id == "S"


def test_exactly_400_cubes_and_20_cells_are_allowed():
    assert query_stack(_compile(_stack(heights=[[1] * 20] * 20)), "S")["cube_count"] == 400
    assert query_stack(_compile(_stack(heights=[[20]])), "S")["height"] == 20


def test_authored_id_colliding_with_a_derived_id_is_an_error():
    with pytest.raises(IRCompileError, match="S_top_0_0"):
        _compile(_stack(), ir.PointFixed(id="S_top_0_0", x=0, y=0))
    with pytest.raises(IRCompileError):
        _compile(ir.PointFixed(id="__S_l0_0_0", x=0, y=0), _stack())


def test_stack_origin_must_be_a_point():
    d = ir.DiagramIR(
        define=[ir.PointFixed(id="A", x=0, y=0), ir.PointFixed(id="B", x=1, y=0),
                ir.Segment(id="seg", a="A", b="B"), _stack(origin="seg")],
        render=[],
    )
    with pytest.raises(IRCompileError, match="point"):
        compile_defs(d)


# --- lattice points -------------------------------------------------------------

def test_lattice_points_are_hidden_but_addressable():
    sym = _compile(_stack(view="oblique"))
    lattice = [k for k in sym if k.startswith("__S_l")]
    # Corners of the stack's cubes, not the whole bounding box.
    assert "__S_l0_0_0" in lattice
    assert sym["__S_l0_0_0"].x == 1 and sym["__S_l0_0_0"].y == 2
    assert float(sym["__S_l1_0_0"].x) == pytest.approx(2.0)   # one cell along x
    assert float(sym["__S_l0_1_0"].y) == pytest.approx(3.0)   # one cell up
    listing = list_objects(sym)
    assert not any(k.startswith("__") for k in listing)
    assert listing["S"] == "Stack"


def test_lattice_points_use_the_prism_projection():
    from geometry_diagrams.ir.prism import projection_for

    for view, side in (("oblique", "right"), ("oblique", "left"), ("isometric", "right"), ("isometric", "left")):
        sym = _compile(_stack(view=view, side=side))
        proj = projection_for(view, side)
        dx, dy = proj.offset(2, 3, 1)
        p = sym["__S_l2_3_1"] if "__S_l2_3_1" in sym else None
        # (2, 3, 1) is a corner of the stack (column x=1,z=1 has height 3)
        assert p is not None
        assert float(p.x) == pytest.approx(1 + float(dx)) and float(p.y) == pytest.approx(2 + float(dy))


def test_owned_ids_list_every_lattice_id_and_order_dependents():
    stmt = _stack()
    owned = set(REGISTRY.get(stmt).owned_ids(stmt))
    sym = _compile(stmt)
    assert owned == {k for k in sym if k.startswith("__S_l")}
    # A definition authored BEFORE the stack that uses a lattice point and
    # a derived top polygon still compiles (owner map orders it after).
    d = ir.DiagramIR(
        define=[ir.Segment(id="seg", a="__S_l0_0_0", b="__S_l1_0_0"),
                ir.PointFixed(id="O", x=1, y=2),
                _stack()],
        render=[],
    )
    sym = compile_defs(d)
    assert float(sym["seg"].length) == pytest.approx(1.0)


def test_effective_view_adds_only_column_top_polygons():
    d = _diagram(_stack(heights=[[2, 0], [1, 3]]))
    extra = [s for s in effective_defs(d) if s.id not in {"O", "S"}]
    assert {s.id for s in extra} == {"S_top_0_0", "S_top_0_1", "S_top_1_1"}  # no zero column
    assert all(isinstance(s, ir.Polygon) for s in extra)
    assert [s.id for s in d.define] == ["O", "S"]  # authored IR untouched


def test_column_top_polygon_sits_at_the_column_top_plane():
    sym = _compile(_stack(view="oblique"))
    top = sym["S_top_1_1"]   # height 3 column at x=1, z=1
    d = 0.5 * 2 ** 0.5 / 2  # oblique default depth step, per axis
    ys = sorted({round(float(v.y), 9) for v in top.vertices})
    assert ys == pytest.approx([2 + 3 + d, 2 + 3 + 2 * d])


def test_refs_ignore_heights_cubes_and_colors():
    stmt = _stack(front_color="O", side_color="S", top_color="p")
    assert def_references(stmt) == {"O"}
    assert def_references(_stack(heights=[[1]])) == {"O"}


# --- position hook and pipeline ---------------------------------------------------

def test_centroid_of_stack_is_the_silhouette_bbox_center():
    sym = _compile(_stack(heights=[[1]], view="oblique"))
    cx, cy = centroid_of_obj(sym["S"])
    # unit cube, oblique default: corners span x in [1, 2 + .25*sqrt2], y in [2, 3 + .25*sqrt2]
    d = 2 ** 0.5 / 4
    assert cx == pytest.approx(1 + (1 + d) / 2) and cy == pytest.approx(2 + (1 + d) / 2)


@pytest.mark.parametrize("view, side", [("oblique", "right"), ("isometric", "left")])
def test_concave_stack_center_is_the_bounding_box_center_even_in_a_notch(view, side):
    # L shape: the back-left column (x=0, z=1) is empty, so the bbox center can
    # sit in the notch. The position is pinned to the bbox-center definition.
    sym = _compile(_stack(heights=[[3, 0], [3, 3]], view=view, side=side))
    xs = [float(p.x) for k, p in sym.items() if k.startswith("__S_l")]
    ys = [float(p.y) for k, p in sym.items() if k.startswith("__S_l")]
    cx, cy = centroid_of_obj(sym["S"])
    assert cx == pytest.approx((min(xs) + max(xs)) / 2)
    assert cy == pytest.approx((min(ys) + max(ys)) / 2)


@pytest.mark.asyncio
async def test_label_centered_on_stack_and_drawing_it_do_not_crash():
    diagram = _diagram(
        _stack(),
        render=[ir.Draw(obj="S"), ir.LabelFreeText(text="7 cubes", centroid_of="S")],
    )
    result = await run_ir_pipeline(diagram, SVGRenderer())
    assert "7 cubes" in result.svg


@pytest.mark.parametrize("op", [
    ir.Fill(obj="S"),
])
def test_fill_on_the_stack_is_a_typed_error_naming_the_colors(op):
    with pytest.raises(IRCompileError, match="front_color"):
        compile_defs(_diagram(_stack(), render=[op]))


def test_unequal_canvas_scale_warns():
    from geometry_diagrams.ir.derived import lower_render

    d = _diagram(_stack(), canvas=ir.Canvas(aspect=2))
    warnings: list[str] = []
    lower_render(d, warnings)
    assert any("S" in w and "unequal" in w for w in warnings)


# --- feature gating ---------------------------------------------------------------

def test_block_stack_belongs_to_solids_and_gate_rejects_it_when_off():
    assert REGISTRY.get(_stack()).feature == "solids"
    d = _diagram(_stack())
    with pytest.raises(Exception):
        features.require_features(d, frozenset())
    features.require_features(d, frozenset({"solids"}))
    compile_defs(d)  # stored stack IR compiles regardless


# --- incremental builder ------------------------------------------------------------

def test_builder_incremental_compile_mirrors_registration():
    from geometry_diagrams.ir.ir import PointFixed, Segment

    with new_builder_context() as b:
        b._add(PointFixed(id="O", x=1, y=2))
        b._add(_stack())
        b._add(Segment(id="seg", a="__S_l0_0_0", b="__S_l1_0_0"))
        b._advance_sym()
        assert b._sym["S"].cube_count == 7
        assert "S_top_0_0" in b._sym
        assert b._coord_floats["__S_l1_0_0"][0] == pytest.approx(2.0)
        whole = compile_defs(b.build())
        assert set(whole) == set(b._sym) - {k for k in b._sym if k.startswith("__pydsl")}
