"""Profile latency of a single recipe-strategy scenario run.

Times each phase of the RecipeStrategy pipeline so we can identify bottlenecks.

Usage:
    uv run python profile_single_scenario.py [--model MODEL] [--renderer svg|tikz]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv()

from evals.scenarios import _validate_scenarios
from strategies.base import DEFAULT_AGENT_MODEL
from strategies.recipe import RecipeStrategy, RecipeMetadata
from strategies.structured import StructuredRunResult, _run_ir_pipeline
from ir.renderer import Renderer, TikZRenderer, SVGRenderer
from recipe.catalog import load_catalog, load_recipe, build_selection_prompt, build_generation_prompt, DSL_DOCS
from recipe.lower import lower_to_ir, LoweringError
from recipe.dsl import RecipeDSL

import pydantic
from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.exceptions import UnexpectedModelBehavior

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# A simple scenario that's known to succeed
_SIMPLE_PROMPT = (
    "Can you draw a coordinate grid and plot two points — let's call them A at (1, 2) "
    "and B at (7, 6)? Then draw a right triangle by adding a third point C at (7, 2) "
    "so that AC is horizontal and BC is vertical. Label all three points, show the "
    "right angle at C, and mark the lengths of the two legs."
)


async def profile_run(prompt: str, model: str, renderer: Renderer, use_recipes: bool = True, thinking: bool = False, judge_model: str | None = None) -> None:
    """Run a single recipe-strategy scenario with per-phase timing."""
    strategy = RecipeStrategy(use_recipes=use_recipes, enable_cache=False, thinking=thinking)

    total_start = time.monotonic()
    timings: dict[str, float] = {}

    recipe_metadata = RecipeMetadata()
    total_input_tokens = 0
    total_output_tokens = 0

    # --- Phase 1: Recipe selection ---
    if use_recipes:
        print("\n── Phase 1: Recipe Selection ──")
        t0 = time.monotonic()
        catalog = load_catalog(strategy.catalog)
        t1 = time.monotonic()
        timings["catalog_load"] = t1 - t0
        print(f"  Catalog load:     {timings['catalog_load']*1000:.1f} ms")

        selection_prompt = build_selection_prompt(prompt, catalog)
        t2 = time.monotonic()
        timings["build_selection_prompt"] = t2 - t1
        print(f"  Build sel prompt:  {timings['build_selection_prompt']*1000:.1f} ms")

        from strategies.instructions import RECIPE_SELECTION_SYSTEM
        from strategies.recipe import _SELECTOR_MODEL
        selector_agent: Agent[None, str] = Agent(
            _SELECTOR_MODEL,
            instructions=RECIPE_SELECTION_SYSTEM,
            output_type=str,
            model_settings=strategy.model_settings,
        )
        t3 = time.monotonic()
        sel_response = await selector_agent.run(selection_prompt)
        t4 = time.monotonic()
        timings["selector_llm_call"] = t4 - t3
        sel_usage = sel_response.usage()
        recipe_metadata.selection_input_tokens = sel_usage.input_tokens or 0
        recipe_metadata.selection_output_tokens = sel_usage.output_tokens or 0
        total_input_tokens += recipe_metadata.selection_input_tokens
        total_output_tokens += recipe_metadata.selection_output_tokens
        print(f"  Selector LLM call: {timings['selector_llm_call']:.2f} s  (in={recipe_metadata.selection_input_tokens}, out={recipe_metadata.selection_output_tokens} tokens)")

        # Parse selection
        raw_text = sel_response.output
        selected_ids: list[str] = []
        try:
            text = raw_text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            parsed = json.loads(text)
            selected_ids = parsed.get("selected_recipes", parsed.get("selected", []))
        except (json.JSONDecodeError, AttributeError):
            pass
        print(f"  Selected recipes:  {selected_ids}")

        recipes = []
        for rid in selected_ids:
            try:
                recipes.append(load_recipe(rid, catalog=strategy.catalog))
                recipe_metadata.selected_recipes.append(rid)
            except KeyError:
                pass

        t5 = time.monotonic()
        timings["selection_total"] = t5 - t0
        print(f"  Selection total:  {timings['selection_total']:.2f} s")
    else:
        recipes = []

    # --- Build generation prompt ---
    print("\n── Phase 2: Generation Prompt ──")
    t0 = time.monotonic()
    generation_prompt = build_generation_prompt(prompt, recipes, DSL_DOCS)
    t1 = time.monotonic()
    timings["build_generation_prompt"] = t1 - t0
    print(f"  Build gen prompt:  {timings['build_generation_prompt']*1000:.1f} ms")
    print(f"  Prompt length:    {len(generation_prompt)} chars")

    # --- Phase 3: Generation (LLM call) ---
    MAX_RETRIES = 3
    last_error = ""
    result: StructuredRunResult | None = None

    for attempt in range(MAX_RETRIES):
        print(f"\n── Phase 3: Generation (Attempt {attempt + 1}/{MAX_RETRIES}) ──")
        user_message = generation_prompt
        if attempt > 0:
            user_message = f"{generation_prompt}\n\nPrevious attempt failed: {last_error}\nPlease produce a corrected RecipeDSL."

        from strategies.instructions import RECIPE_GENERATION_SYSTEM
        gen_agent: Agent[None, RecipeDSL] = Agent(
            model,
            instructions=RECIPE_GENERATION_SYSTEM,
            output_type=RecipeDSL,
            model_settings=strategy.model_settings,
        )

        t0 = time.monotonic()
        with capture_run_messages() as agent_messages:
            try:
                response = await gen_agent.run(user_message)
            except UnexpectedModelBehavior as exc:
                t1 = time.monotonic()
                timings[f"gen_llm_attempt_{attempt+1}"] = t1 - t0
                print(f"  Gen LLM call:     {timings[f'gen_llm_attempt_{attempt+1}']:.2f} s  — OUTPUT VALIDATION FAILED")
                print(f"  Error: {exc}")
                from strategies.recipe import _extract_failure_diagnostics
                diag_summary, raw_payload = _extract_failure_diagnostics(exc, agent_messages)
                last_error = diag_summary
                continue

        t1 = time.monotonic()
        timings[f"gen_llm_attempt_{attempt+1}"] = t1 - t0
        usage = response.usage()
        gen_in = usage.input_tokens or 0
        gen_out = usage.output_tokens or 0
        total_input_tokens += gen_in
        total_output_tokens += gen_out
        print(f"  Gen LLM call:     {timings[f'gen_llm_attempt_{attempt+1}']:.2f} s  (in={gen_in}, out={gen_out} tokens)")

        dsl = response.output
        print(f"  DSL ops count:    {len(dsl.construction)}")

        # --- Phase 4: Lowering ---
        print(f"\n── Phase 4: Lowering (Attempt {attempt + 1}) ──")
        t0 = time.monotonic()
        try:
            diagram_ir = lower_to_ir(dsl)
        except (LoweringError, pydantic.ValidationError) as e:
            t1 = time.monotonic()
            timings[f"lowering_attempt_{attempt+1}"] = t1 - t0
            print(f"  Lowering:         {timings[f'lowering_attempt_{attempt+1}']*1000:.1f} ms  — FAILED")
            print(f"  Error: {e}")
            last_error = f"Lowering failed: {e}"
            continue
        t1 = time.monotonic()
        timings[f"lowering_attempt_{attempt+1}"] = t1 - t0
        print(f"  Lowering:         {timings[f'lowering_attempt_{attempt+1}']*1000:.1f} ms  ✓")
        print(f"  IR defs:          {len(diagram_ir.define)}")
        print(f"  IR render ops:    {len(diagram_ir.render)}")
        print(f"  IR checks:        {len(diagram_ir.checks)}")

        # --- Phase 5: IR Pipeline (compile → check → render) ---
        print(f"\n── Phase 5: IR Pipeline (Attempt {attempt + 1}) ──")
        ir_t0 = time.monotonic()

        # 5a: Compile
        from ir.to_sympy import compile_defs
        from ir.checks import run_checks, check_render_angles
        from ir.errors import IRCompileError
        try:
            t_c0 = time.monotonic()
            sym = compile_defs(diagram_ir)
            t_c1 = time.monotonic()
            timings[f"ir_compile_attempt_{attempt+1}"] = t_c1 - t_c0
            print(f"  Compile defs:     {(t_c1-t_c0)*1000:.1f} ms")
        except IRCompileError as e:
            ir_t1 = time.monotonic()
            timings[f"ir_pipeline_attempt_{attempt+1}"] = ir_t1 - ir_t0
            last_error = f"IR compilation failed: {e}"
            print(f"  Compile FAILED:   {e}")
            continue

        # 5b: Checks
        t_ck0 = time.monotonic()
        check_results = run_checks(diagram_ir.checks, sym)
        must_failures = [r for r in check_results if not r.passed and r.check.level == "must"]
        t_ck1 = time.monotonic()
        timings[f"ir_checks_attempt_{attempt+1}"] = t_ck1 - t_ck0
        print(f"  Geometric checks: {(t_ck1-t_ck0)*1000:.1f} ms  ({len(check_results)} checks, {len(must_failures)} must-failures)")
        if must_failures:
            msgs = "\n".join(f"    - {r.message}" for r in must_failures)
            last_error = f"Geometric checks failed:\n{msgs}"
            timings[f"ir_pipeline_attempt_{attempt+1}"] = time.monotonic() - ir_t0
            print(f"  Checks FAILED")
            continue

        # 5c: Render-angle check
        t_ra0 = time.monotonic()
        angle_errors = check_render_angles(diagram_ir, sym)
        t_ra1 = time.monotonic()
        timings[f"ir_render_angles_attempt_{attempt+1}"] = t_ra1 - t_ra0
        print(f"  Render angles:    {(t_ra1-t_ra0)*1000:.1f} ms  ({len(angle_errors)} errors)")
        if angle_errors:
            msgs = "\n".join(f"    - {e}" for e in angle_errors)
            last_error = f"Invalid angle triples in render ops:\n{msgs}"
            timings[f"ir_pipeline_attempt_{attempt+1}"] = time.monotonic() - ir_t0
            print(f"  Render angles FAILED")
            continue

        # 5d: Render
        t_r0 = time.monotonic()
        try:
            render_result = renderer.render(diagram_ir, sym)
        except Exception as e:
            t_r1 = time.monotonic()
            timings[f"ir_render_attempt_{attempt+1}"] = t_r1 - t_r0
            timings[f"ir_pipeline_attempt_{attempt+1}"] = time.monotonic() - ir_t0
            last_error = f"Rendering failed: {e}"
            print(f"  Render FAILED:    {e}")
            continue
        t_r1 = time.monotonic()
        timings[f"ir_render_attempt_{attempt+1}"] = t_r1 - t_r0
        print(f"  Render:           {(t_r1-t_r0)*1000:.1f} ms")

        ir_t1 = time.monotonic()
        timings[f"ir_pipeline_attempt_{attempt+1}"] = ir_t1 - ir_t0
        print(f"  IR Pipeline total: {timings[f'ir_pipeline_attempt_{attempt+1}']*1000:.1f} ms  ✓")

        # Build result object
        import sympy.geometry as spg
        tikz_code = render_result.intermediate
        svg_code = render_result.output
        sym_float = {
            k: (float(v.x), float(v.y))
            for k, v in sym.items()
            if isinstance(v, spg.Point)
        }
        result = StructuredRunResult(
            diagram_ir=diagram_ir, tikz=tikz_code, svg=svg_code,
            sym_table=sym_float, sym_full=sym,
        )
        print(f"  TikZ length:      {len(tikz_code)} chars")
        print(f"  SVG length:       {len(svg_code)} chars")

        # Success!
        break
    else:
        print(f"\n── All {MAX_RETRIES} attempts failed — would fall back to StructuredStrategy ──")

    total_elapsed = time.monotonic() - total_start
    timings["total_without_judge"] = total_elapsed

    # --- Phase 6: LLM Judge ---
    _judge_model = judge_model or model
    print(f"\n── Phase 6: LLM Judge (model: {_judge_model}) ──")
    judge_result_data = None
    if result is not None and result.tikz:
        t0 = time.monotonic()
        from util.llm_judge import judge_tikz_code
        # Suppress verbose logfire output from judge
        import logging as _logging
        _logging.getLogger("logfire").setLevel(_logging.WARNING)
        try:
            judge_result_data = await judge_tikz_code(
                prompt=prompt,
                tikz_code=result.tikz,
                model=_judge_model,
                enable_cache=False,
            )
        except Exception as e:
            print(f"  Judge error: {e}")
        t1 = time.monotonic()
        timings["llm_judge"] = t1 - t0
        if judge_result_data:
            print(f"  LLM Judge call:    {timings['llm_judge']:.2f} s")
            print(f"  Score:             {judge_result_data['score']}/5")
            print(f"  Reasoning:         {judge_result_data['reasoning'][:120]}...")
    else:
        # For SVG renderer there's no TikZ code, so the code judge can't run.
        # Try the visual judge instead if SVG is available.
        if result is not None and result.svg:
            print(f"  (No TikZ code — using visual judge on SVG instead)")
            t0 = time.monotonic()
            from util.llm_judge import judge_rendered_diagram
            import logging as _logging
            _logging.getLogger("logfire").setLevel(_logging.WARNING)
            try:
                judge_result_data = await judge_rendered_diagram(
                    prompt=prompt,
                    svg=result.svg,
                    model=_judge_model,
                    enable_cache=False,
                )
            except Exception as e:
                print(f"  Visual judge error: {e}")
            t1 = time.monotonic()
            timings["llm_judge"] = t1 - t0
            if judge_result_data:
                print(f"  Visual Judge call: {timings['llm_judge']:.2f} s")
                print(f"  Score:             {judge_result_data['score']}/5")
                print(f"  Reasoning:         {judge_result_data['reasoning'][:120]}...")
        else:
            print(f"  (Skipped — no TikZ or SVG available)")

    total_with_judge = time.monotonic() - total_start
    timings["total_with_judge"] = total_with_judge

    # --- Summary ---
    print("\n" + "=" * 60)
    print("LATENCY SUMMARY")
    print("=" * 60)

    # Group by phase
    selection_total = timings.get("selection_total", 0)
    gen_total = sum(v for k, v in timings.items() if k.startswith("gen_llm_"))
    lowering_total = sum(v for k, v in timings.items() if k.startswith("lowering_"))
    ir_compile_total = sum(v for k, v in timings.items() if k.startswith("ir_compile_"))
    ir_checks_total = sum(v for k, v in timings.items() if k.startswith("ir_checks_"))
    ir_render_angles_total = sum(v for k, v in timings.items() if k.startswith("ir_render_angles_"))
    ir_render_total = sum(v for k, v in timings.items() if k.startswith("ir_render_") and "angles" not in k)
    ir_total = ir_compile_total + ir_checks_total + ir_render_angles_total + ir_render_total
    judge_total = timings.get("llm_judge", 0)
    other = total_with_judge - selection_total - gen_total - lowering_total - ir_total - judge_total

    print(f"  Recipe selection:   {selection_total:7.2f} s  ({selection_total/total_with_judge*100:5.1f}%)")
    print(f"  Generation LLM:    {gen_total:7.2f} s  ({gen_total/total_with_judge*100:5.1f}%)")
    print(f"  Lowering (local):   {lowering_total:7.2f} s  ({lowering_total/total_with_judge*100:5.1f}%)")
    print(f"  IR compile:         {ir_compile_total:7.2f} s  ({ir_compile_total/total_with_judge*100:5.1f}%)")
    print(f"  IR checks:         {ir_checks_total:7.2f} s  ({ir_checks_total/total_with_judge*100:5.1f}%)")
    print(f"  IR render angles:  {ir_render_angles_total:7.2f} s  ({ir_render_angles_total/total_with_judge*100:5.1f}%)")
    print(f"  IR render:          {ir_render_total:7.2f} s  ({ir_render_total/total_with_judge*100:5.1f}%)")
    print(f"  LLM Judge:          {judge_total:7.2f} s  ({judge_total/total_with_judge*100:5.1f}%)")
    print(f"  Other overhead:     {other:7.2f} s  ({other/total_with_judge*100:5.1f}%)")
    print(f"  ─────────────────────────────")
    print(f"  TOTAL (w/o judge): {total_elapsed:7.2f} s")
    print(f"  TOTAL (w/  judge):  {total_with_judge:7.2f} s")

    print(f"\n  Total tokens:      in={total_input_tokens}, out={total_output_tokens}")
    gen_time = gen_total if gen_total > 0 else 1
    print(f"  Throughput:        {total_output_tokens/gen_time:.1f} out-tokens/s (generation)")

    # Detailed breakdown
    print("\n" + "=" * 60)
    print("DETAILED TIMINGS")
    print("=" * 60)
    for k, v in sorted(timings.items()):
        if v >= 1.0:
            print(f"  {k:40s}  {v:7.2f} s")
        elif v >= 0.001:
            print(f"  {k:40s}  {v*1000:7.1f} ms")
        else:
            print(f"  {k:40s}  {v*1e6:7.0f} µs")


def main():
    parser = argparse.ArgumentParser(description="Profile a single recipe-strategy scenario")
    parser.add_argument("--model", default=DEFAULT_AGENT_MODEL, help="LLM model for generation")
    parser.add_argument("--renderer", choices=["tikz", "svg"], default="svg", help="Renderer backend")
    parser.add_argument("--no-recipes", action="store_true", help="Skip recipe selection phase")
    parser.add_argument("--thinking", action="store_true", help="Enable thinking mode")
    parser.add_argument("--judge-model", default=None, help="Model for LLM judge (defaults to generation model)")
    parser.add_argument("--prompt", default=None, help="Custom prompt to use")
    args = parser.parse_args()

    if args.renderer == "svg":
        renderer = SVGRenderer()
    else:
        from util.tikz_renderer import check_renderer_health
        import os
        renderer_url = os.getenv("TIKZ_RENDERER_URL", "http://localhost:8001")
        if not check_renderer_health(renderer_url):
            print(f"ERROR: TikZ renderer not reachable at {renderer_url}")
            sys.exit(1)
        renderer = TikZRenderer(renderer_url)

    prompt = args.prompt or _SIMPLE_PROMPT
    print(f"Model:     {args.model}")
    print(f"Renderer:  {args.renderer}")
    print(f"Recipes:   {'off' if args.no_recipes else 'on'}")
    print(f"Thinking:  {'on' if args.thinking else 'off'}")
    print(f"Prompt:    {prompt[:80]}...")

    asyncio.run(profile_run(
        prompt=prompt,
        model=args.model,
        renderer=renderer,
        use_recipes=not args.no_recipes,
        thinking=args.thinking,
        judge_model=args.judge_model,
    ))


if __name__ == "__main__":
    main()