#!/usr/bin/env python3
"""
filter_genexam.py — Filter GenExam-Math problems by geometry relevance.

Relevance tiers (defined in RELEVANCE table below):
  HIGH    — Pure plane geometry, constructible via DSL+recipes pipeline,
            aligned with Bluebonnet 6–8 curriculum. Always included.
  MEDIUM  — Geometric content but out of primary scope. Two sub-types:
              cartesian  : shapes on coordinate axes (circles, polygons, LP regions)
              3d         : solid geometry (pyramids, prisms, cones, sections)
  LOW     — Analytic/function plots, calculus, polar/parametric, graph theory.
            Never included.

Default output: HIGH + MEDIUM cartesian  (51 + 15 = ... see below)
Flags:
  --include-3d        also include MEDIUM 3d problems
  --high-only         only HIGH problems
  --exclude-medium    same as --high-only (alias)
  --stats             print relevance breakdown and exit (no file written)

Usage:
  python filter_genexam.py input.jsonl
  python filter_genexam.py input.jsonl -o filtered.jsonl
  python filter_genexam.py input.jsonl --include-3d
  python filter_genexam.py input.jsonl --high-only
  python filter_genexam.py input.jsonl --stats
"""

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Relevance table
# Each entry: id -> (tier, sub, note)
#   tier : "HIGH" | "MEDIUM" | "LOW"
#   sub  : None | "cartesian" | "3d"   (only for MEDIUM)
#   note : short human-readable reason
# ---------------------------------------------------------------------------

RELEVANCE: dict[str, tuple[str, str | None, str]] = {
    # ── HIGH ────────────────────────────────────────────────────────────────
    # Parallel lines / transversals
    "Mathematics_72":  ("HIGH", None, "Two parallel lines + transversal — direct parallel_transversal recipe match"),
    "Mathematics_146": ("HIGH", None, "Three parallel lines + two transversals — recipe extension"),
    # Angles
    "Mathematics_71":  ("HIGH", None, "Compass construction of angle bisector"),
    "Mathematics_141": ("HIGH", None, "Taxonomy of angle types — annotation-heavy test"),
    "Mathematics_118": ("HIGH", None, "Triangle interior/exterior angles — angle annotation recipe"),
    # Circles / Chord
    "Mathematics_95":  ("HIGH", None, "Circle + two chords inside + external secant"),
    "Mathematics_94":  ("HIGH", None, "Circle + tangent + secant (power of a point)"),
    "Mathematics_101": ("HIGH", None, "Circle + two intersecting chords — basic chord intersection"),
    "Mathematics_99":  ("HIGH", None, "Circle + two intersecting chords — simpler variant"),
    "Mathematics_100": ("HIGH", None, "Circle + diameter + perpendicular chord + intersection"),
    "Mathematics_97":  ("HIGH", None, "Circle + two secants from external point"),
    "Mathematics_98":  ("HIGH", None, "Circle with diameter + equilateral triangle from midpoint"),
    "Mathematics_96":  ("HIGH", None, "Circle + intersecting chords"),
    # Circles / Inscribed & Circumscribed
    "Mathematics_103": ("HIGH", None, "Triangle + incircle + three tangent points — incircle recipe match"),
    "Mathematics_104": ("HIGH", None, "Triangle circumscribed about incircle — incircle variant"),
    "Mathematics_105": ("HIGH", None, "Isosceles triangle + incircle + chord through incenter"),
    "Mathematics_106": ("HIGH", None, "Two equal circles externally tangent + both inscribed in large circle"),
    "Mathematics_102": ("HIGH", None, "Triangle inscribed in circumcircle + perpendiculars from circumcenter"),
    # Circles / Others
    "Mathematics_109": ("HIGH", None, "Circle + diameter + chord + angle bisector — multi-feature"),
    "Mathematics_110": ("HIGH", None, "Square + inscribed circle + chord through second intersection"),
    # Circles / Tangent
    "Mathematics_111": ("HIGH", None, "Circle + tangent + secant from external — power of a point"),
    "Mathematics_113": ("HIGH", None, "Two circles + common external tangent + point distances"),
    "Mathematics_112": ("HIGH", None, "Two circles + two tangents from external point each"),
    # Complex geometry
    "Mathematics_90":  ("HIGH", None, "Square + perpendicular segments + midpoints + circle"),
    "Mathematics_77":  ("HIGH", None, "Isosceles right triangle + attached square — triangle+polygon recipe"),
    "Mathematics_74":  ("HIGH", None, "Rhombus with diagonals + perpendicular foot — rhombus recipe candidate"),
    "Mathematics_73":  ("HIGH", None, "Parallelogram + angle bisector intersecting opposite side"),
    "Mathematics_75":  ("HIGH", None, "Parallelogram + midpoint + diagonal intersection — ratio/midpoint recipe"),
    "Mathematics_80":  ("HIGH", None, "Square + midpoints + intersecting cevians"),
    "Mathematics_84":  ("HIGH", None, "Right triangle + two perpendiculars from base points to legs"),
    "Mathematics_82":  ("HIGH", None, "Rectangle + diagonal + reflected variable point"),
    "Mathematics_83":  ("HIGH", None, "Right triangle + 30° rotation of a side — rotation op test"),
    "Mathematics_87":  ("HIGH", None, "Cyclic quadrilateral in circle + arc ratio + midpoint of side"),
    "Mathematics_81":  ("HIGH", None, "Circle + chord⊥diameter + tangent + parallel line — multi-feature"),
    "Mathematics_85":  ("HIGH", None, "Circle + tangent + rhombus construction"),
    "Mathematics_88":  ("HIGH", None, "Rectangle + circle at vertex + tangent from opposite corner"),
    "Mathematics_79":  ("HIGH", None, "Right triangle + square attached to leg — existing recipe pattern"),
    "Mathematics_78":  ("HIGH", None, "Right triangle + parallelogram attached to leg"),
    "Mathematics_86":  ("HIGH", None, "Right triangle + reflection across hypotenuse — reflection op test"),
    "Mathematics_93":  ("HIGH", None, "Square + perpendicular from vertex to interior segment"),
    "Mathematics_89":  ("HIGH", None, "Triangle + 2:1 ratio point + midpoint + cevian intersection"),
    "Mathematics_91":  ("HIGH", None, "Circle + diameter + midpoint + perpendicular chord"),
    "Mathematics_92":  ("HIGH", None, "Rectangle + perpendicular + circumcircle + variable point"),
    "Mathematics_76":  ("HIGH", None, "Two triangles sharing a side with angle constraints"),
    # Polygons
    "Mathematics_51":  ("HIGH", None, "Regular octagon with labeled vertices"),
    "Mathematics_151": ("HIGH", None, "L-shaped polygon (n×n minus corner square)"),
    "Mathematics_54":  ("HIGH", None, "Pentagon with labeled interior angle values"),
    "Mathematics_66":  ("HIGH", None, "Regular hexagon + midpoints + quadrilateral construction"),
    # Quadrilaterals
    "Mathematics_56":  ("HIGH", None, "Quadrilateral with diagonals bisecting at midpoints + angle labels"),
    "Mathematics_145": ("HIGH", None, "Cyclic quadrilateral inscribed in circle with side lengths"),
    "Mathematics_137": ("HIGH", None, "Coordinate-grid quadrilateral with shaded interior — simple polygon"),
    "Mathematics_55":  ("HIGH", None, "Quadrilateral with angle labels at vertices and diagonal intersection"),
    "Mathematics_57":  ("HIGH", None, "Quadrilateral with diagonal brace + angle labels"),
    # Parallelograms
    "Mathematics_52":  ("HIGH", None, "Parallelogram + projections of vertices onto diagonal"),
    "Mathematics_53":  ("HIGH", None, "Parallelogram + diagonals + projections onto diagonal"),
    # Rectangles / squares
    "Mathematics_65":  ("HIGH", None, "L-shaped octagon, all right angles, labeled sides"),
    "Mathematics_63":  ("HIGH", None, "Square (baseball diamond) + perpendicular to diagonal"),
    "Mathematics_62":  ("HIGH", None, "Rectangle with annotated corner-segment marks"),
    "Mathematics_59":  ("HIGH", None, "Rectangle with inscribed rotated square — complex constraint set"),
    "Mathematics_61":  ("HIGH", None, "Square + two segments intersecting at right angle"),
    "Mathematics_60":  ("HIGH", None, "Square + exterior point with angle annotation"),
    "Mathematics_64":  ("HIGH", None, "L-shaped hexagon, all right angles, labeled sides"),
    "Mathematics_144": ("HIGH", None, "Square + four interior points + parallel segments — annotation stress test"),
    "Mathematics_147": ("HIGH", None, "Square + exterior semicircle + tangent circle construction"),
    # Trapezoids
    "Mathematics_69":  ("HIGH", None, "Isosceles trapezoid with labeled vertices — basic trapezoid recipe"),
    "Mathematics_68":  ("HIGH", None, "Isosceles trapezoid + points on diagonal with perpendicular constraints"),
    "Mathematics_67":  ("HIGH", None, "Right-angle trapezoid with angle constraint"),
    # Triangles
    "Mathematics_120": ("HIGH", None, "Right triangle + point on hypotenuse + perpendicular foot"),
    "Mathematics_121": ("HIGH", None, "Collinear vertical points + triangle with angle markers"),
    "Mathematics_122": ("HIGH", None, "Right triangle + small square inscribed at right-angle vertex"),
    "Mathematics_119": ("HIGH", None, "Vertical collinear points + right-angle triangle with markers"),
    "Mathematics_124": ("HIGH", None, "Triangle + altitude from vertex — altitude recipe"),
    "Mathematics_114": ("HIGH", None, "Perpendicular bisectors of two sides + circumcircle — circumcircle recipe"),
    "Mathematics_115": ("HIGH", None, "Two nested similar isosceles triangles — similarity recipe"),
    "Mathematics_116": ("HIGH", None, "Triangle + parallel line cutting two sides — parallel/similarity recipe"),
    "Mathematics_117": ("HIGH", None, "Two congruent triangles labeled for correspondence"),
    "Mathematics_123": ("HIGH", None, "Two angle bisectors + their intersection — angle bisector recipe"),

    # ── MEDIUM / cartesian ─────────────────────────────────────────────────
    # Circles / shapes placed on coordinate axes — geometric but Cartesian context
    "Mathematics_13":  ("MEDIUM", "cartesian", "Circle on coordinate plane"),
    "Mathematics_15":  ("MEDIUM", "cartesian", "Ellipse on coordinate plane"),
    "Mathematics_9":   ("MEDIUM", "cartesian", "Two circles + sector on coordinate plane"),
    "Mathematics_12":  ("MEDIUM", "cartesian", "Circle + line segment + point on coordinates"),
    "Mathematics_18":  ("MEDIUM", "cartesian", "Circle + rectangle + segment on coordinates"),
    "Mathematics_14":  ("MEDIUM", "cartesian", "Circle + square + segment on coordinates"),
    "Mathematics_17":  ("MEDIUM", "cartesian", "Ellipse + pentagon on coordinates — hybrid"),
    "Mathematics_143": ("MEDIUM", "cartesian", "Lines on coordinate plane forming a rectangle"),
    "Mathematics_25":  ("LOW", None, "Linear programming feasible region — inequality region, out of scope"),
    "Mathematics_26":  ("LOW", None, "Linear programming feasible region — inequality region, out of scope"),
    # Edge-case plane geometry
    "Mathematics_70":  ("MEDIUM", "cartesian", "Five rays from vertex, complex multi-angle labeling"),
    "Mathematics_58":  ("MEDIUM", "cartesian", "Square folded so vertex touches edge — origami geometry"),
    "Mathematics_108": ("MEDIUM", "cartesian", "N semicircles along diameter — variable N makes generalization harder"),
    "Mathematics_107": ("MEDIUM", "cartesian", "24 sectors rearranged to approximate rectangle — conceptual"),
    "Mathematics_150": ("MEDIUM", "cartesian", "Seven circles packed in minimum containing circle — packing"),
    "Mathematics_148": ("MEDIUM", "cartesian", "Cone net (2D unfolding of 3D shape)"),

    # ── MEDIUM / 3d ────────────────────────────────────────────────────────
    "Mathematics_127": ("MEDIUM", "3d", "Regular tetrahedron with colored edges"),
    "Mathematics_126": ("MEDIUM", "3d", "Square pyramid with slant height labeled"),
    "Mathematics_129": ("MEDIUM", "3d", "Inverted cone + variable cross-section"),
    "Mathematics_131": ("MEDIUM", "3d", "Cone + cross-section at height h"),
    "Mathematics_128": ("MEDIUM", "3d", "Cone labeled r/h/s — basic 3D annotation"),
    "Mathematics_130": ("MEDIUM", "3d", "Two cones with liquid surfaces"),
    "Mathematics_132": ("MEDIUM", "3d", "Non-right hexagonal prism"),
    "Mathematics_133": ("MEDIUM", "3d", "Right prism with trapezoidal base"),
    "Mathematics_125": ("MEDIUM", "3d", "Sphere + cylinder + tangent planes"),
    "Mathematics_134": ("MEDIUM", "3d", "Two intersecting planes + perpendicular line"),
    "Mathematics_135": ("MEDIUM", "3d", "Three planes + line through all"),

    # ── LOW ───────────────────────────────────────────────────────────────
    "Mathematics_45":  ("LOW", None, "Area between y=x² and y=x³ — calculus"),
    "Mathematics_40":  ("LOW", None, "Area between parabola and line — calculus"),
    "Mathematics_44":  ("LOW", None, "Area bounded by two curves and x-axis — calculus"),
    "Mathematics_39":  ("LOW", None, "Area under √x+√y=1 — calculus"),
    "Mathematics_48":  ("LOW", None, "Area between x=-y² and y=x+6 — calculus"),
    "Mathematics_46":  ("LOW", None, "Area between y=(x-1)³ and x-axis — calculus"),
    "Mathematics_42":  ("LOW", None, "Regions for function crossing x-axis — calculus"),
    "Mathematics_47":  ("LOW", None, "Area between sin curve and cubic — calculus"),
    "Mathematics_50":  ("LOW", None, "Area between parabola and cosine curve — calculus"),
    "Mathematics_43":  ("LOW", None, "Three enclosed regions A/B/C — calculus"),
    "Mathematics_49":  ("LOW", None, "Mean value theorem illustration — calculus"),
    "Mathematics_41":  ("LOW", None, "Rational function with asymptote — calculus"),
    "Mathematics_32":  ("LOW", None, "Piecewise linear function — function plot"),
    "Mathematics_34":  ("LOW", None, "Periodic piecewise linear function — function plot"),
    "Mathematics_35":  ("LOW", None, "f'(x) with line segments + semicircle — function plot"),
    "Mathematics_136": ("LOW", None, "Piecewise function with multiple segment types — function plot"),
    "Mathematics_36":  ("LOW", None, "Piecewise function with semicircle component — function plot"),
    "Mathematics_37":  ("LOW", None, "Piecewise f'(x) derivative graph — function plot"),
    "Mathematics_38":  ("LOW", None, "Two piecewise linear functions on same axes — function plot"),
    "Mathematics_33":  ("LOW", None, "Piecewise function with open/closed circles — function plot"),
    "Mathematics_31":  ("LOW", None, "Cubic + quadratic on same axes with shaded region — analytic"),
    "Mathematics_29":  ("LOW", None, "Quadratic + tangent line — analytic"),
    "Mathematics_138": ("LOW", None, "Region bounded by parabola and line — analytic"),
    "Mathematics_30":  ("LOW", None, "Parabola + line shaded intersection — analytic"),
    "Mathematics_28":  ("LOW", None, "y=√x with secant from origin — analytic"),
    "Mathematics_27":  ("LOW", None, "Two curves with labeled regions R and S — analytic"),
    "Mathematics_3":   ("LOW", None, "Generic continuous function with slope signs — calculus sketch"),
    "Mathematics_4":   ("LOW", None, "y=3x/(x³+1) with region R — calculus"),
    "Mathematics_8":   ("LOW", None, "y=3sin(2x+6) with extrema — trig function plot"),
    "Mathematics_10":  ("LOW", None, "y=2log₁₀(x+3) — logarithm function plot"),
    "Mathematics_11":  ("LOW", None, "y=log₁₀(2x+3) — logarithm function plot"),
    "Mathematics_16":  ("LOW", None, "y=3tan(x+4) with asymptotes — trig function plot"),
    "Mathematics_19":  ("LOW", None, "y=|-5x-2| — absolute value function plot"),
    "Mathematics_2":   ("LOW", None, "y=(1/2)^x+2 with asymptote — exponential function plot"),
    "Mathematics_142": ("LOW", None, "y=eˣ-1 + tangent line — analytic/calculus"),
    "Mathematics_5":   ("LOW", None, "Region between cos and sin in first quadrant — trig"),
    "Mathematics_7":   ("LOW", None, "y=sin(x) and y=-sin(x) shaded region — trig"),
    "Mathematics_6":   ("LOW", None, "Inscribed rectangle under cosine arch — trig"),
    "Mathematics_22":  ("LOW", None, "Polar curve r=4/(1+sinθ) — polar/analytic"),
    "Mathematics_21":  ("LOW", None, "Inside r=3cosθ, outside cardioid — polar/analytic"),
    "Mathematics_23":  ("LOW", None, "r=sinθ and r=cosθ intersection — polar/analytic"),
    "Mathematics_24":  ("LOW", None, "Inside r=1-sinθ, outside r=1 — polar/analytic"),
    "Mathematics_20":  ("LOW", None, "y=|x| — absolute value function plot"),
    "Mathematics_140": ("LOW", None, "Concave up/down function illustrations — calculus conceptual"),
    "Mathematics_1":   ("LOW", None, "Linear function with open circle discontinuity — function plot"),
    "Mathematics_139": ("LOW", None, "Step function ±1 — function plot"),
    "Mathematics_149": ("LOW", None, "Petersen graph — graph theory, out of scope"),
}


def print_stats(problems: list[dict]) -> None:
    from collections import Counter

    counts: Counter = Counter()
    sub_counts: Counter = Counter()

    for p in problems:
        pid = p["id"]
        if pid not in RELEVANCE:
            counts["UNKNOWN"] += 1
            continue
        tier, sub, _ = RELEVANCE[pid]
        counts[tier] += 1
        if sub:
            sub_counts[f"{tier}/{sub}"] += 1

    total = sum(counts.values())
    print(f"{'─'*50}")
    print(f"  Total problems : {total}")
    print(f"{'─'*50}")
    for tier in ("HIGH", "MEDIUM", "LOW", "UNKNOWN"):
        n = counts.get(tier, 0)
        bar = "█" * (n // 2)
        print(f"  {tier:<8} {n:>3}  {bar}")
        for key, v in sorted(sub_counts.items()):
            if key.startswith(tier + "/"):
                sub_label = key.split("/")[1]
                print(f"    └─ {sub_label:<12} {v:>3}")
    print(f"{'─'*50}")


def should_include(pid: str, include_3d: bool, high_only: bool) -> bool:
    if pid not in RELEVANCE:
        # Unknown ID: exclude by default; warn to stderr
        print(f"WARNING: {pid!r} not in relevance table — excluded", file=sys.stderr)
        return False

    tier, sub, _ = RELEVANCE[pid]

    if tier == "LOW":
        return False
    if tier == "HIGH":
        return True
    # tier == "MEDIUM"
    if high_only:
        return False
    if sub == "3d":
        return include_3d
    # sub == "cartesian" or other MEDIUM non-3D
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter GenExam-Math problems by geometry relevance.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input", help="Path to input JSONL file")
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Path to write filtered JSONL (default: <input_stem>_filtered.jsonl)",
    )
    parser.add_argument(
        "--include-3d",
        action="store_true",
        default=False,
        help="Also include MEDIUM solid-geometry (3D) problems",
    )
    parser.add_argument(
        "--high-only",
        "--exclude-medium",
        action="store_true",
        default=False,
        dest="high_only",
        help="Only include HIGH relevance problems (exclude all MEDIUM)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        default=False,
        help="Print relevance breakdown and exit without writing output",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    problems: list[dict] = []
    with input_path.open() as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                problems.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"WARNING: skipping malformed JSON on line {lineno}: {exc}", file=sys.stderr)

    if args.stats:
        print_stats(problems)
        return

    kept = [p for p in problems if should_include(p["id"], args.include_3d, args.high_only)]
    dropped = len(problems) - len(kept)

    if args.output:
        out_path = Path(args.output)
    else:
        out_path = input_path.parent / f"{input_path.stem}_filtered.jsonl"

    with out_path.open("w") as fh:
        for p in kept:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")

    # Summary
    mode_parts = ["HIGH"]
    if not args.high_only:
        mode_parts.append("MEDIUM-cartesian")
        if args.include_3d:
            mode_parts.append("MEDIUM-3d")
    mode_str = " + ".join(mode_parts)

    print(f"Input    : {input_path}  ({len(problems)} problems)")
    print(f"Mode     : {mode_str}")
    print(f"Kept     : {len(kept)}")
    print(f"Dropped  : {dropped}")
    print(f"Output   : {out_path}")


if __name__ == "__main__":
    main()
