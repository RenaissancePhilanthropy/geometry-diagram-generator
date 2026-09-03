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
#      tier1_review.py -> by default `aws s3 sync` to s3://renphil-geogen-interp/activations
#      (RenPhil AWS account 437659978445, us-east-1, private, SSE, IA after 30 days).
#      Override with RCLONE_REMOTE=<remote>:<bucket> or RSYNC_DEST=user@host:/path.
#      If the upload fails (most often: expired SSO credentials) the script exits non-zero,
#      so a bare run cannot silently skip it.
#
# AWS auth on a rented box — the org SCP forbids IAM users / static keys, so use SSO:
#   pip install awscli   (or the bundled installer)
#   scp ~/.aws/config root@<box>:~/.aws/config        # carries the [profile renphil] block
#   aws sso login --profile renphil --use-device-code  # prints a URL + code; open on laptop
#   export AWS_PROFILE=renphil
# Role credentials last ~1 hour per login. For a long run: let the driver finish, then log in
# on the box and run this script by hand before destroying.
#
# Usage (from the repo root on the box):
#   bash interp/save_off_box.sh --small                       # tier A only (seconds)
#   AWS_PROFILE=renphil bash interp/save_off_box.sh           # A + B -> S3 (default)
#   RCLONE_REMOTE=s3:renphil-geogen-interp bash interp/save_off_box.sh  # via rclone (env_auth)
#   RSYNC_DEST=user@host:/data/geogen bash interp/save_off_box.sh       # via rsync
#
# Restore a run later:  aws s3 sync s3://renphil-geogen-interp/activations/<run> interp/activations/<run>
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACT="$ROOT/interp/activations"
RES="$ROOT/interp/results"
SMALL_ONLY=0; [ "${1:-}" = "--small" ] && SMALL_ONLY=1
S3_BUCKET="${S3_BUCKET:-renphil-geogen-interp}"
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
  command -v aws >/dev/null || { echo "aws cli not installed: pip install awscli"; exit 1; }
  if ! aws sts get-caller-identity --output text >/dev/null 2>&1; then
    cat <<MSG
   !! No valid AWS credentials ($total of activations NOT saved).
   On the box:  aws sso login --profile renphil --use-device-code && export AWS_PROFILE=renphil
   then rerun this script. Do NOT destroy the box until it exits 0.
MSG
    exit 2
  fi
  echo "   aws s3 sync $ACT -> s3://$S3_BUCKET/activations  ($total)"
  aws s3 sync "$ACT" "s3://$S3_BUCKET/activations" --only-show-errors
  echo "   verifying…"
  local_n=$(find "$ACT" -type f | wc -l | tr -d ' ')
  remote_n=$(aws s3 ls --recursive "s3://$S3_BUCKET/activations/" | wc -l | tr -d ' ')
  echo "   local files: $local_n   remote files (all runs): $remote_n"
  [ "$remote_n" -ge "$local_n" ] || { echo "   !! remote has fewer files than local — rerun"; exit 3; }
  echo "   OK: s3 sync finished"
fi
echo "==> SAVE COMPLETE ($TAG). Safe to destroy the box."
