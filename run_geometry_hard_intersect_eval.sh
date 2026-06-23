#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./run_geometry_curriculum_eval.sh --repeats 3 --model ollama:gemma4:31b-cloud
#
# Defaults:
#   --repeats 3
#   --model   ollama:gemma4:31b-cloud
# Output log is auto-generated as:
#   output_run_curricullum_<MODEL_NAME>_<REPEATS>.txt
#   (with an incrementing suffix if the file already exists)
# Judge model is fixed to: ollama:gemma4:31b-cloud

REPEATS=1
MODEL="ollama:gemma4:31b-cloud"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repeats)
      REPEATS="$2"
      shift 2
      ;;
    --model)
      MODEL="$2"
      shift 2
      ;;
    --help|-h)
      sed -n '/^# Usage:/,/^# Judge/p' "$0" | sed 's/^# //'
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

# Strip 'ollama:' prefix and ':...cloud' / ':...it' suffix to get the bare model name.
MODEL_NAME=$(echo "$MODEL" | sed -E 's/^ollama://; s/:.*//')

OUTPUT_BASE="output_run_hard_intersect_tikz_${MODEL_NAME}_${REPEATS}"
OUTPUT_LOG="${OUTPUT_BASE}.txt"

if [[ -e "$OUTPUT_LOG" ]]; then
  i=1
  while [[ -e "${OUTPUT_BASE}_${i}.txt" ]]; do
    i=$((i + 1))
  done
  OUTPUT_LOG="${OUTPUT_BASE}_${i}.txt"
fi

uv run python -u -m evals.run \
  --scenarios evals/scenarios_hard_intersection3.yaml \
  --strategies recipe \
  --model "$MODEL" \
  --repeats "$REPEATS" \
  --output evals/results \
  --renderer tikz \
  --thinking \
  --cot-analysis \
  --use-optimized-prompts \
  --judge-model ollama:gemma4:31b-cloud \
  > "$OUTPUT_LOG" 2>&1

echo "Wrote output to: $OUTPUT_LOG"
