# GeoGen — NeurIPS Datasets & Benchmarks paper outline

Working document. Updated as evidence accumulates.

## One-line claim

GeoGen is the first benchmark that measures **generative geometric reasoning** in LLMs with **fully-automatic, geometry-aware verification** — bridging the gap between text-only math benchmarks (which can't test diagrammatic reasoning) and existing geometry benchmarks (which only test understanding of *given* diagrams).

## Headline contribution (one paragraph)

We release **GeoGen**, a benchmark of N+ natural-language prompts asking an LLM to *produce* a geometry diagram (as TikZ/SVG), paired with N+ machine-checkable geometric properties that any correct rendering must satisfy. Verification runs in <100 ms per scenario via a SymPy-based property checker, requires no human grading, and (we show) correlates with expert judgments at κ ≥ 0.X. Across F frontier models and S generation strategies on G scenarios, we observe a Y-percentage-point pass-rate spread, with a clear Pareto frontier between cost and capability. Contributions: (1) the benchmark + verification pipeline, (2) a leaderboard for current frontier models, (3) a taxonomy of failure modes specific to generative geometry, and (4) an open-source generation/grading toolkit.

## Why this matters / Why now

1. **Existing geometry benchmarks measure understanding, not generation.** Geometry3K, GeoQA, UniGeo, MathVista's geometry subset, GeoEval, and OlympiadBench all give the model a diagram and ask a question. None test whether a model can *produce* a correct diagram from a description. Frontier models are increasingly used as agents that must produce visual artifacts (slides, math worksheets, technical drawings) — generative capability is the part that's *not* measured.

2. **Text-math benchmarks (GSM8K, MATH, AIME, FrontierMath) skip diagrams entirely.** Geometry without diagrams is a missing modality.

3. **GenExam (released 2026) introduces text→exam-style image generation but uses LLM-judged scores.** GeoGen is complementary: same generation task family, but in a geometric domain where we can do *automatic, verifiable* grading via symbolic computation rather than vision-LM scoring.

4. **No public leaderboard exists for diagram generation in geometry.** Headline metric vacuum that GeoGen fills.

## Anticipated reviewer pushback (and our defenses)

| Pushback | Defense |
|---|---|
| "Templated prompts aren't naturalistic" | We pair templated (provably-correct GT) with curriculum-extracted prompts (LLM-rewritten in student voice from real textbook content). Report results separately. |
| "SymPy property lists aren't complete characterizations" | (a) For ~50 sampled scenarios, we exhibit a *certified-complete* check set proving any diagram passing all listed checks is congruent to the intended construction. (b) For the rest, we report a "completeness witness" coverage metric. (c) Human-correlation study shows automatic verdict agrees with experts at κ ≥ 0.X across N=200 samples. |
| "30 templates is small" | After cap fix, we cover 30 templates × 6-25 instances each = 600 scenarios, plus 201 curriculum-extracted scenarios spanning broader topics (3D, transformations, proofs, coordinate plane). |
| "Verification has soft spots (TikZ-source `mark_present`)" | We replace string checks with a render-aware checker that parses the rendered SVG for the actual right-angle glyph, segment ticks, etc. (Hardening pass — see workplan.) |
| "Why TikZ specifically?" | TikZ is text-emitting (so any LLM can target it without image tokens), exactly reproducible, and compiles to vector SVG suitable for downstream verification. We show our pipeline is renderer-agnostic by also accepting and grading raw SVG output (ablation). |
| "Models will train on this" | We commit to releasing N held-out test scenarios that are revealed only at evaluation time, plus a procedural variant generator (the same template engine that produced the train split, parameterized differently) so reviewers can re-roll if contamination is suspected. |

## Headline figures (in priority order)

### Figure 1 (HEADLINE) — Pareto: pass-rate vs cost-per-scenario

- x-axis: USD per passed scenario (log scale) — *cost-amortized success*, not just $/call
- y-axis: pass-rate (%) on full benchmark
- Each point = (model, strategy) combo
- Color = model family; shape = strategy
- Pareto frontier line marked
- Annotation: "structured + Haiku is on the frontier; raw_code + Opus is dominated"

### Figure 2 — Per-template heatmap

- Rows = 30 templates, Cols = M models (best strategy per model)
- Cell color = pass rate
- Reveals **which constructions are hard for everyone** (e.g., cyclic quadrilaterals) vs **what differentiates the leader** (e.g., 2-altitude constructions only the frontier solves).
- Most-cited figure in benchmark papers; high diagnostic value.

### Figure 3 — Failure-mode stacked bar

For each (model, strategy):
- gen_failure (LLM produced no/invalid output)
- render_failure (TikZ won't compile)
- topology_failure (objects exist but wrong incidence)
- metric_failure (right shapes but wrong distances/angles)
- mark_failure (geometry correct but labels/marks missing)

Diagnoses *what's wrong* not just *how often*.

### Figure 4 — Scaling curve: # in-context examples × pass-rate (recipe strategy ablation)

If recipe strategy is interesting, show how few-shot recipe count affects success — supports the claim that GeoGen is useful for prompt-engineering research, not just absolute scoring.

## Key tables

### Table 1 — Dataset composition

| Split | # scenarios | Tiers | Source | Avg props/scen | Topics |
|---|---|---|---|---|---|
| Templated | 600 | 200/200/200 | Synthetic | 3.4 | Plane Euclidean |
| Curriculum | 201 | 36/128/37 | LLM-extracted from K-12 textbooks | TBD | + 3D, transformations, proofs, coord-plane |
| Total | 801 | … | … | … | … |

### Table 2 — Leaderboard (full benchmark)

Sortable by pass-rate; columns: model, strategy, T1/T2/T3 pass-rate, total $, mean latency.

### Table 3 — Verification reliability vs human raters

| Check type | N samples | Cohen's κ vs experts | False-positive rate | False-negative rate |
|---|---|---|---|---|
| right_angle | 50 | 0.X | … | … |
| midpoint | … | … | … | … |
| (etc.) | | | | |

### Table 4 — Comparison with prior geometry benchmarks

| Benchmark | Task | Auto-grading | Domain | # items | Modality | Year |
|---|---|---|---|---|---|---|
| Geometry3K | QA | partial | plane | 3,002 | image+text | 2021 |
| GeoQA | QA | partial | plane | 5,010 | image+text | 2021 |
| UniGeo | QA + proof | proof only | plane | 14,541 | image+text | 2022 |
| MathVista (geo) | QA | yes | mixed | 1,000s | image+text | 2024 |
| GeoEval | QA | yes | plane | … | image+text | 2024 |
| OlympiadBench (geo) | proof | LLM-judge | olympiad | … | image+text | 2024 |
| GenExam | generate exam image | LLM-judge | broad | 600 | text→image | 2026 |
| **GeoGen (ours)** | **generate diagram** | **automatic, geometric** | **plane + curriculum** | **801** | **text→TikZ→SVG** | **2026** |

## Sections

### 1. Introduction
- Motivating example (one paragraph, one figure showing 4 model attempts at "draw the medial triangle" — 3 wrong, 1 right)
- Contributions list (the 4 above)
- Roadmap

### 2. Related work
- Geometry-understanding benchmarks (Geometry3K, GeoQA, UniGeo, MathVista, GeoEval, OlympiadBench)
- Math benchmarks without diagrams (GSM8K, MATH, AIME, FrontierMath)
- Image-generation benchmarks (GenExam, T2I-CompBench, DrawBench)
- Auto-formalization & symbolic-grading benchmarks (Lean, Isabelle, AlphaProof)
- Tool-use & agent benchmarks (where diagram production has shown up incidentally — SWE-bench-VL?)

### 3. Benchmark design
- 3.1 Task formulation (text → TikZ → SVG, with rendering as ground-truth fixative)
- 3.2 Templated scenarios — generation, parameter sweeps, label rotation
- 3.3 Curriculum scenarios — pipeline, source documents, quality control
- 3.4 Property language (right_angle, midpoint, parallel, …)
- 3.5 Verification pipeline (SymPy, tolerance, soft-pass semantics)
- 3.6 Dataset statistics

### 4. Verification reliability
- 4.1 Completeness analysis (sampled "certified-complete" check sets)
- 4.2 Human-correlation study (200 samples, 3 raters, IRR)
- 4.3 Adversarial analysis (can we construct diagrams that pass all listed checks but are clearly wrong?)

### 5. Models & strategies
- 5.1 Models tested
- 5.2 Strategies (raw_code, structured, recipe) — algorithms + minimal ablations
- 5.3 Cost / latency methodology

### 6. Results
- 6.1 Headline (Fig. 1, Table 2)
- 6.2 Per-tier breakdown
- 6.3 Per-template heatmap (Fig. 2)
- 6.4 Failure modes (Fig. 3)
- 6.5 Strategy ablations (raw vs structured vs recipe)
- 6.6 Cost-quality Pareto

### 7. Discussion
- What's hard for current models
- Where templated vs curriculum diverge in difficulty
- Limitations: 2D Euclidean only; no proof construction; …
- Threats to validity: contamination, soft-pass semantics, LLM-judged check authoring

### 8. Conclusion + datasheet pointer

### Appendices
- A. Full template specifications (all 30, with example renderings)
- B. Property type reference (signatures, semantics, validation code)
- C. Per-scenario gold check completeness witnesses
- D. Reproduction instructions, Docker images, dataset card
- E. Prompts used in human-correlation study + rater instructions
- F. Failure-mode coding manual

## Critical-path workplan to submission

Roughly ordered by dependency. Items marked **B** are blockers for the headline claim.

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | **B** Pilot leaderboard (4M × 3S × 30) | in progress | Confirms dataset has signal |
| 2 | Cap-fix → regenerate scenarios | DONE (`240afa8`) | All 30 templates now appear |
| 3 | **B** Verification hardening: bounds for `point_on_segment`, render-aware `mark_present` | TODO | Removes biggest reviewer attack |
| 4 | **B** Unify templated + curriculum into one benchmark spec | TODO | Same schema, single loader |
| 5 | **B** Full leaderboard run (≥6 models × 3 strategies × full benchmark × 3 repeats) | TODO | After pilot signal confirmed |
| 6 | **B** Human-correlation study (N=200) | TODO | Use existing benchmark/ irr.py |
| 7 | Failure-mode taxonomy + automated coder | TODO | Feeds Figure 3 |
| 8 | Per-template heatmap renderer | TODO | Feeds Figure 2 |
| 9 | Pareto plotter | TODO | Feeds Figure 1 |
| 10 | Topic-breadth templates: 3D, transformations, coord-overlay, proof aux-line | TODO | Only if outline says we need them; curriculum may cover this |
| 11 | Strategy ablations | TODO | recipe-no-recipes, structured-two-phase, etc. |
| 12 | Held-out test split (contamination defense) | TODO | Generate, withhold, document |
| 13 | Dataset card + datasheet (Gebru et al.) | TODO | Required for D&B |
| 14 | Public leaderboard site | TODO | HF Spaces or static |
| 15 | Related-work section + comparison table | TODO | Tied to ICML or NeurIPS dates |
| 16 | Camera-ready / arXiv | TODO | Final |

## Open questions to settle

1. **Single benchmark or split?** Templated and curriculum could be reported separately (cleaner science) or as one weighted score (cleaner story). Recommendation: report both, headline = unweighted average.
2. **Strategy in scope of paper?** "Strategy" mixes prompting + scaffolding + tool use. Cleaner is to report only `raw_code` (zero-shot diagram generation as a baseline) and `structured` (with our recommended pipeline) — recipe goes into the appendix as a "future-work-able prompt-engineering knob."
3. **Tier-1 saturation already visible.** Pilot showed Opus + raw_code passes 100% of T1. If frontier saturates at T1, we should consider:
   - (a) Removing T1 from the headline (use only T2+T3)
   - (b) Adding a T0 "trivial sanity" tier explicitly
   - (c) Tightening T1 checks (mark_present today is rendering-only / soft-pass)
4. **Headline metric: pass-rate vs strict-pass-rate?** Soft-pass currently counts as pass in many places. Reviewers will want strict-pass as the main metric. We should decide and document.
5. **Visual judge?** We have a TikZ→PNG→VLM judge in `util/llm_judge.py`. Including it as a corroborating signal in the human-correlation study would strengthen Section 4 substantially.

## What we know already (from existing data)

- **Sonnet + structured on 201 curriculum scenarios (Apr 13 run)**: 78 pass, 8 soft-pass, 115 fail = **39% strict pass / 43% pass+soft**.
- Avg duration 22.1s/scenario, ~20K input + 1.5K output tokens.
- Total compute: 4M input + 311K output tokens, ~$15-30 at Sonnet pricing.
- Failure modes (sampled): coordinate placement errors, missing tick marks, off-canvas elements, malformed environment usage (`tkzelements undefined`).

## What the pilot will tell us

- **Spread**: do frontier vs cheap models differ by >20pp on the same benchmark? If yes, dataset is discriminative.
- **Strategy gap**: does `structured` beat `raw_code` consistently? If yes, our pipeline contribution is justified.
- **Pareto shape**: is there a clear cost-quality knee? If yes, we have a meaningful Figure 1.
- **Tier monotonicity**: do all models score T1 ≥ T2 ≥ T3? If not, our tier definitions are suspect.
