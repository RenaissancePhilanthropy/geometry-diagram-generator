"""Block stack drawing (block-stacks ticket 02): drawing a stack id lowers to
painter-ordered, exterior-culled ``OrderedPolygon`` faces in both renderers.

Seams: an authored DiagramIR through the shared pipeline (parsed SVG/TikZ
structure: polygon count, order, fills, strokes), the lowered render list (for
the painter-order property, which needs the faces' 3D lattice corners), and
``stack.painter_faces`` for the unculled count."""
from __future__ import annotations

import asyncio
import random
import re

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.derived import lower_render
from geometry_diagrams.ir.prism import projection_for
from geometry_diagrams.ir.queries import list_objects
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.stack import DEFAULT_COLORS, painter_faces
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_svg import ir_to_svg
from geometry_diagrams.ir.to_tikz import ir_to_tikz
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline
from tests.availability import renderer_available

# The painter prototype's grid (heights 3,2,4 / 2,1,2 / 1,2,1 / 2,1,1 indexed
# [x][depth]) transposed to the spec's heights[z][x] layout: 22 cubes.
PROTOTYPE = [[3, 2, 1, 2], [2, 1, 2, 1], [4, 2, 1, 1]]
VIEWS = [("oblique", "right"), ("oblique", "left"), ("isometric", "right"), ("isometric", "left")]

SVG_ORDERED = re.compile(r'<polygon\b[^>]*data-role="ordered-polygon"[^>]*>')
LATTICE = re.compile(r"^__S_l(\d+)_(\d+)_(\d+)$")


def _diagram(heights=PROTOTYPE, render=None, styles=None, extra=(), **stack_kw) -> ir.DiagramIR:
    return ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=0, y=0),
                ir.BlockStack(id="S", origin="O", heights=heights, **stack_kw), *extra],
        render=render if render is not None else [ir.Draw(obj="S")],
        styles=styles or {},
    )


def _pipeline(d: ir.DiagramIR):
    return asyncio.run(run_ir_pipeline(d, SVGRenderer()))


def _faces(d: ir.DiagramIR) -> list[ir.OrderedPolygon]:
    return [op for op in lower_render(d, compile_defs(d)).render if isinstance(op, ir.OrderedPolygon)]


def _corners3d(face: ir.OrderedPolygon) -> list[tuple[int, int, int]]:
    out = []
    for pid in face.points:
        m = LATTICE.match(pid)
        assert m, f"face corner {pid!r} is not a lattice id"
        out.append(tuple(int(g) for g in m.groups()))
    return out


def _tikz_ordered(tikz: str) -> list[str]:
    return [ln for ln in tikz.splitlines() if ln.startswith("\\filldraw")]


# --- 2D geometry helpers for the painter-order property ------------------------------

def _clip(subject, clipper):
    """Sutherland-Hodgman: convex ``subject`` clipped by convex CCW ``clipper``."""
    def inside(p, a, b):
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= -1e-12

    def cross_point(p, q, a, b):
        x1, y1, x2, y2 = *p, *q
        x3, y3, x4, y4 = *a, *b
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

    out = list(subject)
    for i in range(len(clipper)):
        a, b = clipper[i], clipper[(i + 1) % len(clipper)]
        inp, out = out, []
        for j in range(len(inp)):
            p, q = inp[j], inp[(j + 1) % len(inp)]
            if inside(q, a, b):
                if not inside(p, a, b):
                    out.append(cross_point(p, q, a, b))
                out.append(q)
            elif inside(p, a, b):
                out.append(cross_point(p, q, a, b))
        if not out:
            return []
    return out


def _area(poly) -> float:
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                     for i in range(len(poly)))


def _ccw(poly):
    return poly if _area(poly) > 0 else poly[::-1]


class _View:
    """Float projection matrix and viewer vector of a view, for the test's own
    independent depth computation."""

    def __init__(self, view, side, depth_angle=None, depth_scale=None):
        proj = projection_for(view, side, depth_angle, depth_scale)
        self.cols = [(float(a[0]), float(a[1])) for a in proj.axes]
        self.k = [float(c) for c in proj.viewer]

    def project(self, p):
        return (sum(p[i] * self.cols[i][0] for i in range(3)), sum(p[i] * self.cols[i][1] for i in range(3)))

    def depth_at(self, corners, q) -> float:
        """Distance toward the viewer of the face's point that projects to q."""
        axis = next(a for a in range(3) if len({c[a] for c in corners}) == 1)
        c = corners[0][axis]
        u, v = (a for a in range(3) if a != axis)
        rx = q[0] - c * self.cols[axis][0]
        ry = q[1] - c * self.cols[axis][1]
        a11, a12, a21, a22 = self.cols[u][0], self.cols[v][0], self.cols[u][1], self.cols[v][1]
        det = a11 * a22 - a12 * a21
        pu, pv = (rx * a22 - a12 * ry) / det, (a11 * ry - a21 * rx) / det
        p = [0.0, 0.0, 0.0]
        p[axis], p[u], p[v] = c, pu, pv
        return sum(p[i] * self.k[i] for i in range(3))


def _overlapping_pairs(view: _View, faces3d):
    """(i, j, centroid of the overlap) for every i < j whose projections
    overlap with positive area."""
    polys = [_ccw([view.project(c) for c in f]) for f in faces3d]
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            inter = _clip(polys[i], polys[j])
            if len(inter) >= 3 and abs(_area(inter)) > 1e-6:
                cx = sum(p[0] for p in inter) / len(inter)
                cy = sum(p[1] for p in inter) / len(inter)
                yield i, j, (cx, cy)


def _assert_painter_order(view: _View, faces3d) -> int:
    pairs = 0
    for i, j, q in _overlapping_pairs(view, faces3d):
        pairs += 1
        di, dj = view.depth_at(faces3d[i], q), view.depth_at(faces3d[j], q)
        assert dj >= di - 1e-9, f"face {j} is painted after face {i} but lies behind it"
    return pairs


# --- painter order ---------------------------------------------------------------------

def _random_heights(rng: random.Random):
    rows, cols = rng.randint(1, 4), rng.randint(1, 4)
    grid = [[rng.randint(0, 4) for _ in range(cols)] for _ in range(rows)]
    if not any(map(any, grid)):
        grid[0][0] = 1
    return grid


@pytest.mark.parametrize("view,side,angle,scale", [
    ("oblique", "right", None, None), ("oblique", "left", None, None),
    ("oblique", "right", 30, 0.8), ("oblique", "left", 60, 1),
    ("isometric", "right", None, None), ("isometric", "left", None, None),
])
def test_property_no_face_is_painted_over_by_one_behind_it(view, side, angle, scale):
    rng = random.Random(f"{view}-{side}-{angle}")
    v = _View(view, side, angle, scale)
    overlaps = 0
    for _ in range(25):
        d = _diagram(_random_heights(rng), view=view, side=side, depth_angle=angle, depth_scale=scale)
        overlaps += _assert_painter_order(v, [_corners3d(f) for f in _faces(d)])
    assert overlaps > 0  # the property was actually exercised


@pytest.mark.parametrize("view,side", VIEWS)
def test_prototype_grid_painter_order_both_views_both_sides(view, side):
    faces = _faces(_diagram(view=view, side=side))
    assert _assert_painter_order(_View(view, side), [_corners3d(f) for f in faces]) > 0


@pytest.mark.parametrize("view,side", VIEWS)
def test_every_face_faces_the_viewer_and_is_exterior(view, side):
    """Each face lies on a visible plane (its outward normal points toward
    the viewer): the cell behind it holds a cube, the cell in front is empty."""
    k = _View(view, side).k
    cubes = {(x, y, z) for z, row in enumerate(PROTOTYPE) for x, h in enumerate(row) for y in range(h)}
    for f in _faces(_diagram(view=view, side=side)):
        corners = _corners3d(f)
        axis = next(a for a in range(3) if len({c[a] for c in corners}) == 1)
        low = [min(c[a] for c in corners) for a in range(3)]
        step = 1 if k[axis] > 0 else -1
        behind, front = list(low), list(low)
        behind[axis] += -1 if step > 0 else 0
        front[axis] += 0 if step > 0 else -1
        assert tuple(behind) in cubes and tuple(front) not in cubes


# --- culling counts --------------------------------------------------------------------

def test_prototype_grid_face_counts_culled_and_unculled():
    proj = projection_for("oblique", "right")
    cubes = frozenset((x, y, z) for z, row in enumerate(PROTOTYPE) for x, h in enumerate(row) for y in range(h))
    viewer = tuple(float(c) for c in proj.viewer)
    assert len(painter_faces(cubes, viewer, cull=False)) == 66
    assert len(painter_faces(cubes, viewer)) == 35
    assert len(_faces(_diagram())) == 35


@pytest.mark.parametrize("view,side", VIEWS)
def test_single_cube_has_three_faces_and_a_full_box_only_its_exterior(view, side):
    assert len(_faces(_diagram([[1]], view=view, side=side))) == 3
    # 2x2x2 box: 4 faces on each of the three visible planes
    assert len(_faces(_diagram([[2, 2], [2, 2]], view=view, side=side))) == 12


def test_culled_faces_are_exactly_those_with_a_neighbour_across_them():
    proj = projection_for("isometric", "left")
    viewer = tuple(float(c) for c in proj.viewer)
    cubes = frozenset({(0, 0, 0), (1, 0, 0), (0, 1, 0)})
    names = sorted(name for name, _ in painter_faces(cubes, viewer))
    # side=left: the left face of (1,0,0) is covered by (0,0,0); the top of
    # (0,0,0) by (0,1,0)
    assert names == sorted(["front"] * 3 + ["side"] * 2 + ["top"] * 2)


# --- pipeline: structure of the SVG and the TikZ ----------------------------------------

@pytest.mark.parametrize("view,side", VIEWS)
def test_pipeline_svg_has_one_ordered_polygon_per_face_in_lowered_order(view, side):
    d = _diagram(view=view, side=side)
    faces = _faces(d)
    result = _pipeline(d)
    polys = SVG_ORDERED.findall(result.svg)
    assert len(polys) == len(faces)
    fills = [re.search(r'fill="([^"]+)"', p).group(1) for p in polys]
    assert fills == [f.fill for f in faces]
    assert set(fills) == set(DEFAULT_COLORS.values())
    assert 'data-role="fill"' not in result.svg  # no hoisted fill layer
    assert not result.warnings


@pytest.mark.parametrize("view,side", VIEWS)
def test_tikz_has_one_filldraw_per_face_in_order(view, side):
    d = _diagram(view=view, side=side)
    faces = _faces(d)
    lines = _tikz_ordered(ir_to_tikz(d, compile_defs(d), warnings=[]))
    assert len(lines) == len(faces)
    assert "\\tkzDrawPolygon" not in "\n".join(lines)


def test_default_face_colors_are_three_distinct_opaque_light_blues():
    assert len(set(DEFAULT_COLORS.values())) == 3
    d = _diagram([[1]])
    by_name = {f.fill for f in _faces(d)}
    assert by_name == set(DEFAULT_COLORS.values())
    assert "fill-opacity" not in ir_to_svg(d, compile_defs(d), [])


def test_face_colors_go_through_the_color_layer_in_both_backends():
    d = _diagram([[1]], front_color="#f80", side_color="salmon", top_color="rgb(1,2,3)")
    sym = compile_defs(d)
    w: list[str] = []
    svg = ir_to_svg(d, sym, w)
    fills = {re.search(r'fill="([^"]+)"', p).group(1) for p in SVG_ORDERED.findall(svg)}
    assert fills == {"#ff8800", "salmon", "#010203"}  # SVG knows CSS names natively
    tikz = ir_to_tikz(d, sym, warnings=w)
    defs = {(int(r), int(g), int(b)) for _, r, g, b in
            re.findall(r"\\definecolor\{(\w+)\}\{RGB\}\{(\d+),(\d+),(\d+)\}", tikz)}
    assert {(255, 136, 0), (250, 128, 114), (1, 2, 3)} <= defs
    assert not w


def test_each_face_painted_with_the_color_of_its_plane():
    d = _diagram([[1]], front_color="#ff0000", side_color="#00ff00", top_color="#0000ff")
    by_axis = {}
    for f in _faces(d):
        corners = _corners3d(f)
        axis = next(a for a in range(3) if len({c[a] for c in corners}) == 1)
        by_axis[axis] = f.fill
    assert by_axis == {0: "#00ff00", 1: "#0000ff", 2: "#ff0000"}


# --- naive Fill + Draw vs ordered ---------------------------------------------------------

def _naive_diagram(view="oblique", side="right"):
    """The same faces as separate Polygons, each filled then drawn: the
    renderer hoists every fill before every stroke."""
    faces = _faces(_diagram(view=view, side=side))
    extra, render = [], []
    for n, f in enumerate(faces):
        extra.append(ir.Polygon(id=f"f{n}", points=list(f.points)))
        render += [ir.Fill(obj=f"f{n}", style=f.fill, opacity=1.0), ir.Draw(obj=f"f{n}")]
    return _diagram(render=render, extra=extra, view=view, side=side), faces


def test_naive_fill_and_draw_paints_far_outlines_over_near_fills_ordered_does_not():
    naive, faces = _naive_diagram()
    v = _View("oblique", "right")
    pairs = list(_overlapping_pairs(v, [_corners3d(f) for f in faces]))
    assert pairs

    svg = ir_to_svg(naive, compile_defs(naive), [])
    fill_at = {m.group(1): m.start() for m in re.finditer(r'data-ir-id="(f\d+)"[^>]*data-role="fill"', svg)}
    stroke_at = {m.group(1): m.start() for m in re.finditer(r'data-ir-id="(f\d+)"(?![^>]*data-role="fill")', svg)}
    # some far face's outline is painted after a nearer overlapping face's fill
    assert any(stroke_at[f"f{i}"] > fill_at[f"f{j}"] for i, j, _ in pairs)

    ordered = _diagram()
    polys = [m.start() for m in SVG_ORDERED.finditer(ir_to_svg(ordered, compile_defs(ordered), []))]
    # ordered: one element per face carrying fill AND stroke, in painter order
    assert polys == sorted(polys) and len(polys) == len(faces)
    for i, j, _ in pairs:
        assert polys[i] < polys[j]


# --- stroke: the author's draw style -------------------------------------------------------

def test_no_style_strokes_black_at_the_ordinary_draw_width_in_both_backends():
    d = _diagram([[1]], extra=[ir.Segment(id="seg", a="__S_l0_0_0", b="__S_l1_0_0")],
                 render=[ir.Draw(obj="S"), ir.Draw(obj="seg")])
    sym = compile_defs(d)
    svg = ir_to_svg(d, sym, [])
    seg_width = re.search(r'<line\b[^>]*data-ir-id="seg"[^>]*stroke-width="([\d.]+)"', svg)
    seg_width = seg_width or re.search(r'data-ir-id="seg"[^>]*stroke-width="([\d.]+)"', svg)
    assert seg_width.group(1) == "1.5"
    for p in SVG_ORDERED.findall(svg):
        assert 'stroke="black"' in p and 'stroke-width="1.5"' in p
    tikz = ir_to_tikz(d, sym, warnings=[])
    for line in _tikz_ordered(tikz):
        # tkz-euclide's own "line style" (the one \tkzDrawSegment uses) sets
        # the ordinary width; no explicit width overrides it
        assert "line style" in line and "line width" not in line


def test_draw_style_color_and_width_carry_dashed_does_not():
    styles = {"edge": {"color": "red", "thick": True, "dashed": True}}
    d = _diagram([[1]], styles=styles, render=[ir.Draw(obj="S", style="edge")])
    sym = compile_defs(d)
    for p in SVG_ORDERED.findall(ir_to_svg(d, sym, [])):
        assert 'stroke="red"' in p and 'stroke-width="2.5"' in p and "dasharray" not in p
    for line in _tikz_ordered(ir_to_tikz(d, sym, warnings=[])):
        assert "draw=red" in line and "thick" in line and "dashed" not in line


def test_draw_style_line_width_and_bare_color():
    d = _diagram([[1]], styles={"w": {"line_width": 0.8}}, render=[ir.Draw(obj="S", style="w")])
    sym = compile_defs(d)
    assert all('stroke-width="0.8"' in p for p in SVG_ORDERED.findall(ir_to_svg(d, sym, [])))
    assert all("line width=0.8pt" in ln for ln in _tikz_ordered(ir_to_tikz(d, sym, warnings=[])))
    d = _diagram([[1]], render=[ir.Draw(obj="S", style="#336699")])
    assert {f.stroke for f in _faces(d)} == {"#336699"}
    d = _diagram([[1]], styles={"t": {"thin": True}}, render=[ir.Draw(obj="S", style="t")])
    assert all('stroke-width="0.75"' in p for p in SVG_ORDERED.findall(ir_to_svg(d, compile_defs(d), [])))


# --- listings, top faces, labels ------------------------------------------------------------

def test_lattice_points_stay_out_of_object_listings_after_drawing():
    result = _pipeline(_diagram())
    assert not any(k.startswith("__") for k in list_objects(result.sym_full))


def test_column_top_faces_still_label_and_fill_after_drawing():
    d = _diagram(render=[ir.Draw(obj="S"), ir.Fill(obj="S_top_0_2", style="yellow"),
                         ir.LabelFreeText(text="4", centroid_of="S_top_0_2")])
    result = _pipeline(d)
    assert ">4<" in result.svg or "4</text>" in result.svg
    assert 'data-ir-id="S_top_0_2"' in result.svg


def test_column_top_face_matches_a_validated_sympy_polygon():
    import sympy.geometry as spg

    for view, side in VIEWS:
        sym = compile_defs(_diagram([[2, 1], [1, 3]], view=view, side=side))
        top = sym["S_top_1_1"]
        assert isinstance(top, spg.Polygon)
        ref = spg.Polygon(*top.vertices)
        assert list(ref.vertices) == list(top.vertices)
        assert top.area == ref.area and top.centroid == ref.centroid


# --- TikZ in the renderer container ---------------------------------------------------------

@pytest.mark.skipif(not renderer_available(), reason="TikZ renderer container not running")
@pytest.mark.parametrize("view,side", VIEWS)
def test_tikz_compiles_in_container_per_view(view, side):
    from geometry_diagrams.util.tikz_renderer import render_tikz

    d = _diagram(view=view, side=side)
    svg = render_tikz(ir_to_tikz(d, compile_defs(d), warnings=[]))
    assert svg.count("<path") >= len(_faces(d))


@pytest.mark.skipif(not renderer_available(), reason="TikZ renderer container not running")
def test_tikz_faces_and_ordinary_draws_render_at_the_same_width():
    from geometry_diagrams.util.tikz_renderer import render_tikz

    d = _diagram([[1]], extra=[ir.PointFixed(id="P", x=3, y=0), ir.PointFixed(id="Q", x=4, y=1),
                               ir.Segment(id="seg", a="P", b="Q")],
                 render=[ir.Draw(obj="seg"), ir.Draw(obj="S")])
    svg = render_tikz(ir_to_tikz(d, compile_defs(d), warnings=[]))
    # the stroke width of every group that paints a path (the page group's
    # default width is not a drawn line)
    widths = re.findall(r"<g stroke-width='([\d.]+)'[^>]*>\s*<path", svg)
    assert len(widths) == 4 and len(set(widths)) == 1, widths


# --- cost at the cap -------------------------------------------------------------------------

@pytest.mark.parametrize("view", ["oblique", "isometric"])
def test_a_stack_at_the_cap_runs_the_pipeline_in_reasonable_time(view):
    """400 occupied columns (the costliest shape: one top face each) used to
    take about 21 s (oblique) through the pipeline, and an angle mark next
    to it about a minute; both now take well under a second. The bound is
    loose so a loaded machine does not flake."""
    import time

    flat = [[1] * 20 for _ in range(20)]
    extra = [ir.PointFixed(id="A", x=-3, y=0), ir.PointFixed(id="B", x=-3, y=3),
             ir.PointFixed(id="C", x=0, y=-3), ir.Segment(id="ab", a="A", b="B"),
             ir.Segment(id="ac", a="A", b="C")]
    d = _diagram(flat, view=view, extra=extra,
                 render=[ir.Draw(obj="S"), ir.Draw(obj="ab"), ir.Draw(obj="ac"),
                         ir.MarkAngles(angles=[ir.AnglePoints(a="B", o="A", b="C")])])
    start = time.perf_counter()
    result = _pipeline(d)
    assert time.perf_counter() - start < 10
    assert len(SVG_ORDERED.findall(result.svg)) == 440  # 400 tops, 20 front, 20 side
