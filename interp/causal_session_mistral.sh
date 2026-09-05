#!/usr/bin/env bash
# causal_session_mistral.sh — one GPU session that closes the three open questions about
# what the steering result actually shows. Mistral-Small-24B x MATH, ~1.5 h total.
#
# Runs, in order of how much they matter:
#
#  1. ABLATION + dose sweep (gains 0, 0.5, 1, 2, 4, with the magnitude-matched random control).
#     Gain 0 is mean ablation: every record is moved to the mean projection, so the direction
#     survives but carries no per-record information. Gain 1 is an exact no-op.
#     READ IT AS: does the stated-confidence AUROC collapse toward chance? Not "does confidence
#     drop". A generally damaged model writes worse text; it does not selectively lose the
#     ability to rank its own failures below its own successes. Two damage checks are built in:
#     parse rate (must stay ~1.0) and the matched random ablation (must leave AUROC intact).
#     Prediction from the existing gain-0.5 run, where half-removal pushed failure confidence
#     UP 84 -> 88 and AUROC DOWN 0.832 -> 0.809: full removal should push failure confidence
#     further up toward the correct-answer level and drive AUROC toward 0.5. Damage cannot
#     mimic that, because it is not selective.
#
#  2. LAYER SWEEP (same intervention at ~0.3, 0.5, 0.7, 0.9 of depth). If the effect only
#     appears where the probe reads best, the representation is localized and specific. If
#     pushing at any depth works equally, we are probably just perturbing the model.
#     Random control skipped here; run 1 supplies it at the reported layer.
#
#  3. CROSS-DOMAIN DIRECTION (fit on MMLU-Pro, steer MATH). On MMLU-Pro the surface baseline
#     is 0.54 against a probe of 0.75, so a direction learned there cannot be a "my output
#     looks messy" detector. On MATH surface reaches 0.74, so it might be. If the MMLU-Pro
#     direction still moves MATH confidence, the effect is not surface. This is the cheapest
#     decisive test of what the direction encodes.
#
# Setup on the box (2x RTX 5090 or one 80 GB card; 200 GB disk):
#   bash setup_vast.sh
#   scp ~/.aws/config root@<box>:~/.aws/config       # from the laptop
#   aws sso login --profile renphil --use-device-code
#   export AWS_PROFILE=renphil
#   cd ~/geometry-diagram-generator && nohup bash interp/causal_session_mistral.sh > causal.log 2>&1 &
#
# No Hugging Face token needed: Mistral-Small-24B and MATH-500 are both public.
# Afterwards: bash interp/save_off_box.sh  (must exit 0 before the box is destroyed)
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT" || exit 1
export HF_HOME="${HF_HOME:-/root/.hf}"
PY="${PY:-$(command -v python)}"
M="mistralai/Mistral-Small-24B-Instruct-2501"
ACT="$ROOT/interp/activations"
BUCKET="${S3_BUCKET:-renphil-geogen-interp}"
NEVAL="${NEVAL:-150}"
t0=$(date +%s)
stamp () { printf '[%s +%dm] ' "$(date +%H:%M)" $((($(date +%s)-t0)/60)); }

stamp; echo "===== fetch the two cells we need (direction + evaluation) ====="
for c in fix_mistral_math fix_mistral_mmlu_pro; do
  if [ ! -f "$ACT/$c/meta.jsonl" ]; then
    aws s3 sync "s3://$BUCKET/activations/$c" "$ACT/$c" --only-show-errors \
      || { echo "!! could not fetch $c — is AWS_PROFILE set and the SSO login current?"; exit 1; }
  fi
  echo "   $c: $(ls "$ACT/$c"/*.npz 2>/dev/null | wc -l) npz"
done

stamp; echo "===== model ====="
$PY -c "from huggingface_hub import snapshot_download; snapshot_download('$M', ignore_patterns=['*.gguf','*.pth','*consolidated*'])"
$PY -c "
import torch; n=torch.cuda.device_count(); tot=sum(torch.cuda.mem_get_info(i)[1] for i in range(n))/2**30
print('GPUs', n, '| total VRAM', round(tot), 'GB')
assert tot >= 58, 'not enough VRAM for bf16 Mistral-24B'"

run () {  # $1=tag  $2..=extra args
  local tag="$1"; shift
  stamp; echo "----- $tag -----"
  $PY interp/steer_confidence.py --act-dir "$ACT/fix_mistral_math" --model "$M" --task math \
      --device cuda --mode amplify --n-eval "$NEVAL" --seed 0 "$@" \
      --out "$ACT/fix_mistral_math/steer_${tag}.json" 2>&1 \
    | grep -vE "Loading weights|it/s\]|^Fetching" | tail -30
}

# 1. the ablation, with the matched random control
run "ablation" --coeffs 0,0.5,1,2,4

# 2. localization: is the effect specific to the depth the probe reads?
for L in 12 20 28 36; do
  run "layer${L}" --layer "$L" --coeffs 0,1,4 --skip-random
done

# 3. specificity: a direction that cannot be a surface detector
run "dir_from_mmlu" --dir-act-dir "$ACT/fix_mistral_mmlu_pro" --coeffs 0,1,2,4

stamp; echo "===== results written ====="
ls -la "$ACT/fix_mistral_math"/steer_*.json
stamp; echo "SESSION COMPLETE — now run: bash interp/save_off_box.sh (needs a live SSO login)"
