#!/usr/bin/env python3
"""
dry_run.py — Run benchmark prompt(s) end-to-end without touching the
benchmark SQLite database. Real LLM calls are made; per-prompt SVGs and
an aggregate JSONL summary are written to disk.

Pipeline per prompt:
  1. Load a BenchmarkDefinition YAML
  2. Generate an SVG via the selected strategy (no Docker required)
  3. Optionally run the AI judge against the prompt's rubric
  4. Record per-item answers + weighted/unweighted scores

Usage:
  # Single prompt
  python -m benchmark.genexam.dry_run --prompt-id Mathematics_72

  # Random sample of N prompts (reproducible with --seed)
  python -m benchmark.genexam.dry_run --sample 5 --seed 0

  # Run everything in the definition
  python -m benchmark.genexam.dry_run --all

  # Filter by tier before sampling
  python -m benchmark.genexam.dry_run --sample 3 --tier 1 --seed 42

  # Generation only, no judge
  python -m benchmark.genexam.dry_run --sample 5 --no-judge

  # Use a different strategy
  python -m benchmark.genexam.dry_run --sample 5 --strategy structured
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from benchmark.models import BenchmarkDefinition, BenchmarkPrompt, load_definition
from strategies.base import SubstanceStrategy
from strategies.recipe import RecipeStrategy
from strategies.structured import StructureStrategy
from strategies.raw_code import RawCodeStrategy
from strategies.raw_code_with_revise import RawCodeWithReviseStrategy
from strategies.raw_svg import RawSVGStrategy
from strategies.raw_svg_with_revise import RawSVGWithReviseStrategy
from ir.renderer import SVGRenderer

_STRATEGIES: dict[str, type[SubstanceStrategy]] = {
    "recipe": RecipeStrategy,
    "structured": StructureStrategy,
    "raw_code": RawCodeStrategy,
    "raw_code_with_revise": RawCodeWithReviseStrategy,
    "raw_svg": RawSVGStrategy,
    "raw_svg_with_revise": RawSVGWithReviseStrategy,
}


def _make_strategy(name: str, enable_cache: bool = False) -> SubstanceStrategy:
    cls = _STRATEGIES[name]
    if cls is RecipeStrategy:
        return RecipeStrategy(use_recipes=True, enable_cache=enable_cache)
    return cls(enable_cache=enable_cache)


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DEFINITION = _REPO_ROOT / "benchmark" / "definitions" / "bench_genexam.yaml"
_DEFAULT_OUT_DIR = Path("/tmp/bench_dry_run")


@dataclass
class PromptOutcome:
    prompt_id: str
    tier: int | None
    status: str  # "ok" | "gen_failed" | "judge_failed"
    error: str | None = None
    svg_path: str | None = None
    svg_length: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    gen_seconds: float = 0.0
    judge_seconds: float = 0.0
    answers: dict[str, bool] = field(default_factory=dict)
    unweighted_earned: int = 0
    unweighted_total: int = 0
    weighted_earned: float = 0.0
    weighted_total: float = 0.0
    gen_attempts: int = 0           # total strategy.run() invocations (including outer retries)
    error_details: str | None = None  # validation error summary from last failed attempt
    failed_payload: str | None = None  # raw model output from last output_validation failure


def _select_prompts(
    definition: BenchmarkDefinition,
    prompt_id: str | None,
    sample: int | None,
    run_all: bool,
    tier: int | None,
    seed: int | None,
) -> list[BenchmarkPrompt]:
    if prompt_id is not None:
        entry = next((p for p in definition.prompts if p.id == prompt_id), None)
        if entry is None:
            raise SystemExit(f"ERROR: prompt_id {prompt_id!r} not found")
        return [entry]

    candidates = list(definition.prompts)
    if tier is not None:
        candidates = [p for p in candidates if p.tier == tier]
    if not candidates:
        raise SystemExit("ERROR: no prompts match the filter")

    if run_all:
        return candidates

    if sample is None:
        raise SystemExit("ERROR: specify one of --prompt-id, --sample N, or --all")

    rng = random.Random(seed)
    k = min(sample, len(candidates))
    return rng.sample(candidates, k)


def _get_validation_diagnostics(strategy: SubstanceStrategy) -> tuple[str | None, str | None]:
    """Pull error_details and failed_payload from the last output_validation trace, if any."""
    meta = getattr(strategy, "_partial_recipe_metadata", None)
    if meta is None:
        return None, None
    for trace in reversed(meta.attempt_traces):
        if trace.stage == "output_validation":
            return trace.error, trace.raw_output
    return None, None


_W = 58  # width of the right-fill in section headers


def _sec(title: str) -> str:
    return f"─ {title} {'─' * max(2, _W - len(title))}─"


async def _process_one(
    entry: BenchmarkPrompt,
    definition: BenchmarkDefinition,
    args: argparse.Namespace,
    out_dir: Path,
    semaphore: asyncio.Semaphore,
    verbose: bool = False,
    enable_cache: bool = False,
) -> PromptOutcome:
    async with semaphore:
        outcome = PromptOutcome(prompt_id=entry.id, tier=entry.tier, status="ok")
        rubric = definition.effective_rubric(entry.id)

        if verbose:
            prompt_preview = entry.prompt if len(entry.prompt) <= 130 else entry.prompt[:127] + "..."
            print(_sec("Prompt"))
            print(f"  id         : {entry.id}")
            print(f"  tier       : {entry.tier}")
            print(f"  tags       : {entry.tags}")
            print(f"  prompt     : {prompt_preview}")
            print(f"  rubric     : {len(rubric)} items")

        renderer = SVGRenderer()
        max_outer_attempts = 1 + args.gen_retries

        t0 = time.perf_counter()
        last_exc: Exception | None = None
        result = None
        all_traces: list = []
        for outer_attempt in range(max_outer_attempts):
            strategy = _make_strategy(args.strategy, enable_cache=enable_cache)
            if outer_attempt > 0 and not verbose:
                print(f"  [{entry.id}] retrying generation (attempt {outer_attempt + 1}/{max_outer_attempts})")
            try:
                result = await strategy.run(
                    prompt=entry.prompt,
                    model=args.model,
                    renderer=renderer,
                )
                last_exc = None
                outcome.gen_attempts = outer_attempt + 1
                meta = getattr(result, "recipe_metadata", None)
                if meta:
                    all_traces.extend(meta.attempt_traces)
                break
            except Exception as exc:
                last_exc = exc
                outcome.gen_attempts = outer_attempt + 1
                # Capture diagnostics from this attempt before overwriting strategy
                err_details, failed_payload = _get_validation_diagnostics(strategy)
                if err_details:
                    outcome.error_details = err_details
                    outcome.failed_payload = failed_payload
                meta = getattr(strategy, "_partial_recipe_metadata", None)
                if meta:
                    all_traces.extend(meta.attempt_traces)

        outcome.gen_seconds = time.perf_counter() - t0

        if verbose:
            print(_sec("Generation"))
            for t in all_traces:
                if t.stage != "success":
                    first_line = (t.error or "").splitlines()[0][:120]
                    print(f"Attempt {t.attempt} {t.stage} error: {first_line}")

        if last_exc is not None or result is None:
            outcome.status = "gen_failed"
            outcome.error = f"{type(last_exc).__name__}: {last_exc}" if last_exc else "unknown"
            if verbose:
                print(f"  GEN FAILED: {outcome.error}")
                if outcome.error_details:
                    for line in outcome.error_details.splitlines()[:5]:
                        print(f"  {line}")
            else:
                log_line = f"  [{entry.id}] GEN FAILED (attempt {outcome.gen_attempts}/{max_outer_attempts}): {outcome.error}"
                if outcome.error_details:
                    diag_preview = "\n    ".join(outcome.error_details.splitlines()[:3])
                    log_line += f"\n    {diag_preview}"
                print(log_line)
            return outcome

        svg = result.svg or ""
        svg_path = out_dir / f"{entry.id}.svg"
        svg_path.write_text(svg)
        outcome.svg_path = str(svg_path)
        outcome.svg_length = len(svg)
        outcome.input_tokens = result.input_tokens or 0
        outcome.output_tokens = result.output_tokens or 0

        if verbose:
            print(f"  model      : {args.model}")
            print(f"  svg_length : {outcome.svg_length}")
            print(f"  svg_path   : {outcome.svg_path}")
            print(f"  tokens in  : {outcome.input_tokens}")
            print(f"  tokens out : {outcome.output_tokens}")
        else:
            print(
                f"  [{entry.id}] gen ok  "
                f"tier={entry.tier} svg={outcome.svg_length}ch "
                f"tok={outcome.input_tokens}/{outcome.output_tokens} "
                f"in {outcome.gen_seconds:.1f}s"
            )

        if args.no_judge:
            return outcome

        from benchmark.ai_judge import judge_result

        fake_result = {
            "prompt_id": entry.id,
            "generation_success": True,
            "svg_path": str(svg_path),
        }
        t0 = time.perf_counter()
        try:
            answers = await judge_result(fake_result, definition, args.judge_model)
        except Exception as exc:
            outcome.status = "judge_failed"
            outcome.error = f"{type(exc).__name__}: {exc}"
            outcome.judge_seconds = time.perf_counter() - t0
            if verbose:
                print(_sec("AI Judge"))
                print(f"  JUDGE FAILED: {outcome.error}")
            else:
                print(f"  [{entry.id}] JUDGE FAILED: {outcome.error}")
            return outcome
        outcome.judge_seconds = time.perf_counter() - t0
        outcome.answers = answers

        rubric_by_id = {r.id: r for r in rubric}
        for item_id, passed in answers.items():
            item = rubric_by_id.get(item_id)
            outcome.unweighted_total += 1
            if passed:
                outcome.unweighted_earned += 1
            if item and item.weight is not None:
                outcome.weighted_total += item.weight
                if passed:
                    outcome.weighted_earned += item.weight

        pct = (100 * outcome.weighted_earned / outcome.weighted_total) if outcome.weighted_total > 0 else 0.0

        if verbose:
            print(_sec("AI Judge"))
            for item_id, passed in answers.items():
                item = rubric_by_id.get(item_id)
                sym = "✓" if passed else "✗"
                wt_str = f"weight={item.weight:.2f}" if item and item.weight is not None else ""
                text = item.text if item else item_id
                print(f"  {sym} {item_id} ({wt_str}): {text}")
            print(_sec("Score"))
            print(f"  unweighted : {outcome.unweighted_earned}/{outcome.unweighted_total}")
            print(f"  weighted   : {outcome.weighted_earned:.3f}/{outcome.weighted_total:.3f} ({pct:.1f}%)")
        else:
            print(
                f"  [{entry.id}] judge   "
                f"{outcome.unweighted_earned}/{outcome.unweighted_total} items, "
                f"weighted {outcome.weighted_earned:.2f}/{outcome.weighted_total:.2f} "
                f"({pct:.0f}%) in {outcome.judge_seconds:.1f}s"
            )
        return outcome


async def main_async(args: argparse.Namespace) -> int:
    definition = load_definition(Path(args.definition))
    prompts = _select_prompts(
        definition,
        prompt_id=args.prompt_id,
        sample=args.sample,
        run_all=args.all,
        tier=args.tier,
        seed=args.seed,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"─ Dry Run ─────────────────────────────────────────────")
    print(f"  definition : {args.definition}")
    print(f"  prompts    : {len(prompts)}")
    print(f"  strategy   : {args.strategy}")
    print(f"  model      : {args.model}")
    print(f"  judge      : {'skipped' if args.no_judge else args.judge_model}")
    print(f"  concurrency: {args.concurrency}")
    print(f"  out_dir    : {out_dir}")
    print(f"─ Running ─────────────────────────────────────────────")

    # Verbose per-prompt output: always on for single prompt, opt-in for batch.
    verbose = len(prompts) == 1 or getattr(args, "verbose", False)

    enable_cache = len(prompts) > 1
    semaphore = asyncio.Semaphore(args.concurrency)
    coros = [_process_one(p, definition, args, out_dir, semaphore, verbose=verbose, enable_cache=enable_cache) for p in prompts]
    outcomes = await asyncio.gather(*coros)

    outcomes.sort(key=lambda o: o.prompt_id)

    # Per-prompt JSONL
    jsonl_path = out_dir / "dry_run.jsonl"
    with jsonl_path.open("w") as fh:
        for o in outcomes:
            fh.write(json.dumps(asdict(o), ensure_ascii=False) + "\n")

    # Aggregate summary
    ok = [o for o in outcomes if o.status == "ok"]
    gen_failed = [o for o in outcomes if o.status == "gen_failed"]
    judge_failed = [o for o in outcomes if o.status == "judge_failed"]

    total_tok_in = sum(o.input_tokens for o in outcomes)
    total_tok_out = sum(o.output_tokens for o in outcomes)
    total_weighted_earned = sum(o.weighted_earned for o in ok)
    total_weighted_total = sum(o.weighted_total for o in ok)
    total_unw_earned = sum(o.unweighted_earned for o in ok)
    total_unw_total = sum(o.unweighted_total for o in ok)

    print(f"─ Summary ─────────────────────────────────────────────")
    print(f"  ok           : {len(ok)}/{len(outcomes)}")
    if gen_failed:
        print(f"  gen_failed   : {len(gen_failed)} ({', '.join(o.prompt_id for o in gen_failed)})")
    if judge_failed:
        print(f"  judge_failed : {len(judge_failed)} ({', '.join(o.prompt_id for o in judge_failed)})")
    print(f"  tokens       : {total_tok_in} in, {total_tok_out} out")
    if not args.no_judge and total_unw_total > 0:
        print(f"  unweighted   : {total_unw_earned}/{total_unw_total} rubric items")
    if not args.no_judge and total_weighted_total > 0:
        pct = 100 * total_weighted_earned / total_weighted_total
        print(f"  weighted     : {total_weighted_earned:.2f}/{total_weighted_total:.2f} ({pct:.1f}%)")

    # Per-prompt table
    if not args.no_judge and ok:
        print(f"─ Per-prompt scores ───────────────────────────────────")
        print(f"  {'prompt_id':<22} {'tier':<5} {'items':<8} {'weighted':<14}")
        for o in ok:
            items_str = f"{o.unweighted_earned}/{o.unweighted_total}"
            if o.weighted_total > 0:
                w_str = f"{o.weighted_earned:.2f}/{o.weighted_total:.2f} ({100*o.weighted_earned/o.weighted_total:.0f}%)"
            else:
                w_str = "—"
            print(f"  {o.prompt_id:<22} {str(o.tier):<5} {items_str:<8} {w_str:<14}")

    print(f"─ Output ──────────────────────────────────────────────")
    print(f"  jsonl      : {jsonl_path}")
    print(f"  svgs       : {out_dir}/<prompt_id>.svg")

    return 0 if not gen_failed and not judge_failed else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--prompt-id", help="Run a single BenchmarkPrompt id (e.g. Mathematics_72)")
    selector.add_argument("--sample", type=int, help="Randomly sample N prompts")
    selector.add_argument("--all", action="store_true", help="Run every prompt in the definition")

    parser.add_argument("--definition", default=str(_DEFAULT_DEFINITION), help="Path to BenchmarkDefinition YAML")
    parser.add_argument("--tier", type=int, default=None, help="Filter prompts by tier (applies to --sample/--all)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for --sample")
    parser.add_argument("--strategy", choices=list(_STRATEGIES), default="recipe",
                        help="Generation strategy (default: recipe)")
    parser.add_argument("--model", default="anthropic:claude-sonnet-4-6", help="Generation model")
    parser.add_argument("--judge-model", default="openai:gpt-5.4-mini", help="AI judge model (ignored if --no-judge)")
    parser.add_argument("--concurrency", type=int, default=4, help="Max concurrent prompts")
    parser.add_argument("--out-dir", default=str(_DEFAULT_OUT_DIR), help="Directory for SVGs + dry_run.jsonl")
    parser.add_argument("--no-judge", action="store_true", help="Skip AI judge step")
    parser.add_argument("--gen-retries", type=int, default=0, metavar="N",
                        help="Outer-loop retries on generation failure (default: 0). "
                             "Each retry creates a fresh RecipeStrategy. Total attempts = 1 + N.")
    parser.add_argument("--verbose", action="store_true", default=False,
                        help="Print rich per-prompt sections (Prompt / Generation / AI Judge / Score). "
                             "Enabled automatically when running a single prompt; "
                             "for batch runs with concurrency > 1 output may interleave.")

    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
