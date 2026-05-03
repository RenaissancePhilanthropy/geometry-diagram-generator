---
license: mit
language:
  - en
pretty_name: GeoGenBench
size_categories:
  - n<1K
task_categories:
  - text-generation
  - other
task_ids:
  - language-modeling
tags:
  - geometry
  - diagram-generation
  - tikz
  - evaluation-benchmark
  - symbolic-verification
  - k12-mathematics
  - generative-reasoning
configs:
  - config_name: templated
    data_files: bench_generated.jsonl
  - config_name: curriculum
    data_files: bench_curriculum.jsonl
---

# GeoGenBench

GeoGenBench is an automatically-verifiable benchmark of **generative geometric reasoning**: 801 natural-language prompts asking a language model to produce a TikZ source string that renders a specific 2D plane-geometry construction, paired with machine-checkable expected geometric properties drawn from a fixed 17-predicate vocabulary.

It is the first instantiation of the **GeoGen** methodology, which combines:
1. **Procedural co-generation** of prompts and rubrics from shared source code, eliminating drift between question and grading criteria.
2. **Render-then-symbolic-verify**: the model's TikZ output is compiled to SymPy geometry objects against which declarative predicates are decided in microseconds — no LLM judge, no human grading.

## Splits

| Split | File | # | Tier 1 | Tier 2 | Tier 3 | Avg # props |
|---|---|---:|---:|---:|---:|---:|
| `templated` | `bench_generated.jsonl` | 600 | 200 | 200 | 200 | 3.2 |
| `curriculum` | `bench_curriculum.jsonl` | 201 | 36 | 128 | 37 | 6.0 |
| **Total** | | **801** | **236** | **328** | **237** | — |

- **Templated** (provably-correct ground truth): 600 scenarios from 30 procedurally-generated construction templates (right/equilateral/isosceles triangles, polygons, segment+midpoint, parallel/perpendicular constructions, circle constructions including incircle/circumcircle/tangent, altitude/median/angle-bisector, and composed constructions). Each scenario's prose and property list are emitted by the **same** Python function, so they cannot drift.
- **Curriculum** (broader topic coverage): 201 scenarios LLM-extracted from K-12 geometry textbooks under author supervision; covers topics the templates do not (3D solids, transformations, coordinate-overlay constructions, multi-step proofs requiring auxiliary lines), at the cost of LLM-authored ground truth that is spot-audited but not provably correct.

Headline benchmark numbers in the accompanying paper are reported **templated-only**; curriculum metrics are reported as a robustness check.

## Record schema

Each JSONL line is one scenario:

```json
{
  "id": "tpl-t2-alt-EFG-H-60-70",
  "prompt": "Draw an acute triangle EFG ... altitude from G meeting EF at H ...",
  "tier": 2,
  "tags": ["templated", "triangle", "altitude"],
  "rubric": [
    {"id": "...", "text": "Is angle GHE a right angle?", "category": "curriculum", "weight": 0.4}
    /* ... */
  ],
  "reference_svg": null,
  "metadata": {
    "original_expected_properties": [
      {"name": "altitude_perp", "type": "right_angle", "args": ["G", "H", "E"]},
      {"name": "foot_on_base",  "type": "point_on_segment", "args": ["H", "E", "F"]}
      /* ... */
    ],
    "coordinate_tolerance": 0.0001,
    "required_canvas": {},
    "expected_points": {},
    "structural_checks": [],
    "queries": [],
    "raw_weights": [1.0, 0.5, ...],
    "source": "curriculum"
  }
}
```

The Croissant metadata file (`croissant.json`) describes the four atomic per-record fields (`id`, `prompt`, `tier`, `tags`); `rubric` and `metadata` are nested JSON sub-trees and should be parsed directly from the JSONL line. Both are documented in the project datasheet (`docs/datasheet.md`) and the paper's Appendix B (full predicate vocabulary).

## Usage

### Plain Python

```python
import json
with open("bench_generated.jsonl") as f:
    scenarios = [json.loads(line) for line in f]
print(len(scenarios), "templated scenarios")
```

### Hugging Face `datasets`

```python
from datasets import load_dataset
ds_templated  = load_dataset("<anon>/geogenbench", "templated",  split="train")
ds_curriculum = load_dataset("<anon>/geogenbench", "curriculum", split="train")
```

### Croissant

```python
import mlcroissant as mlc
ds = mlc.Dataset(jsonld="croissant.json")
for record in ds.records("templated"):
    ...
```

## Verification pipeline

GeoGenBench is graded by a deterministic two-renderer pipeline:

1. The model produces a TikZ source string from the prompt only (the rubric is not given to the model).
2. The TikZ is rendered to SVG via a containerised LuaLaTeX + dvisvgm pipeline (released as `tikz-renderer:v1.0.0`).
3. The same TikZ is compiled to SymPy geometry objects.
4. Each predicate in `metadata.original_expected_properties` is decided against the SymPy symbol table with tolerance τ = 5×10⁻³.
5. The scenario is scored as `pass` (all predicates satisfied), `soft_pass` (no failures, ≥1 skipped), `fail` (≥1 hard failure), or `gen_failure`/`render_failure`.

The full verifier toolkit and the Docker renderer are released in the project repository alongside this dataset.

## Sources

- Templated split: deterministic Python template engine (`evals/generate_scenarios.py` in the source repo); seed 42.
- Curriculum split: K-12 geometry textbook chapters, processed by Anthropic Claude Sonnet under author supervision; only generated prompts and verifier annotations are released, not source textbook text.

## Licensing

- Code (template engine, verifier, renderer, this dataset card): MIT License (`https://opensource.org/licenses/MIT`).
- Templated scenarios: MIT License.
- Curriculum scenarios: derivative annotations released under MIT; the underlying textbook content is not redistributed and is referenced under §107 (educational fair use, US Copyright Act).

## Versioning

- **v1.0.0** (2026-05-06): post-hardening v1 verifier; 801 scenarios; submission release.

A `CHANGELOG.md` will track future revisions. Older versions remain accessible under their git tags. v1.1 is planned to include a held-back parameter-rolled test split for contamination defence.

## Citation

```bibtex
@inproceedings{geogenbench2026,
  title     = {{GeoGenBench}: An automatically-verifiable benchmark of generative geometric reasoning},
  author    = {Anonymous},
  booktitle = {NeurIPS 2026 Evaluations and Datasets Track},
  year      = {2026},
  note      = {Anonymized for double-blind review}
}
```

## Notes for reviewers (NeurIPS 2026 E&D Track)

- **Croissant 1.0 metadata** is provided in `croissant.json`; passes `mlcroissant.Dataset(...)` validation locally.
- `<anon>` placeholders in URLs and citation will be replaced with the public hosting target post-acceptance.
- The full GeoGen datasheet (Gebru et al. format) is available at `docs/datasheet.md` in the source repository.
- The human-correlation study reported in the paper's Appendix E used a separately-frozen 200-scenario sample drawn deterministically from this dataset (see `evals/human_study/sample.json`).
