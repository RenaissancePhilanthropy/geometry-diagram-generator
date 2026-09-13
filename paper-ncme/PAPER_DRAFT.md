# Machine-Verifiable Item Models for Geometry Diagram Generation

*Mei Chen, Gordon Stein. Renaissance Philanthropy.*

<!--
EDITING COPY. Edit the prose here in your own words; Claude diffs this file against the LaTeX,
applies the changes, rebuilds the PDF, and commits. Markers:
  [citekey]        a citation, e.g. [bejar2002generative]; leave as is
  {ref:label}      a cross-reference, e.g. {ref:sec:scoring}; leave as is
  ## Heading       a section; the {label:...} tag after it is the LaTeX label
  **Bold lead**    a paragraph heading (\paragraph in LaTeX)
  > [FIGURE ...]   a figure; only its caption is editable here
  > [TABLE ...]    a table; captions and cell text are editable
  $...$            math, unchanged
Delete this file before submission.
-->

## Abstract

Language models can draw geometry diagrams that look right but are actually
wrong. We found a more reliable way to generate diagrams is to have the model
first describe the construction, then have a
geometry engine compute every point and check the result against the stated
geometric requirements, and only then render the diagram. Because the same
checks also grade the diagram, grading is automatic: no one writes or applies
an answer key by hand. We tested this on 600 benchmark prompts across six
models and found that structured generation raised pass rates for every model
that could run it. We also had two human graders check the grader. They showed
it is lenient in one direction: it passed 36 of 200 diagrams they failed and
failed none the human graders passed.


## Introduction  {label:sec:motivation}

*Automatic item generation* (AIG) can reduce the workload of producing new test items and their answer keys. In template-based AIG, an author writes a single template, or *item model*, from which a computer generates many items, each carrying its own answer key [bejar2002generative,gierl2013aig]. AIG has worked best for items built from text. It has struggled with items whose response is a *picture*. In K-12 mathematics, the picture that often matters most is the geometry diagram.

Producing a correct diagram is harder than it looks. Take a simple request:

> *"Draw an acute triangle $ABC$ with $\angle A = 60^\circ$ and $\angle B = 70^\circ$, then draw the altitude from $C$, meeting $AB$ at $H$."*

To be correct, the drawing has to get several things *exactly* right. Angle $A$ is $60^\circ$. The point $H$ lies on the segment $AB$, not past its end. The altitude meets $AB$ at a true right angle. A model that draws directly has no step where the drawing is checked against these requirements. Whether they hold is a matter of probability. When they fail, they fail silently.

The same exactness makes such diagrams hard to score. Most geometry benchmarks run the task backwards. They show the model a finished diagram and ask a question about it [lu2021intergps,lu2024mathvista]. They do not ask whether a model can *produce* a correct figure. The benchmarks that do score generated pictures were built for everyday images. They rely on an AI "judge" that looks at the output [huang2025t2icompbenchpp,wang2025genexam]. A judge can say a shape *looks like* a right triangle. It cannot certify that an angle is exactly $90^\circ$. For geometry diagrams, then, neither making the item nor scoring it comes for free.

Our idea is to stop guessing and stop looking. We have the model describe the construction in words: "$H$ is the foot of the perpendicular from $C$ to $AB$." A geometry engine then computes the exact coordinates. The model chooses *what* to build. The engine works out *where* every point goes. That one move answers both problems.


- **Better drawings.** A solver does the hard arithmetic, so a right angle comes out exactly right instead of merely close.
- **Automatic scoring.** The finished figure is exact numbers, so we can check each requirement directly. "Is this angle $90^\circ$?" replaces asking a judge what the picture looks like.


That is this paper's contribution: a *machine-verifiable item-model framework* for geometry diagrams. One item model emits both the prompt and a *computed* answer key. The key is a machine-checkable list of geometric requirements. The figure produced in response is verified against that key. We make two empirical claims and are deliberate about their strength. Structured construction improves how often models get the geometry right ({ref:sec:benchmark}). Human validation shows the automatic score runs optimistic, so it is not yet a validated high-stakes score ({ref:sec:scoring}). A fuller leaderboard and cost analysis appear in a companion paper. Here the benchmark is evidence for these two claims, not the contribution itself.

The rest of the paper walks through how the model describes a diagram ({ref:sec:pipeline}), how scoring follows from that same description ({ref:sec:scoring}), what we found on six large models ({ref:sec:benchmark}), and why this matters for educational measurement ({ref:sec:measurement}).


## How the model draws a diagram  {label:sec:pipeline}

A request becomes a picture in three steps ({ref:fig:trace}). The model writes a short, structured description of the construction. A geometry engine turns that description into exact coordinates. A renderer turns the coordinates into a drawing. The division of labour is the important idea: **the model decides what to build, and the engine decides where the points go.** The model never writes a coordinate.


> **[FIGURE fig:trace]** (drawing unchanged) Caption: One request, start to finish. The model writes a description of the construction. The geometry engine solves it for exact coordinates. The system emits drawing code and renders it. The model writes relationships ("$H$ is the foot of the perpendicular from $C$") rather than numbers, so the geometry is computed rather than guessed. Those same coordinates are what we score against in {ref:sec:scoring}.


**Step 1: a description, not coordinates.** The model fills in a simple, typed form. We call it the intermediate representation, or IR. The form offers 31 kinds of building block: points, segments, lines, circles, ellipses, polygons, and intersections. Each block names a *relationship* rather than a position. A point can be "the midpoint of $A$ and $B$," "where these two lines cross," or "the foot of the perpendicular from $C$." In our example the model writes "$H$ is where line $AB$ meets the perpendicular to $AB$ through $C$." It never writes "$H = (3.07, 0)$." Because the form is typed, obvious mistakes are caught right away, before any geometry is computed. A missing point or the wrong number of arguments never reaches the engine.

**Step 2: the engine solves for the points.** A geometry engine reads the description and works out the coordinates, handling the building blocks in dependency order. We use SymPy, a symbolic-mathematics library. Symbolic methods have made headlines for solving olympiad geometry [trinh2024alphageometry]. Here the engine does a humbler job. It works out where the points of a described figure go. When a step is ambiguous, say two circles cross at two points, the description says which one to keep ("the higher one"). The engine, not the model, produces every coordinate. That is what makes the right angle in our example exactly $90^\circ$ rather than approximately so.

**Step 3: render.** From the exact coordinates the system writes standard drawing code and compiles it to an image. Fiddly details are handled automatically, such as clipping a line at the edge of the canvas.

**Two ways to drive it.** The model can fill in the form directly. It can also use a short "recipe" language that names a construction, such as `perp_bisector(A,B)`, which then expands into the same form. Every result in this paper comes from the direct form. The recipe language was not yet mature when the benchmark was run, and we have not compared the two at scale. Either way, the description can carry its own requirements, tested *before* the figure is drawn, so the model can catch a mistake and retry. We compare the direct form against a plain baseline in which the model writes drawing code by hand, with no engine and no checks. That baseline is how we measure what the structured approach is worth ({ref:sec:benchmark}). Having a model write drawing code directly is itself an active line of work [belouadi2024automatikz,belouadi2024detikzify]. That work asks how closely the output resembles a target picture. We ask whether its geometry checks out.


## Automatic scoring from shared construction logic  {label:sec:scoring}

The finished diagram is just exact coordinates, so many of a prompt's requirements can be scored directly, as explicit geometric predicates. "Is the angle at $H$ a right angle?" is settled by a one-line calculation on the coordinates, in a fraction of a millisecond. No judge is asked whether the picture looks square. This makes scoring inspectable and inexpensive. It does not make scoring complete. The checklist's validity still depends on whether it captures everything the prompt asks for and the visual conventions a reader expects. We examine both limits below.

**The question and its answer key are written together.** Here is the move that makes this practical. Each item and its answer key come from the *same* short program ({ref:fig:cogen}). One template produces both the wording shown to the model and the checklist used to score it. Because the two are emitted together, they are far less likely to drift apart through manual editing. Template-level errors remain possible. An author can still omit a predicate, encode the wrong one, or write wording whose intended constraint the checklist does not fully capture. Re-running the template with a new random seed mints a fresh, parallel item. The checklist is never shown to the model while it works.


> **[FIGURE fig:cogen]** (drawing unchanged) Caption: One template writes both the question and its answer key. The two cannot drift apart through separate editing. A template can still leave a check out. This key confirms the altitude but not the two stated angles. That is the gap the validity study below finds.


**A small, readable checklist.** Every requirement is written in a small, fixed vocabulary of checks ({ref:tab:predicates}): right angle, midpoint, parallel lines, point on segment, and so on. There are 15 such checks in the current version. Each is decided on the coordinates, within a small rounding tolerance. A diagram passes only if every check on its list passes. The list is, in plain terms, the definition of what the item is testing. It plays the role a specification plays in formal methods: a statement of what must hold, written so that a machine can check it. The check here is numeric and applied to one figure at a time, not a proof over all figures. That is why we say *verifiable* rather than *verified*.


> **[TABLE tab:predicates]** Caption: A sample of the 15 checks in the scoring vocabulary. Each is decided on the computed coordinates. An item's list of checks is, in plain terms, what a passing answer must satisfy.

| **Check** | **What it confirms** |
|---|---|
| `right_angle` | an angle is a right angle |
| `midpoint` | a point is halfway along a segment |
| `collinear` / `parallel` | points lie on a line / lines never meet |
| `point_on_segment` | a point lies between two endpoints |
| `equal_lengths` | two segments have equal length |
| `angle_equal` | an angle equals a stated value |


**Does the automatic score match a human's?** An automatic score is only worth having if it agrees with a careful human grader, so we checked. We fixed a few blind spots found on pilot data. We then ran a pre-registered study. We set the bar in advance: the automatic score had to match the human verdict at Cohen's $\kappa \ge 0.70$, on a scale where $1.0$ is perfect agreement and $0$ is chance. Two graduate-level graders then scored 200 diagrams by hand, without seeing the automatic verdict.

We did not clear that bar. Agreement was moderate, Cohen's $\kappa = 0.46$, well short of the pre-registered $0.70$. We treat this as a central limitation, not a footnote. The disagreements run *one way*. In 36 of the 200 cases the automatic scorer passed a diagram the graders failed. In *zero* cases was it too harsh. In this sample that one-sidedness meant no model was penalised unjustly. But it is the dangerous direction once a score is read as a certificate of correctness, because every disagreement is a false positive. We therefore state it plainly: **the pass rates in {ref:sec:benchmark** are optimistic}. In our sample the checker erred only toward passing, never toward failing. The errors concentrate in one place. They come from items with an added construction, like our altitude, where the checklist confirms the construction but does not separately re-check the prompt's stated angles. The two graders agreed with *each other* at the $0.70$ we had asked the scorer to reach. So the gap is in the checklist, not the human ratings. The fix is to add the missing numeric checks to those templates. That revision was not applied to the results reported here. Instead, {ref:sec:benchmark} reports, alongside each automatic pass rate, the share of automatic passes the graders confirmed, and uses it to correct the rates.

**What the checks cannot see.** That particular gap closes with more checks. A deeper one does not. The checks read the geometry, the coordinates, and nothing else. They never look at how the figure is drawn. A diagram can satisfy every requirement and still mislead a reader. A right-angle mark can sit on the outside of the corner. An angle can be labelled on the wrong side. A figure can pass every check and still be laid out so awkwardly that no reader could follow it. This is the mirror image of the AI judge from {ref:sec:motivation}. A judge sees how a picture looks but cannot check its geometry. Our checks test the geometry but cannot see how it looks. The two are complementary. The checks say whether the computed geometry is correct. Whether the drawing shows that geometry faithfully and clearly is still best judged by eye.


## Putting it to the test  {label:sec:benchmark}

To show the approach works beyond a single example, we evaluate on GeoGenBench. It holds 801 prompts, all scored by the checker of {ref:sec:scoring}. Six hundred come from the templates described above. Another 201 were written from the topic scaffold of a K-12 mathematics curriculum [bluebonnet2024]. The results below cover the 600 templated prompts. The curriculum set is reported in the companion paper. The prompt set, templates, checker vocabulary, and rendered outputs are public, and so is the code. [footnote: Data: https://huggingface.co/datasets/meix/geogenbench. Code: https://github.com/RenaissancePhilanthropy/geometry-diagram-generator.] We ran six large models from three companies, each in two modes. The *by-hand* mode has the model write drawing code directly. The *structured* mode has it fill in the description of {ref:sec:pipeline}. Throughout, a *pass* means passing the automatic checker. The checker is lenient in one direction ({ref:sec:scoring}), so the rates below run high.

**How we ran it.** The by-hand mode asks the model for TikZ drawing code. The structured mode asks for the typed form of {ref:sec:pipeline}. Both run at temperature $1.0$, the sampling setting that controls randomness, with no explicit limit on output length. Both get the same budget of up to three attempts. What differs is the retry trigger. The by-hand mode retries only when its code fails to render. The structured mode also retries when its description fails to compile or the figure breaks a check it declared. Those declared checks are the model's own. The held-out scoring predicates the item template generates, the ones we grade against, are never fed back to it. The structured advantage is therefore not more attempts but more feedback. It lets a model catch its own geometric mistakes, which hand-written code cannot, and those extra retries show up in its per-item cost. Each requirement is decided on the computed coordinates within an absolute tolerance of $\tau = 5\times10^{-3}$, with coordinates normalised to $[-10, 10]$. The $600$ templated prompts divide evenly across three difficulty tiers of $200$ each. They come from $30$ construction templates covering triangles, quadrilaterals, circles, segments, and lines, with $3.2$ requirements apiece on average. The $201$ curriculum prompts were drafted with a language model, with answer keys written by hand. They carry more requirements, $6.0$ on average. Cost per item is the prompt's token count, summed across any retries and priced at each vendor's published rates, then averaged over every prompt, failures included. Failures are dominated by wrong geometry, a requirement that simply does not hold, rather than broken drawing code. The structured mode's remaining failures skew toward timeouts.


> **[TABLE tab:results]** Caption: Share of the $600$ templated prompts *passing the current automatic checker*, in the by-hand mode and the structured mode, with the average cost of one structured generation in US dollars. The checker is lenient in one direction ({ref:sec:scoring}), so these rates run high. The last row gives the share of automatic passes that human graders confirmed, pooled over models. Every model that could run the structured mode improves. The three strongest converge near $93$--$94%$ despite a sevenfold cost spread. Gemini 2.5 Flash could not run the structured mode (see text).

| **Model** | **By hand** | **Structured** | **\$/item** |
|---|---|---|---|
| GPT-5.5 | 91.9% | **94.1%** | 0.075 |
| Claude Sonnet 4.6 | 81.2% | 93.4% | 0.088 |
| Claude Opus 4.7 | 71.6% | 93.3% | 0.53 |
| Claude Haiku 4.5 | 70.5% | 75.3% | 0.032 |
| Gemini 2.5 Pro | 58.4% | 83.1% | 0.050 |
| Gemini 2.5 Flash | 35.9% | blocked | --- |
| *Confirmed by graders* | 75% | 87% | --- |


The structured mode helped every model that could run it ({ref:tab:results}). Pass rates rose by 2 to 25 percentage points. The two largest gains went to models that drew poorly by hand. Handing a model the geometry engine tends to matter most when the model is poor at drawing on its own. More striking still, in the structured mode the three strongest models landed within a single point of one another, even though they differ sevenfold in price. On this task, the method does more of the work than the model does.

The human study of {ref:sec:scoring} gives a rough correction. In that study the checker erred in one direction only. The graders rated diagrams from a pilot run of the same benchmark. They confirmed 75% of the automatic passes drawn by hand (86 of 114) and 87% of those from the structured mode (55 of 63). If those proportions carry over to the full run, the structured rates in {ref:tab:results} fall to about seven-eighths of those shown and the by-hand rates to about three-quarters. Under that assumption the structured advantage survives and widens. The description cuts not only the failures the checker catches but also the silent errors it misses. The per-model cells in that study hold 7 to 23 diagrams, too few to correct each row separately.

We also hit one practical snag worth flagging for anyone building something similar. Gemini 2.5 Flash could not run the structured mode at all. The likely cause is not model ability but the vendor's decoding machinery. When a schema is supplied, the API compiles it into a finite-state constraint on the output. Our form, with its 31 kinds of building block, compiles to more states than Flash's serving tier allows. The request was rejected before any token was generated, with the message that the schema "produces a constraint that has too many states for serving." Gemini 2.5 Pro and the OpenAI models accepted the same schema. Additional per-template results, cost breakdowns, and failure analyses appear in the companion paper. Here they make a single point. Structured construction helps at scale, across every model we tried.


## Why this matters for measurement  {label:sec:measurement}

Seen through the lens of educational measurement, this is a way to write test items and score them automatically, at the same time.


> **[FIGURE fig:variants]** (drawing unchanged) Caption: From one item model to a family of verified items. This is automatic item generation with the answer key built in. Hold every parameter fixed but the angle at $A$ and sweep it through $30^\circ, 40^\circ, 50^\circ$. That produces parallel variants. For each, the checker of {ref:sec:scoring} confirms that the altitude from $C$ meets $AB$ at a right angle (✓), with no human review. One model yields a refreshable supply of items, each carrying its own key.


Each template is an item generator. Fix every parameter but one and sweep that parameter, say an angle through $30^\circ, 40^\circ, 50^\circ$. That mints a family of structurally parallel questions, and the checker confirms each variant without anyone looking ({ref:fig:variants}). The answer key is produced *with* each item rather than written afterward. So a common source of scoring error, a hand-written key that has drifted from its question, is largely designed out. In the vocabulary of the field the template is an *item model* [gierl2012itemmodels], now one that emits its own key. That move also shifts where quality control happens, in the way the item-generation literature recommends. Rather than vetting every generated item, one reviews the construction logic that produces them all [gierl2016review].

The diagram a student (or a model) produces is a constructed response. The same description that built the item can score it. Here a measurement audience should weigh two claims separately. The *generation* claim is the firmer one. The key is computed with the item rather than written separately, so question and key are far less likely to drift apart. And the key is a short, readable list of exactly what must be true ({ref:tab:predicates}), open to inspection rather than buried inside a holistic rubric. The *scoring* claim has to be earned empirically, and our validity study ({ref:sec:scoring}) is candid that it is not yet earned. The auto-score agrees with human graders only moderately and errs in a single direction. For now it is an optimistic estimate. That is fit for benchmarking and for flagging likely-wrong work. It is not yet fit for standalone high-stakes scoring. Closing that gap means adding the numeric checks that {ref:sec:scoring} pinpoints.

**Three measurement questions the checklist opens.** First, isomorphism. Variants minted from one item model are parallel in construction. Parallel construction does not guarantee equal difficulty. A $30^\circ$ angle may be harder to draw than a $50^\circ$ one. Whether the variants are true isomorphs is a calibration question. The framework makes that study cheap, because every variant arrives already keyed. Second, partial credit. The checker decides every requirement separately, so a score need not be all-or-nothing. A diagram that places the altitude correctly but misses the stated angle can earn credit for what it got right. The per-requirement verdicts are the raw material for a partial-credit rubric. The weights and score categories remain to be decided. Our graders also rated diagrams requirement by requirement. They agreed with the checker on 98% of 864 individual ratings. The overall disagreement in {ref:sec:scoring} comes largely from requirements the checklist left out, not from the ones it contains. Third, the checklist as a Q-matrix. Each item's list of checks names the geometric requirements the item imposes, in a fixed vocabulary shared across items. That is the raw form of a Q-matrix, the item-by-attribute table a cognitive diagnostic model needs. Mapping requirements to the skills a student uses still takes judgment and empirical validation. But the first draft of the table comes out of the item model instead of being coded by hand afterward.

**Scope.** The version described here covers plane geometry. The same machinery should extend to coordinate graphs and 3D solids by adding new kinds of building block. We have not built those yet. Where a topic has no natural template, an author can still write items and keys by hand and score them with the same checker. The core idea stays simple. When a diagram is built from a structured description, that description says what must be checked, and a machine can check it. Whether the description is complete is a question for validation, and {ref:sec:scoring} shows why.
