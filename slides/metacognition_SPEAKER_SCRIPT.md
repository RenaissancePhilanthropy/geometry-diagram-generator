# Speaker script — "Do models know when they're wrong?"

Companion to `slides/metacognition_progress.html` (**25 slides**). Open the deck in a browser.
**→ reveals / advances · ← steps back · `#N` in the URL jumps to slide N · press **N** to toggle the hidden on-screen notes (full spoken narration per slide; this file adds staging, Q&A and the numbers).**
Present time ~25–30 min + discussion.

The slides are deliberately sparse — a diagram and a line or two. **This script is the talk.**
`[→]` marks where you press to reveal a fragment — set it up first, then reveal.

**Audience:** the team, including people new to mech-interp. Goal: they follow every step,
believe the results, and steer the next phase.

**The three things they should leave with** (these are literally slide 5):
1. **It knows.** Models internally track their own correctness better than they say — sharpest on
   math (probe wins 12 of 16 model×subject cells).
2. **You can read it** — even without labels, on dense transformers; MoE and Mamba break the
   label-free reader, proven with a within-family control.
3. **Gauge, not wheel.** Steering the signal makes the model honest about being wrong; it cannot
   make it right. The gap is an *access* problem, not a missing capability.

---

## Act I — The problem, the question, the answer up front (slides 1–5)

### Slide 1 — Title: the two voices
The slide is the story: our question up top; below, the model speaking twice — **out loud** in the
coral speech bubble ("…the answer is 28. Confidence: 95") and **silently** in the grey thought
bubble ("…honestly? I'm probably wrong").

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

### Slide 5 — The short version (the answer, up front)
"Before the how — here's what we found, so you know where this is going." Reveal the three cards
one at a time:

`[→]` "**It knows.** Inside, these models track their own correctness — better than what they
say. Sharpest on math."
`[→]` "**You can read it.** Even with no answer key — on some architectures the model's own
wiring gives it up. And which architectures those are turns out to be a finding in itself."
`[→]` "**Gauge, not wheel.** Poke the signal and the model gets honest about being wrong. It does
not get more right."

`[→]` "In other words: the bluffer is real. The rest of the talk earns these three claims — and
you should hold me to each one."

This is the BLUF beat. It gives the audience a map; every later result slide pays one of these off.

---

## Act II — The toolkit (slides 6–10)

### Slide 6 — How a model thinks (mech-interp 101, 1/2)
"One slide of background — this is genuinely all you need. Three steps. The model chops text into
**tokens**. Each token becomes a **vector** — about five thousand numbers. Then every layer does
the same simple thing: **read** the running vector, compute something, **add** the result back.
Never overwrite, only add." Trace one block: grey arrow up = reads, coral arrow into ⊕ = adds
back. "Stacked forty to sixty times."

`[→]` "That running total is the **residual stream** — the name is literal, each layer adds a
residual on top. Think: the model's working memory. That's the thing we read, everywhere in this
talk."

`[→]` "And the key empirical fact: ideas live in that stream as **directions**. There's a
direction for 'this is a midpoint' — and, it turns out, one that tracks 'I am about to be wrong.'
Finding and testing that direction is the project."

If someone wants math: a direction is a unit vector u; its amount in the state h is the dot
product u·h. Q&A only.

### Slide 7 — Read, then poke (mech-interp 101, 2/2)
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

"Step one: a mid-stream vector, layer ~20. Not words yet. Step two: push it through the model's
own **phrasebook** — one map from thought-space to word-space. We build it once by asking the
model: averaged over ordinary text, how does a change here end up changing your word choices?
Note the fine print: built once, **averaged over inputs**, reused for everything." Point at the ⚠:
"Remember that. It comes back."

"Step three: out come word-leanings. We look at exactly two families — right/true/correct versus
wrong/false/error. The score is the lean."

`[→]` "The property that matters: **no correctness label ever enters**. If this label-free reader
agrees with the trained probe, the signal can't be our labels' artifact — it's really in the
model. (Internally this is the Jacobian lens / J-lens; keep 'Jacobian' for Q&A.)"

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

## Act III — The experiment (slides 11–16)

### Slide 11 — Testbed 1: a compiler as the judge
"To study 'knows it's wrong,' you need an unimpeachable 'wrong.' Testbed one: our geometry
benchmark. The model writes a small geometry program; a symbolic compiler checks it — parse,
compile, verify every required property, tangency, perpendicularity, all of it. Pass everything
or fail at a specific stage."

`[→]` "Exact — no human judge, no LLM judge. And hard on purpose: 13 to 39 percent pass.
Metacognition research is failure-hungry — a model that's never wrong can't show you whether it
knows it's wrong."

### Slide 12 — Testbed 2: QA, chosen by failure rate
"For breadth: standard exams, picked the same way — by failure rate. MMLU-Pro, competition MATH,
GPQA-Diamond stay. GSM8K and MedQA dropped — 90-95% pass, nothing to study. Grading is strict:
validated letter-extraction; MATH by symbolic equivalence, so ½, 0.5, and \\frac{1}{2} all count."

`[→]` "On the record: our first MATH grader marked correct answers wrong over formatting. A
planned audit caught it; we fixed it and re-graded everything. Every cell: zero extraction
failures, plus manual spot-checks. If your project is 'does the model know it's wrong,' your own
ground truth better be right."

Don't skip the audit anecdote — it buys trust for everything after.

### Slide 13 — Three turns, and the grader never tells
"The protocol, per question. **Turn 1, pre-task**: 'how confident are you that you *will* get
this right?' One line, no reasoning. **Turn 2**: solve it — reasoning allowed here only.
**Turn 3, post-task**: 'how confident are you that your answer *is* correct?' One line."

`[→]` Point at the lock. "The grader scores everything externally and **never tells the model**.
No 'correct!' ever enters the chat. So if confidence drops after a failed attempt, that came from
inside."

### Slides 14 & 15 — The exact prompts, verbatim
"The receipts — verbatim prompts, no trickery. Confidence turns demand exactly one line,
'Confidence: N', 0 to 100. For hybrid reasoners — Qwen3.6, GLM — extended thinking is ON for the
attempt, OFF for both confidence turns: best-effort answers, snap-judgment confidence."

20 seconds each; they exist to be checkable.

### Slide 16 — Where we read the residual stream
"Last setup slide — the bridge to results. We read the residual stream at one fixed spot: the
token about to emit the confidence number, turn 3. Identical wording every question, so phrasing
can't leak the answer."

"And the check that matters — the chart. At layer 0, before any computation, that spot decodes
correctness at chance, 0.5. Then it climbs, layer by layer, to about 0.8."

`[→]` "So what we read is **computed**. The model *builds* its sense of 'did that work' as the
thought moves through the layers. If the audience gets one setup slide, make it this one — pause
here."

---

## Act IV — The results (slides 17–23)

### Slide 17 — Result 1: internal beats stated (pays off "It knows")
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

### Slide 18 — Result 2: math is the purest knowing-but-not-saying
"Same data, cut by domain: this is the gap itself, internal minus stated; each dot a model. Math
towers."

`[→]` "Meaning: the model quietly registers whether its derivation checks out — up to 0.95
internally, the strongest of any subject — and doesn't put it in the answer. The information is
computed and legible. It just doesn't reach the output. Knowing–saying gap, purest form."

### Slide 19 — Result 3: it's judging this attempt, not "hard question"
"The obvious objection: maybe it just senses 'hard topic' and states lower confidence there —
that's not self-monitoring. Kill it: keep only questions the model sometimes gets right and
sometimes wrong across repeats. Difficulty fixed; the only variable left is *this attempt*."

"Coral: the probe still separates good attempts from bad, cell after cell. Red: the model's own
explicit bet — the probability it puts on 'True' when asked if it's correct — collapses to
chance."

`[→]` "Best cell, GLM on MATH: probe 0.89, its own bet 0.48. It's tracking whether *this attempt
worked*. That's genuine per-attempt self-monitoring."

### Slide 20 — Result 4: a reader with no answer key finds it too (pays off "You can read it")
"Skeptic's turn: 'your probe saw labels — it memorized your dataset.' Hence the lens. Two
independent witnesses: the probe, trained on thousands of graded attempts — and the lens from
slide 9, which never sees a single label and derives the 'am I right' direction from the model's
own wiring. If the probe were memorizing, they'd have no reason to agree."

"On Mistral they converge: lens 0.76–0.82, on par with the probe, beating stated confidence."

`[→]` "Memorization objection: dead. And a deeper point — the signal sits in the model's
**speakable** wiring. The pathway that turns thoughts into words knows about it. The model
*could* say this. It doesn't."

### Slide 21 — Result 4, the twist: dense-only
"Then it got interesting. Same lens, five models — and it splits exactly on architecture." Walk
the table: "Dense attention: works — 0.88, 0.82. Mamba hybrid: fails, 0.43. Mixture-of-Experts:
fails, 0.31. Gemma's variant won't even build."

`[→]` "The clincher — within-family control. Same Qwen family, same task, one change: Mamba out,
dense attention in. The lens flips 0.43 → **0.88**. It's the architecture. And the nuance: the
signal is still there in all five — the trained probe finds it everywhere, 0.75–0.98. Only the
label-free *shortcut* is architecture-limited."

Freshest slide; give it air. Questions cluster here.

### Slide 22 — Result 4: why it breaks
"Why would architecture break a reader? Remember the lens's phrasebook — one map, **averaged over
inputs**. That's faithful only if the wiring is the same for every input. Dense attention: one
fixed wiring — the average of one thing is that thing; sharp. 'Correct' and 'wrong' point apart —
cosine 0.4. MoE and Mamba re-route *per input* — different experts, input-dependent scan. Average
many different wirings and you get a **smear**."

`[→]` "Through the smear, 'correct' and 'wrong' land on essentially the same vector — cosine
0.96. The lens isn't missing the signal; the smear destroyed its ability to tell the two words
apart. Keep it plain-language here; 'Jacobian' lives in Q&A."

### Slide 23 — Result 5: gauge, not wheel (pays off finding 3)
"The causal one. Steering, exactly as slide 10, all three controls. Experiment one: amplify the
model's own signal at the reading site, watch what it *says*. The chart: on wrong answers, stated
confidence falls ~87 → 43 as the dose rises — it gets honest about failing. On correct answers,
barely moves. Random direction: flat. Dose-dependent, direction-specific; calibration error
halved. Causal — for what it says."

`[→]` "Experiment two: nudge 'toward correct' while it answers. Accuracy never rises — GLM on
GPQA, 0.38 steered vs 0.41 baseline, flat-to-worse at every dose."

`[→]` "So: a **gauge the model reads, not a wheel that drives the answer**. You can make it
honest; you can't nudge it into being right. Being right takes the actual reasoning."

---

## Act V — Landing (slides 24–25)

### Slide 24 — What we can say now
"As promised at the start." The three verdict cards mirror slide 5, now earned:

`[→]` "**READ — yes.** Probe on any architecture; label-free on dense."
`[→]` "**DISRUPT — yes.** Steer the signal, the stated confidence gets honest. With controls."
`[→]` "**DRIVE — no.** Gauge, not wheel."

`[→]` "And the safety headline: the knowing–saying gap is an **access problem, not a missing
capability**. The 'I'm probably wrong' signal already exists. It just isn't routed to the mouth.
So the fix isn't 'teach models self-knowledge' — it's *wire up what's already there*."

### Slide 25 — Open questions (discussion)
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
  **won't build** (✗) · probe **0.75–0.98** everywhere.
- Readout collapse cos(correct, wrong): dense **~0.4** · Mamba 0.54 · MoE **0.96**.
- Steering: wrong-answer stated confidence **~87→43** over the dose sweep; ECE **0.31→0.13**;
  random flat. Correctness: GLM×GPQA **0.38** steered vs **0.41** baseline — no lift.
- Geometry pass **13–39%** · QA kept: MMLU-Pro, MATH, GPQA-Diamond (GSM8K/MedQA dropped, 90–95%
  pass).
