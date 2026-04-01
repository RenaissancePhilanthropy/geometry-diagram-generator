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
  tikz_checks, canvas_checks, expected_point_checks,
  deterministic_pass, gate_status, gate_failures,
  tool_calls, retries, input_tokens,
  output_tokens, duration_s, error,
  query_results,
  llm_judge_score, llm_judge_reasoning,
  human_score, human_notes
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
import yaml

load_dotenv()

# ---------------------------------------------------------------------------
# Project imports — resolve from repo root regardless of cwd
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from evals.ir_diagnostics import classify_ir
from evals.scenarios import _validate_scenarios
from evals.sympy_checks import _validate_properties_sympy
from evals.reporting import (
    _externalize_traces,
    _append_jsonl,
    _print_record,
    _print_summary,
)
from strategies.base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from strategies.raw_code import RawCodeStrategy
from strategies.raw_code_with_revise import RawCodeWithReviseStrategy
from strategies.plan_and_code import PlanAndCodeStrategy
from strategies.structured import StructureStrategy, StructuredRunResult
from strategies.recipe import RecipeStrategy
from strategies.structured_plus_refine import StructuredPlusRefineStrategy
from strategies.structured_two_phase import StructuredTwoPhaseStrategy
from strategies.progressive_tools import ProgressiveToolsStrategy, ProgressiveToolsRunResult
from util.tikz_renderer import check_renderer_health
from ir.renderer import TikZRenderer
from util.tikz_analysis import (
    resolve_all_coordinates,
    validate_geometric_property,
    validate_expected_points,
    validate_required_canvas,
    validate_required_labels,
    validate_required_entities,
)
from util.svg_checks import run_svg_checks
from util.message_helpers import extract_tool_return, extract_tool_call_args, count_tool_calls

class _RecipeNoRecipesStrategy(RecipeStrategy):
    def __init__(self) -> None:
        super().__init__(use_recipes=False)


_STRATEGY_MAP: dict[str, type[SubstanceStrategy]] = {
    "raw_code": RawCodeStrategy,
    "raw_code_with_revise": RawCodeWithReviseStrategy,
    "plan_and_code": PlanAndCodeStrategy,
    "structured": StructureStrategy,
    "structured_plus_refine": StructuredPlusRefineStrategy,
    "structured_two_phase": StructuredTwoPhaseStrategy,
    "progressive_tools": ProgressiveToolsStrategy,
    "recipe": RecipeStrategy,
    "recipe_no_recipes": _RecipeNoRecipesStrategy,
}

# Tolerance for geometric checks. Relaxed from 1e-4 to handle LLM-chosen
# coordinates that are approximate (3 decimal places → ~0.001 rounding error).
_TIKZ_CHECK_TOLERANCE = 0.01
_DEFAULT_POINT_TOLERANCE = 1e-4


# ---------------------------------------------------------------------------
# Per-scenario runner
# ---------------------------------------------------------------------------

async def _run_query_phase(
    queries: list[dict],
    sym: dict,
    model: str,
) -> list[dict[str, Any]]:
    """Run follow-up query eval against a pre-computed SymPy symbol table.

    For each query, builds a fresh Agent with query_diagram pre-loaded,
    sends the question, and checks whether the tool was called correctly.
    Checks the LAST query_diagram tool call (one agent per query, so this
    is the relevant call even if the LLM also calls list_objects first).
    """
    from pydantic_ai import Agent
    from strategies.structured import dispatch_query
    from ir.queries import list_objects as _list_objects

    _QUERY_EVAL_INSTRUCTIONS = (
        "You are a geometry assistant. A diagram has already been rendered. "
        "The user will ask about properties of the current diagram. "
        "Use the query_diagram tool to answer their question, then report "
        "the result clearly."
    )

    objects_info = json.dumps(_list_objects(sym))
    results: list[dict[str, Any]] = []

    for query_def in queries:
        question = query_def["question"]
        expected_tc = query_def.get("expected_tool_call") or {}
        expected_answer = query_def.get("expected_answer")

        qr: dict[str, Any] = {
            "question": question,
            "tool_called": False,
            "tool_call_args": None,
            "query_type_match": None,
            "tool_return": None,
            "answer_match": None,
            "answer_error": None,
            "error": None,
        }

        try:
            agent = Agent(model, instructions=_QUERY_EVAL_INSTRUCTIONS)

            @agent.tool_plain
            async def query_diagram(query_type: str, args: dict[str, str]) -> str:
                """Query a geometric property of the current diagram.

                query_type and args:
                  coordinate  {"point": "A"}           -> x, y coords
                  distance    {"a": "A", "b": "B"}     -> distance between points (use for side lengths too)
                  angle       {"ray1": "A", "vertex": "B", "ray2": "C"} -> angle in degrees
                  length      {"segment": "seg_AB"}    -> segment length
                  radius      {"circle": "c1"}         -> circle radius
                  area        {"object": "tri_ABC"}    -> area
                  perimeter   {"object": "tri_ABC"}    -> perimeter
                  list_objects {}                       -> all objects and their types
                """
                return dispatch_query(sym, query_type, args)

            context_msg = (
                f"The following objects exist in the diagram: {objects_info}. "
                f"User question: {question}"
            )

            agent_result = await agent.run(context_msg)
            messages = agent_result.all_messages()

            tc_count = count_tool_calls(messages, "query_diagram")
            qr["tool_called"] = tc_count > 0

            if tc_count > 0:
                tc_args = extract_tool_call_args(messages, "query_diagram")
                qr["tool_call_args"] = tc_args

                if tc_args and expected_tc.get("query_type"):
                    qr["query_type_match"] = (
                        tc_args.get("query_type") == expected_tc["query_type"]
                    )

                tool_ret = extract_tool_return(messages, "query_diagram")
                if tool_ret:
                    qr["tool_return"] = tool_ret
                    if expected_answer:
                        try:
                            ret_data = json.loads(tool_ret)
                            key = expected_answer.get("key")
                            if key and key in ret_data:
                                actual = ret_data[key]
                                if expected_answer.get("value") is not None:
                                    tol = expected_answer.get("tolerance", 0.5)
                                    qr["answer_match"] = (
                                        abs(actual - expected_answer["value"]) < tol
                                    )
                                else:
                                    qr["answer_match"] = True
                        except (json.JSONDecodeError, TypeError, KeyError) as e:
                            qr["answer_error"] = str(e)

        except Exception as e:
            qr["error"] = str(e)

        results.append(qr)

    return results


async def run_scenario(
    scenario: dict,
    strategy_name: str,
    model: str,
    repeat_index: int,
    svg_output_dir: Path,
    benchmark: str,
    llm_judge: bool = False,
    visual_judge: bool = False,
    judge_model: str = DEFAULT_AGENT_MODEL,
) -> dict:
    """Run one scenario against one strategy. Returns a result dict."""
    record: dict[str, Any] = {
        "scenario_id": scenario["id"],
        "benchmark": benchmark,
        "tier": scenario.get("tier"),
        "tags": scenario.get("tags", []),
        "strategy": strategy_name,
        "model": model,
        "user_prompt": scenario["prompt"],
        "repeat_index": repeat_index,
        "svg_path": None,
        "tikz_code": None,
        "diagram_ir": None,
        "tkzelements_code": None,
        "generation_success": False,
        "svg_rendered": False,
        "svg_checks": None,
        "tikz_checks": None,
        "canvas_checks": None,
        "expected_point_checks": None,
        "deterministic_pass": None,
        "gate_status": "fail",
        "gate_failures": [],
        "tool_calls": 0,
        "retries": 0,
        "input_tokens": None,
        "output_tokens": None,
        "duration_s": None,
        "error": None,
        "ir_diagnostics": None,
        "sympy_property_checks": [],
        "structural_checks": None,
        "query_results": [],
        "llm_judge_score": None,
        "llm_judge_reasoning": None,
        "human_score": None,
        "human_notes": None,
    }

    strategy_cls = _STRATEGY_MAP[strategy_name]
    strategy = strategy_cls()

    start = time.monotonic()
    try:
        renderer = TikZRenderer()
        result = await strategy.run(scenario["prompt"], model=model, renderer=renderer)
    except Exception as e:
        record["duration_s"] = round(time.monotonic() - start, 2)
        record["error"] = str(e)
        if isinstance(strategy, ProgressiveToolsStrategy):
            record["input_tokens"] = getattr(strategy, "_partial_input_tokens", None)
            record["output_tokens"] = getattr(strategy, "_partial_output_tokens", None)
            record["tool_calls"] = getattr(strategy, "_partial_tool_calls", None)
            record["phase_traces"] = getattr(strategy, "_partial_phase_traces", None)
            record["phase_usage"] = getattr(strategy, "_partial_phase_usage", None)
            record["retries"] = getattr(strategy, "_partial_repair_cycles", None)
        if isinstance(strategy, RecipeStrategy):
            record["input_tokens"] = getattr(strategy, "_partial_input_tokens", 0)
            record["output_tokens"] = getattr(strategy, "_partial_output_tokens", 0)
            partial_meta = getattr(strategy, "_partial_recipe_metadata", None)
            if partial_meta is not None:
                record["recipe_metadata"] = {
                    "selected_recipes": partial_meta.selected_recipes,
                    "unmatched_concepts": partial_meta.unmatched_concepts,
                    "selection_input_tokens": partial_meta.selection_input_tokens,
                    "selection_output_tokens": partial_meta.selection_output_tokens,
                    "attempt_traces": [
                        {"attempt": t.attempt, "dsl_json": t.dsl_json, "error": t.error, "stage": t.stage}
                        for t in partial_meta.attempt_traces
                    ],
                }
        return record

    record["duration_s"] = round(time.monotonic() - start, 2)

    if isinstance(result, ProgressiveToolsRunResult):
        record["tikz_code"] = result.tikz
        svg = result.svg
        record["input_tokens"] = result.input_tokens
        record["output_tokens"] = result.output_tokens
        record["retries"] = result.repair_cycles
        record["tool_calls"] = result.tool_calls
        record["skipped_render_ids"] = result.skipped_render_ids
        # No diagram_ir or sym_table available for this strategy
        record["ir_diagnostics"] = None
        record["sympy_property_checks"] = []
        record["phase_traces"] = result.phase_traces
        record["phase_usage"] = result.phase_usage
    elif isinstance(result, StructuredRunResult):
        record["tikz_code"] = result.tikz
        record["diagram_ir"] = result.diagram_ir.model_dump(mode="json")
        svg = result.svg

        ir_diagnostics_data = None
        try:
            ir_diagnostics_data = classify_ir(result.diagram_ir).to_dict()
        except Exception:
            pass
        record["ir_diagnostics"] = ir_diagnostics_data
        record["input_tokens"] = result.input_tokens
        record["output_tokens"] = result.output_tokens

        sympy_property_checks: list[dict] = []
        if result.sym_table is not None and scenario.get("expected_properties"):
            sympy_property_checks = _validate_properties_sympy(
                scenario["expected_properties"],
                result.sym_table,
            )
        record["sympy_property_checks"] = sympy_property_checks

        if result.recipe_metadata is not None:
            record["recipe_metadata"] = {
                "selected_recipes": result.recipe_metadata.selected_recipes,
                "unmatched_concepts": result.recipe_metadata.unmatched_concepts,
                "selection_input_tokens": result.recipe_metadata.selection_input_tokens,
                "selection_output_tokens": result.recipe_metadata.selection_output_tokens,
                "attempt_traces": [
                    {"attempt": t.attempt, "dsl_json": t.dsl_json, "error": t.error, "stage": t.stage}
                    for t in result.recipe_metadata.attempt_traces
                ],
            }
        else:
            record["recipe_metadata"] = None

        # Query eval phase — test follow-up questions via query_diagram tool
        queries = scenario.get("queries", [])
        if queries:
            if result.sym_full is not None:
                record["query_results"] = await _run_query_phase(
                    queries, result.sym_full, model
                )
            else:
                logger.warning(
                    "Scenario %s has queries but sym_full is None — skipping query phase",
                    scenario["id"],
                )
                record["query_results"] = [
                    {"question": q["question"], "tool_called": False, "error": "sym_full unavailable"}
                    for q in queries
                ]
    else:
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
                tolerance=_TIKZ_CHECK_TOLERANCE,
            )
            tikz_check_results[prop["name"]] = {
                "passed": prop_result,
                "type": prop["type"],
                "skipped": prop_result is None,
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

        required_canvas = scenario.get("required_canvas", {})
        if required_canvas:
            record["canvas_checks"] = validate_required_canvas(tikz_code, required_canvas)

        expected_points = scenario.get("expected_points", {})
        if expected_points:
            record["expected_point_checks"] = validate_expected_points(
                coords,
                expected_points,
                tolerance=scenario.get("coordinate_tolerance", _DEFAULT_POINT_TOLERANCE),
            )

    # LLM judge (code review)
    if llm_judge and tikz_code:
        if strategy_name not in ("structured",):
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
        else:
            record["llm_judge_score"] = None
            record["llm_judge_reasoning"] = "(skipped for structured strategy)"

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

    # Structural checks (polygon count, etc.)
    structural_check_defs = scenario.get("structural_checks", [])
    if structural_check_defs:
        record["structural_checks"] = _run_structural_checks(
            structural_check_defs,
            record.get("diagram_ir"),
            record.get("tikz_code"),
        )

    _finalize_gate_status(record)
    return record


# ---------------------------------------------------------------------------
# Gate helpers
# ---------------------------------------------------------------------------

def _run_structural_checks(
    structural_checks: list[dict],
    diagram_ir: dict | None,
    tikz_code: str | None,
) -> dict[str, dict]:
    """Run structural checks against the IR (preferred) or TikZ code.

    Currently supports: polygon_count — assert at least N polygons with a given side count.
    Returns a dict mapping check name -> {"passed": bool, "message": str}.
    """
    results: dict[str, dict] = {}
    for check in structural_checks:
        name = check["name"]
        ctype = check["type"]
        args = check.get("args", {})
        try:
            if ctype == "polygon_count":
                min_count = int(args.get("min", 1))
                sides = args.get("sides")  # None means any polygon
                count = 0
                if diagram_ir is not None:
                    # Count Polygon, PolygonExterior, and Triangle defs in IR
                    for defn in diagram_ir.get("define", []):
                        kind = defn.get("kind")
                        if kind == "polygon":
                            pts = defn.get("points", [])
                            n = len(pts)
                            if sides is None or n == sides:
                                count += 1
                        elif kind == "polygon_exterior":
                            n = defn.get("sides", 4)
                            if sides is None or n == sides:
                                count += 1
                        elif kind == "triangle":
                            n = 3
                            if sides is None or n == sides:
                                count += 1
                elif tikz_code is not None:
                    # Fallback: count \tkzDrawPolygon / \tkzFillPolygon in TikZ
                    import re as _re
                    for m in _re.finditer(r'\\tkz(?:Draw|Fill)Polygon\(([^)]*)\)', tikz_code):
                        pts = [p.strip() for p in m.group(1).split(",") if p.strip()]
                        n = len(pts)
                        if sides is None or n == sides:
                            count += 1
                ok = count >= min_count
                msg = "" if ok else (
                    f"expected at least {min_count} polygon(s) with "
                    f"{'any' if sides is None else sides} sides, found {count}"
                )
                results[name] = {"passed": ok, "message": msg}
            else:
                results[name] = {"passed": True, "message": f"(skipped: unknown type {ctype!r})"}
        except Exception as exc:
            results[name] = {"passed": False, "message": f"Error: {exc}"}
    return results


def _collect_check_outcomes(record: dict) -> tuple[list[str], list[str], bool]:
    """Return (failures, skipped, had_checks) across deterministic checks."""
    failures: list[str] = []
    skipped: list[str] = []
    had_checks = False

    for name, result in (record.get("tikz_checks") or {}).items():
        if not isinstance(result, dict):
            continue
        had_checks = True
        passed = result.get("passed")
        if passed is False:
            failures.append(name)
        elif result.get("skipped") is True or passed is None:
            skipped.append(name)

    canvas_checks = record.get("canvas_checks")
    if isinstance(canvas_checks, dict):
        had_checks = True
        if not canvas_checks.get("passed", False):
            missing = canvas_checks.get("missing") or ["required_canvas"]
            failures.extend(f"canvas:{name}" for name in missing)

    expected_point_checks = record.get("expected_point_checks")
    if isinstance(expected_point_checks, dict):
        had_checks = True
        failures.extend(f"point:{name}:missing" for name in expected_point_checks.get("missing", []))
        failures.extend(
            f"point:{name}:mismatch"
            for name in sorted((expected_point_checks.get("mismatches") or {}).keys())
        )

    structural_checks = record.get("structural_checks")
    if isinstance(structural_checks, dict):
        had_checks = True
        for name, result in structural_checks.items():
            if isinstance(result, dict) and result.get("passed") is False:
                failures.append(f"structural:{name}")

    query_results = record.get("query_results", [])
    if query_results:
        had_checks = True
        for qidx, qr in enumerate(query_results):
            if qr.get("error"):
                failures.append(f"query:{qidx}:error")
            elif not qr.get("tool_called"):
                failures.append(f"query:{qidx}:tool_not_called")
            elif qr.get("query_type_match") is False:
                failures.append(f"query:{qidx}:wrong_query_type")

    return failures, skipped, had_checks


def _finalize_gate_status(record: dict) -> None:
    """Populate deterministic_pass, gate_status, and gate_failures."""
    failures, skipped, had_checks = _collect_check_outcomes(record)

    if failures:
        record["deterministic_pass"] = False
    elif skipped:
        record["deterministic_pass"] = None
    else:
        record["deterministic_pass"] = True if had_checks or record.get("tikz_code") else None

    gate_failures: list[str] = []
    if not record.get("generation_success"):
        gate_failures.append("generation")
    if not record.get("svg_rendered"):
        gate_failures.append("svg_render")
    svg_checks = record.get("svg_checks")
    if svg_checks and not svg_checks.get("passed", False):
        for failure in svg_checks.get("failures", []):
            gate_failures.append(f"svg:{failure}")
    gate_failures.extend(failures)
    record["gate_failures"] = gate_failures

    if gate_failures:
        record["gate_status"] = "fail"
    elif skipped:
        record["gate_status"] = "soft_pass"
    elif record.get("svg_rendered"):
        record["gate_status"] = "pass"
    else:
        record["gate_status"] = "fail"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(description="Run geometry diagram evals")
    parser.add_argument(
        "--scenarios",
        default="evals/scenarios_core.yaml",
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
    benchmark = scenarios_path.stem

    # Build run ID and output path
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output)
    output_path = output_dir / f"{run_id}.jsonl"
    svg_output_dir = output_dir / run_id / "svgs"
    traces_output_dir = output_dir / run_id / "traces"

    total = len(args.strategies) * len(scenarios) * args.repeats
    print(f"Running {total} evals  (run_id={run_id})")
    print(f"Output: {output_path}")
    print(f"Max concurrency: {args.max_concurrency}")
    if args.llm_judge:
        print(f"LLM judge: on  (model: {args.judge_model})")
    if args.visual_judge:
        print(f"Visual judge: on")
    print()

    renderer_url = os.getenv("TIKZ_RENDERER_URL", "http://localhost:8001")
    if not check_renderer_health(renderer_url):
        print(f"ERROR: TikZ renderer is not reachable at {renderer_url}.")
        print("Start it with: docker run -p 8001:8001 tikz-renderer")
        sys.exit(1)

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
                benchmark,
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
            _externalize_traces(record, traces_output_dir)
            _print_record(record)
            _append_jsonl(output_path, record)
            all_records.append(record)

    _print_summary(all_records)
    print(f"\nResults written to {output_path}")
    print(f"SVGs written to {svg_output_dir}")


if __name__ == "__main__":
    asyncio.run(main())
