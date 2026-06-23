#!/usr/bin/env bash
# GEPA prompt optimization run: 10 varied train + 10 varied val scenarios
# with LLM judge, larger budget (100 metric calls), unbuffered output.
#
# Training set (evals/scenarios_gepa_train.yaml):
#   5 gate-fail + 5 low-score scenarios covering:
#   reflections, rotations, SSA, similarity, circles, transversals, 3D solids
#
# Validation set (evals/scenarios_gepa_val.yaml):
#   7 strong (0.82-0.85, regression guards) + 3 moderate (0.69-0.82)
#
# Output: gepa_runs/gepa_varied_10x10/
set -euo pipefail

cd "$(dirname "$0")"

source .venv/bin/activate

python -u optimize_recipe_prompts.py \
  --train evals/scenarios_gepa_train.yaml \
  --val evals/scenarios_gepa_val.yaml \
  --model ollama:gemma4:31b-cloud \
  --reflection-lm ollama:gemma4:31b-cloud \ #ollama:deepseek-v4-pro:cloud \ 
  --max-metric-calls 100 \
  --components generation_system \
  --renderer tikz \
  --thinking \
  --llm-judge \
  --output-dir gepa_runs/gepa_varied_10x10 \
  > gepa_runs/gepa_varied_10x10.log 2>&1 #| tee gepa_runs/gepa_varied_10x10.log
