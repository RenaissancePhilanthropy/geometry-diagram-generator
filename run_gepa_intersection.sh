#!/usr/bin/env bash
# GEPA prompt optimization run: hard-intersection scenarios (43 total)
#
# Re-optimizes the recipe strategy's generation_system prompt against the FULL
# tikz gate (properties incl. mark_present, required labels/entities/canvas,
# expected points, structural checks) instead of the svg-only gate the current
# on-disk prompts were tuned against. This makes the optimization objective
# match the evals/run.py --renderer tikz ablation measurement.
#
# Splits evals/scenarios_hard_intersection3.yaml (43 scenarios) into:
#   train: evals/scenarios_hard_intersection3_train.yaml  (15 scenarios)
#   val:   evals/scenarios_hard_intersection3_val.yaml    (28 scenarios)
# The 15 train scenarios were chosen to mirror the full-43 property-type
# distribution (greedy L1 on scenario-membership fractions): 12 of 15 property
# types appear in BOTH sets (the max possible; angle_bisector/centroid/
# not_between are singletons). Train and val therefore test similar things.
#
# Cross-model setup (the ablation was positive for gemma4, negative for deepseek):
#   --train-model deepseek-v4-flash  -> optimize the prompt FOR deepseek (the
#                                       negative-ablation model), to try to fix
#                                       its regression under the full tikz gate.
#   --val-model   gemma4:31b-cloud    -> validate on gemma4 to confirm the
#                                       deepseek-tuned prompt doesn't regress the
#                                       model that previously benefited.
#   --reflection-lm glm-5.2           -> GEPA's reflection proposer (litellm).
# The LLM judge is not passed explicitly, so it defaults to --model's default
# (gemma4:31b-cloud) — the recommended judge (Anthropic default has no API key).
# Per-scenario model routing is handled inside the adapter by scenario id, so
# GEPA's train minibatches use deepseek and its valset evals use gemma4 with no
# change to GEPA's batch protocol.
#
# IMPORTANT: max_metric_calls counts INDIVIDUAL scenario evaluations, NOT rounds.
# Cost breakdown per GEPA iteration (val=28, train=15, minibatch=3):
#   - Seed evaluation (val):   28 calls (once)
#   - Train minibatch (cur):    3 calls (reflection_minibatch_size default)
#   - Train minibatch (new):    3 calls
#   - Full valset evaluation:  28 calls
#   Total per iteration:        34 calls (after seed)
#
# max_metric_calls=700 -> 28 (seed) + ~20 iterations (20*34=680) of optimization.
#
# Latency note: each scenario now does a LaTeX compile over HTTP (tikz renderer)
# on top of LLM time, so iterations are slower than the svg challenge run.
# With concurrency=5 and ~40-60s/scenario (LLM + compile), each iteration takes
# ~10-15 min. 20 iterations x ~12 min ~= 4 hours.
#
# Prerequisites:
#   - tikz renderer up on port 8001 (see memory: tikz-renderer-bare-metal).
#     Preflight-checked below; the script exits early if it's unreachable.
#   - generation/reflection models reachable (ollama-cloud).
set -euo pipefail

cd "$(dirname "$0")"

source .venv/bin/activate

# --- Preflight: tikz renderer must be up (tikz gate + judge need it) ---
RENDERER_URL="${TIKZ_RENDERER_URL:-http://localhost:8001}"
if ! curl -sf --max-time 3 "${RENDERER_URL}/health" >/dev/null 2>&1; then
  echo "ERROR: tikz renderer not reachable at ${RENDERER_URL}/health" >&2
  echo "Start it first (port 8001), then re-run. Without it every scenario" >&2
  echo "fails to render (score 0) and the tikz gate never fires." >&2
  exit 1
fi
echo "tikz renderer healthy at ${RENDERER_URL}"

python -u optimize_recipe_prompts.py \
  --train evals/scenarios_hard_intersection3_train.yaml \
  --val evals/scenarios_hard_intersection3_val.yaml \
  --train-model ollama:deepseek-v4-flash:cloud \
  --val-model ollama:gemma4:31b-cloud \
  --reflection-lm ollama:glm-5.2:cloud \
  --max-metric-calls 700 \
  --components generation_system \
  --renderer tikz \
  --thinking \
  --llm-judge \
  --max-concurrency 3 \
  --output-dir gepa_runs/intersection \
  > gepa_runs/intersection.log 2>&1 #| tee gepa_runs/intersection.log
