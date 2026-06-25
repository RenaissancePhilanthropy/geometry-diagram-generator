# Results — where geometric concepts live in Qwen2.5-7B

**Date:** 2026-06-25 · **Model:** Qwen2.5-7B-Instruct (bf16) · **Method:** see
[METHODOLOGY.md](METHODOLOGY.md)

## Headline

When the model writes a geometry construction, **point coordinates, vertex
angles, and entity relations are all linearly decodable from its residual
stream** — and the decodability **rises across the layers**, peaking in the
**middle-to-late network (layers ~14–20)**. That rising shape (low early →
high mid-late) is the signature of a *computed* representation, not information
copied from the input tokens.

## Setup

- **Data:** 186 captured constructions (Qwen2.5-7B, GenExam geometry prompts,
  few-shot=all, 12 temperature samples/prompt). Activations = residual stream at
  all 29 hidden states, saved only at entity-name token positions.
- **Probes:** per layer, `StandardScaler → PCA(100) → linear` probe. Split at the
  **prompt level** (no within-construction leakage). Labels come from the
  compiled SymPy ground truth, not the tokens.
- **Sample sizes:** 1798 coordinate positions, 454 angle positions, 770 relation
  positions — well above the ~240 of the first (under-powered) attempt.

## 1. Point coordinates — regression, R² (target: position in figure bbox)

The cleanest result. R² climbs steadily and peaks ~L20.

| layer | 0 | 4 | 8 | 12 | 14 | 16 | **20** | 24 | 28 |
|---|---|---|---|---|---|---|---|---|---|
| R² | 0.13 | 0.20 | 0.22 | 0.32 | 0.33 | 0.38 | **0.40** | 0.37 | 0.30 |

**Read:** ~13% of position variance is decodable at the input layer, rising to
**~40% at the peak (L17–20)**, then easing off. The model **builds a linear map
of where each point sits** as information flows up the network. Coordinates are
nowhere in a point's name token, so this is genuine spatial structure.

## 2. Vertex angles — regression, R² (target: interior angle in degrees)

Highest absolute decodability.

| layer | 0 | 4 | 9 | 12 | 15 | **18** | 22 | 26 | 28 |
|---|---|---|---|---|---|---|---|---|---|
| R² | 0.46 | 0.56 | 0.59 | 0.59 | 0.60 | **0.63** | 0.59 | 0.62 | 0.59 |

**Read:** angle is the most decodable property (R²≈0.63 at the peak, L18).
**Caveat:** it is already R²≈0.46 at layer 0, so part of it is predictable from
the token/position before any computation (a mild confound — e.g. common angles
like 60/90 clustering). The genuinely *computed* gain is the **+0.17 rise** from
L0 to the L18 peak. Worth a follow-up control (regress angle on token identity
alone, subtract).

## 3. Entity relations — classification, accuracy (midpoint / perpendicular / …)

Baseline (majority class) = 0.35. **Token-identity baseline = 0.55** (predict the
relation from the name token alone — e.g. midpoints tend to be named "M").

| layer | 0 | 4 | 8 | 10 | 12 | **14** | 18 | 22 | 28 |
|---|---|---|---|---|---|---|---|---|---|
| acc | 0.58 | 0.77 | 0.77 | 0.83 | 0.85 | **0.87** | 0.81 | 0.80 | 0.80 |

**Read:** at L0 the probe (0.58) ≈ the naming baseline (0.55), as expected. It
then climbs to **0.87 at L14 — beating the token-only baseline by +0.32.** This
**reverses our first, under-powered run**, where the curve looked flat and we
concluded "mostly naming." With proper power (PCA + ~3× the data), there is a
strong *computed* relation representation beyond naming, peaking at L14.

## What it means

- **Yes, the model represents geometry internally**, and in a *linear* (usable)
  form — coordinates, angles, and relation roles are all readable along single
  directions in the residual stream.
- **It computes them across depth.** All three curves rise from low/near-baseline
  early to a mid-late peak — they are not present in the input, they are built.
- **The representations are concentrated in layers ~14–20.** That localizes where
  to intervene for the causal test.

## Caveats / limits

- **Correlational, not causal.** Decodability shows the information is present and
  linearly accessible, not that the model *uses* it. (Phase 3 below.)
- **Angle has a layer-0 confound** (~0.46); the computed component is the +0.17
  rise. A token-only control would quantify it cleanly.
- **Single seed / single train-test split.** Point estimates; no error bars yet.
  Re-running over a few seeds would give confidence intervals.
- **Coordinate R²≈0.40 is partial** — a real but imperfect linear map (the rest
  may be nonlinear or simply not represented).
- **20% construction validity** — labels for compiled constructions are exact;
  the model's lower-quality outputs are filtered out by `--require-ground-truth`.

## Next step — Phase 3 (causal)

Patch the residual stream at the peak layers (~L14–20) between minimal-pair
prompts (60°↔70°, perpendicular↔parallel). If the output geometry flips, the
representation is **causal**, not merely decodable. Decodability told us *where*
to aim; patching confirms *whether the model uses it*.
