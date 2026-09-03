#!/usr/bin/env bash
# save_off_box.sh — copy EVERY experiment artifact off a rented GPU box before it is destroyed.
#
# Rented boxes are always destroyed. In July 2026 the full 16-cell activation matrix
# (mtx_*, *_temporal), plot_cache.json, tier1_review.json, temporal_analysis.json and the
# steering result files lived only on the box and were lost. This script is the fix.
# Run it BEFORE `vastai destroy`, and let rerun_driver.sh call it automatically at the end.
#
# Two tiers:
#   A. SMALL (megabytes, always): per-run meta.jsonl (labels, grades, stated confidences,
#      token positions) and every *.json/*.jsonl/*.csv/*.txt/*.log under interp/activations
#      -> copied into interp/results/<run>/, which IS tracked by git, committed and pushed.
#      Every headline number can be recomputed from these + the probe scores they contain.
#   B. LARGE (gigabytes): the *.npz activation files needed to retrain probes / rerun
#      tier1_review.py -> uploaded with rclone to $RCLONE_REMOTE, or rsync'd to $RSYNC_DEST.
#      If neither is set the script REFUSES to exit 0, so a bare run cannot silently skip it.
#
# Usage (from the repo root on the box):
#   bash interp/save_off_box.sh --small                       # tier A only (seconds)
#   RCLONE_REMOTE=b2:geogen-interp bash interp/save_off_box.sh   # A + B via rclone
#   RSYNC_DEST=user@host:/data/geogen bash interp/save_off_box.sh # A + B via rsync
#
# rclone one-time setup on a fresh box:  curl https://rclone.org/install.sh | bash
#   then `rclone config` (or copy ~/.config/rclone/rclone.conf from your laptop).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACT="$ROOT/interp/activations"
RES="$ROOT/interp/results"
SMALL_ONLY=0; [ "${1:-}" = "--small" ] && SMALL_ONLY=1
TAG="$(hostname -s 2>/dev/null || echo box)-$(date +%Y%m%d-%H%M)"

[ -d "$ACT" ] || { echo "no $ACT — nothing to save"; exit 0; }

echo "==> Tier A: small artifacts -> $RES"
mkdir -p "$RES"
# top-level analysis outputs (plot_cache.json, tier1_review.json, temporal_analysis.json, ...)
find "$ACT" -maxdepth 1 -type f \( -name '*.json' -o -name '*.jsonl' -o -name '*.csv' -o -name '*.txt' -o -name '*.log' -o -name '*.md' \) \
  -exec cp -p {} "$RES/" \;
# per-run: meta.jsonl + any small result files, never the npz
for d in "$ACT"/*/; do
  run="$(basename "$d")"
  mkdir -p "$RES/$run"
  find "$d" -maxdepth 1 -type f \( -name '*.json' -o -name '*.jsonl' -o -name '*.csv' -o -name '*.txt' -o -name '*.log' -o -name '*.md' \) \
    -exec cp -p {} "$RES/$run/" \;
  n_npz=$(find "$d" -maxdepth 1 -name '*.npz' | wc -l | tr -d ' ')
  sz=$(du -sh "$d" | cut -f1)
  printf '   %-32s %6s npz  %8s\n' "$run" "$n_npz" "$sz"
  echo "{\"run\":\"$run\",\"npz_files\":$n_npz,\"size\":\"$sz\",\"saved_from\":\"$TAG\"}" > "$RES/$run/_manifest.json"
done
du -sh "$RES" | sed 's/^/   results dir: /'

if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$ROOT" add -A interp/results
  if ! git -C "$ROOT" diff --cached --quiet; then
    git -C "$ROOT" commit -q -m "results: snapshot small artifacts from $TAG (save_off_box.sh)"
    git -C "$ROOT" push -q origin HEAD && echo "   committed + pushed interp/results" \
      || echo "   !! push failed — commit is local only; push manually before destroying the box"
  else
    echo "   results unchanged, nothing to commit"
  fi
fi

[ "$SMALL_ONLY" = 1 ] && { echo "==> --small: skipping Tier B (npz). Remember to run the full save before destroy."; exit 0; }

echo "==> Tier B: activations (*.npz) -> off-box storage"
total=$(du -sh "$ACT" | cut -f1)
if [ -n "${RCLONE_REMOTE:-}" ]; then
  command -v rclone >/dev/null || { echo "rclone not installed: curl https://rclone.org/install.sh | bash"; exit 1; }
  echo "   rclone copy $ACT -> $RCLONE_REMOTE/activations  ($total)"
  rclone copy "$ACT" "$RCLONE_REMOTE/activations" --transfers 8 --checkers 16 --stats 30s --stats-one-line
  echo "   verifying…"; rclone check "$ACT" "$RCLONE_REMOTE/activations" --one-way && echo "   OK: every local file present remotely"
elif [ -n "${RSYNC_DEST:-}" ]; then
  echo "   rsync $ACT -> $RSYNC_DEST/activations  ($total)"
  rsync -a --partial --info=progress2 "$ACT/" "$RSYNC_DEST/activations/"
  echo "   OK: rsync finished"
else
  cat <<MSG
   !! $total of activations under $ACT and NO destination set.
   Set one and rerun:   RCLONE_REMOTE=<remote>:<bucket>   or   RSYNC_DEST=user@host:/path
   Do NOT destroy the box until this exits 0.
MSG
  exit 2
fi
echo "==> SAVE COMPLETE ($TAG). Safe to destroy the box."
