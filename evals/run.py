"""
Eval runner for geometry-penrose-demo strategies.

Usage:
    python -m evals.run [--scenarios PATH] [--strategies S [S ...]]
                        [--model MODEL] [--output DIR] [--repeats N]

Each scenario is run against each strategy. Results are appended as JSONL
records to a file in the output directory.

Result fields:
  run_id, timestamp, scenario_id, strategy, model, user_prompt,
    repeat_index, svg_path,
  generation_success, substance, svg_rendered, general_checks_passed,
  predicate_checks {passed, failed}, tool_calls, retries, input_tokens,
  output_tokens, duration_s, error, human_score, human_notes
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

load_dotenv()  # Load environment variables from .env file

# ---------------------------------------------------------------------------
# Project imports — resolve from repo root regardless of cwd
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from ir import build_diagram_model, parse_domain
from strategies.base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from strategies.raw_code import RawCodeStrategy
from strategies.structured import StructuredStrategy
from strategies.validated import ValidatedStrategy
from util.roger import render_svg
from util.svg_checks import (
    PREDICATE_CHECKS,
    check_elements_in_bounds,
    check_no_collapsed_points,
    checks_from_diagram,
    run_checks,
)

_STRATEGY_MAP: dict[str, type[SubstanceStrategy]] = {
    "raw_code": RawCodeStrategy,
    "structured": StructuredStrategy,
    "validated": ValidatedStrategy,
}

_GENERAL_CHECKS = [check_no_collapsed_points, check_elements_in_bounds]


# ---------------------------------------------------------------------------
# Message history helpers
# ---------------------------------------------------------------------------

def _extract_tool_return(messages, tool_name: str) -> str | None:
    """Return the content of the last successful ToolReturnPart for tool_name."""
    from pydantic_ai.messages import ModelRequest, ToolReturnPart

    for msg in reversed(messages):
        if not isinstance(msg, ModelRequest):
            continue
        for part in reversed(msg.parts):
            if isinstance(part, ToolReturnPart) and part.tool_name == tool_name:
                content = part.content
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    # List of content blocks — join text parts
                    return "".join(
                        c if isinstance(c, str) else getattr(c, "text", "")
                        for c in content
                    )
    return None


def _extract_tool_call_args(messages, tool_name: str) -> dict | None:
    """Return the args dict of the last ToolCallPart for tool_name."""
    from pydantic_ai.messages import ModelResponse, ToolCallPart

    for msg in reversed(messages):
        if not isinstance(msg, ModelResponse):
            continue
        for part in reversed(msg.parts):
            if isinstance(part, ToolCallPart) and part.tool_name == tool_name:
                args = part.args
                if isinstance(args, dict):
                    return args
                if isinstance(args, str):
                    try:
                        return json.loads(args)
                    except json.JSONDecodeError:
                        return None
    return None


def _parse_substance(tool_return_content: str) -> str:
    """Extract substance string from a tool return value.

    ValidatedStrategy returns JSON {"substance": "...", "variation": "..."}.
    Other strategies return the substance string directly.
    """
    try:
        data = json.loads(tool_return_content)
        if isinstance(data, dict) and "substance" in data:
            return data["substance"]
    except (json.JSONDecodeError, TypeError):
        pass
    return tool_return_content


def _count_tool_calls(messages, tool_name: str) -> int:
    from pydantic_ai.messages import ModelResponse, ToolCallPart

    count = 0
    for msg in messages:
        if not isinstance(msg, ModelResponse):
            continue
        for part in msg.parts:
            if isinstance(part, ToolCallPart) and part.tool_name == tool_name:
                count += 1
    return count


# ---------------------------------------------------------------------------
# Per-scenario runner
# ---------------------------------------------------------------------------

async def run_scenario(
    scenario: dict,
    strategy_name: str,
    model: str,
    domain: str,
    domain_info,
    repeat_index: int,
    svg_output_dir: Path,
) -> dict:
    """Run one scenario against one strategy. Returns a result dict."""
    record: dict[str, Any] = {
        "scenario_id": scenario["id"],
        "strategy": strategy_name,
        "model": model,
        "user_prompt": scenario["prompt"],
        "repeat_index": repeat_index,
        "svg_path": None,
        "generation_success": False,
        "substance": None,
        "svg_rendered": False,
        "general_checks_passed": None,
        "predicate_checks": None,
        "tool_calls": 0,
        "retries": 0,
        "input_tokens": None,
        "output_tokens": None,
        "duration_s": None,
        "error": None,
        "human_score": None,
        "human_notes": None,
    }

    strategy_cls = _STRATEGY_MAP[strategy_name]
    strategy = strategy_cls()
    agent = strategy.build_agent(domain, model=model)

    start = time.monotonic()
    try:
        result = await agent.run(scenario["prompt"])
    except Exception as e:
        record["duration_s"] = round(time.monotonic() - start, 2)
        record["error"] = str(e)
        return record

    record["duration_s"] = round(time.monotonic() - start, 2)

    messages = result.all_messages()
    usage = result.usage()

    record["input_tokens"] = usage.input_tokens
    record["output_tokens"] = usage.output_tokens

    total_tool_calls = _count_tool_calls(messages, "render_diagram")
    record["tool_calls"] = total_tool_calls
    # retries = tool calls beyond the first successful attempt
    record["retries"] = max(0, total_tool_calls - 1)

    # Extract substance
    tool_return = _extract_tool_return(messages, "render_diagram")
    if tool_return is None:
        record["error"] = "No render_diagram tool return found in message history"
        return record

    substance = _parse_substance(tool_return)
    record["substance"] = substance
    record["generation_success"] = True

    # Independent SVG rendering
    try:
        svg = render_svg(substance)
    except Exception as e:
        record["error"] = f"SVG render failed: {e}"
        return record

    record["svg_rendered"] = True

    scenario_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", str(scenario["id"]))
    strategy_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", strategy_name)
    svg_filename = f"{scenario_slug}__{strategy_slug}__r{repeat_index:03d}.svg"
    svg_path = svg_output_dir / svg_filename
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(svg)
    record["svg_path"] = str(svg_path)

    # General checks
    general_failures = run_checks(svg, _EmptyDiagram(), _GENERAL_CHECKS)
    record["general_checks_passed"] = len(general_failures) == 0

    # Predicate checks — only for structured/validated (we have the diagram args)
    if strategy_name in ("structured", "validated"):
        tool_args = _extract_tool_call_args(messages, "render_diagram")
        if tool_args is not None:
            try:
                DiagramModel = build_diagram_model(domain_info)
                diagram = DiagramModel(**tool_args)
                pred_checks = checks_from_diagram(diagram)
                pred_failures = run_checks(svg, diagram, pred_checks)
                pred_names_run = [p.name for p in diagram.predicates if p.name in PREDICATE_CHECKS]
                record["predicate_checks"] = {
                    "passed": [n for n in pred_names_run if not any(n in f for f in pred_failures)],
                    "failed": pred_failures,
                }
            except Exception as e:
                record["predicate_checks"] = {"error": str(e)}

    return record


class _EmptyDiagram:
    """Minimal DiagramLike with no objects for running general checks."""
    def __init__(self) -> None:
        self.objects: list = []
        self.predicates: list = []


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
    checks = "CHK:ok  " if record.get("general_checks_passed") else "CHK:fail"
    duration = f"{record['duration_s']:.1f}s" if record["duration_s"] is not None else "?"
    repeat = f"r{record.get('repeat_index', 1):03d}"
    error = f" [{record['error'][:60]}]" if record["error"] else ""
    print(
        f"  [{status}] {record['scenario_id']:<25} {repeat} {svg} {checks} "
        f"{duration:>7}{error}"
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
        chk_ok = sum(1 for r in recs if r.get("general_checks_passed"))
        avg_s = sum(r["duration_s"] for r in recs if r["duration_s"]) / max(n, 1)
        print(
            f"  {strategy:<12}  gen:{gen_ok}/{n}  svg:{svg_ok}/{n}  "
            f"checks:{chk_ok}/{n}  avg:{avg_s:.1f}s"
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
    args = parser.parse_args()

    if args.repeats < 1:
        raise ValueError("--repeats must be >= 1")

    # Load scenarios
    scenarios_path = Path(args.scenarios)
    with scenarios_path.open() as f:
        scenarios = yaml.safe_load(f)
    print(f"Loaded {len(scenarios)} scenarios from {scenarios_path}")

    # Load domain
    domain_path = _REPO_ROOT / "demo-ui" / "geometry.domain"
    domain = domain_path.read_text()
    domain_info = parse_domain(domain)

    # Build run ID and output path
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output)
    output_path = output_dir / f"{run_id}.jsonl"
    svg_output_dir = output_dir / run_id / "svgs"

    total = len(args.strategies) * len(scenarios) * args.repeats
    print(f"Running {total} evals  (run_id={run_id})")
    print(f"Output: {output_path}\n")

    all_records = []
    for strategy_name in args.strategies:
        print(f"Strategy: {strategy_name}  model: {args.model}")
        for scenario in scenarios:
            for repeat_index in range(1, args.repeats + 1):
                record = await run_scenario(
                    scenario,
                    strategy_name,
                    args.model,
                    domain,
                    domain_info,
                    repeat_index,
                    svg_output_dir,
                )
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
