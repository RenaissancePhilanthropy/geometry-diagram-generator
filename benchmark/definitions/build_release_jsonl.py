"""Convert benchmark YAML definitions into release JSONL artefacts.

The YAML files (`bench_generated.yaml`, `bench_curriculum.yaml`) are the
canonical source consumed by the verifier; the JSONL files are the
release artefact referenced by `croissant.json` and uploaded to the
external dataset host (Hugging Face). Each JSONL line is one
`BenchmarkPrompt` record with the rich `metadata` block (containing the
verifier's `original_expected_properties` list) preserved as a nested
JSON object.

Determinism: keys are emitted in a fixed order and JSON is encoded with
`sort_keys=True` and `ensure_ascii=False`. Re-running on the same
YAML inputs is byte-identical, so the SHA-256 hashes printed at the end
can be pasted into `croissant.json` for the file-integrity check.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from benchmark.models import BenchmarkDefinition

DEFINITIONS = Path(__file__).parent
RELEASES: list[tuple[str, str]] = [
    ("bench_generated.yaml", "bench_generated.jsonl"),
    ("bench_curriculum.yaml", "bench_curriculum.jsonl"),
]


def _to_record(prompt: dict) -> dict:
    """Round-trip a YAML prompt dict into the canonical JSONL record shape."""
    return {
        "id": prompt["id"],
        "prompt": prompt["prompt"],
        "tier": prompt.get("tier"),
        "tags": list(prompt.get("tags") or []),
        "rubric": [
            {
                "id": item["id"],
                "text": item["text"],
                "category": item.get("category", "custom"),
                "weight": item.get("weight"),
            }
            for item in prompt.get("rubric") or []
        ],
        "reference_svg": prompt.get("reference_svg"),
        "metadata": prompt.get("metadata") or {},
    }


def convert(src: Path, dst: Path) -> tuple[int, str]:
    with open(src) as f:
        raw = yaml.safe_load(f)
    BenchmarkDefinition.model_validate(raw)
    records = [_to_record(p) for p in raw["prompts"]]
    payload = (
        "\n".join(
            json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            for r in records
        )
        + "\n"
    )
    dst.write_text(payload, encoding="utf-8")
    sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return len(records), sha


def main() -> None:
    print(f"{'file':36s}  {'records':>8s}  {'bytes':>10s}  sha256")
    print("-" * 100)
    for src_name, dst_name in RELEASES:
        n, sha = convert(DEFINITIONS / src_name, DEFINITIONS / dst_name)
        size = (DEFINITIONS / dst_name).stat().st_size
        print(f"{dst_name:36s}  {n:8d}  {size:10d}  {sha}")


if __name__ == "__main__":
    main()
