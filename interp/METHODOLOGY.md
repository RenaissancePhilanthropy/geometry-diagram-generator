# Methodology — how we probe what a geometry LLM represents internally

A detailed, read-it-top-to-bottom account of the experimental protocol: what we
measure, how the data flows, every control, and the honest limitations. Written
for someone comfortable with ML but new to mechanistic interpretability.
Companion to [PLAN.md](PLAN.md) (the plan) and [RESULTS.md](RESULTS.md) (findings).

---

## 0. The one-paragraph version

We have an LLM write geometry constructions, record its internal activations at
every layer, and train simple linear "probes" to test whether known geometric
facts (a point's role, its coordinates, an angle) are readable from those
activations — and *at which layer* they become readable. Because the project's
pipeline compiles every construction to exact geometry (SymPy), we have a
ground-truth answer key for every output, which is what makes the probing
meaningful. We then patch activations to test whether the model *causally uses*
what we can decode. The whole design is built around **controls** that separate
"the model represents X" from cheaper explanations (naming conventions,
memorization, the probe's own power).

---

## 1. The claim format

Every result is phrased as one of:

> **Geometric property *X*** (relational role / coordinates / angle) is **linearly
> decodable** from the residual stream at **layer L**, **above a control baseline** —
> evidence the model forms an internal, *usable* representation of *X*.

Three words in that sentence are load-bearing and each maps to a design choice:

- **linearly** — the probe is linear (§6.3), so "decodable" means "in a form the
  model's own machinery could read," not "extractable by a clever enough decoder."
- **above a control baseline** — the number only counts as a *representation* if
  it beats what you'd get from the token's name alone (§6.4).
- **at layer L** — we probe every layer, because *where* a fact appears tells us
  whether it was given by the input or computed by the network (§6.6).

---

## 2. Why this substrate (the thing that makes it possible)

Most LLM interpretability lacks an answer key — there is no "correct" internal
state for writing an essay. Our generator is different: the model emits an
explicit construction DSL, and the project compiles it to **exact geometry** —
every point's coordinates, every angle, every relation, plus a 15-predicate
checker. So for each token the model writes, we *know* the true geometric fact it
should encode. That ground truth is the target the probes are trained against;
without it, "decode the geometry from activations" has nothing to decode against.

---

## 3. The four-phase design (with gates)

Each phase only matters if the previous one passes:

| Phase | Question | Artifact |
|---|---|---|
| 0 — Capability gate | Can the model even do the task? | `capability_check.py`, `grade.py` |
| 1 — Capture | Record internal state during the task | `capture.py`, `geometry_labels.py` |
| 2 — Probe | Is geometry decodable, and where? | `probe.py` |
| 3 — Patch | Does the model *use* it (causal)? | `patch.py` |

Gating matters: probing a model that cannot construct geometry would be studying
noise. So Phase 0 must clear a usable validity rate before anything else.

---

## 4. Phase 0 — capability gate

**Goal:** measure the valid-construction rate, and confirm it is high enough that
the model's internals are worth probing.

`grade.py` runs each model completion through the project's *real* pipeline,
render-free, recording the furthest stage reached:

```
extract JSON → RecipeDSL.model_validate → lower_to_ir
            → compile_defs (SymPy) → run_checks (+ angle checks)
```

- **parse** — pull the DSL JSON out of the model's free text.
- **validate** — does it satisfy the RecipeDSL schema?
- **lower** — expand high-level ops (`median`, `altitude`) into primitive
  definitions (`PointMidpoint`, `LinePerpendicularThrough`, …).
- **compile** — turn those into SymPy objects with concrete coordinates.
- **check** — do the asserted geometric invariants hold?

A construction is "valid" only if it reaches **success** (compiles + passes
must-level checks). The grader is wrapped to **catch any exception** (degenerate
model output can throw arbitrary SymPy errors) so one bad completion never aborts
a long run.

Prompts come from the GenExam geometry benchmark; we use few-shot exemplars
(`--few-shot all|relevant:K`) plus a small `DSL_GOTCHAS` addendum that targets the
recurring schema mistakes. **Findings:** 7B ≈ 20%, 32B ≈ 40% valid — low but
enough valid constructions to probe (and the gate itself is a clean capability
comparison, since it involves no probe).

---

## 5. Phase 1 — activation capture

### 5.1 What we capture: the residual stream

A transformer represents each token as a vector (3584 numbers for 7B, 5120 for
32B). That vector flows up through the layers, and **each layer adds an edit to
it** (`x = x + attention(x); x = x + mlp(x)`). This running vector is the
**residual stream** — the model's evolving "workspace" for that token. Reading it
after each layer gives us a snapshot of the model's state at that computational
depth. `output_hidden_states=True` returns all of them: a tuple of
`num_layers + 1` tensors (index 0 = embeddings, i = output of layer i).

### 5.2 Two-pass design (generate, then capture)

We do **not** read activations during generation. Instead:

1. **Generate** the construction (`model.generate`). Keep only the produced token
   ids.
2. **Capture:** run a *single* forward pass over the full realized sequence
   `[prompt_ids + completion_ids]` with `output_hidden_states=True`, and snapshot
   the residual stream.

Why a second pass: forwarding the *finished* sequence in one shot gives every
layer at every position with indices that line up exactly to known tokens.
Crucially we forward the **realized generated ids**, not a re-tokenization of the
decoded text — re-tokenizing can split tokens differently ("detok drift") and
desync activations from labels. Realized ids guarantee position *p* ↔ the exact
token the model produced at *p*. (`capture.capture_activations`)

### 5.3 What gets stored, and how it stays small

- We keep only the **completion** positions (where the model writes the figure),
  and with `--keep-positions entities` only the **entity-name token positions**
  the probes actually read (~10–20 per construction). The `.npz` stores the
  compacted `acts [n_layers, n_kept, d_model]` (float16) plus a `positions` array
  recording each kept slot's *original* token index — so the probe can map labels
  (which live at original token positions) back to stored slots.
- This makes each record ~25× smaller, which is what lets us afford many samples.

### 5.4 Multiple samples per prompt

For each prompt we generate **K completions at temperature** (`--samples K`),
saved as `<prompt>_s0 … _s{K-1}`. Diverse samples were intended to multiply the
data. (This is also the source of the leakage subtlety — see §9. A "record" =
one sample = one completion; a "prompt" = the underlying problem, shared by all
its samples.)

### 5.5 Ground-truth extraction (the answer key)

`geometry_labels.ground_truth(construction)` re-runs the construction through
validate → lower → compile and returns, keyed to entity ids:

- **`entity_relations`** — the geometric role each entity embodies, read from the
  *lowered definitions* (`PointMidpoint`→midpoint, `LinePerpendicularThrough`→
  perpendicular, `PointIntersection`→intersection, `LineTangent`→tangent, …).
- **`point_coords`** — exact compiled (x, y) for each point (`ir.queries`).
- **`vertex_angles`** — interior angle at each triangle vertex.

It degrades gracefully: a construction that lowers but fails to compile still
yields relations (just no coordinates). Each capture record's `meta.jsonl` line
carries this ground truth plus the prompt, completion, tokens, and grade.

---

## 6. Phase 2 — linear probing (the core experiment)

### 6.1 The data matrix

For a chosen layer L, `probe.build_xy` walks every record and emits one row per
labeled token position:

- **X** = the residual-stream vector at that (layer, position) — the model's
  "state" for that token. (3584 or 5120 numbers.)
- **y** = the geometric label for that entity (its role / coords / angle), from
  the record's ground truth.
- **group** = the **base prompt** id (the `_sN` suffix stripped — see §9).
- **token** = the literal token string (used for the naming baseline).

A *labeler* (`label_entity_relation`, `label_point_coord`, `label_angle`) maps a
record → `{token_position: label}`. `geometry_labels.id_positions` finds the
positions where an entity id is written (matching the quoted `"M"` form against
saved char offsets, so we never match `A` inside `AB`).

### 6.2 Trivial vs non-trivial targets (the cardinal rule)

> **A probe target must come from the geometry, and must NOT be readable off the
> probed token's own string.**

| | Probed position | Target | Verdict |
|---|---|---|---|
| ❌ trivial | the token "perp" | "is this the perp token?" | The unembedding decodes the current token by design — meaningless. (`label_relation` is this; kept only as a plumbing sanity check.) |
| ✅ non-trivial | the token naming a point | that point's geometric **role** | Role isn't in the letter "M" — it comes from how M was constructed. |
| ✅ non-trivial | the token naming a point | that point's **(x, y)** | Coordinates aren't in the name at all. |
| ✅ non-trivial | a triangle-vertex token | that vertex's **angle** | Not in the name. |

### 6.3 The probe pipeline, and why each piece

Per layer: **`StandardScaler → PCA(≤100) → linear head`** (LogisticRegression for
classification, Ridge for regression).

- **StandardScaler** — z-score the features. The residual stream's norm grows
  with depth, so without scaling, layers aren't comparable.
- **PCA(≤100)** — reduce 3584/5120 dims to ≤100 before fitting. With only a few
  hundred–thousand samples, fitting thousands of weights overfits (it produced
  negative R² before we added PCA). PCA keeps the directions where the data
  actually varies. Capped at `min(100, n_train−1, n_features)`.
- **Linear head** — *deliberately weak.* The model reads its own activations via
  dot products (attention `q·k`, MLP `W·h`). A linear probe uses the same
  operation, so if it succeeds, the fact is in a form **the model itself could
  read** = a usable representation. A nonlinear probe could recover information
  the model can't actually use — measuring the probe's cleverness, not the model.

### 6.4 The controls (what separates a real result from an artifact)

1. **Prompt-level train/test split** (`GroupShuffleSplit` on the base-prompt
   group). All rows from a prompt — across *all its samples* — go to one side.
   The test set is prompts the probe has never seen in any form, so the score
   measures **generalization**, not memorization. (This is the control the
   leakage bug violated; see §9.)
2. **Token-identity baseline.** For classification, also predict the label from
   the **token string alone** (majority label per token on train). The probe only
   demonstrates *representation* to the extent it **beats this** ("lift over
   naming"). Example: midpoints are usually named "M", so naming alone scores
   ~0.55 on relations; the probe's lift above that (+0.37) is the real signal.
   (A regression analogue — predict coords from the name alone — is computed in
   the analysis scripts; it should be folded into `run_probe`.)
3. **Per-layer comparability** — one split reused across all layers; standardize
   per layer; baseline measured on the *test* fold.

### 6.5 Metrics

- **Classification (relations):** accuracy on held-out prompts; report **lift =
  accuracy − token-baseline**. Chance = majority class.
- **Regression (coords, angle):** **R²** (1 = perfect, 0 = no better than
  predicting the mean, <0 = worse than the mean / overfitting). Report **lift =
  R² − name-only-baseline R²**.
- **Multi-seed** — repeat over several random splits for mean ± std; single-seed
  point estimates are not trusted for fine distinctions.

### 6.6 Reading the curve (decodability vs layer)

We run the probe at **every layer** and plot score vs depth:

- **Flat-and-low early, rising to a mid/late peak** → the property is *computed*
  across depth (it wasn't in the input embedding; the network derived it). This
  is the signature we look for.
- **High already at layer 0** → it was essentially *given* by the input tokens
  (e.g. naming convention) — not computed.
- **Rises then falls toward the output** → an *intermediate* representation: built
  up, then converted back into output tokens in the final layers.

For multi-point analyses we also use a **coherent-map** measure: decode every
point in a figure, then correlate the *pairwise-distance matrix* of decoded vs
true points (rotation/translation invariant), against a permutation null — tests
whether the decoded points preserve the figure's *shape*, not just individual
coordinates.

---

## 7. Phase 3 — causal patching

Decodability is correlational ("the info is present and readable"). Patching
tests **use** ("does the model act on it?").

Design (`patch.py`, angle): build **minimal pairs** that differ at one token —
`"angle A = 60°…"` (clean) vs `"…70°…"` (corrupt). Then:

1. Run **corrupt**, cache its residual stream at the differing token, every layer.
2. Run **clean**, but at layer L **overwrite** that token's activation with the
   cached corrupt one (forward hook), and read the output.
3. **Effect(L)** = normalized logit-difference recovery:
   `(diff_clean − diff_patched) / (diff_clean − diff_corrupt)` — 0 = patch did
   nothing, 1 = prediction fully flipped 60→70.

Sweep L → a causal-vs-layer curve. Because this uses fresh minimal-pair prompts,
**it is unaffected by the capture-split leakage.** (Current version patches the
angle *literal* — a "uses the stated value" test; patching the relational
representation during construction is the deeper next step.)

---

## 8. Scale comparison (7B vs 32B)

- **Capability** is a direct comparison (no probe): 40% vs 20%.
- **Representation:** because 32B only fit the GPU as **AWQ 4-bit** while 7B is
  bf16, a raw 7B-vs-32B gap confounds *size* with *quantization*. We added a
  **7B-AWQ control** so: 7B-bf16 → 7B-AWQ isolates *quantization*; 7B-AWQ →
  32B-AWQ isolates *size* (both 4-bit).
- **Different layer counts** (29 vs 65 hidden states) → compare by **fractional
  depth** (layer / max-layer), not raw layer number.

---

## 9. The leakage incident (a methodology lesson)

This is worth its own section because it is the clearest example of why the
controls matter.

**The bug.** `build_xy` originally grouped the train/test split by *captured
sample* (record index), not by *prompt*. But each prompt has many temperature
samples (`Mathematics_65` had 13: `_s0, _s3, _s6, …`) — same problem, same point
names, near-identical geometry. So siblings landed on **both** sides of the
split: the probe could train on `_s0` and be "tested" on the near-identical `_s3`,
effectively **memorizing each prompt's answer** rather than generalizing.

**How it was caught.** An adversarial code review (Codex) flagged that the group
was the sample, not the base problem.

**The fix.** Group by **base prompt** (strip the `_sN` suffix) so *all* samples of
a prompt stay on one side. The fix is in analysis code only — no re-capture
needed; we re-ran the probes offline.

**Impact.** Multi-sample numbers fell sharply: coordinates R² 0.49 → ~0.15, angle
→ unstable. **Relational role survived** (lift over naming held at +0.37). The
deeper cause it exposed: each dataset has only **35–50 unique prompts** —
multi-sampling inflated *record counts*, not *construction diversity*. Coarse
facts (a point's role) generalize from few prompts; fine-grained coordinates do
not. This is why the next experiment needs **more unique prompts, not more
samples.**

The lesson: a result is only as trustworthy as its split. Pseudo-replication
(many correlated samples of the same item) silently inflates held-out scores
unless the split groups by the true independent unit.

---

## 10. Threats to validity → controls (summary)

| Threat | Control |
|---|---|
| Probe reads the token's own identity (trivial) | Labels from geometry, never the token (§6.2) |
| "Representation" is just naming convention | Token-identity baseline; report lift (§6.4) |
| Probe finds info the model can't use | Linear probe matched to model's dot-product reads (§6.3) |
| Overfitting (dims ≫ samples) | PCA(≤100) + standardize (§6.3) |
| Memorization across correlated samples | Prompt-level group split (§6.4, §9) |
| Correlation ≠ causation | Activation patching (§7) |
| Size vs quantization confound | 7B-AWQ control (§8) |
| Different model depths | Fractional-depth comparison (§8) |
| Single-split luck | Multi-seed mean ± std (§6.5) |

---

## 11. Limitations (current, honest)

- **Few unique prompts (35–50).** The binding limit. Fine-grained targets
  (coordinates, angle) are data-starved and do not yet generalize; only the
  relational-role result is robust leak-free.
- **32B is AWQ-4bit only** (disk-bound); a clean bf16-32B needs an 80 GB GPU.
- **Relational role is partly naming-correlated** — the lift over the token
  baseline (+0.37) is the honest signal, not the raw accuracy.
- **Capability is low (20–40%)** — we probe only the constructions that compile;
  the model's worse outputs are filtered out, which may bias toward easier cases.
- **Patching so far tests a stated literal,** not the constructed relational
  representation.

---

## 12. Reproducibility

**Files:** `grade.py` (gate scoring), `capability_check.py` (gate + model loading
+ few-shot + `load_model` with `--quant none|4bit|awq`), `capture.py` (Phase 1),
`geometry_labels.py` (ground truth), `probe.py` (Phase 2), `patch.py` (Phase 3),
`analysis/` (coherent-map, layerwise, consistency, ordering scripts). Tests:
`test_*.py` (offline, tiny models / synthetic signals).

**Representative run (GPU box):**
```bash
python interp/capability_check.py --device cuda --tier 1 --n 20 --few-shot all
python interp/capture.py --device cuda --n 100 --few-shot all --samples 8 \
    --max-new-tokens 512 --require-ground-truth --keep-positions entities \
    --layers all --out-dir interp/activations/run
# then, offline (CPU):
python interp/probe.py --act-dir interp/activations/run --labeler entity_relation
python interp/probe.py --act-dir interp/activations/run --labeler point_coord
python interp/patch.py --device cuda            # causal, needs the model
```

Probing is CPU-only once activations are captured, so all of Phase 2 analysis
runs offline on the saved `.npz` + `meta.jsonl`.
