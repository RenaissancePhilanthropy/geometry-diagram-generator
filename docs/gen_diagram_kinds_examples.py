"""Generate example SVG diagrams for the diagram-kinds cookbook gallery,
using PythonFullStrategy (pydsl script generation) -- the diagram-kinds-poc
counterpart to docs/gen_examples.py, which uses the structured IR pipeline
directly instead.

For the 5 kinds that needed a genuine fresh generation (rather than reuse
of a baseline SVG -- see docs/assemble_diagram_kinds_manifest.py's
FRESH_CHOICES), this script runs each of
diagram_kinds_prompts.FINAL_KIND_CONFIGS[kind]'s attempt prompts in order
and saves every attempt's SVG (and mechanical generation facts) under
docs/examples/diagram_kinds/attempts/<kind>_attempt<N>.svg and
docs/examples/diagram_kinds/generation_log.json -- a human then reviews the
saved SVGs and records a verdict per kind in
assemble_diagram_kinds_manifest.py's FRESH_CHOICES, which
assemble_diagram_kinds_manifest.py consumes to build the final manifest.

A small amount of prompt iteration (2-3 tries) is expected and intentional
here -- this mirrors how the diagram-kinds-poc gallery was actually built,
not a scripted one-shot generator.

Run from the project root:
  .venv/bin/python docs/gen_diagram_kinds_examples.py
  .venv/bin/python docs/gen_diagram_kinds_examples.py --kind area_model
  .venv/bin/python docs/gen_diagram_kinds_examples.py --kind coordinate_plane --attempt 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
for p in (str(SCRIPT_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from diagram_kinds_prompts import FINAL_KIND_CONFIGS  # noqa: E402

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from geometry_diagrams.strategies.base import DEFAULT_AGENT_MODEL  # noqa: E402
from geometry_diagrams.strategies.python_full import PythonFullStrategy  # noqa: E402
from geometry_diagrams.ir.renderer import SVGRenderer  # noqa: E402

OUT_DIR = SCRIPT_DIR / "examples" / "diagram_kinds"
ATTEMPTS_DIR = OUT_DIR / "attempts"
GENERATION_LOG_PATH = OUT_DIR / "generation_log.json"


async def generate_one(
    kind: str, attempt_index: int, prompt: str, use_cookbook: bool, model: str
) -> dict:
    """Run PythonFullStrategy.run() once for one (kind, attempt) pair.
    Returns raw generation facts only -- never a verdict; a human reviews
    the saved SVG and records the verdict separately."""
    strategy = PythonFullStrategy()
    record: dict = {
        "kind": kind,
        "attempt": attempt_index,
        "prompt": prompt,
        "use_cookbook": use_cookbook,
        "ok": False,
        "error": None,
        "retries": None,
        "svg_path": None,
    }
    start = time.monotonic()
    try:
        result = await strategy.run(
            prompt,
            model=model,
            renderer=SVGRenderer(),
            experimental_diagram_cookbook=use_cookbook,
        )
        record["ok"] = True
        record["retries"] = result.retries
        ATTEMPTS_DIR.mkdir(parents=True, exist_ok=True)
        svg_path = ATTEMPTS_DIR / f"{kind}_attempt{attempt_index}.svg"
        svg_path.write_text(result.svg)
        record["svg_path"] = str(svg_path.relative_to(OUT_DIR))
    except Exception as exc:  # noqa: BLE001 -- record and keep going; a
        # generation failure for one attempt shouldn't abort the whole run.
        record["error"] = str(exc)
        partial_meta = getattr(strategy, "_partial_python_full_metadata", None)
        if partial_meta is not None:
            record["retries"] = max(0, len(partial_meta.attempt_traces) - 1)
    record["duration_s"] = round(time.monotonic() - start, 2)
    return record


def _load_log() -> "list[dict]":
    if GENERATION_LOG_PATH.exists():
        return json.loads(GENERATION_LOG_PATH.read_text())
    return []


def _save_log(log: "list[dict]") -> None:
    GENERATION_LOG_PATH.write_text(json.dumps(log, indent=2) + "\n")


async def run(kind_filter: "str | None", attempt_filter: "int | None", model: str) -> None:
    log = _load_log()
    kinds = [kind_filter] if kind_filter else list(FINAL_KIND_CONFIGS.keys())
    for kind in kinds:
        use_cookbook, prompts = FINAL_KIND_CONFIGS[kind]
        indices = [attempt_filter] if attempt_filter is not None else list(range(len(prompts)))
        for idx in indices:
            prompt = prompts[idx]
            print(f"[final] generating: {kind} attempt {idx} (cookbook={use_cookbook}) ...", flush=True)
            record = await generate_one(kind, idx, prompt, use_cookbook, model)
            status = "ok" if record["ok"] else f"FAILED: {str(record['error'])[:200]}"
            print(f"[final] {kind} attempt {idx}: {status} ({record['duration_s']}s)", flush=True)
            # Replace any prior record for this (kind, attempt) pair.
            log = [
                r for r in log
                if not (r["kind"] == kind and r["attempt"] == idx)
            ]
            log.append(record)
            _save_log(log)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", default=None, choices=sorted(FINAL_KIND_CONFIGS.keys()))
    parser.add_argument("--attempt", type=int, default=None)
    parser.add_argument("--model", default=DEFAULT_AGENT_MODEL)
    args = parser.parse_args()
    asyncio.run(run(args.kind, args.attempt, args.model))


if __name__ == "__main__":
    main()
