"""Eval runner for pydsl multi-turn edit-chain reliability (see design doc
docs/superpowers/specs/2026-08-10-pydsl-edit-chain-eval-design.md).

Deliberately separate from evals/run.py: this drives build_agent()'s
render_diagram tool directly, turn by turn, in a fixed known order,
bypassing the full conversational ReAct loop entirely — only python_full
supports this editing mechanism today (see design doc, Component C).

Usage:
    python -m evals.run_edit_chains [--scenarios PATH] [--models M [M ...]]
                                     [--modes full_rewrite patch]
                                     [--repeats N] [--renderer tikz|svg]
                                     [--turn-timeout SECONDS] [--output DIR]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
import yaml

load_dotenv()

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from evals.edit_chain_metrics import (
    aggregate_turn_records,
    categorize_edit_error,
    resolve_and_validate_properties,
)
from evals.reporting import _append_jsonl
from evals.scenarios_editing_chains import _validate_chain_scenarios
from geometry_diagrams.ir.renderer import SVGRenderer, TikZRenderer
from geometry_diagrams.strategies.base import DEFAULT_AGENT_MODEL
from geometry_diagrams.strategies.python_full import PythonFullStrategy


def _closure_stack(render_tool):
    """Pull the `_stack` list out of render_diagram's closure. There is no
    public accessor for the edit stack — same private-API pattern already
    used in tests/test_python_full_strategy.py's own tests."""
    fn = render_tool.coroutine
    idx = fn.__code__.co_freevars.index("_stack")
    return fn.__closure__[idx].cell_contents


async def run_chain(
    chain: dict,
    model: str,
    edit_generation_mode: str,
    repeat_index: int,
    renderer,
    turn_timeout: float,
    hash_algorithm: str = "blake2s",
) -> list[dict]:
    """Run one chain once against one (model, edit_generation_mode).
    Returns one record per turn. A failed turn does not stop the chain —
    the next turn's request is issued against the same (unchanged) state,
    and the failed turn itself is never retried by this harness (see
    design doc, Component C, step 4)."""
    strategy = PythonFullStrategy()
    graph = strategy.build_agent(
        model=model, renderer=renderer, edit_generation_mode=edit_generation_mode,
        hash_algorithm=hash_algorithm,
    )
    tools_by_name = {t.name: t for t in graph.nodes["tools"].bound.tools_by_name.values()}
    render_tool = tools_by_name["render_diagram"]

    records: list[dict] = []
    prior_failure_count = 0

    for turn_index, turn in enumerate(chain["turns"], start=1):
        stack = _closure_stack(render_tool)
        prev_script = stack[-1]["script"] if stack else ""

        record: dict = {
            "chain_id": chain["id"],
            "model": model,
            "edit_generation_mode": edit_generation_mode,
            "repeat_index": repeat_index,
            "turn_index": turn_index,
            "request": turn["request"],
            "prior_failure_count": prior_failure_count,
            "script_chars_before": len(prev_script),
            "script_lines_before": prev_script.count("\n"),
        }

        try:
            raw_result = await asyncio.wait_for(
                render_tool.ainvoke({"request": turn["request"]}),
                timeout=turn_timeout,
            )
            parsed = json.loads(raw_result)
        except asyncio.TimeoutError:
            record.update({
                "success": False, "error": f"turn timed out after {turn_timeout}s",
                "error_category": "other", "retries": None,
                "script_chars_after": None, "script_lines_after": None,
                "locality_diagnostic": None, "sympy_property_checks": [],
                "edit_ops_meta": None,
            })
            prior_failure_count += 1
            records.append(record)
            continue
        except Exception as e:
            record.update({
                "success": False, "error": str(e),
                "error_category": categorize_edit_error(str(e)), "retries": None,
                "script_chars_after": None, "script_lines_after": None,
                "locality_diagnostic": None, "sympy_property_checks": [],
                "edit_ops_meta": None,
            })
            prior_failure_count += 1
            records.append(record)
            continue

        if "error" in parsed:
            record.update({
                "success": False, "error": parsed["error"],
                "error_category": categorize_edit_error(parsed["error"]), "retries": None,
                "script_chars_after": None, "script_lines_after": None,
                "locality_diagnostic": None, "sympy_property_checks": [],
                "edit_ops_meta": None,
            })
            prior_failure_count += 1
            records.append(record)
            continue

        stack = _closure_stack(render_tool)
        top = stack[-1]
        result = top["result"]
        diagnostic = top["locality_diagnostic"]

        sympy_checks = []
        if turn.get("expected_properties"):
            sympy_checks = resolve_and_validate_properties(
                turn["expected_properties"], result.variable_ids, result.sym_table,
            )

        record.update({
            "success": True, "error": None, "error_category": None,
            "retries": result.retries,
            "script_chars_after": len(result.script),
            "script_lines_after": result.script.count("\n"),
            "locality_diagnostic": (
                {
                    "unmatched_old_names": len(diagnostic.unmatched_old_names),
                    "unmatched_new_names": len(diagnostic.unmatched_new_names),
                    "violations": len(diagnostic.violations),
                    "violated_names": [v["name"] for v in diagnostic.violations],
                }
                if diagnostic is not None else None
            ),
            "sympy_property_checks": sympy_checks,
            "edit_ops_meta": top.get("edit_ops_meta"),
        })
        records.append(record)

    return records


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run pydsl multi-turn edit-chain reliability evals")
    parser.add_argument("--scenarios", default="evals/scenarios_editing_chains.yaml")
    parser.add_argument("--models", nargs="+", default=[DEFAULT_AGENT_MODEL])
    parser.add_argument(
        "--modes", nargs="+", default=["full_rewrite", "patch"],
        choices=["full_rewrite", "patch", "search_replace", "hashline", "line_number"],
    )
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--renderer", choices=["tikz", "svg"], default="svg")
    parser.add_argument("--turn-timeout", type=float, default=60.0)
    parser.add_argument(
        "--hash-algorithm", choices=["blake2s", "xxhash"], default="blake2s",
        help="Hash function for hashline mode's line tags (ignored by other modes).",
    )
    parser.add_argument("--output", default="evals/results")
    args = parser.parse_args()

    with open(args.scenarios) as f:
        raw = yaml.safe_load(f)
    chains = _validate_chain_scenarios(raw)

    renderer = SVGRenderer() if args.renderer == "svg" else TikZRenderer()

    output_dir = Path(args.output)
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    output_path = output_dir / f"edit_chains_{run_id}.jsonl"

    print(f"Running {len(chains)} chains x {len(args.models)} models x {len(args.modes)} modes x {args.repeats} repeats")
    print(f"Output: {output_path}")

    all_records: list[dict] = []
    for chain in chains:
        for model in args.models:
            for mode in args.modes:
                for repeat_index in range(1, args.repeats + 1):
                    records = await run_chain(
                        chain, model, mode, repeat_index, renderer, args.turn_timeout,
                        hash_algorithm=args.hash_algorithm,
                    )
                    for record in records:
                        _append_jsonl(output_path, record)
                        all_records.append(record)

    print(f"\nResults written to {output_path}")
    summary = aggregate_turn_records(all_records)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
