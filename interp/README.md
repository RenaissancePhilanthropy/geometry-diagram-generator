# interp/ — spatial-representation interpretability

Mechanistic-interpretability probe of how an LLM represents geometric
relationships when it writes a GeoGen construction. See **[PLAN.md](PLAN.md)**
for the full research plan.

> **Status:** scaffold. Run on an Apple-Silicon Mac with **≥32 GB** unified
> memory (Qwen2.5-7B in bf16 needs ~15 GB weights + cache). The code here has
> **not been run yet** — `capability_check.py` is the Phase-0 starting point.

## Setup (Apple Silicon)

From the repo root, into a virtualenv (the project's `.venv` or a fresh one):

```bash
pip install -r interp/requirements.txt
```

PyTorch's macOS wheel includes the **MPS** (Metal) backend automatically — no
CUDA. First run downloads Qwen2.5-7B-Instruct (~15 GB) from Hugging Face.

## Phase 0: capability gate

```bash
# from the repo root
python interp/capability_check.py                          # Qwen2.5-7B (default)
python interp/capability_check.py --model Qwen/Qwen2.5-3B-Instruct   # faster
```

Prompts the model with the project's recipe-DSL instructions on a few geometry
prompts and prints the output. First just **eyeball** whether it looks like a
valid `RecipeDSL`; then wire the automated parse → lower → compile → check grade
(TODO with module pointers is in the file) to get a real valid-construction rate.

If the rate is usable, move on to the Phase-1 activation-capture harness (PLAN.md).
