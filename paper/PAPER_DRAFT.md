# Full paper body, for editing

Edit the prose directly. `## ` is a section heading; a bold lead is a subheading. A numbered list (1., 2., 3.) becomes a compact list. Keep [citation keys] and {ref:...} markers where they are; I map them back. Math stays as $...$. Tables are not shown; the `{{TABLE:...}}` lines mark where each sits and must stay. Do not edit the appendix here; tell me and I will export it separately. Tell me to apply when done.

Synced from workshop_readable.tex after the style pass (commit 49fb06c plus this pass).

---

## Abstract

Language models are often confidently wrong. We ask whether a model's activations carry a better signal of its own errors than its stated confidence does. We test four open models on four tasks: MMLU-Pro, MATH, GPQA-Diamond, and a geometry task graded by a compiler. A linear probe on the hidden state predicts whether an answer is right better than the model's stated confidence in 12 of 16 cases, by 0.09 AUROC on average. The gap is largest on MATH. The probe is not just detecting hard questions: it still works when the same question is attempted five times. The signal exists before the model is asked how confident it is. On Mistral, the model uses this signal when it reports confidence: erase it from the hidden state and stated confidence no longer separates right answers from wrong ($0.84 \to 0.56$), while erasing a random direction does nothing. On GLM, erasing it changes nothing. In short, these models carry more information about their own errors than they report, and at least one of them uses that information when it reports.

## Introduction

A language model that is confidently wrong is a problem. Its stated confidence, which we call its self-report, is a signal for deciding whether to trust its answer. This paper asks whether the model's activations contain a signal of when it is wrong.

Two things could be going on. Upon giving an incorrect answer and saying it has high confidence, either the model genuinely has no idea it might be wrong and is just blindly confident, or it deep down holds the error signal in its activations but does not surface it in its self-report. Hence it is either a capability problem or a reporting problem.

In this paper we tell these two apart. We read the model's hidden state with a linear *probe* and compare what the probe finds to what the model reports. We say a fact is *represented* when a probe can read that fact from the model's state. We say a fact is *reported* when that fact reaches the confidence number the model writes. We refer to "knowing" as shorthand for a representation that is present, specific to the attempt, and, in at least one model, used by the self-report. We make no claim about awareness. A probe alone could not support one.

Prior work reads the truth of a statement from activations [azaria2023internal, burns2023discovering, marks2024geometry], and reads a model's own errors from its hidden state better than its output reveals them [orgad2025llms, chwang2024androids]. A model's output probabilities are often better calibrated than its words [kadavath2022language], and asked confidence is known to be overconfident [lin2022teaching, tian2023just, xiong2024can]. Probes can latch onto confounds rather than the intended variable [levinstein2024still], which is why {ref:sec:what} exists. Intervening on a truth direction changes what a model says [li2023iti, zou2023representation]. We apply those tools to the model's own attempts, and then ask whether the self-report depends on the representation.

## Reading the state

**Models and tasks.** We test four open models of three architectures: Mistral-Small-24B (dense), Qwen3.6-27B (gated linear attention interleaved with full attention), and GLM-4.7-Flash and Gemma-4-26B (mixture of experts). Each answers 150 questions, five times each, in four domains: MMLU-Pro, MATH, GPQA-Diamond, and GeoGenBench. GeoGenBench is a geometry task. The model writes a construction and a compiler checks it against a formal specification, so its labels need no judge. In a pre-registered check of 200 attempts by two trained raters, the compiler never failed a correct construction. That is 16 cells of about 750 attempts each.

**Prompting structure.**

1. The model is shown the question and asked, before answering, how confident it is, from 0 to 100, that it will get it right.
2. It answers.
3. It is asked how confident it is that the answer it just gave is correct.

**The probe.** At the moment the model is about to write its confidence digit, we record the number and the residual-stream hidden state at that token (2,048 to 5,120 dimensions, depending on the model). The probe is a linear classifier on that vector: features are standardized, reduced to 50 principal components, and fed to an L2-regularized logistic regression that predicts whether the attempt was correct. We fit it with five-fold cross-validation grouped by question, so all five attempts at a question fall in the same fold and the probe is always scored on questions it never saw. The read depth is fixed in advance at 70% of the network (layer 28 of 40 for Mistral, 33 of 47 for GLM, 21 of 30 for Gemma-4, 45 of 64 for Qwen3.6). Every readout is scored with AUROC.

**The activation state carries more than self-report.** The probe beats the model's self-report in **12 of 16** cells, with one tie. The mean gain is $+0.09$ AUROC ({ref:app:cells}). The gap is largest on MATH, at $+0.20$. Mistral on MATH is a good example of what this looks like. The model is never told whether it got the answer right. Yet after attempting, it raises its confidence, and it raises it more on the attempts it got wrong ($+22$ points) than on the ones it got right ($+16$ points). The probe on the same records reads 0.83. The state tracks correctness better than the self-report does.

**Why MATH.** On MATH, right and wrong answers have the same shape. Both are a chain of steps ending in a boxed result, so the model cannot tell from the look of its answer whether it went wrong. {ref:app:worked} follows one attempt where a single wrong subtraction leads to a wrong answer, and the model then raises its confidence. Shape still carries a little signal. A baseline classifier that sees only surface features of the answer text, such as its length and line count, reaches 0.74, but the probe reaches 0.83. Geometry is the opposite case. A failed construction usually does not compile, so the failure is visible in the answer itself, and there the surface baseline does as well as the probe. The internal signal helps most where the failure is invisible from outside.

**Controls.** Three things could make a probe look better than it is; the next section tests each. It could be reading how hard the question is rather than the attempt, so we compare attempts within one question. It could be reading the shape of the output, so we compare it with the surface baseline in every cell; on Mistral, adding the probe to the surface features raises AUROC by $+0.21$ on MMLU-Pro, $+0.07$ on MATH, $+0.05$ on GPQA, and $-0.11$ on geometry. And it could be reading something that was there before the attempt, so we check the input layer, where the token is identical in every record and the probe sits at exactly 0.5. These controls were run on Mistral only, for time. Its four cells reproduce the headline.

## What the signal is

**Difficulty control.** A probe that beats self-report could be doing something simpler. It could be learning which questions are hard. Hard questions fail more often, so a difficulty detector would predict correctness without reading the attempt. We run two checks.

First, hold the question fixed. Each question is attempted five times, so within one question, difficulty cannot vary. The probe still separates the successful attempts from the failed ones (0.72 to 0.74 in the cells of {ref:tab:knowing}). The model's own P(True), its probability of answering "True" when asked whether it was right, drops to near chance (0.47 to 0.59).

Second, test where the probe's direction lives. The probe is a direction in the hidden state, and we can ask when that direction appears. Before the attempt, at the last token of the question, the model's state is the same across all five attempts. It can encode difficulty and nothing else. A probe trained after the attempt and read at that point scores 0.49 on MMLU-Pro, which is chance, against 0.75 at its own site. The direction that separates good attempts from bad ones does not exist until the model has tried. Geometry is the exception. There the pre-attempt state already predicts failure, so that cell is mostly difficulty.

**Reading before the question.** A subtler worry. Every read so far came after the model was asked to assess itself. Maybe the question creates the signal rather than reveals it. So we read the state at the last token of the answer, before any confidence question exists. On MMLU-Pro, correctness is readable there at 0.69. From the question alone it is 0.57, so the model cannot see failure coming. Asking the model to self-assess sharpens the signal to 0.77.

**Transfer across domains.** {ref:tab:transfer} trains a probe on one domain and tests it on each of the others. On Mistral it keeps about 90% of its lift above chance (0.69 off the diagonal against 0.71 on it). The full four-model matrix showed the same pattern. The one exception is Gemma-4. There, probes trained on geometry fail elsewhere (0.31 to 0.39), while probes trained elsewhere work on geometry (about 0.70). A probe trained on the one generative task can learn features specific to it.

{{TABLE:tab:transfer}}

## Whether self-report depends on the residual signal

**Intervention.** A model could carry a perfect internal record of its errors and never consult it during self-report. The only way to find out is to change the record and watch the number. At the confidence token, after the answer is written so the answer cannot change, we scale the model's position along the correctness direction by a gain $g$. Gain 1 leaves the model untouched, gain 0 erases the per-attempt information, and gains 2 and 4 exaggerate it. We run this on Mistral and MATH, 150 held-out records, with a random direction of the same size as a control. {ref:tab:ablation} shows what the model wrote at each setting.

{{TABLE:tab:ablation}}

**Result on Mistral.** Erase the direction and self-report loses its information. Its AUROC falls from 0.84 to 0.56 (95% bootstrap interval on the change, $-0.42$ to $-0.12$). Erase a random direction and nothing happens (interval $-0.03$ to $+0.03$). This is not generic damage. The output stays well formed. Confidence on wrong answers goes *up* to match right answers, so the model becomes uniformly sure rather than confused. Amplify the direction and the opposite happens: confidence on wrong answers falls while right answers hold, and expected calibration error halves, $0.34 \to 0.19$. Two checks say the effect is specific. The same intervention 30% of the way through the network does nothing. A direction learned on MMLU-Pro, where surface features cannot explain the probe, still controls the MATH report ($0.88 \to 0.71$).

**Result on GLM.** GLM has the strongest signal in the study: within a question on MATH, the probe reads 0.87 while the model's own P(True) reads 0.53. Yet erasing the direction leaves self-report where it was, 0.76 before and after. GLM represents its errors more sharply than Mistral and reports them less. This is our cleanest case of represented but not reported, and it makes the causal result a fact about particular models, not models in general.

## The Jacobian lens

**A label-free check.** A trained probe might have overfit to our data. So we add an instrument that uses no correctness labels. The Jacobian lens [gurnee2026workspace] is fit on generic text. It reads an activation for what it pushes the model to say next. We score each state by how far it leans toward "wrong" over "correct." On dense models the lens matches the probe. On Mistral it reads 0.82 on MATH and 0.75 on MMLU-Pro, against the probe's 0.83 and 0.75, and it reads 0.5 at the input layer, as it should. Two instruments built from different evidence find the same direction. And because the lens reads through the model's own output pathway, that direction sits where it could influence what the model says.

**Where the lens fails.** The lens is a fixed dictionary from hidden-state directions to words, built once from generic text. On a dense model one dictionary is enough, because every input takes the same path to the output. GLM routes each input through a different subset of experts, and Qwen3.6 mixes two kinds of attention layers, so there is no single path and the lens averages many into a blur. The numbers show it: on GLM the lens's entries for "correct" and "wrong" point almost the same way, cosine 0.96, against 0.40 on a dense model, and it scores 0.31 there and 0.43 on Qwen3.6, while the probe still works on both. Swap Qwen3.6 for Qwen2.5-14B, same family but dense, and the lens jumps to 0.88. The signal is there in every model. A label-free reader works only where the architecture gives it one path.

## What this means

**Practical use.** Without an exact checker, the probe is the best per-attempt readout we found. Keeping the attempts it scores highest raises accuracy more than keeping the ones the model is most confident in. It works where the model's confidence is useless.

**Limitations.** A probe could be reading properties of failed output rather than a self-assessment. The surface baseline bounds this without closing it, most loosely on MATH, geometry ({ref:app:alternatives}), and GLM. Every number is a single seed. The before-asking test runs only on MMLU-Pro, because on MATH the question alone already predicts correctness at 0.79. The causal result holds on Mistral and fails on GLM. Gemma-4 leaves too few failures to test. The Qwen3.6 run did not finish in time. Whether preference tuning creates the gap is open. A base model would answer it.

**Takeaway.** These models carry information about their own errors that their self-report does not. On one model, self-report depends on it.
