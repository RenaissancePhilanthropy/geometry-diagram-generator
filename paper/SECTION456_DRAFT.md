# Sections 4 to 6, for editing

Edit the prose directly. Each paragraph is one block. A bold lead is a subheading and stays bold. A `## ` line is a section heading. A numbered list (1., 2., 3.) becomes a compact list in the PDF. Keep [citation keys] and {ref:...} markers where they are; I map them back. Math stays as $...$. Table 2 is not shown here; it stays in the tex and {ref:tab:ablation} is its reference. Tell me to apply when done.

Synced from workshop_readable.tex at commit 2691511.

---

## Whether self-report depends on the residual signal

**Intervention.** A model could carry a perfect internal record of its errors and never consult it during self-report. The only way to find out is to change the record and watch the number. At the confidence token, after the answer is written so the answer cannot change, we scale the model's position along the correctness direction by a gain $g$. Gain 1 leaves the model untouched, gain 0 erases the per-attempt information, and gains 2 and 4 exaggerate it. We run this on Mistral and MATH, 150 held-out records, with a random direction of the same size as a control. {ref:tab:ablation} shows what the model wrote at each setting.

**Result on Mistral.** Erase the direction and self-report loses its information: AUROC falls from 0.84 to 0.56, a change of $-0.27$ $[-0.42, -0.12]$. Erase a random direction and nothing happens ($-0.00$ $[-0.03, +0.03]$). This is not generic damage. The output stays well formed, and confidence on wrong answers goes *up* to match right answers, so the model becomes uniformly sure rather than confused. Exaggerate the direction and confidence on wrong answers falls while right answers hold; calibration error halves, $0.34 \to 0.19$. Two checks say the effect is specific. The same intervention 30% of the way through the network does nothing, and a direction learned on MMLU-Pro, where surface features cannot explain the probe, still controls the MATH report ($0.88 \to 0.71$).

**Result on GLM.** GLM has the strongest signal in the study: within a question, the probe reads 0.87 while the model's own P(True) reads 0.53. Yet erasing the direction leaves self-report where it was, 0.76 before and after. GLM represents its errors more sharply than Mistral and reports them less. This is our cleanest case of represented but not reported, and it makes the causal result a fact about particular models, not models in general.

## The Jacobian lens

**A label-free check.** A trained probe might have overfit to our data. So we added an instrument that uses no correctness labels. The Jacobian lens [gurnee2026workspace] is fit on generic text and reads an activation for what it pushes the model to say next; we score each state by how far it leans toward "wrong" over "correct." On dense models the lens matches the probe: on Mistral it reads 0.82 on MATH and 0.75 on MMLU-Pro, against the probe's 0.83 and 0.75, with a clean input-layer control. Two instruments built from different evidence find the same direction, and because the lens reads through the model's own output pathway, that direction sits where it could influence what the model says.

**Where the lens fails.** The lens is a fixed dictionary from hidden-state directions to words, built once from generic text. On a dense model one dictionary is enough, because every input takes the same path to the output. GLM routes each input through a different subset of experts, and Qwen3.6 mixes two kinds of attention layers, so there is no single path and the lens averages many into a blur. The numbers show it: on GLM the lens's entries for "correct" and "wrong" point almost the same way, cosine 0.96, against 0.4 on a dense model, and it scores 0.31 there and 0.43 on Qwen3.6, while the probe still works on both. Swap Qwen3.6 for Qwen2.5-14B, same family but dense, and the lens jumps to 0.88. The signal is there in every model. A label-free reader only works where the architecture gives it one path to read.

## What this means

**Practical use.** Without an exact checker, the probe is the best per-attempt readout we found. Keeping the attempts it scores highest raises accuracy far more than keeping the ones the model is most confident in, and it works where the model's confidence is useless.

**Limitations.** A probe could be reading properties of failed output rather than a self-assessment; the surface baseline bounds this without closing it, most loosely on MATH, geometry ({ref:app:alternatives}), and GLM. Every number is a single seed. The before-asking test runs only on MMLU-Pro; on MATH the question alone already predicts correctness at 0.81. The causal result holds on Mistral and fails on GLM; Gemma-4 leaves too few failures to test, and the Qwen3.6 run did not finish in time. Whether preference tuning creates the gap is open; a base model would answer it.

**Takeaway.** These models carry information about their own errors that their self-report does not, and on one model self-report depends on it.
