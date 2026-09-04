"""Ticket 13 driver: genuine PythonFullStrategy.run() calls for the 5 kinds
that need a fresh fix (area_model, attribute_chart with
experimental_diagram_cookbook=True; coordinate_plane, scatter_plot,
shape_comparison without it), per final_prompts.FINAL_KIND_CONFIGS.

Mirrors ../baseline/run_baseline.py's call pattern exactly
(PythonFullStrategy().run(prompt, model=..., renderer=SVGRenderer())) --
same discipline: a fresh PythonFullStrategy() instance per attempt, no
shared state, no hand-authored pydsl standing in for the LLM's output.

Unlike the baseline (one attempt per kind, no verdict), this ticket
explicitly allows a small amount of prompt iteration (2-3 tries): for each
kind, this script runs each of final_prompts.FINAL_KIND_CONFIGS[kind]'s
attempt prompts in order and saves every attempt's SVG (and mechanical
generation facts) to attempts/<kind>_attempt<N>.svg /
generation_log.json -- a human (the engineer running this) then reviews
the saved SVGs and records a verdict per kind in review_verdicts.py,
which assemble_manifest.py consumes.

Usage:
  .venv/bin/python .scratch/diagram-kinds-poc/final/run_final.py
  .venv/bin/python .scratch/diagram-kinds-poc/final/run_final.py --kind area_model
  .venv/bin/python .scratch/diagram-kinds-poc/final/run_final.py --kind coordinate_plane --attempt 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

FINAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = FINAL_DIR.parents[2]
for p in (str(FINAL_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from final_prompts import FINAL_KIND_CONFIGS  # noqa: E402

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from geometry_diagrams.strategies.base import DEFAULT_AGENT_MODEL  # noqa: E402
from geometry_diagrams.strategies.python_full import PythonFullStrategy  # noqa: E402
from geometry_diagrams.ir.renderer import SVGRenderer  # noqa: E402

ATTEMPTS_DIR = FINAL_DIR / "attempts"
GENERATION_LOG_PATH = FINAL_DIR / "generation_log.json"


async def generate_one(
    kind: str, attempt_index: int, prompt: str, use_cookbook: bool, model: str
) -> dict:
    """Run PythonFullStrategy.run() once for one (kind, attempt) pair.
    Returns raw generation facts only -- never a verdict (same discipline
    as run_baseline.py's generate_one)."""
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
        record["svg_path"] = str(svg_path.relative_to(FINAL_DIR))
    except Exception as exc:  # noqa: BLE001 -- see run_baseline.py's rationale
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
