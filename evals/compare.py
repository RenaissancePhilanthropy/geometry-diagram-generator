"""
Compare eval results across runs.

Usage:
    python -m evals.compare <run1.jsonl> <run2.jsonl> [--threshold FLOAT]
    python -m evals.compare --baseline evals/results/baseline.jsonl evals/results/latest.jsonl

Prints a comparison table and flags regressions where quality dropped.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_results(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _key(record: dict) -> tuple[str, str, int]:
    return (record["scenario_id"], record["strategy"], record["repeat_index"])


def _group_by_scenario(records: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        groups[r["scenario_id"]].append(r)
    return groups


def _group_by_field(records: list[dict], field: str) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        value = r.get(field)
        if value is None:
            continue
        groups[str(value)].append(r)
    return groups


# ---------------------------------------------------------------------------
# Metrics extraction
# ---------------------------------------------------------------------------

def _success_rate(records: list[dict]) -> float:
    if not records:
        return 0.0
    return sum(1 for r in records if r.get("generation_success")) / len(records)


def _svg_rate(records: list[dict]) -> float:
    if not records:
        return 0.0
    return sum(1 for r in records if r.get("svg_rendered")) / len(records)


def _svg_check_rate(records: list[dict]) -> float:
    scored = [r for r in records if r.get("svg_checks") is not None]
    if not scored:
        return float("nan")
    return sum(1 for r in scored if r["svg_checks"].get("passed")) / len(scored)


def _gate_pass_rate(records: list[dict]) -> float:
    if not records:
        return 0.0
    return sum(1 for r in records if r.get("gate_status") == "pass") / len(records)


def _soft_pass_rate(records: list[dict]) -> float:
    if not records:
        return 0.0
    return sum(1 for r in records if r.get("gate_status") == "soft_pass") / len(records)


def _avg_judge_score(records: list[dict], gate_only: bool = False) -> float | None:
    scores = [
        r["llm_judge_score"]
        for r in records
        if r.get("llm_judge_score") is not None and (not gate_only or r.get("gate_status") == "pass")
    ]
    return sum(scores) / len(scores) if scores else None


def _avg_visual_score(records: list[dict], gate_only: bool = False) -> float | None:
    scores = [
        r["visual_judge_score"]
        for r in records
        if r.get("visual_judge_score") is not None and (not gate_only or r.get("gate_status") == "pass")
    ]
    return sum(scores) / len(scores) if scores else None


def _avg_retries(records: list[dict]) -> float:
    return sum(r.get("retries", 0) for r in records) / max(len(records), 1)


def _avg_duration(records: list[dict]) -> float:
    durations = [r["duration_s"] for r in records if r.get("duration_s") is not None]
    return sum(durations) / len(durations) if durations else 0.0


def _tikz_check_pass_rate(records: list[dict]) -> float | None:
    all_checks = []
    for r in records:
        checks = r.get("tikz_checks") or {}
        for v in checks.values():
            if v.get("passed") is not None:
                all_checks.append(v["passed"])
    if not all_checks:
        return None
    return sum(all_checks) / len(all_checks)


def _summary(records: list[dict]) -> dict[str, Any]:
    return {
        "success": _success_rate(records),
        "svg": _svg_rate(records),
        "svg_checks": _svg_check_rate(records),
        "gate": _gate_pass_rate(records),
        "soft_pass": _soft_pass_rate(records),
        "judge": _avg_judge_score(records),
        "judge_pass": _avg_judge_score(records, gate_only=True),
        "visual_pass": _avg_visual_score(records, gate_only=True),
        "retries": _avg_retries(records),
        "duration": _avg_duration(records),
        "tikz_checks": _tikz_check_pass_rate(records),
    }


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def compare_runs(
    baseline: list[dict],
    candidate: list[dict],
) -> dict[str, Any]:
    """Compare two eval runs. Returns a comparison summary dict."""
    baseline_by_scenario = _group_by_scenario(baseline)
    candidate_by_scenario = _group_by_scenario(candidate)
    baseline_by_tier = _group_by_field(baseline, "tier")
    candidate_by_tier = _group_by_field(candidate, "tier")
    baseline_by_benchmark = _group_by_field(baseline, "benchmark")
    candidate_by_benchmark = _group_by_field(candidate, "benchmark")

    all_scenarios = sorted(
        set(baseline_by_scenario) | set(candidate_by_scenario)
    )

    scenario_deltas = {}
    for scenario_id in all_scenarios:
        b_recs = baseline_by_scenario.get(scenario_id, [])
        c_recs = candidate_by_scenario.get(scenario_id, [])

        b_judge = _avg_judge_score(b_recs, gate_only=True)
        c_judge = _avg_judge_score(c_recs, gate_only=True)

        if b_judge is not None and c_judge is not None:
            judge_delta = c_judge - b_judge
        else:
            judge_delta = None

        scenario_deltas[scenario_id] = {
            "baseline_success": _success_rate(b_recs),
            "candidate_success": _success_rate(c_recs),
            "baseline_gate": _gate_pass_rate(b_recs),
            "candidate_gate": _gate_pass_rate(c_recs),
            "baseline_soft_pass": _soft_pass_rate(b_recs),
            "candidate_soft_pass": _soft_pass_rate(c_recs),
            "baseline_judge": b_judge,
            "candidate_judge": c_judge,
            "judge_delta": judge_delta,
            "baseline_retries": _avg_retries(b_recs),
            "candidate_retries": _avg_retries(c_recs),
            "tier": b_recs[0].get("tier") if b_recs else (c_recs[0].get("tier") if c_recs else None),
        }

    def _compare_grouped(
        baseline_groups: dict[str, list[dict]],
        candidate_groups: dict[str, list[dict]],
    ) -> dict[str, Any]:
        group_keys = sorted(set(baseline_groups) | set(candidate_groups))
        out: dict[str, Any] = {}
        for key in group_keys:
            out[key] = {
                "baseline": _summary(baseline_groups.get(key, [])),
                "candidate": _summary(candidate_groups.get(key, [])),
            }
        return out

    bs = _summary(baseline)
    cs = _summary(candidate)
    return {
        "baseline_total": len(baseline),
        "candidate_total": len(candidate),
        "overall": {
            "baseline_success": bs["success"],
            "candidate_success": cs["success"],
            "baseline_svg": bs["svg"],
            "candidate_svg": cs["svg"],
            "baseline_svg_checks": bs["svg_checks"],
            "candidate_svg_checks": cs["svg_checks"],
            "baseline_gate": bs["gate"],
            "candidate_gate": cs["gate"],
            "baseline_soft_pass": bs["soft_pass"],
            "candidate_soft_pass": cs["soft_pass"],
            "baseline_judge": bs["judge"],
            "candidate_judge": cs["judge"],
            "baseline_judge_pass": bs["judge_pass"],
            "candidate_judge_pass": cs["judge_pass"],
            "baseline_visual_pass": bs["visual_pass"],
            "candidate_visual_pass": cs["visual_pass"],
            "baseline_retries": bs["retries"],
            "candidate_retries": cs["retries"],
            "baseline_duration": bs["duration"],
            "candidate_duration": cs["duration"],
            "baseline_tikz_checks": bs["tikz_checks"],
            "candidate_tikz_checks": cs["tikz_checks"],
        },
        "scenarios": scenario_deltas,
        "tiers": _compare_grouped(baseline_by_tier, candidate_by_tier),
        "benchmarks": _compare_grouped(baseline_by_benchmark, candidate_by_benchmark),
    }


def detect_regressions(
    comparison: dict,
    threshold: float = 0.5,
) -> list[str]:
    """
    Return scenario IDs where either gate pass rate regressed or the judge
    score among gate-passing records dropped by more than `threshold`.
    """
    regressions = []
    for scenario_id, delta_info in comparison["scenarios"].items():
        if delta_info.get("candidate_gate", 0.0) < delta_info.get("baseline_gate", 0.0):
            regressions.append(scenario_id)
            continue
        judge_delta = delta_info.get("judge_delta")
        if judge_delta is not None and judge_delta < -threshold:
            regressions.append(scenario_id)
    return regressions


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------

def _fmt_rate(v: float | None) -> str:
    if v is None or v != v:  # nan check
        return "  n/a"
    return f"{v*100:5.1f}%"


def _fmt_score(v: float | None) -> str:
    if v is None:
        return " n/a "
    return f"{v:4.1f}/5"


def _fmt_delta(v: float | None) -> str:
    if v is None:
        return "   —  "
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:5.2f}"


def print_comparison(comparison: dict, threshold: float = 0.5) -> None:
    o = comparison["overall"]

    print(f"\n{'='*70}")
    print("EVAL RUN COMPARISON")
    print(f"{'='*70}")
    print(f"  {'Metric':<25}  {'Baseline':>10}  {'Candidate':>10}  {'Δ':>8}")
    print(f"  {'-'*25}  {'-'*10}  {'-'*10}  {'-'*8}")

    def _row(label, b_val, c_val, fmt_fn):
        delta = None
        if b_val is not None and c_val is not None:
            try:
                delta = c_val - b_val
            except TypeError:
                pass
        print(f"  {label:<25}  {fmt_fn(b_val):>10}  {fmt_fn(c_val):>10}  {_fmt_delta(delta):>8}")

    _row("gate pass", o["baseline_gate"], o["candidate_gate"], _fmt_rate)
    _row("soft pass", o["baseline_soft_pass"], o["candidate_soft_pass"], _fmt_rate)
    _row("judge on passes", o["baseline_judge_pass"], o["candidate_judge_pass"], _fmt_score)
    _row("visual on passes", o["baseline_visual_pass"], o["candidate_visual_pass"], _fmt_score)
    _row("generation success", o["baseline_success"], o["candidate_success"], _fmt_rate)
    _row("svg rendered", o["baseline_svg"], o["candidate_svg"], _fmt_rate)
    _row("svg checks passed", o["baseline_svg_checks"], o["candidate_svg_checks"], _fmt_rate)
    _row("tikz checks passed", o["baseline_tikz_checks"], o["candidate_tikz_checks"], _fmt_rate)
    _row("llm judge score", o["baseline_judge"], o["candidate_judge"], _fmt_score)
    _row("avg retries", o["baseline_retries"], o["candidate_retries"], lambda v: f"{v:.2f}" if v is not None else "n/a")
    _row("avg duration (s)", o["baseline_duration"], o["candidate_duration"], lambda v: f"{v:.1f}s" if v else "n/a")

    print(f"\n  Per-scenario gate/judge:")
    print(f"  {'Scenario':<28}  {'Gate B':>7}  {'Gate C':>7}  {'Judge B':>8}  {'Judge C':>8}  {'Δ':>8}  Status")
    print(f"  {'-'*28}  {'-'*7}  {'-'*7}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*10}")

    regressions = detect_regressions(comparison, threshold)
    for scenario_id, sd in sorted(comparison["scenarios"].items()):
        gb = _fmt_rate(sd["baseline_gate"])
        gc = _fmt_rate(sd["candidate_gate"])
        b = _fmt_score(sd["baseline_judge"])
        c = _fmt_score(sd["candidate_judge"])
        delta = _fmt_delta(sd["judge_delta"])
        status = "REGRESSION" if scenario_id in regressions else ""
        print(f"  {scenario_id:<28}  {gb:>7}  {gc:>7}  {b:>8}  {c:>8}  {delta:>8}  {status}")

    for section_name in ("benchmarks", "tiers"):
        grouped = comparison.get(section_name) or {}
        if not grouped:
            continue
        print(f"\n  By {section_name[:-1]}:")
        print(f"  {'Name':<18}  {'Gate B':>7}  {'Gate C':>7}  {'Judge B':>8}  {'Judge C':>8}")
        print(f"  {'-'*18}  {'-'*7}  {'-'*7}  {'-'*8}  {'-'*8}")
        for name, payload in sorted(grouped.items()):
            bsum = payload["baseline"]
            csum = payload["candidate"]
            print(
                f"  {name:<18}  {_fmt_rate(bsum['gate']):>7}  {_fmt_rate(csum['gate']):>7}  "
                f"{_fmt_score(bsum['judge_pass']):>8}  {_fmt_score(csum['judge_pass']):>8}"
            )

    if regressions:
        print(f"\n  ⚠ Regressions (gate drop or score drop > {threshold:.1f}): {', '.join(regressions)}")
    else:
        print(f"\n  ✓ No regressions detected (threshold: {threshold:.1f})")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Compare geometry eval runs")
    parser.add_argument(
        "files",
        nargs="+",
        metavar="JSONL",
        help="Two JSONL result files to compare (baseline then candidate)",
    )
    parser.add_argument(
        "--baseline",
        metavar="JSONL",
        help="Explicit baseline file (overrides positional)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="LLM judge score drop threshold to flag as regression (default: 0.5)",
    )
    args = parser.parse_args()

    if args.baseline:
        baseline_path = Path(args.baseline)
        candidate_path = Path(args.files[0])
    elif len(args.files) == 2:
        baseline_path, candidate_path = Path(args.files[0]), Path(args.files[1])
    else:
        parser.error("Provide exactly two JSONL files, or use --baseline + one file")

    baseline = load_results(baseline_path)
    candidate = load_results(candidate_path)

    print(f"Baseline:  {baseline_path}  ({len(baseline)} records)")
    print(f"Candidate: {candidate_path}  ({len(candidate)} records)")

    comparison = compare_runs(baseline, candidate)
    print_comparison(comparison, threshold=args.threshold)

    regressions = detect_regressions(comparison, threshold=args.threshold)
    sys.exit(1 if regressions else 0)


def compare_runs_with_taxonomy(
    records_a: list[dict],
    records_b: list[dict],
    label_a: str = "A",
    label_b: str = "B",
) -> str:
    """Compare two sets of eval records with failure-mode breakdown.

    Each record must have: scenario_id, gate_status, ir_diagnostics (dict or None).
    Returns a formatted text table.
    """
    def _group(records):
        by_scenario: dict[str, list] = defaultdict(list)
        for r in records:
            by_scenario[r["scenario_id"]].append(r)
        return by_scenario

    group_a = _group(records_a)
    group_b = _group(records_b)
    scenarios = sorted(set(group_a) | set(group_b))

    header = (
        f"{'Scenario':<30} {label_a+' pass':<12} {label_b+' pass':<12} "
        f"{'hardcoded':<12} {'parametric':<12} {'missing_pick':<12}"
    )
    lines = [header, "-" * 90]

    for s in scenarios:
        ra = group_a.get(s, [])
        rb = group_b.get(s, [])

        def pass_rate(records):
            if not records:
                return "N/A"
            passing = sum(1 for r in records if r.get("gate_status") == "pass")
            return f"{passing}/{len(records)}"

        def avg_diag(records, key):
            vals = [
                r.get("ir_diagnostics", {}).get(key, 0)
                for r in records
                if r.get("ir_diagnostics")
            ]
            return f"{sum(vals)/len(vals):.1f}" if vals else "N/A"

        lines.append(
            f"{s:<30} {pass_rate(ra):<12} {pass_rate(rb):<12} "
            f"{avg_diag(rb, 'hardcoded_count'):<12} "
            f"{avg_diag(rb, 'parametric_count'):<12} "
            f"{avg_diag(rb, 'missing_pick_count'):<12}"
        )

    return "\n".join(lines)


if __name__ == "__main__":
    main()
