# Section 1 — Introduction

Working draft. The introduction has to do four things in 1.5–2 pages: (i) name the gap, (ii) show why it matters with a concrete failure example, (iii) state our contribution sharply, (iv) preview the headline result.

---

## 1.1 The gap (one paragraph)

Frontier large language models are increasingly deployed to *author* technical content — worksheets, slides, scientific figures, and diagrams — not merely to *answer questions about* it. In K-12 mathematics alone, Khan Academy, Khanmigo, GPT-4o-based math tutors, and a wave of education startups now ship diagram generation as a default feature. Yet the public benchmarks for evaluating LLMs on geometry are uniformly *consumption*-side: Geometry3K [Lu et al. 2021], GeoQA [Chen et al. 2021], UniGeo [Chen et al. 2022], MathVista [Lu et al. 2023], and the recent GeoEval [Yan et al. 2024] all measure whether a model can answer questions *given* a diagram. None test whether it can *produce* a correct diagram from a description. **GeoGen closes this gap with the first generation-side, automatically-graded geometry benchmark for LLMs.**

## 1.2 Why this matters: a motivating example

Consider the prompt every middle-school teacher writes by Tuesday morning (one of 30 in our pilot, scenario `tpl-t2-alt-EFG-H-60-70`):

> *"Draw an acute triangle EFG where the angle at F is 60° and the angle at G is 70°. Drop the altitude from vertex E to side FG, meeting it at the foot H. Mark the right angle at H and label all four points."*

We asked four frontier models — GPT-5.1, Claude Opus 4.7, Claude Sonnet 4.6, Claude Haiku 4.5 — to render this prompt as a TikZ diagram, with each of three generation strategies. **Figure 1** *(to be inserted; pulled from `evals/results/leaderboard_pilot/<run>/svgs/tpl-t2-alt-EFG-H-60-70__*.svg`)* shows their outputs. Across the twelve attempts on this single prompt:

- some attempts **render the altitude as a line that extends beyond segment FG** (geometric error: the foot H is not on segment FG, only on the line through it);
- some **omit the right-angle mark at H** (fidelity error: a stated prompt requirement is silently dropped);
- some **mislabel which vertex the altitude is dropped from**, producing an altitude from F instead of E (instruction-following error);
- some produce a fully correct diagram.

A human teacher distinguishes all four cases at a glance. A naive LLM-as-judge ("does this look like an altitude?") catches the gross errors but cannot reliably distinguish the foot-outside-segment case from the correct one without explicit symbolic reasoning. A diagram-question-answering benchmark catches none of these errors at all — they live entirely in the production step, which existing benchmarks skip over.

In our pilot, this single prompt distinguishes models. Direct TikZ generation (`raw_code`) fails for half the models on tier-2 prompts like this one — the cross-model strict-pass rate is 4/10 to 6/10 on T2 across raw_code variants. A generic intermediate-representation strategy with check-and-revise (`structured`) brings every model to **at least 9/10 strict pass on T2**. **This is the GeoGen task.** Each scenario provides a natural-language prompt plus a machine-checkable property list; a model passes only if the rendered diagram satisfies every property under symbolic verification.

## 1.3 Contributions

We make four contributions:

1. **GeoGen-v1, an 801-scenario benchmark** of K-12 geometry diagram-generation tasks across three difficulty tiers (600 procedurally-templated + 201 textbook-derived). Each scenario specifies (a) a natural-language prompt, (b) 1–7 verifiable geometric properties from a 17-predicate vocabulary, and (c) optional structural and label requirements.
2. **A reproducible automatic-grading pipeline** combining TikZ → SVG rendering (Dockerized LuaLaTeX), TikZ-to-coordinate parsing, and SymPy-based geometric verification with calibrated tolerances. The pipeline grades a scenario in <1 second on commodity hardware.
3. **A leaderboard of 4 frontier models × 3 generation strategies** (raw TikZ, structured intermediate-representation JSON with check-and-revise, and recipe-DSL with constraint solving), revealing — at the §4.5-hardened verifier — a strict-pass spread of **30.0 percentage points** (60.0% to 91.7%) across non-saturating combos and a **19× cost-with-equal-pass spread** between Haiku + raw_code (83% at $0.017/scen) and Opus + raw_code (80% at $0.329/scen).
4. **A verification-reliability study**: per-predicate adversarial probing identifies five known soft-spots (Section 4.4); a pre-registered N=200 human-correlation study targets Cohen's κ ≥ 0.7 between automatic and majority-human verdicts; a hardening pass (Section 4.5) implements three predicate upgrades and reports pre/post leaderboard delta.

## 1.4 Headline result preview

From our 30-scenario stratified pilot evaluating four frontier models — Claude Opus 4.7, Claude Sonnet 4.6, Claude Haiku 4.5, GPT-5.1 — on three strategies, with verification at the §4.5-hardened tolerance, we find:

- **Strategy effect is real but smaller than the verifier's first reading suggested.** The `structured` strategy lifts every model by **4–20 percentage points** of strict pass rate over direct TikZ (`raw_code`): GPT-5.1 (70% → 90%, +20 pp), Sonnet (77% → 92%, +15 pp), Opus (80% → 100% on N=9, +20 pp), Haiku (83% → 87%, +4 pp). The pre-hardening verifier reported gaps of 10–30 pp; the §4.5 audit attributes about half of that gap to silent skips of `\pgfmathsetmacro`-style coordinates that `raw_code` outputs use more often than IR-compiled outputs. We report both numbers in §6.2 and Appendix B.
- **Cost-equivalence: scaffolding beats scale.** Claude Haiku 4.5 with `raw_code` (83% strict pass, $0.017/scenario) **dominates** Claude Opus 4.7 with `raw_code` (80% strict pass, $0.329/scenario) on both axes — 3 pp more correct diagrams at 19× lower cost. Adding `structured` on Haiku ($0.032/scenario) buys a further 4 pp at 2× the Haiku cost. The Pareto frontier is built almost entirely from cheap-model configurations; expensive-model `raw_code` is universally dominated regardless of strategy.
- **The recipe-DSL strategy is unstable across models.** It works for Sonnet (93%, +16 pp over Sonnet's hardened `raw_code`) but actively hurts GPT-5.1 (60%, –10 pp) and Haiku (70%, –13 pp). Small custom DSLs with built-in geometric priors are *not* a transferable scaffolding pattern; we recommend the structured-IR strategy in deployment.
- **Failure modes are interpretable.** Of the failures we observe post-hardening, the dominant bucket for `raw_code` is **silent geometric error** (the model produced TikZ that renders but violates a property like "right angle at H" or "F lies on the circle"); for `structured` it is **completeness gaps in our verifier on remaining unresolved constructions** (e.g. `\foreach`-driven point lists); rendering errors are <1% across the board.

The pilot is small (30 scenarios × 1 repeat) and the full 600-scenario × 3-repeat headline run will tighten the numbers above. The *qualitative findings* (strategy still helps but less than first reported, cost-equivalence flips toward cheap-model dominance, recipe-instability, low rendering-error rate) are robust across the partial Sonnet/Opus runs we collected during the pilot's rate-limit recovery.

## 1.5 What we are *not* claiming

To set scope:

- We do not claim our verifier is sound on every conceivable adversarial diagram. Section 4 quantifies the soft-spots and reports per-predicate human agreement.
- We do not claim the templated split exhausts the space of K-12 geometry. The curriculum split (201 textbook-derived scenarios) provides a cross-source robustness check.
- We do not claim 2D plane geometry is the right scope for all uses. Section 7 outlines explicit extension paths to 3D, transformations, and proof-diagrams; v1 sets the foundation.

## 1.6 Outline

Section 2 reviews related work in geometric reasoning, text-to-image generation, and code-generation benchmarks. Section 3 specifies the benchmark — task formulation, scenario sources, the 17-predicate property vocabulary, and the verification pipeline. Section 4 establishes verification reliability via completeness analysis, adversarial probing, and a pre-registered human study. Section 5 describes the three reference strategies. Section 6 presents the leaderboard, headline figures, and failure-mode analysis. Section 7 discusses limitations and the roadmap to v2. Section 8 concludes.

The benchmark, verifier, renderer Docker image, and leaderboard infrastructure are released under MIT license at [URL]. The dataset is permanently archived on HuggingFace Datasets at [URL].
