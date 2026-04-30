#!/usr/bin/env bash
# Refresh paper/figures/ from the latest hardened pilot data.
#
# Usage (from anywhere):
#   bash paper/scripts/refresh_figures.sh
#
# This regenerates the four matplotlib figures (Pareto, tier-stratified,
# per-template heatmap, failure modes) from the leaderboard JSONLs and copies
# them into paper/figures/ so the LaTeX build stays self-contained.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PILOT_DIR="${PILOT_DIR:-$REPO_ROOT/evals/results/leaderboard_pilot_hardened}"
DOCS_FIG_DIR="$REPO_ROOT/docs/figures/geogen-pilot"
PAPER_FIG_DIR="$REPO_ROOT/paper/figures"

if [[ ! -d "$PILOT_DIR" ]]; then
  echo "Pilot dir not found: $PILOT_DIR"
  echo "Set PILOT_DIR to override."
  exit 1
fi

cd "$REPO_ROOT"
uv run python -m evals.leaderboard_plot \
  --input-dir "$PILOT_DIR" \
  --output-dir "$DOCS_FIG_DIR"

mkdir -p "$PAPER_FIG_DIR"
cp "$DOCS_FIG_DIR"/{pareto,tier_stratified,per_template_heatmap,failure_modes}.pdf "$PAPER_FIG_DIR/"

echo
echo "Figures refreshed:"
ls -la "$PAPER_FIG_DIR"/*.pdf
