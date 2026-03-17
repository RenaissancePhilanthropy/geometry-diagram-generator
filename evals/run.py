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

from evals.ir_diagnostics import classify_ir
from strategies.base import DEFAULT_AGENT_MODEL, SubstanceStrategy
from strategies.raw_code import RawCodeStrategy
from strategies.raw_code_with_revise import RawCodeWithReviseStrategy
from strategies.plan_and_code import PlanAndCodeStrategy
from strategies.structured import StructureStrategy, StructuredRunResult
from strategies.structured_plus_refine import StructuredPlusRefineStrategy
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

_STRATEGY_MAP: dict[str, type[SubstanceStrategy]] = {
    "raw_code": RawCodeStrategy,
    "raw_code_with_revise": RawCodeWithReviseStrategy,
    "plan_and_code": PlanAndCodeStrategy,
    "structured": StructureStrategy,
    "structured_plus_refine": StructuredPlusRefineStrategy,
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
    "equidistant_from_sides",
}

# Tolerance for geometric checks. Relaxed from 1e-4 to handle LLM-chosen
# coordinates that are approximate (3 decimal places → ~0.001 rounding error).
_TIKZ_CHECK_TOLERANCE = 0.01
_DEFAULT_POINT_TOLERANCE = 1e-4
_CANVAS_FEATURES = {"grid", "axes"}


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

        tags = raw.get("tags", [])
        if tags is None:
            tags = []
        if not isinstance(tags, list):
            raise ValueError(f"{where} ({scenario_id}): 'tags' must be a list when provided")
        for i, tag in enumerate(tags, start=1):
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError(
                    f"{where} ({scenario_id}) tags[{i}]: must be a non-empty string"
                )

        required_canvas = raw.get("required_canvas", {})
        if required_canvas is None:
            required_canvas = {}
        if not isinstance(required_canvas, dict):
            raise ValueError(
                f"{where} ({scenario_id}): 'required_canvas' must be an object when provided"
            )
        normalized_canvas: dict[str, bool] = {}
        for key, value in required_canvas.items():
            if key not in _CANVAS_FEATURES:
                supported = ", ".join(sorted(_CANVAS_FEATURES))
                raise ValueError(
                    f"{where} ({scenario_id}): unsupported required_canvas key {key!r}; "
                    f"supported: {supported}"
                )
            if not isinstance(value, bool):
                raise ValueError(
                    f"{where} ({scenario_id}) required_canvas[{key!r}]: must be a boolean"
                )
            normalized_canvas[key] = value

        expected_points = raw.get("expected_points", {})
        if expected_points is None:
            expected_points = {}
        if not isinstance(expected_points, dict):
            raise ValueError(
                f"{where} ({scenario_id}): 'expected_points' must be an object when provided"
            )
        normalized_points: dict[str, list[float]] = {}
        for name, coords in expected_points.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError(
                    f"{where} ({scenario_id}) expected_points: point names must be non-empty strings"
                )
            if (
                not isinstance(coords, list)
                or len(coords) != 2
                or not all(isinstance(v, (int, float)) for v in coords)
            ):
                raise ValueError(
                    f"{where} ({scenario_id}) expected_points[{name!r}]: "
                    "must be a 2-item numeric list"
                )
            normalized_points[name] = [float(coords[0]), float(coords[1])]

        coordinate_tolerance = raw.get("coordinate_tolerance", _DEFAULT_POINT_TOLERANCE)
        if not isinstance(coordinate_tolerance, (int, float)) or coordinate_tolerance <= 0:
            raise ValueError(
                f"{where} ({scenario_id}): 'coordinate_tolerance' must be a positive number"
            )

        tier = raw.get("tier")
        if tier is not None and (not isinstance(tier, int) or tier < 1):
            raise ValueError(f"{where} ({scenario_id}): 'tier' must be a positive integer")
        normalized.append(
            {
                "id": scenario_id,
                "tier": tier,
                "tags": list(tags),
                "prompt": prompt,
                "expected_properties": normalized_props,
                "required_labels": list(required_labels),
                "required_entities": list(required_entities),
                "required_canvas": normalized_canvas,
                "expected_points": normalized_points,
                "coordinate_tolerance": float(coordinate_tolerance),
            }
        )

    return normalized


# ---------------------------------------------------------------------------
# SymPy property validation helpers
# ---------------------------------------------------------------------------

def _validate_properties_sympy(
    expected_properties: list[dict],
    sym_float: dict,
    tol: float = 5e-3,
) -> list[dict]:
    """Validate scenario expected_properties against a float-coords symbol table.
    sym_float maps point_id -> (x, y) float tuples.
    Returns list of {name, type, passed, message} dicts.
    """
    import math
    results = []
    for prop in expected_properties:
        name = prop.get("name", "")
        ptype = prop.get("type", "")
        args = prop.get("args", [])
        try:
            passed, msg = _check_sympy_property(ptype, args, sym_float, tol)
        except Exception as exc:
            passed, msg = False, f"Error: {exc}"
        results.append({"name": name, "type": ptype, "passed": passed, "message": msg})
    return results


def _check_sympy_property(ptype: str, args: list, sym_float: dict, tol: float) -> tuple[bool, str]:
    import math

    def pt(name: str) -> tuple[float, float]:
        p = sym_float.get(name)
        if p is None:
            raise KeyError(f"Point {name!r} not in symbol table")
        return p

    def dist(a: tuple, b: tuple) -> float:
        return math.sqrt((a[0] - b[0])**2 + (a[1] - b[1])**2)

    match ptype:
        case "right_angle":
            a, o, b = args[0]
            A, O, B = pt(a), pt(o), pt(b)
            va = (A[0] - O[0], A[1] - O[1])
            vb = (B[0] - O[0], B[1] - O[1])
            dot = va[0]*vb[0] + va[1]*vb[1]
            mag_a = math.sqrt(va[0]**2 + va[1]**2)
            mag_b = math.sqrt(vb[0]**2 + vb[1]**2)
            if mag_a < 1e-12 or mag_b < 1e-12:
                return False, "Degenerate angle"
            cos_v = max(-1.0, min(1.0, dot / (mag_a * mag_b)))
            ang = math.acos(cos_v)
            ok = abs(ang - math.pi / 2) < tol
            return ok, "" if ok else f"angle={math.degrees(ang):.2f}° (expected 90°)"

        case "midpoint":
            m_id, a_id, b_id = args[0], args[1], args[2]
            M, A, B = pt(m_id), pt(a_id), pt(b_id)
            d_ma = dist(M, A)
            d_mb = dist(M, B)
            ok = abs(d_ma - d_mb) < tol
            return ok, "" if ok else f"|MA|={d_ma:.4f} ≠ |MB|={d_mb:.4f}"

        case "collinear":
            pts = [pt(n) for n in args[0]]
            (x1, y1), (x2, y2), (x3, y3) = pts[0], pts[1], pts[2]
            cross = (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1)
            ok = abs(cross) < tol
            return ok, "" if ok else f"Points {args[0]} are not collinear (cross={cross:.4f})"

        case "equal_lengths":
            d1 = dist(pt(args[0][0]), pt(args[0][1]))
            d2 = dist(pt(args[1][0]), pt(args[1][1]))
            ok = abs(d1 - d2) < tol
            return ok, "" if ok else f"|{args[0]}|={d1:.4f} ≠ |{args[1]}|={d2:.4f}"

        case "parallel":
            A, B = pt(args[0][0]), pt(args[0][1])
            C, D = pt(args[1][0]), pt(args[1][1])
            v1 = (B[0] - A[0], B[1] - A[1])
            v2 = (D[0] - C[0], D[1] - C[1])
            cross = v1[0]*v2[1] - v1[1]*v2[0]
            ok = abs(cross) < tol
            return ok, "" if ok else "Lines are not parallel"

        case "perpendicular":
            A, B = pt(args[0][0]), pt(args[0][1])
            C, D = pt(args[1][0]), pt(args[1][1])
            v1 = (B[0] - A[0], B[1] - A[1])
            v2 = (D[0] - C[0], D[1] - C[1])
            dot = v1[0]*v2[0] + v1[1]*v2[1]
            ok = abs(dot) < tol
            return ok, "" if ok else f"Lines not perpendicular (dot={dot:.4f})"

        case "point_on_line" | "point_on_segment":
            P = pt(args[0])
            A, B = pt(args[1][0]), pt(args[1][1])
            dx, dy = B[0] - A[0], B[1] - A[1]
            length = math.sqrt(dx**2 + dy**2)
            if length < 1e-12:
                return False, "Degenerate line"
            cross = abs((P[0] - A[0]) * dy - (P[1] - A[1]) * dx) / length
            ok = cross < tol
            return ok, "" if ok else f"{args[0]} not on line (dist={cross:.4f})"

        case "label_present" | "mark_present":
            return True, "(skipped: rendering-only check)"

        case _:
            return True, f"(skipped: unsupported type {ptype!r})"


# ---------------------------------------------------------------------------
# Per-scenario runner
# ---------------------------------------------------------------------------

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

    # StructuredRunResult: TikZ and SVG are produced deterministically (no tool calls).
    if isinstance(result, StructuredRunResult):
        record["tikz_code"] = result.tikz
        record["diagram_ir"] = result.diagram_ir.model_dump(mode="json")
        svg = result.svg

        ir_diagnostics_data = None
        try:
            ir_diagnostics_data = classify_ir(result.diagram_ir).to_dict()
        except Exception:
            pass
        record["ir_diagnostics"] = ir_diagnostics_data

        sympy_property_checks: list[dict] = []
        if result.sym_table is not None and scenario.get("expected_properties"):
            sympy_property_checks = _validate_properties_sympy(
                scenario["expected_properties"],
                result.sym_table,
            )
        record["sympy_property_checks"] = sympy_property_checks
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

    _finalize_gate_status(record)
    return record


# ---------------------------------------------------------------------------
# Gate helpers
# ---------------------------------------------------------------------------

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
# Output helpers
# ---------------------------------------------------------------------------

def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def _tikz_check_summary(record: dict) -> str:
    """Return a compact tikz check summary string like 'TIK:3/4(1skip)'."""
    tc = record.get("tikz_checks") or {}
    if not tc:
        return ""
    total = len(tc)
    passed = sum(
        1 for v in tc.values()
        if isinstance(v, dict) and v.get("passed") is True
    )
    skipped = sum(
        1 for v in tc.values()
        if isinstance(v, dict) and v.get("skipped") is True
    )
    if skipped:
        return f" TIK:{passed}/{total}({skipped}skip)"
    return f" TIK:{passed}/{total}"


def _gate_summary(record: dict) -> str:
    status = record.get("gate_status")
    if not status:
        return ""
    return f" G:{status}"


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
    tik_str = _tikz_check_summary(record)
    gate_str = _gate_summary(record)
    print(
        f"  [{status}] {record['scenario_id']:<25} {repeat} {svg} {checks} "
        f"{duration:>7}{judge_str}{tik_str}{gate_str}{error}"
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
        gate_ok = sum(1 for r in recs if r.get("gate_status") == "pass")
        gate_soft = sum(1 for r in recs if r.get("gate_status") == "soft_pass")
        avg_s = sum(r["duration_s"] for r in recs if r["duration_s"]) / max(n, 1)
        retry_rate = sum(r.get("retries", 0) for r in recs) / max(n, 1)

        judge_scores = [r["llm_judge_score"] for r in recs if r.get("llm_judge_score") is not None]
        judge_str = f"  judge:{sum(judge_scores)/len(judge_scores):.1f}/5" if judge_scores else ""
        gate_judge_scores = [
            r["llm_judge_score"]
            for r in recs
            if r.get("gate_status") == "pass" and r.get("llm_judge_score") is not None
        ]
        gate_judge_str = (
            f"  judge(pass):{sum(gate_judge_scores)/len(gate_judge_scores):.1f}/5"
            if gate_judge_scores else ""
        )

        # Tikz check aggregation
        tik_total = sum(len(r.get("tikz_checks") or {}) for r in recs)
        tik_pass = sum(
            sum(1 for v in (r.get("tikz_checks") or {}).values()
                if isinstance(v, dict) and v.get("passed") is True)
            for r in recs
        )
        tik_skip = sum(
            sum(1 for v in (r.get("tikz_checks") or {}).values()
                if isinstance(v, dict) and v.get("skipped") is True)
            for r in recs
        )
        tik_str = ""
        if tik_total:
            tik_str = f"  tik:{tik_pass}/{tik_total}"
            if tik_skip:
                tik_str += f"({tik_skip}skip)"

        print(
            f"  {strategy:<12}  gen:{gen_ok}/{n}  svg:{svg_ok}/{n}  "
            f"svgchk:{svg_chk_ok}/{n}  gate:{gate_ok}/{n}"
            f" soft:{gate_soft}/{n}  retries:{retry_rate:.1f}"
            f"{judge_str}{gate_judge_str}{tik_str}  avg:{avg_s:.1f}s"
        )


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
            _print_record(record)
            _append_jsonl(output_path, record)
            all_records.append(record)

    _print_summary(all_records)
    print(f"\nResults written to {output_path}")
    print(f"SVGs written to {svg_output_dir}")


if __name__ == "__main__":
    asyncio.run(main())
