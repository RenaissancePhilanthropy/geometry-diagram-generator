# recipe/solve.py
"""Triangle constraint solver.

Converts a triangle `spec` dict into concrete vertex coordinates (x, y).
Supports AAS, SAS, SSS, ASA, and right_angle_at+two_sides.
SSA is explicitly not supported (raises SpecError).

Layout: vertex[0] at origin on positive x-axis, vertex[1] at (side_AB, 0),
vertex[2] above x-axis. Then translate so centroid ≈ (2, 2).
"""
from __future__ import annotations

import math
from typing import Any


class SpecError(ValueError):
    """Raised when the triangle spec is invalid or insufficient."""


_TOL = 1e-9


def solve_triangle(
    vertices: list[str],
    spec: dict[str, Any],
) -> dict[str, tuple[float, float]]:
    """Solve triangle spec to concrete (x, y) coordinates.

    Args:
        vertices: List of 3 vertex name strings, e.g. ["A","B","C"].
        spec: Dict with angle/side constraints (see spec combinations).

    Returns:
        Dict mapping vertex name → (x, y) float pair.

    Raises:
        SpecError: If the spec is invalid, ambiguous, or unsupported (SSA).
    """
    v0, v1, v2 = vertices[0], vertices[1], vertices[2]

    # Helper: side key for two vertices (order-independent)
    def _side(*names: str) -> str:
        return "side_" + "".join(names)

    # Helper: angle key for vertex
    def _ang(name: str) -> str:
        return "angle_" + name

    # -------------------------------------------------------------------
    # Attempt each supported combination in priority order
    # -------------------------------------------------------------------

    # right_angle_at + two adjacent sides
    if "right_angle_at" in spec:
        return _solve_right_angle_at(vertices, spec)

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

    # --- SSS ---
    if n_sides == 3 and n_angles == 0:
        ab = _get_side(v0, v1)
        bc = _get_side(v1, v2)
        ca = _get_side(v2, v0)
        if None in (ab, bc, ca):
            raise SpecError(f"SSS spec requires side_{v0}{v1}, side_{v1}{v2}, side_{v2}{v0}")
        return _sss(v0, v1, v2, ab, bc, ca)

    # --- AAS: two angles + one side ---
    if n_angles == 2 and n_sides == 1:
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
        # Identify the two vertices of this side
        if len(side_key) != 2:
            raise SpecError(f"Unexpected side key {side_key!r}; expected two vertex names")
        sv0, sv1 = side_key[0], side_key[1]
        # Law of sines: side / sin(opposite_angle) = constant
        # Use the given side to derive the other two
        opp_angle = all_angles.get(
            next(v for v in vertices if v != sv0 and v != sv1), None
        )
        if opp_angle is None:
            raise SpecError(f"Cannot find angle opposite to side {side_key}")
        return _aas_via_law_of_sines(v0, v1, v2, all_angles, sv0, sv1, float(side_val), opp_angle)

    # --- ASA: two angles + enclosed side ---
    # (same data shape as AAS — handled above)

    # --- SAS vs SSA: one angle + two sides ---
    if n_angles == 1 and n_sides == 2:
        ang_vertex, ang_val = list(angles.items())[0]
        ang_val = float(ang_val)
        # Find the two sides meeting at ang_vertex
        other_verts = [v for v in vertices if v != ang_vertex]
        s1 = _get_side(ang_vertex, other_verts[0])
        s2 = _get_side(ang_vertex, other_verts[1])
        if None in (s1, s2):
            # One or both sides don't meet ang_vertex → SSA (ambiguous)
            raise SpecError(
                "SSA (two sides + non-included angle) is ambiguous; "
                "use AAS, SAS, SSS, or ASA instead"
            )
        return _sas(v0, v1, v2, ang_vertex, ang_val, other_verts[0], s1, other_verts[1], s2)

    raise SpecError(
        f"Cannot determine triangle from spec {spec!r}. "
        "Supported: AAS, SAS, SSS, ASA, right_angle_at+two_sides."
    )


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

    ab = sides.get((v0, v1)) or sides.get((v1, v0))
    bc = sides.get((v1, v2)) or sides.get((v2, v1))
    ca = sides.get((v2, v0)) or sides.get((v0, v2))
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
    verts = [v0, v1, v2]
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
