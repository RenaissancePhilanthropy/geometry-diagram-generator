# Introduction, for editing

Edit the prose below directly. Each paragraph is one block. Keep the `[citation keys]` where they are; I map them back to `\citep`. Tell me to apply when you are done.

Synced from `workshop_readable.tex` at commit `3a58855`.

---

A language model that is confidently wrong is a problem. Its stated confidence is the one signal a downstream system has for deciding whether to trust an answer, and when that number is high on a wrong answer, nothing downstream can catch the error. A model that is sometimes wrong can be managed; a model that is wrong and sure cannot. This paper asks whether the model's activations carry what its stated confidence does not: a readable signal, at the moment the number is written, of whether the answer is right.

Two very different things could be going on inside such a model. Its internal state might carry no trace of the error, so that the confident number is the honest output of a system with no idea it has slipped. Or the error might be represented somewhere in the computation and simply fail to reach the number the model writes down. The first is a capability problem. The second is a reporting problem, and reporting problems are the kind an intervention can reach.

This paper is about telling those two apart. We read the model's internal state directly with a linear detector, a *probe*, and compare what the probe finds to what the model says. The question we keep asking is whether the difference between them is real, and each section below answers one way it could be an illusion.

We say a fact is *represented* when a probe can read it from the model's state, and *reported* when it reaches the confidence number the model writes. The title's "knowing" is shorthand for a representation that is present, specific to the attempt, and, in at least one model, used by the report. We make no claim about awareness, and a probe alone could not support one.

Prior work has shown that a model's output probabilities are often better calibrated than its words [kadavath2022language], and that the truth of a given statement can be read from activations [azaria2023internal, burns2023discovering, marks2024geometry]. We apply those tools to the model's own attempts, and then intervene on the representation [zou2023representation] to ask whether the report depends on it.
