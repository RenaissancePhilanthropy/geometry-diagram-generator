# recipe/solve.py
"""Geometry constraint solvers.

Converts geometry spec dicts into concrete vertex coordinates (x, y).

Triangle solver: supports AAS, SAS, SSS, ASA, right_angle_at+two_sides, and
right-angle SSA (angle=90 with one adjacent leg and the hypotenuse, which is
uniquely determined). General SSA (non-right-angle) raises SpecError.
Layout: vertex[0] at origin on positive x-axis, vertex[1] at (side_AB, 0),
vertex[2] above x-axis. Then translate so centroid ≈ (2, 2).

Rectangle solver: lays out 4 vertices with given labeled side lengths.
Default orientation: A top-left, B top-right, C bottom-right, D bottom-left.
"""
from __future__ import annotations

import math
from typing import Any


class SpecError(ValueError):
    """Raised when the triangle spec is invalid or insufficient."""


_TOL = 1e-9


def _split_side_key(key: str, vertices: list[str]) -> tuple[str, str]:
    """Split a concatenated side key like 'AB' or 'A1B1' into two vertex names.

    Tries all prefix splits and returns the first pair where both halves are
    in the vertex list. Raises SpecError if no valid split is found.
    """
    for i in range(1, len(key)):
        sv0, sv1 = key[:i], key[i:]
        if sv0 in vertices and sv1 in vertices:
            return sv0, sv1
    raise SpecError(
        f"Side key {key!r} cannot be split into two known vertices from {vertices}"
    )


def solve_triangle(
    vertices: list[str],
    spec: dict[str, Any],
    *,
    center: tuple[float, float] | list[float] | None = None,
) -> dict[str, tuple[float, float]]:
    """Solve triangle spec to concrete (x, y) coordinates.

    Args:
        vertices: List of 3 vertex name strings, e.g. ["A","B","C"].
        spec: Dict with angle/side constraints (see spec combinations).
        center: Optional (x, y) target for the centroid. Defaults to (2, 2).

    Returns:
        Dict mapping vertex name → (x, y) float pair.

    Raises:
        SpecError: If the spec is invalid, ambiguous, or unsupported (SSA).
    """
    v0, v1, v2 = vertices[0], vertices[1], vertices[2]

    # -------------------------------------------------------------------
    # Attempt each supported combination in priority order
    # -------------------------------------------------------------------

    # right_angle_at + two adjacent sides
    if "right_angle_at" in spec:
        result = _solve_right_angle_at(vertices, spec)
    else:
        # Collect what's given
        angles = {k[len("angle_"):]: v for k, v in spec.items() if k.startswith("angle_")}
        sides_raw = {k[len("side_"):]: v for k, v in spec.items() if k.startswith("side_")}

        # Normalise side keys: sort the two vertex names alphabetically
        # so "AB" and "BA" are the same key internally.
        # We keep original keys but resolve lookups both ways.
        def _get_side(a: str, b: str) -> float | None:
            for key in (a+b, b+a):
                if key in sides_raw:
                    return float(sides_raw[key])
            return None

        n_angles = len(angles)
        n_sides  = len(sides_raw)

        # Reduce overdefined specs by dropping redundant constraints
        if n_angles == 3:
            angle_sum = sum(float(v) for v in angles.values())
            if abs(angle_sum - 180.0) > 1.0:
                raise SpecError(f"Three angles sum to {angle_sum:.1f}°, not 180°")
            if n_sides >= 1:
                # Drop any one angle — AAS path handles the remaining 2+sides
                drop = list(angles.keys())[-1]
                angles = {k: v for k, v in angles.items() if k != drop}
                n_angles = 2
            else:
                raise SpecError(
                    "Three angles but no side — AAA is underdetermined (infinitely many similar triangles)"
                )

        if n_sides == 3 and n_angles > 0:
            # All three sides given — angles are redundant, use SSS
            n_angles = 0
            angles = {}

        # --- SSS ---
        if n_sides == 3 and n_angles == 0:
            ab = _get_side(v0, v1)
            bc = _get_side(v1, v2)
            ca = _get_side(v2, v0)
            if None in (ab, bc, ca):
                raise SpecError(f"SSS spec requires side_{v0}{v1}, side_{v1}{v2}, side_{v2}{v0}")
            result = _sss(v0, v1, v2, ab, bc, ca)

        # --- AAS: two angles + one side ---
        elif n_angles == 2 and n_sides == 1:
            # Infer third angle
            given_angles = list(angles.items())
            n0, a0 = given_angles[0]
            n1, a1 = given_angles[1]
            a_third = 180.0 - float(a0) - float(a1)
            if a_third <= _TOL:
                raise SpecError(f"Angles sum to ≥180°: {a0} + {a1} = {float(a0)+float(a1)}")
            all_angles = {n0: float(a0), n1: float(a1)}
            for v in vertices:
                if v not in all_angles:
                    all_angles[v] = a_third
            # Which side?
            side_key, side_val = list(sides_raw.items())[0]
            # Identify the two vertices of this side — vertex names may be multi-character,
            # so find the split point by trying all prefix lengths.
            sv0, sv1 = _split_side_key(side_key, vertices)
            # Law of sines: side / sin(opposite_angle) = constant
            # Use the given side to derive the other two
            opp_angle = all_angles.get(
                next(v for v in vertices if v != sv0 and v != sv1), None
            )
            if opp_angle is None:
                raise SpecError(f"Cannot find angle opposite to side {side_key}")
            result = _aas_via_law_of_sines(v0, v1, v2, all_angles, sv0, sv1, float(side_val), opp_angle)

        # --- ASA: two angles + enclosed side ---
        # (same data shape as AAS — handled above)

        # --- SAS vs SSA: one angle + two sides ---
        elif n_angles == 1 and n_sides == 2:
            ang_vertex, ang_val = list(angles.items())[0]
            ang_val = float(ang_val)
            # Find the two sides meeting at ang_vertex
            other_verts = [v for v in vertices if v != ang_vertex]
            s1 = _get_side(ang_vertex, other_verts[0])
            s2 = _get_side(ang_vertex, other_verts[1])
            if None in (s1, s2):
                # One side doesn't meet ang_vertex → potential SSA.
                # Special case: if the angle is 90° and the non-adjacent side is the
                # hypotenuse (opposite ang_vertex), compute the missing leg via
                # Pythagorean theorem and reduce to right_angle_at.
                if abs(ang_val - 90.0) < _TOL:
                    hyp = _get_side(other_verts[0], other_verts[1])
                    leg = s1 if s1 is not None else s2
                    adj_vert = other_verts[0] if s1 is not None else other_verts[1]
                    missing_vert = other_verts[1] if s1 is not None else other_verts[0]
                    if hyp is not None and leg is not None:
                        if hyp <= leg:
                            raise SpecError(
                                f"right triangle: hypotenuse ({hyp}) must be longer than leg ({leg})"
                            )
                        missing_leg = math.sqrt(hyp**2 - leg**2)
                        ra_spec = {
                            "right_angle_at": ang_vertex,
                            f"side_{ang_vertex}{adj_vert}": leg,
                            f"side_{ang_vertex}{missing_vert}": missing_leg,
                        }
                        result = _solve_right_angle_at(vertices, ra_spec)
                    else:
                        raise SpecError(
                            "SSA (two sides + non-included angle) is ambiguous; "
                            "use AAS, SAS, SSS, or ASA instead"
                        )
                else:
                    # One or both sides don't meet ang_vertex → SSA (ambiguous)
                    raise SpecError(
                        "SSA (two sides + non-included angle) is ambiguous; "
                        "use AAS, SAS, SSS, or ASA instead"
                    )
            else:
                result = _sas(v0, v1, v2, ang_vertex, ang_val, other_verts[0], s1, other_verts[1], s2)

        else:
            raise SpecError(
                f"Cannot determine triangle from spec {spec!r}. "
                "Supported: AAS, SAS, SSS, ASA, right_angle_at+two_sides."
            )

    # Apply custom centroid placement if requested
    if center is not None:
        cx_target, cy_target = float(center[0]), float(center[1])
        xs = [p[0] for p in result.values()]
        ys = [p[1] for p in result.values()]
        dx = cx_target - sum(xs) / 3
        dy = cy_target - sum(ys) / 3
        result = {k: (x + dx, y + dy) for k, (x, y) in result.items()}

    return result


# ---------------------------------------------------------------------------
# Solvers
# ---------------------------------------------------------------------------

def _layout(v0: str, v1: str, v2: str, A: tuple, B: tuple, C: tuple) -> dict:
    """Translate so centroid ≈ (2, 2)."""
    cx = (A[0]+B[0]+C[0]) / 3
    cy = (A[1]+B[1]+C[1]) / 3
    dx, dy = 2.0 - cx, 2.0 - cy
    return {
        v0: (A[0]+dx, A[1]+dy),
        v1: (B[0]+dx, B[1]+dy),
        v2: (C[0]+dx, C[1]+dy),
    }


def _sss(v0: str, v1: str, v2: str, ab: float, bc: float, ca: float) -> dict:
    # Triangle inequality
    if ab + bc <= ca + _TOL or bc + ca <= ab + _TOL or ca + ab <= bc + _TOL:
        raise SpecError(f"Triangle inequality violated: sides {ab}, {bc}, {ca}")
    # Place v0 at origin, v1 at (ab, 0)
    cos_A = (ab**2 + ca**2 - bc**2) / (2*ab*ca)
    cos_A = max(-1.0, min(1.0, cos_A))
    angle_A = math.acos(cos_A)
    Cx = ca * math.cos(angle_A)
    Cy = ca * math.sin(angle_A)
    return _layout(v0, v1, v2, (0.0, 0.0), (ab, 0.0), (Cx, Cy))


def _aas_via_law_of_sines(
    v0: str, v1: str, v2: str,
    all_angles: dict[str, float],
    sv0: str, sv1: str, side_val: float, opp_angle: float,
) -> dict:
    """Use law of sines to solve all sides, then place with SSS."""
    # side / sin(opposite) = k
    if abs(math.sin(math.radians(opp_angle))) < _TOL:
        raise SpecError(f"Degenerate: sin({opp_angle}°) ≈ 0")
    k = side_val / math.sin(math.radians(opp_angle))
    sides: dict[tuple[str,str], float] = {}
    verts = [v0, v1, v2]
    for i, va in enumerate(verts):
        vb = verts[(i+1) % 3]
        vc = verts[(i+2) % 3]  # vertex opposite edge va-vb; angle at vc
        opp = all_angles.get(vc)
        if opp is None:
            raise SpecError(f"Missing angle for vertex {vc!r}")
        sides[(va, vb)] = k * math.sin(math.radians(opp))

    ab = sides[(v0, v1)]
    bc = sides[(v1, v2)]
    ca = sides[(v2, v0)]
    return _sss(v0, v1, v2, ab, bc, ca)


def _sas(
    v0: str, v1: str, v2: str,
    ang_vertex: str, ang_val: float,
    ov0: str, s0: float,
    ov1: str, s1: float,
) -> dict:
    """SAS: angle at ang_vertex, adjacent sides s0 (to ov0) and s1 (to ov1)."""
    if ang_val <= 0 or ang_val >= 180:
        raise SpecError(f"Angle at {ang_vertex!r} must be in (0, 180), got {ang_val}")
    # Use law of cosines to find the opposite side
    opp = math.sqrt(s0**2 + s1**2 - 2*s0*s1*math.cos(math.radians(ang_val)))
    # Determine which sides are v0-v1, v1-v2, v2-v0
    # ang_vertex is one of {v0, v1, v2}; ov0 and ov1 are the other two
    side_dict: dict[frozenset, float] = {
        frozenset({ang_vertex, ov0}): s0,
        frozenset({ang_vertex, ov1}): s1,
        frozenset({ov0, ov1}): opp,
    }
    ab = side_dict.get(frozenset({v0, v1}))
    bc = side_dict.get(frozenset({v1, v2}))
    ca = side_dict.get(frozenset({v2, v0}))
    return _sss(v0, v1, v2, ab, bc, ca)


def _solve_right_angle_at(vertices: list[str], spec: dict) -> dict:
    """right_angle_at + two adjacent sides."""
    v0, v1, v2 = vertices
    ra = spec["right_angle_at"]
    if ra not in vertices:
        raise SpecError(f"right_angle_at={ra!r} is not a vertex in {vertices}")

    other = [v for v in vertices if v != ra]
    sides_raw = {k[len("side_"):]: float(v) for k, v in spec.items() if k.startswith("side_")}

    def _get(a: str, b: str) -> float | None:
        for key in (a+b, b+a):
            if key in sides_raw:
                return sides_raw[key]
        return None

    s0 = _get(ra, other[0])
    s1 = _get(ra, other[1])
    n_sides = sum(1 for s in (s0, s1) if s is not None)
    if n_sides == 0:
        # No sides given — default to legs of 3 and 4 (Pythagorean triple ratio)
        adjacent_sides = [3.0, 4.0]
        s0, s1 = adjacent_sides
    elif n_sides == 1:
        # One side given — derive the other from a fixed ratio
        given_len = s0 if s0 is not None else s1
        other_len = given_len * (4/3)
        if s0 is None:
            s0 = other_len
        else:
            s1 = other_len
    # right_angle_at + s0 (ra→other[0]) + s1 (ra→other[1])
    # Use SAS with 90°
    return _sas(v0, v1, v2, ra, 90.0, other[0], s0, other[1], s1)


# ---------------------------------------------------------------------------
# Polygon-from-sides solver
# ---------------------------------------------------------------------------

def solve_polygon_from_sides(
    vertices: list[str],
    side_lengths: list[float],
    *,
    center: tuple[float, float] | list[float] | None = None,
) -> dict[str, tuple[float, float]]:
    """Compute vertex positions for a polygon with given consecutive side lengths.

    Produces the maximum-area (cyclic) polygon.
    side_lengths[i] is the distance from vertices[i] to vertices[(i+1) % N].

    Returns dict mapping vertex name → (x, y).
    Raises SpecError if the side lengths cannot form a valid polygon.
    """
    if len(vertices) != len(side_lengths):
        raise SpecError(
            f"solve_polygon_from_sides: len(vertices)={len(vertices)} "
            f"must equal len(side_lengths)={len(side_lengths)}"
        )
    n = len(vertices)
    if n < 3:
        raise SpecError(
            f"solve_polygon_from_sides requires at least 3 vertices, got {n}"
        )
    sides = [float(s) for s in side_lengths]
    if any(s <= 0 for s in sides):
        raise SpecError(
            f"solve_polygon_from_sides: all side lengths must be positive, got {sides}"
        )
    total = sum(sides)
    if max(sides) >= total / 2:
        raise SpecError(
            f"solve_polygon_from_sides: polygon inequality violated — "
            f"max side {max(sides)} >= half-perimeter {total/2}"
        )

    # Find circumradius R by bisection on f(R) = Σ 2*arcsin(l_i/2R) - 2π = 0
    def _f(R: float) -> float:
        return sum(2 * math.asin(s / (2 * R)) for s in sides) - 2 * math.pi

    R_lo = max(sides) / 2 + 1e-9
    R_hi = total / math.pi
    while _f(R_hi) > 0:
        R_hi *= 2

    for _ in range(200):
        R_mid = (R_lo + R_hi) / 2
        if _f(R_mid) > 0:
            R_lo = R_mid
        else:
            R_hi = R_mid
        if R_hi - R_lo < 1e-12:
            break
    R = (R_lo + R_hi) / 2

    # Central angles and cumulative placement
    thetas = [2 * math.asin(s / (2 * R)) for s in sides]
    raw = []
    alpha = 0.0
    for theta in thetas:
        raw.append((R * math.cos(alpha), R * math.sin(alpha)))
        alpha += theta

    # Translate centroid to target center (default (2, 2))
    cx_target, cy_target = (float(center[0]), float(center[1])) if center is not None else (2.0, 2.0)
    cx = sum(p[0] for p in raw) / n
    cy = sum(p[1] for p in raw) / n
    dx, dy = cx_target - cx, cy_target - cy
    result = {}
    for i, name in enumerate(vertices):
        result[name] = (raw[i][0] + dx, raw[i][1] + dy)
    return result


# ---------------------------------------------------------------------------
# Rectangle solver
# ---------------------------------------------------------------------------

def solve_rectangle(
    vertices: list[str],
    spec: dict[str, Any],
    center: tuple[float, float] = (2.0, 2.0),
) -> dict[str, tuple[float, float]]:
    """Lay out a rectangle so that labeled side lengths match the spec.

    Parameters
    ----------
    vertices:
        4 corner names in perimeter order, e.g. ["A", "B", "C", "D"].
        Side AB connects vertices[0]→vertices[1]; side BC connects [1]→[2];
        sides CD and DA are the opposites.
    spec:
        Must contain exactly the two adjacent-side length keys that correspond
        to the first two edges, e.g. ``{side_AB: 4, side_BC: 3}``.
        Accepted key patterns: ``side_XY`` where XY is any two-character combo
        of the vertex names covering one adjacent pair.
        Optional: ``rotation`` (float, degrees CCW, default 0).
    center:
        (cx, cy) target for the rectangle centroid; default (2.0, 2.0).

    Returns
    -------
    dict mapping each vertex name to (x, y).

    Default layout (rotation=0): A top-left, B top-right, C bottom-right,
    D bottom-left, so ``|AB| = side_AB`` (horizontal) and ``|BC| = side_BC``
    (vertical).

    Raises
    ------
    SpecError
        If fewer than two adjacent-side lengths are specified, or if the spec
        keys don't correspond to the provided vertex names.
    """
    if len(vertices) != 4:
        raise SpecError(f"solve_rectangle requires exactly 4 vertices; got {len(vertices)}")

    v = list(vertices)
    # Extract all side_XY keys
    sides_raw: dict[str, float] = {}
    for k, val in spec.items():
        if k.startswith("side_") and len(k) == 7:
            sides_raw[k[5:]] = float(val)

    def _get_side(a: str, b: str) -> float | None:
        for key in (a + b, b + a):
            if key in sides_raw:
                return sides_raw[key]
        return None

    # Need two adjacent sides meeting at v[1] (B): AB and BC
    w = _get_side(v[0], v[1])  # side_AB  (width)
    h = _get_side(v[1], v[2])  # side_BC  (height)

    # Fall back: accept the opposite side of the same orientation
    if w is None:
        w = _get_side(v[2], v[3])
    if h is None:
        h = _get_side(v[3], v[0])

    missing = []
    if w is None:
        missing.append(f"side_{v[0]}{v[1]} (or side_{v[1]}{v[0]})")
    if h is None:
        missing.append(f"side_{v[1]}{v[2]} (or side_{v[2]}{v[1]})")
    if missing:
        raise SpecError(
            f"Rectangle spec missing required side lengths: {', '.join(missing)}. "
            f"Provide e.g. side_{v[0]}{v[1]}=<width> and side_{v[1]}{v[2]}=<height>."
        )

    rotation_deg = float(spec.get("rotation", 0.0))
    rotation_rad = rotation_deg * math.pi / 180.0

    # Default orientation: A top-left, B top-right, C bottom-right, D bottom-left
    # Width = |AB| = w, Height = |BC| = h
    half_w = w / 2.0
    half_h = h / 2.0
    raw: dict[str, tuple[float, float]] = {
        v[0]: (-half_w,  half_h),   # A top-left
        v[1]: ( half_w,  half_h),   # B top-right
        v[2]: ( half_w, -half_h),   # C bottom-right
        v[3]: (-half_w, -half_h),   # D bottom-left
    }

    if rotation_rad != 0.0:
        cos_r, sin_r = math.cos(rotation_rad), math.sin(rotation_rad)
        raw = {
            name: (x * cos_r - y * sin_r, x * sin_r + y * cos_r)
            for name, (x, y) in raw.items()
        }

    # Translate centroid to target center
    cx, cy = center
    result = {name: (x + cx, y + cy) for name, (x, y) in raw.items()}
    return result
