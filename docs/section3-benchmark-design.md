# Section 3 — Benchmark Design

Working draft. Pulls from actual implementation in `evals/scenarios.py`, `evals/sympy_checks.py`, `evals/generate_scenarios.py`, and `ir/`.

---

## 3.1 Task formulation

A GeoGen scenario is a tuple

\[
\mathcal{S} = \langle \text{prompt},\ \mathcal{P},\ \mathcal{L},\ \mathcal{C} \rangle
\]

where the **prompt** is a natural-language request to draw a geometric figure (e.g., "Draw an acute triangle ABC with the altitude from A meeting BC at H. Label all four points and mark the right angle at H."), $\mathcal{P}$ is a list of *expected geometric properties* the rendered figure must satisfy, $\mathcal{L}$ is a set of *required labels* (point names that must appear in the output), and $\mathcal{C}$ is an optional set of *structural checks* (e.g., "must contain at least one quadrilateral").

A model must produce a TikZ source string that compiles to a valid SVG. The system then:

1. **Renders** the TikZ via a containerized LuaLaTeX + dvisvgm pipeline (FastAPI service on `:8001`).
2. **Verifies** by compiling the diagram's coordinate set and applying each property in $\mathcal{P}$ against a SymPy symbol table; comparing $\mathcal{L}$ against TikZ string content; and applying each structural check.
3. **Scores** the scenario as `pass` (all checks passed), `soft_pass` (no failures but at least one check skipped — typically rendering-only checks like marks), `fail` (≥1 hard failure), or `gen_failure` / `render_failure` (no usable output).

Crucially, the model is *not* given access to the property list or check definitions during generation — only the natural-language prompt. Properties are **the grading rubric, not the input**.

## 3.2 Scenario sources

GeoGen consists of two complementary sources of scenarios:

### 3.2.1 Templated scenarios (provably correct ground truth)

A procedural template engine (`evals/generate_scenarios.py`) emits scenarios in which the prompt prose and the expected-property list are produced **from the same source code**, guaranteeing they are mutually consistent.

- **30 templates** grouped by tier (9 tier-1 / 10 tier-2 / 11 tier-3) covering: right / equilateral / isosceles triangles, squares / rectangles / parallelograms / rhombi / trapezoids, segment + midpoint, parallel / perpendicular pairs, circle + point, altitude / median / angle-bisector / circumcircle / incircle / perpendicular bisector / chord, right-triangle altitude to hypotenuse, medial triangle, centroid + medians, parallel lines + transversal, isosceles altitude bisects base, tangent to circle, cyclic quadrilateral, two intersecting circles, Thales' theorem, triangle with two altitudes, inscribed angle in semicircle.

- **Per-template variation axes** multiply each construction across:
  - 10 vertex-triple label sets, 6 quad-label sets, 8 pair-label sets;
  - numeric parameter sweeps (e.g., Pythagorean leg pairs `[(3,4), (5,12), (6,8), …]`, equilateral side lengths, acute-triangle angle specs, circle radii);
  - 7 prompt-opener variants (`Draw…`, `Sketch…`, `Construct…`, `Make a diagram of…`, `Show…`, `Create a diagram showing…`, `I need a drawing of…`).

- **Round-robin per-tier capping** to 200 scenarios/tier, with every template guaranteed at least 12 instances. Total: **600 scenarios** (200 × 3 tiers).

Property correctness is by construction: a template that emits "Draw an equilateral triangle RST" also emits `{type: equal_lengths, args: [[R,S],[S,T],[T,R]]}` — both come from the same Python function, so prose and ground-truth cannot drift apart.

### 3.2.2 Curriculum-extracted scenarios (broader topic coverage)

A separate pipeline (`curriculum/generate_prompts.py`) extracts curriculum structure from K-12 geometry textbooks and uses an LLM to convert each into a student-style diagram request, plus structural and property-level expected outputs. **201 scenarios** ([36, 128, 37] across tiers 1, 2, 3).

Top tags include: `circle` (29), `proof` (16), `triangle` (14), `coordinate-plane` (14), `rotation` (14), `congruence` (13), `translation` (12), `parallel-lines` (12), `perpendicular-bisector` (11), `cone` (11), `pythagorean-theorem` (10), `right-triangle` (10).

This source covers topics templated scenarios do not (3D solids like cones, transformations, coordinate-overlay constructions, multi-step proofs requiring auxiliary lines), at the cost of LLM-authored ground truth that is spot-checkable but not guaranteed correct in the same way templated GT is.

### 3.2.3 Combined dataset

The final benchmark is the union: **801 scenarios** spanning [236, 328, 237] across tiers 1, 2, 3. Reported metrics decompose by source so reviewers can trust the templated half as a calibration anchor while the curriculum half stress-tests breadth.

## 3.3 Property language

Each scenario carries a list of expected geometric properties drawn from a fixed vocabulary of **20 types**, all enforced by `evals/sympy_checks._check_sympy_property` against a coordinate symbol table. Each property is decided in microseconds with a numeric tolerance `tol = 5×10⁻³`. The full vocabulary:

| Type | Args | Predicate | Tolerance use |
|---|---|---|---|
| `right_angle` | [a, o, b] | $\angle aob = \pi/2$ | $|\angle - \pi/2| < \text{tol}$ |
| `midpoint` | [m, a, b] | $|MA| = |MB|$ | $\big||MA| - |MB|\big| < \text{tol}$ |
| `collinear` | [p₁, p₂, p₃] | cross-product zero | $|\text{cross}| < \text{tol}$ |
| `equal_lengths` | [[a,b], [c,d]] | $|AB| = |CD|$ | $\big||AB| - |CD|\big| < \text{tol}$ |
| `parallel` | [[a,b], [c,d]] | $\vec{AB} \times \vec{CD} = 0$ | $|\text{cross}| < \text{tol}$ |
| `perpendicular` | [[a,b], [c,d]] | $\vec{AB} \cdot \vec{CD} = 0$ | $|\text{dot}| < \text{tol}$ |
| `point_on_line` | [p, a, b] | P collinear with line AB | $\text{perp dist}(P, AB) < \text{tol}$ |
| `point_on_segment` | [p, a, b] | P collinear with line AB | (same as above; **does not check segment bounds — known soft spot, see §4**) |
| `point_on_circle` | [p, o, r] | $|PO| = |OR|$ | $\big||PO|-|OR|\big| < \text{tol}$ |
| `tangent` | [[L₁,L₂], O, T] | $\text{perp dist}(O, L_1L_2) = |OT|$ | $\big|d_{O,L} - r\big| < \text{tol}$ |
| `angle_bisector` | [D, A, B, C] | $\angle BAD = \angle DAC$ | $\big|\angle BAD - \angle DAC\big| < \text{tol}$ |
| `intersects` | [[A,B], [C,D], P] | P on both lines | both perpendicular distances < tol |
| `equidistant_from_sides` | [I, A, B, C] | I incenter of $\triangle ABC$ | distances to the three sides equal within tol |
| `centroid` | [G, A, B, C] | $G = \frac{A+B+C}{3}$ | $|G - \text{centroid}| < \text{tol}$ |
| `opposite_side` | [P, Q, A, B] | P, Q on opposite sides of line AB | signed-cross product test |
| `same_side` | [P, Q, A, B] | P, Q on same side of line AB | signed-cross product test |
| `not_between` | [D, B, C] | D collinear with BC, outside segment | parametric $t$ test |
| `label_present` | [name] | label appears in TikZ source | string match (rendering-only; **soft check**) |
| `mark_present` | [kind, point] | tick / right-angle mark in TikZ source | string match (rendering-only; **soft check**) |
| `angle_equal` | [a₁, o₁, b₁, a₂, o₂, b₂] | $\angle a_1 o_1 b_1 = \angle a_2 o_2 b_2$ | (in property list, *not yet implemented* — see §4) |

The **first 17 are exact symbolic checks** computed against compiled coordinates; **`label_present` and `mark_present` are TikZ-source string checks** (intentionally weaker — they don't verify the mark renders correctly, just that a tikz primitive that *would* render it appears in the source); **`angle_equal` is currently a no-op** that returns `True, "skipped"` — the most prominent gap in the verification toolkit.

## 3.4 Verification pipeline

```
prompt
  ↓
LLM (any of: raw_code, structured, recipe strategies)
  ↓
TikZ source string
  ↓
LuaLaTeX (containerized, restricted-shell-escape)
  ↓
DVI → SVG (dvisvgm)
  ↓
parallel:
  • SymPy property check against compiled coordinates
  • TikZ-string label/mark check
  • SVG well-formedness check (run_svg_checks)
  • optional structural check (polygon_count)
  ↓
gate_status ∈ {pass, soft_pass, fail}
```

The two-renderer choice (TikZ → SVG via Docker by default; pure-Python `SVGRenderer` as fallback) decouples the benchmark from any specific TeX install while staying reproducible. The `--renderer svg` flag on `evals/run.py` switches to the dependency-free path.

### Gate-status semantics

```python
if any check failed:                 status = "fail"
elif any check skipped (soft):       status = "soft_pass"
elif checks ran successfully:        status = "pass"
else (no usable code):               status = "fail" (gate_failures = ["generation"])
```

Reported metrics:

- **strict-pass rate**: $\#\{\text{status}=\texttt{pass}\}\,/\,N$
- **strict+soft pass rate**: $\#\{\text{status} \in \{\texttt{pass},\texttt{soft\_pass}\}\}\,/\,N$

Headline tables use **strict-pass**; soft-pass acts as a diagnostic for "did the model get the geometry right but skip a label?" vs "did it produce something illegible."

## 3.5 Strategies (decoupled from benchmark, but evaluated together)

GeoGen ships three reference strategies as comparators, each implementing a `SubstanceStrategy` interface. The *benchmark* does not depend on any of these — any text-emitting model can be benchmarked by routing its TikZ output through the verification pipeline.

1. **`raw_code`** — single-shot. The LLM is given the prompt + a TikZ tutorial system prompt and produces TikZ via a `render_diagram(tikz: str)` tool call. May call the tool multiple times to revise.

2. **`structured`** — schema-constrained. The LLM is given a Pydantic schema for an intermediate `DiagramIR` representation and must emit IR JSON. Code (not LLM) compiles IR → SymPy objects → TikZ → SVG. Validation against expected properties happens *before* render so the strategy can self-correct.

3. **`recipe`** — schema + few-shot retrieval. A cheaper "selector" model picks 0–N relevant *recipes* (curated DSL examples like `circumcircle.yaml`, `altitude.yaml`) which are prepended as in-context examples for the main model. The main model emits a `RecipeDSL` (high-level operations like `triangle`, `altitude`, `circumcircle`); a lowering pass (`recipe/lower.py`) compiles to `DiagramIR`, then the structured pipeline runs.

The strategies sit on a spectrum from "freedom + LLM does everything" (raw_code) to "constrained schema + scaffolding does everything except final geometry choices" (recipe). Comparing them isolates the contribution of structured intermediate representations vs. retrieval vs. raw generation.

## 3.6 Tiered difficulty

Templated scenarios are tier-labeled at template-definition time:

- **Tier 1 — easy**: single named shape, no auxiliary construction (right triangle with sides specified, equilateral, square, segment + midpoint, …).
- **Tier 2 — medium**: one shape + one auxiliary construction (triangle + altitude / median / bisector / circumcircle / incircle, parallelogram, trapezoid, chord in circle, …).
- **Tier 3 — hard**: multi-step or composed construction (right-triangle altitude to hypotenuse, medial triangle, centroid, parallel + transversal, tangent to circle, cyclic quadrilateral, intersecting circles, Thales' theorem, …).

Curriculum scenarios inherit tier labels from the LLM curriculum extractor; we audit them but do not retier.

## 3.7 Dataset statistics

| Split | # scenarios | Tier 1 | Tier 2 | Tier 3 | Avg #properties | Tag-unique constructions |
|---|---:|---:|---:|---:|---:|---:|
| Templated | 600 | 200 | 200 | 200 | 3.4 | 30 templates |
| Curriculum | 201 | 36 | 128 | 37 | TBD | 73 unique tags |
| **Total** | **801** | 236 | 328 | 237 | TBD | 100+ |

Token cost note: the structured strategy uses ~25K input tokens / scenario (large IR-schema system prompt) and ~600 output tokens; raw_code uses ~17K / 880 with retries pushing input to 70K+ on hard scenarios. Per-scenario costs at frontier-model rates: $0.02-0.03 (Haiku) up to $0.33-0.42 (Opus); Pareto frontier almost always sits at Sonnet/Haiku + structured.

## 3.8 Reproducibility & contamination defense

- The procedural template engine is part of the release; reviewers can re-roll the templated split with a different `--seed` or new label sets to detect contamination.
- We commit to releasing the templated set as `train` and a held-back roll of the engine as `test`; the curriculum set is released entirely (it is naturalistic and hard to contamination-defend, so we report templated-only metrics in the headline and curriculum metrics as a robustness check).
- All renders are deterministic: same TikZ → same SVG (LuaLaTeX with fixed seed and fixed dvisvgm version).
- The scenario YAML schema (`evals/scenarios.py::_validate_scenarios`) and the property checker (`evals/sympy_checks.py`) are pure functions of the input — no nondeterminism in grading.

## 3.9 Known limitations of the verification toolkit

We document soft spots up front rather than be surprised by them in review:

1. **`point_on_segment` only checks collinearity, not bounds.** A point on the line *extending* segment AB will pass. This is intentional for altitude-foot scenarios where the foot can lie outside an obtuse triangle's base, but it is a true source of false positives elsewhere. Section 4 reports the impact.
2. **`label_present` and `mark_present` are TikZ-string checks.** A model that emits `\tkzMarkRightAngle(A,C,B)` passes the check even if the mark would visually clip off-canvas. These checks are intentionally classified as "soft" and contribute to `soft_pass`, not `pass`.
3. **`angle_equal` is currently a no-op.** Listed in the supported set but `_check_sympy_property` falls through to the default skip. We fix this in §4 hardening.
4. **No incidence checks for tangent point on circle.** The `tangent` predicate verifies the line is at radial distance r from the center but does not separately verify that T itself lies on the circle. Two-circle tangencies and internal-vs-external tangents are not distinguished.
5. **No 3D / solid-geometry checks.** Curriculum scenarios that mention cones / spheres exercise the renderer but cannot be symbolically verified by the current toolkit. We mark these as `soft_pass` in the most generous reading; in the headline metric they only count as pass if all *other* checks pass and no hard failures occur.
6. **Tolerance is fixed.** The `5×10⁻³` threshold was tuned for human-rating agreement on a small sample and is uniform across check types. Some checks may benefit from per-type tolerances (e.g., longer segments need looser absolute tolerance); we leave this for future work.
