# GeoGen Datasheet

Following Gebru et al., "Datasheets for Datasets" (2018). Required for NeurIPS Datasets & Benchmarks submissions.

## Motivation

**For what purpose was the dataset created?**
GeoGen was created to fill a gap in the LLM evaluation landscape: existing geometry benchmarks (Geometry3K, GeoQA, MathVista, GeoEval, etc.) measure whether models can *answer questions about given diagrams*; none test whether models can *produce* a correct geometry diagram from a textual description. As frontier LLMs are increasingly deployed to author worksheets, slides, and technical illustrations, generative geometric capability is a deployed task that lacks a public benchmark with rigorous, automatic grading.

**Who created the dataset and on behalf of which entity?**
[redacted for review]; on behalf of [redacted].

**Who funded the creation of the dataset?**
[redacted for review].

## Composition

**What do the instances represent?**
Each instance is a *geometry-diagram-generation task*: a natural-language prompt asking a model to draw a specific geometric figure, paired with (a) machine-checkable expected geometric properties, (b) required textual labels, and (c) optional structural and follow-up checks.

**How many instances total?**
**801** scenarios:
- 600 from the templated split (procedurally generated; 200 per tier)
- 201 from the curriculum split (LLM-extracted from K-12 textbooks)

**Does the dataset contain all possible instances or a sample?**
Templated: deterministic enumeration of (template × label set × numeric parameter × phrasing-opener); we cap at 200/tier via round-robin to keep the dataset tractable, but the engine can generate ~766 raw scenarios pre-cap.
Curriculum: a sample drawn by an LLM from textbook chapters; not exhaustive coverage of K-12 geometry.

**What data does each instance consist of?**
Each scenario is a YAML object with fields:
- `id` (str): unique identifier
- `tier` (int 1-3): difficulty tier
- `tags` (list[str]): topic tags
- `prompt` (str): the natural-language request
- `expected_properties` (list[dict]): property-list, each with `{name, type, args}` from the 20-type vocabulary in Section 3
- `required_labels` (list[str]): point names that must appear in TikZ output
- `required_canvas` (dict): optional Cartesian-grid / axes requirements
- `expected_points` (dict[str, [x,y]]): optional exact-coordinate matches with tolerance
- `coordinate_tolerance` (float): per-scenario tolerance override
- `structural_checks` (list[dict]): e.g., `polygon_count`
- `queries` (list[dict]): optional follow-up questions for query-eval phase

**Is there a label or target?**
The label *is* the property list — automatic verification is the grading signal.

**Is any information missing from individual instances?**
For curriculum scenarios, the property list is LLM-generated and not provably complete (see Section 4 completeness analysis). For some instances we explicitly mark properties as `(skipped: rendering-only check)` — these contribute to soft-pass not strict-pass.

**Are relationships between individual instances explicit?**
Templates are explicit: every templated scenario's `id` encodes its template, label set, and numeric parameters (`tpl-t2-alt-EFG-H-60-70` = tier-2 altitude template, vertices E/F/G + foot H, angles 60° and 70°). This makes it trivial to compute leave-one-template-out splits or to filter by topic.

**Are there recommended data splits?**
- **Templated split (provably-correct ground truth)**: 600 scenarios. Recommended for headline metrics.
- **Curriculum split (broader topic coverage)**: 201 scenarios. Recommended as a robustness check.
- **Per-tier**: tier-1 / tier-2 / tier-3 splits for difficulty-stratified analysis.
- **Held-out test (planned)**: a parameter-rolled re-generation of templates with different label sets / numeric ranges, withheld until evaluation, to defend against contamination.

**Are there errors, sources of noise, or redundancies?**
Known issues (also documented in Section 3.9):
- `point_on_segment` checks collinearity, not segment bounds.
- `mark_present` and `label_present` are TikZ-source string checks, not render-aware.
- `angle_equal` is supported in scenario YAML but currently not implemented in the predicate evaluator (returns "skipped"). **Hardening pass implements it.**
- Tolerance is fixed at 5×10⁻³ for SymPy checks and 10⁻² for TikZ-string checks.

The hardening pass (Section 4.5) reduces these issues; we report pre/post numbers in Appendix B.

**Is the dataset self-contained?**
Yes. The YAML files plus the verification toolkit (`evals/sympy_checks.py`, `util/tikz_geometry.py`) are sufficient to run the benchmark. The only external dependencies are: a working SymPy install, and either a local LuaLaTeX install or our published Docker container `tikz-renderer` (the latter is part of the release).

**Does the dataset contain confidential information?**
No.

**Does the dataset contain data that might be considered offensive, insulting, or harmful?**
No. All scenarios are mathematically benign K-12 geometry constructions.

**Does the dataset relate to people?**
No.

## Collection process

**How was the data acquired?**
- *Templated*: each scenario is generated by a Python function (one per template). The generator takes a fixed seed and is deterministic.
- *Curriculum*: extracted from publicly-available K-12 textbook chapters via `curriculum/generate_prompts.py` using an LLM (Sonnet) to convert curriculum descriptions into student-style diagram requests. We have intellectual-property attribution of the source textbooks; we release only the generated prompts and our property annotations.

**What mechanisms or procedures were used to collect the data?**
Templated: programmatic enumeration. Curriculum: LLM extraction with manual spot-check audit on a 50-sample subset.

**If the dataset is a sample from a larger set, what was the sampling strategy?**
Templated: round-robin per-template within tier, capped at 200/tier.
Curriculum: LLM-driven sampling weighted by topic coverage; not random.

**Who was involved in the data collection process and how were they compensated?**
The templated scenarios were authored by the paper authors. The curriculum extraction was performed by an LLM under author supervision; no human annotators beyond the human-correlation study (planned) were paid for data creation.

**Over what timeframe was the data collected?**
Templated: April 2026. Curriculum: April 2026.

**Were any ethical review processes conducted?**
Not applicable — no human subjects, no personally identifiable information.

## Preprocessing / cleaning / labeling

**Was any preprocessing/cleaning/labeling of the data done?**
- Templated: no preprocessing; scenarios are emitted directly from generator code.
- Curriculum: LLM-extracted scenarios were filtered by `evals/scenarios.py::_validate_scenarios` to enforce schema correctness; ~5% were rejected at this stage due to malformed property args.

**Was the "raw" data saved?**
Yes — `evals/generate_scenarios.py` is the raw template specification (and is part of the release).

## Uses

**Has the dataset been used for any tasks already?**
- Internal pilot leaderboard across [3-6] frontier models × 3 strategies (results in Section 6).
- Calibration of the verification tolerance (`5×10⁻³`).

**Is there a repository that links to any or all papers or systems that use the dataset?**
[Will be created at submission time as a HuggingFace dataset card + leaderboard page.]

**What other tasks could the dataset be used for?**
- Few-shot prompt engineering research: which in-context examples best help models produce correct geometry?
- Visual reasoning evaluation as image-to-text: take rendered SVGs as input and ask models to verify properties (inverse direction).
- Curriculum learning for math-tutor agents.
- Evaluating tool-use loops where the model has access to a render-and-check tool.

**Is there anything about the composition of the dataset or the way it was collected and preprocessed that might impact future uses?**
- Templated scenarios use only Latin letters A-Z for vertex labels. Models trained predominantly on Greek/Cyrillic geometry notation may underperform.
- All prompts are in English. We have not evaluated cross-lingual generalization.
- The verification toolkit assumes 2D plane geometry; 3D solid scenarios from the curriculum split are not symbolically verifiable today.
- The fixed 5×10⁻³ tolerance was tuned for human-rating agreement on a small sample. Per-check-type tolerances may be more accurate.

**Are there tasks for which the dataset should not be used?**
Not for evaluating image-to-text models (it's text-to-diagram). Not for evaluating models on solid/3D geometry without significant verifier extension.

## Distribution

**Will the dataset be distributed to third parties?**
Yes — public release on HuggingFace Datasets and a project GitHub repository.

**How will it be distributed?**
- HuggingFace Datasets: the YAML files + a Python loader.
- GitHub: full source including the generator, verifier, renderer Docker image build, and reference strategies.

**When will the dataset be distributed?**
At paper-submission time.

**Will the dataset be distributed under a copyright or other intellectual property license?**
- Generated scenarios + verifier code: MIT License.
- Curriculum scenarios are derived works of textbook content; we license only our property annotations under MIT and provide attribution per source.

**Have any third parties imposed IP-based or other restrictions on the data associated with the instances?**
The K-12 textbook source for the curriculum split has its own copyright; we use it for educational fair-use under §107 of the US Copyright Act and release only our derivative prompts + verification annotations.

**Do any export controls or other regulatory restrictions apply to the dataset or to individual instances?**
No.

## Maintenance

**Who will be supporting/hosting/maintaining the dataset?**
[Author group; details at submission time.]

**How can the owner/curator/manager of the dataset be contacted?**
[Email at submission time.]

**Is there an erratum?**
A `CHANGELOG.md` will track version increments and any rolled-back scenarios. Each release is git-tagged.

**Will the dataset be updated?**
Yes — we plan a v1.0 at submission, v1.1 with the hardening pass, and a v2.0 if topic-breadth (3D, transformations, proofs) is added.

**If the dataset relates to people, are there applicable limits on the retention of the data associated with the instances?**
N/A (no people).

**Will older versions of the dataset continue to be supported/hosted/maintained?**
Yes — all versions remain available under their git tags.

**If others want to extend/augment/build on/contribute to the dataset, is there a mechanism for them to do so?**
A `CONTRIBUTING.md` will document the process for submitting new templates. The template-engine architecture (one Python function per template, one YAML output per scenario) makes contribution straightforward, and `evals/scenarios.py::_validate_scenarios` provides automatic schema enforcement.
