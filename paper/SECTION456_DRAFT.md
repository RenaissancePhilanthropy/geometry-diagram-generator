# Sections 4 to 6, for editing

Edit the prose directly. Each paragraph is one block. A bold lead is a subheading and stays bold. A `## ` line is a section heading. A numbered list (1., 2., 3.) becomes a compact list in the PDF. Keep [citation keys] and {ref:...} markers where they are; I map them back. Math stays as $...$. Table 2 is not shown here; it stays in the tex and {ref:tab:ablation} is its reference. Tell me to apply when done.

Synced from workshop_readable.tex at commit 2691511.

---

## Whether the report depends on it

**Present is not used.** A model could carry a perfect internal record of its errors and never consult it when writing the number. So we intervene. At the confidence token, after the answer is written so the answer itself cannot change, we scale the model's position along the correctness direction by a gain $g$. Gain 1 leaves the model untouched. Gain 0 erases the per-attempt information along that direction. Gains 2 and 4 exaggerate it. We run this on Mistral and MATH, and repeat it with a random direction of the same size as a control. {ref:tab:ablation} shows what the model wrote at each setting.

**On Mistral, the report depends on it.** Remove the direction ($g{=}0$) and stated confidence can no longer tell the model's successes from its failures: 0.84 drops to 0.56, a change of $-0.27$ $[-0.42, -0.12]$. Remove the random direction and nothing happens ($-0.00$ $[-0.03, +0.03]$). This does not look like generic damage. The output stays well formed, and confidence on wrong answers goes *up* until it matches confidence on right answers; the model becomes uniformly sure. Turn the direction up instead and confidence on wrong answers falls while right answers hold; calibration error halves, $0.34 \to 0.19$. The same intervention 30% of the way through the network does nothing, and a direction learned on MMLU-Pro, where surface features cannot explain the probe, still controls MATH's report ($0.88 \to 0.71$).

**On GLM, it does not.** GLM's signal is the strongest in the study: within a question, the probe reads 0.87 while the model's own words read 0.53. Yet removing the direction leaves stated confidence where it was, 0.76 before and after. GLM represents its errors more sharply than Mistral and reports them less. That is our cleanest case of represented but not reported, so the causal result is a fact about particular models, not models in general.

## A second witness

**A label-free instrument agrees.** A trained probe invites one more objection: it might have overfit to our data. So we added an instrument that uses no correctness labels. The Jacobian lens [gurnee2026workspace] is fit on generic text and reads an activation for what it pushes the model to say next; we score each stored state by how far it leans toward "wrong" over "correct."

On dense models the lens matches the probe. On Mistral it reads 0.82 on MATH and 0.75 on MMLU-Pro, against the probe's 0.83 and 0.75, with a clean input-layer control. Two instruments built from different evidence find the same direction, and because the lens reads through the model's own output pathway, that direction sits where it could influence what the model says.

**Where it fails, it shows why.** On GLM (mixture-of-experts) and Qwen3.6 (gated linear attention) the lens fails (0.31 and 0.43) while the probe still works. Its "correct" and "wrong" readouts collapse together, cosine 0.96 on MoE against 0.4 on dense. The lens averages one map over all inputs; these architectures route differently per input, so the average smears. Swap Qwen3.6 for dense Qwen2.5-14B, same family, and the lens jumps to 0.88.

Together: the archived matrix finds the signal in every model we tested; whether it reaches the report, and whether a label-free instrument can read it, varies by model.

## What this means

**For reliability.** Without an exact checker, the probe is the best per-attempt readout we found: keeping the attempts it scores highest raises accuracy far more than keeping the ones the model is most confident in, and it works where the model's confidence is useless.

**Limitations.** A probe could be reading properties of failed output rather than a dedicated self-assessment; the surface baseline bounds this without closing it, most loosely on MATH and geometry ({ref:app:alternatives}) and on GLM, where surface nearly matches the probe. Every number is a single seed. The before-asking test runs only on MMLU-Pro: on MATH the question alone already predicts correctness at 0.81, leaving no room to see what the attempt adds. The causal result holds on Mistral and fails on GLM; Gemma-4 passes 94% of MATH, leaving five failures, too few to test; the Qwen3.6 run did not finish in time. Whether preference tuning creates the gap is open; a base model would answer it.

**Takeaway.** These models carry information about their own errors that their stated confidence does not report, and on one model the report depends on it.
