# Section 1 — Introduction

Working draft. The introduction has to do four things in 1.5–2 pages: (i) name the gap, (ii) show why it matters with a concrete failure example, (iii) state our contribution sharply, (iv) preview the headline result.

---

## 1.1 The gap (one paragraph)

Frontier large language models are increasingly deployed to *author* technical content — worksheets, slides, scientific figures, and diagrams — not merely to *answer questions about* it. In K-12 mathematics alone, Khan Academy, Khanmigo, GPT-4o-based math tutors, and a wave of education startups now ship diagram generation as a default feature. Yet the public benchmarks for evaluating LLMs on geometry are uniformly *consumption*-side: Geometry3K [Lu et al. 2021], GeoQA [Chen et al. 2021], UniGeo [Chen et al. 2022], MathVista [Lu et al. 2023], and the recent GeoEval [Yan et al. 2024] all measure whether a model can answer questions *given* a diagram. None test whether it can *produce* a correct diagram from a description. **GeoGen closes this gap with the first generation-side, automatically-graded geometry benchmark for LLMs.**

## 1.2 Why this matters: a motivating example

Consider the prompt every middle-school teacher writes by Tuesday morning:

> *"Draw an acute triangle ABC. Drop the altitude from vertex A to side BC, meeting it at the foot H. Mark the right angle at H. Label all four points."*

We asked four frontier models — GPT-5.1, Claude Opus 4.7, Claude Sonnet 4.6, and Claude Haiku 4.5 — to render this prompt as a TikZ diagram. The naive raw-code prompt yielded the diagrams in **Figure 1**. *(figure to be inserted; pulled from `evals/results/leaderboard_pilot/<run>/svgs/`)*. Across the four outputs:

- one model rendered the altitude correctly but **placed H outside segment BC** (geometric error: extended-line foot, not segment foot);
- one model omitted the right-angle mark (fidelity error: prompt requirement violated);
- one model labeled H but rendered no altitude segment at all (rendering error);
- one model produced a visually correct diagram.

A human teacher catches all four cases at a glance. A naive LLM-as-judge ("does this look like an altitude?") catches the gross errors but cannot reliably distinguish the foot-outside-segment case from the correct one without explicit symbolic reasoning. A diagram-question-answering benchmark catches none of these errors at all — they live entirely in the production step, which existing benchmarks skip over.

**This is the GeoGen task.** Each scenario provides a natural-language prompt plus a machine-checkable property list; a model passes only if the rendered diagram satisfies every property under symbolic verification.

## 1.3 Contributions

We make four contributions:

1. **GeoGen-v1, an 801-scenario benchmark** of K-12 geometry diagram-generation tasks across three difficulty tiers. Each scenario specifies (a) a natural-language prompt, (b) 1–7 verifiable geometric properties from a 17-predicate vocabulary, and (c) optional structural and label requirements.
2. **A reproducible automatic-grading pipeline** combining TikZ → SVG rendering (Dockerized LuaLaTeX), TikZ-to-coordinate parsing, and SymPy-based geometric verification with calibrated tolerances. The pipeline grades a scenario in <1 second on commodity hardware.
3. **A leaderboard of [N] frontier models × 3 generation strategies** (raw TikZ, structured intermediate-representation JSON, and recipe-DSL with constraint solving), revealing a [X]-percentage-point spread between the strongest and weakest model and a [Y]× cost spread between equivalent-quality combinations.
4. **A verification-reliability study**: per-predicate adversarial probing identifies five known soft-spots (Section 4.4); a pre-registered N=200 human-correlation study targets Cohen's κ ≥ 0.7 between automatic and majority-human verdicts.

## 1.4 Headline result preview

Across our pilot leaderboard (30 scenarios stratified across 23 templates and three tiers, evaluated on [N] frontier models), we observe:

- **Strict-pass rates range from [X]% to [Y]%** at the top of the leaderboard, with tier-3 (advanced) scenarios producing the largest spread.
- **Cost-equivalence**: the structured-IR strategy with Sonnet 4.6 matches the strict-pass rate of Opus 4.7 at **~1/19th the per-scenario cost** ($0.007 vs $0.13), demonstrating that strategy choice dominates model choice in the cost-quality trade-off.
- **Failure-mode taxonomy**: across all failures, [Z]% are geometric-violation (the model produced TikZ that rendered but did not satisfy the property list), [W]% are rendering errors (LaTeX compilation failed), and [V]% are completeness skips (the prompt required a check our verifier marks as soft).

These numbers will be updated post-pilot; the *qualitative shape* (sharp tier-3 spread + dominant strategy effect + low rendering-error rate) is robust across the partial data we have today.

## 1.5 What we are *not* claiming

To set scope:

- We do not claim our verifier is sound on every conceivable adversarial diagram. Section 4 quantifies the soft-spots and reports per-predicate human agreement.
- We do not claim the templated split exhausts the space of K-12 geometry. The curriculum split (201 textbook-derived scenarios) provides a cross-source robustness check.
- We do not claim 2D plane geometry is the right scope for all uses. Section 7 outlines explicit extension paths to 3D, transformations, and proof-diagrams; v1 sets the foundation.

## 1.6 Outline

Section 2 reviews related work in geometric reasoning, text-to-image generation, and code-generation benchmarks. Section 3 specifies the benchmark — task formulation, scenario sources, the 17-predicate property vocabulary, and the verification pipeline. Section 4 establishes verification reliability via completeness analysis, adversarial probing, and a pre-registered human study. Section 5 describes the three reference strategies. Section 6 presents the leaderboard, headline figures, and failure-mode analysis. Section 7 discusses limitations and the roadmap to v2. Section 8 concludes.

The benchmark, verifier, renderer Docker image, and leaderboard infrastructure are released under MIT license at [URL]. The dataset is permanently archived on HuggingFace Datasets at [URL].
