# Speaker script — progress report: "Do models know when they're wrong?"

Companion to `slides/metacognition_progress_report.html` (**19 slides**). Open the deck in a browser.
**→ reveals / advances · ← steps back · `#N` in the URL jumps to slide N · N toggles on-screen notes ·
P opens the two-screen presenter console** (timer, current notes, next-slide preview; arrow keys work
in either window).

**This deck's job:** a team progress report — per experiment: *why we ran it → what ran → result →
next step*. **Every graph sits on its own slide with the calculation panel beside it** — the
figure on the left, "how this is computed" on the right (the metric, the per-mark recipe, the data
provenance), the takeaway below. Present each graph slide the same way: recipe first, then the
picture, then the numbers. It is deliberately **not** the tutorial; the 24-slide talk deck
(`metacognition_progress.html`) carries the full mech-interp walkthrough.

**The embedded N-notes in the deck are the canonical word-for-word narration** (expanded
2026-07-23). This file adds: the timing plan, staging and transitions, per-slide Q&A ammo, the
numbers cheat-sheet, and a cut plan.

**Audience:** the team. Several will pattern-match to "is this rigorous?" — which is why the
standards line (slide 3), the calculation panels, and the deviations slide (17) exist.
**Target: ~19–20 min of content + discussion anchored on slide 19** (the cut plan gets it to ~15–16).

---

## Timing plan (~19:45 content)

| # | slide | time | cumulative |
|---|---|---|---|
| 1 | title + status strip | 0:30 | 0:30 |
| 2 | why this program exists | 1:00 | 1:30 |
| 3 | experiment progress | 1:00 | 2:30 |
| 4 | experiment setup | 1:15 | 3:45 |
| 5 | toolkit in one breath | 0:45 | 4:30 |
| 6 | E1 · internal vs stated (setup) | 0:45 | 5:15 |
| 7 | GRAPH · probe vs stated, 16 cells (fig1) | 1:15 | 6:30 |
| 8 | GRAPH · the gap by domain (fig2) | 1:15 | 7:45 |
| 9 | GRAPH · read-site check (fig5) | 1:00 | 8:45 |
| 10 | GRAPH · pre vs post (fig6) | 1:00 | 9:45 |
| 11 | E2 · difficulty control (setup) | 1:00 | 10:45 |
| 12 | GRAPH · within-question (fig3) | 1:15 | 12:00 |
| 13 | E3 · label-free lens | 1:45 | 13:45 |
| 14 | E4 · architecture twist | 1:45 | 15:30 |
| 15 | E5 · steering (setup) | 1:00 | 16:30 |
| 16 | GRAPH · dose–response (fig4) | 1:15 | 17:45 |
| 17 | what bit us | 0:45 | 18:30 |
| 18 | where this lands | 1:15 | 19:45 |
| 19 | next steps & asks | rest of meeting |  |

Protect 11–14 and 16; compress 7 and 10 under pressure (cut plan at the end).

---

## Slide 1 — Title + status strip (0:30)

Frame the meeting immediately:

> "This is the **progress report** on the metacognition work — does a model know when it's wrong.
> Organized **by experiment**: why we ran it, what ran, the result, what's next. Every graph gets
> its own slide with the calculation right beside it, so you can check where each number comes
> from. Light on background — the tutorial deck exists if you want the full walkthrough."

Status cards left→right: capture matrix **done** · label-free lens on all five models **done** ·
steering **causal on one model, replicating on two** · paper framing — "a *decision*, not a run."

If asked "what's a cell?": one model × one benchmark — 150 questions × 5 attempts = 750 records.

## Slide 2 — Why this program exists (1:00)

Left card — the phenomenon: models fail **confidently**; a wrong answer ships with the same
fluent 95 as a right one. Right card — the split: *doesn't know* vs *won't say* are different
claims; measure each. The payoff: a calibrated "I'm not sure" is a **free safety margin** —
abstain, retry, escalate — sitting unused *if* the signal exists.

`[→]` Inspiration: psychology's **metacognition** split — prospective ("will I get this right?")
vs retrospective ("did I?"). We measure both — and unlike behavioral calibration work, we also
**read the stream while it happens**. (The pre-vs-post graph on slide 10 is that split, measured.)

**Q&A ammo:** "Isn't this calibration research?" — Calibration scores the *output* channel; we
also measure the *internal* channel and the gap. The within-question result (slide 12) can't
even be expressed output-only.

## Slide 3 — Experiment progress (1:00)

The BLUF table — don't read every cell; pick one column and walk it. Best choice: **why we ran
it**, the motivation chain in the plainest words (if the grades are wrong, every result is wrong
→ first make sure the signal exists at all → make sure it isn't just spotting hard questions →
we need a reader that never saw the answers → the reader broke on two models, find out why →
seeing the signal isn't proof the model uses it). The **asks** column is the same logic as
questions. Then the **findings** column: name each once — each gets a slide.

`[→]` Standards fragment, said once so every slide inherits it: out-of-fold at a fixed layer —
never best-of-forty — layer-0 surface check on the read site; dose / random / sign-flip on the
causal claim. "Hold us to that bar."

## Slide 4 — Experiment setup (1:15)

Three turns: ① pre-task confidence, one locked line · ② the attempt, reasoning only here
(hybrid reasoners: thinking ON here, OFF for confidence turns) · ③ post-task confidence, one
locked line. The lock: the external grader **never tells the model** — any confidence change
after failure came from inside.

**Name the models** (top of left column): four carry the full matrix, chosen to *span
architectures* — **Mistral-24B** (dense) · **Qwen3.6-27B** (Mamba hybrid) · **GLM-4.7** and
**Gemma-4** (mixture-of-experts). All open-weight and run locally, which is what lets us read
*and* steer the stream. A fifth, **Qwen2.5-14B** (dense), is held aside as the within-family
architecture control — it becomes the whole point at E4 (slide 14). Don't dwell; the architecture
spread pays off later.

**Walk the benchmark bullets** (left column): **GeoGen geometry** (our construction benchmark:
the model writes a RecipeDSL program, a symbolic compiler checks every property — the label is a
theorem check; 13–39% pass *by design*) · **MMLU-Pro** (10-option MC, validated letter match) ·
competition **MATH** (boxed answers, symbolic equivalence — ½ = 0.5 = \frac{1}{2}) ·
**GPQA-Diamond** (graduate-level, 4-option). Chosen by failure rate; GSM8K/MedQA dropped at
90–95%. Footnote line: 4×4×150×5 = **12,000 graded records** + the fifth model as lens control.

**Then read the worked example aloud** (right column) — one MMLU-Pro attempt end to end:
confidence before ("Confidence: 80"), the answer ("Answer: C"), confidence after
("Confidence: 85"), and the grader recording ✗ against gold = B — **silently**. That transcript
is the whole methodology on one item; after it, "750 records per cell" means something concrete.

`[→]` Read-site fragment with the scar story: we read the token that decides "Confidence: N" —
identical context everywhere; an earlier site (the answer tokens) decoded **0.74 at layer 0** —
surface cues — and was scrapped. **We show the layer-by-layer chart behind this claim once the probe's introduced — slide 9; the toolkit's next.**

**Q&A ammo:**
- "Does the model see its own turn-1 confidence while answering?" — Yes, as **text**: the three
  turns are one conversation (`question → "Confidence: 80" → "now answer" → answer → "assess"`),
  so its stated prior is in the transcript it re-reads at turn 2. One locked line, structurally
  identical everywhere — it can't differentially confound comparisons.
- "How is memory imposed across turns?" — It isn't. The model is stateless between turns; the
  only memory is the growing transcript, re-read from scratch each turn. Within a forward pass,
  **attention** carries information from the transcript (including the model's own answer) into
  the confidence token's stream — that's why the turn-3 token can hold "how did my attempt go."
  We inject nothing; the sole exception is E5 steering, deliberately, turn 3 only. Cross-ref:
  the pre/post graph (slide 10) is this fact made visible — PRE reads with only the question in
  context, POST with its own attempt; the lift is what its own work adds.
- "Why one seed per cell?" — honest limit; CIs cover item sampling, not seed variance.
- "Why these models?" — largest open weights that fit the capture pipeline; open weights let us
  read *and write* the stream.

## Slide 5 — Toolkit in one breath (0:45)

Three cards, one sentence each; do not teach. Probe = supervised read (saw the answer key —
suspicion warranted). Lens = label-free read from the model's own wiring; reads through the
*output pathway*, so findings are **speakable**. Steering = the write-tool; bar = dose + flat
random + sign flip. `[→]` The rule: **decodable ≠ used** — reading proves presence, only
intervention proves use.

Math if pressed: one object, the residual vector h at the confidence token; read = u·h,
write = h + α·u. Depth lives in the talk deck.

## Slide 6 — E1 · internal vs stated — setup (0:45)

Why-box (the per-experiment template): **question zero** — is there any internal signal at all?
If the probe can't beat the stated number, there is no gap to study.

What ran: per cell, probe reads the stored decision-token states — out-of-fold, fixed 0.7·L —
AUROC compared against stated confidence's AUROC on the **same 750 records**.

**Transition: "the sixteen-cell graph is next, with the calculation beside it."** Status: track
closed and audited.

## Slide 7 — GRAPH · probe vs stated, 16 cells (fig1) (1:15)

Recipe first: grey bar = rank the cell's 750 records by the number the model *said*; coral bar =
rank the **same records** by the probe's read-out (out-of-fold, fixed layer); AUROC each — only
the scorer changes. The ruler (the equation on the slide): pick one right + one wrong attempt at
random — how often does the scorer rank the right one higher? 0.5 = coin flip; rank-based, so
"everything is 95" is scored fairly; ties get half credit.

Let them scan: coral above grey nearly everywhere; MATH cells sharpest.

`[→]` Numbers, slowly: probe **0.57–0.95** vs stated **0.54–0.87**; probe wins **12/16** (one
tie); MATH **+0.20**, geometry **+0.02**. Exceptions named first: three losses, all small-n, two
Gemma-4. "The sweep plus the math gap — not a clean sweep."

**Q&A ammo:**
- "Pre- or post-task confidence?" — **Post** (turn 3, after answering), for both bars: grey is
  the post-task stated number, coral is the probe at the turn-3 decision token — apples to
  apples. The pre-task read appears only on the pre/post graph (slide 10).
- "Why AUROC?" — threshold-free, rank-based, imbalance-robust (some cells ~90% one class); the
  tie term matters because stated confidence bunches at 95. `interp/AUROC_NOTE.md`.
- "Why no ECE here?" — ECE needs a calibrated 0–100 probability; the stated number has one, the
  probe's read-out is an arbitrary-scale score — you'd have to fit a calibration map on top,
  which muddies "simple linear reader." And ECE isn't comparable across cells whose pass rates
  span 13–92%, while AUROC is. ECE appears where it's the right tool: steering (slide 16), same
  scale and same cell before/after.

## Slide 8 — GRAPH · the gap by domain (fig2) (1:15)

The why line: the gap should be widest **where surface cues die** — a wrong `\boxed{42}` has no
tell. The calculation is one subtraction: probe − stated per cell (the previous slide's bars),
grouped by benchmark; bar = mean over the 4 models, one dot per model.

"MATH towers (+0.20). Geometry smallest (+0.02) — at 13–39% pass, failure is near-default,
compressing any reader's contrast. The *ordering* is itself evidence the signal is computed
self-assessment."

`[→]` "Internal read on MATH up to **0.95**; stated sits near 0.6 — it registers whether the
derivation held, and reports 95 anyway."
`[→]` The leak: after failures — grader silent — stated confidence revised **downward**
(geometry, MMLU-Pro). Blind self-correction: the verbal channel is weak, not deaf.

## Slide 9 — GRAPH · the read-site check (fig5) (1:00)

Recipe first (right panel): save the decision-token vector **at every layer**; per layer train
the same question-grouped, out-of-fold probe; plot held-out AUROC vs relative depth ℓ/L — one
line per model (MMLU-Pro cells).

Then the picture: "layer 0 — raw embeddings — exactly **chance**: the wording there is identical
for every record, nothing to read. Then it climbs to ~0.8 mid-late. Whatever a deep layer knows
at that spot, it **computed**." Discipline note: all reported numbers use the fixed **0.7·L**
depth, never the peak.

`[→]` "The 'did that work?' signal is **built during the forward pass**."

**Transition:** "same recipe, one more cut — next slide compares this after-the-attempt read
with the before-the-attempt read."

## Slide 10 — GRAPH · prospective vs retrospective (fig6) (1:00)

This slide answers the question someone is already forming: *"is that curve just difficulty?"*

Recipe first: two read sites per record, everything else identical. **PRE** = the **last prompt
token** — the model has read the question but written nothing; no elicitation, we simply read
the stream there. **POST** = the turn-3 confidence decision token (the previous slide's curve).
Same probe pipeline at every layer, same grader labels, same question-grouped out-of-fold
scoring — only the read site changes. Four panels, one per model, MMLU-Pro.

How to read it: "PRE above chance is not mysterious — the prompt alone carries signal about
whether the attempt will succeed. That's **difficulty**, readable before any work happens. The
gap between the curves is what changes once the model has seen its own attempt — *that* part
deserves the name **self-assessment**."

`[→]` Takeaway: "POST rises above PRE — decisively by mid-depth — in **all four models**. And
they're largely **distinct directions**: a probe trained on the POST site reads the PRE site at
only **0.39–0.67**. Difficulty and 'did this attempt work' are different representations, in
different places." Pocket line: this is the layer-curve twin of the within-question dissociation
(slide 12) — two independent methods, same conclusion.

**Q&A ammo:** "Is PRE just a worse elicitation?" — There is *no* elicitation: it's a raw read at
the last prompt token, before any output exists. "Why is PRE so high on MMLU-Pro?" — because
difficulty *is* genuinely decodable from the prompt — that's exactly the confound the contrast
isolates; the claim was never that difficulty isn't readable, it's that POST adds attempt-specific
signal on top. (The audited geometry summary: POST 0.66–0.70 vs PRE 0.52–0.62.)

## Slide 11 — E2 · difficulty control — setup (1:00)

The objection, at full force: "the probe just learned which *questions* are hard — that's not
self-monitoring." The design that kills it: **mixed-outcome questions** only (same model, same
question, some of the 5 attempts pass, some fail); AUROC **within** each question; race the
probe against **P(True)** — the model's own explicit bet ("is your answer correct — True or
False?", read the probability on True), the strongest output-side baseline.

`[→]` Corroboration: the pre/post split (slide 10's graph) — retrospective beats prospective
(geometry POST **0.66–0.70** vs PRE **0.52–0.62**), largely **distinct directions** (transfer
0.39–0.67). Next-step line: nothing open — the pre/post layer curve landed (slide 10).

**Transition: "the graph and its recipe are next."**

## Slide 12 — GRAPH · within-question (fig3) (1:15)

Recipe, slowly — it kills the objection **by construction**: keep mixed-outcome questions;
AUROC inside each question (its own 5 attempts — same question, same difficulty); average across
questions; bootstrap resamples questions, not records. Coral = probe; grey = P(True).

"Read it: anything above 0.5 here is per-attempt information. Topic difficulty *cannot* explain
it — difficulty is identical inside a question."

`[→]` "Probe holds — **0.89** GLM×MATH — the model's own bet collapses to **0.48**. The stream
knows which attempt worked; the stated bet only knows which questions are scary. The study's
central dissociation."

**Q&A ammo:** "Is P(True) broken?" — No: cross-question it tracks difficulty fine; it collapses
only within-question — which is exactly the point.

## Slide 13 — E3 · the label-free lens (1:45)

Why-box, two halves: adversarial — the probe saw the answer key; "you fit your dataset" survives
all hygiene; the only killer rebuttal is a **second witness with no shared evidence**. And the
inspiration — Anthropic's verbalizable-workspace result (2026) supplied the instrument (adapted
open-source tool; fit ≈ one GPU-day; readouts = 15 MB; scoring = laptop dot products).

Three cards: ① one **averaged** input→output map per layer, fit on ~500 generic prompts ·
② every word gets a **precursor direction** · ③ score stored snapshots: "wrong/error/…" vs
"correct/right/…" lean. **What label-free deeply means:** the map is the model's own wiring, the
word lists are English, **nothing is fitted to our records**.

`[→]` Dense models land in probe territory: Mistral **0.76–0.82**, Qwen2.5 **0.88**, zero labels.
`[→]` Two upgrades: memorization objection **dead**; and the signal is **speakable** — "the
model could say this. It doesn't."

**Q&A ammo:** the averaged map can *miss* (under-sees input-specific routing) but cannot
hallucinate — conservative in the protective direction. The map = input→output Jacobian averaged
over text, validated by reproducing real logits on held-out text.

## Slide 14 — E4 · the architecture twist (1:45) — give it air

"The result we didn't order." Why-box: lens failed on two of five — bug or finding? The roster
was built for this; a same-family dense control was held aside.

Table: dense ✓ 0.88 / ✓ 0.82 · Mamba ✗ 0.43 · MoE ✗ 0.31 · Gemma ✗ won't build.

`[→]` Clincher: same Qwen family, one change — **0.43 → 0.88**. The trained probe still reads
all four matrix models (0.57–0.95): only the label-free *shortcut* is gated.
`[→]` Mechanism, plain: one map **averaged over inputs**; dense = stable transport, average
stays sharp (readout cos ≈ 0.4); MoE/Mamba re-route per input → smear → "correct" and "wrong"
collapse to one vector (**cos 0.96**). Field rule: dense → label-free OK; MoE/Mamba → probe.

Honest scope, unprompted: within-family control is **MATH-only**; smear = **fingerprint, not
measurement** — both queued.

**Q&A ammo:** "Why does the probe survive?" — it reads *in place*; the lens must *transport*
through one averaged map, and MoE/Mamba make true transport input-dependent.

## Slide 15 — E5 · steering — setup (1:00)

Why-box: decodable ≠ used; pre-registered bar = dose + random + sign. Two clean-design choices:
**amplify the model's own signal** (g = 1 is an exact no-op; no labels at intervention time) and
inject during the **assessment turn only** — answer-invariance is structural.

`[→]` The other half: the same direction **cannot make it right** — accuracy steering 0.38 vs
0.41 baseline (GLM×GPQA), every dose — **preliminary, provenance being audited**. Replication is
architecture-shaped: GLM null (verbalization saturates ~100 under greedy), Gemma MATH
underpowered → GPQA rerun queued.

**Transition: "the dose–response curves and the exact intervention formula are next."**

## Slide 16 — GRAPH · dose–response (fig4) (1:15)

Explain steering as a **physical action**, not a formula — this is the slide people get lost on.
"At the moment the model is about to state its confidence, its working memory is a big list of
numbers. We've found one *direction* in that list that tracks 'am I right?' — by comparing its
memory on answers it got right versus wrong. Steering means reaching into that memory as it
writes its confidence and turning its <i>own</i> reading along that direction up or down — a
volume knob on a signal it already computed, adding no new information. The knob at 1× is an
exact no-op. We only ever turn it during the assessment turn, so the answer is already fixed on
the page and can't change — we're moving what it <i>says</i>, not what it did." The formula in
the panel footnote is that knob written out, for anyone who wants it; don't read it aloud.

Curves: red = wrong answers, green = correct, dashed = random direction at matched strength.

`[→]` Frame the numbers first — stated confidence is a 0–100 scale. "As we turn the model's own
doubt signal up, its confidence on **wrong** answers falls from about **80 to 43** — it stops
insisting it's right. On **correct** answers it barely moves, 97 to 89 — so we're only deflating
*false* confidence, not muffling everything. (Midpoint on the chart: 65 at the halfway setting —
a clean dose-response.) Calibration error — the gap between claimed confidence and real accuracy
— roughly halves, 0.31 to 0.13. A random signal of equal strength does nothing, and turning the
signal *down* makes it more overconfident. All three checks pass." Land the phrase: "**a gauge
the model reads, not a wheel that drives the answer**."

**Q&A ammo:** "Just weak steering?" — the sweep reaches strengths that visibly move the report
and can break generation when pushed; moves the report, can degrade the answer, never improves
it — an asymmetry, not weakness.

## Slide 17 — What bit us (0:45)

Four rows, one sentence each: leakage → question-grouped folds, re-scored · read site (0.74 at
layer 0) → decision token · MATH grader → symbolic equivalence, re-graded · prompt wording →
re-ran, identical. `[→]` "Every headline number is post-fix; each bug was caught by a **planned**
control. Controls that have drawn blood are why the survivors are believable."

## Slide 18 — Where this lands (1:15)

`[→]` **It knows** — 12/16, up to 0.95; 0.89 vs 0.48 with difficulty frozen.
`[→]` **Readable without labels** — 0.76–0.88 dense; gated, isolated by the family swap.
`[→]` **Gauge, not wheel** — 80→43, ECE halved, controls clean; cannot produce correctness.
`[→]` Thesis sentence, slowly: "the knowing–saying gap is largely an **access problem, not a
missing capability** — the signal exists, is computed per attempt, sits in speakable wiring, and
isn't routed to the mouth. The engineering problem is **connecting what's already there**."

## Slide 19 — Next steps & asks (the rest of the meeting)

One `[→]` per item: ① GPU queue (booked): Gemma×GPQA steering rerun · per-input wiring variance
(the pre/post layer-curve figure from this queue already landed — slide 10) — FYI. ② **Close the
gap** — route the signal to abstain/retry/escalate; **ask: which target task?** (~a week of
runs). ③ Broaden the architecture control beyond MATH. ④ RLHF attribution — base-vs-instruct,
one box-day; **ask: now or post-skeleton?** ⑤ **Paper framing** — which thread leads? The
decision with a deadline.

"Floor's yours." If discussion stalls, seed with ⑤.

---

## Anticipated questions (cross-slide)

- **"Isn't the probe just overfitting?"** — Grouped out-of-fold splits + fixed layer + layer-0
  check *and* an independent label-free witness agreeing on dense models (slide 13).
- **"Why AUROC?"** — threshold-free, rank-based, imbalance-robust; tie-aware form;
  `interp/AUROC_NOTE.md`.
- **"Why the confidence token and not the answer?"** — We tried the answer tokens: 0.74 at
  layer 0 = surface cues. The fixed token is content-neutral by construction.
- **"Isn't the internal signal just difficulty?"** — Two independent answers: the pre/post
  layer curves (slide 10 — POST adds a lift over the PRE/difficulty read, distinct directions)
  and the within-question control (slide 12 — difficulty frozen, probe still separates).
- **"Could the lens failure on MoE/Mamba be a bad fit?"** — The within-family swap says no
  (0.43→0.88, one variable), and the failure has a signature (readout cos 0.96) a bad fit
  wouldn't produce.
- **"What would falsify the access-problem framing?"** — If routing experiments (slide 19, ②)
  can't surface the signal behaviorally even with direct access, "access problem" weakens toward
  "epiphenomenal signal." Exactly why the gap-closing demo is the payoff experiment.
- **Caveats to volunteer:** one seed per cell; within-family control MATH-only; smear =
  fingerprint not measurement; accuracy-steering number preliminary; geometry steering cells
  underpowered.

## Numbers cheat-sheet

- Matrix: 4 models × 4 benchmarks (GeoGen geometry · MMLU-Pro · MATH · GPQA-Diamond) × 150 q ×
  5 attempts = **750/cell**, 16 cells, **12,000 records**; + Qwen2.5-14B as lens control. One
  seed per cell.
- Probe vs stated: **0.57–0.95** vs **0.54–0.87**; probe wins **12/16** (1 tie, 3 small-n
  losses); mean gap **+0.09** — MATH **+0.20**, GPQA +0.08, MMLU-Pro +0.06, geometry **+0.02**.
- Within-question: probe up to **0.89** (GLM×MATH, n=36) vs P(True) **0.48**.
- Pre/post: PRE = **last-prompt-token, no-elicitation** read; POST = confidence decision token.
  Layer curves (fig6, MMLU-Pro): POST above PRE, decisively by mid-depth, all four models.
  Geometry summary: POST **0.66–0.70** vs PRE **0.52–0.62**; POST→PRE transfer **0.39–0.67**;
  POST residualized on PRE keeps **0.59–0.87**.
- Lens: Mistral **0.76–0.82**, Qwen2.5 **0.88** (dense ✓) · Qwen3.6 **0.43**, GLM **0.31**,
  Gemma **won't build** (✗). Probe still reads all four matrix models (**0.57–0.95**).
- Readout collapse cos(correct, wrong): dense **~0.4** · Mamba 0.54 · MoE **0.96**.
- Steering (Mistral×MATH): failures **80→65→43** (gain 1→2→4) · correct **97→96→89** ·
  ECE **0.31→0.13** · random flat · dampening → more overconfident. Accuracy steering:
  **0.38 vs 0.41** baseline (GLM×GPQA) — preliminary.
- Layer curve: chance at L0 → **~0.8** mid/late (fig5). Scrapped read site: **0.74 at L0**.
- Amplify formula: h → h + (g−1)·(û·h − μ)·û; g=1 exact no-op.
- Testbeds: geometry pass **13–39%**; GSM8K/MedQA dropped (**90–95%** pass).

## Cut plan (if the meeting compresses)

- **−2 min:** compress slide 5 (toolkit) to one sentence ("probe = supervised read, lens =
  label-free read, steering = write; decodable ≠ used") and present slide 8 (the gap) as one
  beat (the subtraction + "MATH towers", skip the leak fragment).
- **−4 min:** additionally give slide 4 one breath (protocol + silent grader + benchmark names)
  and present slides 9–10 (the two layer curves) as one beat ("layer 0 chance → ~0.8, and the
  pre-read shows the difficulty floor — POST adds the self-assessment lift"), and drop slide 17
  to one sentence over slide 18.
- **Never cut:** slides 11–14 and 16 (the dissociation, the label-free logic, the architecture
  control, the causal graph) and slide 19 — they are the report.
