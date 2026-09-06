# Abstract drafts

Scratch file for editing. Open beside `workshop_confidence.tex`. Delete before submission.
Edit A in place and tell me to apply it, or say which of B/C to take.

Synced with the paper as of commit `0d341b9`. D added after.

---

## A — what is in the paper right now

When a language model is confidently wrong, is the error unrepresented, or left unsaid?
We test this by reading the model's internal state directly.
Across four open models and four reasoning domains (MMLU-Pro, MATH, GPQA-Diamond, and a
formally graded geometry task), a simple linear probe predicts whether an answer is correct
better than the model's stated confidence in 12 of 16 model–domain settings (one tie; mean
+0.09 AUROC). The gap is largest on MATH (+0.20), where many incorrect solutions remain
fluent and well formed.

The signal appears to reflect the model's particular attempt, rather than just question
difficulty. When we compare multiple attempts at the same question, the model's own P(True)
falls toward chance while the internal probe remains predictive. The signal also transfers
across domains, suggesting that different tasks share some internal representation of
correctness.

Finally, we test whether this signal merely correlates with confidence or actually
influences it. On Mistral-Small-24B, removing the learned correctness direction after the
answer has been produced reduces the ability of stated confidence to distinguish correct
from incorrect answers (0.84 → 0.56 AUROC), while removing a matched random direction has
almost no effect. Amplifying the same direction lowers confidence on incorrect answers and
improves calibration. Together, these results suggest that language models can contain more
information about the correctness of their own answers than they express in verbal
confidence, and that some of this internal information is causally connected to what they
report.

### Still open in A

- **The answer-end result is missing.** Tonight's biggest finding, and the one that answers
  the obvious objection that the probe only works because we asked the model to introspect.
  One sentence would carry it (see B2 below).
- **Three "suggest"s in the last paragraph**, hedging hardest where the evidence is firmest.
  The ablation has a matched random control; it is not a "suggests".
- **The closing sentence** spends 18 words on "models know more than they say", and "can
  contain" hedges twice.
- **Three paragraphs** is unusual for this venue; most abstracts here are one block.
- Minor: "reasoning domains" is a stretch for MMLU-Pro, which is largely knowledge recall.

---

## B — A with three surgical edits

**B1.** Paragraph 3 opener, replacing "Finally, we test whether this signal merely correlates
with confidence or actually influences it":

> We then test whether the signal is used, not just present.

**B2.** Add to the end of paragraph 2:

> The signal is also present before we ask for it: read at the final token of the answer,
> with no confidence question in play, it already separates correct from incorrect attempts
> on MMLU-Pro (0.69, against 0.57 from the question alone).

**B3.** Replace the closing sentence:

> Together, these models carry more information about their own errors than their stated
> confidence conveys, and on Mistral that reporting channel depends on the direction we
> identify.

---

## C — single block, ~4 lines shorter, less hedged where the evidence carries it

When a language model is confidently wrong, is the error unrepresented, or left unsaid? We
read the model's internal state directly. Across four open models and four domains
(MMLU-Pro, MATH, GPQA-Diamond, and a formally graded geometry task), a linear probe predicts
correctness better than the model's stated confidence in 12 of 16 settings (one tie; mean
+0.09 AUROC), and the gap is largest on MATH (+0.20), where wrong solutions stay fluent and
well formed. The signal tracks the particular attempt rather than the question: across
repeated attempts at one question the model's own P(True) falls toward chance while the probe
holds, and a probe fitted after the attempt reads at chance before it. It is present before
we ask for it, already separating correct from incorrect attempts at the final token of the
answer (0.69 on MMLU-Pro, against 0.57 from the question alone). And the report depends on
it: removing the direction, after the answer is fixed, leaves stated confidence barely able
to separate the model's successes from its failures (0.84 → 0.56), while removing a matched
random direction changes nothing; amplifying it lowers confidence on wrong answers and halves
calibration error. Models carry more about their own errors than they say, and what they say
depends on it.

**C also folds in** the cross-site result (a probe fitted after the attempt reads at chance
before it), which is currently only in the body.

---

## D — colloquial rewrite (proposed; edit here, then tell me to apply)

When a language model is confidently wrong, is the error undetected or left unsaid? We
look inside the model to find out. Across four open models and four domains (MMLU-Pro, MATH,
GPQA-Diamond, and a geometry task graded by a compiler), a simple linear detector
reading the model's internal state predicts whether an answer is correct better than the
model's own stated confidence in 12 of 16 settings, by a mean of +0.09 AUROC. The gap is
widest on MATH (+0.20), where a wrong solution looks just as fluent as a right one. The
detector is not just spotting hard questions: given the same question several times, it still
separates the attempts that succeeded from the ones that failed, and read before the model
has attempted anything it is at chance. The signal is already there before we ask. At the
last token of the answer, with no confidence question in play, correctness is readable on
MMLU-Pro at 0.69 against 0.57 from the question alone. And on Mistral the model's report
depends on it: remove that direction after the answer is written and stated confidence can no
longer tell the model's successes from its failures (0.84 → 0.56), while removing a random
direction of the same size changes nothing; turn it up and confidence on wrong answers drops
while calibration error halves. Models carry more about their own errors than they say, and
on at least one model, what they say depends on it.

**What changed from A, and why**

- The difficulty argument is stated the way it was explained in conversation: "given the
  same question several times, it still separates the attempts that succeeded from the ones
  that failed." No P(True), no "within-question control"; those live in the body.
- The direction-level test is in ("read before the model has attempted anything it is at
  chance"), since it is the strongest form of the specificity argument.
- The answer-end result is in. It was missing from A and is the most novel finding.
- The ablation reads as an action ("remove that direction") rather than an operation on a
  learned object; "a random direction of the same size" replaces "matched random direction".
- The closing says "on at least one model" because the causal result failed to replicate
  on GLM. If Gemma replicates, this clause can strengthen.
- The cross-domain transfer sentence is dropped. It was the weakest claim in A and the body
  covers it.

**Length:** roughly the same as A once A's paragraph breaks are removed.

---

## Opening line, for the record

Settled: *"When a language model is confidently wrong, is the error unrepresented, or left
unsaid?"*

- "unrepresented / unsaid" are the paper's own Representation and Expression claims, so the
  question names the two things the five-claim paragraph separates.
- Perception verbs (register, notice, miss) were rejected: they imply awareness, which is
  what the paper is careful not to assume.
- "Information" was rejected: vague, noun-heavy, and it carries a technical sense in an ML
  abstract that is not what we mean.

---

## Numbers, and where each comes from

| claim | value | source | recomputable? |
|---|---|---|---|
| probe beats stated | 12 of 16, one tie, +0.09 | original matrix | no, hardware loss |
| MATH gap | +0.20 | original matrix | no |
| answer-end, MMLU-Pro | 0.693 | `results/answersite/temporal_sites_mistral_mmlu_pro.json` | yes |
| question-only, MMLU-Pro | 0.565 | same | yes |
| post probe read at pre site | 0.490 | `tier1_review.json`, cross_site_post_to_pre | yes |
| ablation | 0.836 → 0.564 | `results/causal/steer_ablation.json` | yes |
| matched random ablation | 0.833 | same | yes |
| calibration error | 0.337 → 0.186 | same | yes |
| lens, label-free | 0.82 MATH / 0.75 MMLU-Pro | `jlens_score.json` on recaptured cells | yes |
