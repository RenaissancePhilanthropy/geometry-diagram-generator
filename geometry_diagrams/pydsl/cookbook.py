# geometry_diagrams/pydsl/cookbook.py
"""Experimental diagram cookbook: opt-in helper functions layered on top of
the core pydsl API (geometry_diagrams/pydsl/api.py).

Anything defined here is only ever handed to a sandboxed pydsl script when
the caller has opted in: `PythonFullStrategy.run(experimental_diagram_cookbook=True)`
(threaded through to `geometry_diagrams.pydsl.sandbox.run_script`'s
`enable_cookbook` flag). With the flag unset (the default everywhere,
including `RecipeStrategy`/`facade.py`, which never runs pydsl scripts at
all and has no way to enable this), none of these names ever reach the
sandbox's tool namespace — see `_sandbox_child.py`'s `_build_tool_names`.

Every helper here is built purely out of the stable, already-exported pydsl
API (`point`, `segment`, `circle`, `rectangle`, `draw`, `fill`, ...) plus
plain Python arithmetic/loops — no new IR node types, no sandbox changes.

Ticket 09 (diagram-kinds-poc) adds the three grid/discrete-object helpers
below. Tickets 10-12 each append further helpers here, keeping each group
under its own section comment rather than restructuring what's already
here — ticket 12's oblique_point (3D-to-2D projection) is the last one on
this branch, so this file is feature-complete after it.
"""
from __future__ import annotations

import math

from geometry_diagrams.pydsl.api import circle, draw, fill, label_text, point, rectangle, segment
from geometry_diagrams.pydsl.handles import Point, Polygon


# --- unit_grid: background reference grid -----------------------------------

def unit_grid(
    x0: float,
    y0: float,
    cols: int,
    rows: int,
    cell_size: float = 1.0,
    color: str = "gray",
) -> None:
    """Draw a `cols` x `rows` reference grid of unit-square lines, anchored
    with its bottom-left corner at (x0, y0) and each cell `cell_size` wide.
    Purely a visual backdrop (e.g. for `grid_area`'s square counting grid,
    `place_value_blocks`' ruled flats, or a grid behind a composite
    polygon) — it draws (cols + 1) vertical and (rows + 1) horizontal lines
    and returns nothing; it does not create points/segments you can refer
    to afterward. Call `canvas(...)` yourself to fit the grid's extent."""
    if cols < 1 or rows < 1:
        raise ValueError(f"unit_grid(): cols and rows must be >= 1, got cols={cols!r}, rows={rows!r}")
    if cell_size <= 0:
        raise ValueError(f"unit_grid(): cell_size must be positive, got {cell_size!r}")

    width = cols * cell_size
    height = rows * cell_size
    for i in range(cols + 1):
        x = x0 + i * cell_size
        draw(segment(point(x, y0), point(x, y0 + height)), color=color, thin=True)
    for j in range(rows + 1):
        y = y0 + j * cell_size
        draw(segment(point(x0, y), point(x0 + width, y)), color=color, thin=True)


# --- array_of: N discrete unit shapes in a grid layout -----------------------

def array_of(
    n: int,
    shape: str = "circle",
    cols: "int | None" = None,
    spacing: float = 1.0,
    origin: "tuple[float, float]" = (0.0, 0.0),
    size: float = 0.3,
    color: "str | None" = None,
):
    """Place `n` identical discrete unit shapes ("circle" or "square") in a
    row-major grid — for equal-groups counting (`object_array`) or the
    stacked-dot pattern in `dot_plot`. Shapes fill rows left-to-right,
    top-to-bottom starting at `origin` (the center of the first shape);
    `cols` defaults to a roughly-square layout (ceil(sqrt(n))) if omitted.
    `spacing` is the center-to-center distance between shapes; `size` is
    each shape's radius (circle) or half-side-length (square). Every shape
    is drawn (and filled with `color` if given) and returned as a list of
    handles, in placement order, so the caller can label/reference
    individual ones afterward."""
    if n < 1:
        raise ValueError(f"array_of(): n must be >= 1, got {n!r}")
    if shape not in ("circle", "square"):
        raise ValueError(f"array_of(): shape must be 'circle' or 'square', got {shape!r}")
    if spacing <= 0:
        raise ValueError(f"array_of(): spacing must be positive, got {spacing!r}")
    if size <= 0:
        raise ValueError(f"array_of(): size must be positive, got {size!r}")

    effective_cols = cols if cols is not None else math.ceil(math.sqrt(n))
    if effective_cols < 1:
        raise ValueError(f"array_of(): cols must be >= 1, got {cols!r}")

    ox, oy = origin
    shapes = []
    for i in range(n):
        row, col = divmod(i, effective_cols)
        cx = ox + col * spacing
        cy = oy - row * spacing
        if shape == "circle":
            obj = circle(center=point(cx, cy), radius=size)
        else:
            obj = rectangle(corner=point(cx - size, cy - size), width=2 * size, height=2 * size)
        draw(obj)
        if color is not None:
            fill(obj, color=color)
        shapes.append(obj)
    return shapes


# --- tick_marks: evenly spaced perpendicular ticks along a segment ----------

def tick_marks(p1: Point, p2: Point, n: int, length: float = 0.2):
    """Draw `n` evenly spaced tick marks — short segments perpendicular to
    the line from `p1` to `p2` — for `number_line`'s unit ticks or
    `ruler_measure`'s graduation marks. Ticks are placed at `n` equally
    spaced parametric positions from `p1` (t=0) to `p2` (t=1) inclusive of
    both endpoints (so `n=2` marks just the two ends; `n=11` marks a
    0..10 number line every unit). `length` is each tick's total length,
    centered on the p1-p2 line. Returns the list of drawn tick segments, in
    order from `p1` to `p2`."""
    if n < 2:
        raise ValueError(f"tick_marks(): n must be >= 2, got {n!r}")
    if length <= 0:
        raise ValueError(f"tick_marks(): length must be positive, got {length!r}")

    dx = p2.x - p1.x
    dy = p2.y - p1.y
    seg_len = math.hypot(dx, dy)
    if seg_len < 1e-9:
        raise ValueError("tick_marks(): p1 and p2 must be distinct points")

    # Unit vector along p1->p2, rotated 90 degrees CCW to get the
    # perpendicular direction each tick extends along.
    ux, uy = dx / seg_len, dy / seg_len
    perp_x, perp_y = -uy, ux
    half = length / 2.0

    ticks = []
    for i in range(n):
        t = i / (n - 1)
        cx = p1.x + t * dx
        cy = p1.y + t * dy
        a = point(cx - perp_x * half, cy - perp_y * half)
        b = point(cx + perp_x * half, cy + perp_y * half)
        tick = segment(a, b)
        draw(tick)
        ticks.append(tick)
    return ticks


# --- bar / bars: rectangle bars for tape diagrams, bar graphs, area-model ----
# cells, and fill-level containers (ticket 10) -------------------------------

def bar(
    x: float,
    y: float,
    width: float,
    height: float,
    fill_color: "str | None" = None,
    fill_opacity: float = 1.0,
    label: "str | None" = None,
    **draw_style,
) -> Polygon:
    """A single rectangle bar with corner (x, y) and the given width/height
    (same corner/width/height convention as `rectangle()`) — the one-bar
    building block for a tape-diagram section, a single bar-graph column, an
    area-model cell, or a fill-level container (call it twice: once for the
    container outline, once more for the filled portion). `draw_style`
    kwargs (color, thick, dashed, ...) are forwarded to `draw()` for the
    outline. If `fill_color` is given, the bar's interior is filled (at
    `fill_opacity`, default fully opaque) — e.g. a shaded fill-level portion
    or a bar-graph bar's fill color. If `label` is given, it's placed at the
    bar's centroid — e.g. an area-model cell's partial product, or a
    tape-diagram section's value. Returns the underlying rectangle handle."""
    if width == 0 or height == 0:
        raise ValueError(f"bar(): width and height must be nonzero, got width={width!r}, height={height!r}")
    rect = rectangle(corner=point(x, y), width=width, height=height)
    draw(rect, **draw_style)
    if fill_color is not None:
        fill(rect, color=fill_color, opacity=fill_opacity)
    if label is not None:
        label_text(str(label), centroid_of=rect)
    return rect


def bars(
    values: "list[float]",
    x0: float = 0.0,
    y0: float = 0.0,
    bar_width: float = 1.0,
    gap: float = 0.2,
    orientation: str = "vertical",
    fill_color: "str | None" = None,
    labels: "list[str] | None" = None,
    **draw_style,
) -> "list[Polygon]":
    """A row of `len(values)` equal-thickness bars laid out side by side,
    starting at (x0, y0) — for a bar graph's whole series, or a tape
    diagram's row of (typically equal) sections. Built on top of `bar()`,
    called once per value.

    orientation="vertical" (default): bars stand upright, each growing from
    baseline y0 to height `values[i]`, arranged left-to-right along x, each
    `bar_width` wide with `gap` between consecutive bars — a standard
    vertical bar-graph layout.
    orientation="horizontal": bars extend rightward from baseline x0 to
    width `values[i]`, stacked top-to-bottom along y (same `bar_width`/`gap`
    spacing) — a horizontal tape-diagram row of sections.

    `fill_color`/`draw_style` are forwarded to every `bar()` call unchanged.
    `labels[i]`, if given, is centered inside the i-th bar (e.g. each
    section's value, or each column's bar value) — must be the same length
    as `values` if given. Returns the list of rectangle handles, in the
    same order as `values`."""
    if orientation not in ("vertical", "horizontal"):
        raise ValueError(f"bars(): orientation must be 'vertical' or 'horizontal', got {orientation!r}")
    if not values:
        raise ValueError("bars(): values must be non-empty")
    if labels is not None and len(labels) != len(values):
        raise ValueError(f"bars(): labels must be the same length as values ({len(values)}), got {len(labels)}")
    if bar_width <= 0:
        raise ValueError(f"bars(): bar_width must be positive, got {bar_width!r}")

    rects = []
    for i, v in enumerate(values):
        offset = i * (bar_width + gap)
        if orientation == "vertical":
            bx, by = x0 + offset, y0
            w, h = bar_width, v
        else:
            bx, by = x0, y0 + offset
            w, h = v, bar_width
        lbl = labels[i] if labels is not None else None
        rects.append(bar(bx, by, w, h, fill_color=fill_color, label=lbl, **draw_style))
    return rects


# --- table_grid: bordered grid of labeled cells (ticket 11) -----------------
# Underlies attribute_chart, work_table, place_value_chart,
# column_arithmetic, and long_division. A header row or label column is
# just an ordinary row 0 / column 0 of the grid — placing each header/label
# exactly once via one cell's `.cx`/`.cy` anchor is what avoids the
# duplicate-header defect a hand-rolled table is prone to.

class TableCell:
    """One cell of a `table_grid()`, addressed by (row, col) starting at
    (0, 0) for the top-left cell. `x0`/`y0` is the cell's top-left corner
    and `x1`/`y1` its bottom-right corner (y0 >= y1, since row 0 sits at
    the top and rows stack downward as y decreases); `width`/`height` are
    always positive. `cx`/`cy` is the cell's center — pass it straight to
    `label_text(text, at=(cell.cx, cell.cy))` to place a header, row label,
    or value exactly once, precisely centered in the cell."""
    __slots__ = ("row", "col", "x0", "y0", "x1", "y1", "width", "height", "cx", "cy")

    def __init__(self, row: int, col: int, x0: float, y0: float, x1: float, y1: float):
        self.row = row
        self.col = col
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.width = x1 - x0
        self.height = y0 - y1
        self.cx = (x0 + x1) / 2.0
        self.cy = (y0 + y1) / 2.0


class TableGrid:
    """The return value of `table_grid()`: `n_rows` x `n_cols` cells,
    addressable via `.cell(row, col)`. Iterating over a `TableGrid` yields
    every `TableCell` in row-major order."""

    def __init__(self, cells: "dict[tuple[int, int], TableCell]", n_rows: int, n_cols: int):
        self._cells = cells
        self.n_rows = n_rows
        self.n_cols = n_cols

    def cell(self, row: int, col: int) -> TableCell:
        """The `TableCell` at (row, col). Raises KeyError if out of range."""
        return self._cells[(row, col)]

    def __iter__(self):
        return iter(self._cells.values())


def table_grid(
    x0: float,
    y0: float,
    col_widths: "list[float]",
    row_heights: "list[float]",
    color: str = "black",
    **draw_style,
) -> TableGrid:
    """Draw a bordered `len(row_heights)` x `len(col_widths)` table grid
    anchored with its top-left corner at (x0, y0) — row 0 is the top row,
    rows stacking downward (decreasing y) by each entry in `row_heights`;
    column 0 is the leftmost column, columns extending rightward
    (increasing x) by each entry in `col_widths`. Treat a header row or a
    row-label column as an ordinary row 0 / column 0 of the SAME grid
    (rather than drawing it as a separate table) — that is what keeps each
    header/label rendered exactly once instead of duplicated.

    Draws every interior and exterior grid line exactly once (shared
    borders between adjacent cells are a single line, never doubled);
    `color`/`draw_style` kwargs (thick, dashed, ...) are forwarded to each
    `draw()` call, same as `unit_grid()`.

    Returns a `TableGrid` — call `.cell(row, col)` to get that cell's
    `TableCell`, whose `.cx`/`.cy` center is the anchor to pass to
    `label_text(text, at=(cell.cx, cell.cy))` for a header, row label, or
    value placed exactly once and precisely centered; `.x0`/`.y0`/`.x1`/
    `.y1`/`.width`/`.height` give the cell's exact extent if you need to
    `fill()` a highlighted cell via your own `rectangle()` call."""
    if not col_widths:
        raise ValueError("table_grid(): col_widths must be non-empty")
    if not row_heights:
        raise ValueError("table_grid(): row_heights must be non-empty")
    if any(w <= 0 for w in col_widths):
        raise ValueError(f"table_grid(): all col_widths must be positive, got {col_widths!r}")
    if any(h <= 0 for h in row_heights):
        raise ValueError(f"table_grid(): all row_heights must be positive, got {row_heights!r}")

    col_edges = [x0]
    for w in col_widths:
        col_edges.append(col_edges[-1] + w)
    row_edges = [y0]
    for h in row_heights:
        row_edges.append(row_edges[-1] - h)

    n_cols = len(col_widths)
    n_rows = len(row_heights)

    for i in range(n_cols + 1):
        x = col_edges[i]
        draw(segment(point(x, row_edges[0]), point(x, row_edges[-1])), color=color, **draw_style)
    for j in range(n_rows + 1):
        y = row_edges[j]
        draw(segment(point(col_edges[0], y), point(col_edges[-1], y)), color=color, **draw_style)

    cells = {
        (r, c): TableCell(r, c, col_edges[c], row_edges[r], col_edges[c + 1], row_edges[r + 1])
        for r in range(n_rows)
        for c in range(n_cols)
    }
    return TableGrid(cells, n_rows, n_cols)


# --- oblique_point: 2D oblique projection of a 3D coordinate (ticket 12) ----
# Underlies cube_volume, prism_3d, l_prism, and prism_net. Ticket 07's
# baseline found all four of these already got a "pass" verdict from
# PythonFullStrategy using only hand-rolled arithmetic (each script computed
# its own "x + skew*z, y + skew*z" projection inline) — this helper doesn't
# fix anything broken, it just gives a name to the pattern so future scripts
# (especially from a less capable model) don't have to reinvent/re-derive it
# every time, and so every depth-axis point in one script uses a provably
# consistent skew.
#
# There is NO depth/occlusion concept anywhere in the IR — to_sympy.py and
# to_svg.py know nothing about which 3D face a segment "belongs to" or which
# edges a solid face would hide. A script using oblique_point() must decide
# for itself which edges represent hidden geometry (e.g. the back-bottom
# edges of a box, hidden behind its front-bottom-left corner from the
# viewer's implied vantage point) and mark exactly those `draw(..., dashed=True)`
# — oblique_point() only computes coordinates, it has no way to do this for
# the caller.

def oblique_point(x: float, y: float, z: float, skew: float = 0.5) -> Point:
    """A 2D oblique (cavalier-style) projection of a 3D coordinate (x, y, z)
    onto the diagram plane — the standard "receding depth axis" trick for
    drawing a box/prism/net in 2D: the visible width/height axes (x, y) are
    drawn true-to-scale, and the depth axis z is projected by adding
    `skew * z` to BOTH the x and y screen coordinates, so increasing z
    walks "back and up" along a 45-degree receding direction (skew=0.5, the
    default, is a common cavalier-projection ratio; pass a smaller skew for
    a shallower recession, 0 to collapse z entirely and get a flat
    front-on view). Returns an ordinary Point handle — usable directly with
    `segment()`, `polygon()`, `draw()`, `.label()`, etc., exactly like a
    point built via `point(x, y)`. Build every vertex of a 3D solid with
    this SAME skew value so the whole shape shares one consistent
    projection; e.g. for a box from (0,0,0) to (w,h,d):
        front = [oblique_point(0, 0, 0), oblique_point(w, 0, 0),
                 oblique_point(w, h, 0), oblique_point(0, h, 0)]
        back  = [oblique_point(0, 0, d), oblique_point(w, 0, d),
                 oblique_point(w, h, d), oblique_point(0, h, d)]
        draw(polygon(*front))  # the near face: fully visible
        draw(segment(back[2], back[3]), dashed=True)  # a hidden back edge
        draw(segment(front[2], back[2]), dashed=True)  # a hidden connecting edge
        draw(segment(front[1], back[1]))  # a visible connecting edge
    See the section comment above for the manual-hidden-edge convention
    this helper deliberately does NOT automate."""
    return point(x + skew * z, y + skew * z)
