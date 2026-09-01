# Cross-format probe transfer

**Question:** the spatial probes in `interp/RESULTS.md` are model-specific and
domain-specific by construction. Is the *representation* they read also
domain-specific — or does the model park the same geometric information in the
same residual directions regardless of the surface format it is reading?

**Design:** render the SAME figure (identical compiled SymPy ground truth)
into four surface formats, forward-pass each through the model (reading mode —
no generation), train a linear probe on one format, evaluate it frozen on the
others. High transfer ⇒ a shared, format-independent spatial representation;
floor-level transfer ⇒ task-local encoding, and the RESULTS.md claims stay
domain-scoped.

This is legitimate because the original captures also probed a plain forward
pass over [prompt + completion] (`capture.py` two-pass design) — reading mode
is the same activation regime, minus self-generation.

## Formats

| format | source | entities findable |
|---|---|---|
| `recipe` | RecipeDSL JSON (original probe domain) | all (quoted ids) |
| `tikz` | `ir_to_tikz` body (pure text) | points (+ some lines) |
| `svg` | `ir_to_svg` source; spans only inside `<text>` labels | labeled points |
| `english` | template prose renderer | all |

Caveat for regression targets: `tikz`/`svg` texts contain literal coordinates,
`recipe`/`english` are constraint-based — surface availability of coordinates
differs by format. `entity_relation` is the lead labeler (relation words also
appear in all formats, but the probe reads the *entity-name* token, and
transfer across different surface encodings of the relation is the point).

## Corpus (`build_corpus.py`)

~300 unique figures from 8 parametric templates (midsegment, altitude,
perp+parallel, angle bisector, tangent, cevian, perpendicular bisector,
median), covering 8 relation classes. **Entity labels are randomized per
figure** — midpoints are not named "M" — so the token-identity floor sits near
majority class by design (the original corpus had a 0.55 naming baseline).
Validity gated by the real `validate → lower → compile → check` pipeline;
ground truth via `interp/geometry_labels.py`. Exact char spans of every entity
id are recorded per format, so capture/probing need no format-specific parsing.

## Pipeline

```bash
# 1. corpus (CPU, no model)
interp/.venv/bin/python interp/transfer/build_corpus.py \
    --n-figures 300 --seed 0 --out interp/transfer/corpus

# 2. reading-mode capture, one dir per format (MPS-friendly; no generation)
interp/.venv/bin/python interp/transfer/capture_reading.py \
    --corpus interp/transfer/corpus --out interp/activations/transfer_q15 \
    --model Qwen/Qwen2.5-1.5B-Instruct --device mps

# 3. transfer probes (CPU)
interp/.venv/bin/python interp/transfer/probe_transfer.py \
    --act-root interp/activations/transfer_q15 --train-format recipe \
    --seeds 5 --out interp/transfer/results_q15.json

# offline tests (no model)
interp/.venv/bin/python interp/transfer/test_transfer.py
```

Capture output is `probe.py`-schema-compatible (`meta.jsonl` + per-figure
`.npz` with `positions`); `pid` = figure id, so the figure-level split doubles
as the base-prompt-grouped split. The `recipe` capture dir can be fed to the
original `interp/probe.py` unchanged.

## Conditions reported per (labeler, layer, target format)

- `in_domain` — source probe, held-out figures, source format
- `transfer_strict` — source probe, held-out figures, target format
- `transfer_seen` — source probe, train figures, target format (diagnostic)
- `ceiling` — target-trained probe, held-out figures
- `floor` — token-identity baseline (clf; ≈ majority class here by design)

Transfer fraction = (transfer_strict − floor) / (ceiling − floor).

## Status / scale notes

- **Pilot complete — see [RESULTS.md](RESULTS.md).** Headline: recipe↔english
  share a mid-layer (~L14–20) representation (relation transfer fraction 0.61,
  coord 77% of ceiling); recipe↔tikz/svg do NOT (at token-identity floor
  despite 0.92–0.99 format-native ceilings); angle is a null in reading mode.

- Pilot model: Qwen2.5-1.5B-Instruct on Apple Silicon (this machine cannot
  hold the 7B — 17 GB free disk). The 7B/32B runs that connect to
  RESULTS.md need the GPU-box workflow (`interp/setup_vast.sh`); the scripts
  take `--model`/`--device` and run unchanged.
- Pre-registered expectations: recipe→tikz transfers substantially (both
  coordinate-bearing code), recipe→english partial and mid-layer-peaked,
  layer-0 transfer ≈ floor everywhere.
