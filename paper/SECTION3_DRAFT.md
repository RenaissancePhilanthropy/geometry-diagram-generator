# Section 3, for editing

Edit the prose directly. Each paragraph is one block. A bold lead is a subheading and stays bold. A numbered list (1., 2., 3.) becomes a compact list in the PDF. Keep [citation keys] and {ref:...} markers where they are; I map them back. Math stays as $...$. Table 1 is not shown here; it stays in the tex and {ref:tab:transfer} is its reference. Tell me to apply when done.

Synced from workshop_readable.tex at commit 68b2065.

---

## What the signal is

**It is about this attempt, not this question.** A probe that outranks stated confidence could still be doing something dull: learning which questions are hard. Hard questions fail more often, so a difficulty detector would predict correctness without reading the attempt at all.

Two tests argue against it. First, hold the question fixed. Across five attempts at one question, difficulty cannot vary, yet the probe still separates the successes from the failures (0.72 to 0.74 in representative cells) while the model's own P(True), its probability of answering "True" when asked whether it was right, falls to near chance (0.47 to 0.59). Second, test the direction itself. Before the attempt, at the last token of the question, the model's state is identical across all five attempts: it can encode difficulty and nothing else. A probe trained after the attempt and read there gives 0.49 on MMLU-Pro, chance, against 0.75 at its own site. The direction that separates good attempts from bad ones does not exist until the model has tried. Geometry is the boundary case: there the pre-attempt state already predicts failure, so that cell is mostly difficulty.

**It is there before we ask.** That leaves a subtler worry. Every read so far came from a token the model reaches after being asked to assess itself. Perhaps the signal is not carried from the work at all; perhaps the question manufactures it. So we read the state at the last token of the answer instead, before any confidence question exists. On MMLU-Pro, where the model cannot see failure coming (0.57 from the question alone), correctness is already readable at 0.69 the moment it stops writing. Being asked sharpens it to 0.77. The signal is made by working, and the prompt clarifies rather than creates it. MATH cannot run this test, because its question-only read is already 0.81.

**It is not tied to one subject.** {ref:tab:transfer} trains a probe on one domain and tests it on each of the others. On Mistral it keeps about 90% of its lift above chance (0.69 off the diagonal against 0.71 on it), and the original matrix showed the same pattern in every model. The one exception is instructive: on Gemma-4, probes trained on geometry fail elsewhere (0.31 to 0.39) while probes trained elsewhere work on geometry (about 0.70). A probe trained on the one generative task can learn features specific to it.
