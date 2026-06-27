# Proposal: Interpretability study of spatial reasoning in the geometry generator

**Author:** Mei Chen · **Date:** 2026-06-23 · **Status:** Phase 0 complete, requesting go-ahead for Phase 1+

## Summary

I'm proposing a focused interpretability study on the model behind our geometry
diagram generator: **when an LLM constructs a geometric figure, how does it
internally represent spatial relationships** (perpendicularity, midpoint, "the
higher intersection," a specific angle), and *where* in the network do those
representations live? Phase 0 (a local capability check) is done. To proceed I'm
requesting approval to **rent an on-demand cloud GPU**, estimated at **well under
$100 total** for the remaining phases.

## Why this is worth doing

- **We have a rare, clean research substrate.** Most interpretability work fights
  with free-form text. Our pipeline makes the model emit an *explicit construction
  language* with **ground-truth geometry** (exact coordinates + a 15-predicate
  checker) for every output. That lets us correlate the model's internals against
  *known* spatial structure — something most interp setups can't do.
- **Direct product value.** Understanding where/how the model encodes geometric
  relations tells us *why* it fails on certain constructions and where to
  intervene — feeding back into prompt design, strategy choice, and model
  selection for the generator itself.
- **External value.** A clean result ("is 'perpendicular' a linear direction, and
  where does it emerge?") is publishable and raises the profile of the work.

## Progress to date (Phase 0 — capability gate)

Built and ran locally (Apple Silicon), at no cost:

- A **render-free grader** that scores model output through our real pipeline
  (parse → validate → lower → compile → check).
- A **capability harness** testing Qwen2.5 (3B and 7B) on benchmark geometry
  prompts.

Findings:

| Model | Result | Interpretation |
|-------|--------|----------------|
| Qwen2.5-3B | ~5%, malformed output | Too weak — not a probing target |
| Qwen2.5-7B | ~5% fully valid, but emits well-formed constructions and reaches deep pipeline stages | **Understands the task**; failures are ~3 *fixable* schema conventions, not reasoning |

**Conclusion:** 7B is the right model. Its low score is a fixable prompting
problem (it needs a few relevant worked examples), not a capability ceiling. The
study is viable — *once we can run it on the right hardware.*

## The blocker, briefly

Fixing the score means slightly longer prompts (worked examples). Attention memory
grows with the **square** of prompt length. Standard GPUs handle this with
"FlashAttention"; **Apple Silicon (our local machine) does not**, so longer
prompts exhaust memory and crash. This is an architecture gap in the local
backend — not something more RAM solves. The later phases (capturing the model's
internal activations across many forward passes) are also impractically slow
locally.

## Proposed plan

Run on a **rented, on-demand GPU** (single 24 GB card — e.g. RTX 4090 on
RunPod/Vast). Our code is already GPU-ready.

| Phase | Work | GPU need |
|-------|------|----------|
| 0′ | Re-run the capability gate with proper few-shot examples; confirm a usable success rate | Hours |
| 1 | **Activation capture** — record the model's internal state at every layer while it constructs figures, tagged to ground-truth geometry | Bulk of usage |
| 2 | **Linear probes (core experiment)** — decode coordinates, relation type, intersection choice, and angle from internals; plot *where* each becomes decodable | Light |
| 3 | **Causal patching** — swap internals between near-identical prompts (60°↔70°, perpendicular↔parallel) to find where relations are *causally* encoded | Light |
| 4 | **(Stretch) SAE features** — hunt for interpretable features firing on geometric concepts | Medium |

## Ask

- **One on-demand GPU instance, rented hourly** (not a standing reservation).
- **Estimated cost: well under $100 total** across all phases (RTX 4090 ≈
  $0.40–0.70/hr; the work is tens of GPU-hours, spun down between sessions).
- **Time:** a few weeks of part-time effort.

## Deliverables

1. A passing capability gate (7B + few-shot) confirming the model can do the task.
2. **Layer-wise decodability curves** per geometric property — the headline result.
3. Causal localization of where key relations/angles are encoded.
4. A short write-up; publishable if results are clean.

## Risks & mitigations

- *Model can't be made reliable enough* → bump to Qwen2.5-14B (same approach);
  Phase 0 already suggests 7B + examples will suffice.
- *Token-position alignment is fiddly* → mitigated by our explicit DSL output.
- *Cost overrun* → on-demand hourly billing with a hard cap; spin down when idle.
