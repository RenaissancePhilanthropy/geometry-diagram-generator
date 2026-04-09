from __future__ import annotations

import argparse
import json
import shutil
import sys
import warnings
from datetime import datetime
from pathlib import Path

from benchmark.db import get_db, insert_run, insert_result
from benchmark.models import load_definition

_DEFINITIONS_DIR = Path(__file__).parent / "definitions"
_SVGS_DIR = Path(__file__).parent / "data" / "svgs"


def _definition_path(benchmark_id: str) -> Path:
    return _DEFINITIONS_DIR / f"{benchmark_id}.yaml"


def _dest_svg_dir(run_id: str) -> Path:
    return _SVGS_DIR / run_id


def import_from_dir(
    benchmark_id: str,
    svgs_dir: Path,
    label: str,
    db_path: Path | None = None,
) -> str:
    definition = load_definition(_definition_path(benchmark_id))
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")

    svg_map: dict[str, Path] = {}
    for f in Path(svgs_dir).iterdir():
        if f.suffix.lower() == ".svg":
            svg_map[f.stem] = f

    prompt_ids = {p.id for p in definition.prompts}
    for stem in svg_map:
        if stem not in prompt_ids:
            warnings.warn(f"Unmatched SVG file: {stem}.svg — no prompt with that id, skipping")

    dest_dir = _dest_svg_dir(run_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    conn = get_db(db_path)
    insert_run(conn, run_id, benchmark_id, label)

    success_count = 0
    for prompt in definition.prompts:
        result_id = f"{run_id}__{prompt.id}"
        if prompt.id in svg_map:
            src = svg_map[prompt.id]
            dest = dest_dir / f"{prompt.id}.svg"
            shutil.copy2(src, dest)
            insert_result(conn, result_id, run_id, prompt.id, str(dest), None, True, None)
            success_count += 1
        else:
            insert_result(conn, result_id, run_id, prompt.id, None, None, False, None)

    total = len(definition.prompts)
    print(f"Imported {success_count}/{total} SVGs for benchmark '{benchmark_id}' (run {run_id})")
    print(f"run_id: {run_id}")
    return run_id


def import_from_manifest(
    benchmark_id: str,
    manifest_path: Path,
    label: str,
    db_path: Path | None = None,
) -> str:
    definition = load_definition(_definition_path(benchmark_id))
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")

    prompt_ids = {p.id for p in definition.prompts}

    entries: list[dict] = []
    with open(manifest_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            pid = entry.get("prompt_id")
            if pid not in prompt_ids:
                warnings.warn(f"Unknown prompt_id in manifest: {pid!r} — skipping")
                continue
            entries.append(entry)

    manifest_prompt_ids = {e["prompt_id"] for e in entries}

    dest_dir = _dest_svg_dir(run_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    conn = get_db(db_path)
    insert_run(conn, run_id, benchmark_id, label)

    success_count = 0
    for prompt in definition.prompts:
        result_id = f"{run_id}__{prompt.id}"
        if prompt.id in manifest_prompt_ids:
            entry = next(e for e in entries if e["prompt_id"] == prompt.id)
            src = Path(entry["svg_path"])
            dest = dest_dir / f"{prompt.id}.svg"
            shutil.copy2(src, dest)
            metadata = entry.get("metadata")
            insert_result(conn, result_id, run_id, prompt.id, str(dest), None, True, metadata)
            success_count += 1
        else:
            insert_result(conn, result_id, run_id, prompt.id, None, None, False, None)

    total = len(definition.prompts)
    print(f"Imported {success_count}/{total} SVGs for benchmark '{benchmark_id}' (run {run_id})")
    print(f"run_id: {run_id}")
    return run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Import SVGs into a benchmark run")
    parser.add_argument("--benchmark", required=True, help="Benchmark definition ID")
    parser.add_argument("--label", required=True, help="Human-readable label for this run")

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--svgs", type=Path, help="Directory of SVG files")
    source.add_argument("--manifest", type=Path, help="JSONL manifest file")

    args = parser.parse_args()

    if args.svgs:
        import_from_dir(args.benchmark, args.svgs, args.label)
    else:
        import_from_manifest(args.benchmark, args.manifest, args.label)


if __name__ == "__main__":
    main()
