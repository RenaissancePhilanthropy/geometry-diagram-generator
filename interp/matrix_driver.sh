#!/bin/bash
# Full QA metacognition matrix: 4 models x {mmlu_pro, gsm8k, math} x 3-turn (pre/answer/post).
# Self-driving + resumable (capture_qa skips already-captured records). One model in VRAM/disk
# at a time: download -> run its 3 benchmarks -> free. Thinking models get --no-think.
set -u
cd /root/geo || exit 1
export HF_HOME=/root/.hf
PY=/venv/main/bin/python
N=250; SAMPLES=2; MAXTOK=2048
BENCHES="mmlu_pro gsm8k math"

run_model () {
  local M="$1" SHORT="$2" NT="$3"
  echo "===== MODEL $M  (short=$SHORT, nothink='$NT')  $(date +%F_%H:%M) ====="
  $PY -c "from huggingface_hub import snapshot_download; snapshot_download('$M', ignore_patterns=['*.gguf','*.pth','*consolidated*'])" \
      || { echo "DOWNLOAD FAILED: $M"; return 1; }
  for B in $BENCHES; do
    echo "----- $SHORT x $B  $(date +%H:%M) -----"
    $PY interp/capture_qa.py --task "$B" --device cuda --model "$M" \
        --n $N --samples $SAMPLES $NT --max-new-tokens $MAXTOK \
        --out-dir /root/geo/interp/activations/mtx_${SHORT}_${B} 2>&1 \
        | grep -vE "Loading weights|it/s\]|Warning: You are sending" | tail -45
  done
  rm -rf "/root/.hf/hub/models--$(echo "$M" | sed 's#/#--#')"
  echo "freed $M cache"
}

# Gemma-4 is already cached -> first (no download wait). Qwen3.6 + GLM are hybrid/thinking -> --no-think.
run_model "google/gemma-4-26B-A4B-it"                 "gemma4"  ""
run_model "Qwen/Qwen3.6-27B"                          "qwen36"  "--no-think"
run_model "zai-org/GLM-4.7-Flash"                     "glm"     "--no-think"
run_model "mistralai/Mistral-Small-24B-Instruct-2501" "mistral" ""
echo "===== MATRIX COMPLETE  $(date +%F_%H:%M) ====="
