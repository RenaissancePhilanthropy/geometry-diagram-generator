# Section 3, for editing

Edit the prose directly. Each paragraph is one block. A bold lead is a subheading and stays bold. A numbered list (1., 2., 3.) becomes a compact list in the PDF. Keep [citation keys] and {ref:...} markers where they are; I map them back. Math stays as $...$. Table 1 is not shown here; it stays in the tex and {ref:tab:transfer} is its reference. Tell me to apply when done.

Synced from workshop_readable.tex at commit 68b2065.

---

## What the signal is

**Difficulty control.** A probe that beats stated confidence could be doing something simpler. It could be learning which questions are hard. Hard questions fail more often, so a difficulty detector would predict correctness without reading the attempt. We run two checks.

First, hold the question fixed. Each question is attempted five times, so within one question, difficulty cannot vary. The probe still separates the successful attempts from the failed ones (0.72 to 0.74 in representative cells). The model's own P(True), its probability of answering "True" when asked whether it was right, drops to near chance (0.47 to 0.59).

Second, test where the direction lives. Before the attempt, at the last token of the question, the model's state is the same across all five attempts. It can encode difficulty and nothing else. A probe trained after the attempt and read at that point scores 0.49 on MMLU-Pro, which is chance, against 0.75 at its own site. The direction that separates good attempts from bad ones does not exist until the model has tried. Geometry is the exception. There the pre-attempt state already predicts failure, so that cell is mostly difficulty.

**Reading before the question.** There is a subtler worry. Every read so far came from a token the model reaches after being asked to assess itself. Maybe the question creates the signal rather than reveals it. So we also read the state at the last token of the answer, before any confidence question exists. On MMLU-Pro, correctness is already readable there at 0.69. From the question alone it is 0.57, so the model cannot see failure coming. Asking the model to self-assess sharpens the signal to 0.77.

**Transfer across domains.** {ref:tab:transfer} trains a probe on one domain and tests it on each of the others. On Mistral it keeps about 90% of its lift above chance (0.69 off the diagonal against 0.71 on it). The original matrix showed the same pattern in every model. The one exception is Gemma-4. There, probes trained on geometry fail elsewhere (0.31 to 0.39), while probes trained elsewhere work on geometry (about 0.70). A probe trained on the one generative task can learn features specific to it.
