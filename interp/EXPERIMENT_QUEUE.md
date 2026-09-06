# Experiment queue

Running list of experiments to add, ranked by how much they change what the paper can
claim per hour of GPU. Kept current as things land. Status values: `queued`,
`running`, `done`, `blocked`, `dropped`.

The framing these serve: **decode, locate, intervene, measure**. Three of those four are
supported today. The fourth is where most of the queue sits.

| # | experiment | serves | status | lands | where |
|---|---|---|---|---|---|
| 1 | Answer-end read site | decode | done: present on MMLU-Pro before the prompt | — | results/answersite |
| 2 | Confidence vs accuracy (monitor or driver) | measure | queued | ~2 h once a box frees | — |
| 3 | Ablation on GLM | intervene | done: clean null | — | results/causal_glm |
| 4 | Ablation on Gemma-4 | intervene | done: underpowered (5 wrong in eval) | — | results/causal_gemma4 |
| 5 | Ablation on Qwen3.6 | intervene | **running** | ~02:30 on the 7th | box B |
| 6 | Base-model arm | origin | queued | ~6 h + capture | needs a box |
| 7 | Multiple seeds | all | queued | recapture | needs a box |

Boxes, all RTX PRO 6000 Blackwell 97.9 GB, all with `~/.aws/config` and a live SSO login:

| | address | job |
|---|---|---|
| A | `ssh -p 15713 root@ssh2.vast.ai` | GLM then Gemma (`~/chain.log`) |
| B | `ssh -p 40021 root@98.86.102.84` | Qwen3.6 (`~/qwen.log`) |
| C | `ssh -p 29766 root@206.41.207.98` | answer-site (`~/answersite.log`) |

Clone needs `ssh -A`: the repo is private and the boxes authenticate through the
forwarded agent. Every run pushes its capture to S3 as soon as it exists, so no box
holds the only copy of anything.

---

## 1. Answer-end read site — highest priority

**The objection it kills.** Every probe number in the paper is read at the confidence
decision token, which the model reaches *after being asked to assess itself*. A reviewer
can say the correctness signal is manufactured by the introspection prompt rather than
carried from the work. The paper concedes exactly this in Limitations: the judgment is
"shown available when asked rather than formed while solving".

**The experiment.** Snapshot immediately after the model finishes its answer and before
the retrospective-confidence prompt is given, then train the identical correctness probe
there. Start with Mistral × MATH.

**Why it is cheap.** No generation. `meta.jsonl` already holds the full turn-2 context and
the full answer text, so each record is one teacher-forced forward pass. About 2,250
passes covers math, MMLU-Pro and GPQA.

**Already built.** `interp/capture_answer_site.py` (reads `answer_last` plus 16 evenly
spaced trajectory positions across the answer), `interp/analysis/answer_site_probe.py`,
orchestrated by `interp/overnight_answersite.sh`.

**What each outcome buys.** If the signal is already there at the answer's end, the claim
upgrades from "the model can assess itself when asked" to "the model tracks its own
correctness as a byproduct of working, and we are only reading it". That is the biggest
single lift available to the paper. If the signal is *absent* there and appears only at the
confidence token, that is also publishable and genuinely interesting: it would mean
self-assessment is computed on demand, which reframes the whole result rather than
sinking it.

**Note.** `overnight_answersite.sh` passes `--per-turn-think` for Mistral, which has no
thinking mode. Harmless but worth removing.

## 2. Confidence versus accuracy — the missing leg of "measure"

**The gap.** We measure effects on stated confidence exhaustively (AUROC, ECE). We have
never measured effects on *accuracy*. One unaudited July data point (GLM × GPQA, 0.38
steered against 0.41 baseline) suggested no lift, and that data died with the box.

**Why it matters.** "Steering changes what the model says but not whether it is right" is
the sharpest possible statement that this is a report channel and not a competence
channel. Without it, a reader can ask whether we have simply found a general
quality direction.

**Already built.** `interp/steer_correctness.py`, which steers the same diff-of-means
direction *during* answer generation, deliberately drops answer-invariance, and includes a
norm-matched random control. Its own docstring frames it as monitor versus driver.

**Note.** Answer-invariance in the confidence experiment is currently presented as a
methods aside. Under this framing it is a result and should be stated as one: steering
after the answer is written cannot change the answer, by construction.

## 3-5. Architectural replication of the ablation

Necessity and sufficiency currently rest on Mistral alone. GLM and Qwen are capturing now,
Gemma is queued. GLM is the interesting case: amplification was null there because its
stated confidence saturates near 100, leaving no headroom to push down, but ablation asks
the opposite question and can succeed where amplification could not.

## 6. Base-model arm

The only experiment that speaks to *what makes* a model self-aware, which is the question
the current abstract framing gestures at and the paper cannot answer. Same protocol on a
model before preference tuning. If the knowing-saying gap disappears, RLHF creates it.

## 7. Multiple seeds

Every number in the paper is a single seed. Not glamorous and it changes no conclusion,
but reviewers ask.

---

## Not queued, and why

**More records per cell.** 750 records over 150 questions gives a 95% interval of about
±0.09, and doubling it would reach ±0.06. That flips nothing. GPQA is a genuine null
rather than an underpowered one: it has the best class balance in the study and still
shows nothing. The one place the count genuinely hurts is geometry, where only 38 of 364
attempts were correct, and there the fix is prompts the model can sometimes solve rather
than more records at a 10% pass rate.

**A fifth benchmark for breadth.** MedQA needs no new code and would add coverage, but it
tests no new idea. Code with unit tests is the interesting version: it gives geometry's
exact judge-free labels without geometry's fatal flaw, since a subtly wrong function looks
exactly like a correct one. It would directly test the account we arrived at, that the
internal signal earns its keep precisely when failure is invisible. Needs a sandbox.
