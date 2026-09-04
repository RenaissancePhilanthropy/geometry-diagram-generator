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
below. Later tickets (10-12) append further helpers here — keep each
group under its own section comment so they can be added without
restructuring what's already here.
"""
from __future__ import annotations

import math

from geometry_diagrams.pydsl.api import circle, draw, fill, point, rectangle, segment
from geometry_diagrams.pydsl.handles import Point


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
