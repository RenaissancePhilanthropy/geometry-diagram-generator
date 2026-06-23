# interp/ — spatial-representation interpretability

Mechanistic-interpretability probe of how an LLM represents geometric
relationships when it writes a GeoGen construction. See **[PLAN.md](PLAN.md)**
for the full research plan.

> **Status:** Phase 0 done; Phase 1–2 infrastructure built and offline-tested.
> Heavy runs (few-shot capability, activation capture) are a **GPU** job —
> Apple Silicon/MPS lacks FlashAttention, so long few-shot prompts OOM (it
> materializes the full O(seq²) attention). Rent a 24 GB card; see
> [`setup_vast.sh`](setup_vast.sh).

## Files

| File | Phase | What |
|------|-------|------|
| `grade.py` | 0 | Render-free grader: completion → parse → validate → lower → compile → check. |
| `capability_check.py` | 0 | Prompt the model on benchmark prompts, grade each, report valid-construction rate. Supports few-shot exemplars. |
| `capture.py` | 1 | Generate + forward-pass; save residual stream at chosen layers for completion positions, with token offsets + parsed DSL for labeling. |
| `probe.py` | 2 | Train per-layer linear probes over captured activations → decodability-vs-layer curve. |
| `test_capture.py`, `test_probe.py` | — | Offline smoke tests (tiny random model / synthetic data). |
| `setup_vast.sh` | — | Bootstrap a rented CUDA box: clone, pin CUDA torch, install, run. |

## Findings so far (Qwen2.5, tier-1 GenExam, MPS)

- **3B too weak** (~5%, malformed). **7B understands the DSL** — zero-shot it
  emits well-formed constructions and reaches `compile`/`lower`; the ~5% is ~3
  *fixable* schema conventions (labels→`annotations`, intersection selector
  `kind`, triangle/rectangle spec fields), not reasoning.
- **few-shot helps but MPS can't fit it**: `none` (~5.6k tok) runs; `3` (~6.9k)
  OOMs partway; `all` (~14k) OOMs at once. Hence the GPU.
- The capability harness now does **relevant per-prompt exemplar selection**
  (`--few-shot relevant:K`) — a local keyword stand-in for production's LLM
  selector, so a small budget is spent on relevant recipes (a square prompt gets
  `square_on_segment`, etc.).

## On a GPU box (after `setup_vast.sh`)

```bash
# Phase 0' — the capability run MPS could not do: all exemplars, relevant subset
python interp/capability_check.py --device cuda --tier 1 --n 20 --few-shot all
python interp/capability_check.py --device cuda --tier 1 --n 20 --few-shot relevant:4

# Phase 1 — capture activations from valid constructions
python interp/capture.py --device cuda --tier 1 --n 100 --few-shot relevant:4 \
    --only-valid --layers all --out-dir interp/activations/tier1

# Phase 2 — where does relation identity become linearly decodable?
python interp/probe.py --act-dir interp/activations/tier1 --labeler relation
```

## Local dev (no GPU)

```bash
pip install -r interp/requirements.txt
interp/.venv/bin/python interp/test_capture.py   # capture plumbing
interp/.venv/bin/python interp/test_probe.py     # probe pipeline
# small capability check on the 3B model (MPS):
python interp/capability_check.py --model Qwen/Qwen2.5-3B-Instruct --n 5 --few-shot relevant:3
```

Next labels to add in `probe.py` (`LABELERS`): point **coordinates** (regression,
via the compiled SymPy truth), the prompt's **numeric angle**, and **intersection
disambiguation** — each a new `meta-record → {pos: label}` function.
