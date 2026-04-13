#!/usr/bin/env python3
"""Export eval results as static JSON/SVG files for the eval viewer UI.

Reads JSONL from evals/results/ and writes pre-built API responses into
eval-viewer-ui/public/data/ so the frontend can be deployed as a purely
static site (Vercel, Netlify, GitHub Pages, etc.).

Usage:
    uv run python scripts/export_static.py            # export all runs
    uv run python scripts/export_static.py 20260413-170204  # export specific run
"""

import json
import shutil
import sys
from pathlib import Path

RESULTS_DIR = Path("evals/results")
OUTPUT_DIR = Path("eval-viewer-ui/public/data")


def record_metadata(record: dict) -> dict:
    return {k: v for k, v in record.items() if k not in ("tikz_code", "diagram_ir")}


def run_summary(run_id: str, records: list[dict]) -> dict:
    strategies = sorted({r.get("strategy", "") for r in records})
    gate_counts: dict[str, int] = {}
    for r in records:
        g = r.get("gate_status", "fail")
        gate_counts[g] = gate_counts.get(g, 0) + 1
    return {
        "run_id": run_id,
        "record_count": len(records),
        "strategies": strategies,
        "gate_counts": gate_counts,
    }


def export_run(run_id: str, records: list[dict]) -> None:
    run_dir = OUTPUT_DIR / "runs" / run_id
    records_dir = run_dir / "records"
    svg_dir = run_dir / "svg"
    records_dir.mkdir(parents=True, exist_ok=True)
    svg_dir.mkdir(parents=True, exist_ok=True)

    # /data/runs/{runId}.json — record metadata list
    meta_list = [record_metadata(r) for r in records]
    (run_dir / "index.json").write_text(json.dumps(meta_list))

    for i, record in enumerate(records):
        # /data/runs/{runId}/records/{index}.json — full record
        (records_dir / f"{i}.json").write_text(json.dumps(record))

        # /data/runs/{runId}/svg/{index}.svg — SVG file
        svg_path = record.get("svg_path")
        if svg_path:
            src = Path(svg_path)
            if src.exists():
                shutil.copy2(src, svg_dir / f"{i}.svg")


def main() -> None:
    if not RESULTS_DIR.exists():
        print("No evals/results/ directory found.")
        sys.exit(1)

    filter_ids = set(sys.argv[1:]) if len(sys.argv) > 1 else None

    # Clean previous export
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    jsonl_files = sorted(RESULTS_DIR.glob("*.jsonl"), reverse=True)
    if not jsonl_files:
        print("No .jsonl files found in evals/results/")
        sys.exit(1)

    summaries = []
    for path in jsonl_files:
        run_id = path.stem
        if filter_ids and run_id not in filter_ids:
            continue

        records = []
        with path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))

        summaries.append(run_summary(run_id, records))
        export_run(run_id, records)
        print(f"  Exported {run_id}: {len(records)} records")

    # /data/runs.json — run list
    (OUTPUT_DIR / "runs.json").write_text(json.dumps(summaries))

    total_records = sum(s["record_count"] for s in summaries)
    print(f"\nDone — {len(summaries)} run(s), {total_records} record(s) → {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
