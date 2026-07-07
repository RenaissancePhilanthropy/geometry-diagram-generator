#!/bin/bash
# CORRECTED re-run (bundles tasks #11 + #12):
#   1. QA matrix with TASK-WORDED confidence prompts (fixes the geometry-wording bug:
#      the old runs asked about a "construction" being "geometrically correct" on QA).
#   2. Per-turn thinking: hybrid reasoners (Qwen3.6, GLM) answer with think-ON but give
#      confidence with think-OFF (clean 1-line read) — dense models (Gemma-4, Mistral)
#      get no thinking flag.
#   3. Qwen3.6 geometry re-capture at full n (the original was 77 records vs 364).
#
# Outputs go to fix_* dirs so the ORIGINAL mtx_*/_temporal runs are preserved for
# before/after comparison. Self-driving + resumable (capture skips done records).
# One model in VRAM/disk at a time: download -> run -> free (82 GB disk constraint).
set -u
cd /root/geo || exit 1
export HF_HOME=/root/.hf
PY=/venv/main/bin/python
N=250; SAMPLES=2; MAXTOK=2048        # bump SAMPLES to 5-8 for QA within-question power
BENCHES="mmlu_pro gsm8k math"        # gsm8k is ceiling'd (~94%); drop it to save time

dl ()   { $PY -c "from huggingface_hub import snapshot_download; snapshot_download('$1', ignore_patterns=['*.gguf','*.pth','*consolidated*'])"; }
free () { rm -rf "/root/.hf/hub/models--$(echo "$1" | sed 's#/#--#')"; echo "freed $1"; }

qa () {  # $1=model $2=short $3=think-flag
  for B in $BENCHES; do
    echo "----- $2 x $B  $(date +%H:%M) -----"
    $PY interp/capture_qa.py --task "$B" --device cuda --model "$1" \
        --n $N --samples $SAMPLES $3 --max-new-tokens $MAXTOK \
        --out-dir /root/geo/interp/activations/fix_${2}_${B} 2>&1 \
        | grep -vE "Loading weights|it/s\]|Warning: You are sending" | tail -45
  done
}

M_GEMMA="google/gemma-4-26B-A4B-it"; M_QWEN="Qwen/Qwen3.6-27B"
M_GLM="zai-org/GLM-4.7-Flash";       M_MISTRAL="mistralai/Mistral-Small-24B-Instruct-2501"

echo "===== gemma4 (QA)  $(date +%F_%H:%M) ====="
dl "$M_GEMMA"   && qa "$M_GEMMA"   "gemma4"  "";                 free "$M_GEMMA"

# Qwen3.6: QA + geometry back-to-back so the (large) download is shared, then free.
echo "===== qwen36 (QA + geometry)  $(date +%F_%H:%M) ====="
dl "$M_QWEN" && {
  qa "$M_QWEN" "qwen36" "--per-turn-think"
  echo "----- qwen36 geometry (full n)  $(date +%H:%M) -----"
  $PY interp/capture_temporal.py --device cuda --model "$M_QWEN" \
      --n 200 --samples 2 --per-turn-think --max-new-tokens $MAXTOK --keep-positions entities \
      --out-dir /root/geo/interp/activations/fix_qwen36_temporal 2>&1 \
      | grep -vE "Loading weights|it/s\]" | tail -45
}; free "$M_QWEN"

echo "===== glm (QA)  $(date +%F_%H:%M) ====="
dl "$M_GLM"     && qa "$M_GLM"     "glm"     "--per-turn-think"; free "$M_GLM"

echo "===== mistral (QA)  $(date +%F_%H:%M) ====="
dl "$M_MISTRAL" && qa "$M_MISTRAL" "mistral" "";                 free "$M_MISTRAL"

echo "===== RERUN COMPLETE  $(date +%F_%H:%M) ====="
