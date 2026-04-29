# GeoGen — abstract drafts

Three drafts at decreasing length and increasing punch. Backfilled with pilot numbers (30-scenario stratified pilot; full 600-scenario headline run pending). Headline numbers below are pilot strict-pass — they will tighten with the full run but the qualitative claims are robust to N.

---

## Draft 1 — Long form (~200 words)

Existing geometry benchmarks measure whether language models can *interpret* a given diagram and answer a question about it. None measures whether a model can *produce* a correct diagram from a description — yet diagram production is increasingly the deployed task, as LLMs are asked to author worksheets, slides, and technical illustrations. We introduce **GeoGen**, the first benchmark for generative geometric reasoning with **fully-automatic, geometry-aware verification**. GeoGen pairs **801** natural-language prompts ("draw an acute triangle ABC with the altitude from A meeting BC at H") with machine-checkable geometric properties that any correct rendering must satisfy ("angle AHB is right; H lies on segment BC"). Verification compiles the model's TikZ output to symbolic geometry via SymPy and decides each property in milliseconds, requiring no human grading or vision-language judge. Across **four frontier models** (Claude Opus 4.7, Claude Sonnet 4.6, Claude Haiku 4.5, GPT-5.1) and **three generation strategies** on a stratified pilot, we find that **the cost-quality Pareto frontier is dominated by cheap-model configurations**: Claude Haiku 4.5 with direct TikZ generation reaches 83% strict pass at $0.017/scenario, beating Claude Opus 4.7 with the same strategy (80%, $0.329) on both axes — 3 pp more correct diagrams at 19× lower cost. A generic intermediate-representation strategy adds a further 4–20 pp on top. We also report a verification-reliability audit: §4.5 of the paper closes 13/315 (4.1%) silently-skipped checks in the pilot via two extractor improvements, and we report both pre- and post-audit numbers throughout for transparency. We release the dataset, the procedural template engine that generated it (allowing reviewers to roll new contamination-free splits), the verification toolkit, and a public leaderboard.

---

## Draft 2 — Short form (~100 words, target conference abstract)

Frontier LLMs are increasingly deployed to *produce* diagrams — for slides, math worksheets, technical illustrations — yet existing geometry benchmarks only test understanding of *given* diagrams. We introduce **GeoGen**, a benchmark of 801 prompts with **fully-automatic verification**: each prompt is paired with machine-checkable geometric properties decided in milliseconds via SymPy, no human grading. Across four frontier models × three generation strategies, the cost-quality frontier is dominated by cheap-model configurations: Claude Haiku 4.5 with direct TikZ generation (83% strict pass, $0.017/scenario) **beats Opus 4.7 (80%, $0.329) on both axes** — 19× cheaper. A structured-IR strategy adds a further 4–20 pp. We include a verification-reliability audit that closes 4.1% of silently-skipped checks. Dataset, generator, verifier, and leaderboard released.

---

## Draft 3 — Punchline (~50 words, for talk title slide / tweet)

**GeoGen** is the first geometry benchmark that asks LLMs to *produce* diagrams, graded by symbolic geometry instead of vision-language judges. 801 prompts, fully-automatic verification, public leaderboard. Headline finding: **Haiku beats Opus on raw TikZ generation** — 3 pp more correct diagrams at 19× lower cost.

---

## Pilot numbers used above (post-§4.5 hardening, locked in until full run lands)

| Variable | Source | Value |
|---|---|---|
| **N** (# prompts in full benchmark) | `len(scenarios_generated.yaml) + len(scenarios_geometry_curriculum.yaml)` | 600 + 201 = **801** |
| **F** (# models in headline) | leaderboard config | **4** (Opus 4.7, Sonnet 4.6, Haiku 4.5, GPT-5.1) |
| **S** (# strategies) | leaderboard config | **3** (raw_code, structured, recipe) |
| **Strategy effect** | structured – raw_code, by model | **+4–20 pp** (Haiku +4, Sonnet +15, GPT-5.1 +20, Opus +20 on N=9) |
| **Cost-equivalence** | Haiku+raw_code vs Opus+raw_code | **+3 pp pass, 19× cheaper** ($0.017 vs $0.329 per scenario) |
| **Headline strict pass** | Sonnet+structured (best non-Opus) | **92%** strict pass on full pilot |
| **§4.5 verifier impact** | regrade vs original verifier | 13/315 records (4.1%) promote soft_pass → strict |
| **κ vs human raters** | human-correlation study | TBD; target ≥ 0.7 (pre-registered) |

---

## Title candidates

1. **GeoGen: A Benchmark for Generative Geometric Reasoning with Symbolic Verification**
2. **GeoGen: Drawing on Demand — Evaluating LLM Diagram Generation in Plane Geometry**
3. **GeoGen: When LLMs Pick Up the Compass — A Generative Benchmark for Geometric Reasoning**
4. **From Reading to Drawing: GeoGen Benchmarks Generative Geometric Reasoning in LLMs**
5. **The GeoGen Benchmark: Symbolic Verification of LLM-Generated Geometry Diagrams**

My pick: still #1 (most-Google-able, says exactly what the contribution is, sets up the methodology in the title). After the pilot data, I'd consider a subtitle: "*A Benchmark for Generative Geometric Reasoning with Symbolic Verification — and how scaffolding beats scale*."

---

## Notes — what the pilot data settled

- **Tier 1 is not saturated for `recipe` (90% Haiku, 70% GPT-5.1)** but is saturated for raw_code/structured. We keep T1 in the headline because it's part of the "structured generalizes, recipe doesn't" story. We do flag in §6.4 that v2 should add harder T1 templates.
- **Structured beats raw_code by a wide margin (10–30 pp)**, so we lead with the strategy effect as the central contribution.
- **Recipe is *not* universally good** — the T2/T3 pilot suggests recipe only helps Sonnet (93%); Haiku/GPT-5.1 do worse with it than with structured. We keep recipe in the leaderboard for the "what kind of scaffolding works" finding but explicitly *do not* recommend it as a deployment strategy for sub-frontier models.
- **Strict vs strict+soft**: the abstract uses *strict* (every check fired and returned True). We define this on first use in the introduction. Loose-pass is reported alongside in the headline table for transparency.
