"""AI judge for benchmark rubric grading.

Grades each rubric item as yes/no (1/0) for a benchmark run result.

Usage:
    python -m benchmark.ai_judge --run-id 20260409-123456 --model anthropic:claude-sonnet-4-6
"""
from __future__ import annotations
import argparse
import asyncio
import json
from pathlib import Path
from datetime import datetime

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.messages import BinaryContent

from benchmark.db import get_db, list_results_for_run, upsert_annotation, get_run
from benchmark.models import load_definition, BenchmarkDefinition

_BENCHMARK_ROOT = Path(__file__).parent
_DB_PATH = _BENCHMARK_ROOT / "data" / "benchmark.db"
_DEFINITIONS_DIR = _BENCHMARK_ROOT / "definitions"
_REFERENCES_DIR = _BENCHMARK_ROOT / "references"


class _RubricJudgment(BaseModel):
    """Binary yes/no judgment for each rubric item."""
    answers: dict[str, bool]


async def judge_result(result: dict, definition: BenchmarkDefinition, model: str) -> dict[str, bool]:
    """Judge a single result against its full rubric.

    Returns a mapping of rubric_item_id to bool. Returns {} if result cannot
    be judged (missing SVG).
    """
    prompt_id = result["prompt_id"]
    prompt = next((p for p in definition.prompts if p.id == prompt_id), None)
    if prompt is None:
        return {}

    rubric = definition.effective_rubric(prompt_id)
    if not rubric:
        return {}

    svg_path = result.get("svg_path")
    if not svg_path or not Path(svg_path).exists():
        return {}

    svg = Path(svg_path).read_text()

    import cairosvg
    png_data = cairosvg.svg2png(bytestring=svg.encode(), background_color="white")

    has_reference = False
    ref_png_data = None
    if prompt.reference_svg:
        ref_path = _REFERENCES_DIR / prompt.reference_svg
        if ref_path.exists():
            ref_svg = ref_path.read_text()
            ref_png_data = cairosvg.svg2png(bytestring=ref_svg.encode(), background_color="white")
            has_reference = True

    ref_note = "\nYou will also be shown a reference (gold-standard) diagram for comparison." if has_reference else ""

    system_prompt = (
        "You are an expert geometry teacher evaluating a diagram.\n\n"
        "You will be shown a rendered geometry diagram and the original prompt."
        f"{ref_note}\n\n"
        "For each rubric item below, answer YES (true) or NO (false).\n\n"
        "Be strict: only mark YES if the item is clearly satisfied in the diagram.\n\n"
        "Respond with a JSON object mapping each item ID to true or false."
    )

    rubric_lines = "\n".join(f"- {item.id}: {item.text}" for item in rubric)
    user_text = f"Prompt: {prompt.prompt}\n\nRubric items:\n{rubric_lines}"

    user_content: list = [BinaryContent(data=png_data, media_type="image/png")]
    if has_reference and ref_png_data is not None:
        user_content.append(BinaryContent(data=ref_png_data, media_type="image/png"))
    user_content.append(user_text)

    agent: Agent[None, _RubricJudgment] = Agent(
        model,
        system_prompt=system_prompt,
        output_type=_RubricJudgment,
    )

    result_obj = await agent.run(user_content)
    return result_obj.output.answers


async def judge_run(
    run_id: str,
    model: str,
    annotator_id: str,
    db_path: Path | None = None,
) -> None:
    """Judge all results for a run and store annotations in the DB."""
    conn = get_db(db_path or _DB_PATH)

    run = get_run(conn, run_id)
    if run is None:
        print(f"Run not found: {run_id}")
        return

    benchmark_id = run["benchmark_id"]
    def_path = _DEFINITIONS_DIR / f"{benchmark_id}.yaml"
    definition = load_definition(def_path)

    results = list_results_for_run(conn, run_id)

    judged = 0
    skipped = 0
    for result in results:
        if not result["generation_success"]:
            skipped += 1
            continue

        prompt_id = result["prompt_id"]
        result_id = result["result_id"]

        answers = await judge_result(result, definition, model)
        if not answers:
            skipped += 1
            continue

        for item_id, bool_value in answers.items():
            upsert_annotation(conn, result_id, item_id, annotator_id, "ai", int(bool_value))

        yes_count = sum(1 for v in answers.values() if v)
        print(f"  Judged {prompt_id}: {yes_count}/{len(answers)} yes")
        judged += 1

    print(f"\nDone. Judged {judged} results, skipped {skipped}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AI judge on benchmark results")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model", default="anthropic:claude-sonnet-4-6")
    parser.add_argument(
        "--annotator-id",
        default=None,
        help="e.g. ai:claude-sonnet-4-6; defaults to ai:{model}",
    )
    args = parser.parse_args()
    annotator_id = args.annotator_id or f"ai:{args.model.split(':')[-1]}"
    asyncio.run(judge_run(args.run_id, args.model, annotator_id))


if __name__ == "__main__":
    main()
