"""Re-grade existing pilot JSONL records against the *current* verifier.

Use this after a hardening pass that improves coordinate resolution or
predicate semantics, to quantify how many soft_pass / fail records now
promote to strict pass without re-running any LLM calls.

For each record we re-extract coordinates from the stored ``tikz_code``,
re-evaluate every property in ``tikz_checks`` whose predicate type is
implemented by ``util.tikz_geometry.validate_geometric_property``, and
recompute ``gate_status`` using the same logic as ``evals/run.py``.

Usage:
    python evals/regrade.py \\
        --input-dir evals/results/leaderboard_pilot \\
        --output-dir evals/results/leaderboard_pilot_hardened
"""
from __future__ import annotations

import argparse
import json
import shutil
import yaml
from collections import Counter
from pathlib import Path

from geometry_diagrams.util.tikz_geometry import resolve_all_coordinates, validate_geometric_property

# Match the production tolerance from evals/run.py
_TIKZ_CHECK_TOLERANCE = 1e-2


def _scenario_index(yaml_paths: list[Path]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in yaml_paths:
        scens = yaml.safe_load(p.read_text())
        if isinstance(scens, dict) and "scenarios" in scens:
            scens = scens["scenarios"]
        for s in scens or []:
            out[s["id"]] = s
    return out


def _regrade_record(rec: dict, scenario: dict | None) -> tuple[dict, str]:
    """Return (new_record, change_summary)."""
    tikz = rec.get("tikz_code") or ""
    if not tikz:
        return rec, "no-tikz"

    coords = resolve_all_coordinates(tikz)
    new_checks: dict[str, dict] = {}
    promoted = 0
    demoted = 0

    expected = (scenario or {}).get("expected_properties", []) if scenario else []
    expected_by_name = {p.get("name"): p for p in expected if p.get("name")}

    for name, old in (rec.get("tikz_checks") or {}).items():
        # Don't try to regrade structural checks (required_labels, required_entities)
        if name in {"required_labels", "required_entities"}:
            new_checks[name] = old
            continue

        prop = expected_by_name.get(name)
        if not prop:
            new_checks[name] = old
            continue

        try:
            new_result = validate_geometric_property(
                coords,
                prop["type"],
                prop["args"],
                tikz=tikz,
                tolerance=_TIKZ_CHECK_TOLERANCE,
            )
        except (ValueError, KeyError, TypeError) as exc:
            new_checks[name] = {
                "passed": None,
                "type": prop["type"],
                "skipped": True,
                "error": str(exc),
            }
            continue

        new_entry = {
            "passed": new_result,
            "type": prop["type"],
            "skipped": new_result is None,
        }
        new_checks[name] = new_entry

        old_pass = old.get("passed")
        new_pass = new_entry["passed"]
        if old_pass is None and new_pass is True:
            promoted += 1
        elif old_pass is True and new_pass is False:
            demoted += 1
        elif old_pass is None and new_pass is False:
            demoted += 1  # was skipped, now a real fail
        elif old_pass is False and new_pass is True:
            promoted += 1

    rec = dict(rec)
    rec["tikz_checks"] = new_checks

    # Recompute gate_status (mirrors evals/run.py::_finalize_gate_status)
    failures: list[str] = []
    skipped: list[str] = []
    for n, r in new_checks.items():
        passed = r.get("passed")
        if passed is False:
            failures.append(n)
        elif r.get("skipped") is True or passed is None:
            skipped.append(n)

    canvas = rec.get("canvas_checks")
    if isinstance(canvas, dict):
        for cname, c in canvas.items():
            if isinstance(c, dict) and c.get("passed") is False:
                failures.append(f"canvas:{cname}")

    if failures:
        new_gate = "fail"
    elif skipped:
        new_gate = "soft_pass"
    elif rec.get("svg_rendered") or rec.get("svg_path"):
        new_gate = "pass"
    else:
        new_gate = rec.get("gate_status", "fail")

    old_gate = rec.get("gate_status")
    rec["gate_status"] = new_gate
    rec["gate_failures"] = failures

    summary = ""
    if old_gate != new_gate:
        summary = f"gate: {old_gate} -> {new_gate}"
    if promoted:
        summary += f" promoted={promoted}"
    if demoted:
        summary += f" demoted={demoted}"
    return rec, summary or "unchanged"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--scenarios",
        type=Path,
        nargs="+",
        default=[Path("evals/scenarios_pilot.yaml"), Path("evals/scenarios_pilot_t3.yaml")],
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    scenario_index = _scenario_index(args.scenarios)

    transitions: Counter[tuple[str, str]] = Counter()
    n_total = 0

    for jsonl in sorted(args.input_dir.glob("*.jsonl")):
        out_path = args.output_dir / jsonl.name
        with out_path.open("w") as out_f:
            for line in jsonl.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    out_f.write(line + "\n")
                    continue
                scenario = scenario_index.get(rec.get("scenario_id"))
                old_gate = rec.get("gate_status", "?")
                new_rec, summary = _regrade_record(rec, scenario)
                new_gate = new_rec.get("gate_status", "?")
                transitions[(old_gate, new_gate)] += 1
                n_total += 1
                if args.verbose and old_gate != new_gate:
                    print(f"  {rec.get('scenario_id'):35} {summary}")
                out_f.write(json.dumps(new_rec) + "\n")
        print(f"wrote {out_path}")

    # Also copy non-jsonl artifacts (REPORT.md, csv, svg dirs) so the hardened
    # output dir stands alone for comparison.
    for child in args.input_dir.iterdir():
        if child.suffix == ".jsonl":
            continue
        if child.name.startswith("."):
            continue
        target = args.output_dir / child.name
        if child.is_dir() and not target.exists():
            shutil.copytree(child, target, dirs_exist_ok=True)

    print()
    print(f"Total records regraded: {n_total}")
    print()
    print("Gate transitions (old -> new):")
    for (old_g, new_g), n in sorted(transitions.items(), key=lambda x: -x[1]):
        marker = "" if old_g == new_g else "  *"
        print(f"  {old_g:10} -> {new_g:10}  n={n:4}{marker}")


if __name__ == "__main__":
    main()
