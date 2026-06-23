#!/usr/bin/env bash
# GEPA prompt optimization run: challenge scenarios (86 scenarios)
#
# Training + validation set (evals/scenarios_gepa_challenge.yaml):
#   61 curriculum scenarios that produce diagrams but fail property checks
#   12 tier-3 generalization scenarios (never tested)
#   13 stress scenarios (never tested)
#
# IMPORTANT: max_metric_calls counts INDIVIDUAL scenario evaluations, NOT rounds.
# Cost breakdown per GEPA iteration:
#   - Seed evaluation:           86 calls (once)
#   - Train minibatch (cur):     3 calls (reflection_minibatch_size default)
#   - Train minibatch (new):     3 calls
#   - Full valset evaluation:   86 calls
#   Total per iteration:         ~92 calls (after seed)
#
# So max_metric_calls=1720 → 86 (seed) + ~17 iterations ≈ 17 optimization steps
# (NOT 20, because each iteration costs 92 calls, not just 86).
#
# With concurrency=5 and ~30s/scenario (throttled), each iteration takes ~25 min.
#   17 iterations × 25 min ≈ 7 hours
#
# The previous 10×10 run used max_metric_calls=100 with only 20 scenarios
# (5 rounds). With 86 scenarios, scale proportionally.
#
set -euo pipefail

cd "$(dirname "$0")"

source .venv/bin/activate

python -u optimize_recipe_prompts.py \
  --train evals/scenarios_gepa_challenge.yaml \
  --val evals/scenarios_gepa_challenge.yaml \
  --model ollama:gemma4:31b-cloud \
  --reflection-lm ollama:kimi-k2.6:cloud \
  --max-metric-calls 1720 \
  --components generation_system \
  --renderer tikz \
  --thinking \
  --llm-judge \
  --max-concurrency 5 \
  --output-dir gepa_runs/challenge2 \
  > gepa_runs/challenge2.log 2>&1 #| tee gepa_runs/challenge.log
