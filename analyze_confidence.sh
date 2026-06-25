#!/usr/bin/env bash
set -euo pipefail

# Analyze self-reported-confidence eval results (wraps evals/analyze_confidence.py).
#
# Usage:
#   ./analyze_confidence.sh                                 # analyze the newest evals/results/*.jsonl, strict label
#   ./analyze_confidence.sh evals/results/20260625-134136.jsonl
#   ./analyze_confidence.sh --lenient evals/results/<run>.jsonl
#   ./analyze_confidence.sh --results a.jsonl b.jsonl --out report.json --n-boot 5000
#   ./analyze_confidence.sh --help
#
# Parameters:
#   [RESULTS...]            One or more eval-run JSONL files to analyze. If none are
#                           given (and --results is not set), the newest
#                           evals/results/*.jsonl is used automatically.
#   --results a b ...       Explicit results file(s); same as passing them positionally.
#                           The analyzer pools all given files into one report.
#   --lenient               Count soft_pass as a SUCCESS alongside pass (vs fail). Use
#                           this for more data — soft_pass records did render and pass
#                           svg_checks, they just had some property checks skipped.
#                           Default: STRICT (only pass is a success; soft_pass dropped).
#   --strict                Force strict label (the default; accepted for clarity).
#   --n-boot N              Bootstrap iterations for the AUC 95% confidence intervals
#                           (default 2000). Higher = tighter CI edges, slower.
#   --seed N                Bootstrap RNG seed (default 0), for reproducible CIs.
#   --out FILE              Also write the full report (all cells, all metrics) as JSON.
#
# What it reports (per model x tier cell, never pooled):
#   - HARD (record-level, from the fenced prelude) and SOFT (attempt-level, from the
#     structured field): AUC-ROC + bootstrap 95% CI, Brier, ECE, Cohen's d,
#     pass/fail means, silently-overconfident rate, PR of "flag score<T -> fail".
#   - Baselines: cot_analysis_score and llm_judge_score AUC (scale-invariant).
#   - Coverage gap (attempts with no soft = unparseable output), contradictions_found
#     precision-for-fail, per-dimension AUC.
#   - Decision gate per cell: AUC>0.5 (CI excludes 0.5) AND beats-cot AND overconf-ok.
#
# Truth label: strict = pass vs fail (default); --lenient = pass+soft_pass vs fail.
# Stratified by model x tier (easy tiers show no-data; that's expected). Pure stdlib.
# HELP-END

RESULTS=()
LENIENT=0
N_BOOT=2000
SEED=0
OUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --results)
      shift
      while [[ $# -gt 0 && "$1" != --* ]]; do RESULTS+=("$1"); shift; done
      ;;
    --lenient) LENIENT=1; shift ;;
    --strict)  LENIENT=0; shift ;;
    --n-boot)  N_BOOT="$2"; shift 2 ;;
    --seed)    SEED="$2"; shift 2 ;;
    --out)     OUT="$2"; shift 2 ;;
    --help|-h) sed -n '/^# Analyze self-reported/,/^# HELP-END/p' "$0" | sed 's/^# //'
               exit 0 ;;
    --*)      echo "Unknown option: $1" >&2; exit 1 ;;
    *)        RESULTS+=("$1"); shift ;;
  esac
done

# Default to the newest eval results JSONL if none given.
if [[ ${#RESULTS[@]} -eq 0 ]]; then
  LATEST=$(ls -t evals/results/*.jsonl 2>/dev/null | head -1 || true)
  if [[ -z "$LATEST" ]]; then
    echo "No results file given and none found in evals/results/*.jsonl" >&2
    exit 1
  fi
  echo "No --results given; using newest: $LATEST"
  RESULTS=("$LATEST")
fi

ARGS=(--n-boot "$N_BOOT" --seed "$SEED" --results "${RESULTS[@]}")
[[ "$LENIENT" -eq 1 ]] && ARGS+=(--lenient)
[[ -n "$OUT" ]] && ARGS+=(--out "$OUT")

uv run python -u -m evals.analyze_confidence "${ARGS[@]}"