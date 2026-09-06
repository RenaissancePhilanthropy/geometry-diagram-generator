# Section 2, for editing

Edit the prose directly. Each paragraph is one block. A bold lead such as the first words of the probe paragraph is a subheading and stays bold. A numbered list (1., 2., 3.) becomes a compact list in the PDF. Keep [citation keys] and {ref:...} markers where they are; I map them back. Math stays as $...$. Tell me to apply when done.

Synced from workshop_readable.tex at commit c24b1f2, plus the numbered prompting structure.

---

## Reading the state

**Models and tasks.** We tested four open models built in four different ways: Mistral-Small-24B (dense), Qwen3.6-27B (gated linear attention interleaved with full attention), and GLM-4.7-Flash and Gemma-4-26B (mixture of experts). Each answered 150 questions, five times each, in four domains: MMLU-Pro, MATH, GPQA-Diamond, and GeoGenBench, a geometry task in which the model writes a construction and a compiler checks it against a formal specification, so its labels need no judge; in a pre-registered check of 200 attempts by two trained raters, the compiler never failed a correct construction. That is 16 cells of about 750 attempts each.

**Prompting structure.**

1. The model is shown the question and asked, before answering, how confident it is, from 0 to 100, that it will get it right.
2. It answers.
3. It is asked how confident it is that the answer it just gave is correct.

**The probe.** At the moment the model is about to write its confidence digit, we record the number and the residual-stream hidden state at that token (2,048 to 5,120 dimensions, depending on the model). The probe is a linear classifier on that vector: features are standardized, reduced to 50 principal components, and fed to an L2-regularized logistic regression that predicts whether the attempt was correct. We fit it with five-fold cross-validation grouped by question, so all five attempts at a question fall in the same fold and the probe is always scored on questions it never saw. The read depth is fixed in advance at 70% of the network (layer 28 of 40 for Mistral, 33 of 47 for GLM, 21 of 30 for Gemma, 45 of 64 for Qwen3.6). Every readout is scored with AUROC.

**The activation state carries more than self-report.** The probe beats the model's stated confidence in **12 of 16** cells, with one tie. The mean gain is $+0.09$ AUROC ({ref:app:cells}). The gap is largest on MATH, at $+0.20$. Mistral on MATH is a good example of what this looks like. The model is never told whether it got the answer right. Yet after attempting, it raises its confidence, and it raises it more on the attempts it got wrong ($+22$ points) than on the ones it got right ($+16$ points). The probe on the same records reads 0.83. The state tracks correctness better than the self-report does.

**Why MATH.** On MATH, right and wrong answers have the same shape. Both are a chain of steps ending in a boxed result, so the model cannot tell from the look of its answer whether it went wrong. {ref:app:worked} follows one attempt where a single wrong subtraction leads to a wrong answer, and the model then raises its confidence. Shape still carries a little signal. A baseline classifier that sees only surface features of the answer text, such as its length and line count, reaches 0.74, but the probe reaches 0.83. Geometry is the opposite case. A failed construction usually does not compile, so the failure is visible in the answer itself, and there the surface baseline does as well as the probe. The internal signal matters most where the failure is invisible from outside.

**Controls.** The token we read is identical in every record, so at the input layer the probe sits at exactly 0.5 and anything it finds deeper was computed during the attempt. A within-question comparison holds difficulty fixed. For time, the controls below were run on Mistral only. Its four cells reproduce the headline, with a smaller margin over the surface baseline ($+0.21$ on MMLU-Pro, $+0.07$ on MATH, $+0.05$ on GPQA, where neither reads far above chance, and $-0.11$ on geometry).
