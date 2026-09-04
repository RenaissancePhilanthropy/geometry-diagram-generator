"""Ticket 07 driver: run PythonFullStrategy.run() once per taxonomy kind,
with experimental_diagram_cookbook left at its default (False) and a plain
kind-specific prompt (kinds_prompts.KIND_PROMPTS) -- no cookbook content
exists yet (tickets 09-12 build it later, informed by this baseline).

Each kind's call to strategy.run() is its own fresh LangGraph run (its own
LLM conversation, own retry loop) -- there is no shared state between
kinds (a fresh PythonFullStrategy() instance per kind, and each script.run
call reads only its own prompt). Reuses the same call pattern
evals/run.py's "python_full" branch uses: PythonFullStrategy().run(prompt,
model=..., renderer=SVGRenderer()) with experimental_diagram_cookbook
omitted (default False).

This script produces ONLY the mechanical generation facts (did it produce
an SVG at all, what error if not, how many retries) -- NOT a pass/partial/
fail verdict. A verdict requires actually looking at the rendered SVG
(ticket 07's Honesty self-review criterion), which is a manual step done
separately; see finalize_manifest.py, which combines this script's
generation_log.json with a hand-reviewed verdict for each kind into the
final manifest.json (manifest_lib.ManifestEntry format).

Usage: .venv/bin/python .scratch/diagram-kinds-poc/baseline/run_baseline.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

BASELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASELINE_DIR.parents[2]
for p in (str(BASELINE_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from kinds_prompts import KIND_PROMPTS  # noqa: E402

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from geometry_diagrams.strategies.base import DEFAULT_AGENT_MODEL  # noqa: E402
from geometry_diagrams.strategies.python_full import PythonFullStrategy  # noqa: E402
from geometry_diagrams.ir.renderer import SVGRenderer  # noqa: E402

SVG_DIR = BASELINE_DIR / "svgs"
GENERATION_LOG_PATH = BASELINE_DIR / "generation_log.json"


async def generate_one(kind: str, prompt: str, model: str) -> dict:
    """Run PythonFullStrategy.run() once for `kind`'s prompt, as a fresh,
    self-contained agent run. Returns raw generation facts -- never a
    verdict. `ok=True` means an SVG was produced (StructuredRunResult
    returned without raising); it says nothing about whether that SVG is
    a good rendering of the requested kind."""
    strategy = PythonFullStrategy()
    record: dict = {
        "kind": kind,
        "prompt": prompt,
        "ok": False,
        "error": None,
        "retries": None,
        "svg_path": None,
    }
    start = time.monotonic()
    try:
        result = await strategy.run(prompt, model=model, renderer=SVGRenderer())
        record["ok"] = True
        record["retries"] = result.retries
        SVG_DIR.mkdir(parents=True, exist_ok=True)
        svg_path = SVG_DIR / f"{kind}.svg"
        svg_path.write_text(result.svg)
        record["svg_path"] = str(svg_path.relative_to(BASELINE_DIR))
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: any failure
        # (sandbox crash, invalid script, timeout, retries exhausted,
        # non-rendering IR) is a legitimate "fail" outcome for this ticket,
        # not something to let propagate and abort the whole run.
        record["error"] = str(exc)
        partial_meta = getattr(strategy, "_partial_python_full_metadata", None)
        if partial_meta is not None:
            record["retries"] = max(0, len(partial_meta.attempt_traces) - 1)
    record["duration_s"] = round(time.monotonic() - start, 2)
    return record


async def run_all(model: str = DEFAULT_AGENT_MODEL) -> "list[dict]":
    results: list[dict] = []
    for kind, prompt in KIND_PROMPTS:
        if prompt is None:
            # "none" (item 30) is not a rendering kind -- no attempt made.
            results.append({
                "kind": kind, "prompt": None, "ok": None, "error": None,
                "retries": None, "svg_path": None, "duration_s": 0.0,
            })
            continue
        print(f"[baseline] generating: {kind} ...", flush=True)
        record = await generate_one(kind, prompt, model)
        status = "ok" if record["ok"] else f"FAILED: {str(record['error'])[:200]}"
        print(f"[baseline] {kind}: {status} ({record['duration_s']}s)", flush=True)
        results.append(record)
    return results


def main() -> None:
    results = asyncio.run(run_all())
    GENERATION_LOG_PATH.write_text(json.dumps(results, indent=2) + "\n")
    n_ok = sum(1 for r in results if r["ok"])
    n_fail = sum(1 for r in results if r["ok"] is False)
    n_skip = sum(1 for r in results if r["ok"] is None)
    print(
        f"[baseline] done: {n_ok} produced an SVG, {n_fail} failed, "
        f"{n_skip} skipped (none). Log: {GENERATION_LOG_PATH}"
    )


if __name__ == "__main__":
    main()
