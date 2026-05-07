#!/usr/bin/env bash
# Build the supplementary material zip for the NeurIPS submission.
# Output: /tmp/geogenbench_supp_v1.zip (~140 KB compressed, ~1.6 MB uncompressed).
#
# Usage:  bash paper/scripts/build_supp_bundle.sh
#
# Upload the resulting zip alongside the paper PDF in OpenReview as
# "supplementary material". 100 MB OpenReview limit; this bundle is
# well under it.

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

OUT_DIR=/tmp/geogenbench_supp_v1
ZIP=/tmp/geogenbench_supp_v1.zip

rm -rf "$OUT_DIR" "$ZIP"
mkdir -p "$OUT_DIR"

# Dataset artefacts
cp benchmark/definitions/bench_generated.jsonl "$OUT_DIR"/
cp benchmark/definitions/bench_curriculum.jsonl "$OUT_DIR"/
cp benchmark/definitions/croissant.json        "$OUT_DIR"/

# Metadata
cp benchmark/definitions/README.md             "$OUT_DIR"/dataset_card.md
cp docs/datasheet.md                           "$OUT_DIR"/datasheet.md
cp docs/human_study_protocol.md                "$OUT_DIR"/human_study_protocol.md

# Top-level reviewer-facing index
cat > "$OUT_DIR"/README.md <<'EOF'
# GeoGenBench v1 — Supplementary Material

This bundle contains the full dataset and supporting metadata for the
paper *"GeoGenBench: A Benchmark for Generative Geometric Reasoning
with Symbolic Verification"*.

## Contents

| File | Purpose |
|---|---|
| `bench_generated.jsonl` | 600 procedurally-generated scenarios (templated split). |
| `bench_curriculum.jsonl` | 201 LLM-extracted scenarios (curriculum split). |
| `croissant.json` | Croissant 1.0 metadata for both splits. Validates against `mlcroissant >= 1.1.0`. |
| `dataset_card.md` | Hugging Face-style dataset card. |
| `datasheet.md` | Gebru-format datasheet (Datasheets for Datasets). |
| `human_study_protocol.md` | Frozen pre-registration of the human-correlation study. |

## File integrity

| File | SHA-256 |
|---|---|
| `bench_generated.jsonl` | `5e116307c99d9550c62f29b28c5594c7129c7084467ad06d63fed83abda332bb` |
| `bench_curriculum.jsonl` | `33efed400fbb494027005e3a24097130963c9b8c033e31318a2d3af9b4809df9` |

These match the `sha256` field in `croissant.json`'s `FileObject` entries.

## Loading the data

```python
import json
def load(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]

scenarios = load("bench_generated.jsonl")
print(f"Loaded {len(scenarios)} scenarios")
print(scenarios[0].keys())
```

## Validating the Croissant metadata

```python
import mlcroissant as mlc
ds = mlc.Dataset(jsonld="croissant.json")
print(ds.metadata.ctx.issues.report() or "OK")  # prints: OK
```

## License

All files released under MIT. The Bluebonnet Learning curriculum
referenced in the curriculum split is NOT redistributed; only
LLM-generated prompt rewrites and author-written property rubrics are.
See `dataset_card.md` and `datasheet.md` for full attribution.

## Anonymity

This bundle contains no author-identifying information. URLs in the
metadata point only to public licenses (MIT, opensource.org) and the
public Bluebonnet curriculum at the Texas Education Agency
(learn.texas.gov).

## What's NOT in this bundle (in the source repo)

- The procedural template engine (re-roll the templated split with a
  different seed for contamination defence).
- The verification toolkit (re-grade outputs against the predicate language).
- The Docker renderer image.
- The headline-run JSONLs (~12 K records per cell) and rendered SVGs
  for failure-mode analysis.

These are excluded for size; the bundle is the dataset, not the entire
reproduction stack. The full source repository is anonymised at
the URL given in the paper's appendix D.
EOF

# Build zip
( cd /tmp && zip -r geogenbench_supp_v1.zip geogenbench_supp_v1/ > /dev/null )

echo "Built: $ZIP"
ls -la "$ZIP"
echo
echo "Contents:"
unzip -l "$ZIP"
