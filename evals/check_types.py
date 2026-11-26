"""The eval check types: one registration per type.

A check type is a name plus what the loader and the runner need of it:

- ``validate_args(args, where)`` raises ValueError for malformed arguments when a scenario
  file loads (optional);
- ``evaluate`` does the check. A *geometry* property (``family="geometry"``) is
  ``evaluate(args, ctx) -> (passed, message)`` on a ``GeometryContext`` (the figure's float
  point table and the tolerance); a *structural* check is
  ``evaluate(args, diagram_ir, tikz_code) -> {"passed": ..., "message": ...}``;
- ``dimension`` (geometry properties): the power of the figure's length scale the compared
  quantity carries, so a ``rel_tol`` becomes ``rel_tol * scale ** dimension``; 0 = only an
  absolute ``tol`` applies (angles in radians, a fraction along a segment, a required
  margin). A type with no dimension takes neither tolerance field.

Property families: ``geometry`` (evaluated on the 2D float points; its point-name arguments
are resolved, see evals/property_names.py), ``render`` (rendering-only: recorded as passing,
never evaluated), ``prism`` / ``stack`` (evaluated through the registered solid queries on the
full symbol table by evals/sympy_checks.py, so ``evaluate`` is None here).

Adding a type is one ``register_property_type`` / ``register_structural_type`` (usable as a
decorator) in this file or any module imported before scenarios load. The loader, the
runner, the tolerance rules and the name resolution all read this registry, so there is no
second list to keep in sync. A type no one registered loads as ``unsupported`` and runs as
skipped (see evals/scenarios.py).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Literal


@dataclass(frozen=True)
class CheckType:
    name: str
    kind: Literal["property", "structural"]
    family: str = "geometry"
    dimension: int | None = None
    validate_args: Callable[[Any, str], None] | None = None
    evaluate: Callable[..., Any] | None = None


_REGISTRY: dict[tuple[str, str], CheckType] = {}
_PROPERTY_FAMILIES = ("geometry", "render", "prism", "stack")


def register_property_type(
    name: str,
    evaluate: Callable | None = None,
    *,
    family: str = "geometry",
    dimension: int | None = None,
    validate_args: Callable[[list, str], None] | None = None,
):
    """Register an ``expected_properties`` type; a decorator when ``evaluate`` is omitted
    (stack it to register one function under several names)."""
    if family not in _PROPERTY_FAMILIES:
        raise ValueError(f"unknown property family {family!r}; expected one of {_PROPERTY_FAMILIES}")
    if family == "geometry" and (dimension is None or not 0 <= dimension <= 4):
        raise ValueError(f"geometry property {name!r} needs a tolerance dimension 0-4")
    if family != "geometry" and dimension is not None:
        raise ValueError(f"{family} property {name!r} takes no tolerance dimension")

    def register(fn: Callable | None):
        if family in ("geometry", "render") and fn is None:
            raise ValueError(f"{family} property {name!r} needs an evaluator")
        _REGISTRY[("property", name)] = CheckType(
            name, "property", family, dimension, validate_args, fn,
        )
        return fn

    if evaluate is None and family in ("prism", "stack"):
        return register(None)  # nothing to decorate: they are evaluated elsewhere
    return register if evaluate is None else register(evaluate)


def register_structural_type(
    name: str,
    evaluate: Callable | None = None,
    *,
    validate_args: Callable[[dict, str], None] | None = None,
):
    """Register a ``structural_checks`` type; a decorator when ``evaluate`` is omitted."""
    def register(fn: Callable):
        _REGISTRY[("structural", name)] = CheckType(
            name, "structural", "structural", None, validate_args, fn,
        )
        return fn

    return register if evaluate is None else register(evaluate)


def unregister(kind: str, name: str) -> None:
    """Remove a registration (for tests that add a temporary type)."""
    _REGISTRY.pop((kind, name), None)


def property_type(name: Any) -> CheckType | None:
    return _REGISTRY.get(("property", name)) if isinstance(name, str) else None


def structural_type(name: Any) -> CheckType | None:
    return _REGISTRY.get(("structural", name)) if isinstance(name, str) else None


def property_type_names(family: str | None = None) -> frozenset[str]:
    return frozenset(
        n for (k, n), t in _REGISTRY.items() if k == "property" and (family is None or t.family == family)
    )


def structural_type_names() -> frozenset[str]:
    return frozenset(n for (k, n) in _REGISTRY if k == "structural")


def tolerance_dimension(name: Any) -> int | None:
    """The geometry property's tolerance dimension; None for any other type."""
    t = property_type(name)
    return t.dimension if t is not None and t.family == "geometry" else None


# ---------------------------------------------------------------------------
# Argument validators (run when a scenario file loads)
# ---------------------------------------------------------------------------

def _validate_solid_count_args(args: dict[str, Any], where: str) -> None:
    """solid_count args: optional kind (str), min (int >= 0), optional
    literal dimensions length/width/height (numbers) and, for block_stack,
    a literal cube_count (int >= 0)."""
    unknown = sorted(set(args) - {"kind", "min", "length", "width", "height", "cube_count"})
    if unknown:
        raise ValueError(f"{where}: unknown solid_count arg(s) {unknown}")
    if "kind" in args and not (isinstance(args["kind"], str) and args["kind"].strip()):
        raise ValueError(f"{where}: solid_count 'kind' must be a non-empty string")
    if "min" in args and (
        isinstance(args["min"], bool) or not isinstance(args["min"], int) or args["min"] < 0
    ):
        raise ValueError(f"{where}: solid_count 'min' must be a non-negative integer")
    for dim in ("length", "width", "height"):
        if dim in args and (
            isinstance(args[dim], bool) or not isinstance(args[dim], (int, float))
        ):
            raise ValueError(f"{where}: solid_count {dim!r} must be a literal number")


    if "cube_count" in args and (
        isinstance(args["cube_count"], bool)
        or not isinstance(args["cube_count"], int)
        or args["cube_count"] < 0
    ):
        raise ValueError(f"{where}: solid_count 'cube_count' must be a non-negative integer")


def _validate_stack_cube_count_args(args: list, where: str) -> None:
    """stack_cube_count args: [stack id or "*", expected count (int >= 0)]."""
    ok = (
        len(args) == 2
        and isinstance(args[0], str) and args[0].strip()
        and isinstance(args[1], int) and not isinstance(args[1], bool) and args[1] >= 0
    )
    if not ok:
        raise ValueError(
            f"{where}: stack_cube_count args must be [stack id or \"*\", "
            "non-negative integer count]"
        )


def _is_stack_id(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _validate_stack_extents_args(args: list, where: str) -> None:
    """stack_extents args: [stack id or "*", length, width, height] (ints >= 0)."""
    ok = (
        len(args) == 4
        and _is_stack_id(args[0])
        and all(isinstance(a, int) and not isinstance(a, bool) and a >= 0 for a in args[1:])
    )
    if not ok:
        raise ValueError(
            f"{where}: stack_extents args must be [stack id or \"*\", "
            "length, width, height] (non-negative integers)"
        )


def _validate_stack_is_height_map_args(args: list, where: str) -> None:
    """stack_is_height_map args: [stack id or "*", true/false]."""
    if not (len(args) == 2 and _is_stack_id(args[0]) and isinstance(args[1], bool)):
        raise ValueError(
            f"{where}: stack_is_height_map args must be [stack id or \"*\", true/false]"
        )


def _is_name(x: Any) -> bool:
    return isinstance(x, str) and bool(x.strip())


def _distinct_names(items: Any, count: int | None, where: str, what: str) -> None:
    if not isinstance(items, list) or not all(_is_name(i) for i in items):
        raise ValueError(f"{where}: {what} must be a list of point names, got {items!r}")
    if (count is not None and len(items) != count) or len(set(items)) != len(items):
        need = f"{count} " if count is not None else ""
        raise ValueError(f"{where}: {what} must be {need}distinct points, got {items!r}")


def _validate_angle_args(args: list, where: str) -> None:
    """right_angle [a, o, b]; angle_value [a, o, b, degrees]: three distinct points."""
    _distinct_names(args[:3], 3, where, "the angle's points [a, o, b]")


def _validate_angle_pair_args(args: list, where: str) -> None:
    """angle_equal [[a1, o1, b1], [a2, o2, b2]]: two angles of three distinct points each
    (an angle named by a number, "angle 1", is not a point triple)."""
    if len(args) != 2:
        raise ValueError(f"{where}: needs two angles [[a, o, b], [a, o, b]], got {len(args)} argument(s)")
    for triple in args:
        _distinct_names(triple, 3, where, "an angle [a, o, b]")


def _validate_segment_args(args: list, where: str) -> None:
    """equal_lengths / parallel / perpendicular [[p, q], ...]: segments of two distinct points."""
    if not args or not all(isinstance(seg, list) for seg in args):
        raise ValueError(f"{where}: needs a list of segments [[p, q], ...], got {args!r}")
    for seg in args:
        _distinct_names(seg, 2, where, "a segment [p, q]")


def _validate_distinct_points_args(count: int | None, minimum: int = 0):
    def validate(args: list, where: str) -> None:
        _distinct_names(args[:count] if count else args, count, where, "the points")
        if len(args) < minimum:
            raise ValueError(f"{where}: needs at least {minimum} points, got {len(args)}")
    return validate


# ---------------------------------------------------------------------------
# Geometry properties, evaluated on the figure's float point table
# ---------------------------------------------------------------------------

class GeometryContext:
    """What a geometry evaluator works with: the figure's points (id -> (x, y)) and the
    tolerance this property is held to."""

    def __init__(self, points: dict, tol: float):
        self.points = points
        self.tol = tol

    def pt(self, name: str) -> tuple[float, float]:
        p = self.points.get(name)
        if p is None:
            raise KeyError(f"Point {name!r} not in symbol table")
        return p

    @staticmethod
    def dist(a: tuple, b: tuple) -> float:
        return math.sqrt((a[0] - b[0])**2 + (a[1] - b[1])**2)

    def angle_at(self, o_id: str, p_id: str, q_id: str) -> float:
        """Angle p-o-q in radians, given point ids."""
        O, P, Q = self.pt(o_id), self.pt(p_id), self.pt(q_id)
        va = (P[0] - O[0], P[1] - O[1])
        vb = (Q[0] - O[0], Q[1] - O[1])
        mag_a = math.sqrt(va[0]**2 + va[1]**2)
        mag_b = math.sqrt(vb[0]**2 + vb[1]**2)
        if mag_a < 1e-12 or mag_b < 1e-12:
            raise ValueError("Degenerate angle")
        cos_v = max(-1.0, min(1.0, (va[0]*vb[0] + va[1]*vb[1]) / (mag_a * mag_b)))
        return math.acos(cos_v)


@register_property_type("right_angle", dimension=0, validate_args=_validate_angle_args)
def _right_angle(args, c):
    a, o, b = args[0], args[1], args[2]
    A, O, B = c.pt(a), c.pt(o), c.pt(b)
    va = (A[0] - O[0], A[1] - O[1])
    vb = (B[0] - O[0], B[1] - O[1])
    dot = va[0]*vb[0] + va[1]*vb[1]
    mag_a = math.sqrt(va[0]**2 + va[1]**2)
    mag_b = math.sqrt(vb[0]**2 + vb[1]**2)
    if mag_a < 1e-12 or mag_b < 1e-12:
        return False, "Degenerate angle"
    cos_v = max(-1.0, min(1.0, dot / (mag_a * mag_b)))
    ang = math.acos(cos_v)
    ok = abs(ang - math.pi / 2) < c.tol
    return ok, "" if ok else f"angle={math.degrees(ang):.2f}° (expected 90°)"


@register_property_type("midpoint", dimension=1, validate_args=_validate_distinct_points_args(3))
def _midpoint(args, c):
    m_id, a_id, b_id = args[0], args[1], args[2]
    M, A, B = c.pt(m_id), c.pt(a_id), c.pt(b_id)
    d_ma = c.dist(M, A)
    d_mb = c.dist(M, B)
    ok = abs(d_ma - d_mb) < c.tol
    return ok, "" if ok else f"|MA|={d_ma:.4f} ≠ |MB|={d_mb:.4f}"


@register_property_type("collinear", dimension=2, validate_args=_validate_distinct_points_args(None, 3))
def _collinear(args, c):
    """Every named point lies on the line through the first two (three or more points)."""
    (x1, y1), (x2, y2) = c.pt(args[0]), c.pt(args[1])
    cross = max(abs((x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)) for x, y in (c.pt(n) for n in args[2:]))
    ok = cross < c.tol
    return ok, "" if ok else f"Points {args} are not collinear (cross={cross:.4f})"


@register_property_type("equal_lengths", dimension=1, validate_args=_validate_segment_args)
def _equal_lengths(args, c):
    # args: [[A,B], [C,D], ...] — 2 or more segments, all must be equal length.
    # Every segment is compared against the first (transitively equivalent to
    # all-pairs for equality), so N segments still only need N-1 comparisons.
    lengths = [c.dist(c.pt(seg[0]), c.pt(seg[1])) for seg in args]
    d0 = lengths[0]
    mismatches = [
        (args[i], lengths[i]) for i in range(1, len(lengths))
        if abs(lengths[i] - d0) >= c.tol
    ]
    ok = not mismatches
    msg = "" if ok else (
        f"|{args[0]}|={d0:.4f} but " +
        ", ".join(f"|{seg}|={d:.4f}" for seg, d in mismatches)
    )
    return ok, msg


@register_property_type("parallel", dimension=2, validate_args=_validate_segment_args)
def _parallel(args, c):
    A, B = c.pt(args[0][0]), c.pt(args[0][1])
    C, D = c.pt(args[1][0]), c.pt(args[1][1])
    v1 = (B[0] - A[0], B[1] - A[1])
    v2 = (D[0] - C[0], D[1] - C[1])
    cross = v1[0]*v2[1] - v1[1]*v2[0]
    ok = abs(cross) < c.tol
    return ok, "" if ok else "Lines are not parallel"


@register_property_type("perpendicular", dimension=2, validate_args=_validate_segment_args)
def _perpendicular(args, c):
    A, B = c.pt(args[0][0]), c.pt(args[0][1])
    C, D = c.pt(args[1][0]), c.pt(args[1][1])
    v1 = (B[0] - A[0], B[1] - A[1])
    v2 = (D[0] - C[0], D[1] - C[1])
    dot = v1[0]*v2[0] + v1[1]*v2[1]
    ok = abs(dot) < c.tol
    return ok, "" if ok else f"Lines not perpendicular (dot={dot:.4f})"


@register_property_type("point_on_line", dimension=1)
@register_property_type("point_on_segment", dimension=1)
def _point_on_line(args, c):
    P = c.pt(args[0])
    A, B = c.pt(args[1]), c.pt(args[2])
    dx, dy = B[0] - A[0], B[1] - A[1]
    length = math.sqrt(dx**2 + dy**2)
    if length < 1e-12:
        return False, "Degenerate line"
    cross = abs((P[0] - A[0]) * dy - (P[1] - A[1]) * dx) / length
    ok = cross < c.tol
    return ok, "" if ok else f"{args[0]} not on line (dist={cross:.4f})"


@register_property_type("point_on_circle", dimension=1)
def _point_on_circle(args, c):
    # args: [P, O, R_point] — P on circle centered at O with radius dist(O, R_point)
    P = c.pt(args[0])
    O = c.pt(args[1])
    R = c.pt(args[2])
    r = c.dist(O, R)
    d = c.dist(P, O)
    ok = abs(d - r) < c.tol
    return ok, "" if ok else f"dist({args[0]}, {args[1]})={d:.4f}, radius={r:.4f}"


@register_property_type("tangent", dimension=1)
def _tangent(args, c):
    # args: [[L1, L2], O, T] — line L1-L2 tangent to circle centered O at point T
    # Tangency condition: perpendicular distance from center O to line = radius dist(O, T)
    L1, L2 = c.pt(args[0][0]), c.pt(args[0][1])
    O = c.pt(args[1])
    T = c.pt(args[2])
    r = c.dist(O, T)
    dx, dy = L2[0] - L1[0], L2[1] - L1[1]
    mag_L = math.sqrt(dx**2 + dy**2)
    if mag_L < 1e-12:
        return False, "Degenerate tangent line"
    d_center = abs(dx * (L1[1] - O[1]) - dy * (L1[0] - O[0])) / mag_L
    ok = abs(d_center - r) < c.tol
    return ok, "" if ok else f"dist(center, line)={d_center:.4f} ≠ radius={r:.4f}"


@register_property_type("angle_bisector", dimension=0)
def _angle_bisector(args, c):
    # args: [D, A, B, C] — ray AD bisects angle BAC
    a_id, o_id, b_id, c_id = args[0], args[1], args[2], args[3]
    ang_bad = c.angle_at(o_id, b_id, a_id)
    ang_dac = c.angle_at(o_id, a_id, c_id)
    ok = abs(ang_bad - ang_dac) < c.tol
    return ok, "" if ok else (
        f"angle BAD={math.degrees(ang_bad):.2f}° ≠ angle DAC={math.degrees(ang_dac):.2f}°"
    )


@register_property_type("angle_equal", dimension=0, validate_args=_validate_angle_pair_args)
def _angle_equal(args, c):
    # args: [[a1, o1, b1], [a2, o2, b2]] — angle a1-o1-b1 equals angle a2-o2-b2
    (a1, o1, b1), (a2, o2, b2) = args[0], args[1]
    ang1 = c.angle_at(o1, a1, b1)
    ang2 = c.angle_at(o2, a2, b2)
    ok = abs(ang1 - ang2) < c.tol
    return ok, "" if ok else (
        f"angle {a1}-{o1}-{b1}={math.degrees(ang1):.2f}° ≠ "
        f"angle {a2}-{o2}-{b2}={math.degrees(ang2):.2f}°"
    )


@register_property_type("angle_value", dimension=0, validate_args=_validate_angle_args)
def _angle_value(args, c):
    # args: [a, o, b, expected_deg] — angle a-o-b equals expected_deg
    a_id, o_id, b_id, expected_deg = args[0], args[1], args[2], args[3]
    ang = c.angle_at(o_id, a_id, b_id)
    tol_deg = math.degrees(c.tol)
    ok = abs(math.degrees(ang) - expected_deg) < tol_deg
    return ok, "" if ok else (
        f"angle {a_id}-{o_id}-{b_id}={math.degrees(ang):.2f}° ≠ expected {expected_deg}°"
    )


@register_property_type("distance_equals", dimension=1)
def _distance_equals(args, c):
    # args: [[p1, p2], expected] — distance p1-p2 equals expected
    (p1_id, p2_id), expected = args[0], args[1]
    d = c.dist(c.pt(p1_id), c.pt(p2_id))
    ok = abs(d - expected) < c.tol
    return ok, "" if ok else f"|{p1_id}{p2_id}|={d:.4f} ≠ expected {expected}"


def _line_distance(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.sqrt(dx**2 + dy**2)
    if length < 1e-12:
        return 0.0
    return abs((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) / length


@register_property_type("intersects", dimension=1)
def _intersects(args, c):
    # args: [[A, B], [C, D], P] — P lies on both lines AB and CD
    A, B = c.pt(args[0][0]), c.pt(args[0][1])
    C, D = c.pt(args[1][0]), c.pt(args[1][1])
    P = c.pt(args[2])
    d1 = _line_distance(P, A, B)
    d2 = _line_distance(P, C, D)
    ok = d1 < c.tol and d2 < c.tol
    return ok, "" if ok else f"P not at intersection: d_to_AB={d1:.4f}, d_to_CD={d2:.4f}"


@register_property_type("equidistant_from_sides", dimension=1)
def _equidistant_from_sides(args, c):
    # args: [I, A, B, C] — I equidistant from sides AB, BC, CA
    I = c.pt(args[0])
    A, B, C = c.pt(args[1]), c.pt(args[2]), c.pt(args[3])
    d_ab = _line_distance(I, A, B)
    d_bc = _line_distance(I, B, C)
    d_ca = _line_distance(I, C, A)
    ok = abs(d_ab - d_bc) < c.tol and abs(d_bc - d_ca) < c.tol
    return ok, "" if ok else (
        f"distances to sides not equal: AB={d_ab:.4f}, BC={d_bc:.4f}, CA={d_ca:.4f}"
    )


@register_property_type("centroid", dimension=1)
def _centroid(args, c):
    # args: [G, A, B, C] — G is centroid of triangle ABC
    G = c.pt(args[0])
    A, B, C = c.pt(args[1]), c.pt(args[2]), c.pt(args[3])
    cx = (A[0] + B[0] + C[0]) / 3
    cy = (A[1] + B[1] + C[1]) / 3
    d = math.sqrt((G[0] - cx)**2 + (G[1] - cy)**2)
    ok = d < c.tol
    return ok, "" if ok else f"{args[0]} not at centroid: dist={d:.4f}"


def _side_crosses(args, c) -> tuple[float, float]:
    P, Q = c.pt(args[0]), c.pt(args[1])
    A, B = c.pt(args[2]), c.pt(args[3])
    dx, dy = B[0] - A[0], B[1] - A[1]
    return (dx * (P[1] - A[1]) - dy * (P[0] - A[0]), dx * (Q[1] - A[1]) - dy * (Q[0] - A[0]))


@register_property_type("opposite_side", dimension=0)
def _opposite_side(args, c):
    # args: [P, Q, A, B] — P and Q on opposite sides of line AB. ``tol`` is a required
    # margin on the product of the two signed cross products, so a larger one is stricter.
    cross_p, cross_q = _side_crosses(args, c)
    ok = cross_p * cross_q < -c.tol
    return ok, "" if ok else (
        f"{args[0]} and {args[1]} not on opposite sides of line {args[2]}-{args[3]}"
    )


@register_property_type("same_side", dimension=0)
def _same_side(args, c):
    # args: [P, Q, A, B] — P and Q on the same side of line AB (``tol`` a required margin)
    cross_p, cross_q = _side_crosses(args, c)
    ok = cross_p * cross_q > c.tol
    return ok, "" if ok else (
        f"{args[0]} and {args[1]} not on same side of line {args[2]}-{args[3]}"
    )


@register_property_type("not_between", dimension=0)
def _not_between(args, c):
    # args: [D, B, C] — D is on line BC but NOT between B and C (``tol`` a required margin
    # on the unit fraction t along BC)
    D = c.pt(args[0])
    B = c.pt(args[1])
    C = c.pt(args[2])
    dx, dy = C[0] - B[0], C[1] - B[1]
    length_sq = dx**2 + dy**2
    if length_sq < 1e-24:
        return False, "Degenerate segment"
    # project D onto BC: t = dot(D-B, C-B) / |C-B|^2
    t = ((D[0] - B[0]) * dx + (D[1] - B[1]) * dy) / length_sq
    ok = t < -c.tol or t > 1 + c.tol
    return ok, "" if ok else f"{args[0]} is between {args[1]} and {args[2]} (t={t:.4f})"


# ---------------------------------------------------------------------------
# Rendering-only, prism and stack properties
# ---------------------------------------------------------------------------

def _rendering_only(args, c):
    return True, "(skipped: rendering-only check)"


register_property_type("label_present", _rendering_only, family="render")
register_property_type("mark_present", _rendering_only, family="render")

# Evaluated on the full compiled symbol table through query_prism / query_stack
# (evals/sympy_checks.py _validate_prism_properties / _validate_stack_properties).
# prism_volume args [prism_id | "*", volume]; prism_dimensions [prism_id | "*", length,
# width, height]; stack_cube_count [stack_id | "*", count]; stack_extents [stack_id | "*",
# length, width, height] (ints); stack_is_height_map [stack_id | "*", bool].
register_property_type("prism_volume", family="prism")
register_property_type("prism_dimensions", family="prism")
register_property_type("stack_cube_count", family="stack", validate_args=_validate_stack_cube_count_args)
register_property_type("stack_extents", family="stack", validate_args=_validate_stack_extents_args)
register_property_type("stack_is_height_map", family="stack", validate_args=_validate_stack_is_height_map_args)

# ---------------------------------------------------------------------------
# Structural checks, run on the authored IR (or the TikZ source)
# ---------------------------------------------------------------------------

# IR def kinds that are solids (counted by solid_count, never by polygon_count).
_SOLID_KINDS = frozenset({"rectangular_prism", "block_stack"})


def _authored_cube_count(defn: dict) -> int | None:
    """Cube count of an authored block_stack def, from its literal heights
    (sum of non-negative integers) or cubes (number of triples). Literal-only,
    like the solid_count dimensions: it reads the authored IR, so the check
    needs no compile, and an expression/ragged/non-integer value is None
    (never matches). The compiled Stack's count is checked separately by the
    stack_cube_count property."""
    heights, cubes = defn.get("heights"), defn.get("cubes")
    def is_int(v):
        # Same integer-entry rule as ir.stack._integer_entry: ints and integral
        # finite floats (2.0) are accepted; bools and non-integral values are not.
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return False
        return math.isfinite(v) and float(v) == int(v)
    if defn.get("kind") != "block_stack":
        return None
    if isinstance(heights, list) and cubes is None:
        if all(isinstance(r, list) and all(is_int(v) and v >= 0 for v in r) for r in heights):
            return sum(int(v) for r in heights for v in r)
        return None
    if isinstance(cubes, list) and heights is None:
        return len(cubes)
    return None


_UNSUPPORTED_MESSAGE = "(skipped: check type not supported by this build)"


def _eval_polygon_count(args: dict, diagram_ir: dict | None, tikz_code: str | None) -> dict:
    """polygon_count — at least N authored 2D plane polygons (polygon,
    polygon_exterior, triangle defs) with a given side count. Prisms never
    count: a prism is one rectangular_prism def, its derived faces never
    appear in the authored IR."""
    min_count = int(args.get("min", 1))
    sides = args.get("sides")  # None means any polygon
    count = 0
    if diagram_ir is not None:
        # Count Polygon, PolygonExterior, and Triangle defs in IR
        for defn in diagram_ir.get("define", []):
            kind = defn.get("kind")
            if kind == "polygon":
                n = len(defn.get("points", []))
            elif kind == "polygon_exterior":
                n = defn.get("sides", 4)
            elif kind == "triangle":
                n = 3
            else:
                continue
            if sides is None or n == sides:
                count += 1
    elif tikz_code is not None:
        # Fallback: count \tkzDrawPolygon / \tkzFillPolygon in TikZ
        import re as _re
        for m in _re.finditer(r'\\tkz(?:Draw|Fill)Polygon\(([^)]*)\)', tikz_code):
            pts = [p.strip() for p in m.group(1).split(",") if p.strip()]
            if sides is None or len(pts) == sides:
                count += 1
    ok = count >= min_count
    msg = "" if ok else (
        f"expected at least {min_count} polygon(s) with "
        f"{'any' if sides is None else sides} sides, found {count}"
    )
    return {"passed": ok, "message": msg}


def _eval_solid_count(args: dict, diagram_ir: dict | None, tikz_code: str | None) -> dict:
    """solid_count — at least ``min`` (default 1) authored solids, optionally
    only those of ``kind`` (e.g. rectangular_prism) and whose literal
    length/width/height equal the given values (an expression-valued
    dimension never matches) and, for block_stack, whose literal cube
    count (sum of heights or number of cubes) equals ``cube_count``.
    Needs the authored IR."""
    min_count = int(args.get("min", 1))
    kind = args.get("kind")
    dims = {d: args[d] for d in ("length", "width", "height") if d in args}
    want_cubes = args.get("cube_count")
    if diagram_ir is None:
        return {"passed": False, "message": "solid_count needs the authored IR (none available)"}
    count = 0
    for defn in diagram_ir.get("define", []):
        dkind = defn.get("kind")
        if dkind not in _SOLID_KINDS or (kind is not None and dkind != kind):
            continue
        if want_cubes is not None and _authored_cube_count(defn) != want_cubes:
            continue
        if all(
            isinstance(defn.get(d), (int, float))
            and not isinstance(defn.get(d), bool)
            and defn[d] == v
            for d, v in dims.items()
        ):
            count += 1
    ok = count >= min_count
    desc = (kind or "any kind") + (f" {dims}" if dims else "") + (
        f" cube_count={want_cubes}" if want_cubes is not None else ""
    )
    return {
        "passed": ok,
        "message": "" if ok else f"expected at least {min_count} solid(s) ({desc}), found {count}",
    }


register_structural_type("polygon_count", _eval_polygon_count)
register_structural_type("solid_count", _eval_solid_count, validate_args=_validate_solid_count_args)
