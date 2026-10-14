"""Rectangular prism core (solids ticket 07): an authored prism definition
compiled through the shared pipeline -- query results, symbol-table listing,
dependents tracking, entity manifest, typed errors, the view rules and the
incremental builder reading a corner mid-script."""
from __future__ import annotations

import itertools
import json
import math

import pytest
import sympy as sp

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.errors import IRCompileError
from geometry_diagrams.ir.prism import projection_for
from geometry_diagrams.ir.refs import compute_dependents, downstream_of
from geometry_diagrams.ir.render_util import build_entity_manifest
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline
from geometry_diagrams.strategies.structured import dispatch_query

BITS = list(itertools.product((0, 1), repeat=3))  # (length, height, width)
DEFAULT_IDS = [f"P_v{a}{b}{c}" for a, b, c in BITS]
R3 = math.sqrt(3) / 2
# Measured oblique default (solids ticket 08; was the provisional 45 deg x 0.45):
# depth recedes at 45 deg at half scale (cabinet projection), measured on the
# reference art at 44.7-45.1 deg and a 0.50 depth scale.
OBLIQUE_DEFAULT = (math.sqrt(2) / 4, math.sqrt(2) / 4)


def _diagram(*prism_defs, extra=(), params=None, render=None) -> ir.DiagramIR:
    return ir.DiagramIR(
        params=ir.Params(assign=params) if params else None,
        define=[ir.PointFixed(id="O", x=1, y=2), *extra, *prism_defs],
        render=render if render is not None else [ir.Draw(obj="O")],
    )


def _prism(**overrides) -> ir.RectangularPrism:
    fields = dict(id="P", origin="O", length=4, width=3, height=2)
    fields.update(overrides)
    return ir.RectangularPrism(**fields)


def _q(sym, query_type, args):
    return json.loads(dispatch_query(sym, query_type, args))


def _xy(sym, pid):
    return _q(sym, "coordinate", {"point": pid})


def _expected_corner(origin, dims, axes, bits):
    (ox, oy), (L, H, W) = origin, dims
    ex, ey, ez = axes
    a, b, c = bits
    return (
        ox + a * L * ex[0] + b * H * ey[0] + c * W * ez[0],
        oy + a * L * ex[1] + b * H * ey[1] + c * W * ez[1],
    )


# --- compile + query through the shared pipeline ----------------------------

@pytest.mark.asyncio
async def test_point_and_prism_compile_through_pipeline_and_prism_query_reports_dimensions():
    result = await run_ir_pipeline(_diagram(_prism()), SVGRenderer())
    got = _q(result.sym_full, "prism", {"prism": "P"})
    assert got["length"] == 4 and got["width"] == 3 and got["height"] == 2
    assert got["volume"] == 24
    assert got["base_area"] == 12
    assert got["surface_area"] == 2 * (4 * 3 + 4 * 2 + 3 * 2)
    assert got["corner_ids"] == {f"{a}{b}{c}": f"P_v{a}{b}{c}" for a, b, c in BITS}


@pytest.mark.asyncio
async def test_prism_corners_are_addressable_points_at_the_oblique_default_map():
    result = await run_ir_pipeline(_diagram(_prism()), SVGRenderer())
    axes = ((1, 0), (0, 1), OBLIQUE_DEFAULT)
    for bits, pid in zip(BITS, DEFAULT_IDS):
        x, y = _expected_corner((1, 2), (4, 2, 3), axes, bits)
        got = _xy(result.sym_full, pid)
        assert got["x"] == pytest.approx(x) and got["y"] == pytest.approx(y), pid
    # A later definition may reference a corner.
    sym = compile_defs(_diagram(_prism(), ir.Segment(id="s", a="P_v000", b="P_v100")))
    assert _q(sym, "length", {"segment": "s"})["length"] == pytest.approx(4)


def test_vertex_names_are_used_in_product_order():
    names = list("ABCDEFGH")
    sym = compile_defs(_diagram(_prism(vertex_names=names)))
    got = _q(sym, "prism", {"id": "P"})
    assert list(got["corner_ids"].values()) == names
    assert _xy(sym, "A") == {"x": 1.0, "y": 2.0}           # (0,0,0) = origin
    assert _xy(sym, "E")["x"] == pytest.approx(5.0)         # (1,0,0): + length
    assert "P_v000" not in sym


def test_corners_stay_exact_symbolic_values():
    sym = compile_defs(_diagram(_prism(view="isometric")))
    corner = sym["P_v111"]
    assert not corner.x.atoms(sp.Float) and not corner.y.atoms(sp.Float)
    assert sp.simplify(corner.x - (1 + 4 * sp.sqrt(3) / 2 + 3 * sp.sqrt(3) / 2)) == 0


def test_list_objects_shows_the_prism_and_its_corners():
    sym = compile_defs(_diagram(_prism()))
    listing = _q(sym, "list_objects", {})
    assert listing["P"] == "Prism"
    for pid in DEFAULT_IDS:
        assert listing[pid] == "Point"


def test_prism_query_on_a_non_prism_is_an_error():
    sym = compile_defs(_diagram(_prism()))
    assert "error" in _q(sym, "prism", {"prism": "O"})


# --- anchoring ---------------------------------------------------------------

def test_derived_origin_and_expression_dimensions_and_dependents():
    extra = [
        ir.PointFixed(id="A", x=0, y=0),
        ir.PointFixed(id="B", x=6, y=0),
        ir.PointMidpoint(id="M", p="A", q="B"),
    ]
    prism = ir.RectangularPrism(
        id="P", origin="M", length="2*k", width="length(A, B) / 2", height="k + 1",
    )
    diagram = ir.DiagramIR(
        params=ir.Params(assign={"k": 2}), define=[*extra, prism, ir.Segment(id="s", a="P_v000", b="P_v111")],
        render=[],
    )
    sym = compile_defs(diagram)
    got = _q(sym, "prism", {"prism": "P"})
    assert (got["length"], got["width"], got["height"]) == (4, 3, 3)
    assert _xy(sym, "P_v000") == {"x": 3.0, "y": 0.0}
    downstream = downstream_of(compute_dependents(diagram), {"A"})
    assert {"M", "P", "P_v000", "P_v111", "s"} <= downstream
    # Dimension expressions are dependency edges too.
    assert "P" in compute_dependents(diagram)["B"]


def test_definition_order_does_not_matter():
    prism = _prism()
    diagram = ir.DiagramIR(
        define=[ir.Segment(id="s", a="P_v000", b="P_v010"), prism, ir.PointFixed(id="O", x=1, y=2)],
        render=[],
    )
    sym = compile_defs(diagram)
    assert _q(sym, "length", {"segment": "s"})["length"] == pytest.approx(2)


# --- view rules --------------------------------------------------------------

@pytest.mark.parametrize("view, side, visible, hidden", [
    ("oblique", "right", {("length", "max"), ("height", "max"), ("width", "min")}, (0, 0, 1)),
    ("oblique", "left", {("length", "min"), ("height", "max"), ("width", "min")}, (1, 0, 1)),
    ("isometric", "right", {("length", "max"), ("height", "max"), ("width", "min")}, (0, 0, 1)),
    ("isometric", "left", {("length", "min"), ("height", "max"), ("width", "min")}, (1, 0, 1)),
])
def test_visible_planes_and_hidden_corner_derive_from_the_map(view, side, visible, hidden):
    proj = projection_for(view=view, side=side)
    assert proj.visible_planes == frozenset(visible)
    assert proj.hidden_corner == hidden


def test_oblique_default_depth_vector_is_exact_cabinet_half_scale_at_45_degrees():
    # Solids ticket 08 measured the reference art: 45 deg, depth scale 1/2.
    proj = projection_for(view="oblique", side="right")
    assert proj.width == (sp.sqrt(2) / 4, sp.sqrt(2) / 4)
    sym = compile_defs(_diagram(_prism()))
    corner = sym["P_v001"]  # origin + width (3) * depth vector
    assert sp.simplify(corner.x - (1 + 3 * sp.sqrt(2) / 4)) == 0
    assert sp.simplify(corner.y - (2 + 3 * sp.sqrt(2) / 4)) == 0


def test_view_rules_hold_for_overridden_oblique_constants():
    proj = projection_for(view="oblique", side="right", depth_angle=30, depth_scale=1)
    assert proj.hidden_corner == (0, 0, 1)


@pytest.mark.parametrize("view, side, axes", [
    ("oblique", "right", ((1, 0), (0, 1), OBLIQUE_DEFAULT)),
    ("oblique", "left", ((1, 0), (0, 1), (-OBLIQUE_DEFAULT[0], OBLIQUE_DEFAULT[1]))),
    ("isometric", "right", ((R3, -0.5), (0, 1), (R3, 0.5))),
    ("isometric", "left", ((R3, 0.5), (0, 1), (-R3, 0.5))),
])
def test_corners_placed_per_documented_linear_map(view, side, axes):
    sym = compile_defs(_diagram(_prism(view=view, side=side)))
    for bits, pid in zip(BITS, DEFAULT_IDS):
        x, y = _expected_corner((1, 2), (4, 2, 3), axes, bits)
        got = _xy(sym, pid)
        assert got["x"] == pytest.approx(x) and got["y"] == pytest.approx(y), (view, side, pid)


def test_oblique_overrides_change_the_depth_vector():
    sym = compile_defs(_diagram(_prism(depth_angle=30, depth_scale=0.5)))
    got = _xy(sym, "P_v001")  # origin + width * depth vector
    assert got["x"] == pytest.approx(1 + 3 * 0.5 * math.cos(math.radians(30)))
    assert got["y"] == pytest.approx(2 + 3 * 0.5 * math.sin(math.radians(30)))


# --- typed errors --------------------------------------------------------------

def _compile_error(diagram) -> IRCompileError:
    with pytest.raises(IRCompileError) as exc:
        compile_defs(diagram)
    return exc.value


def test_corner_name_equal_to_the_prism_id_is_an_error():
    err = _compile_error(_diagram(_prism(vertex_names=["P", *"BCDEFGH"])))
    assert err.def_id == "P" and "'P'" in str(err)


def test_corner_name_shadowing_an_authored_point_is_an_error():
    # The authored point would otherwise silently win (or be overwritten).
    err = _compile_error(_diagram(_prism(vertex_names=list("ABCDEFGH")),
                                  extra=[ir.PointFixed(id="C", x=9, y=9)]))
    assert err.def_id == "P" and "'C'" in str(err)


def test_authored_point_named_like_a_default_corner_is_an_error():
    err = _compile_error(_diagram(_prism(), extra=[ir.PointFixed(id="P_v001", x=9, y=9)]))
    assert err.def_id == "P" and "P_v001" in str(err)


def test_two_prisms_sharing_a_corner_name_is_an_error():
    err = _compile_error(_diagram(
        _prism(vertex_names=list("ABCDEFGH")),
        _prism(id="Q", vertex_names=list("HIJKLMNO")),
    ))
    assert err.def_id == "Q" and "'H'" in str(err) and "'P'" in str(err)


def test_duplicate_names_within_one_prism_is_an_error():
    err = _compile_error(_diagram(_prism(vertex_names=list("ABCDEFGA"))))
    assert err.def_id == "P" and "'A'" in str(err)


@pytest.mark.parametrize("names", [list("ABCDEFG"), list("ABCDEFGHI"), []])
def test_wrong_length_corner_name_list_is_an_error(names):
    err = _compile_error(_diagram(_prism(vertex_names=names)))
    assert err.def_id == "P" and "eight" in str(err)


@pytest.mark.parametrize("field, value", [("length", 0), ("width", -2), ("height", "k - 5")])
def test_non_positive_dimension_is_an_error(field, value):
    err = _compile_error(_diagram(_prism(**{field: value}), params={"k": 2}))
    assert err.def_id == "P" and field in str(err)


@pytest.mark.parametrize("dims", [dict(length=2.5), dict(height="2*k")])
def test_non_integer_or_expression_dimensions_with_unit_cubes_is_an_error(dims):
    err = _compile_error(_diagram(_prism(unit_cubes=True, **dims), params={"k": 2}))
    assert err.def_id == "P" and "unit_cubes" in str(err)


def test_integer_valued_dimensions_with_unit_cubes_compile():
    sym = compile_defs(_diagram(_prism(unit_cubes=True, length=4.0)))
    assert _q(sym, "prism", {"prism": "P"})["volume"] == 24


@pytest.mark.parametrize("override", [dict(depth_angle=30), dict(depth_scale=0.5)])
def test_oblique_overrides_with_isometric_view_is_an_error(override):
    err = _compile_error(_diagram(_prism(view="isometric", **override)))
    assert err.def_id == "P" and "isometric" in str(err)


# --- position, manifest, incremental builder ----------------------------------

def test_entity_manifest_positions_the_prism_at_its_projected_center():
    diagram = _diagram(_prism())
    sym = compile_defs(diagram)
    manifest = build_entity_manifest(diagram, sym, {"box": "P"})
    (entry,) = manifest["named"]
    assert entry["name"] == "box" and entry["type"] == "rectangular_prism"
    corners = [_xy(sym, pid) for pid in DEFAULT_IDS]
    cx = sum(c["x"] for c in corners) / 8
    cy = sum(c["y"] for c in corners) / 8
    assert entry["approx_position"] == pytest.approx([cx, cy])


def test_incremental_builder_reads_a_corner_mid_script():
    with new_builder_context():
        b = get_builder()
        b._add(ir.PointFixed(id="O", x=1, y=2))
        b._add(_prism(view="isometric"))
        mid_script = b._resolve_point("P_v111")
        diagram = b.build()
    p = compile_defs(diagram)["P_v111"]
    assert mid_script == pytest.approx((float(p.x), float(p.y)))


def test_incremental_builder_rejects_a_corner_name_already_defined():
    with new_builder_context():
        b = get_builder()
        b._add(ir.PointFixed(id="O", x=1, y=2))
        b._add(ir.PointFixed(id="C", x=9, y=9))
        b._add(_prism(vertex_names=list("ABCDEFGH")))
        with pytest.raises(IRCompileError) as exc:
            b._resolve_point("A")
    assert exc.value.def_id == "P" and "'C'" in str(exc.value)
