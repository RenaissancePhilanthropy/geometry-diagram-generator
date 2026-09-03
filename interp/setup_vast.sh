#!/usr/bin/env bash
# Bootstrap a rented vast.ai (or any CUDA) box to run the Phase-0 capability gate.
#
# Assumes a PyTorch+CUDA base image (torch already installed with CUDA — do NOT
# let pip reinstall a CPU torch over it). Run from the box's home dir:
#
#   export HF_TOKEN=hf_xxx         # optional: faster, un-throttled model download
#   export GH_PAT=ghp_xxx          # optional: only if the repo is private again
#   bash setup_vast.sh
#
# The repo is currently PUBLIC, so no GitHub auth is needed.
set -euo pipefail

# Use a PAT only if one is provided (repo is public; PAT optional).
if [ -n "${GH_PAT:-}" ]; then
  REPO_URL="https://${GH_PAT}@github.com/RenaissancePhilanthropy/geometry-diagram-generator.git"
else
  REPO_URL="https://github.com/RenaissancePhilanthropy/geometry-diagram-generator.git"
fi
BRANCH="feat/spatial-interp"
WORKDIR="${HOME}/geometry-diagram-generator"

echo "==> sanity: CUDA torch present?"
python -c "import torch; assert torch.cuda.is_available(), 'no CUDA!'; \
print('torch', torch.__version__, '| cuda', torch.version.cuda, '|', torch.cuda.get_device_name(0))"

echo "==> ensure git is installed (the pytorch -runtime images often lack it)"
if ! command -v git >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq git || \
    { echo "could not install git — install it manually then re-run"; exit 1; }
fi

echo "==> clone repo @ ${BRANCH}"
if [ ! -d "${WORKDIR}" ]; then
  git clone --branch "${BRANCH}" --single-branch "${REPO_URL}" "${WORKDIR}"
fi
cd "${WORKDIR}"

echo "==> aws cli (for interp/save_off_box.sh -> s3://renphil-geogen-interp; auth = aws sso login)"
command -v aws >/dev/null 2>&1 || pip install -q awscli
mkdir -p ~/.aws; [ -f ~/.aws/config ] || echo "   NOTE: scp ~/.aws/config from the laptop, then: aws sso login --profile renphil --use-device-code"

echo "==> install deps — PIN the image's CUDA torch so nothing can replace it"
# Drop the torch line from requirements, and pin the already-installed torch via
# a constraints file. Constraints stop transitive deps (e.g. nnsight) from
# downgrading/reinstalling torch with a CPU wheel.
grep -viE '^\s*torch(\s|$|>|=|<)' interp/requirements.txt > /tmp/reqs_notorch.txt
python - <<'PY' > /tmp/torch_constraint.txt
import torch; print(f"torch=={torch.__version__.split('+')[0]}")
PY
echo "    pinning $(cat /tmp/torch_constraint.txt)"
pip install --no-input -c /tmp/torch_constraint.txt -r /tmp/reqs_notorch.txt
echo "==> verify CUDA torch survived the install"
python -c "import torch; assert torch.cuda.is_available(), 'torch lost CUDA — a dep clobbered it'; print('ok, cuda still available')"

if [ -n "${HF_TOKEN:-}" ]; then
  echo "==> hugging face auth"
  python -c "from huggingface_hub import login; import os; login(os.environ['HF_TOKEN'])"
else
  echo "==> no HF_TOKEN set — downloading Qwen2.5 anonymously (public model, slower)"
fi

echo "==> READY. Example gate runs (note --device cuda):"
cat <<'EOF'

  cd ~/geometry-diagram-generator

  # zero-shot baseline (matches what we ran on the Mac)
  python interp/capability_check.py --model Qwen/Qwen2.5-7B-Instruct \
      --device cuda --tier 1 --n 20 --few-shot none

  # the one MPS could NOT do — all 20 catalog exemplars (~14k-token prompts)
  python interp/capability_check.py --model Qwen/Qwen2.5-7B-Instruct \
      --device cuda --tier 1 --n 20 --few-shot all

  # full sweep, more output, dump completions for inspection
  python interp/capability_check.py --model Qwen/Qwen2.5-7B-Instruct \
      --device cuda --n 50 --few-shot all --print-output

EOF
