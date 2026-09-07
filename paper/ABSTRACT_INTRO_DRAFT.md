# Abstract and introduction, for editing

Edit the prose directly. Each paragraph is one block. Keep [citation keys] and {ref:...} markers where they are. Math stays as $...$. Tell me to apply when done.

Synced from workshop_readable.tex at commit 69fe3af.

---

## Abstract

Language models are often confidently wrong. We ask whether a model's activations carry a better signal of its own errors than its stated confidence does. We test four open models on four tasks: MMLU-Pro, MATH, GPQA-Diamond, and a geometry task graded by a compiler. We put a linear probe on the hidden state to predict whether an answer is right. This probe was better than the model's stated confidence in 12 of 16 cases, by 0.09 AUROC on average. The gap is largest on MATH. The probe is not just detecting hard questions: it still works when the same question is attempted five times. The signal exists before the model is asked how confident it is. On Mistral, the model uses this signal when it reports confidence. When we erase the signal from the hidden state, the stated confidence no longer separates right answers from wrong ($0.84 \to 0.56$), while erasing a random direction did nothing. On GLM and Qwen3.6, erasing it changes nothing. In short, four open models carry more confidence signal about their own errors than they report. One of them uses that information when it self-reports. 

## Introduction

A language model that is confidently wrong is a problem. Its stated confidence, which we call its self-report, is a signal for deciding whether to trust its answer or not. This paper asks whether the model's activations contain a signal related to its confidence.

We have two hypothesis. Upon giving an incorrect answer and saying it has high confidence, either the model genuinely has no idea it might be wrong and is just blindly confident, or holds the error signal deep down in its activations but does not surface it in its self-report. Hence it is either a capability problem or a reporting problem.

In this paper we tell these two apart. We read the model's hidden state with a linear *probe* and compare what the probe finds to what the model reports. We say a fact is *represented* when a probe can read that fact from the model's state. We say a fact is *reported* when that fact reaches the confidence number the model writes. We refer to *knowing* as shorthand for a representation used by self-report. We make no claim about awareness. A probe alone could not support one.

Prior work reads the truth of a statement from activations [azaria2023internal, burns2023discovering, marks2024geometry], and reads a model's own errors from its hidden state better than its output reveals them [orgad2025llms, chwang2024androids]. A model's output probabilities are often better calibrated than its words [kadavath2022language], and asked confidence is known to be overconfident [lin2022teaching, tian2023just, xiong2024can]. Probes can latch onto confounds rather than the intended variable [levinstein2024still]. Intervening on a truth direction changes what a model says [li2023iti, zou2023representation]. We apply those tools to the model's own attempts, and then ask whether the self-report depends on the representation.
