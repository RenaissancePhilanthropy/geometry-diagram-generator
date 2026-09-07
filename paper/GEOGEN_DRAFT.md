# GeoGenBench four-pager, for editing

Edit the prose directly. `## ` is a section heading; a bold lead is a subheading. Keep [citation keys] and {ref:...} markers where they are. Macros like \GeoGenBench, \structured, \rawcode, \opus, \tone stay as they are; I map them back. Math stays as $...$. The figure and table are not shown; the `{{FLOAT:...}}` lines mark where they sit and must stay. Tell me to apply when done.

---

## Abstract

Existing geometry benchmarks ask a model to read a diagram. None asks whether it can draw one. We introduce \GeoGenBench: 801 prompts that each ask for a plane-geometry construction, paired with a list of properties a correct drawing must have. The prompt and the property list come from the same Python template, so they cannot drift apart. The model writes TikZ. We compile it, recover the coordinates, and check every property symbolically. No human grades and no vision model judges. We test six frontier models under two strategies. Asking for a typed intermediate representation instead of raw TikZ lifts every model, by 2 to 25 points, most for the weakest. Under that strategy, three flagship models land within one point of each other at a $7\times$ cost spread. One model cannot use the strategy at all, because its API rejects the schema. A pre-registered human check of 200 outputs finds the verifier lenient in one direction only: it never fails a correct drawing, and experts overturn 18% of its passes, almost all on one difficulty tier. We release the dataset, the template engine, the verifier, and the leaderboard.

## Introduction

Frontier language models now write slide decks, worksheets, and technical illustrations. In K--12 education the most common such artifact is the geometry diagram. Every existing geometry benchmark tests the other direction: given a diagram, answer a question. None tests whether a model can produce a correct diagram from a description. \GeoGenBench fills that gap.

Take the prompt *"Draw an acute triangle $EFG$ with angles $60^\circ$ and $70^\circ$ at $E$ and $F$. Construct the altitude from $G$ meeting $EF$ at $H$."* A correct drawing has $\angle E = 60^\circ$, $\angle F = 70^\circ$, $H$ on the segment $EF$ rather than its extension, $\angle GHE = 90^\circ$, and all three angles acute. Each of those is a predicate we can check on the coordinates of the model's drawing. In our pilot, one flagship model put $H$ on the line $EF$ but outside the segment. Another drew an obtuse triangle. The verifier names the failed predicate in each case rather than giving a holistic score.

Two ideas make this work. The prompt and its rubric are generated together from one template, so a rubric can never ask for something the prompt did not. And the drawing is graded in symbolic space, from coordinates, so a "right angle" verdict is a numeric check rather than a judgment about how the picture looks. We call the method \GeoGen and its first instance \GeoGenBench.

**Prior work.** Geometry3K [lu2021intergps], GeoQA [chen2021geoqa], UniGeo [chen2022unigeo], MathVista [lu2024mathvista], GeoEval [zhang2024geoeval], and GeoBench [geobench2026] all test diagram interpretation. On the generation side, T2I-CompBench++ [huang2025t2icompbenchpp] and GenExam [wang2025genexam] grade generated images with CLIP, multimodal, or language-model judges, which can say whether an image looks like a right triangle but not whether it has a right angle. Lean and Isabelle corpora and AlphaGeometry [trinh2024alphageometry] machine-check proofs. \GeoGenBench applies machine checking to diagram generation, a cell that was empty.

## The benchmark

**Co-generation.** One Python template emits both the prompt and the rubric ({ref:fig:cogen}). The altitude template above returns the prose request and the predicate list `[right\_angle($A$,$H$,$B$), point\_on\_segment($H$,$B$,$C$)]` that any correct drawing must satisfy. This removes drift between question and rubric. It also defends against contamination, because a reviewer can re-roll the engine with fresh seeds at the same difficulty.

{{FLOAT:fig:cogen}}

**Symbolic verification.** The model emits TikZ. A containerised LuaLaTeX renderer compiles it to SVG, and an extractor compiles the same source into SymPy geometry with coordinates. A fixed, typed predicate language is then decided against those coordinates in microseconds per predicate. Version 1 has 15 symbolic predicates, such as `right\_angle`, `midpoint`, `collinear`, `parallel`, `tangent`, and `point\_on\_segment`, decided with numeric tolerance $\tau = 5\times10^{-3}$. Two weaker source-string checks, for labels and marks, count only toward a *loose* pass. Authors state what must hold, not how to check it.

**Scoring.** The model sees only the prompt. Each output scores `pass` if every check passes, `soft\_pass` if nothing fails but at least one check was skipped, `fail`, or a generation or render failure.

**Composition.** 801 prompts. 600 come from 30 procedural templates, 200 per difficulty tier: \tone is a single shape, \ttwo adds one auxiliary construction, \tthree composes several steps. The other 201 are extracted by a language model from the topical scaffold of a state-adopted K--12 curriculum [bluebonnet2024], which adds breadth at the cost of model-authored ground truth. We report the two sources separately, and the templated half is the calibration anchor.

## Verifier reliability

**Completeness.** A property list is complete if every drawing that passes it is congruent to the intended construction, up to rigid motion and scale. Auditing all 30 templates gives 18 tight, 11 loose, and 1 skeletal, or 63%, 35%, and 2% of scenarios. Loose templates pin the named relations but leave continuous parameters free, which matches educational practice. For each predicate we tried to write TikZ that passes the predicate while contradicting the prompt. Five predicates have soft spots. All are closable by hardening or by pairing checks in the template, and because templates already pair check types, we estimate fewer than 5% of strict passes are exploitable in the wild.

**Hardening.** Three verifier changes, closed-form intersection solving, a pgfmath-style coordinate evaluator, and a `centroid` predicate, promoted 4.6% of pilot records from `soft\_pass` to `pass` with no demotions. They also cut the apparent gap between the two strategies by about half. Part of the "strategy gap" was the verifier struggling with raw output, not the models. All numbers below are post-hardening.

**Human check.** A pre-registered study rated 200 outputs, stratified over the pilot. Two raters, a PhD mathematician who is an award-winning educator and an engineer with mathematics-teaching experience, rated blind to the verifier's verdict, then met to reach consensus. Agreement between verifier and raters is moderate: $\kappa = 0.455$ (95% interval 0.30 to 0.59), balanced accuracy 0.68, below the pre-registered threshold of 0.70. The raters agree with each other ($\kappa = 0.704$), so the instrument is consistent and the gap is between raters and verifier. The disagreement runs one way. Experts overturned 18% of strict passes to fail and never overturned a fail to pass. Nearly all of it sits on \ttwo ($\kappa = 0.16$, against 0.65 and 0.80 on \tone and \tthree), where property lists check the named auxiliary construction but not the numeric parameters the prompt specifies. 89% of disagreements code as "verifier missed a prompt-numeric constraint." Leaderboard rates are therefore conservative, and differences between cells survive, because the lenience applies to every model on the same templates. Numeric predicates that lift the affected \ttwo templates to tight are the committed version-2 fix.

## Experiments

**Setup.** Six production models from three vendors, spanning a $20\times$ price range: \opus, \sonnet, \haiku, \gpt, \geminipro, and \geminiflash, at temperature 1.0 and April 2026 prices. Two strategies. \rawcode gives the model the prompt and a TikZ tutorial and takes the TikZ it writes. \structured asks the model for typed JSON in a Pydantic intermediate representation, with points, segments, intersections, circles, render operations, and check declarations, which code compiles to SymPy and then TikZ. Declared checks run before rendering, so the strategy corrects itself with up to three retries. The headline run covers all 12 model-by-strategy cells on the 600 templated scenarios, three repeats each. A subprocess-isolated runner with a hard timeout keeps coverage at or above 91% per cell except where noted.

{{FLOAT:tab:headline}}

**Structured output helps unevenly.** \structured lifts every model: \gpt by 2.2 points, \haiku by 4.8, \sonnet by 12.2, \opus by 21.7, and \geminipro by 24.7. The lift is largest for the models weakest at raw TikZ and smallest for the strongest.

**The frontier converges.** Under \structured, \gpt (94.1%, \dollars{0.075} per scenario), \sonnet (93.4%, \dollars{0.088}), and \opus (93.3%, \dollars{0.532}) span 0.8 points at a $7\times$ cost ratio. The most expensive model carries no measurable quality premium once the scaffold is in place, and the cost-quality frontier collapses to one corner. Under \rawcode the spread is wide, from 91.9% down to 35.9%, and \opus is the most dominated cell, beaten by \gpt by 20 points at $4.5\times$ lower cost. By tier, \tone is nearly saturated for every Anthropic and OpenAI \structured cell. \ttwo is where strategy first matters (\opus $+43$ points, \geminipro $+54$). \tthree separates the frontier cells (\gpt 93%, \sonnet 87%, \opus 82%). Most wrong outputs are rendered diagrams with wrong geometry, not broken LaTeX.

**Portability.** \structured relies on schema-constrained generation, which OpenAI and Google compile into a server-side state machine with vendor-specific limits. Our schema, a discriminated union of about 20 variants, compiles to thousands of states. \geminiflash rejects it at the API layer, HTTP 400, "too many states for serving," before generating a token. That is a portability gap, not a capability gap, and a caution for any benchmark that ships a multi-variant schema.

## Conclusion

**Limitations.** \GeoGenBench measures whether a model can turn a text specification of a plane-geometry construction into a consistent drawing. It does not test proofs, 3D solids, or teaching value. 35% of templated scenarios are intentionally loose, so a pass means a drawing consistent with the stated constraints rather than the one canonical drawing. The human study localises the verifier's lenience to \ttwo numeric constraints, and the fix is identified. The curriculum split is harder for every model measured; \haiku under \rawcode drops from 82.1% to 36.0%. The headline findings are templated-split findings.

**Takeaway.** A geometry drawing can be graded exactly, from its coordinates, with no judge. Graded that way, the scaffold matters more than the model: a typed intermediate representation lifts every model, erases the premium of the most expensive one, and fails only where a vendor's API cannot accept the schema. We release the dataset, template engine, verifier, renderer, and leaderboard.
