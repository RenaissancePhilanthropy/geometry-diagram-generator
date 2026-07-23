# The experiments, explained — a script for conceptualizing the deck

*Written 2026-07-22 as a thinking aid: one pass through everything we actually ran, what each
experiment showed, and what it deeply means — with a proper treatment of the question "what does
label-free really mean?" Companion docs: [METHODS_MATH.md](METHODS_MATH.md) (formal),
[PROGRESS_REPORT.md](PROGRESS_REPORT.md) (earlier plain-language briefing),
[LAB_NOTEBOOK.md](LAB_NOTEBOOK.md) (dated results). Numbers here are the audited ones that
survived the Codex review pass — the same set the deck uses.*

---

## 0. First, your question: what does "label-free" deeply mean?

Start with what a **label** is in this study: the external grader's verdict on an attempt —
right or wrong, produced by the geometry compiler, letter-match, or `math_verify`. It is the
piece of information the *model never sees* and the experimenter *does*.

Now the four levels at which "label-free" matters, from shallow to deep:

**Level 1 — operational.** The J-lens is built without a single correctness label touching any
part of it:
- The **translation map** (the averaged Jacobian, J_ℓ) is fitted on ~500 prompts of generic
  Wikipedia text. It answers "if this layer-20 thought shifted slightly, which words get more
  likely later?" — a question about the network's wiring, not about our dataset.
- The **word lists** ("wrong, incorrect, error, mistake…" vs "correct, right, true, valid…")
  come from English, not from our data. No tuning against outcomes.
- **Scoring** a stored thought is one dot product per word against a precursor direction
  (r = J_ℓᵀ u_w). Nothing is fitted to our records at read time.

Contrast the probe: it is *defined* by the labels — logistic regression on thousands of
(thought-vector, grade) pairs. The probe finds whatever direction separates the two piles;
the lens derives its direction from the model's own output geometry and only then looks at
our data.

**Level 2 — epistemic (why we built it).** The probe's weakness is that "it separates the
piles" has a boring alternative explanation: it fit an artifact of *our dataset* — some quirk
correlated with failure that isn't "the model's sense of being wrong." Our hygiene (grouped
splits, out-of-fold scoring, fixed layer, layer-0 check) rules out the crude versions, but no
amount of hygiene fully kills the objection, because the labels were in the loop. The lens is a
**second witness with no shared evidence**: different information source (wiring vs labels),
different failure modes. When both point at the same direction — lens 0.76–0.82 on Mistral,
0.88 on Qwen2.5, probe territory — the artifact explanation has to explain *two* independent
instruments agreeing. It can't. That is the entire logic of Result 4a.

**Level 3 — mechanistic (the bonus we didn't have to get).** *How* the lens reads matters as
much as what it reads. It reads through the model's **output pathway** — the machinery that
turns thoughts into words. So lens-readable ≠ merely "present"; it means the signal sits in the
**speakable (verbalizable) subspace**. This is the global-workspace framing: the model *could*
route this content to its mouth. It just doesn't. That upgrade is what licenses the deck's
closing sentence — the knowing–saying gap is largely an **access problem, not a missing
capability**. A probe alone could never support that sentence; a probe only shows presence.

**Level 4 — practical (why the architecture split is a big deal).** A label-free reader is a
reader you can deploy **where no grader exists** — which is almost everywhere that matters.
If you need labels to build the reader, you can only monitor models on tasks you can already
grade. The lens promises monitoring without ground truth… and then Result 4b shows the promise
is **architecture-gated**: it holds on dense transformers and breaks on MoE and Mamba (the
averaged map smears when the wiring re-routes per input). Hence the field rule: dense → trust a
label-free readout; MoE/Mamba → bring a trained probe. That's an actionable engineering fact,
not just a curiosity.

**The honest boundary.** Label-free is not assumption-free. The lens assumes (a) linear
readability and (b) that one *averaged* map is a fair stand-in for the true, input-dependent
transport. Both failures are conservative — the lens can **miss** real signal (as it does on
MoE/Mamba), but it has no mechanism to **hallucinate** one. And one scope note on steering: the
main amplify experiment uses *no labels at intervention time* (it magnifies the model's own
projection), but the direction v was estimated with labels; the fully label-free variant
(steer along the lens's "wrong" precursor) is the strongest version of the causal demo and is
part of the pitch, not yet the headline number.

---

## 1. The cast: one object, four operations

Everything below operates on a single object — the residual-stream vector **h** at one token
(usually the confidence **decision token**: the position that generates the digit of
`Confidence: N`, whose surrounding words are identical in every record).

| operation | what it is | direction comes from | question it answers |
|---|---|---|---|
| **probe** (read) | logistic regression on stored h's | supervised labels | is the signal *present*? |
| **diff-of-means** | v = mean(h_ok) − mean(h_fail) | class means | crude version of the same axis |
| **J-lens** (read) | project h on J_ℓᵀu_word | model's own wiring, **no labels** | is it *speakable*? |
| **steering** (write) | h → h + α·v, or amplify gain g | reuse v (or the lens direction) | does the model *use* it? |

The through-line: a concept is a direction; reading is a dot product, writing is vector
addition. Every experiment is one of those two moves plus controls.

---

## 2. The experiments, one by one

Ordered as run conceptually, not chronologically. Each: what we did → what we found → what it
deeply means.

### E0. The protocol + the read site (the foundation everything sits on)

**Did:** 3-turn protocol per question — pre-task confidence (one locked line, "do NOT answer
yet"), the attempt (reasoning allowed only here; thinking ON for hybrid reasoners, OFF for
confidence turns), post-task confidence (one locked line). External grader scores everything
and **never tells the model**. 150 questions × 5 attempts per cell; 4 matrix models
(Mistral-24B dense · Qwen3.6-27B Mamba-hybrid · GLM-4.7-Flash MoE · Gemma-4-26B MoE) × 4
domains (geometry, MMLU-Pro, MATH, GPQA-Diamond) = 16 cells × 750 records. Capture h at every
layer at the decision token.

**Found:** at layer 0 the decision token decodes correctness at exactly chance; decodability
climbs through the stack to ~0.8 mid-late. (And the check has teeth: an earlier read site — the
answer tokens themselves — decoded 0.74 *at layer 0*, pure surface cues, and was scrapped.)

**Means:** whatever we read deeper was **computed by the model during this attempt**, not
leaked by wording. This is the license for every claim after it. Also the quiet design win:
the 5 repeats per question are what make the difficulty control (E3) possible at all.

### E1. Internal vs stated (Result 1 — "it knows")

**Did:** for each of the 16 cells, AUROC of the trained probe vs AUROC of the model's stated
confidence, both scored out-of-fold at fixed depth 0.7L.

**Found:** probe 0.57–0.95, stated 0.54–0.87; probe wins **12/16** (one tie, three losses —
all small-n, two of them Gemma-4). Mean gap +0.09; **MATH +0.20**; geometry +0.02.

**Means:** models carry an internal correctness signal that is systematically sharper than
anything they say. Not a clean sweep — the claim is the 12/16 sweep plus the decisive math gap.

### E2. The gap by domain + blind self-correction (Result 2)

**Did:** same data, cut as (probe − stated) per domain; separately, compared stated confidence
before vs after failed attempts (grader silent).

**Found:** math towers (+0.20) — internal read up to 0.95 while stated sits near 0.6. And a
trace leaks into words: after failures, models revise stated confidence *downward with zero
feedback* (geometry, MMLU-Pro).

**Means:** the purest knowing-but-not-saying is where wrong work *looks* right on the page
(a wrong \boxed{42} has no surface tell). Blind self-correction shows the verbal channel isn't
deaf — just far weaker than reading the stream.

### E3. Within-question control (Result 3 — "this attempt, not hard topic")

**Did:** keep only mixed-outcome questions (same model, same question, some of the 5 attempts
pass and some fail). Compute AUROC *within* each question, then average — difficulty is constant
by construction. Race the probe against **P(True)** (the model's own explicit bet: probability
mass on "True" when asked if its answer is correct).

**Found:** the probe holds well above chance cell after cell; P(True) collapses to ~chance.
Best cell GLM×MATH: probe **0.89** vs P(True) **0.48**.

**Means:** the study's central dissociation. Output-based confidence tracks *which questions
are hard*; the internal signal tracks *whether this attempt worked*. That's genuine per-attempt
self-monitoring — the thing "metacognition" actually means.

### E4. Prospective vs retrospective (the pre/post beat)

**Did:** compare probes on the turn-1 (pre) vs turn-3 (post) read sites; transfer probes across
sites; residualize post on pre.

**Found:** retrospective beats prospective everywhere (geometry POST 0.66–0.70 vs PRE
0.52–0.62). PRE peaks early/mid and mostly encodes prompt difficulty; POST is chance at layer 0
and peaks mid-late. Post→pre transfer only 0.39–0.67; post residualized on pre keeps 0.59–0.87.

**Means:** "how hard is this question" and "did this attempt work" are **different directions**,
computed at different depths. Seeing its own work genuinely informs the model. This
independently corroborates E3 with a completely different analysis.

### E5. The lens agrees on dense models (Result 4a — the label-free witness)

**Did:** fit the averaged Jacobian per layer on generic text (one GPU-day of backward passes;
readouts collapse to a ~15 MB file); score the *same stored snapshots* the probe used, as a
"wrong-family minus correct-family" disposition; enter it in the same AUROC race.

**Found:** on Mistral the lens lands at 0.76–0.82 — probe territory, beating stated
confidence — with zero labels anywhere in its construction.

**Means:** see §0. Kills memorization; upgrades "present" to "speakable." Two independent
instruments, one direction.

### E6. The architecture split + within-family control + mechanism (Results 4b/4c)

**Did:** ran the same lens on all five models (the fifth, Qwen2.5-14B dense, exists solely as
the within-family control against Qwen3.6's Mamba hybrid). Measured the lens's readout geometry:
cosine between the "correct" and "wrong" readout vectors after transport through the averaged
map.

**Found:** dense works (Qwen2.5 **0.88**, Mistral 0.82); Mamba hybrid fails (0.43); MoE fails
(GLM 0.31); Gemma's variant won't even fit stably. Same Qwen family, swap Mamba → dense:
**0.43 → 0.88**. Readout geometry: cos(correct, wrong) ≈ 0.4 on dense, 0.54 Mamba, **0.96**
MoE — through the smeared map the two words become the same vector.

**Means:** the *label-free shortcut* is architecture-gated; the *signal* is not (the trained
probe reads it in every matrix model, 0.57–0.95). Why: one averaged map is only faithful if the
wiring barely varies per input; MoE/Mamba re-route per input, so the average smears and the
reader goes blind — it isn't missing the signal, it lost the ability to tell its two readout
words apart. Status: leading explanation with a clear fingerprint (the cosine collapse), not
yet a direct per-input variance measurement — that GPU run is a named open item.

### E7. Steering (Result 5 — "gauge, not wheel")

**Did:** amplify mode — during turn 3 only (answer already on the page, so answer-invariance is
structural), magnify the model's own projection on the direction by gain g (g=1 is an exact
no-op). Controls: dose sweep, norm-matched random direction, sign flip. Separately (experiment
two): inject "toward correct" during turn 2 and measure accuracy.

**Found:** Mistral×MATH — stated confidence on wrong answers **80→65→43** as g goes 1→2→4;
correct answers barely move (97→96→89); ECE **0.31→0.13**; random flat; dampening increases
overconfidence (sign flip ✓). Accuracy steering: no lift (GLM×GPQA 0.38 steered vs 0.41
baseline, every dose) — **preliminary**, not yet in the audited write-up. Replication is
architecture-dependent: GLM null at tested settings (its stated confidence saturates at ~100
under greedy decoding), Gemma underpowered on MATH (GPQA rerun queued).

**Means:** causal, for the *report*: the model uses this direction when stating confidence, and
amplifying its own computed doubt makes it honest about failing. Not causal for *competence*:
the same direction can't be pushed to produce right answers. A gauge the model reads, not a
wheel that drives the answer — which is exactly what you'd want a monitor to be.

### E8. The deviations log (the trust experiment we ran on ourselves)

Four planned controls each caught a real bug, forced a fix, and a re-run: (1) train/test
leakage — sibling samples of one prompt straddled the split; fixed with question-grouped folds;
(2) the confounded read site — answer tokens decoded 0.74 at layer 0; fixed with the decision
token; (3) the MATH grader marked correct answers wrong over formatting; caught by a planned
label-validity audit, everything re-graded; (4) a prompt-wording leak (geometry wording on QA);
behavior identical before/after, re-ran anyway. **Means:** the surviving results are believable
*because* the controls have drawn blood. This is a slide-worthy meta-point and buys credibility
for everything else.

### E9. (Lineage, pre-pivot) Where geometric concepts live

Before the metacognition pivot, the same apparatus probed *spatial* content in Qwen2.5-7B/32B
while writing constructions: relational role → angle → precise coordinates become decodable in
that order across depth, identically at both scales (coarse-to-fine); coordinates are the
deepest-computed and most quantization-fragile property. Post-leakage-fix, the robust survivor
is the relational-role result (acc 0.70, +0.37 over the naming baseline); coords/angle were
mostly leakage. Worth one breath in a talk at most — it explains where the read-then-poke
toolkit and the grouped-split hygiene came from.

---

## 3. So which experiments carry which slide beats?

| beat | experiment | one-line payoff |
|---|---|---|
| It knows | E1 (+E2) | probe beats stated 12/16, math +0.20 |
| It's *this attempt* | E3 (+E4) | probe 0.89 vs own bet 0.48, difficulty fixed |
| You can read it without labels | E5 | lens = probe on dense, zero labels |
| …but only on dense | E6 | 0.43 → 0.88 within one family; cos 0.96 smear |
| You can use it (as a gauge) | E7 | 80→43 on failures, ECE halved, random flat |
| Why believe any of it | E0 + E8 | layer-0 chance; four bugs caught by design |

Current deck (v4, 24 slides) covers all six beats. If a future cut needs to go deeper on
"label-free," the material lives in §0 above — the four levels (operational, epistemic,
mechanistic, practical) are themselves a candidate slide: most audiences hear "no labels" as a
technicality when it's actually the load-bearing move that turns a correlation study into an
access-problem claim.
