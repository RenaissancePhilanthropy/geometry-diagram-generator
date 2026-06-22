# Spatial-representation interpretability — plan

## The question
When an LLM is asked to *construct* a geometry figure, how does it internally
represent the spatial relationships — perpendicularity, midpoint, "the higher
intersection," a specific angle? **Where** in the network do these become
decodable, and are they **linear directions / discrete features** or something
messier?

## Why GeoGen is a good substrate
This project gives us two things most interp setups lack:
1. An LLM that emits **explicit constructions** (the recipe DSL / `DiagramIR`)
   rather than free text — so the spatial content is localized to specific
   output tokens (`perp`, `inter`, point names, angle literals).
2. **Ground-truth geometry** for every prompt (SymPy coordinates + the
   15-predicate checker). So we can correlate internals against *known* spatial
   structure, token-aligned to what the model is writing.

## Model + hardware
- **Model:** `Qwen/Qwen2.5-7B-Instruct` — open weights, strong at math/structured
  output (so it can actually do the task), and has **Qwen-Scope** pretrained SAEs.
  Use a small model (`Qwen/Qwen2.5-3B-Instruct` or `google/gemma-2-2b-it`) for
  fast iteration while building the harness.
- **Hardware:** Apple Silicon, PyTorch **MPS**, **bf16**.
  7B bf16 ≈ 15 GB weights + activation cache + overhead → run on the **≥32 GB**
  machine. Do **not** 4-bit quantize for real runs (it muddies activations).

## Tooling
- **Capability check:** plain `transformers` (no interp lib).
- **Activation capture:** **nnsight** — wraps arbitrary HF models, most reliable
  for Qwen2.5's architecture. (TransformerLens is an option *only if* it lists
  Qwen2.5 in its supported archs — verify; otherwise use nnsight.)
- **Probes:** cached activations + scikit-learn / torch. No special lib needed.
- **SAE features (later):** Qwen-Scope SAEs via SAELens; Delphi for auto-interp.
  Verify Qwen-Scope covers the 2.5-7B layers we care about before relying on it.

## Phases
**Phase 0 — Capability gate** (`capability_check.py`).
Download Qwen2.5-7B, prompt it with the project's recipe-DSL instructions on
~20–30 GeoGenBench prompts, parse → lower → compile → check with the existing
pipeline, measure the valid-construction rate.
*Gate:* if Qwen can't produce usable constructions, bump to Qwen2.5-14B or add
few-shot exemplars **before** any interp work — a model's internals only matter
if it can do the task.

**Phase 1 — Activation-capture harness.**
Forward passes (nnsight) on geometry prompts; cache the residual stream at every
layer at chosen token positions — the tokens where the model writes each
geometric entity/relation. Save activations + metadata linking each position to
its ground-truth geometric role.

**Phase 2 — Linear probes (the core experiment).**
Train probes on cached activations to decode, per layer:
- point **coordinates** (regression),
- **relation type** (perpendicular / parallel / midpoint / tangent — classification),
- **intersection disambiguation** ("the higher one"),
- the prompt's **numeric angle** (e.g. 60° vs 70°).
Plot decodability vs layer → *where* spatial structure emerges, and whether it's linear.

**Phase 3 — Causal / activation patching.**
Swap activations between minimal-pair prompts (60° ↔ 70°, perpendicular ↔
parallel) to locate where the relation/angle is *causally* encoded — not just
correlationally decodable.

**Phase 4 — SAE features (stretch).**
Run Qwen-Scope SAEs on cached activations; hunt for interpretable features that
fire on geometric concepts (perpendicular, intersection, midpoint).

## What we'd report
Layer-wise decodability curves per geometric property; causal locations from
patching; any clean SAE features. Headline question: *is "perpendicular" (etc.)
a linear direction / discrete feature, and where does it live?*

## Risks / open questions
- Qwen2.5 task capability (the Phase-0 gate).
- TransformerLens Qwen2.5 support → fall back to nnsight.
- Qwen-Scope layer coverage for 2.5-7B.
- **Token alignment:** mapping ground-truth geometric roles to exact output
  token positions needs care (depends on how the DSL tokenizes).
- MPS speed: fine for research-scale; if we need thousands of forward passes,
  consider a cloud GPU (single 24 GB card runs 7B fp16 far faster).

## First session on the big machine
1. `pip install -r interp/requirements.txt` (into the project venv or a fresh one).
2. `python interp/capability_check.py` → eyeball outputs, then wire the auto-grade
   (TODO + module pointers are in the file).
3. If the gate passes, build the Phase-1 capture harness.
