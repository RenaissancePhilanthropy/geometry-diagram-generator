#!/usr/bin/env bash
# Launch the GeoGen leaderboard pilot: M models × S strategies × N scenarios.
#
# Prereqs:
#   * .venv activated (or use uv run)
#   * TikZ renderer container running on :8001
#   * .env populated with ANTHROPIC_API_KEY and OPENAI_API_KEY
#
# Usage:
#   bash evals/leaderboard_launch.sh
#
# Outputs:
#   evals/results/leaderboard_pilot/<run_id>.jsonl  (one per model×strategy)
#   evals/results/leaderboard_pilot/<run_id>/svgs/  (per run)
set -euo pipefail

SCENARIOS=${SCENARIOS:-evals/scenarios_pilot.yaml}
OUTPUT_DIR=${OUTPUT_DIR:-evals/results/leaderboard_pilot}

# Per-model concurrency. Anthropic models get throttled at ~4-concurrent
# 19K-token bursts (CLOSE_WAIT 429s, observed in v1 + v2). OpenAI models
# have a separate rate-limit pool. (macOS bash 3.2 lacks assoc arrays.)
concurrency_for() {
  case "$1" in
    anthropic:*) echo 2 ;;
    openai-responses:*) echo 4 ;;
    *) echo 2 ;;
  esac
}

# Skip combos that already completed cleanly in earlier runs (manual list).
# Format: "model|strategy"
SKIP=${SKIP:-"anthropic:claude-sonnet-4-6|raw_code"}

# Pilot v2: dropped Opus (rate-limited; deadlocked the v1 launch). Keeping
# Sonnet/Haiku/GPT-5.1 for the cost-quality spread.
MODELS=(
  "anthropic:claude-sonnet-4-6"
  "anthropic:claude-haiku-4-5-20251001"
  "openai-responses:gpt-5.1"
)
STRATEGIES=("raw_code" "structured" "recipe")

mkdir -p "$OUTPUT_DIR"

INDEX="$OUTPUT_DIR/index.tsv"
[[ -f "$INDEX" ]] || echo -e "model\tstrategy\trun_id\tjsonl\tstatus\tstart\tend\twallclock_s" > "$INDEX"

total=$(( ${#MODELS[@]} * ${#STRATEGIES[@]} ))
i=0
for model in "${MODELS[@]}"; do
  for strategy in "${STRATEGIES[@]}"; do
    i=$((i+1))
    label="[$i/$total] $model | $strategy"
    echo "===================================================================="
    echo "$label"
    echo "===================================================================="

    if [[ "$SKIP" == *"${model}|${strategy}"* ]]; then
      echo "  skipped (already completed in earlier run)"
      continue
    fi

    conc=$(concurrency_for "$model")
    echo "  using concurrency=$conc"

    start_ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    t0=$(date +%s)

    set +e
    uv run python -m evals.run \
      --scenarios "$SCENARIOS" \
      --strategies "$strategy" \
      --model "$model" \
      --output "$OUTPUT_DIR" \
      --max-concurrency "$conc" \
      --no-llm-judge
    rc=$?
    set -e

    t1=$(date +%s)
    end_ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    wall=$((t1 - t0))

    # Most-recently-modified .jsonl in OUTPUT_DIR is presumed to be ours
    latest=$(ls -t "$OUTPUT_DIR"/*.jsonl 2>/dev/null | head -1 || echo "")
    rid=$(basename "$latest" .jsonl 2>/dev/null || echo "unknown")

    status="ok"
    [[ $rc -ne 0 ]] && status="error_rc=$rc"

    echo -e "${model}\t${strategy}\t${rid}\t${latest}\t${status}\t${start_ts}\t${end_ts}\t${wall}" >> "$INDEX"
    echo "completed: rc=$rc wall=${wall}s run_id=${rid}"
  done
done

echo
echo "All runs complete. Index: $INDEX"
echo
column -t -s $'\t' "$INDEX"
