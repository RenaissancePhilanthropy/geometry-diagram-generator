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


def _avg_judge_score(records: list[dict]) -> float | None:
    scores = [r["llm_judge_score"] for r in records if r.get("llm_judge_score") is not None]
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

    all_scenarios = sorted(
        set(baseline_by_scenario) | set(candidate_by_scenario)
    )

    scenario_deltas = {}
    for scenario_id in all_scenarios:
        b_recs = baseline_by_scenario.get(scenario_id, [])
        c_recs = candidate_by_scenario.get(scenario_id, [])

        b_judge = _avg_judge_score(b_recs)
        c_judge = _avg_judge_score(c_recs)

        if b_judge is not None and c_judge is not None:
            judge_delta = c_judge - b_judge
        else:
            judge_delta = None

        scenario_deltas[scenario_id] = {
            "baseline_success": _success_rate(b_recs),
            "candidate_success": _success_rate(c_recs),
            "baseline_judge": b_judge,
            "candidate_judge": c_judge,
            "judge_delta": judge_delta,
            "baseline_retries": _avg_retries(b_recs),
            "candidate_retries": _avg_retries(c_recs),
        }

    return {
        "baseline_total": len(baseline),
        "candidate_total": len(candidate),
        "overall": {
            "baseline_success": _success_rate(baseline),
            "candidate_success": _success_rate(candidate),
            "baseline_svg": _svg_rate(baseline),
            "candidate_svg": _svg_rate(candidate),
            "baseline_svg_checks": _svg_check_rate(baseline),
            "candidate_svg_checks": _svg_check_rate(candidate),
            "baseline_judge": _avg_judge_score(baseline),
            "candidate_judge": _avg_judge_score(candidate),
            "baseline_retries": _avg_retries(baseline),
            "candidate_retries": _avg_retries(candidate),
            "baseline_duration": _avg_duration(baseline),
            "candidate_duration": _avg_duration(candidate),
            "baseline_tikz_checks": _tikz_check_pass_rate(baseline),
            "candidate_tikz_checks": _tikz_check_pass_rate(candidate),
        },
        "scenarios": scenario_deltas,
    }


def detect_regressions(
    comparison: dict,
    threshold: float = 0.5,
) -> list[str]:
    """
    Return a list of scenario IDs where the LLM judge score dropped by more
    than `threshold` points between baseline and candidate.
    """
    regressions = []
    for scenario_id, delta_info in comparison["scenarios"].items():
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

    _row("generation success", o["baseline_success"], o["candidate_success"], _fmt_rate)
    _row("svg rendered", o["baseline_svg"], o["candidate_svg"], _fmt_rate)
    _row("svg checks passed", o["baseline_svg_checks"], o["candidate_svg_checks"], _fmt_rate)
    _row("tikz checks passed", o["baseline_tikz_checks"], o["candidate_tikz_checks"], _fmt_rate)
    _row("llm judge score", o["baseline_judge"], o["candidate_judge"], _fmt_score)
    _row("avg retries", o["baseline_retries"], o["candidate_retries"], lambda v: f"{v:.2f}" if v is not None else "n/a")
    _row("avg duration (s)", o["baseline_duration"], o["candidate_duration"], lambda v: f"{v:.1f}s" if v else "n/a")

    print(f"\n  Per-scenario judge scores:")
    print(f"  {'Scenario':<28}  {'Baseline':>8}  {'Cand.':>8}  {'Δ':>8}  Status")
    print(f"  {'-'*28}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*10}")

    regressions = detect_regressions(comparison, threshold)
    for scenario_id, sd in sorted(comparison["scenarios"].items()):
        b = _fmt_score(sd["baseline_judge"])
        c = _fmt_score(sd["candidate_judge"])
        delta = _fmt_delta(sd["judge_delta"])
        status = "REGRESSION" if scenario_id in regressions else ""
        print(f"  {scenario_id:<28}  {b:>8}  {c:>8}  {delta:>8}  {status}")

    if regressions:
        print(f"\n  ⚠ Regressions (score drop > {threshold:.1f}): {', '.join(regressions)}")
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


if __name__ == "__main__":
    main()
