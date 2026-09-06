# Section 2, for editing

Edit the prose directly. Each paragraph is one block; a bold lead like **Prompting structure.** Every attempt takes three turns.

1. The model is shown the question and asked, before answering, how confident it is, from 0 to 100, that it will get it right.
2. It answers.
3. It is asked how confident it is that the answer it just gave is correct.

A grader scores the attempt and never tells the model, so any movement in stated confidence is the model's own.

**The probe.** At the moment the model is about to write its confidence digit, we record the number and the hidden state behind it, a vector of a few thousand numbers. On that vector we train the probe: a logistic regression that predicts whether the attempt was correct. It is always tested on questions it never saw in training, and always read at one depth fixed in advance, 70% of the way through the network. We score every readout with AUROC, the chance that a random correct attempt outranks a random wrong one, where 0.5 is useless and 1.0 is perfect.

**The state carries more than the report.** The probe outranks the model's own stated confidence in **12 of 16** cells, one tie, by a mean of $+0.09$ AUROC ({ref:app:cells}). The gap is widest on MATH, $+0.20$, and MATH is also where the report goes most wrong. On the Mistral MATH cell, with the grade never revealed, the model raises its confidence after attempting, and raises it *more* on the attempts it got wrong ($+22$) than on the ones it got right ($+16$). The probe on those same records reads 0.83. The number moves away from the truth while the state tracks it.

**Why MATH.** A wrong derivation ends in a clean boxed answer that reads like a correct solution; {ref:app:worked} follows one, a single wrong subtraction after which the model *raises* its confidence. Its length and shape still carry signal (a surface baseline reaches 0.74), but the model's stated confidence does not use it, and the probe reads 0.83, $+0.07$ over surface. Geometry is the opposite: a failed construction usually does not compile, and there the surface baseline does as well as the probe.

**Controls.** The token we read is identical in every record, so at the input layer the probe sits at exactly 0.5 and anything it finds deeper was computed during the attempt. A within-question comparison holds difficulty fixed. For time, the controls below were run on Mistral only. Its four cells reproduce the headline, with a smaller margin over the surface baseline ($+0.21$ on MMLU-Pro, $+0.07$ on MATH, $+0.05$ on GPQA, where neither reads far above chance, and $-0.11$ on geometry).
