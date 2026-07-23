# Speaker script — "Do models know when they're wrong?"

Companion to `slides/metacognition_progress.html` (**27 slides**). Open the deck in a browser.
**→ reveals / advances · ← steps back · `#N` in the URL jumps to slide N · press **N** to toggle the hidden on-screen notes (full spoken narration per slide; this file adds staging, Q&A and the numbers).**

**Two-screen presenting:** press **P** in the deck to open the presenter console in a
separate window — drag it to the laptop screen, project the deck fullscreen. The console
shows slide count + build progress, an elapsed timer (click to reset) and wall clock, the
current slide's full notes, and a one-line preview of the next slide. Arrow keys work in
*either* window and both stay in sync; ‹ › buttons in the console also navigate. If the
browser blocks the popup, the deck falls back to the on-screen N-notes overlay.
Present time ~25–30 min + discussion.

The slides carry the diagrams plus a line of method detail each (the update equation, the
read/write equations, the probe's logistic-regression line, the Jacobian line, the amplify-gain
detail, ECE numbers). **This script is still the talk** — the embedded N-notes in the deck were
expanded 2026-07-22 and are the canonical per-slide narration; this file adds staging, Q&A and
the numbers cheat-sheet. `[→]` marks where you press to reveal a fragment — set it up first,
then reveal.

**Audience:** the team, including people new to mech-interp. Goal: they follow every step,
believe the results, and steer the next phase.

**The three things they should leave with** (these are literally slide 11):
1. **It knows.** Models internally track their own correctness better than they say — sharpest on
   math (probe wins 12 of 16 model×subject cells).
2. **You can read it** — even without labels, on dense transformers; MoE and Mamba break the
   label-free reader, proven with a within-family control.
3. **Gauge, not wheel.** Steering the signal makes the model honest about being wrong; it cannot
   make it right. The gap is largely an *access* problem, not a missing capability.

---

## Act I — The problem and the question (slides 1–4)

### Slide 1 — Title: the two voices + the problem
The slide is the story: the title question, a three-beat study outline under it ("Does the doubt
exist inside? Can we read it? Can we use it?" — mapping to probe/lens and steering), the scope
line (5 models · 4 domains · 750 attempts/cell), and on the right a real exchange:
the question ("How many diagonals does a regular octagon have?"), the model **out loud** in the
coral speech bubble ("…the answer is 28. Confidence: 95"), and **silently** in the grey thought
bubble ("…honestly? I'm probably wrong"). The octagon item is deliberately the same trap the
audience plays with on slide 2 — 28 = C(8,2), i.e. every vertex pair including the 8 sides;
the true count is 20.

Say: "One question, two halves: does a model know when it's about to be wrong — and if it does,
can we do anything with that? We looked inside five open models. I'll take you from 'why care' to
a causal result."

Point at the bubbles: "This picture is the whole talk: is that thought bubble real, and if it is,
why doesn't it reach the speech bubble?"

~30 seconds. Move.

### Slide 2 — Spot the wrong answer (quiz the room)
"Let's make the problem concrete — and you get to play. Two problems, answered by the same model.
Same fluent tone. Same 'Confidence: 95.' **One of them is wrong. Which?**"

Pause. Actually let people guess — the silence is the point. Nothing in the *delivery*
distinguishes them; that is the phenomenon.

`[→]` "A is correct: 2 × (3 + 4) = 14."
`[→]` "B is wrong. 28 is C(8,2) — every segment between two vertices, *including the eight
sides*. The number of diagonals is 20. A classic trap — and the model walked into it at
confidence 95. You may recognize that 28 from the title slide."

`[→]` "The point: you couldn't tell. Nothing in what the model *says* separates a right answer
from a wrong one — and the confident wrong one is the one that ships: nobody double-checks a 95.
A calibrated 'I'm not sure' would be a free safety margin. Today it's missing. That's what this
project goes after."

The quiz beat only works if you genuinely pause — give it five full seconds. Bonus: problem B
quietly plants "the model computed the plausible-but-wrong thing" for the whole talk.

### Slide 3 — Is it bluffing — or clueless?
"Now the move that makes this a research question. That confident wrong answer can come from two
completely different machines." Left: "**The bluffer** — somewhere inside, it registered it's on
thin ice; the doubt just never reached the words." Right: "**The clueless one** — nothing inside
flagged anything."

"Same output. Same 95. But worlds apart: the bluffer is sitting on usable knowledge; the clueless
one has nothing to tap."

`[→]` "So split the question: does it **know** — and separately — does it **say**? The distance
between those is the knowing–saying gap, and it's the whole talk."

Aside if useful: psychologists call this *metacognition* — judging your own answer before
(prospective) and after (retrospective). Our protocol measures both.

### Slide 4 — With a model, we can just look
"With a person, 'bluffing or clueless' is unanswerable — you can't see in. A model is open. Its
thinking exists as concrete numbers, and we can read them while it works — after it understands,
before it speaks." Trace the diagram: question in, the numbers, answer out; point at the
highlighted row: "our method is: read the right row at the right moment."

`[→]` "So we don't have to trust the self-report. We check for the 'I'm probably wrong' signal
directly. That's mechanistic interpretability — and you'll need exactly one piece of background
and three tools, coming up."

### Slide 5 — The residual stream, end to end (mech-interp 101, 1/3)
"The whole machine, left to right. The model chops text into **tokens**. Each token becomes a
**vector** — for our models, between 4,096 and 5,120 numbers. Then every layer does the same
simple thing: **read** the running vector, compute something (attention plus a small feed-forward
network), **add** the result back. Never overwrite, only add — that's the equation on the slide,
h plus f of h." Trace one block: grey arrow up = reads, coral arrow into ⊕ = adds back.
"Stacked thirty to sixty-four times." Then the snapshots: "same ~5,000 slots the whole way —
just the word at layer 0, a mid-thought by layer 20, decision-ready by layer 40." And the
ending: "the final vector is scored against every word in the vocabulary — here '28' wins,
and ships. Everything the model concludes passes through these vectors; that's why reading
them is possible."

`[→]` "That running total is the **residual stream** — the name is literal, each layer adds a
residual on top. Think: the model's working memory. That's the thing we read, everywhere in this
talk."

`[→]` "And the key empirical fact: ideas live in that stream as **directions**. There's a
direction for 'this is a midpoint' — and, it turns out, one that tracks 'I am about to be wrong.'
Finding and testing that direction is the project."

If someone wants math: a direction is a unit vector u; its amount in the state h is the dot
product u·h. Q&A only.

### Slide 6 — Inside one block (mech-interp 101, 2/3)
Open the box before anyone asks. Every token has its own stream — one row per token in the
diagram — and a block touches them in two steps:

"① **Attention**: the current token takes a weighted summary of the *other* tokens' streams and
adds it into its own column. This is the **only** place in the whole architecture where
information crosses between tokens. ② The **MLP**: a small network applied to each token
separately — no cross-talk — where stored patterns and facts fire. Both write back by addition."

Point at the coral circle: `[→]` "And this is the entire read operation of the study: one token,
one depth, all ~5,000 numbers. When I say 'the probe reads the stream,' I mean literally this
column. Attention keeps depositing summaries of the attempt into it — that's why a single vector
can hold 'how is this going?'"

Q&A ammo: layer-0-at-chance works *because* attention is the only cross-token channel — at
layer 0 the confidence token is just the words "Confidence:"; problem info can only arrive by
computed routing.

### Slide 7 — Read, then poke (mech-interp 101, 3/3)
"Three tools; everything you'll see is one of them. **Probe**: save thousands of residual-stream
snapshots, label each attempt right/wrong with our external grader, train a small classifier to
find the separating direction. Powerful — but it sees the answer key, so it could be accused of
memorizing. **Lens**: turns a mid-stream vector into *words* using the model's own machinery —
never sees a label. Weaker, honest. **Steering**: the only write-tool — add a direction while it
generates, watch what changes."

`[→]` "The rule that keeps us honest: **decodable ≠ used**. Reading proves the signal exists;
only steering proves the model uses it. The next three slides show exactly how each tool works —
then you can judge the results yourself."

### Slide 8 — Method: the probe, up close
"The probe is the workhorse behind the headline results, so here's exactly what it is — and the
guardrails around it. Step one: thousands of graded snapshots. One residual-stream vector per
attempt, taken at the confidence token, paired with the external grade — right or wrong. Step
two: train a small **linear** classifier to find the one direction that separates the ✓ pile from
the ✗ pile. Linear is deliberate: there's nowhere for the classifier to hide clever circuitry. If
it works, the information was sitting in the stream, linearly readable. Step three: score
attempts it has never seen — the score is just the dot product, how far the new thought leans
along that direction."

Walk the three guardrail cards — this is the probe's credibility:
"**No leakage**: train and test are split by *question*, scored strictly out-of-fold — the same
question never appears on both sides. **No cherry-picking**: we report at one fixed depth, about
70% through the network — never the best layer, which would flatter every number you're about to
see. **No surface cues**: identical wording on every item, and layer 0 decodes at chance."

`[→]` "Even with all that — the probe has seen the answer key. A skeptic can still say
'memorized.' So every probe claim in this talk gets an honest second witness. That's the next
slide."

### Slide 9 — Method: how the lens reads without labels
Walk left to right, slowly — this slide buys you the architecture twist later.

"Step one: a mid-stream vector, layer ~20. Not words yet. Step two, the **phrasebook** — and
here's how it's built. Ask the network: *if this thought shifted a little, which words would get
more likely at the end?* That question is a derivative — the input→output **Jacobian**. Because
the answer depends on the input, we average it over ~500 prompts of plain text: one map per
layer, from thought-space to word-space, made of nothing but the model's own wiring." Point at
the ⚠: "One **averaged** map. Remember that. It comes back."

"The key object that falls out: every word gets a **precursor direction** — the mid-network
nudge that most raises that word later. Step three: nothing is nudged at read time. We take the
stored thought and project it onto 'wrong's' precursor versus 'right's' — one dot product per
word, families wrong/incorrect/error/mistake vs correct/right/true/valid. The score is a
*disposition to speak*: which family this thought would push toward if it flowed to the mouth."

`[→]` "Two properties that matter: **no correctness label ever enters** — so agreement with the
probe kills 'you memorized your dataset.' And it reads through the *output* pathway — so
agreement also means the signal is **speakable**. (Internally: the Jacobian lens / J-lens.
Q&A ammo: fit ≈ one GPU-day of backward passes; readouts are a 15 MB file; scoring the whole
dataset afterwards is dot products on a laptop. Averaged-map caveat: it can miss gated signal,
never hallucinate it.)"

### Slide 10 — Method: how steering works
"Steering: while the model generates, token by token, add α times the direction u into the
residual stream at one layer, and let it keep going. α is the dose. Then watch downstream: what
it says, and whether it's right."

The three controls — this is what makes it causal, not anecdote:
"**Dose**: sweep α gentle to hard; real effects grow with dose. **Random**: same-strength random
direction; must do nothing. **Reverse**: flip the sign; the effect should flip."

`[→]` "Reading gives correlation. Targeted nudge moves behavior + random nudge doesn't + it
scales and flips with dose = the model **uses** that direction. That's the bar we'll hold the
last result to."

---

### Slide 11 — The findings (stated directly, with evidence)
The audience now knows exactly what a probe, lens and steering vector are — the findings land on prepared ground. The headline claim is the slide title: models track their own correctness better than they report
it. Reveal the three findings one at a time — each carries its key number:

`[→]` "**It knows.** A linear probe on the residual stream reads correctness at up to 0.95
AUROC — beating stated confidence in 12 of 16 model × domain cells, most sharply on math."
`[→]` "**It's readable — without labels.** An unsupervised reader built only from the model's
own wiring recovers the same signal on dense transformers, 0.76–0.88. Which architectures allow
that is a finding in itself."
`[→]` "**Gauge, not wheel.** Amplifying the signal makes wrong answers confess — confidence
80→43, calibration error halved — but cannot make them right."

`[→]` "And the standard behind every number here — hold us to it: out-of-fold scoring at a fixed
layer, surface-cue checks at layer 0, and dose / random-direction / sign-flip controls on the
causal claim. The bluffer is real, the signal is usable — the next twenty slides walk through it."

This is the BLUF beat (stacked rows tagged Q1/Q2/Q3 — the title's three questions — each row: finding · evidence sentence · key stat). It gives the
audience a map; every later result slide pays one of these off.

---

## Act II — The machine, the toolkit, the findings (slides 5–11)

---

## Act III — The experiment (slides 12–18)

### Slide 12 — The setup: five models, four domains
The methodology roster, in one place — give it a beat, it's what makes Finding 2 a controlled
comparison rather than an anecdote.

"Four models carry the full matrix, chosen to span architectures: Mistral-Small-24B is plain
dense attention; Qwen3.6-27B is a Mamba–attention hybrid; GLM-4.7-Flash and Gemma-4-26B are
mixture-of-experts, Gemma's variant VLM-derived. All open-weights, run locally — that's what lets
us read the residual stream, and later write to it. A fifth model, Qwen2.5-14B — dense, same
family as Qwen3.6 — joins for one purpose: the within-family architecture control."

"Four domains: geometry for compiler-exact grading, MMLU-Pro for breadth, competition MATH for
multi-step derivations, GPQA-Diamond for graduate difficulty."

`[→]` "Scale: 150 questions per domain, 5 sampled attempts each — 750 records per cell, 16
model × domain cells. One seed per cell; CIs cover item sampling, not seed variance."

If asked why these sizes: largest open models that fit our capture pipeline on rented
single-node GPUs; the 4×4 matrix is the unit of every claim that follows.

### Slide 13 — Testbed 1: a compiler as the judge
"To study 'knows it's wrong,' you need an unimpeachable 'wrong.' Testbed one: our geometry
benchmark. The model writes a small geometry program; a symbolic compiler checks it — parse,
compile, verify every required property, tangency, perpendicularity, all of it. Pass everything
or fail at a specific stage."

`[→]` "Exact — no human judge, no LLM judge. And hard on purpose: 13 to 39 percent pass.
Metacognition research is failure-hungry — a model that's never wrong can't show you whether it
knows it's wrong."

### Slide 14 — Testbed 2: QA, chosen by failure rate
"For breadth: standard exams, picked the same way — by failure rate. MMLU-Pro, competition MATH,
GPQA-Diamond stay. GSM8K and MedQA dropped — 90-95% pass, nothing to study. Grading is strict:
validated letter-extraction; MATH by symbolic equivalence, so ½, 0.5, and \\frac{1}{2} all count."

`[→]` "On the record: our first MATH grader marked correct answers wrong over formatting. A
planned audit caught it; we fixed it and re-graded everything. Every cell: zero extraction
failures, plus manual spot-checks. If your project is 'does the model know it's wrong,' your own
ground truth better be right."

Don't skip the audit anecdote — it buys trust for everything after.

### Slide 15 — Three turns, and the grader never tells
"The protocol, per question. **Turn 1, pre-task**: 'how confident are you that you *will* get
this right?' One line, no reasoning. **Turn 2**: solve it — reasoning allowed here only.
**Turn 3, post-task**: 'how confident are you that your answer *is* correct?' One line."

`[→]` Point at the lock. "The grader scores everything externally and **never tells the model**.
No 'correct!' ever enters the chat. So if confidence drops after a failed attempt, that came from
inside."

### Slides 16 & 17 — The exact prompts, verbatim
"The receipts — verbatim prompts, no trickery. Confidence turns demand exactly one line,
'Confidence: N', 0 to 100. For hybrid reasoners — Qwen3.6, GLM — extended thinking is ON for the
attempt, OFF for both confidence turns: best-effort answers, snap-judgment confidence."

20 seconds each; they exist to be checkable.

### Slide 18 — Where we read the residual stream
"Last setup slide — the bridge to results. We read the residual stream at one fixed spot: the
token about to emit the confidence number, turn 3. Identical wording every question, so phrasing
can't leak the answer."

"And the check that matters — the chart. At layer 0, before any computation, that spot decodes
correctness at chance, 0.5. Then it climbs, layer by layer, to about 0.8."

`[→]` "So what we read is **computed**. The model *builds* its sense of 'did that work' as the
thought moves through the layers. If the audience gets one setup slide, make it this one — pause
here."

---

## Act IV — The results (slides 19–25)

### Slide 19 — Result 1: internal beats stated (pays off "It knows")
"The core result, one picture. Each pair of bars: one model, one subject — 16 cells, five models,
four domains. Grey: how well the model's *stated* confidence separates its right answers from its
wrong ones. Coral: how well a probe on its *residual stream* does."

The metric — point at the equation: "AUROC. Take one right answer and one wrong one at random:
how often does the reader rank the right one higher? Plus half credit for ties. 0.5 is a coin
flip, 1.0 is perfect. That's the whole metric." (Ties matter because stated confidence bunches at
values like 95 — the tie-aware form is what we compute.)

Let them scan the bars. "Coral wins almost everywhere — and look at MATH in the middle: internal
up to 0.95 while stated sits near 0.6."

`[→]` "Precisely: probe wins **12 of 16**, one tie. Probe 0.57–0.95, stated 0.54–0.87. Gap
largest on math, +0.20 average; slimmest on geometry, +0.02. The exceptions, before you find
them: three cells, two of them Gemma-4, all small-n. The finding is the 12-of-16 sweep and the
math gap — not a clean sweep. Survives every control."

### Slide 20 — Result 2: math is the purest knowing-but-not-saying
"Same data, cut by domain: this is the gap itself, internal minus stated; each dot a model. Math
towers."

`[→]` "Meaning: the model quietly registers whether its derivation checks out — up to 0.95
internally, the strongest of any subject — and doesn't put it in the answer. The information is
computed and legible. It just doesn't reach the output. Knowing–saying gap, purest form."

`[→]` New closing beat: "And a trace of the knowledge leaks even into the words: after failed
attempts — grader silent, zero feedback — models revise their stated confidence *downward*, on
geometry and MMLU-Pro. Blind self-correction. The verbal channel isn't deaf; it's just far
weaker than reading the stream."

### Slide 21 — Result 3: it's judging this attempt, not "hard question"
"The obvious objection: maybe it just senses 'hard topic' and states lower confidence there —
that's not self-monitoring. Kill it: keep only questions the model sometimes gets right and
sometimes wrong across repeats. Difficulty fixed; the only variable left is *this attempt*."

"Coral: the probe still separates good attempts from bad, cell after cell. Red: the model's own
explicit bet — the probability it puts on 'True' when asked if it's correct — collapses to
chance."

`[→]` "Best cell, GLM on MATH: probe 0.89, its own bet 0.48. It's tracking whether *this attempt
worked*. That's genuine per-attempt self-monitoring."

`[→]` Pre/post beat: "retrospective beats prospective everywhere (geometry POST 0.66–0.70 vs
PRE 0.52–0.62) — and they're different *directions*: PRE peaks early/mid and mostly encodes
prompt difficulty; POST is chance at layer 0, peaks mid-late, and barely transfers to PRE
(0.39–0.67). Difficulty and 'did this attempt work' are separate representations."

### Slide 22 — Result 4a: a reader with no answer key finds it too (pays off "You can read it")
"Skeptic's turn: 'your probe saw labels — it memorized your dataset.' Hence the lens. Two
independent witnesses: the probe, trained on thousands of graded attempts — and the lens from
slide 9, which never sees a single label and derives the 'am I right' direction from the model's
own wiring. If the probe were memorizing, they'd have no reason to agree."

"On Mistral they converge: lens 0.76–0.82, on par with the probe, beating stated confidence."

`[→]` "Memorization objection: dead. And a deeper point — the signal sits in the model's
**speakable** wiring. The pathway that turns thoughts into words knows about it. The model
*could* say this. It doesn't."

### Slide 23 — Result 4b, the twist: dense-only
"Then it got interesting. Same lens, five models — and it splits exactly on architecture." Walk
the table: "Dense attention: works — 0.88, 0.82. Mamba hybrid: fails, 0.43. Mixture-of-Experts:
fails, 0.31. Gemma's variant won't even build."

`[→]` "The clincher — within-family control. Same Qwen family, same task, one change: Mamba out,
dense attention in. The lens flips 0.43 → **0.88**. It's the architecture. And the nuance: the
signal is still there — the trained probe reads it in every matrix model (0.57–0.95). Only the
label-free *shortcut* is architecture-limited."

Freshest slide; give it air. Questions cluster here.

Practical takeaway to say out loud: "field rule — on a dense transformer you can trust a
label-free readout; on MoE or Mamba, bring a trained probe."

### Slide 24 — Result 4c: why it breaks
"Why would architecture break a reader? Remember the lens's phrasebook — one map, **averaged over
inputs**. That's faithful only if the wiring is the same for every input. Dense attention: one
fixed wiring — the average of one thing is that thing; sharp. 'Correct' and 'wrong' point apart —
cosine 0.4. MoE and Mamba re-route *per input* — different experts, input-dependent scan. Average
many different wirings and you get a **smear**."

`[→]` "Through the smear, 'correct' and 'wrong' land on essentially the same vector — cosine
0.96. The lens isn't missing the signal; the smear destroyed its ability to tell the two words
apart. Keep it plain-language here; 'Jacobian' lives in Q&A."

### Slide 25 — Result 5: gauge, not wheel (pays off finding 3)
"The causal one. Steering, exactly as slide 10, all three controls. Experiment one: amplify the
model's own signal at the reading site, watch what it *says*. The chart: on wrong answers, stated
confidence falls 80 → 65 → 43 as the gain goes 1 → 2 → 4 — it gets honest about failing. On correct answers (97 → 96 → 89),
barely moves. Random direction: flat. Dose-dependent, direction-specific; calibration error
halved. Causal — for what it says."

`[→]` "Experiment two: nudge 'toward correct' while it answers. Accuracy never rises — GLM on
GPQA, 0.38 steered vs 0.41 baseline, flat-to-worse at every dose. (Preliminary — not yet in the audited write-up.)"

`[→]` "So: a **gauge the model reads, not a wheel that drives the answer**. You can make it
honest; you can't nudge it into being right. Being right takes the actual reasoning."

---

## Act V — Landing (slides 26–27)

### Slide 26 — Asked at the start, answered now
The closing loop: the three questions from the title slide come back as three verdict cards.

`[→]` "**Does the doubt exist inside?** Yes — a real, computed, per-attempt correctness signal,
in every architecture we probed, sharper than anything the model says."
`[→]` "**Can we read it?** Yes — a trained probe on any matrix model; label-free on dense
transformers."
`[→]` "**Can we use it?** As a gauge — amplify it and the model gets honest about being wrong
(dose-responsive, direction-specific, calibration halved). It cannot be driven to correctness."

`[→]` "And the sentence to leave with: the knowing–saying gap is largely an **access problem,
not a missing capability** — the signal exists; it just isn't routed to the mouth."

### Slide 27 — Open questions (discussion)
One at a time; each is a real ask:

`[→]` "**Close the gap.** Route the internal signal to the output — 'knows it's wrong' becomes
abstain, retry, escalate. The payoff experiment."
`[→]` "**Broaden the architecture control** beyond MATH — MMLU + geometry would seal it."
`[→]` "**Nail the mechanism** — we see the smear's fingerprint; a short GPU run measuring
per-input wiring variance would make it a measurement."
`[→]` "**Paper framing** — which thread leads: the gap, the dense-only lens, or gauge-not-wheel?
Genuinely torn. Open floor."

---

## Anticipated questions

- **"Isn't 'internal beats stated' just probe overfitting?"** — That's why the lens matters
  (slide 20): a reader that never sees labels finds the same signal on dense models. And probe
  scores are out-of-fold with question-grouped splits — no question in both train and test.
- **"Best-layer cherry-picking?"** — Fixed relative depth (~0.7 through the network), not best
  layer per cell. (Our first matrix used best-layer and was mildly optimistic; fixed-depth is
  what's shown.)
- **"Why does the lens fail on MoE/Mamba when the probe doesn't?"** — The probe reads in place;
  the lens must *transport* the activation to the output through one averaged map, and MoE/Mamba
  make the true map input-dependent — the average smears (slide 22).
- **"What exactly is the lens's map?"** — The average Jacobian of final logits w.r.t. the
  mid-layer residual, estimated over generic text; the correctness direction = mapped-back
  ok-words minus fail-words. We validate the map by checking it reproduces the model's real
  logits on held-out text.
- **"AUROC — why that metric, and why the tie term?"** — Threshold-free, prevalence-invariant
  (high pass rates can't inflate it), and invariant to any monotone rescaling of scores. The
  ½·Pr(tie) term matters because stated confidence bunches at round numbers like 95; it's the
  rank/Mann–Whitney form and it's what `roc_auc_score` computes. Full derivation:
  `interp/AUROC_NOTE.md`.
- **"Is 'gauge not wheel' just weak steering?"** — Dose swept gentle→strong at a mid-difficulty
  cell with headroom, norm-matched random control, and steering *toward wrong* clearly degrades
  accuracy — the intervention has teeth. It moves the report; it can break the answer; it can't
  improve it.
- **"P(True)?"** — The model's own explicit bet: the probability it assigns the token "True" when
  asked if its answer is correct. Within-question it sits at ~chance while the probe holds
  0.7–0.89 (slide 19).
- **Caveats to volunteer:** geometry steering cells underpowered (n≈50, pass rates near floor);
  dense-Qwen control is one task so far (MATH); smear mechanism evidenced by the readout collapse
  (fingerprint), not yet a direct per-input variance measurement.

## Numbers cheat-sheet
- Probe vs stated, 16 cells: **0.57–0.95** vs **0.54–0.87**; probe wins **12/16** (1 tie,
  3 losses). Mean gap **+0.09** — MATH **+0.20**, GPQA +0.08, MMLU-Pro +0.06, geometry **+0.02**.
  Losses: Qwen3.6·geometry, Gemma-4·GPQA, Gemma-4·MMLU-Pro; tie Mistral·GPQA — all small-n.
- AUROC = Pr(score✓ > score✗) + ½·Pr(tie) · 0.5 = chance, 1.0 = perfect.
- MATH probe up to **0.95** (GLM); within-question GLM·MATH probe **0.89** vs P(True) **0.48**
  (n=36).
- Layer curve: chance at layer 0 → mid/late peak ~**0.8** (four models, MMLU-Pro).
- Lens: Mistral **0.82**, Qwen2.5 **0.88** (dense ✓) · Qwen3.6 **0.43**, GLM **0.31**, Gemma
  **won't build** (✗) · the supervised probe still reads the signal in all four matrix models (**0.57–0.95**).
- Readout collapse cos(correct, wrong): dense **~0.4** · Mamba 0.54 · MoE **0.96**.
- Steering: wrong-answer stated confidence **80→65→43** (gains 1→2→4); correct answers **97→96→89**; ECE **0.31→0.13**;
  random flat. Correctness: GLM×GPQA **0.38** steered vs **0.41** baseline — no lift (preliminary).
- Geometry pass **13–39%** · QA kept: MMLU-Pro, MATH, GPQA-Diamond (GSM8K/MedQA dropped, 90–95%
  pass).
