# Cross-format probe transfer — pilot results

**Date:** 2026-07-26 · **Model:** Qwen2.5-1.5B-Instruct (bf16, MPS, reading
mode) · **Corpus:** 300 unique figures × 4 formats (`build_corpus.py`, seed 0,
randomized entity names) · **Probes:** StandardScaler → PCA(100) → linear,
figure-level split identical across formats, 5 seeds, mean ± std.

**Question:** are the probe-readable geometry representations format-specific,
or does the model park the same information in the same residual directions
regardless of surface format? Probes trained on `recipe` (the original
domain), evaluated frozen on `tikz` / `svg` / `english` at held-out figures.

## Headline

**Partial transfer, sharply structured by format family.** Recipe-JSON and
English share a substantial mid-layer representation (relation transfer
fraction 0.61, coordinate transfer 77% of ceiling). The rendered code formats
(TikZ, SVG) share almost nothing with recipe for relations — transfer sits at
the token-identity floor — even though format-native probes decode the same
labels near-perfectly there (ceilings 0.92–0.99). Where transfer exists it
lives **only in a mid-network band (~L14–20 of 28)**; outside that band
frozen probes go to floor (clf) or strongly negative R² (reg).

## 1. entity_relation (clf, 8 classes; majority = 0.36)

At the in-domain peak layer L19:

| condition | tikz | svg | english |
|---|---|---|---|
| transfer_strict | 0.516 ± 0.031 | 0.526 ± 0.019 | **0.787 ± 0.024** |
| token-identity floor | 0.574 | 0.538 | 0.449 |
| ceiling (target-trained) | 0.918 | 0.989 | 1.000 |
| **transfer fraction** | **≈ 0 (below floor)** | **≈ 0** | **0.61** |

In-domain (recipe→recipe, held-out figures): **0.997 ± 0.002**. The transfer
curve to English peaks at **L16 (0.87)** — mid-network, earlier than the
in-domain peak.

**Read:** the relation representation the recipe probe finds is *shared with
English* but *not with TikZ/SVG*. The information is present when reading
TikZ/SVG (ceilings ~0.92–0.99) but encoded along different directions — or the
format-native probes are reading format-local structural correlates. Note this
**reverses the pre-registered prediction** (recipe→tikz was expected to
transfer best as code→code); the data say the divide is
*constraint-language vs rendered-geometry*, not code vs prose.

## 2. point_coord (reg, normalized bbox position; R²)

At L19: in-domain **0.914 ± 0.005**.

| condition | tikz | svg | english |
|---|---|---|---|
| transfer_strict | 0.323 ± 0.024 | 0.561 ± 0.025 | **0.720 ± 0.010** |
| ceiling | 0.876 | 0.912 | 0.935 |
| fraction of ceiling | 0.37 | 0.61 | 0.77 |

Transfer is positive **only in L14–20**; outside that band frozen probes are
strongly negative (e.g. tikz at L28: −2.3). The shared coordinate subspace
exists only mid-network; early layers are token-bound and late layers
re-encode format-specifically.

## 3. angle (reg, degrees) — null

In-domain peaks at **R² = −0.03**; target-trained ceilings are also ≈ 0.
Vertex angles are **not linearly decodable in reading mode from this 1.5B
model in any format**, so transfer is undefined. (Consistent with the
leak-free correction in ../RESULTS.md, where angle was already unsupported.)

## Sanity checks

- Original `interp/probe.py` run unchanged on the `recipe` capture dir
  reproduces the harness: peak acc 1.00, majority 0.359, token-identity 0.488
  (names are randomized, so naming carries little — by design).
- Every recorded entity span byte-verified in all 4 formats; kept token
  positions decode to entity-name tokens (incl. BPE space-prefix and
  multi-char span-overlap cases). 76/76 offline tests pass.

## Caveats

1. **Pilot model.** 1.5B, not the 7B/32B from ../RESULTS.md. Probes are
   model-specific; connecting to the published curves needs the same capture
   on 7B (GPU box — scripts run unchanged via `--model/--device`).
2. **Template–relation coupling.** 8 templates; relation is largely a function
   of (construction type, entity slot). A probe could decode the construction
   type from context and get the relation nearly for free — this inflates
   in-domain accuracy (0.997) and the same concern applies to the original
   study (35–50 unique GenExam prompts). The *transfer contrast* between
   formats is unaffected (same figures everywhere), but absolute levels
   should not be read as "relation qua relation." Fix: more templates,
   multi-relation mixed figures.
3. **Coordinate clustering.** Bbox-normalized coordinates cluster by
   (template, role) — e.g. base vertices pin to y=0 — so in-domain R²=0.91
   overstates fine-grained coordinate knowledge. Same-figure transfer
   contrasts remain valid.
4. **Surface availability differs.** TikZ/SVG texts contain literal
   coordinates; recipe/english are constraint-based. Target-side ceilings can
   ride surface cues that source-side probes never saw.
5. **Reading ≠ generation.** The original probes were trained on activations
   over self-generated text. The bridge condition (old generation captures →
   this corpus's recipe format) requires the old capture data, which lives
   with the GPU runs.
6. **One English style.** The prose renderer uses fixed sentence templates;
   transfer to English may partly reflect that regularity. Paraphrase
   robustness untested.

## Answer to the motivating question (so far, 1.5B)

The probes are not *purely* domain-specific: a genuine format-independent
subspace exists mid-network, shared between symbolic-constraint JSON and
natural-language descriptions of the same figure. But it is not a universal
"geometry space" either — rendered-coordinate formats encode the same facts
in different directions. Domain-specificity is graded, and it is *lowest
exactly where the original study localized the computed representations
(mid-late layers)*.

## Next steps

- 7B (and 32B-AWQ) rerun on a GPU box → does the shared band sit at the same
  fractional depth? Does the recipe↔tikz divide persist at scale?
- Bridge condition: old generation-mode captures → reading-mode recipe.
- Break template coupling: 20+ templates, compositional multi-relation figures.
- English paraphrase variants (style-robust transfer).
- Causal follow-up: patch the shared mid-band subspace recipe→english and
  test whether downstream behavior (e.g. QA about the figure) flips.
