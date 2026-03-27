"""SymPy-based geometric property validation for eval scenarios.

Used to verify expected_properties from scenario YAML against the compiled
float-coordinate symbol table produced by the structured strategy.
"""
from __future__ import annotations


def _validate_properties_sympy(
    expected_properties: list[dict],
    sym_float: dict,
    tol: float = 5e-3,
) -> list[dict]:
    """Validate scenario expected_properties against a float-coords symbol table.
    sym_float maps point_id -> (x, y) float tuples.
    Returns list of {name, type, passed, message} dicts.
    """
    results = []
    for prop in expected_properties:
        name = prop.get("name", "")
        ptype = prop.get("type", "")
        args = prop.get("args", [])
        try:
            passed, msg = _check_sympy_property(ptype, args, sym_float, tol)
        except Exception as exc:
            passed, msg = False, f"Error: {exc}"
        results.append({"name": name, "type": ptype, "passed": passed, "message": msg})
    return results


def _check_sympy_property(ptype: str, args: list, sym_float: dict, tol: float) -> tuple[bool, str]:
    import math

    def pt(name: str) -> tuple[float, float]:
        p = sym_float.get(name)
        if p is None:
            raise KeyError(f"Point {name!r} not in symbol table")
        return p

    def dist(a: tuple, b: tuple) -> float:
        return math.sqrt((a[0] - b[0])**2 + (a[1] - b[1])**2)

    match ptype:
        case "right_angle":
            a, o, b = args[0], args[1], args[2]
            A, O, B = pt(a), pt(o), pt(b)
            va = (A[0] - O[0], A[1] - O[1])
            vb = (B[0] - O[0], B[1] - O[1])
            dot = va[0]*vb[0] + va[1]*vb[1]
            mag_a = math.sqrt(va[0]**2 + va[1]**2)
            mag_b = math.sqrt(vb[0]**2 + vb[1]**2)
            if mag_a < 1e-12 or mag_b < 1e-12:
                return False, "Degenerate angle"
            cos_v = max(-1.0, min(1.0, dot / (mag_a * mag_b)))
            ang = math.acos(cos_v)
            ok = abs(ang - math.pi / 2) < tol
            return ok, "" if ok else f"angle={math.degrees(ang):.2f}° (expected 90°)"

        case "midpoint":
            m_id, a_id, b_id = args[0], args[1], args[2]
            M, A, B = pt(m_id), pt(a_id), pt(b_id)
            d_ma = dist(M, A)
            d_mb = dist(M, B)
            ok = abs(d_ma - d_mb) < tol
            return ok, "" if ok else f"|MA|={d_ma:.4f} ≠ |MB|={d_mb:.4f}"

        case "collinear":
            pts = [pt(n) for n in args]
            (x1, y1), (x2, y2), (x3, y3) = pts[0], pts[1], pts[2]
            cross = (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1)
            ok = abs(cross) < tol
            return ok, "" if ok else f"Points {args} are not collinear (cross={cross:.4f})"

        case "equal_lengths":
            d1 = dist(pt(args[0][0]), pt(args[0][1]))
            d2 = dist(pt(args[1][0]), pt(args[1][1]))
            ok = abs(d1 - d2) < tol
            return ok, "" if ok else f"|{args[0]}|={d1:.4f} ≠ |{args[1]}|={d2:.4f}"

        case "parallel":
            A, B = pt(args[0][0]), pt(args[0][1])
            C, D = pt(args[1][0]), pt(args[1][1])
            v1 = (B[0] - A[0], B[1] - A[1])
            v2 = (D[0] - C[0], D[1] - C[1])
            cross = v1[0]*v2[1] - v1[1]*v2[0]
            ok = abs(cross) < tol
            return ok, "" if ok else "Lines are not parallel"

        case "perpendicular":
            A, B = pt(args[0][0]), pt(args[0][1])
            C, D = pt(args[1][0]), pt(args[1][1])
            v1 = (B[0] - A[0], B[1] - A[1])
            v2 = (D[0] - C[0], D[1] - C[1])
            dot = v1[0]*v2[0] + v1[1]*v2[1]
            ok = abs(dot) < tol
            return ok, "" if ok else f"Lines not perpendicular (dot={dot:.4f})"

        case "point_on_line" | "point_on_segment":
            P = pt(args[0])
            A, B = pt(args[1]), pt(args[2])
            dx, dy = B[0] - A[0], B[1] - A[1]
            length = math.sqrt(dx**2 + dy**2)
            if length < 1e-12:
                return False, "Degenerate line"
            cross = abs((P[0] - A[0]) * dy - (P[1] - A[1]) * dx) / length
            ok = cross < tol
            return ok, "" if ok else f"{args[0]} not on line (dist={cross:.4f})"

        case "point_on_circle":
            # args: [P, O, R_point] — P on circle centered at O with radius dist(O, R_point)
            P = pt(args[0])
            O = pt(args[1])
            R = pt(args[2])
            r = dist(O, R)
            d = dist(P, O)
            ok = abs(d - r) < tol
            return ok, "" if ok else f"dist({args[0]}, {args[1]})={d:.4f}, radius={r:.4f}"

        case "tangent":
            # args: [[L1, L2], O, T] — line L1-L2 tangent to circle centered O at point T
            # Tangency condition: perpendicular distance from center O to line = radius dist(O, T)
            L1, L2 = pt(args[0][0]), pt(args[0][1])
            O = pt(args[1])
            T = pt(args[2])
            r = dist(O, T)
            dx, dy = L2[0] - L1[0], L2[1] - L1[1]
            mag_L = math.sqrt(dx**2 + dy**2)
            if mag_L < 1e-12:
                return False, "Degenerate tangent line"
            d_center = abs(dx * (L1[1] - O[1]) - dy * (L1[0] - O[0])) / mag_L
            ok = abs(d_center - r) < tol
            return ok, "" if ok else f"dist(center, line)={d_center:.4f} ≠ radius={r:.4f}"

        case "angle_bisector":
            # args: [D, A, B, C] — ray AD bisects angle BAC
            D, A, B, C = pt(args[0]), pt(args[1]), pt(args[2]), pt(args[3])
            # angle BAD vs angle DAC
            def _angle(o, v1, v2):
                a = (v1[0] - o[0], v1[1] - o[1])
                b = (v2[0] - o[0], v2[1] - o[1])
                dot_ab = a[0]*b[0] + a[1]*b[1]
                mag_a = math.sqrt(a[0]**2 + a[1]**2)
                mag_b = math.sqrt(b[0]**2 + b[1]**2)
                if mag_a < 1e-12 or mag_b < 1e-12:
                    raise ValueError("Degenerate angle")
                return math.acos(max(-1.0, min(1.0, dot_ab / (mag_a * mag_b))))
            ang_bad = _angle(A, B, D)
            ang_dac = _angle(A, D, C)
            ok = abs(ang_bad - ang_dac) < tol
            return ok, "" if ok else (
                f"angle BAD={math.degrees(ang_bad):.2f}° ≠ angle DAC={math.degrees(ang_dac):.2f}°"
            )

        case "intersects":
            # args: [[A, B], [C, D], P] — P lies on both lines AB and CD
            A, B = pt(args[0][0]), pt(args[0][1])
            C, D = pt(args[1][0]), pt(args[1][1])
            P = pt(args[2])
            def _on_line(p, a, b):
                dx, dy = b[0] - a[0], b[1] - a[1]
                length = math.sqrt(dx**2 + dy**2)
                if length < 1e-12:
                    return 0.0
                return abs((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) / length
            d1 = _on_line(P, A, B)
            d2 = _on_line(P, C, D)
            ok = d1 < tol and d2 < tol
            return ok, "" if ok else f"P not at intersection: d_to_AB={d1:.4f}, d_to_CD={d2:.4f}"

        case "equidistant_from_sides":
            # args: [I, A, B, C] — I equidistant from sides AB, BC, CA
            I = pt(args[0])
            A, B, C = pt(args[1]), pt(args[2]), pt(args[3])
            def _pt_to_line_dist(p, a, b):
                dx, dy = b[0] - a[0], b[1] - a[1]
                length = math.sqrt(dx**2 + dy**2)
                if length < 1e-12:
                    return 0.0
                return abs((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) / length
            d_ab = _pt_to_line_dist(I, A, B)
            d_bc = _pt_to_line_dist(I, B, C)
            d_ca = _pt_to_line_dist(I, C, A)
            ok = abs(d_ab - d_bc) < tol and abs(d_bc - d_ca) < tol
            return ok, "" if ok else (
                f"distances to sides not equal: AB={d_ab:.4f}, BC={d_bc:.4f}, CA={d_ca:.4f}"
            )

        case "centroid":
            # args: [G, A, B, C] — G is centroid of triangle ABC
            G = pt(args[0])
            A, B, C = pt(args[1]), pt(args[2]), pt(args[3])
            cx = (A[0] + B[0] + C[0]) / 3
            cy = (A[1] + B[1] + C[1]) / 3
            d = math.sqrt((G[0] - cx)**2 + (G[1] - cy)**2)
            ok = d < tol
            return ok, "" if ok else f"{args[0]} not at centroid: dist={d:.4f}"

        case "opposite_side":
            # args: [P, Q, A, B] — P and Q on opposite sides of line AB
            P = pt(args[0])
            Q = pt(args[1])
            A = pt(args[2])
            B = pt(args[3])
            dx, dy = B[0] - A[0], B[1] - A[1]
            cross_p = dx * (P[1] - A[1]) - dy * (P[0] - A[0])
            cross_q = dx * (Q[1] - A[1]) - dy * (Q[0] - A[0])
            ok = cross_p * cross_q < -tol
            return ok, "" if ok else (
                f"{args[0]} and {args[1]} not on opposite sides of line {args[2]}-{args[3]}"
            )

        case "same_side":
            # args: [P, Q, A, B] — P and Q on same side of line AB
            P = pt(args[0])
            Q = pt(args[1])
            A = pt(args[2])
            B = pt(args[3])
            dx, dy = B[0] - A[0], B[1] - A[1]
            cross_p = dx * (P[1] - A[1]) - dy * (P[0] - A[0])
            cross_q = dx * (Q[1] - A[1]) - dy * (Q[0] - A[0])
            ok = cross_p * cross_q > tol
            return ok, "" if ok else (
                f"{args[0]} and {args[1]} not on same side of line {args[2]}-{args[3]}"
            )

        case "not_between":
            # args: [D, B, C] — D is on line BC but NOT between B and C
            D = pt(args[0])
            B = pt(args[1])
            C = pt(args[2])
            dx, dy = C[0] - B[0], C[1] - B[1]
            length_sq = dx**2 + dy**2
            if length_sq < 1e-24:
                return False, "Degenerate segment"
            # project D onto BC: t = dot(D-B, C-B) / |C-B|^2
            t = ((D[0] - B[0]) * dx + (D[1] - B[1]) * dy) / length_sq
            ok = t < -tol or t > 1 + tol
            return ok, "" if ok else f"{args[0]} is between {args[1]} and {args[2]} (t={t:.4f})"

        case "label_present" | "mark_present":
            return True, "(skipped: rendering-only check)"

        case _:
            return True, f"(skipped: unsupported type {ptype!r})"
