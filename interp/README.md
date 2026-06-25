# interp/ — spatial-representation interpretability

Mechanistic-interpretability probe of how an LLM represents geometric
relationships when it writes a GeoGen construction. See **[PLAN.md](PLAN.md)**
for the research plan and **[METHODOLOGY.md](METHODOLOGY.md)** for the probing
protocol (what we decode, at which position, prompt-level splits, and the
trivial-vs-non-trivial target rule).

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
| `capture.py` | 1 | Generate + forward-pass; save residual stream per completion token + ground-truth geometry for labeling. |
| `geometry_labels.py` | 1–2 | Extract spatial ground truth (entity→relation, point coords, check facts) from a construction — the bridge for non-trivial probes. |
| `probe.py` | 2 | Per-layer linear probes → decodability-vs-layer. `entity_relation` (real, def-sourced) + `relation` (trivial baseline). |
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

## On a GPU box (after `setup_vast.sh`) — high-powered run

Rent **≥60 GB disk** (a 32 GB box only fits ~8 layers) and a **PyTorch image**.

```bash
# Phase 0' — capability gate (DSL_GOTCHAS addendum on by default)
python interp/capability_check.py --device cuda --tier 1 --n 20 --few-shot all

# Phase 1 — capture: all 29 layers, multi-sample for data, lean disk
python interp/capture.py --device cuda --n 100 --few-shot all \
    --samples 4 --require-ground-truth --layers all \
    --out-dir interp/activations/run

# Phase 2 — non-trivial probes (PCA-100 by default; CPU-only, no GPU)
python interp/probe.py --act-dir interp/activations/run --labeler point_coord
python interp/probe.py --act-dir interp/activations/run --labeler angle
python interp/probe.py --act-dir interp/activations/run --labeler entity_relation  # +token baseline
```

`--samples 4` ≈ 4× the labeled positions (the first coord probe was under-powered
at ~240). `--require-ground-truth` skips junk so 29 layers fit disk. `scp
interp/activations/run` to your Mac to keep probing offline (free).

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
