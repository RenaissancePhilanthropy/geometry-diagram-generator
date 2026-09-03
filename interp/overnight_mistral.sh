#!/usr/bin/env bash
# overnight_mistral.sh — one unattended night on a single 80 GB GPU (A100/H100), >=300 GB disk.
#
# Goal: regenerate the Mistral-Small-24B cells lost with the July box, and run the steering
# experiment with the magnitude-matched random control (the MATH-AI paper's stated limitation).
# Order is paper-critical first, so an early cut-off still yields the headline:
#   1. capture  fix_mistral_math      (~3 h)   750 records, full-text meta (needed by steering)
#   2. steer    amplify + add on math  (~2 h)   matched random control, dose sweep
#   3. capture  fix_mistral_mmlu_pro  (~3 h)
#   4. capture  fix_mistral_gpqa      (~3 h)   needs HF_TOKEN with GPQA terms accepted
#   5. save     Tier A -> git (needs GH push auth); Tier B -> S3 needs a fresh SSO login,
#               so it will print instructions rather than succeed unattended (~1 h creds).
#
# Setup (once, on the box):
#   bash setup_vast.sh                        # clones feat/spatial-interp, installs deps + awscli
#   export HF_TOKEN=hf_...                    # GPQA is gated
#   cd ~/geometry-diagram-generator && nohup bash interp/overnight_mistral.sh > overnight.log 2>&1 &
#
# Morning:
#   tail -5 overnight.log                     # expect "OVERNIGHT COMPLETE"
#   aws sso login --profile renphil --use-device-code && export AWS_PROFILE=renphil
#   bash interp/save_off_box.sh               # must exit 0 BEFORE the box is destroyed
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT" || exit 1
export HF_HOME="${HF_HOME:-/root/.hf}"
PY="${PY:-$(command -v python)}"
M="mistralai/Mistral-Small-24B-Instruct-2501"; SHORT=mistral
N=150; SAMPLES=5; MAXTOK=3072          # same settings as rerun_driver.sh (750 records/cell)
ACT="$ROOT/interp/activations"
t0=$(date +%s); stamp () { printf '[%s +%dh%02dm] ' "$(date +%H:%M)" $((($(date +%s)-t0)/3600)) $(((($(date +%s)-t0)%3600)/60)); }

capture () {  # $1 = task
  stamp; echo "===== capture $SHORT x $1 -> fix_${SHORT}_$1 ====="
  $PY interp/capture_qa.py --task "$1" --device cuda --model "$M" \
      --n $N --samples $SAMPLES --max-new-tokens $MAXTOK \
      --out-dir "$ACT/fix_${SHORT}_$1" 2>&1 | grep -vE "Loading weights|it/s\]|Warning: You are sending" | tail -30
  stamp; echo "records: $(ls "$ACT/fix_${SHORT}_$1"/*.npz 2>/dev/null | wc -l)"
}

steer () {  # $1 = mode
  stamp; echo "===== steer $1  (fix_${SHORT}_math, matched random control) ====="
  $PY interp/steer_confidence.py --act-dir "$ACT/fix_${SHORT}_math" --model "$M" --task math \
      --device cuda --mode "$1" --n-eval 150 --seed 0 \
      --out "$ACT/fix_${SHORT}_math/steer_$1.json" 2>&1 | grep -vE "Loading weights|it/s\]" | tail -40
}

stamp; echo "download $M"; $PY -c "from huggingface_hub import snapshot_download; snapshot_download('$M', ignore_patterns=['*.gguf','*.pth','*consolidated*'])"
$PY -c "import torch; print('GPU:', torch.cuda.get_device_name(0), round(torch.cuda.mem_get_info()[1]/2**30), 'GB')"

capture math
steer amplify
steer add
capture mmlu_pro
capture gpqa

stamp; echo "===== save (Tier A now; Tier B needs your SSO login in the morning) ====="
bash interp/save_off_box.sh --small || true
bash interp/save_off_box.sh || echo "!! Tier B not saved (expected without live SSO creds) — log in and rerun save_off_box.sh before destroying"
stamp; echo "OVERNIGHT COMPLETE"
