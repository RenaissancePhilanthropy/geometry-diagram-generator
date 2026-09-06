# Introduction, for editing

Edit the prose below directly. Each paragraph is one block. Keep the `[citation keys]` where they are; I map them back to `\citep`. Tell me to apply when you are done.

Synced from `workshop_readable.tex` at commit `3a58855`.

---

A language model that is confidently wrong is a problem. Its stated confidence is a signal for deciding whether to trust its answer. This paper asks whether the model's activations carry a decodable signal of its answer's correctness.

Two things could be going on. Upon giving an incorrect answer and saying it has high confidence, either the model genuinely has no idea it might be wrong and is just blindly confident, or it deep down holds the error signal in its activations but not surfaced in its confidence report.

The first is a capability problem. The second is a reporting problem.

In this paper we aim to tell these two apart. We read the model's internal state directly with a linear detector, a *probe*, and compare what the probe finds to the model's reported confidence. A probe that reads correctness could be reading something duller: which questions are hard, features of the output text, or an artifact of being asked. The sections below rule those out in turn, then ask whether the report depends on the signal at all.

We say a fact is *represented* when a probe can read it from the model's state, and *reported* when it reaches the confidence number the model writes. The title's "knowing" is shorthand for a representation that is present, specific to the attempt, and, in at least one model, used by the report. We make no claim about awareness, and a probe alone could not support one.

Prior work has shown that a model's output probabilities are often better calibrated than its words [kadavath2022language], and that the truth of a given statement can be read from activations [azaria2023internal, burns2023discovering, marks2024geometry]. We apply those tools to the model's own attempts, and then intervene on the representation [zou2023representation] to ask whether the report depends on it.

----


A language model that is confidently wrong is a problem. Its stated confidence is a signal for deciding whether to trust its answer. This paper asks whether the model's activations contain the signal to know when it might be wrong.

Two things could be going on. Upon giving an incorrect answer and saying it has high confidence, either the model genuinely has no idea it might be wrong and is just blindly confident, or it deep down holds the error signal in its activations but unsurfaced to its confidence report. Hence it's either a capability problem or a reporting problem. 

In this paper we aim to tell these two apart. We read the model's internal state directly with a linear detector, a *probe*, and compare what the probe finds to the model's reported confidence. We say a fact is *represented* when a probe can read it from the model's state, and *reported* when it reaches the confidence number the model writes. The title's "knowing" is shorthand for a representation that is present, specific to the attempt, and, in at least one model, used by the report. We make no claim about awareness, and a probe alone could not support one.

Prior work has shown that a model's output probabilities are often better calibrated than its words [kadavath2022language], and that the truth of a given statement can be read from activations [azaria2023internal, burns2023discovering, marks2024geometry]. We apply those tools to the model's own attempts, and then intervene on the representation [zou2023representation] to ask whether the report depends on it.
