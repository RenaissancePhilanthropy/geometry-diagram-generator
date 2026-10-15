"""Block stack ids, labels and misuse errors (block-stacks ticket 04): column
top-face ids address a column by the ordinary label/fill ops, a free-text label
centred on the stack sits at the silhouette's bounding-box centre, derived ids
cannot be authored, listings expose only public ids, and misuse warns/raises.

Seams: an authored DiagramIR through ``compile_defs`` and ``run_ir_pipeline``
(parsed SVG coordinates), plus ``list_objects`` / ``build_entity_manifest``."""
from __future__ import annotations

import asyncio
import re

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.errors import IRCompileError
from geometry_diagrams.ir.queries import list_objects
from geometry_diagrams.ir.render_util import build_entity_manifest, centroid_of_obj
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline

VIEWS = [("oblique", "right"), ("oblique", "left"), ("isometric", "right"), ("isometric", "left")]
HEIGHTS = [[2, 1], [1, 3]]
# Column (0, 0) holds a floating cube at y=2 over a gap at y=1: its top face is the
# topmost cube's top, at height 3.
FLOATING = [[0, 0, 0], [0, 2, 0], [1, 0, 0], [1, 1, 1]]


def _diagram(heights=None, cubes=None, render=None, **kw) -> ir.DiagramIR:
    if heights is None and cubes is None:
        heights = HEIGHTS
    stack_kw = {k: kw.pop(k) for k in ("view", "side") if k in kw}
    return ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=0, y=0),
                ir.BlockStack(id="S", origin="O", heights=heights, cubes=cubes, **stack_kw)],
        render=render if render is not None else [ir.Draw(obj="S")],
        **kw,
    )


def _pipeline(d):
    return asyncio.run(run_ir_pipeline(d, SVGRenderer()))


def _floats(s: str) -> list[float]:
    return [float(v) for v in re.split(r"[ ,]+", s.strip())]


def _fill_polygon(svg: str, obj_id: str) -> list[tuple[float, float]]:
    m = re.search(rf'<polygon data-ir-id="{obj_id}" data-role="fill" points="([^"]+)"', svg)
    assert m, f"no fill polygon for {obj_id}"
    v = _floats(m.group(1))
    return list(zip(v[0::2], v[1::2]))


def _label_xy(svg: str, text: str) -> tuple[float, float]:
    m = re.search(rf'<text[^>]*data-label-text="{re.escape(text)}"[^>]*? x="([\d.\-]+)" y="([\d.\-]+)"', svg)
    assert m, f"no label {text!r}"
    return float(m.group(1)), float(m.group(2))


def _inside_convex(p, poly) -> bool:
    signs = []
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        signs.append((x2 - x1) * (p[1] - y1) - (y2 - y1) * (p[0] - x1))
    return all(s > 1e-9 for s in signs) or all(s < -1e-9 for s in signs)


def _ordered_points(svg: str) -> list[tuple[float, float]]:
    pts = []
    for m in re.finditer(r'<polygon\b[^>]*data-role="ordered-polygon"[^>]*points="([^"]+)"', svg):
        v = _floats(m.group(1))
        pts += list(zip(v[0::2], v[1::2]))
    return pts


# --- (a) a label placed by column id lands inside that face ------------------------------

@pytest.mark.parametrize("view, side", VIEWS)
@pytest.mark.parametrize("kind, kw, column", [
    ("heights", {"heights": HEIGHTS}, "S_top_1_1"),
    ("heights", {"heights": HEIGHTS}, "S_top_0_0"),
    ("cubes", {"cubes": FLOATING}, "S_top_0_0"),
    ("cubes", {"cubes": FLOATING}, "S_top_1_1"),
])
def test_label_by_column_top_id_lands_inside_that_face(view, side, kind, kw, column):
    d = _diagram(**kw, view=view, side=side, render=[
        ir.Draw(obj="S"),
        ir.Fill(obj=column, style="yellow"),  # only to read the face's drawn polygon back
        ir.LabelFreeText(text="Q", centroid_of=column),
    ])
    svg = _pipeline(d).svg
    face = _fill_polygon(svg, column)
    assert _inside_convex(_label_xy(svg, "Q"), face)


def test_floating_cube_column_label_sits_on_the_topmost_cubes_top():
    d = _diagram(cubes=FLOATING, render=[ir.LabelFreeText(text="Q", centroid_of="S_top_0_0")])
    sym = compile_defs(d)
    top = sym["S_top_0_0"]
    ys = {float(v.y) for v in top.vertices}
    lattice_y = {float(sym[f"__S_l{x}_3_0"].y) for x in (0, 1)}
    assert {round(v, 9) for v in lattice_y} <= {round(v, 9) for v in ys}  # lattice y=3 is its top plane
    cx, cy = centroid_of_obj(top)
    assert min(float(v.y) for v in top.vertices) < cy < max(float(v.y) for v in top.vertices)


# --- (b) free-text label centred on the stack; manifest keeps the variable -----------------

def _to_svg_coords(sym, svg, column="S_top_0_0"):
    """Affine sym->SVG map recovered from one fill polygon (uniform scale, y flipped)."""
    face = _fill_polygon(svg, column)
    verts = [(float(v.x), float(v.y)) for v in sym[column].vertices]
    # match vertices by sorting on the sym x then y; fit scale from the extremes
    sx = (max(f[0] for f in face) - min(f[0] for f in face)) / (
        max(v[0] for v in verts) - min(v[0] for v in verts))
    tx = min(f[0] for f in face) - sx * min(v[0] for v in verts)
    ty = min(f[1] for f in face) + sx * max(v[1] for v in verts)
    return lambda x, y: (sx * x + tx, ty - sx * y)


@pytest.mark.parametrize("view, side", VIEWS)
@pytest.mark.parametrize("kw", [
    {"heights": HEIGHTS}, {"heights": [[3, 0], [3, 3]]}, {"cubes": FLOATING},
])
def test_free_text_label_on_the_stack_is_at_the_silhouette_bbox_centre(view, side, kw):
    # Stack not drawn (so no outline obstacle nudges the label); a fill of one
    # column face supplies the sym->SVG transform.
    d = _diagram(**kw, view=view, side=side, render=[
        ir.Fill(obj="S_top_0_0", style="yellow"), ir.LabelFreeText(text="W", centroid_of="S")])
    sym = compile_defs(d)
    svg = _pipeline(d).svg
    lat = [(float(p.x), float(p.y)) for k, p in sym.items() if k.startswith("__S_l")]
    cx = (min(x for x, _ in lat) + max(x for x, _ in lat)) / 2
    cy = (min(y for _, y in lat) + max(y for _, y in lat)) / 2
    ex, ey = _to_svg_coords(sym, svg)(cx, cy)
    lx, ly = _label_xy(svg, "W")
    assert (lx, ly) == pytest.approx((ex, ey), abs=0.05)


@pytest.mark.parametrize("view, side", VIEWS)
def test_free_text_label_on_a_drawn_stack_stays_within_the_silhouette_bbox(view, side):
    # Drawn: label avoidance may nudge it off a face outline, but only slightly.
    d = _diagram(view=view, side=side,
                 render=[ir.Draw(obj="S"), ir.LabelFreeText(text="W", centroid_of="S")])
    svg = _pipeline(d).svg
    pts = _ordered_points(svg)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    lx, ly = _label_xy(svg, "W")
    assert min(xs) < lx < max(xs) and min(ys) < ly < max(ys)


@pytest.mark.parametrize("kw", [{"heights": HEIGHTS}, {"cubes": FLOATING}])
def test_entity_manifest_keeps_the_stack_variable_at_its_centre(kw):
    d = _diagram(**kw)
    sym = compile_defs(d)
    manifest = build_entity_manifest(d, sym, {"tower": "S", "top": "S_top_0_0"})
    by_name = {e["name"]: e for e in manifest["named"]}
    assert by_name["tower"]["type"] == "block_stack"
    assert by_name["tower"]["approx_position"] == pytest.approx(list(centroid_of_obj(sym["S"])))
    assert by_name["top"]["approx_position"] == pytest.approx(list(centroid_of_obj(sym["S_top_0_0"])))


# --- (c) authored ids colliding with derived ids ---------------------------------------------

@pytest.mark.parametrize("kw", [{"heights": HEIGHTS}, {"cubes": FLOATING}])
@pytest.mark.parametrize("authored", [
    ir.PointFixed(id="S_top_0_0", x=0, y=0),
    ir.PointFixed(id="__S_l0_0_0", x=0, y=0),
    ir.PointFixed(id="__S_l1_1_1", x=0, y=0),
])
def test_authored_definition_named_like_a_derived_id_is_a_typed_error(kw, authored):
    d = _diagram(**kw)
    d.define.append(authored)
    with pytest.raises(IRCompileError) as exc:
        compile_defs(d)
    assert authored.id in str(exc.value)


def test_authored_id_that_is_not_derived_compiles():
    # S_top_1_0 is a height-0 column of this stack: no derived id exists for it
    d = _diagram(heights=[[2, 0]])
    d.define.append(ir.PointFixed(id="S_top_1_0", x=0, y=0))
    assert "S_top_1_0" in compile_defs(d)
    d = _diagram(heights=[[2]])
    d.define.append(ir.PointFixed(id="S_top_5_5", x=0, y=0))
    assert "S_top_5_5" in compile_defs(d)


# --- (d) the object listing exposes only public ids ----------------------------------------------

@pytest.mark.parametrize("kw, public", [
    ({"heights": HEIGHTS}, {"O", "S", "S_top_0_0", "S_top_1_0", "S_top_0_1", "S_top_1_1"}),
    ({"cubes": FLOATING}, {"O", "S", "S_top_0_0", "S_top_1_0", "S_top_1_1"}),
])
def test_object_listing_has_only_the_documented_public_ids(kw, public):
    d = _diagram(**kw)
    assert set(list_objects(compile_defs(d))) == public
    assert set(list_objects(_pipeline(d).sym_full)) == public


# --- (e) unequal axis scales warn, at the pipeline seam ----------------------------------------------

@pytest.mark.parametrize("kw", [{"heights": HEIGHTS}, {"cubes": [[0, 0, 0], [0, 1, 0], [1, 0, 0]]}])
def test_unequal_axis_scale_warning_reaches_the_pipeline_result(kw):
    skewed = _pipeline(_diagram(**kw, canvas=ir.Canvas(aspect=2)))
    assert any("'S'" in w and "unequal axis scales" in w for w in skewed.warnings)
    equal = _pipeline(_diagram(**kw))
    assert not any("unequal" in w for w in equal.warnings)


# --- (f) misuse errors -------------------------------------------------------------------------------

def test_fill_on_the_stack_names_all_three_face_colors_and_the_stack():
    d = _diagram(render=[ir.Fill(obj="S")])
    with pytest.raises(IRCompileError) as exc:
        compile_defs(d)
    msg = str(exc.value)
    assert all(c in msg for c in ("front_color", "side_color", "top_color"))
    assert "S" in msg


def test_fill_of_a_column_top_face_by_id_draws_through_the_fill_layer_behind_the_faces():
    # Observation test: the fill is hoisted behind the ordered polygons, so an
    # opaque top face painted by the stack covers it.
    d = _diagram(render=[ir.Draw(obj="S"), ir.Fill(obj="S_top_0_0", style="yellow")])
    svg = _pipeline(d).svg
    assert svg.index('data-role="fill"') < svg.index('data-role="ordered-polygon"')
