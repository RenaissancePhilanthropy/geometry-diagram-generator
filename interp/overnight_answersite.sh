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

MODEL=mistralai/Mistral-Small-24B-Instruct-2501
ACT=interp/activations
RES=interp/results
export PYTHONUNBUFFERED=1

echo "=== 0. restore the confidence-token cells from S3 (needed for the comparison) ==="
for cell in fix_mistral_math fix_mistral_mmlu_pro fix_mistral_gpqa; do
  aws s3 sync "s3://renphil-geogen-interp/activations/$cell" "$ACT/$cell" --only-show-errors \
    && echo "  restored $cell" || echo "  !! restore FAILED for $cell"
done

echo "=== 1. answer-site capture (the biggest objection) ==="
for task in math mmlu_pro gpqa; do
  echo "--- $task ---"
  python -m interp.capture_answer_site \
    --meta "$RES/fix_mistral_${task}/meta.jsonl" \
    --task "$task" --model "$MODEL" --per-turn-think \
    --n-traj 16 --out-dir "$ACT/ansite_mistral_${task}" \
    || echo "  !! answer-site capture FAILED for $task"
done

echo "=== 2. ablation + dose-response, now logging per-record confidences ==="
# coeff 0 in amplify mode REMOVES the correctness component: if stated-confidence AUROC
# collapses toward 0.5 there, the report is mediated by this direction, which is stronger
# than the current "amplifying it changes what the model says".
python -m interp.steer_confidence \
  --act-dir "$ACT/fix_mistral_math" --model "$MODEL" --task math \
  --mode amplify --coeffs 0,0.5,1,2,4 --n-eval 150 --per-turn-think \
  --out "$RES/fix_mistral_math/steer_amplify_ablate.json" \
  || echo "  !! steering FAILED"

echo "=== 3. analysis (CPU) ==="
for task in math mmlu_pro gpqa; do
  python -m interp.analysis.answer_site_probe \
    --answer-dir "$ACT/ansite_mistral_${task}" \
    --conf-dir   "$ACT/fix_mistral_${task}" \
    --out "$RES/temporal_sites_mistral_${task}.json" \
    || echo "  !! analysis FAILED for $task"
done

echo "=== 4. save off box (must exit 0 before destroying) ==="
AWS_PROFILE=renphil bash interp/save_off_box.sh
echo "save_off_box exit=$?  (0 = safe to destroy; 4 = Tier A not pushed, DO NOT destroy)"
