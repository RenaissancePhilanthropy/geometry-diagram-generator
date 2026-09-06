# Abstract drafts

Scratch file for choosing. Open beside `workshop_confidence.tex`. Delete before submission.
Mark your pick, or edit C directly and tell me to apply it.

---

## A — current, in the paper now

Language models can give wrong answers with high confidence.
But does that mean they lack information about their mistake, or simply fail to express it?
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

**What I would change.** Three "suggest"s in the last paragraph, hedging hardest exactly
where the evidence is firmest. The answer-end result is missing entirely. The closing
sentence spends 18 words on "models know more than they say". Three paragraphs is unusual
for this venue.

---

## B — light touch: A with three edits

Keeps your structure and voice. Changes only:

1. In paragraph 3, replace the opening sentence with:
   > We then test whether the signal is used, not just present.

2. In paragraph 2, after the transfer sentence, add:
   > The signal is also present before we ask for it: read at the final token of the answer,
   > with no confidence question in play, it already separates correct from incorrect
   > attempts on MMLU-Pro (0.69, against 0.57 from the question alone).

3. Replace the closing sentence with:
   > Together, these models carry more information about their own errors than their stated
   > confidence conveys, and on Mistral that reporting channel depends on the direction we
   > identify.

---

## C — tighter, single block, ~4 lines shorter

Language models can give wrong answers with high confidence. Does that mean they lack
information about the mistake, or fail to express it? We read the model's internal state
directly. Across four open models and four domains (MMLU-Pro, MATH, GPQA-Diamond, and a
formally graded geometry task), a linear probe predicts correctness better than the model's
stated confidence in 12 of 16 settings (one tie; mean +0.09 AUROC), and the gap is largest
on MATH (+0.20), where wrong solutions stay fluent and well formed. The signal tracks the
particular attempt rather than the question: across repeated attempts at one question the
model's own P(True) falls toward chance while the probe holds, and a probe fitted after the
attempt reads at chance before it. It is present before we ask for it, already separating
correct from incorrect attempts at the final token of the answer (0.69 on MMLU-Pro, against
0.57 from the question alone). And the report depends on it: removing the direction, after
the answer is fixed, leaves stated confidence barely able to separate the model's successes
from its failures (0.84 → 0.56), while removing a matched random direction changes nothing;
amplifying it lowers confidence on wrong answers and halves calibration error. Models carry
more about their own errors than they say, and what they say depends on it.

**Also folds in** the cross-site result (a probe fitted after the attempt reads at chance
before it), which is currently only in the body.

---

## Numbers used, all from the recaptured Mistral cells

| claim | value | source |
|---|---|---|
| probe beats stated | 12 of 16, one tie, +0.09 | original matrix (not recomputable) |
| MATH gap | +0.20 | original matrix |
| answer-end, MMLU-Pro | 0.693 | `results/answersite/temporal_sites_mistral_mmlu_pro.json` |
| question-only, MMLU-Pro | 0.565 | same |
| post probe read at pre site | 0.490 | `tier1_review.json`, cross_site_post_to_pre |
| ablation | 0.836 → 0.564 | `results/causal/steer_ablation.json` |
| matched random ablation | 0.833 | same |
| calibration error | 0.337 → 0.186 | same |
