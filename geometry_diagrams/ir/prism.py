"""
Rectangular prisms: the projection, the compiled ``Prism`` object and the
prism definition's validation.

A projection is a linear map of the three prism axes to 2D vectors. Axis
order everywhere is (length, height, width), which is also the bit order of a
corner: corner (a, b, c) sits at ``origin + a*L*e_length + b*H*e_height +
c*W*e_width``. The viewer direction is the kernel of that map, signed so the
top face is visible; which faces are visible and which corner is hidden are
derived from it, never hard-coded per view.

All map constants are exact SymPy values (radicals, rationals), never floats:
corner coordinates feed later SymPy constructions, and floats would be turned
into huge rationals there.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Any, Callable

import sympy as sp
import sympy.geometry as spg

from . import ir
from .errors import IRCompileError

AXES = ("length", "height", "width")
CORNER_BITS: tuple[tuple[int, int, int], ...] = tuple(itertools.product((0, 1), repeat=3))

# Oblique defaults, measured on the reference art (solids ticket 08): the
# receding depth edge runs at 45 degrees (fitted 44.2-45.1 across the four
# oblique figures) at half scale (0.50 on the one oblique figure with a stated
# depth, which the art draws proportionally), i.e. cabinet projection. Both
# are exact: cos 45 = sin 45 = sqrt(2)/2. The single place they are defined.
OBLIQUE_DEFAULT_ANGLE_DEG = 45
OBLIQUE_DEFAULT_SCALE = sp.Rational(1, 2)

_COS30 = sp.sqrt(3) / 2
_SIN30 = sp.Rational(1, 2)

Vec2 = tuple[sp.Expr, sp.Expr]


def _sign(value: sp.Expr) -> int:
    """Sign of an exact constant, robust to SymPy not deciding it symbolically."""
    v = float(sp.N(value, 30))
    if abs(v) < 1e-12:
        return 0
    return 1 if v > 0 else -1


@dataclass(frozen=True)
class Projection:
    """Images of the length, height and width axes (in that order)."""

    length: Vec2
    height: Vec2
    width: Vec2

    @property
    def axes(self) -> tuple[Vec2, Vec2, Vec2]:
        return (self.length, self.height, self.width)

    @property
    def viewer(self) -> tuple[sp.Expr, sp.Expr, sp.Expr]:
        """Direction toward the viewer in prism axes (length, height, width):
        the kernel of the map (cross product of its two rows), signed so the
        top face (height max) faces the viewer."""
        row_x = [v[0] for v in self.axes]
        row_y = [v[1] for v in self.axes]
        k = sp.Matrix(row_x).cross(sp.Matrix(row_y))
        if _sign(k[1]) == 0:
            raise ValueError("degenerate projection: the top face is seen edge-on")
        if _sign(k[1]) < 0:
            k = -k
        return (sp.simplify(k[0]), sp.simplify(k[1]), sp.simplify(k[2]))

    @property
    def visible_planes(self) -> frozenset[tuple[str, str]]:
        """Visible faces as (axis, "min" | "max"): a face is visible when its
        outward normal points toward the viewer. An axis whose faces are both
        seen edge-on contributes nothing."""
        planes = set()
        for axis, k in zip(AXES, self.viewer):
            s = _sign(k)
            if s:
                planes.add((axis, "max" if s > 0 else "min"))
        return frozenset(planes)

    @property
    def hidden_corner(self) -> tuple[int, int, int]:
        """Corner bits (length, height, width) of the corner farthest from the
        viewer: on each axis, the side whose face is hidden."""
        return tuple(1 if _sign(k) < 0 else 0 for k in self.viewer)  # type: ignore[return-value]

    def offset(self, length: Any, height: Any, width: Any) -> Vec2:
        x = length * self.length[0] + height * self.height[0] + width * self.width[0]
        y = length * self.length[1] + height * self.height[1] + width * self.width[1]
        return (x, y)


def projection_for(
    view: str = "oblique",
    side: str = "right",
    depth_angle: float | None = None,
    depth_scale: float | None = None,
) -> Projection:
    """The projection a prism's flat view fields select. Raises ValueError for
    an invalid combination (overrides with isometric, out-of-range values).

    oblique: length -> (1, 0), height -> (0, 1), width -> s*(cos a, sin a);
        side=left negates the x component of the width (depth) vector.
    isometric: right: length -> (cos30, -sin30), height -> (0, 1),
        width -> (cos30, sin30). left: length -> (cos30, sin30),
        width -> (-cos30, sin30); the left mapping is the only one with
        isometric axes, a vertical height, length running rightward along the
        front bottom edge, and a kernel that shows the front, left and top
        faces (negating only the depth x component, as oblique does, would
        make width the exact opposite of length: a degenerate map).
    """
    if side not in ("right", "left"):
        raise ValueError(f"side must be 'right' or 'left', got {side!r}")
    if view == "isometric":
        if depth_angle is not None or depth_scale is not None:
            raise ValueError(
                "depth_angle and depth_scale apply only to the oblique view; "
                "remove them for view='isometric' or use view='oblique'"
            )
        if side == "right":
            return Projection((_COS30, -_SIN30), (sp.S(0), sp.S(1)), (_COS30, _SIN30))
        return Projection((_COS30, _SIN30), (sp.S(0), sp.S(1)), (-_COS30, _SIN30))
    if view != "oblique":
        raise ValueError(f"view must be 'oblique' or 'isometric', got {view!r}")
    angle = sp.Rational(str(OBLIQUE_DEFAULT_ANGLE_DEG if depth_angle is None else depth_angle))
    scale = OBLIQUE_DEFAULT_SCALE if depth_scale is None else sp.Rational(str(depth_scale))
    if not 0 < angle < 90:
        raise ValueError(f"depth_angle must be between 0 and 90 degrees (exclusive), got {depth_angle}")
    if not scale > 0:
        raise ValueError(f"depth_scale must be positive, got {depth_scale}")
    rad = sp.pi * angle / 180
    dx, dy = scale * sp.cos(rad), scale * sp.sin(rad)
    if side == "left":
        dx = -dx
    return Projection((sp.S(1), sp.S(0)), (sp.S(0), sp.S(1)), (dx, dy))


class Prism:
    """Marker type for a rectangular prism in the symbol table (not a SymPy
    shape, like Arc/Sector). Holds the true dimensions, the projection and the
    eight projected corners keyed by (length, height, width) bits."""

    __slots__ = ("length", "width", "height", "projection", "corners", "corner_ids")

    def __init__(
        self,
        length: sp.Expr,
        width: sp.Expr,
        height: sp.Expr,
        projection: Projection,
        corners: dict[tuple[int, int, int], spg.Point],
        corner_ids: dict[tuple[int, int, int], str],
    ) -> None:
        self.length = length
        self.width = width
        self.height = height
        self.projection = projection
        self.corners = corners
        self.corner_ids = corner_ids

    @property
    def volume(self) -> sp.Expr:
        return self.length * self.width * self.height

    @property
    def base_area(self) -> sp.Expr:
        """Area of the bottom face (the base): length x width."""
        return self.length * self.width

    @property
    def surface_area(self) -> sp.Expr:
        l, w, h = self.length, self.width, self.height
        return 2 * (l * w + l * h + w * h)

    @property
    def center(self) -> spg.Point:
        """Projected center of the box (mean of the eight corners), which is
        the center of symmetry of the drawn silhouette."""
        xs = sum(p.x for p in self.corners.values())
        ys = sum(p.y for p in self.corners.values())
        return spg.Point(xs / 8, ys / 8)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Prism(L={self.length}, W={self.width}, H={self.height})"


def corner_names(stmt: ir.RectangularPrism) -> dict[tuple[int, int, int], str]:
    """Corner bits -> corner point id, in product order. Default ids are
    ``{id}_v{a}{b}{c}``; ``vertex_names`` replaces them in the same order (a
    list of the wrong length is reported by ``validate``, not here)."""
    if stmt.vertex_names is not None:
        return dict(zip(CORNER_BITS, stmt.vertex_names))
    return {bits: f"{stmt.id}_v{''.join(map(str, bits))}" for bits in CORNER_BITS}


def _unit_cube_dim(stmt: ir.RectangularPrism, field: str) -> sp.Integer:
    raw = getattr(stmt, field)
    literal = isinstance(raw, (int, float)) and not isinstance(raw, bool)
    if not literal or not math.isfinite(raw) or float(raw) != int(raw):
        raise IRCompileError(
            stmt.id,
            f"rectangular_prism with unit_cubes needs literal positive integer "
            f"dimensions; {field} is {raw!r}",
        )
    return sp.Integer(int(raw))


def compile_prism(
    stmt: ir.RectangularPrism,
    origin: Any,
    ev: Callable[[Any], sp.Expr],
) -> Prism:
    """Validate ``stmt`` and build its Prism from the resolved origin point.
    ``ev`` evaluates a dimension (number or expression). Raises IRCompileError."""
    did = stmt.id
    if stmt.vertex_names is not None:
        if len(stmt.vertex_names) != 8:
            raise IRCompileError(
                did,
                f"rectangular_prism vertex_names must list exactly eight corner names "
                f"(in itertools.product((0, 1), repeat=3) order), got {len(stmt.vertex_names)}",
            )
        seen: set[str] = set()
        for name in stmt.vertex_names:
            if name == did:
                raise IRCompileError(did, f"corner name {name!r} is the prism's own id; rename the corner")
            if name in seen:
                raise IRCompileError(did, f"corner name {name!r} is used twice; corner names must be distinct")
            seen.add(name)
    try:
        projection = projection_for(stmt.view, stmt.side, stmt.depth_angle, stmt.depth_scale)
    except ValueError as e:
        raise IRCompileError(did, f"rectangular_prism: {e}") from e
    if not isinstance(origin, spg.Point):
        raise IRCompileError(
            did, f"rectangular_prism origin {stmt.origin!r} must be a point, got {type(origin).__name__}"
        )

    dims: dict[str, sp.Expr] = {}
    for field in ("length", "width", "height"):
        value = _unit_cube_dim(stmt, field) if stmt.unit_cubes else ev(getattr(stmt, field))
        if not (getattr(value, "is_number", False) and value.is_real is not False):
            raise IRCompileError(did, f"rectangular_prism {field} must be a number, got {value}")
        if float(sp.N(value)) <= 0:
            raise IRCompileError(did, f"rectangular_prism {field} must be positive, got {value}")
        dims[field] = value

    L, W, H = dims["length"], dims["width"], dims["height"]
    corners = {}
    for bits in CORNER_BITS:
        a, b, c = bits
        dx, dy = projection.offset(a * L, b * H, c * W)
        corners[bits] = spg.Point(origin.x + dx, origin.y + dy)
    return Prism(L, W, H, projection, corners, corner_names(stmt))


def register_corners(stmt: ir.RectangularPrism, obj: Any, sym: dict[str, Any]) -> None:
    """Add the eight corners to ``sym``. A corner name already present is a
    collision (compile_defs reports those up front; this guards incremental
    compiles), never silently skipped or overwritten."""
    if not isinstance(obj, Prism):
        return
    for bits, name in obj.corner_ids.items():
        if name in sym:
            raise IRCompileError(
                stmt.id, f"corner name {name!r} collides with an existing definition; rename the corner"
            )
        sym[name] = obj.corners[bits]


def prism_position(obj: Any) -> tuple[float, float] | None:
    if not isinstance(obj, Prism):
        return None
    c = obj.center
    return (float(c.x), float(c.y))
