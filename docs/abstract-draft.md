# GeoGen — abstract drafts

Three drafts at decreasing length and increasing punch. We'll iterate after the leaderboard data lands.

---

## Draft 1 — Long form (~200 words)

Existing geometry benchmarks measure whether language models can *interpret* a given diagram and answer a question about it. None measures whether a model can *produce* a correct diagram from a description — yet diagram production is increasingly the deployed task, as LLMs are asked to author worksheets, slides, and technical illustrations. We introduce **GeoGen**, the first benchmark for generative geometric reasoning with **fully-automatic, geometry-aware verification**. GeoGen pairs N natural-language prompts ("draw an acute triangle ABC with the altitude from A meeting BC at H") with machine-checkable geometric properties that any correct rendering must satisfy ("angle AHB is right; H lies on segment BC"). Verification compiles the model's TikZ output to symbolic geometry via SymPy and decides each property in milliseconds, requiring no human grading or vision-language judge. Across F frontier models and S generation strategies on the full benchmark, we observe a Y-percentage-point pass-rate spread, a clear cost-quality Pareto frontier, and a per-construction failure pattern that distinguishes models in ways tier-1 averages do not. We release the dataset, the procedural template engine that generated it (allowing reviewers to roll new contamination-free splits), the verification toolkit, and a public leaderboard.

---

## Draft 2 — Short form (~100 words, target conference abstract)

Frontier LLMs are increasingly deployed to *produce* diagrams — for slides, math worksheets, technical illustrations — yet existing geometry benchmarks only test understanding of *given* diagrams. We introduce **GeoGen**, a benchmark for generative geometric reasoning with **fully-automatic verification**: prompts are paired with machine-checkable geometric properties (angle equalities, midpoints, tangencies, etc.) decided in milliseconds via SymPy, no human grading required. Across F models × S strategies on N prompts we find a Y-point pass-rate spread and a clear cost-quality Pareto. We release the dataset, the procedural template engine (for contamination-free re-splitting), the verification toolkit, and a public leaderboard.

---

## Draft 3 — Punchline (~50 words, for talk title slide / tweet)

**GeoGen** is the first geometry benchmark that asks LLMs to *produce* diagrams, with answers graded by symbolic geometry instead of vision-language judges. N prompts, automatic verification, public leaderboard. Frontier models score Y%, with a clear cost-quality frontier and per-construction failure modes that distinguish them.

---

## Once we have data, fill in:

| Variable | Source | Current best estimate |
|---|---|---|
| **N** (# prompts) | `len(scenarios_generated.yaml) + len(scenarios_geometry_curriculum.yaml)` | 600 + 201 = **801** |
| **F** (# models in headline) | leaderboard config | 4-6 (Opus, Sonnet, Haiku, GPT-5.1, optionally GPT-4.1, optionally an open model) |
| **S** (# strategies) | leaderboard config | 3 (raw_code, structured, recipe) |
| **Y** (pass-rate spread) | from completed pilot | TBD; pilot Opus near-saturated tier 1, so spread is probably top of T2/T3 |
| **per-construction divergence** | per-template heatmap | TBD |
| **κ vs human raters** | human-correlation study | TBD; target ≥ 0.7 |

---

## Title candidates

1. **GeoGen: A Benchmark for Generative Geometric Reasoning with Symbolic Verification**
2. **GeoGen: Drawing on Demand — Evaluating LLM Diagram Generation in Plane Geometry**
3. **GeoGen: When LLMs Pick Up the Compass — A Generative Benchmark for Geometric Reasoning**
4. **From Reading to Drawing: GeoGen Benchmarks Generative Geometric Reasoning in LLMs**
5. **The GeoGen Benchmark: Symbolic Verification of LLM-Generated Geometry Diagrams**

My pick: #1 (most-Google-able, says exactly what the contribution is, sets up the methodology in the title).

---

## Notes for refinement after pilot

- If pilot shows tier-1 saturation, we should drop tier-1 from the headline and lead with "on tier 2-3 challenges" in the abstract.
- If structured beats raw_code by a wide margin, lead with the strategy as a contribution. If the gap is small, deemphasize.
- If recipe is materially better than structured on a budget, that's a quotable third number ("GeoGen-recipe lifts Haiku to within X% of Opus at 1/15th the cost").
- "Strict" vs "Strict+soft" pass-rate matters for the headline number — pick one and define it in the abstract.
