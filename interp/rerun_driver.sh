#!/bin/bash
# CORRECTED + Tier-2 re-run (tasks #11 + #12 + #13). Changes vs the original matrix run:
#   1. QA-worded confidence prompts (fixes the geometry-wording bug on QA turns 1 & 3).
#   2. Per-turn thinking for hybrid reasoners (Qwen3.6, GLM): answer turn think-ON,
#      confidence turns think-OFF (--per-turn-think). Dense models get no flag.
#   3. Output-distribution baselines (Kadavath): P(True) + answer-token logprobs +
#      per-letter MC logprobs, stored in meta.jsonl (on by default in capture_qa).
#   4. Benchmarks: mmlu_pro + math + GPQA-Diamond. GSM8K DROPPED (ceiling'd 90-95% for
#      3/4 models). GPQA is GATED: needs HF_TOKEN with accepted terms
#      (hf.co/datasets/Idavidrein/gpqa) — pre-checked below before burning GPU-hours.
#   5. SAMPLES=5 (was 2) on N=150 items -> 750 records/cell, powering within-question
#      for all models, not just GLM. Same seed -> identical items across models.
#   6. Qwen3.6 geometry re-capture at the full 91x4=364 convention (was n=77).
#
# Outputs go to fix_* dirs so the ORIGINAL mtx_*/_temporal runs stay for before/after
# comparison. Self-driving + resumable (capture skips already-captured records).
# Cache freeing is DISK-AWARE: on a big-disk box (>=150G free) model caches are kept so
# the Tier-3 causal session can reuse them without re-downloading.
#
# Rough sequential wall-clock (750 rec/cell, +think on qwen/glm answers, +3 forwards/rec):
#   gemma4 ~17h | qwen36 ~24-30h (think-on) | glm ~6h | mistral ~9h  => ~55-65h on 1 GPU.
#   Two GPUs: run two copies with CUDA_VISIBLE_DEVICES=0/1 and split the model list.
set -u
cd /root/geo || exit 1
export HF_HOME=/root/.hf
PY="${PY:-/venv/main/bin/python}"
N=150; SAMPLES=5; MAXTOK=3072
BENCHES="mmlu_pro math gpqa"
# Multi-GPU: pass a model subset per invocation, pinned via CUDA_VISIBLE_DEVICES, e.g.
#   CUDA_VISIBLE_DEVICES=0 bash interp/rerun_driver.sh qwen36            # the long pole
#   CUDA_VISIBLE_DEVICES=1 bash interp/rerun_driver.sh gemma4 glm mistral

echo "=== preflight: GPQA gate ==="
$PY - <<'PY'
try:
    from datasets import load_dataset
    ds = load_dataset("Idavidrein/gpqa", "gpqa_diamond", split="train")
    print(f"gpqa OK ({len(ds)} items)")
except Exception as e:
    print(f"GPQA NOT ACCESSIBLE ({type(e).__name__}) — set HF_TOKEN + accept terms at "
          f"hf.co/datasets/Idavidrein/gpqa. mmlu_pro/math will still run; gpqa cells will fail.")
PY

dl () { $PY -c "from huggingface_hub import snapshot_download; snapshot_download('$1', ignore_patterns=['*.gguf','*.pth','*consolidated*'])"; }
free_if_tight () {  # keep caches on big-disk boxes for the Tier-3 causal session
  avail=$(df -BG --output=avail /root/.hf 2>/dev/null | tail -1 | tr -dc 0-9)
  if [ -n "$avail" ] && [ "$avail" -lt 150 ]; then
    rm -rf "/root/.hf/hub/models--$(echo "$1" | sed 's#/#--#')"; echo "freed $1 (disk ${avail}G)"
  else
    echo "keeping $1 cache (disk ${avail:-?}G free)"
  fi
}

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

run_gemma4 ()  { echo "===== gemma4 (QA)  $(date +%F_%H:%M) ====="
                 dl "$M_GEMMA" && qa "$M_GEMMA" "gemma4" ""; free_if_tight "$M_GEMMA"; }
run_qwen36 ()  { echo "===== qwen36 (QA + geometry)  $(date +%F_%H:%M) ====="
  dl "$M_QWEN" && {
    qa "$M_QWEN" "qwen36" "--per-turn-think"
    echo "----- qwen36 geometry (91x4, full-n)  $(date +%H:%M) -----"
    $PY interp/capture_temporal.py --device cuda --model "$M_QWEN" \
        --n 91 --samples 4 --per-turn-think --max-new-tokens $MAXTOK --keep-positions entities \
        --out-dir /root/geo/interp/activations/fix_qwen36_temporal 2>&1 \
        | grep -vE "Loading weights|it/s\]" | tail -45
  }; free_if_tight "$M_QWEN"; }
run_glm ()     { echo "===== glm (QA)  $(date +%F_%H:%M) ====="
                 dl "$M_GLM" && qa "$M_GLM" "glm" "--per-turn-think"; free_if_tight "$M_GLM"; }
run_mistral () { echo "===== mistral (QA)  $(date +%F_%H:%M) ====="
                 dl "$M_MISTRAL" && qa "$M_MISTRAL" "mistral" ""; free_if_tight "$M_MISTRAL"; }

MODELS=("$@")
[ ${#MODELS[@]} -eq 0 ] && MODELS=(gemma4 qwen36 glm mistral)
for m in "${MODELS[@]}"; do "run_$m"; done

# Optional RLHF-attribution arm (review Tier-2d): a BASE model would tell us whether the
# knowing-vs-saying gap is an RLHF artifact. NOT enabled: base checkpoints have no chat
# template, so capture_qa needs a raw-completion prompt path first. Deferred.

echo "===== RERUN COMPLETE  $(date +%F_%H:%M) ====="
