"""
Block stacks: the compiled ``Stack`` object and the ``block_stack``
definition's validation.

A stack is a set of unit cubes on an integer lattice, drawn through the same
parallel projection as the rectangular prism (``prism.projection_for``; this
module never re-derives it). Lattice axes are the prism's: x = length (left to
right), y = height, z = width (depth, front to back). A height map's
``heights[z][x]`` is the number of cubes at column x of row z (rows run front
to back); the cube ``(x, y, z)`` occupies the unit cube from (x, y, z) to
(x+1, y+1, z+1).

The lattice points (every corner of every cube) are owned ids registered into
the symbol table as plain SymPy points with hidden ids ``__{id}_l{x}_{y}_{z}``.
The only public derived ids are the column top faces ``{id}_top_{x}_{z}``
(synthesized polygons at each column's top plane). Cube size is one drawing
unit; all values are literal integers.

Rendering the faces is not implemented here: drawing the stack id lowers to
no operations for now.
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

import sympy as sp
import sympy.geometry as spg

from . import ir
from .errors import IRCompileError
from .prism import Projection, projection_for

Cube = tuple[int, int, int]  # (x, y, z)

MAX_CUBES = 400
MAX_CELLS_PER_AXIS = 20


class Stack:
    """Marker type for a block stack in the symbol table (not a SymPy shape,
    like ``Prism``). Holds the normalized cube set, the projection and the
    projected lattice points keyed by lattice coordinates."""

    __slots__ = (
        "cubes", "extents", "is_height_map", "projection", "lattice", "lattice_ids",
    )

    def __init__(
        self,
        cubes: frozenset[Cube],
        extents: tuple[int, int, int],
        projection: Projection,
        lattice: dict[Cube, spg.Point],
        lattice_ids: dict[Cube, str],
    ) -> None:
        self.cubes = cubes
        self.extents = extents  # (length, height, width)
        self.projection = projection
        self.lattice = lattice
        self.lattice_ids = lattice_ids
        self.is_height_map = _is_height_map(cubes)

    @property
    def cube_count(self) -> int:
        return len(self.cubes)

    @property
    def volume(self) -> int:
        return len(self.cubes)  # unit cubes

    @property
    def length(self) -> int:
        return self.extents[0]

    @property
    def height(self) -> int:
        return self.extents[1]

    @property
    def width(self) -> int:
        return self.extents[2]

    @property
    def center(self) -> tuple[float, float]:
        """Center of the BOUNDING BOX of the projected lattice, i.e. of the
        drawn silhouette (for a full box it equals the prism's center). For a
        concave stack (an L shape) this point can lie in a notch of the
        silhouette, not on a cube: to put a label on the stack itself, address
        a column top face (``{id}_top_{x}_{z}``) instead."""
        xs = [float(p.x) for p in self.lattice.values()]
        ys = [float(p.y) for p in self.lattice.values()]
        return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Stack(cubes={self.cube_count}, extents={self.extents})"


def _is_height_map(cubes: frozenset[Cube]) -> bool:
    """No cube has empty space directly beneath it."""
    return all(y == 0 or (x, y - 1, z) in cubes for x, y, z in cubes)


def lattice_id(stack_id: str, point: Cube) -> str:
    return f"__{stack_id}_l{point[0]}_{point[1]}_{point[2]}"


def top_face_id(stack_id: str, x: int, z: int) -> str:
    return f"{stack_id}_top_{x}_{z}"


# --- validation ---------------------------------------------------------------------

def _integer_entry(did: str, value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise IRCompileError(did, f"block_stack {where} must be a non-negative integer, got {value!r}")
    if not math.isfinite(value) or float(value) != int(value):
        raise IRCompileError(did, f"block_stack {where} must be an integer, got {value!r}")
    if value < 0:
        raise IRCompileError(did, f"block_stack {where} must be non-negative, got {value!r}")
    return int(value)


def _height_grid(stmt: ir.BlockStack) -> tuple[tuple[int, ...], ...]:
    """The validated height map as rows of ints. Raises IRCompileError."""
    did = stmt.id
    if (stmt.heights is None) == (stmt.cubes is None):
        raise IRCompileError(
            did,
            "block_stack needs exactly one of heights (rows of column heights) and cubes "
            "(a list of [x, y, z] cubes); got " + ("both" if stmt.heights is not None else "neither"),
        )
    if stmt.cubes is not None:
        raise IRCompileError(did, "block_stack cubes is not yet supported; use heights")
    rows = stmt.heights
    if not rows or not all(rows):
        raise IRCompileError(did, "block_stack heights is empty: give at least one row with at least one column")
    if len({len(r) for r in rows}) != 1:
        raise IRCompileError(
            did, f"block_stack heights has ragged rows (lengths {[len(r) for r in rows]}); every row needs the same number of columns"
        )
    grid = tuple(
        tuple(_integer_entry(did, v, f"heights[{z}][{x}]") for x, v in enumerate(row))
        for z, row in enumerate(rows)
    )
    for name, size in (("rows", len(grid)), ("columns", len(grid[0])), ("height", max(map(max, grid)))):
        if size > MAX_CELLS_PER_AXIS:
            raise IRCompileError(
                did, f"block_stack allows at most {MAX_CELLS_PER_AXIS} cells along any axis; heights has {size} {name}"
            )
    total = sum(map(sum, grid))
    if total == 0:
        raise IRCompileError(did, "block_stack is empty: every height is 0, so there are no cubes")
    if total > MAX_CUBES:
        raise IRCompileError(did, f"block_stack allows at most {MAX_CUBES} cubes; heights gives {total}")
    return grid


@lru_cache(maxsize=64)
def _cubes_of(grid: tuple[tuple[int, ...], ...]) -> frozenset[Cube]:
    return frozenset(
        (x, y, z) for z, row in enumerate(grid) for x, h in enumerate(row) for y in range(h)
    )


def _extents(grid: tuple[tuple[int, ...], ...]) -> tuple[int, int, int]:
    return (len(grid[0]), max(map(max, grid)), len(grid))


def _valid_cubes(stmt: ir.BlockStack) -> frozenset[Cube] | None:
    """The cube set, or None when the statement is invalid (compile reports
    that; the registry hooks synthesize and own nothing meanwhile)."""
    try:
        return _cubes_of(_height_grid(stmt))
    except IRCompileError:
        return None


def _corners(cubes: frozenset[Cube]) -> list[Cube]:
    pts = {
        (x + dx, y + dy, z + dz)
        for x, y, z in cubes for dx in (0, 1) for dy in (0, 1) for dz in (0, 1)
    }
    return sorted(pts)


@lru_cache(maxsize=64)
def _lattice_names(stack_id: str, cubes: frozenset[Cube]) -> dict[Cube, str]:
    return {p: lattice_id(stack_id, p) for p in _corners(cubes)}


def lattice_names(stmt: ir.BlockStack) -> dict[Cube, str]:
    """Lattice coordinates -> hidden point id, for every cube corner; empty
    for an invalid statement. Cached per (id, cube set); callers must not
    mutate the result."""
    cubes = _valid_cubes(stmt)
    if cubes is None:
        return {}
    return _lattice_names(stmt.id, cubes)


# --- compile ------------------------------------------------------------------------

def compile_stack(stmt: ir.BlockStack, origin: Any) -> Stack:
    """Validate ``stmt`` and build its Stack from the resolved origin point.
    Raises IRCompileError."""
    did = stmt.id
    grid = _height_grid(stmt)
    try:
        projection = projection_for(stmt.view, stmt.side, stmt.depth_angle, stmt.depth_scale)
    except ValueError as e:
        raise IRCompileError(did, f"block_stack: {e}") from e
    if not isinstance(origin, spg.Point):
        raise IRCompileError(
            did, f"block_stack origin {stmt.origin!r} must be a point, got {type(origin).__name__}"
        )
    cubes = _cubes_of(grid)
    lattice: dict[Cube, spg.Point] = {}
    for p in _corners(cubes):
        dx, dy = projection.offset(sp.Integer(p[0]), sp.Integer(p[1]), sp.Integer(p[2]))
        lattice[p] = spg.Point(origin.x + dx, origin.y + dy)
    return Stack(cubes, _extents(grid), projection, lattice, lattice_names(stmt))


def register_lattice(stmt: ir.BlockStack, obj: Any, sym: dict[str, Any]) -> None:
    """Registry ``register`` hook: add the lattice points to ``sym``. A name
    already present is a collision, never silently skipped or overwritten."""
    if not isinstance(obj, Stack):
        return
    for p, name in obj.lattice_ids.items():
        if name in sym:
            raise IRCompileError(stmt.id, f"lattice point id {name!r} collides with an existing definition; rename it")
        sym[name] = obj.lattice[p]


def synthesize_top_faces(stmt: ir.BlockStack) -> list[Any]:
    """Registry ``synthesize`` hook: one polygon per occupied column, at the
    plane of its topmost cube's top, over the lattice ids. Empty for an invalid
    statement (compile reports it)."""
    cubes = _valid_cubes(stmt)
    if cubes is None:
        return []
    top: dict[tuple[int, int], int] = {}
    for x, y, z in cubes:
        top[(x, z)] = max(top.get((x, z), 0), y + 1)
    out = []
    for (x, z), y in sorted(top.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        corners = [(x, y, z), (x + 1, y, z), (x + 1, y, z + 1), (x, y, z + 1)]
        out.append(ir.Polygon(
            id=top_face_id(stmt.id, x, z), points=[lattice_id(stmt.id, c) for c in corners]
        ))
    return out


def stack_position(obj: Any) -> tuple[float, float] | None:
    return obj.center if isinstance(obj, Stack) else None


# --- render operations on the stack id -----------------------------------------------

_VALID_SLOTS = frozenset({"draw", "centroid"})


def render_ref_error(stmt: ir.BlockStack, op_kind: str, slot: str) -> str | None:
    """Registry ``render_ref_error`` hook: the message for the stack id used in
    ``slot`` of a ``op_kind`` render operation; None when valid."""
    if slot in _VALID_SLOTS:
        return None
    sid = stmt.id
    top = top_face_id(sid, 0, 0)
    if slot in ("fill", "fill_hole"):
        alt = (
            "set front_color, side_color and top_color on the stack to colour its faces, or "
            f"fill a column top face id such as {top!r}"
        )
        why = "a stack has no single outline to fill"
    elif slot == "point":
        why, alt = "a stack is not a point", f"use a column top face id such as {top!r} for a label position"
    elif slot == "segment":
        why, alt = "a stack is not a segment", "stacks have no addressable edges"
    else:  # arc
        why, alt = "a stack has no arcs", (
            f"to place text use label_free_text with centroid_of={sid!r} or a column top face id such as {top!r}"
        )
    return f"{op_kind} cannot use the block_stack {sid!r}: {why}; {alt}"


def render_warnings(stmt: ir.BlockStack, diagram: Any) -> list[str]:
    """Registry ``render_warnings`` hook: a stack on a canvas with unequal axis
    scales is drawn skewed (the projection assumes equal units)."""
    canvas = diagram.canvas
    aspect = canvas.aspect if canvas is not None else None
    if aspect is not None and aspect != 1:
        return [
            f"block_stack {stmt.id!r} is drawn on a canvas with unequal axis scales "
            f"(canvas.aspect={aspect}): the projection is skewed (the depth angle and face "
            f"shapes are distorted); remove canvas.aspect for an undistorted stack"
        ]
    return []


def lower_draw(stmt: ir.BlockStack, op: Any, styles: dict[str, Any]) -> Any:
    """Registry ``lower_draw`` hook. Face rendering is a later ticket: for now
    drawing the stack id lowers to no operations (it draws nothing)."""
    from .derived import Lowering

    return Lowering(ops=[])
