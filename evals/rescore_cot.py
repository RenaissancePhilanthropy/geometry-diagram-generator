"""Backfill the top-level `cot` field and re-run CoT-analysis on saved eval runs.

Background
----------
A pre-fix bug left the top-level `cot` field empty on records where every
recipe attempt failed at the `ir_pipeline` stage and the StructuredStrategy
fallback then succeeded: `recipe_metadata.cot` was only set on a recipe
success, and StructuredStrategy collects no CoT, so `record["cot"]` resolved
to None and cot-analysis was skipped. The thinking itself was captured into
`recipe_metadata.attempt_traces[].cot` — it just never reached the top level.

This script recovers that data with NO re-generation, NO renderer:

  1. For every record whose top-level `cot` is empty, backfill it from the
     last attempt trace that captured a CoT (`next(t.cot for t in reversed if t.cot)`),
     mirroring the all-fail path in evals/run.py.
  2. For every record that has a CoT, (re)compute cot-analysis with the
     deterministic text analyzer (`util.cot_analyzer.analyze_cot`) — pure text,
     no LLM call, so this overwrites any prior LLM-judge score for free.

Writes a new JSONL (input + `.cotbackfill.jsonl`); the original is untouched.

Usage:
    python -m evals.rescore_cot evals/results/<run>.jsonl \\
        --judge-model ollama:gemma4:31b-cloud
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from util.cot_analyzer import analyze_cot

DEFAULT_JUDGE_MODEL = "ollama:gemma4:31b-cloud"  # unused now (deterministic)


def _attempt_traces(record: dict) -> list[dict]:
    rm = record.get("recipe_metadata")
    if not isinstance(rm, dict):
        return []
    return rm.get("attempt_traces") or []


def _backfill_cot(record: dict) -> str | None:
    """Set record['cot'] from the last attempt trace that captured CoT.

    Returns the recovered CoT (or None if nothing to recover). Leaves records
    that already have a top-level CoT untouched.
    """
    if (record.get("cot") or "").strip():
        return record["cot"]
    best = next(
        (t.get("cot") for t in reversed(_attempt_traces(record)) if t.get("cot")),
        None,
    )
    if best:
        record["cot"] = best
    return best or None


def _target_dsl(record: dict) -> dict | None:
    """Mirror _maybe_run_cot_analysis's DSL selection: success attempt's DSL,
    else the last attempt that produced one."""
    traces = _attempt_traces(record)
    for t in traces:
        if t.get("stage") == "success" and t.get("dsl_json") is not None:
            return t["dsl_json"]
    for t in reversed(traces):
        if t.get("dsl_json") is not None:
            return t["dsl_json"]
    return None


async def _rescore_record(record: dict, judge_model: str, enable_cache: bool) -> str:
    """Backfill CoT + (re)compute cot-analysis with the deterministic analyzer.

    Always recomputes (overwrites any prior LLM-judge score) because the
    deterministic text analyzer supersedes the LLM one. `judge_model` /
    `enable_cache` are accepted for CLI compatibility but unused — the
    analyzer is pure text, no LLM call. Returns a status tag.
    """
    cot = _backfill_cot(record)
    if not cot:
        return "no-cot"
    try:
        result = analyze_cot(
            prompt=record.get("user_prompt", ""),
            dsl_json=_target_dsl(record),
            cot=cot,
            model=judge_model,
            enable_cache=enable_cache,
        )
        record["cot_analysis_score"] = result["score"]
        record["cot_analysis_reasoning"] = result["reasoning"]
        record["cot_analysis_signals"] = result["signals"]
        record["cot_analysis_details"] = result
        return "rescored"
    except Exception as e:  # noqa: BLE001
        record["cot_analysis_score"] = None
        record["cot_analysis_reasoning"] = f"CoT-analysis error: {e}"
        return "error"


async def _rescore_file(path: Path, judge_model: str, enable_cache: bool) -> None:
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    print(f"Loaded {len(records)} records from {path}")

    counts: dict[str, int] = {}
    for i, rec in enumerate(records, 1):
        tag = await _rescore_record(rec, judge_model, enable_cache)
        counts[tag] = counts.get(tag, 0) + 1
        scenario = rec.get("scenario_id", "?")
        cot_len = len(rec.get("cot") or "")
        score = rec.get("cot_analysis_score")
        print(f"  [{i}/{len(records)}] {scenario:60s} cot_len={cot_len:6d} score={score} ({tag})")

    out = path.with_suffix(path.suffix + ".cotbackfill.jsonl")
    with out.open("w") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    print(f"\nSummary: {counts}")
    print(f"Wrote {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    ap.add_argument("--cache", action="store_true", help="enable prompt caching for the judge")
    args = ap.parse_args()
    asyncio.run(_rescore_file(args.jsonl, args.judge_model, args.cache))


if __name__ == "__main__":
    main()