# Methodology — what we probe and what counts as a result

Companion to [PLAN.md](PLAN.md). This pins down the experimental protocol so the
probes measure spatial *representation*, not tokenizer trivia.

## The claim we want to support

> Geometric property *X* (a relation type, an angle value, a point's coordinates,
> an intersection choice) is **linearly decodable** from the residual stream, and
> it becomes decodable at **layer L** — evidence that the model forms an internal
> spatial representation of *X* while constructing the figure.

A result is only meaningful if the probe target is **not** the identity of the
token at the probed position (see "Trivial vs non-trivial" below).

## Protocol

1. **Substrate.** Greedy-decode a construction for each prompt; keep only the ones
   that pass the render-free grader (`--only-valid`) so we probe *correct* spatial
   structure with known ground truth.
2. **Activations.** Forward the realized `[prompt + completion]` ids once with
   `output_hidden_states`; store the residual stream at every layer for each
   completion token (float16). Position p ↔ generated token p (no detok drift).
3. **Labels.** A labeler maps `(record) → {token_position: label}`. The label's
   *source* matters — see the target table. Special-token positions are dropped.
4. **Probe.** Per layer: `StandardScaler → LogisticRegression` (classification) or
   `→ Ridge` (regression). Standardize because residual norm grows with depth.
5. **Split — PROMPT LEVEL.** All positions of a prompt go to one fold
   (`GroupShuffleSplit` on prompt id). Splitting at the position level leaks
   (two tokens of the same construction are highly correlated) and inflates acc.
6. **Report.** Test accuracy (or R²) vs layer, against the **majority-class /
   mean baseline measured on the test fold**. The shape of the curve (where it
   rises, where it peaks) is the finding, not a single number.

## Trivial vs non-trivial targets

| | Probed position | Target | Why |
|---|---|---|---|
| ❌ trivial | token "perp" | "is this the perp token?" | The unembedding decodes the current token by construction — late-layer acc ≈ 1.0 tells us nothing about *representation*. (`label_relation` is this — kept only as a plumbing sanity curve.) |
| ✅ non-trivial | the point token that **names** an intersection | which of the 2 intersections (the "pick" rule) | Not present in the token string; must be inferred from geometry. |
| ✅ non-trivial | first completion token, **before** any geometry is written | the prompt's target angle (60 vs 70) | Tests whether the property is "planned" ahead of being emitted. |
| ✅ non-trivial | a point's name token | that point's (x, y) coordinates | Regression against the **compiled SymPy truth**, not text. |

Rule of thumb: **the label must come from the ground-truth geometry (SymPy
compile / the parsed DSL / the prompt), and must not be readable off the probed
token's own string.**

## Target labelers (Phase 2 work, in priority order)

Each is a `meta-record → {pos: label}` function added to `probe.LABELERS`. The
capture record already carries `tokens`, `offsets` (char spans), `construction`
(parsed DSL), and `completion` — enough to locate positions and join to truth.

1. **angle value** — find the angle literal token(s); label = the numeric angle.
   Decodability across layers = "where does the angle live?" (regression or
   binned classification). Cleanest first real result.
2. **relation type of the construction** — label a fixed structural position
   (e.g. first completion token) with the dominant relation in the *compiled*
   figure (perpendicular / parallel / midpoint / tangent). One label per prompt.
3. **point coordinates** — at each point's name token, regress the SymPy (x, y).
   Needs joining DSL point ids → compiled coords (use `ir.to_sympy` / `queries`).
4. **intersection disambiguation** — at an intersection's output token, classify
   the `pick` choice ("higher"/"index 0/1"). The headline non-trivial target.

## Phase 3 — causal check (after decodability)

For a property that decodes well, build **minimal pairs** (60°↔70°,
perpendicular↔parallel — identical otherwise) and patch the probed-layer
activation from one onto the other. If the construction/behaviour flips, the
representation is *causal* there, not merely correlated. Decodability locates
*where to patch*; patching is the confirmation.

## Readiness checklist (so the loop runs on the box)

- [x] grader, capability gate, relevant few-shot selection — done, tested.
- [x] capture over realized ids; prompt-level split; per-layer scaling — done.
- [x] offline smoke tests pass (no GPU).
- [ ] **On GPU:** confirm capability rate is usable (`--few-shot all`/`relevant`).
- [ ] capture a tier-1 `--only-valid` run; eyeball `meta.jsonl` token alignment.
- [ ] implement the **angle** labeler (target #1) and read its curve.
