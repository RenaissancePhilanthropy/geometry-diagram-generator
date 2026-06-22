"""Re-score saved eval runs: recompute the full deterministic gate from saved TikZ.

Recomputes every tikz-based gate check from each record's saved `tikz_code`
using the CURRENT checkers, then re-finalizes the gate. No re-generation, no
renderer, no LLM calls. This is the gate-specific rescorer; for CoT re-scoring
(backfill + re-run the analyzer) see ``evals.rescore_cot``.

Recomputed checks -- all of them, not just labels:

  - ``expected_properties`` of every type (marks, angles, collinearity,
    parallelism, perpendicularity, tangency, label_present, ...) via
    ``validate_geometric_property``
  - ``required_labels`` and ``required_entities``
  - ``required_canvas`` and ``expected_points``

Other gate inputs are left untouched: ``svg_checks``, ``structural_checks``, and
``query_results`` are not derivable from ``tikz_code`` alone and are unaffected
by the checker fixes this tool exists to apply retroactively.

Use case: an old run was scored with checkers that had false positives (e.g. the
``mark_present`` tick/arc-multiplicity bug, or free-``\\node`` labels reported
missing). Re-running generation is expensive; this re-derives the gate from the
already-saved TikZ so old results are comparable to runs scored with the current
checkers.

Usage::

    python -m evals.rescore_gate evals/results/<run>.jsonl [...]
    python -m evals.rescore_gate evals/results/<run>.jsonl --scenarios evals/scenarios_hard_intersection3.yaml --restrict evals/results/<other>.jsonl
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from evals.run import (
    _DEFAULT_POINT_TOLERANCE,
    _TIKZ_CHECK_TOLERANCE,
    _finalize_gate_status,
)
from evals.scenarios import load_scenarios
from util.tikz_analysis import (
    resolve_all_coordinates,
    validate_expected_points,
    validate_required_canvas,
    validate_required_entities,
)
from util.tikz_geometry import validate_geometric_property
from util.tikz_validation import validate_required_labels

DEFAULT_SCENARIOS = "evals/scenarios_geometry_curriculum.yaml"


def rescore_gate(record: dict, scenario: dict) -> bool:
    """Recompute all tikz-based gate checks in-place from saved tikz_code.

    Returns True if a recompute happened (tikz_code present), False otherwise.
    Re-finalizes the gate as a side effect via ``_finalize_gate_status``.
    """
    tikz = record.get("tikz_code")
    if not tikz:
        return False

    coords = resolve_all_coordinates(tikz)
    checks: dict[str, object] = {}

    for prop in scenario.get("expected_properties", []):
        try:
            result = validate_geometric_property(
                coords,
                prop["type"],
                prop["args"],
                tikz=tikz,
                tolerance=_TIKZ_CHECK_TOLERANCE,
            )
        except (ValueError, KeyError, TypeError) as exc:
            checks[prop["name"]] = {
                "passed": None,
                "type": prop["type"],
                "skipped": True,
                "error": str(exc),
            }
            continue
        checks[prop["name"]] = {
            "passed": result,
            "type": prop["type"],
            "skipped": result is None,
        }

    required_labels = scenario.get("required_labels") or []
    if required_labels:
        checks["required_labels"] = validate_required_labels(tikz, required_labels)

    required_entities = scenario.get("required_entities") or []
    if required_entities:
        checks["required_entities"] = validate_required_entities(tikz, required_entities)

    record["tikz_checks"] = checks or None

    required_canvas = scenario.get("required_canvas") or {}
    if required_canvas:
        record["canvas_checks"] = validate_required_canvas(tikz, required_canvas)

    expected_points = scenario.get("expected_points") or {}
    if expected_points:
        record["expected_point_checks"] = validate_expected_points(
            coords,
            expected_points,
            tolerance=scenario.get("coordinate_tolerance", _DEFAULT_POINT_TOLERANCE),
        )

    _finalize_gate_status(record)
    return True


def _gate_counts(records: list[dict]) -> Counter:
    return Counter(r.get("gate_status") for r in records)


def rescore_run(
    run_path: Path,
    scenarios_path: Path,
    restrict_ids: set[str] | None = None,
    out_path: Path | None = None,
) -> Path:
    """Re-score one run file; write <stem>_rescored_gate.jsonl and return its path.

    Only records whose ``scenario_id`` is in ``scenarios_path`` (and, if given, in
    ``restrict_ids``) are recomputed; the rest are passed through unchanged.
    """
    scenarios = {s["id"]: s for s in load_scenarios(str(scenarios_path))}
    records = [json.loads(line) for line in run_path.read_text().splitlines() if line.strip()]

    before = _gate_counts(records)
    n_done = n_check_changed = n_gate_changed = 0

    for r in records:
        sid = r.get("scenario_id")
        if restrict_ids is not None and sid not in restrict_ids:
            continue
        sc = scenarios.get(sid)
        if sc is None:
            continue
        old_checks = r.get("tikz_checks")
        old_gate = r.get("gate_status")
        rescore_gate(r, sc)
        r.setdefault("_rescored_gate", True)
        n_done += 1
        if r.get("tikz_checks") != old_checks:
            n_check_changed += 1
        if r.get("gate_status") != old_gate:
            n_gate_changed += 1

    out = out_path or run_path.with_name(run_path.stem + "_rescored_gate.jsonl")
    with out.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    after = _gate_counts(records)
    _print_table(run_path.name, out.name, before, after, len(records), n_done, n_check_changed, n_gate_changed)
    return out


def _print_table(run, out, before, after, n, n_done, n_checks, n_gate):
    def row(c):
        return f"pass={c.get('pass', 0):>3}  soft={c.get('soft_pass', 0):>3}  fail={c.get('fail', 0):>3}"
    print(f"\n{run}  ->  {out}  (n={n})")
    print(f"  before: {row(before)}   pass% = {(before.get('pass',0)+before.get('soft_pass',0))/n:.0%}")
    print(f"  after : {row(after)}    pass% = {(after.get('pass',0)+after.get('soft_pass',0))/n:.0%}")
    print(f"  records recomputed: {n_done}")
    print(f"  records with a changed tikz_checks: {n_checks}")
    print(f"  records whose gate_status flipped     : {n_gate}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runs", nargs="+", type=Path, help="eval result JSONL files to re-score")
    ap.add_argument("--scenarios", default=DEFAULT_SCENARIOS, type=Path)
    ap.add_argument("--restrict", default=None, type=Path,
                    help="only recompute records whose scenario_id appears in this jsonl")
    args = ap.parse_args()

    restrict_ids = None
    if args.restrict:
        restrict_ids = {json.loads(l)["scenario_id"]
                        for l in args.restrict.read_text().splitlines() if l.strip()}

    for run_path in args.runs:
        rescore_run(run_path, args.scenarios, restrict_ids=restrict_ids)


if __name__ == "__main__":
    main()