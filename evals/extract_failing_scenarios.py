"""Extract failing scenarios from eval run results into a new scenarios file.

Reads one or more (typically rescored) eval-result JSONL files, takes the
scenario_ids whose gate_status is 'fail', combines them (intersection or union),
and writes a copy of those scenario entries from a source scenarios YAML into a
new YAML — so you can re-run evals over just the failing set.

Usage:
    python -m evals.extract_failing_scenarios \
        --runs evals/results/<run1>_rescored.jsonl evals/results/<run2>_rescored.jsonl \
        --mode intersection \
        --scenarios evals/scenarios_geometry_curriculum.yaml \
        --out evals/scenarios_hard_intersection3.yaml
"""
from __future__ import annotations

import argparse
import json
from functools import reduce
from pathlib import Path

import yaml


def _failing_ids(run_path: Path) -> set[str]:
    ids: set[str] = set()
    with run_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("gate_status") == "fail":
                ids.add(rec["scenario_id"])
    return ids


def _combine(sets: list[set[str]], mode: str) -> set[str]:
    if mode == "intersection":
        return reduce(lambda a, b: a & b, sets)
    return reduce(lambda a, b: a | b, sets)  # union


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", nargs="+", required=True, type=Path,
                    help="eval-result JSONL files (e.g. *_rescored.jsonl)")
    ap.add_argument("--mode", choices=["intersection", "union"], default="intersection")
    ap.add_argument("--scenarios", type=Path, required=True,
                    help="source scenarios YAML to copy entries from")
    ap.add_argument("--out", type=Path, required=True, help="output scenarios YAML")
    args = ap.parse_args()

    fail_sets = [_failing_ids(p) for p in args.runs]
    for p, s in zip(args.runs, fail_sets):
        print(f"  {p.name}: {len(s)} failing")
    selected = _combine(fail_sets, args.mode)
    print(f"  {args.mode} of {len(fail_sets)} runs -> {len(selected)} scenarios")

    entries = yaml.safe_load(args.scenarios.read_text())
    by_id = {e["id"]: e for e in entries}
    missing = [sid for sid in selected if sid not in by_id]
    if missing:
        raise SystemExit(f"ERROR: {len(missing)} selected ids not in source yaml: {missing[:5]}")

    # Preserve source order.
    out_entries = [e for e in entries if e["id"] in selected]
    args.out.write_text(yaml.safe_dump(out_entries, sort_keys=False, allow_unicode=True))
    print(f"  wrote {len(out_entries)} scenarios -> {args.out}")


if __name__ == "__main__":
    main()