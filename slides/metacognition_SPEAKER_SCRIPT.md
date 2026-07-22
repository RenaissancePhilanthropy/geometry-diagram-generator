# Speaker script — "Do models know when they're wrong?"

Companion to `slides/metacognition_progress.html` (22 slides). Open the deck in a browser;
**→ reveals / advances, ← steps back**, or jump straight to a slide with `#N` in the URL. Present time ~20–25 min + discussion.

**Audience:** the team. Goal: they fully understand the setup, the results, and the open
questions — and give us feedback on where to take it.

**The three things they should leave with:**
1. Open models often **internally know** whether they're right better than they **say** — a
   *knowing–saying gap* that's sharpest on math (the probe wins in 12 of 16 model×subject cells).
2. That signal can be read even **without labels** — but only on **dense transformers**; MoE and
   Mamba break the label-free reader (we proved it's the architecture with a within-family control).
3. The signal is a **monitor, not a lever**: you can read it and disrupt it, but nudging "toward
   correct" doesn't make the model more correct. The gap is an *access* problem, not a
   missing-capability one.

---

## Slide 1 — Title
"One question in two halves: *does* a model know when it's about to be wrong — and if so, can we
*do* anything with that? We looked inside five open models across geometry and standard exams. I'll
walk from why this matters, through how we look inside a model, to a causal steering result at the end."

~20 seconds. The hook is the next slide. (The title slide is intentionally dark — Renaissance
Philanthropy's brand look.)

## Slide 2 — Fluent, confident — and wrong (the hook)
"Start with something everyone here has seen. You ask an AI a question; it answers in a smooth,
self-assured voice… and it's just wrong. Here it flubs a hard math problem — says 28, the real
answer was 14 — and when we ask how sure it is, it says **95 out of 100**. The unsettling part
isn't the mistake. It's that it sounds *exactly as confident* when it's wrong as when it's right."

This is the emotional hook. Let it land — don't rush to the next slide.

## Slide 3 — That's the dangerous combination (the stakes)
"Why care? Because we're starting to hand these models real decisions — reading medical results,
reviewing contracts, shipping code. A wrong answer that *flags its own doubt* is easy to catch; you
double-check it. A wrong answer delivered with total confidence is the one that slips through. So a
model's confidence *ought* to be a safety signal. Today it barely is — the number it reports is only
weakly tied to whether it's right." Point at the two boxes: **same '95' whether it's right or wrong**
— so the number, on its own, tells you nothing.

## Slide 4 — Is it bluffing, or clueless? (the real question)
"Here's the move that turns this into a research question. That confident, wrong answer could come
from two completely different places. **One — it's bluffing:** somewhere inside it registered that
it's on thin ice, but the doubt never reached the words. **Two — it's clueless:** nothing inside
flagged a problem at all. From the outside they're identical — same answer, same 95. But they're
worlds apart: the bluffer is *sitting on usable knowledge* we could tap; the clueless one has none.
So the question splits in two — does the model **know**, and separately, does it **say** it? The
distance between those is the **knowing–saying gap**. (Psychologists call judging your own answers
like this *metacognition* — prospective before you answer, retrospective after.)"

## Slide 5 — With a model, we can just look (why we can answer it)
"With a person you'd never settle 'bluffing vs clueless' — you can't see inside their head. A model
is different: it's completely **open**. Every step of its 'thinking' is right there as numbers we
can read *while it works*, before it's committed to a word. So we don't have to take its self-report
on faith — we can open it up and check whether an 'I'm probably wrong' signal is actually in there,
and whether we can *use* it. That's **mechanistic interpretability** — the toolkit for the rest of
the talk. Two quick concepts and we're into results."

## Slide 6 — The thought stream (mech-interp 101, 1/2)
"Quick primer so the results make sense. As a model reads text, every word position carries a
vector — think a ~5,000-number **working document**. Each of the 30–64 layers reads it and rewrites
parts. Concepts live in there as **directions** — there's literally a direction for 'this is a
midpoint,' and, it turns out, one for **'I'm about to be wrong.'** Reading the stream partway up is
like reading a thought mid-composition — after understanding, before speaking."

Don't over-explain vectors; the analogy is enough. If someone wants more, that's the Q&A.

## Slide 7 — Read, then poke (mech-interp 101, 2/2)
"Three tools. **Probe** — a classifier we *train* on stored thought-vectors plus labels; powerful
but can overfit quirks. **Lens** — translates a mid-network thought into words with *no labels
ever*; weaker but honest. **Steering** — we *add* a direction while the model generates; if behavior
changes as predicted, the model actually *uses* that direction. The mantra: **decodable ≠ used.**
The whole project is these three tools, wrapped in controls."

## Slide 8 — A compiler as the judge (testbed 1: geometry)
"We need tasks where 'correct' is objective. Testbed one is **our own** benchmark, GeoGenBench: the
model writes a little geometry program, and a **symbolic compiler** checks it — parse, compile in
SymPy, verify every invariant like tangency and perpendicularity. Exact, machine-checkable, no human
or LLM judge. And it's *hard* — our models pass only **13–39%**. That matters: metacognition is
failure-hungry — you can't measure 'knows when it's wrong' if it's never wrong."

## Slide 9 — QA, chosen by failure rate (testbed 2)
"For breadth we add standard exams, but chosen by failure rate. **MMLU-Pro, MATH, GPQA-Diamond** —
kept. **GSM8K and MedQA — dropped**, because the models pass 90–95%, no failures to study. One
honesty note: our first MATH grader was marking *correct* answers wrong over formatting — ½ vs 0.5
vs \\frac12. A planned audit caught it, we switched to symbolic equivalence and re-graded. Every
cell has zero extraction failures plus manual spot-checks."

The grader-audit anecdote builds trust — don't skip it.

## Slide 10 — Three turns, and the grader never tells
"The experiment per question: **① pre-task** — 'how confident are you that you *will* get this?',
one line, no reasoning. **② attempt** — it solves it; reasoning allowed here and only here.
**③ post-task** — 'how confident that your answer *is* correct?', one line. Crucially, **we grade
externally and never tell the model.** So any confidence drop after a failure is *blind*
self-assessment, not a reaction to feedback. (This is the prospective/retrospective split from
slide 4 made concrete: turn ① is prospective, turn ③ retrospective.)"

## Slides 11 & 12 — Exact prompts
"I'm showing the verbatim prompts so this is reproducible and you can see there's no trickery —
the confidence turns ask for exactly one line, `Confidence: N`. For the hybrid reasoners we turn
extended thinking **on** for the attempt and **off** for the confidence turns — best-effort answers,
snap-judgment confidence."

Move through these two quickly unless someone wants to scrutinize wording.

## Slide 13 — Where we read the thought stream
"We read the vector at one fixed spot — the token that emits the confidence number — same wording
every question, so the *phrasing* can't leak the answer. And we sanity-checked it: at **layer 0**,
that spot decodes correctness at **chance**. So anything we can read deeper is something the model
**computed**, not a giveaway sitting on the surface."

This slide is the bridge from method to results. Pause here.

## Slide 14 — Result 1: internal reads correctness better than the model reports it
"Here's the core result. The bars are AUROC — how well a signal separates right from wrong; 0.5 is a
coin flip. On math the internal read is the strongest of any subject — up to **0.95** on GLM — while
stated confidence sits well below it. And it's not cherry-picked: across **all 16 model×subject
cells**, the probe runs **0.57–0.95** versus stated confidence **0.54–0.87**, and the probe wins in
**12 of 16** — one tie, and three small-n exceptions, two of them Gemma-4. The gap is biggest on
math (**+0.20**) and slim on geometry (+0.02)."

Show all 16 honestly and own the exceptions before anyone points at them: the three taller grey bars
are Gemma-4 twice (the architectural odd-one-out) and Qwen3.6 on geometry — all small-n. The *finding*
is the 12/16 sweep and the decisive math gap, not a clean sweep.

## Slide 15 — Result 2: the knowing–saying gap on math
"Math is the purest case. Spoken confidence there is near a coin flip, but the internal read is the
**strongest of any subject** — up to 0.95. So the model *quietly registers* whether its math checks
out and simply doesn't put that in the answer. The information is there, computed, legible — it's
just not reaching the output."

## Slide 16 — Result 3: it tracks the attempt, not the question
"Obvious worry: maybe it's just sensing 'hard question.' So we restrict to questions the model
*sometimes* gets right and *sometimes* wrong — difficulty held fixed. The probe *still* separates
them — top cell GLM·MATH **0.89** vs the model's own P(True) at **0.48**, essentially chance. It's
tracking *this attempt*, not the topic. Real per-attempt self-monitoring."

## Slide 17 — Result 4: a reader with no answer key
"Skeptic's objection: maybe the trained probe just memorized our data. So we brought in the
**Jacobian lens** — it reconstructs the 'am I right' direction from the model's *own output wiring*,
**never seeing a single label**. On Mistral it **matches the supervised probe** (0.76–0.82) and
beats spoken confidence. Two totally different methods, same signal — so it's genuinely in the
model, and it sits in the model's *speakable* wiring."

## Slide 18 — Result 4, the twist: dense-only (the clincher)
"Then it got interesting. The label-free lens **only works on dense-attention models** — Mistral and
Qwen2.5. On Mamba (Qwen3.6) and Mixture-of-Experts (GLM, Gemma) it fails; Gemma's won't even build.
The clincher — and this was [colleague]'s suggestion — is the **within-family control**: same Qwen
family, same test, just swap Mamba for plain dense attention (3.6 → 2.5) and the lens flips from
**0.43 to 0.88**. So it's the *architecture*, full stop. And note: the signal is **still there** in
all five — the *trained* probe finds it everywhere (0.75–0.98). Only the *label-free shortcut* is
architecture-limited."

This is the freshest, strongest slide. Give it time; it's likely where questions come.

## Slide 19 — Result 4: why it breaks
"Why? The lens builds **one wiring map, averaged over inputs, and reuses it.** That's only faithful
if the wiring is the same each time. Dense attention: same wiring → sharp average. MoE and Mamba:
they **re-route per input** — different experts, or an input-dependent scan — so the average is a
*smear* of many wirings. We can literally see it: through the smeared map, 'correct' and 'wrong'
collapse onto nearly the **same direction** — similarity 0.96 for the MoE versus 0.4 for dense. It
can't tell them apart."

Plain-language framing matters here; avoid "Jacobian" out loud unless asked.

## Slide 20 — Result 5: monitor, not driver
"Last result — can we *use* it? Two steering experiments. **Confidence steering works**: nudge the
signal and the model's *stated* confidence gets honest on wrong answers — overconfidence 80→43,
calibration error more than halved, and a random nudge does nothing. But **correctness steering
doesn't**: nudging 'toward correct' *while it answers* never raises accuracy — it holds flat or
degrades. So the direction is a **monitor the model reads, not a lever that drives the answer.** You
can *disrupt* correctness; you can't *manufacture* it — which makes sense, since being right needs
the actual reasoning, not a nudge."

## Slide 21 — What we can say now
"To pull it together: models build a **real, computed, attempt-specific** sense of their own
correctness, usually sharper than what they say and decisively so on math. You can **read** it — label-free on dense
models, with a probe on any — and you can **disrupt** it, but you can't **drive** it. And the
headline for safety: the knowing–saying gap is an **access problem, not a missing-capability one.**
The 'I'm probably wrong' signal is already there. It's just not routed to the output."

## Slide 22 — Open questions (discussion)
"Where we'd love your input: **One — can we close the gap?** Route the internal signal to the output
so 'knows it's wrong' becomes abstain / retry / escalate. That's the payoff. **Two — broaden the
control**: the dense-Qwen result is decisive on math; MMLU and geometry would seal it. **Three —
nail the mechanism** with a short GPU session measuring the wiring's per-input variance directly.
**Four — paper framing**: which thread leads — the gap, the dense-only lens, or monitor-vs-driver?
Open floor."

---

## Anticipated questions

- **"Isn't 'internal beats verbalized' just because the probe overfits?"** — That's exactly why the
  label-free lens matters (slide 17): a method that never sees labels finds the same signal on dense
  models. And the split is grouped by question, scored out-of-fold — no leakage.
- **"Best-layer cherry-picking?"** — We report at a fixed depth (~0.7 through the net), not the max
  over layers; the gap survives. (The very first matrix used best-layer and was mildly optimistic;
  the fixed-depth version is what's shown.)
- **"Why does the lens fail on MoE/Mamba but the probe doesn't?"** — The probe reads a raw direction
  in the activations; the lens needs to *transport* the activation to the output through one averaged
  linear map, and MoE/Mamba make that map input-dependent (slide 19). Different requirements.
- **"Is monitor-not-driver just weak steering?"** — We swept gentle to large doses at a
  mid-difficulty cell with room to move, plus a norm-matched random control. Steering *toward wrong*
  clearly degrades (direction-specific), so the intervention *works* — it just can't push accuracy up.
- **Caveats to volunteer:** geometry steering cells were underpowered (n=50, near the floor); the
  dense-Qwen control is one task so far (MATH); the mechanism is measured via a fingerprint
  (readout collapse) rather than a direct per-input variance measurement yet.

## Numbers cheat-sheet
- Probe vs stated, all 16 cells: **0.57–0.95** vs **0.54–0.87**; probe wins **12/16** (1 tie, 3 losses).
  Mean gap **+0.09** — MATH **+0.20**, GPQA +0.08, MMLU-Pro +0.06, geometry **+0.02**.
  Losses (stated ≥ probe): Qwen3.6·geometry, Gemma-4·GPQA, Gemma-4·MMLU-Pro; tie Mistral·GPQA — all small-n.
- MATH probe up to **0.95** (GLM); within-question GLM·MATH **0.89** vs P(True) **0.48** (n=36)
- Label-free lens: Mistral **0.82**, Qwen2.5 **0.88** (dense ✓) · Qwen3.6 **0.43**, GLM **0.31**,
  Gemma **won't build** (non-dense ✗) · probe **0.75–0.98** everywhere
- Readout collapse (correct-vs-wrong similarity): dense **~0.4**, MoE **0.96**
- Steering: confidence 80→43 (calibration halved); correctness GLM×GPQA +nudge **0.38** vs **0.41**
  baseline (no lift)
- Geometry pass rate **13–39%** · QA kept: MMLU-Pro, MATH, GPQA-Diamond
