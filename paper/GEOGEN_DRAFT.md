# GeoGenBench four-pager, for editing

Edit the prose directly. `## ` is a section heading; a bold lead is a subheading. Keep [citation keys] and {ref:...} markers where they are. Macros like \GeoGenBench, \structured, \rawcode, \opus, \tone stay as they are; I map them back. Math stays as $...$. The figure and table are not shown; the `{{FLOAT:...}}` lines mark where they sit and must stay. Tell me to apply when done.

---

## Abstract

Geometry benchmarks ask a model to read a diagram. None asks it to draw one. \GeoGenBench does. It has 801 prompts, each asking for a plane-geometry construction and each paired with the properties a correct drawing must have. The model writes TikZ. We compile it, recover the coordinates, and check every property exactly. No human grades and no vision model judges. We test six frontier models. Asking for a typed intermediate representation instead of raw TikZ lifts every model, by 2 to 25 points, most for the weakest. Under that scaffold the three best models tie within one point at a $7\times$ cost spread. A human check of 200 outputs finds the verifier lenient in one direction only: it never fails a correct drawing. We release the dataset, the templates, the verifier, and the leaderboard.

## Introduction

Language models now write worksheets and slides, and in school the picture they most often need to draw is a geometry diagram. Every geometry benchmark tests the other direction: here is a diagram, answer a question. None tests whether a model can draw a correct diagram from a description.

Take the prompt *"Draw an acute triangle $EFG$ with angles $60^\circ$ and $70^\circ$ at $E$ and $F$. Construct the altitude from $G$ meeting $EF$ at $H$."* A correct drawing has those two angles, $H$ on the segment $EF$ and not beyond it, a right angle at $H$, and no obtuse angle. Each of those is a check we can run on the coordinates of the model's drawing. In our pilot, one flagship model put $H$ beyond the segment. Another drew an obtuse triangle. The verifier names the check that failed.

Two ideas make this work. The prompt and its checks come from the same template, so the checks can never ask for something the prompt did not. And the drawing is graded from its coordinates, so "right angle" is a calculation, not an opinion about how the picture looks.

**Prior work.** Geometry3K [lu2021intergps], GeoQA [chen2021geoqa], UniGeo [chen2022unigeo], MathVista [lu2024mathvista], GeoEval [zhang2024geoeval], and GeoBench [geobench2026] test diagram reading. T2I-CompBench++ [huang2025t2icompbenchpp] and GenExam [wang2025genexam] grade generated images with a model as judge, which can say whether a picture looks like a right triangle but not whether it has a right angle. AlphaGeometry [trinh2024alphageometry] and the Lean corpora machine-check proofs. \GeoGenBench machine-checks drawings.

## The benchmark

**Co-generation.** One Python template writes both the prompt and its checks ({ref:fig:cogen}). The altitude template returns the sentence the model sees and the list `[right\_angle($A$,$H$,$B$), point\_on\_segment($H$,$B$,$C$)]` the grader uses. The two cannot drift apart. A reviewer worried about contamination can re-roll the template with a fresh seed.

{{FLOAT:fig:cogen}}

**Symbolic verification.** The model emits TikZ. We compile it twice: once to an image, once to SymPy geometry with coordinates. Fifteen checks such as `right\_angle`, `midpoint`, `parallel`, and `point\_on\_segment` run on those coordinates in microseconds, with a small numeric tolerance. Two weaker checks on labels and marks count only toward a loose pass. Template authors say what must hold, not how to test it.

**Scoring.** The model sees only the prompt. An output passes if every check passes. It gets a soft pass if nothing fails but a check was skipped. Otherwise it fails, or it never rendered.

**Composition.** 600 of the 801 prompts come from 30 templates, 200 per tier: \tone is a single shape, \ttwo adds one construction, \tthree combines several. The other 201 were extracted by a language model from a state K--12 curriculum [bluebonnet2024]. We report the two sources separately and treat the templated 600 as the anchor.

## Verifier reliability

**Completeness.** A check list is complete if every drawing that passes it is the intended construction, up to position and scale. Of the 30 templates, 18 are that tight. The other 12 pin the named relations but leave free parameters, as a teacher's instructions usually do. We also tried to fool each check with TikZ that passes it while contradicting the prompt. Five checks can be fooled alone. Templates pair checks, so we estimate under 5% of passes are exploitable.

**Hardening.** Three verifier fixes promoted 4.6% of pilot outputs from soft pass to pass and demoted none. They also halved the apparent gap between the two strategies. Part of that gap had been the verifier's, not the models'. Every number below is post-fix.

**Human check.** Two raters, a PhD mathematician and an engineer who has taught mathematics, judged 200 outputs blind to the verifier's verdict. Verifier and raters agree moderately ($\kappa = 0.455$), below the 0.70 we had pre-registered. The raters agree well with each other, so the gap is the verifier's. The disagreement runs one way. The raters overturned 18% of the verifier's passes and none of its fails. Almost all of those sit on \ttwo, where the checks confirm the construction but not the numbers the prompt gave. Leaderboard rates are therefore a little generous, evenly across models. Numeric checks for those templates are the planned fix.

## Experiments

**Setup.** Six models from three vendors at a $20\times$ price spread: \opus, \sonnet, \haiku, \gpt, \geminipro, and \geminiflash. Two strategies. \rawcode hands the model the prompt and a TikZ tutorial and takes what it writes. \structured asks for typed JSON describing points, segments, circles, and checks, which our code turns into SymPy and then TikZ. The checks run before rendering, so the model gets up to three retries. Every model-by-strategy cell runs on the 600 templated prompts three times.

{{FLOAT:tab:headline}}

**The scaffold lifts every model.** \structured helps each model, from 2 points for \gpt to 25 for \geminipro. The weaker a model is at raw TikZ, the more it gains.

**The frontier converges.** With the scaffold, \gpt, \sonnet, and \opus finish within one point of each other, at 94%, 93%, and 93%. \opus costs seven times what \gpt does. Without the scaffold the spread runs from 92% down to 36%. \tone is nearly solved. \ttwo is where the scaffold first matters. \tthree is where the frontier models separate. Most wrong outputs are clean diagrams with the wrong geometry, not broken code.

**Portability.** \structured needs schema-constrained decoding. Our schema compiles to thousands of states, and one vendor's API refuses it before the model writes a token. That is a gap in the API, not the model, and a warning for any benchmark built on a large schema.

## Conclusion

**Limitations.** \GeoGenBench tests whether a model can turn a sentence into a consistent plane drawing. It does not test proofs, solids, or teaching. A third of the templates accept any drawing that meets the stated constraints, not one canonical drawing. The curriculum prompts are harder for every model than the templated ones, and the headline numbers are templated numbers.

**Takeaway.** A geometry drawing can be graded exactly, from its coordinates, with no judge. Graded that way, the scaffold matters more than the model. We release everything needed to run it.
