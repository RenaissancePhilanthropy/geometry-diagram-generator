#!/usr/bin/env python
"""GEPA prompt optimization for the recipe strategy.

Runs evolutionary prompt optimization using GEPA to find improved
versions of the recipe strategy's prompts (generation system prompt,
selection system prompt, DSL docs, and retry hints).

Usage:
    python optimize_recipe_prompts.py \\
        --train evals/scenarios_core.yaml \\
        --val evals/scenarios_generalization.yaml \\
        --model ollama:gemma4:31b-cloud \\
        --max-metric-calls 100 \\
        --output-dir gepa_runs/initial

For quick smoke testing:
    python optimize_recipe_prompts.py \\
        --train evals/scenarios_smoke.yaml \\
        --val evals/scenarios_smoke.yaml \\
        --model ollama:gemma4:31b-cloud \\
        --max-metric-calls 3 \\
        --components generation_system \\
        --output-dir gepa_runs/smoke

Thinking mode is ON by default (suitable for gemma4:31b-cloud).
Use --no-thinking to disable it.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path
_REPO_ROOT = Path(__file__).parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import gepa
from gepa.core.adapter import EvaluationBatch

from gepa_adapter.adapter import RecipeGEPAAdapter
from ir.renderer import SVGRenderer, TikZRenderer
from gepa_adapter.dataset import load_scenarios, TRAIN_DATASET, VAL_DATASET
from strategies.instructions_recipe import RECIPE_GENERATION_SYSTEM, RECIPE_SELECTION_SYSTEM
from strategies.recipe_hints import HINT_TEXTS
from recipe.catalog import DSL_DOCS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# All component keys that can be optimized
ALL_COMPONENTS = {
    "generation_system": RECIPE_GENERATION_SYSTEM,
    "selection_system": RECIPE_SELECTION_SYSTEM,
    "dsl_docs": DSL_DOCS,
    **HINT_TEXTS,  # hint_angle_equality, hint_right_angle, etc.
}


def build_seed_candidate(components: list[str] | None = None) -> dict[str, str]:
    """Build the seed candidate from current prompt constants.

    If components is specified, only include those components.
    Otherwise include all.
    """
    if components:
        missing = [c for c in components if c not in ALL_COMPONENTS]
        if missing:
            raise ValueError(
                f"Unknown component(s): {missing}. "
                f"Available: {sorted(ALL_COMPONENTS.keys())}"
            )
        return {k: v for k, v in ALL_COMPONENTS.items() if k in components}
    return dict(ALL_COMPONENTS)


class ProgressCallback:
    """GEPA callback that prints progress events during optimization.

    This gives real-time visibility into what GEPA is doing:
    which candidates it's evaluating, whether they improve, and
    how scores evolve over time.
    """

    def on_candidate_accepted(self, event):
        """Called when a new candidate improves on the minibatch."""
        idx = event.get("new_candidate_idx", "?")
        new_score = event.get("new_score", 0)
        old_score = event.get("old_score", 0)
        delta = new_score - old_score
        print(f"  ✅ Candidate {idx} ACCEPTED: score {new_score:.4f} (Δ {delta:+.4f} vs {old_score:.4f})")

    def on_candidate_rejected(self, event):
        """Called when a proposed candidate does not improve."""
        new_score = event.get("new_score", 0)
        old_score = event.get("old_score", 0)
        print(f"  ❌ Candidate REJECTED: score {new_score:.4f} (needed > {old_score:.4f})")

    def on_valset_evaluated(self, event):
        """Called after a full validation-set evaluation."""
        avg = event.get("average_score", 0)
        is_best = event.get("is_best_program", False)
        marker = " 🏆 NEW BEST" if is_best else ""
        print(f"  📊 Valset evaluated: avg={avg:.4f}{marker}")

    def on_evaluation_start(self, event):
        """Called before evaluating a candidate on a minibatch."""
        candidate = event.get("candidate", {})
        # Show which components are different from the seed
        changed = [k for k in seed_global if seed_global.get(k) != candidate.get(k)]
        if changed:
            print(f"  🔍 Evaluating candidate (changed: {', '.join(changed[:5])}{'...' if len(changed) > 5 else ''})")
        else:
            print(f"  🔍 Evaluating seed candidate")

    def on_proposal_end(self, event):
        """Called after the reflection LLM proposes new instructions."""
        new_texts = event.get("new_texts", {})
        if new_texts:
            components = list(new_texts.keys())
            print(f"  💡 Proposal: mutated {len(components)} component(s): {', '.join(components[:5])}")

    def on_budget_updated(self, event):
        """Called when metric call budget is updated."""
        remaining = event.get("metric_calls_remaining")
        if remaining is not None and remaining % 10 == 0:
            print(f"  ⏱️  Metric calls remaining: {remaining}")


# Module-level reference to the seed, used by ProgressCallback
seed_global: dict[str, str] = {}


def main():
    parser = argparse.ArgumentParser(
        description="GEPA prompt optimization for recipe strategy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--train",
        default=TRAIN_DATASET,
        help="Path to training scenarios YAML (default: %(default)s)",
    )
    parser.add_argument(
        "--val",
        default=VAL_DATASET,
        help="Path to validation scenarios YAML (default: %(default)s)",
    )
    parser.add_argument(
        "--model",
        default="ollama:gemma4:31b-cloud",
        help="LLM model for the recipe strategy (default: %(default)s)",
    )
    parser.add_argument(
        "--reflection-lm",
        default="ollama:gemma4:31b-cloud",
        help="LLM model for GEPA's reflection proposer via litellm. "
        "For Ollama models, use 'ollama:model' format (auto-converted from pydantic-ai format). "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--max-metric-calls",
        type=int,
        default=100,
        help="Maximum number of evaluation calls (default: %(default)s)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to save results (default: gepa_runs/<timestamp>)",
    )
    parser.add_argument(
        "--components",
        nargs="+",
        default=None,
        help="Specific components to optimize (default: all). "
        f"Available: {sorted(ALL_COMPONENTS.keys())}",
    )
    parser.add_argument(
        "--llm-judge",
        action="store_true",
        default=False,
        help="Enable LLM judge scoring (adds ~0.15 score component)",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help="LLM model for the AI judge (default: same as --model)",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=3,
        help="Max concurrent scenario evaluations (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout per scenario in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--renderer",
        choices=["tikz", "svg"],
        default="svg",
        help="Renderer backend: 'tikz' requires Docker on port 8001, 'svg' works without Docker (default: %(default)s)",
    )
    parser.add_argument(
        "--no-recipes",
        action="store_true",
        default=False,
        help="Disable recipe selection (use RecipeStrategy with use_recipes=False)",
    )
    parser.add_argument(
        "--thinking",
        action="store_true",
        default=True,
        help="Enable LLM thinking/reasoning mode (default: True)",
    )
    parser.add_argument(
        "--no-thinking",
        action="store_true",
        default=False,
        help="Disable LLM thinking/reasoning mode",
    )
    parser.add_argument(
        "--cache-evaluation",
        action="store_true",
        default=False,
        help="Enable GEPA evaluation caching",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Random seed for reproducibility (default: %(default)s)",
    )
    args = parser.parse_args()

    # Setup output directory
    if args.output_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        args.output_dir = f"gepa_runs/{timestamp}"
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load datasets
    logger.info("Loading training scenarios from %s", args.train)
    trainset = load_scenarios(args.train)
    logger.info("Loaded %d training scenarios", len(trainset))

    logger.info("Loading validation scenarios from %s", args.val)
    valset = load_scenarios(args.val)
    logger.info("Loaded %d validation scenarios", len(valset))

    # Build seed candidate
    seed = build_seed_candidate(args.components)
    logger.info("Seed candidate components: %s", sorted(seed.keys()))

    # Save seed candidate for reference
    seed_path = output_dir / "seed_candidate.json"
    with seed_path.open("w") as f:
        json.dump(seed, f, indent=2, ensure_ascii=False)
    logger.info("Seed candidate saved to %s", seed_path)

    # Determine thinking mode
    thinking = args.thinking and not args.no_thinking

    # Create renderer
    renderer = SVGRenderer() if args.renderer == "svg" else TikZRenderer()

    # Convert reflection-lm model name for litellm compatibility.
    # pydantic-ai uses "ollama:model" but litellm uses "ollama/model".
    reflection_lm = args.reflection_lm.replace(":", "/", 1) if args.reflection_lm.startswith("ollama:") else args.reflection_lm
    logger.info("Reflection LM (litellm format): %s", reflection_lm)

    # The judge model uses pydantic-ai format (same as --model), not litellm format.
    # It's passed directly to judge_rendered_diagram which uses pydantic-ai Agent.
    judge_model = args.model

    # Create adapter
    adapter = RecipeGEPAAdapter(
        model=args.model,
        renderer=renderer,
        llm_judge=args.llm_judge,
        judge_model=judge_model,
        max_concurrency=args.max_concurrency,
        timeout_per_scenario=args.timeout,
        use_recipes=not args.no_recipes,
        thinking=thinking,
    )

    # Store seed globally for the progress callback to reference
    global seed_global
    seed_global = seed

    # Run GEPA optimization
    logger.info(
        "Starting GEPA optimization: %d train, %d val, max_metric_calls=%d, model=%s, thinking=%s, renderer=%s",
        len(trainset),
        len(valset),
        args.max_metric_calls,
        args.model,
        thinking,
        args.renderer,
    )
    logger.info("Components to evolve: %s", sorted(seed.keys()))

    result = gepa.optimize(
        seed_candidate=seed,
        trainset=trainset,
        valset=valset,
        adapter=adapter,
        reflection_lm=reflection_lm,
        max_metric_calls=args.max_metric_calls,
        run_dir=str(output_dir),
        cache_evaluation=args.cache_evaluation,
        seed=args.seed,
        display_progress_bar=True,
        callbacks=[ProgressCallback()],
    )

    # Report results
    logger.info("Optimization complete!")
    logger.info(
        "Best candidate index: %d, score: %.4f",
        result.best_idx,
        result.val_aggregate_scores[result.best_idx],
    )
    logger.info("Total candidates explored: %d", result.num_candidates)

    # Save best candidate as a standalone JSON file (easy to inspect and apply)
    best_path = output_dir / "best_candidate.json"
    with best_path.open("w") as f:
        json.dump(result.best_candidate, f, indent=2, ensure_ascii=False)
    logger.info("Best candidate saved to %s", best_path)

    # Save all explored candidates with their scores (for analysis)
    all_candidates_path = output_dir / "all_candidates.jsonl"
    with all_candidates_path.open("w") as f:
        for i, (candidate, score) in enumerate(
            zip(result.candidates, result.val_aggregate_scores)
        ):
            record = {
                "index": i,
                "score": score,
                "parent_indices": result.parents[i] if i < len(result.parents) else None,
                "metric_calls_at_discovery": (
                    result.discovery_eval_counts[i]
                    if i < len(result.discovery_eval_counts)
                    else None
                ),
                "is_best": i == result.best_idx,
                "candidate": candidate,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    logger.info("All candidates (with scores) saved to %s", all_candidates_path)

    # Save seed baselines (attempts and duration per scenario from first evaluation)
    if adapter._baselines:
        baselines_path = output_dir / "seed_baselines.json"
        with baselines_path.open("w") as f:
            json.dump(adapter._baselines, f, indent=2, ensure_ascii=False)
        logger.info("Seed baselines saved to %s", baselines_path)

    # Save per-example validation scores for the best candidate
    if result.val_subscores and result.best_idx < len(result.val_subscores):
        best_subscores = result.val_subscores[result.best_idx]
        subscores_path = output_dir / "best_candidate_val_subscores.json"
        with subscores_path.open("w") as f:
            json.dump(
                {str(k): v for k, v in best_subscores.items()},
                f, indent=2, ensure_ascii=False,
            )
        logger.info("Best candidate per-example val scores saved to %s", subscores_path)

    # Generate evolution tree HTML for visual inspection
    try:
        tree_html = result.candidate_tree_html()
        tree_path = output_dir / "candidate_tree.html"
        with tree_path.open("w") as f:
            f.write(tree_html)
        logger.info("Candidate evolution tree saved to %s", tree_path)
    except Exception as e:
        logger.warning("Could not generate candidate tree HTML: %s", e)

    # Save full result state (for resumption or detailed analysis)
    result_path = output_dir / "gepa_result.json"
    with result_path.open("w") as f:
        json.dump(result.to_dict(), f, indent=2, ensure_ascii=False, default=str)
    logger.info("Full result state saved to %s", result_path)

    # ------------------------------------------------------------------
    # Print human-readable summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  GEPA PROMPT OPTIMIZATION RESULTS")
    print("=" * 70)

    # Score evolution
    seed_score = result.val_aggregate_scores[0]
    best_score = result.val_aggregate_scores[result.best_idx]
    print(f"\n  Seed score:      {seed_score:.4f}")
    print(f"  Best score:      {best_score:.4f}")
    print(f"  Improvement:     {best_score - seed_score:+.4f} ({(best_score - seed_score) / max(seed_score, 0.001) * 100:+.1f}%)")
    print(f"  Candidates:      {result.num_candidates}")
    print(f"  Metric calls:    {result.total_metric_calls}")

    # Score progression table
    print(f"\n  {'─' * 50}")
    print(f"  {'Idx':>4}  {'Score':>8}  {'Δ vs seed':>10}  {'Metric calls':>13}  {'Parents'}")
    print(f"  {'─' * 50}")
    for i in range(min(len(result.candidates), 30)):  # Show first 30
        score = result.val_aggregate_scores[i]
        delta = score - seed_score
        mc = result.discovery_eval_counts[i] if i < len(result.discovery_eval_counts) else "?"
        parents = result.parents[i] if i < len(result.parents) else []
        parent_str = ", ".join(str(p) for p in parents if p is not None) if parents else "seed"
        if not parent_str:
            parent_str = "seed"
        marker = " ◀ BEST" if i == result.best_idx else ""
        print(f"  {i:>4}  {score:>8.4f}  {delta:>+10.4f}  {mc:>13}  {parent_str}{marker}")
    if len(result.candidates) > 30:
        print(f"  ... {len(result.candidates) - 30} more candidates ...")
    print(f"  {'─' * 50}")

    # Efficiency baseline info (attempts and duration per scenario from seed)
    if adapter._baselines:
        n_scenarios = len(adapter._baselines)
        mean_attempts = sum(b["attempts"] for b in adapter._baselines.values()) / max(n_scenarios, 1)
        mean_duration = sum(b["duration_s"] for b in adapter._baselines.values()) / max(n_scenarios, 1)
        fallback_rate = sum(1 for b in adapter._baselines.values()) / max(n_scenarios, 1)  # N/A here, logged per-scenario
        print(f"\n  Seed baselines ({n_scenarios} scenarios):")
        print(f"    Mean attempts:    {mean_attempts:.1f}")
        print(f"    Mean duration:    {mean_duration:.1f}s")
        print(f"  (Baselines saved to {output_dir}/seed_baselines.json)")

    # Per-component diff of best vs seed
    print(f"\n  Component changes (best vs seed):")
    for key in seed:
        seed_text = seed[key]
        best_text = result.best_candidate.get(key, seed_text)
        if seed_text != best_text:
            # Show first differing line
            seed_lines = seed_text.splitlines()
            best_lines = best_text.splitlines()
            n_changed = sum(
                1 for s, b in zip(seed_lines, best_lines) if s != b
            )
            total_lines = max(len(seed_lines), len(best_lines))
            print(f"    {key}: CHANGED ({n_changed}/{total_lines} lines differ)")
        else:
            print(f"    {key}: unchanged")

    # How to apply the winning prompt
    print(f"\n  To apply the best prompt, copy {best_path} and load it in code:")
    print(f'    from strategies.recipe import RecipeStrategy')
    print(f'    import json')
    print(f'    with open("{best_path}") as f:')
    print(f'        overrides = json.load(f)')
    print(f'    strategy = RecipeStrategy(prompt_overrides=overrides)')

    print(f"\n  Output directory: {output_dir}")
    print(f"  Files saved:")
    print(f"    best_candidate.json          — Best evolved prompt (JSON)")
    print(f"    all_candidates.jsonl          — All explored candidates with scores")
    print(f"    candidate_tree.html           — Interactive evolution tree visualization")
    print(f"    gepa_result.json              — Full optimization state (for resumption)")
    if result.val_subscores and result.best_idx < len(result.val_subscores):
        print(f"    best_candidate_val_subscores.json — Per-example scores for best candidate")
    if adapter._baselines:
        print(f"    seed_baselines.json             — Per-scenario seed baselines (attempts, duration)")
    print("=" * 70)


if __name__ == "__main__":
    main()