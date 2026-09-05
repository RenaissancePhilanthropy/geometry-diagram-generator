#!/usr/bin/env bash
# causal_model.sh <qwen36|gemma4|glm|mistral> — capture one MATH cell for a model, then run
# the ablation that tests whether its stated confidence depends on the correctness direction.
#
# Why this exists: the ablation needs a captured cell to fit the direction from, and only
# Mistral survived the July box. Each additional model therefore costs a capture first.
#
# What it does, resumably (capture_qa skips records it already has):
#   1. download the model
#   2. capture MATH, 150 questions x 5 attempts -> interp/activations/fix_<short>_math
#   3. push the capture to S3 immediately, so an expensive capture is never trapped on a box
#   4. ablation sweep: gains 0, 0.5, 1, 2, 4 with the magnitude-matched random control
#   5. push the results
#
# Read the ablation as the AUROC of *stated* confidence collapsing toward chance, not as the
# confidence level dropping. Damage checks are built in: parse rate must stay ~1.0, and the
# matched random ablation must leave the AUROC intact.
#
# Note on GLM: ~96 GB of weights in bf16. It only fits a >=96 GB card, and even then the
# margin is thin. The script checks and refuses rather than dying halfway through a capture.
#
# Worth knowing before you read GLM's result: amplification was null on GLM because its stated
# confidence saturates near 100, leaving no room to push down. Ablation asks the opposite
# question and can succeed where amplification could not.
#
# Setup (same as the Mistral session):
#   bash setup_vast.sh
#   scp ~/.aws/config root@<box>:~/.aws/config
#   aws sso login --profile renphil --use-device-code && export AWS_PROFILE=renphil
#   cd ~/geometry-diagram-generator && nohup bash interp/causal_model.sh qwen36 > qwen.log 2>&1 &
# No Hugging Face token needed: all four models are public.
set -u
SHORT="${1:?usage: causal_model.sh <qwen36|gemma4|glm|mistral>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT" || exit 1
export HF_HOME="${HF_HOME:-/root/.hf}"
PY="${PY:-$(command -v python)}"
ACT="$ROOT/interp/activations"
BUCKET="${S3_BUCKET:-renphil-geogen-interp}"
N="${N:-150}"; SAMPLES="${SAMPLES:-5}"; MAXTOK="${MAXTOK:-3072}"; NEVAL="${NEVAL:-150}"
t0=$(date +%s)
stamp () { printf '[%s +%dm] ' "$(date +%H:%M)" $((($(date +%s)-t0)/60)); }

case "$SHORT" in
  qwen36)  MODEL="Qwen/Qwen3.6-27B";                          THINK="--per-turn-think"; NEED=60 ;;
  gemma4)  MODEL="google/gemma-4-26B-A4B-it";                  THINK="";                NEED=60 ;;
  glm)     MODEL="zai-org/GLM-4.7-Flash";                      THINK="--per-turn-think"; NEED=100 ;;
  mistral) MODEL="mistralai/Mistral-Small-24B-Instruct-2501";  THINK="";                NEED=58 ;;
  *) echo "unknown model '$SHORT'"; exit 2 ;;
esac
CELL="$ACT/fix_${SHORT}_math"
stamp; echo "===== $SHORT ($MODEL), think='$THINK', needs ${NEED} GB ====="

push () {  # $1 = path under interp/activations to mirror into the bucket
  if aws sts get-caller-identity >/dev/null 2>&1; then
    aws s3 sync "$1" "s3://$BUCKET/activations/$(basename "$1")" --only-show-errors \
      && { stamp; echo "pushed $(basename "$1") to S3"; } \
      || { stamp; echo "!! push of $(basename "$1") FAILED"; }
  else
    stamp; echo "!! no live AWS creds — $(basename "$1") is only on this box; run 'aws sso login --profile renphil --use-device-code' then push before destroying"
  fi
}

stamp; echo "----- model -----"
$PY -c "from huggingface_hub import snapshot_download; snapshot_download('$MODEL', ignore_patterns=['*.gguf','*.pth','*consolidated*'])" || exit 1
$PY - <<EOF || exit 1
import torch
n = torch.cuda.device_count()
tot = sum(torch.cuda.mem_get_info(i)[1] for i in range(n)) / 2**30
print(f"GPUs {n} | total VRAM {tot:.0f} GB | this model needs ~$NEED GB")
assert tot >= $NEED, f"not enough VRAM: {tot:.0f} GB < $NEED GB for $MODEL"
EOF

stamp; echo "----- capture MATH ($N x $SAMPLES) -----"
$PY interp/capture_qa.py --task math --device cuda --model "$MODEL" \
    --n "$N" --samples "$SAMPLES" $THINK --max-new-tokens "$MAXTOK" --out-dir "$CELL" 2>&1 \
  | grep -vE "Loading weights|it/s\]|Warning: You are sending" | tail -25
NPZ=$(ls "$CELL"/*.npz 2>/dev/null | wc -l | tr -d ' ')
stamp; echo "captured $NPZ records"
[ "$NPZ" -lt 50 ] && { stamp; echo "!! too few records to fit a direction — stopping"; exit 1; }
push "$CELL"                                   # an expensive capture must not live on one box

stamp; echo "----- ablation (0, 0.5, 1, 2, 4) + matched random control -----"
$PY interp/steer_confidence.py --act-dir "$CELL" --model "$MODEL" --task math \
    --device cuda --mode amplify --coeffs 0,0.5,1,2,4 --n-eval "$NEVAL" --seed 0 $THINK \
    --out "$CELL/steer_ablation.json" 2>&1 \
  | grep -vE "Loading weights|it/s\]" | tail -30

if [ "${LAYER_SWEEP:-0}" = "1" ]; then
  stamp; echo "----- optional layer sweep -----"
  NL=$($PY -c "import json,glob;print(json.load(open(glob.glob('$HF_HOME/hub/models--*/snapshots/*/config.json')[0])).get('num_hidden_layers','40'))" 2>/dev/null || echo 40)
  for f in 30 50 70 90; do
    L=$(( NL * f / 100 ))
    $PY interp/steer_confidence.py --act-dir "$CELL" --model "$MODEL" --task math \
        --device cuda --mode amplify --layer "$L" --coeffs 0,1,4 --skip-random \
        --n-eval "$NEVAL" --seed 0 $THINK --out "$CELL/steer_layer${L}.json" 2>&1 | tail -6
  done
fi

push "$CELL"
stamp; echo "SESSION COMPLETE for $SHORT — results in $CELL/steer_*.json"
