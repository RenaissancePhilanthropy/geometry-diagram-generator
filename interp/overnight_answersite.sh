#!/usr/bin/env bash
# One unattended session on one GPU box, sized for the MATH-AI deadline.
# Answers the two reviewer objections that need compute:
#   1. probe reads at the confidence token, not during the attempt   -> answer-site capture
#   2. "the model uses it" overreaches                               -> ablation (amplify coeff 0)
# Everything else the review asked for was fixable in wording or runs on a laptop.
#
# No generation is needed for the answer-site read: meta.jsonl already holds the full
# turn-2 context and the full answer, so each record is one teacher-forced forward pass.
#
#   ssh -A -p <port> root@<host>          # -A is required: the repo is private
#   cd ~/geometry-diagram-generator && git pull --rebase
#   nohup bash interp/overnight_answersite.sh > ~/answersite.log 2>&1 &
set -uo pipefail

# `nohup bash ...` gets a NON-interactive shell: the vast.ai venv is not on PATH there
# and python3 is the system one without torch. Resolve the interpreter explicitly.
PY="${PY:-/venv/main/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"
"$PY" -c "import torch, transformers, sklearn" 2>/dev/null \
  || { echo "FATAL: $PY lacks torch/transformers/sklearn — set PY=/path/to/python"; exit 1; }
echo "interpreter: $PY"

MODEL=mistralai/Mistral-Small-24B-Instruct-2501
ACT=interp/activations
RES=interp/results
export PYTHONUNBUFFERED=1
# step 0 and step 4 both need the SSO profile; only step 4 used to set it, so a
# missing AWS_PROFILE made the restore fail with a warning and the run continue.
export AWS_PROFILE="${AWS_PROFILE:-renphil}"
export HF_HOME="${HF_HOME:-/root/.hf}"

echo "=== 0. restore the confidence-token cells from S3 (needed for the comparison) ==="
for cell in fix_mistral_math fix_mistral_mmlu_pro fix_mistral_gpqa; do
  aws s3 sync "s3://renphil-geogen-interp/activations/$cell" "$ACT/$cell" --only-show-errors \
    && echo "  restored $cell" || echo "  !! restore FAILED for $cell"
done

echo "=== 1. answer-site capture (the biggest objection) ==="
for task in math mmlu_pro gpqa; do
  echo "--- $task ---"
  "$PY" -m interp.capture_answer_site \
    --meta "$RES/fix_mistral_${task}/meta.jsonl" \
    --task "$task" --model "$MODEL" --per-turn-think \
    --n-traj 16 --out-dir "$ACT/ansite_mistral_${task}" \
    || echo "  !! answer-site capture FAILED for $task"
done

echo "=== 2. ablation + dose-response, now logging per-record confidences ==="
# coeff 0 in amplify mode REMOVES the correctness component: if stated-confidence AUROC
# collapses toward 0.5 there, the report is mediated by this direction, which is stronger
# than the current "amplifying it changes what the model says".
"$PY" -m interp.steer_confidence \
  --act-dir "$ACT/fix_mistral_math" --model "$MODEL" --task math \
  --mode amplify --coeffs 0,0.5,1,2,4 --n-eval 150 --per-turn-think \
  --out "$RES/fix_mistral_math/steer_amplify_ablate.json" \
  || echo "  !! steering FAILED"

echo "=== 3. analysis (CPU) ==="
for task in math mmlu_pro gpqa; do
  "$PY" -m interp.analysis.answer_site_probe \
    --answer-dir "$ACT/ansite_mistral_${task}" \
    --conf-dir   "$ACT/fix_mistral_${task}" \
    --out "$RES/temporal_sites_mistral_${task}.json" \
    || echo "  !! analysis FAILED for $task"
done

echo "=== 4. save off box (must exit 0 before destroying) ==="
bash interp/save_off_box.sh
echo "save_off_box exit=$?  (0 = safe to destroy; 4 = Tier A not pushed, DO NOT destroy)"
