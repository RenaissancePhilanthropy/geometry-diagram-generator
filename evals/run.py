"""
Eval runner for geometry-tikz-demo strategies.

Usage:
    python -m evals.run [--scenarios PATH] [--strategies S [S ...]]
                        [--model MODEL] [--output DIR] [--repeats N]
                        [--max-concurrency N]
                        [--llm-judge] [--no-llm-judge]
                        [--visual-judge] [--judge-model MODEL]

Each scenario is run against each strategy. Results are appended as JSONL
records to a file in the output directory.

Result fields:
  run_id, timestamp, scenario_id, strategy, model, user_prompt,
    repeat_index, svg_path,
  tikz_code, tkzelements_code,
  generation_success, svg_rendered, svg_checks,
  tikz_checks, tool_calls, retries, input_tokens,
  output_tokens, duration_s, error,
  llm_judge_score, llm_judge_reasoning,
  human_score, human_notes
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import yaml

load_dotenv()

# ---------------------------------------------------------------------------
# Project imports — resolve from repo root regardless of cwd
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from strategies.base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from strategies.raw_code import RawCodeStrategy
from strategies.raw_code_with_revise import RawCodeWithReviseStrategy
from strategies.plan_and_code import PlanAndCodeStrategy
from util.tikz_analysis import (
    resolve_all_coordinates,
    validate_geometric_property,
    validate_required_labels,
    validate_required_entities,
)
from util.svg_checks import run_svg_checks
from util.message_helpers import extract_tool_return, extract_tool_call_args, count_tool_calls

_STRATEGY_MAP: dict[str, type[SubstanceStrategy]] = {
    "raw_code": RawCodeStrategy,
    "raw_code_with_revise": RawCodeWithReviseStrategy,
    "plan_and_code": PlanAndCodeStrategy,
}

_SUPPORTED_PROPERTY_TYPES = {
    "right_angle",
    "midpoint",
    "collinear",
    "equal_lengths",
    "parallel",
    "perpendicular",
    "point_on_line",
    "point_on_segment",
    "point_on_circle",
    "tangent",
    "angle_equal",
    "angle_bisector",
    "intersects",
    "label_present",
    "mark_present",
}


def _validate_scenarios(raw_scenarios: Any) -> list[dict[str, Any]]:
    """Validate scenario YAML shape and return normalized list of scenarios."""
    if not isinstance(raw_scenarios, list):
        raise ValueError("Scenario file must be a YAML list of scenario objects")

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for idx, raw in enumerate(raw_scenarios, start=1):
        where = f"scenario #{idx}"
        if not isinstance(raw, dict):
            raise ValueError(f"{where}: expected mapping/object, got {type(raw).__name__}")

        scenario_id = raw.get("id")
        prompt = raw.get("prompt")

        if not isinstance(scenario_id, str) or not scenario_id.strip():
            raise ValueError(f"{where}: 'id' must be a non-empty string")
        if scenario_id in seen_ids:
            raise ValueError(f"{where}: duplicate id '{scenario_id}'")
        seen_ids.add(scenario_id)

        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"{where} ({scenario_id}): 'prompt' must be a non-empty string")

        expected_properties = raw.get("expected_properties", [])
        if expected_properties is None:
            expected_properties = []
        if not isinstance(expected_properties, list):
            raise ValueError(
                f"{where} ({scenario_id}): 'expected_properties' must be a list when provided"
            )

        normalized_props: list[dict[str, Any]] = []
        for pidx, prop in enumerate(expected_properties, start=1):
            prop_where = f"{where} ({scenario_id}) expected_properties[{pidx}]"
            if not isinstance(prop, dict):
                raise ValueError(f"{prop_where}: expected mapping/object")

            name = prop.get("name")
            prop_type = prop.get("type")
            args = prop.get("args")

            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"{prop_where}: 'name' must be a non-empty string")
            if not isinstance(prop_type, str) or prop_type not in _SUPPORTED_PROPERTY_TYPES:
                supported = ", ".join(sorted(_SUPPORTED_PROPERTY_TYPES))
                raise ValueError(
                    f"{prop_where}: unsupported 'type'={prop_type!r}; supported: {supported}"
                )
            if not isinstance(args, list):
                raise ValueError(f"{prop_where}: 'args' must be a list")

            normalized_props.append(
                {
                    "name": name,
                    "type": prop_type,
                    "args": args,
                }
            )

        # required_labels
        required_labels = raw.get("required_labels", [])
        if required_labels is None:
            required_labels = []
        if not isinstance(required_labels, list):
            raise ValueError(
                f"{where} ({scenario_id}): 'required_labels' must be a list when provided"
            )
        for i, label in enumerate(required_labels, start=1):
            if not isinstance(label, str) or not label.strip():
                raise ValueError(
                    f"{where} ({scenario_id}) required_labels[{i}]: must be a non-empty string"
                )

        # required_entities
        required_entities = raw.get("required_entities", [])
        if required_entities is None:
            required_entities = []
        if not isinstance(required_entities, list):
            raise ValueError(
                f"{where} ({scenario_id}): 'required_entities' must be a list when provided"
            )
        for i, entity in enumerate(required_entities, start=1):
            if not isinstance(entity, dict):
                raise ValueError(
                    f"{where} ({scenario_id}) required_entities[{i}]: expected mapping/object"
                )
            if "type" not in entity or not isinstance(entity["type"], str):
                raise ValueError(
                    f"{where} ({scenario_id}) required_entities[{i}]: 'type' must be a string"
                )

        normalized.append(
            {
                "id": scenario_id,
                "prompt": prompt,
                "expected_properties": normalized_props,
                "required_labels": list(required_labels),
                "required_entities": list(required_entities),
            }
        )

    return normalized


# ---------------------------------------------------------------------------
# Per-scenario runner
# ---------------------------------------------------------------------------

async def run_scenario(
    scenario: dict,
    strategy_name: str,
    model: str,
    repeat_index: int,
    svg_output_dir: Path,
    llm_judge: bool = False,
    visual_judge: bool = False,
    judge_model: str = DEFAULT_AGENT_MODEL,
) -> dict:
    """Run one scenario against one strategy. Returns a result dict."""
    record: dict[str, Any] = {
        "scenario_id": scenario["id"],
        "strategy": strategy_name,
        "model": model,
        "user_prompt": scenario["prompt"],
        "repeat_index": repeat_index,
        "svg_path": None,
        "tikz_code": None,
        "tkzelements_code": None,
        "generation_success": False,
        "svg_rendered": False,
        "svg_checks": None,
        "tikz_checks": None,
        "tool_calls": 0,
        "retries": 0,
        "input_tokens": None,
        "output_tokens": None,
        "duration_s": None,
        "error": None,
        "llm_judge_score": None,
        "llm_judge_reasoning": None,
        "human_score": None,
        "human_notes": None,
    }

    strategy_cls = _STRATEGY_MAP[strategy_name]
    strategy = strategy_cls()

    start = time.monotonic()
    try:
        result = await strategy.run(scenario["prompt"], model=model)
    except Exception as e:
        record["duration_s"] = round(time.monotonic() - start, 2)
        record["error"] = str(e)
        return record

    record["duration_s"] = round(time.monotonic() - start, 2)

    messages = result.all_messages()
    usage = result.usage()

    record["input_tokens"] = usage.input_tokens
    record["output_tokens"] = usage.output_tokens

    total_tool_calls = count_tool_calls(messages, "render_diagram")
    record["tool_calls"] = total_tool_calls
    record["retries"] = max(0, total_tool_calls - 1)

    # Extract the tool call args (TikZ source code)
    tool_args = extract_tool_call_args(messages, "render_diagram")
    if tool_args is not None:
        record["tikz_code"] = tool_args.get("tikz")
        record["tkzelements_code"] = tool_args.get("tkzelements") or None

    # Extract SVG from the tool return JSON
    tool_return = extract_tool_return(messages, "render_diagram")
    if tool_return is None:
        record["error"] = "No render_diagram tool return found in message history"
        return record

    try:
        tool_data = json.loads(tool_return)
        svg = tool_data.get("svg")
    except (json.JSONDecodeError, TypeError):
        svg = None

    if not svg:
        record["error"] = "No SVG found in render_diagram tool return"
        return record

    record["generation_success"] = True
    record["svg_rendered"] = True

    # Save SVG
    scenario_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", str(scenario["id"]))
    strategy_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", strategy_name)
    svg_filename = f"{scenario_slug}__{strategy_slug}__r{repeat_index:03d}.svg"
    svg_path = svg_output_dir / svg_filename
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(svg)
    record["svg_path"] = str(svg_path)

    # SVG quality checks
    svg_failures = run_svg_checks(svg)
    record["svg_checks"] = {
        "passed": len(svg_failures) == 0,
        "failures": svg_failures,
    }

    # TikZ static analysis checks
    tikz_code = record["tikz_code"]
    if tikz_code:
        coords = resolve_all_coordinates(tikz_code)
        tikz_check_results: dict[str, Any] = {}

        for prop in scenario.get("expected_properties", []):
            prop_result = validate_geometric_property(
                coords,
                prop["type"],
                prop["args"],
                tikz=tikz_code,
            )
            tikz_check_results[prop["name"]] = {
                "passed": prop_result,
                "type": prop["type"],
            }

        required_labels = scenario.get("required_labels", [])
        if required_labels:
            tikz_check_results["required_labels"] = validate_required_labels(
                tikz_code, required_labels
            )

        required_entities = scenario.get("required_entities", [])
        if required_entities:
            tikz_check_results["required_entities"] = validate_required_entities(
                tikz_code, required_entities
            )

        record["tikz_checks"] = tikz_check_results if tikz_check_results else None

    # LLM judge (code review)
    if llm_judge and tikz_code:
        try:
            from util.llm_judge import judge_tikz_code
            judge_result = await judge_tikz_code(
                prompt=scenario["prompt"],
                tikz_code=tikz_code,
                tkzelements_code=record["tkzelements_code"],
                model=judge_model,
            )
            record["llm_judge_score"] = judge_result["score"]
            record["llm_judge_reasoning"] = judge_result["reasoning"]
            record["llm_judge_details"] = judge_result
        except Exception as e:
            record["llm_judge_score"] = None
            record["llm_judge_reasoning"] = f"Judge error: {e}"

    # Visual judge (SVG → image → LLM)
    if visual_judge:
        try:
            from util.llm_judge import judge_rendered_diagram
            visual_result = await judge_rendered_diagram(
                prompt=scenario["prompt"],
                svg=svg,
                tikz_code=tikz_code,
                model=judge_model,
            )
            record["visual_judge_score"] = visual_result["score"]
            record["visual_judge_reasoning"] = visual_result["reasoning"]
        except Exception as e:
            record["visual_judge_score"] = None
            record["visual_judge_reasoning"] = f"Visual judge error: {e}"

    return record


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def _print_record(record: dict) -> None:
    status = "OK " if record["generation_success"] else "ERR"
    svg = "SVG:ok  " if record["svg_rendered"] else "SVG:fail"
    svg_chk = record.get("svg_checks") or {}
    checks = "CHK:ok  " if svg_chk.get("passed") else "CHK:fail"
    judge_str = ""
    if record.get("llm_judge_score") is not None:
        judge_str = f" J:{record['llm_judge_score']}/5"
    duration = f"{record['duration_s']:.1f}s" if record["duration_s"] is not None else "?"
    repeat = f"r{record.get('repeat_index', 1):03d}"
    error = f" [{record['error'][:60]}]" if record.get("error") else ""
    print(
        f"  [{status}] {record['scenario_id']:<25} {repeat} {svg} {checks} "
        f"{duration:>7}{judge_str}{error}"
    )


def _print_summary(records: list[dict]) -> None:
    from collections import defaultdict

    by_strategy: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_strategy[r["strategy"]].append(r)

    print("\n--- Summary ---")
    for strategy, recs in sorted(by_strategy.items()):
        n = len(recs)
        gen_ok = sum(1 for r in recs if r["generation_success"])
        svg_ok = sum(1 for r in recs if r["svg_rendered"])
        svg_chk_ok = sum(1 for r in recs if (r.get("svg_checks") or {}).get("passed"))
        avg_s = sum(r["duration_s"] for r in recs if r["duration_s"]) / max(n, 1)
        retry_rate = sum(r.get("retries", 0) for r in recs) / max(n, 1)

        judge_scores = [r["llm_judge_score"] for r in recs if r.get("llm_judge_score") is not None]
        judge_str = f"  judge:{sum(judge_scores)/len(judge_scores):.1f}/5" if judge_scores else ""

        print(
            f"  {strategy:<12}  gen:{gen_ok}/{n}  svg:{svg_ok}/{n}  "
            f"svgchk:{svg_chk_ok}/{n}  retries:{retry_rate:.1f}{judge_str}  avg:{avg_s:.1f}s"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(description="Run geometry diagram evals")
    parser.add_argument(
        "--scenarios",
        default="evals/scenarios.yaml",
        help="Path to scenarios YAML file",
    )
    parser.add_argument(
        "--strategies",
        nargs="+",
        default=list(_STRATEGY_MAP.keys()),
        choices=list(_STRATEGY_MAP.keys()),
        help="Strategies to evaluate",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_AGENT_MODEL,
        help="LLM model identifier (e.g. anthropic:claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--output",
        default="evals/results",
        help="Directory for JSONL output files",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="Number of times to run each strategy/scenario combination",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=1,
        help="Max number of concurrent scenario runs (default: 1)",
    )
    parser.add_argument(
        "--llm-judge",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable LLM-as-judge (TikZ code review). Default: on.",
    )
    parser.add_argument(
        "--visual-judge",
        action="store_true",
        default=False,
        help="Enable visual LLM judge (SVG → image review). Requires cairosvg.",
    )
    parser.add_argument(
        "--judge-model",
        default=DEFAULT_AGENT_MODEL,
        help="Model to use for LLM-as-judge evaluation",
    )
    args = parser.parse_args()

    if args.repeats < 1:
        raise ValueError("--repeats must be >= 1")
    if args.max_concurrency < 1:
        raise ValueError("--max-concurrency must be >= 1")

    # Load scenarios
    scenarios_path = Path(args.scenarios)
    with scenarios_path.open() as f:
        raw_scenarios = yaml.safe_load(f)
    scenarios = _validate_scenarios(raw_scenarios)
    print(f"Loaded {len(scenarios)} scenarios from {scenarios_path}")

    # Build run ID and output path
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output)
    output_path = output_dir / f"{run_id}.jsonl"
    svg_output_dir = output_dir / run_id / "svgs"

    total = len(args.strategies) * len(scenarios) * args.repeats
    print(f"Running {total} evals  (run_id={run_id})")
    print(f"Output: {output_path}")
    print(f"Max concurrency: {args.max_concurrency}")
    if args.llm_judge:
        print(f"LLM judge: on  (model: {args.judge_model})")
    if args.visual_judge:
        print(f"Visual judge: on")
    print()

    all_records = []
    semaphore = asyncio.Semaphore(args.max_concurrency)

    async def _run_bounded(
        scenario: dict[str, Any],
        strategy_name: str,
        repeat_index: int,
    ) -> dict[str, Any]:
        async with semaphore:
            return await run_scenario(
                scenario,
                strategy_name,
                args.model,
                repeat_index,
                svg_output_dir,
                llm_judge=args.llm_judge,
                visual_judge=args.visual_judge,
                judge_model=args.judge_model,
            )

    for strategy_name in args.strategies:
        print(f"Strategy: {strategy_name}  model: {args.model}")
        tasks = [
            asyncio.create_task(_run_bounded(scenario, strategy_name, repeat_index))
            for scenario in scenarios
            for repeat_index in range(1, args.repeats + 1)
        ]

        for finished in asyncio.as_completed(tasks):
            record = await finished
            record["run_id"] = run_id
            record["timestamp"] = datetime.now(timezone.utc).isoformat()
            _print_record(record)
            _append_jsonl(output_path, record)
            all_records.append(record)

    _print_summary(all_records)
    print(f"\nResults written to {output_path}")
    print(f"SVGs written to {svg_output_dir}")


if __name__ == "__main__":
    asyncio.run(main())
