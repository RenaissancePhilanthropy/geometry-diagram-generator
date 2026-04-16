#!/usr/bin/env python3
"""
to_benchmark.py — Convert curriculum eval scenarios to BenchmarkDefinition format.

Reads evals/scenarios_geometry_curriculum.yaml and emits a BenchmarkDefinition
YAML suitable for use with benchmark/genexam/dry_run.py and benchmark/ai_judge.py.

Each scenario's expected_properties are converted to rubric items using
natural-language formatters. Items from required_labels that are not already
covered by label_present properties are appended as additional rubric items.
Weights are normalised to sum to 1.0 per prompt.

Usage:
  python -m curriculum.to_benchmark \\
      --input evals/scenarios_geometry_curriculum.yaml \\
      --output benchmark/definitions/bench_curriculum.yaml

  # Print tier/property-type stats without writing output:
  python -m curriculum.to_benchmark \\
      --input evals/scenarios_geometry_curriculum.yaml \\
      --stats
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Property type → rubric question formatters
# ---------------------------------------------------------------------------
# Each formatter accepts the `args` list from the expected_property and returns
# a natural-language string suitable for an LLM judge.


def _fmt_right_angle(args: list) -> str:
    p1, vertex, p2 = args[0], args[1], args[2]
    return f"Is the angle at {vertex} (between rays {vertex}{p1} and {vertex}{p2}) a right angle?"


def _fmt_collinear(args: list) -> str:
    pts = ", ".join(str(a) for a in args)
    return f"Are points {pts} collinear?"


def _fmt_equal_lengths(args: list) -> str:
    seg_strs = ["".join(str(p) for p in seg) for seg in args]
    if len(seg_strs) == 2:
        return f"Are segments {seg_strs[0]} and {seg_strs[1]} drawn the same length?"
    joined = ", ".join(seg_strs[:-1]) + f", and {seg_strs[-1]}"
    return f"Are segments {joined} drawn the same length?"


def _fmt_parallel(args: list) -> str:
    ab = "".join(str(p) for p in args[0])
    cd = "".join(str(p) for p in args[1])
    return f"Are segments {ab} and {cd} parallel?"


def _fmt_perpendicular(args: list) -> str:
    ab = "".join(str(p) for p in args[0])
    cd = "".join(str(p) for p in args[1])
    return f"Are segments {ab} and {cd} perpendicular?"


def _fmt_midpoint(args: list) -> str:
    m, a, b = args[0], args[1], args[2]
    return f"Is {m} the midpoint of segment {a}{b}?"


def _fmt_point_on_line(args: list) -> str:
    p, a, b = args[0], args[1], args[2]
    return f"Does point {p} lie on line {a}{b}?"


def _fmt_point_on_segment(args: list) -> str:
    p, a, b = args[0], args[1], args[2]
    return f"Does point {p} lie on segment {a}{b}?"


def _fmt_point_on_circle(args: list) -> str:
    p, center = args[0], args[1]
    return f"Does point {p} lie on the circle centered at {center}?"


def _fmt_tangent(args: list) -> str:
    line_pts = args[0]
    center = args[1]
    tangent_pt = args[2]
    pq = "".join(str(x) for x in line_pts)
    return f"Is line {pq} tangent to the circle centered at {center} at point {tangent_pt}?"


def _fmt_angle_equal(args: list) -> str:
    ang1, ang2 = args[0], args[1]
    a, v1, b = ang1[0], ang1[1], ang1[2]
    c, v2, d = ang2[0], ang2[1], ang2[2]
    return f"Is angle {a}{v1}{b} equal to angle {c}{v2}{d}?"


def _fmt_angle_bisector(args: list) -> str:
    d, vertex, p1, p2 = args[0], args[1], args[2], args[3]
    return f"Does ray {vertex}{d} bisect angle {p1}{vertex}{p2}?"


def _fmt_mark_present(args: list) -> str:
    mark_type = str(args[0]).lower()
    point = args[1]

    # Right angle mark
    if mark_type == "right_angle":
        return f"Is a right-angle mark drawn at {point}?"

    # Tick marks (segment congruence) — normalize variants
    if mark_type in ("tick", "tick1", "tick_single"):
        return f"Is a single tick mark drawn on the segment at {point}?"
    if mark_type in ("double_tick", "tick2", "tick_double"):
        return f"Is a double tick mark drawn on the segment at {point}?"
    if mark_type in ("triple_tick", "tick_triple"):
        return f"Is a triple tick mark drawn on the segment at {point}?"

    # Angle arc marks — normalize variants
    if mark_type in ("arc", "angle_single"):
        return f"Is an angle arc mark drawn at {point}?"
    if mark_type in ("double_arc", "angle_double"):
        return f"Is a double angle arc mark drawn at {point}?"

    # Conceptual types that were misused as mark types — rephrase as
    # answerable visual questions
    if mark_type == "midpoint":
        return f"Is {point} visually indicated as a midpoint (e.g. with equal tick marks on both sides)?"
    if mark_type == "radius":
        return f"Is a radius drawn and labeled at {point}?"
    if mark_type == "cross_section":
        return f"Is a cross-section indicated at {point}?"
    if mark_type == "slant_height":
        return f"Is the slant height labeled at {point}?"
    if mark_type == "circumference_label":
        return f"Is the circumference labeled near {point}?"

    # Unknown — pass through with readable formatting
    return f"Is a {mark_type.replace('_', ' ')} mark drawn at {point}?"


def _fmt_label_present(args: list) -> str:
    label = args[0]
    return f"Is point {label} labeled in the diagram?"


def _fmt_equidistant_from_sides(args: list) -> str:
    p, a, b, c = args[0], args[1], args[2], args[3]
    return f"Is point {p} equidistant from the three sides of triangle {a}{b}{c}?"


def _fmt_centroid(args: list) -> str:
    g, a, b, c = args[0], args[1], args[2], args[3]
    return f"Is {g} the centroid of triangle {a}{b}{c}?"


def _fmt_opposite_side(args: list) -> str:
    p, ref, a, b = args[0], args[1], args[2], args[3]
    return f"Is point {p} on the opposite side of line {a}{b} from point {ref}?"


def _fmt_not_between(args: list) -> str:
    p, a, b = args[0], args[1], args[2]
    return f"Is point {p} NOT between points {a} and {b}?"


def _fmt_same_side(args: list) -> str:
    p, q, a, b = args[0], args[1], args[2], args[3]
    return f"Are points {p} and {q} on the same side of line {a}{b}?"


def _fmt_intersects(args: list) -> str:
    ab = "".join(str(x) for x in args[0]) if isinstance(args[0], list) else str(args[0])
    cd = "".join(str(x) for x in args[1]) if isinstance(args[1], list) else str(args[1])
    return f"Do {ab} and {cd} intersect?"


PROPERTY_FORMATTERS: dict[str, callable] = {
    "right_angle": _fmt_right_angle,
    "collinear": _fmt_collinear,
    "equal_lengths": _fmt_equal_lengths,
    "parallel": _fmt_parallel,
    "perpendicular": _fmt_perpendicular,
    "midpoint": _fmt_midpoint,
    "point_on_line": _fmt_point_on_line,
    "point_on_segment": _fmt_point_on_segment,
    "point_on_circle": _fmt_point_on_circle,
    "tangent": _fmt_tangent,
    "angle_equal": _fmt_angle_equal,
    "angle_bisector": _fmt_angle_bisector,
    "mark_present": _fmt_mark_present,
    "label_present": _fmt_label_present,
    "equidistant_from_sides": _fmt_equidistant_from_sides,
    "centroid": _fmt_centroid,
    "opposite_side": _fmt_opposite_side,
    "not_between": _fmt_not_between,
    "same_side": _fmt_same_side,
    "intersects": _fmt_intersects,
}

# ---------------------------------------------------------------------------
# Weights by property category
# ---------------------------------------------------------------------------
WEIGHT_GEOMETRIC = 1.0
WEIGHT_MARK = 0.5
WEIGHT_LABEL = 0.3

PROPERTY_WEIGHTS: dict[str, float] = {
    "right_angle": WEIGHT_GEOMETRIC,
    "collinear": WEIGHT_GEOMETRIC,
    "parallel": WEIGHT_GEOMETRIC,
    "perpendicular": WEIGHT_GEOMETRIC,
    "equal_lengths": WEIGHT_GEOMETRIC,
    "midpoint": WEIGHT_GEOMETRIC,
    "point_on_line": WEIGHT_GEOMETRIC,
    "point_on_segment": WEIGHT_GEOMETRIC,
    "point_on_circle": WEIGHT_GEOMETRIC,
    "tangent": WEIGHT_GEOMETRIC,
    "angle_equal": WEIGHT_GEOMETRIC,
    "angle_bisector": WEIGHT_GEOMETRIC,
    "equidistant_from_sides": WEIGHT_GEOMETRIC,
    "centroid": WEIGHT_GEOMETRIC,
    "opposite_side": WEIGHT_GEOMETRIC,
    "intersects": WEIGHT_GEOMETRIC,
    "not_between": WEIGHT_GEOMETRIC,
    "same_side": WEIGHT_GEOMETRIC,
    "mark_present": WEIGHT_MARK,
    "label_present": WEIGHT_LABEL,
}


def _build_rubric(scenario: dict) -> list[dict]:
    """Build normalised rubric items for one scenario."""
    raw_items: list[tuple[str, float]] = []  # (text, raw_weight)

    # Track labels already covered by label_present properties
    covered_labels: set[str] = set()

    for prop in scenario.get("expected_properties", []):
        prop_type = prop["type"]
        args = prop["args"]
        formatter = PROPERTY_FORMATTERS.get(prop_type)
        if formatter is None:
            text = f"Property '{prop['name']}' of type '{prop_type}' present?"
        else:
            text = formatter(args)
        weight = PROPERTY_WEIGHTS.get(prop_type, WEIGHT_GEOMETRIC)
        raw_items.append((text, weight))

        if prop_type == "label_present" and args:
            covered_labels.add(str(args[0]))

    # Add required_labels not already covered
    for label in scenario.get("required_labels", []):
        if label not in covered_labels:
            text = _fmt_label_present([label])
            raw_items.append((text, WEIGHT_LABEL))
            covered_labels.add(label)

    if not raw_items:
        return []

    total_raw = sum(w for _, w in raw_items)
    scenario_id = scenario["id"]
    rubric = []
    for idx, (text, raw_w) in enumerate(raw_items):
        normalised = round(raw_w / total_raw, 4) if total_raw > 0 else 0.0
        rubric.append({
            "id": f"{scenario_id}_r{idx}",
            "text": text,
            "category": "curriculum",
            "weight": normalised,
        })

    return rubric


def build_benchmark_definition(scenarios: list[dict], benchmark_id: str) -> dict:
    """Convert a list of curriculum scenarios to a BenchmarkDefinition dict."""
    prompts = []
    for scenario in scenarios:
        rubric = _build_rubric(scenario)

        # Compute raw_weights for metadata
        raw_weights: list[float] = []
        for prop in scenario.get("expected_properties", []):
            raw_weights.append(PROPERTY_WEIGHTS.get(prop["type"], WEIGHT_GEOMETRIC))
        covered = {str(p["args"][0]) for p in scenario.get("expected_properties", []) if p["type"] == "label_present" and p["args"]}
        for label in scenario.get("required_labels", []):
            if label not in covered:
                raw_weights.append(WEIGHT_LABEL)

        metadata = {
            "source": "curriculum",
            "original_expected_properties": scenario.get("expected_properties", []),
            "structural_checks": scenario.get("structural_checks", []),
            "required_entities": scenario.get("required_entities", []),
            "required_canvas": scenario.get("required_canvas", {}),
            "expected_points": scenario.get("expected_points", {}),
            "coordinate_tolerance": scenario.get("coordinate_tolerance", 0.0001),
            "queries": scenario.get("queries", []),
            "raw_weights": raw_weights,
        }

        prompts.append({
            "id": scenario["id"],
            "prompt": scenario["prompt"],
            "rubric": rubric,
            "reference_svg": None,
            "tags": scenario.get("tags", []),
            "tier": scenario.get("tier"),
            "metadata": metadata,
        })

    return {
        "id": benchmark_id,
        "shared_rubric": [],
        "prompts": prompts,
    }


def print_stats(scenarios: list[dict]) -> None:
    """Print tier breakdown and property type histogram."""
    tier_counts: Counter = Counter()
    prop_counts: Counter = Counter()

    for s in scenarios:
        tier = s.get("tier")
        tier_counts[tier if tier is not None else "none"] += 1
        for prop in s.get("expected_properties", []):
            prop_counts[prop["type"]] += 1

    total = len(scenarios)
    print(f"{'─'*50}")
    print(f"  Total scenarios : {total}")
    print(f"{'─'*50}")
    print("  Tier breakdown:")
    for tier in sorted(tier_counts.keys(), key=lambda x: (x == "none", x)):
        print(f"    tier {tier:<6} : {tier_counts[tier]}")
    print(f"{'─'*50}")
    print("  Property type histogram:")
    for prop_type, count in prop_counts.most_common():
        bar = "█" * (count // 2)
        print(f"    {prop_type:<28} {count:>4}  {bar}")
    print(f"{'─'*50}")


def main() -> None:
    _repo_root = Path(__file__).resolve().parent.parent
    default_input = _repo_root / "evals" / "scenarios_geometry_curriculum.yaml"
    default_output = _repo_root / "benchmark" / "definitions" / "bench_curriculum.yaml"

    parser = argparse.ArgumentParser(
        description="Convert curriculum eval scenarios to BenchmarkDefinition format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input",
        default=str(default_input),
        help=f"Path to curriculum scenarios YAML (default: {default_input})",
    )
    parser.add_argument(
        "--output",
        default=str(default_output),
        help=f"Path to write BenchmarkDefinition YAML (default: {default_output})",
    )
    parser.add_argument(
        "--benchmark-id",
        default="bench_curriculum",
        help="BenchmarkDefinition id field (default: bench_curriculum)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        default=False,
        help="Print tier breakdown and property histogram, then exit without writing output",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    with input_path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, list):
        print("ERROR: input YAML must be a list of scenario objects", file=sys.stderr)
        sys.exit(1)

    scenarios = raw

    if args.stats:
        print_stats(scenarios)
        return

    definition = build_benchmark_definition(scenarios, benchmark_id=args.benchmark_id)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as fh:
        yaml.dump(definition, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)

    kept = len(definition["prompts"])
    print(f"Input    : {input_path}  ({len(scenarios)} scenarios)")
    print(f"Kept     : {kept}")
    print(f"Output   : {out_path}")


if __name__ == "__main__":
    main()
