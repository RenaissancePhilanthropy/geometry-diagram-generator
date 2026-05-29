"""Stratified sampler for the GeoGenBench human-correlation study.

Pre-registration: docs/human_study_protocol.md
This script produces evals/human_study/sample.json, the frozen 200-item sample
used by both raters via the static HTML viewer.

Re-running with the same INPUT_DIR + SEED produces a byte-identical sample;
that property is what makes the pre-registration meaningful.

Usage:
    .venv/bin/python -m evals.human_study.sample_human_study
"""

from __future__ import annotations

import argparse
import json
import os
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_DIR = REPO_ROOT / "evals" / "results" / "leaderboard_pilot_v3"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "evals" / "human_study" / "sample.json"
DEFAULT_SEED = 42
DEFAULT_TARGET_N = 200
DEFAULT_STRATEGIES = ("raw_code", "structured")


def load_pilot_records(input_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for jsonl in sorted(input_dir.glob("*.jsonl")):
        with jsonl.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                records.append(json.loads(line))
    return records


def has_renderable_svg(record: dict[str, Any]) -> bool:
    svg_path = record.get("svg_path")
    if not svg_path:
        return False
    return (REPO_ROOT / svg_path).exists() if not os.path.isabs(svg_path) else os.path.exists(svg_path)


def tier_of(record: dict[str, Any]) -> str:
    """Return T1 / T2 / T3 from the scenario_id (templated convention)."""
    sid = record.get("scenario_id", "")
    if record.get("tier") in (1, 2, 3):
        return f"T{record['tier']}"
    for marker in ("-t1-", "-t2-", "-t3-"):
        if marker in sid:
            return marker.strip("-").upper()
    return "T?"


def stable_sample(items: list[dict], k: int, rng: random.Random) -> list[dict]:
    """Sort then sample so output is deterministic across Python invocations."""
    items = sorted(items, key=lambda r: (r.get("scenario_id", ""), r.get("model", ""), r.get("strategy", ""), r.get("repeat_index", 0)))
    if k >= len(items):
        return list(items)
    return rng.sample(items, k)


def stratified_pass_sample(
    pass_records: list[dict[str, Any]],
    target: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Balance pass-record sampling across (tier, strategy, model).

    We compute a per-cell budget = target / num_nonempty_cells.
    Where a cell has fewer records than its budget, we take all and redistribute
    the deficit proportionally to other cells (one redistribution pass).
    """
    cells: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in pass_records:
        key = (tier_of(r), r.get("strategy", "?"), r.get("model", "?"))
        cells[key].append(r)

    nonempty_keys = [k for k, v in cells.items() if v]
    if not nonempty_keys:
        return []

    base_budget = target // len(nonempty_keys)
    remainder = target - base_budget * len(nonempty_keys)
    budgets: dict[tuple[str, str, str], int] = {k: base_budget for k in nonempty_keys}
    for k in sorted(nonempty_keys)[:remainder]:
        budgets[k] += 1

    chosen: list[dict[str, Any]] = []
    deficit = 0
    surplus_keys: list[tuple[str, str, str]] = []
    for k in nonempty_keys:
        avail = cells[k]
        want = budgets[k]
        if len(avail) <= want:
            chosen.extend(avail)
            deficit += want - len(avail)
        else:
            surplus_keys.append(k)

    if deficit and surplus_keys:
        per_extra = deficit // len(surplus_keys)
        leftover = deficit - per_extra * len(surplus_keys)
        for k in surplus_keys:
            extra = per_extra + (1 if leftover > 0 else 0)
            if leftover > 0:
                leftover -= 1
            budgets[k] += extra

    for k in surplus_keys:
        chosen.extend(stable_sample(cells[k], budgets[k], rng))

    if len(chosen) > target:
        chosen = stable_sample(chosen, target, rng)
    elif len(chosen) < target:
        already_keys = {(r["scenario_id"], r["model"], r["strategy"], r.get("repeat_index", 0)) for r in chosen}
        leftover = [r for r in pass_records
                    if (r["scenario_id"], r["model"], r["strategy"], r.get("repeat_index", 0)) not in already_keys]
        chosen.extend(stable_sample(leftover, target - len(chosen), rng))

    return chosen


def build_sample_record(record: dict[str, Any]) -> dict[str, Any]:
    """Project a pilot record to the fields the viewer needs (and nothing else)."""
    tikz_checks = record.get("tikz_checks") or {}
    predicates = []
    for name, info in tikz_checks.items():
        if not isinstance(info, dict):
            continue
        passed = info.get("passed")
        skipped = info.get("skipped", False)
        verdict = "skip" if skipped else ("pass" if passed else "fail")
        predicates.append({
            "name": name,
            "type": info.get("type", ""),
            "verdict": verdict,
            "raw": {k: v for k, v in info.items() if k in ("passed", "skipped", "type", "reason")},
        })

    return {
        "item_id": f"{record['scenario_id']}__{record['strategy']}__{record['model']}__r{record.get('repeat_index', 1)}",
        "scenario_id": record["scenario_id"],
        "model": record["model"],
        "strategy": record["strategy"],
        "tier": tier_of(record),
        "tags": record.get("tags", []),
        "user_prompt": record.get("user_prompt", ""),
        "svg_path": record["svg_path"],
        "auto_verdict": record.get("gate_status"),
        "gate_failures": record.get("gate_failures", []),
        "predicate_checks": predicates,
        "tikz_code": record.get("tikz_code", ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--target-n", type=int, default=DEFAULT_TARGET_N)
    parser.add_argument(
        "--strategies",
        nargs="+",
        default=list(DEFAULT_STRATEGIES),
        help="Strategies to include in the sampling pool. Default matches the headline run "
             "(raw_code, structured); the deprecated 'recipe' strategy is excluded.",
    )
    args = parser.parse_args()

    rng = random.Random(args.seed)

    records = load_pilot_records(args.input_dir)
    print(f"Loaded {len(records)} records from {args.input_dir}")

    allowed = set(args.strategies)
    pre_strategy = len(records)
    records = [r for r in records if r.get("strategy") in allowed]
    print(f"  filtered to strategies {sorted(allowed)}: {len(records)}/{pre_strategy}")

    rendered = [r for r in records if has_renderable_svg(r)]
    print(f"  with renderable SVG: {len(rendered)}")
    print(f"  excluded (no SVG): {len(records) - len(rendered)}  -- all are gate_status=fail")

    soft_pass = [r for r in rendered if r.get("gate_status") == "soft_pass"]
    fail = [r for r in rendered if r.get("gate_status") == "fail"]
    pass_ = [r for r in rendered if r.get("gate_status") == "pass"]

    chosen: list[dict[str, Any]] = []
    chosen.extend(soft_pass)
    chosen.extend(fail)

    pass_target = args.target_n - len(chosen)
    if pass_target < 0:
        raise SystemExit(
            f"target N={args.target_n} smaller than fixed strata "
            f"(soft_pass={len(soft_pass)} + fail={len(fail)} = {len(chosen)})"
        )
    chosen.extend(stratified_pass_sample(pass_, pass_target, rng))

    chosen.sort(key=lambda r: (r["scenario_id"], r["model"], r["strategy"], r.get("repeat_index", 0)))

    if len(chosen) != args.target_n:
        print(f"WARNING: produced {len(chosen)} items, target was {args.target_n}")

    sample_items = [build_sample_record(r) for r in chosen]
    payload = {
        "schema_version": 1,
        "input_dir": str(args.input_dir.relative_to(REPO_ROOT)),
        "seed": args.seed,
        "target_n": args.target_n,
        "actual_n": len(sample_items),
        "items": sample_items,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
    print(f"Wrote {len(sample_items)} items to {args.output}")

    print("\n--- Sample composition ---")
    print("verdict:", Counter(r["auto_verdict"] for r in sample_items))
    print("tier:", Counter(r["tier"] for r in sample_items))
    print("strategy:", Counter(r["strategy"] for r in sample_items))
    print("model:", Counter(r["model"] for r in sample_items))
    print("avg predicates per item:", sum(len(r["predicate_checks"]) for r in sample_items) / max(1, len(sample_items)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
