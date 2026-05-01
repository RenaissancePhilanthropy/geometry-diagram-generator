# Scenario Data Review — Curriculum Team Request

This document describes data quality issues found in
`evals/scenarios_geometry_curriculum.yaml` and what changes are needed
in the generation pipeline for the next regeneration pass.

**Status of each class:**
- Section 1: needs upstream fixes (pipeline + data)
- Section 2: already handled in `curriculum/to_benchmark.py` — no action needed
- Section 3: keeping by design

---

## Section 1: Upstream fixes needed

### 1a. `generate_prompts.py` — system prompt improvements

The current system prompt says only:
```
- mark_present: [mark_type, point] — visual mark present
```

This leaves `mark_type` undefined, so the LLM invents its own names.
Please add an explicit enumeration and clarify that `mark_present` is for
**visual annotation marks only**, not geometric concepts:

```
- mark_present: [mark_type, point] — visual annotation mark present
  Valid mark_type values:
    right_angle        — small square at a right-angle vertex
    tick               — single tick mark on a segment (congruence)
    double_tick        — double tick mark on a segment
    triple_tick        — triple tick mark on a segment
    arc                — single angle arc at a vertex
    double_arc         — double angle arc at a vertex
  Do NOT use mark_present for concepts like 'midpoint', 'radius',
  'slant_height'. Use midpoint/label_present instead.
```

### 1b. Specific scenario data to fix

#### Wrong geometry: `point_on_segment` where the point is the right-angle vertex

| Scenario | Property | Args | Fix |
|----------|----------|------|-----|
| `geo-m4-t2-l4-tt-cone-slant-height-1` | `slant_height_VA` | `[O, V, A]` | Remove — `right_angle(V, O, A)` already present; O is a vertex, not on VA |

#### Conceptual `mark_present` misuse (11 midpoint marks + 5 others)

These should be `midpoint` property checks or `label_present`, not `mark_present`.

**Midpoint marks** — convert to `midpoint` property (need parent segment endpoints):

| Scenario | Property | Args | Suggested fix |
|----------|----------|------|---------------|
| `geo-m2-t1-l2-a4-midsegment-quadrilateral-1` | `E_mark` | `('midpoint', 'E')` | `midpoint [E, X, Y]` — check prompt for parent segment endpoints |
| `geo-m2-t1-l2-a4-midsegment-quadrilateral-1` | `F_mark` | `('midpoint', 'F')` | `midpoint [F, X, Y]` — check prompt for parent segment endpoints |
| `geo-m2-t1-l2-a4-midsegment-quadrilateral-1` | `G_mark` | `('midpoint', 'G')` | `midpoint [G, X, Y]` — check prompt for parent segment endpoints |
| `geo-m2-t1-l2-a4-midsegment-quadrilateral-1` | `H_mark` | `('midpoint', 'H')` | `midpoint [H, X, Y]` — check prompt for parent segment endpoints |
| `geo-m2-t1-l2-a4-trapezoid-midsegment-2` | `M_mark` | `('midpoint', 'M')` | `midpoint [M, X, Y]` — check prompt for parent segment endpoints |
| `geo-m2-t1-l2-a4-trapezoid-midsegment-2` | `N_mark` | `('midpoint', 'N')` | `midpoint [N, X, Y]` — check prompt for parent segment endpoints |
| `geo-m2-t1-l4-a3-triangle-midsegment-1` | `M_mark` | `('midpoint', 'M')` | `midpoint [M, X, Y]` — check prompt for parent segment endpoints |
| `geo-m2-t1-l4-a3-triangle-midsegment-1` | `N_mark` | `('midpoint', 'N')` | `midpoint [N, X, Y]` — check prompt for parent segment endpoints |
| `geo-m2-t1-l5-a3-centroid-triangle-1` | `D_mark` | `('midpoint', 'D')` | `midpoint [D, X, Y]` — check prompt for parent segment endpoints |
| `geo-m2-t1-l5-a3-centroid-triangle-1` | `E_mark` | `('midpoint', 'E')` | `midpoint [E, X, Y]` — check prompt for parent segment endpoints |
| `geo-m2-t1-l5-a3-centroid-triangle-1` | `F_mark` | `('midpoint', 'F')` | `midpoint [F, X, Y]` — check prompt for parent segment endpoints |

**Other conceptual marks** — convert or remove:

| Scenario | Property | Args | Suggested fix |
|----------|----------|------|---------------|
| `geo-m4-t2-l1-a14-cylinder-disc-stack-1` | `disc_cross_section_circle` | `('cross_section', 'O')` | Remove (not a verifiable visual mark) |
| `geo-m4-t2-l1-gs-disc-definition-2` | `radius_marked` | `('radius', 'O')` | `label_present ['O']` |
| `geo-m4-t2-l2-a22-sphere-cross-sections-1` | `radius_marked` | `('radius', 'O')` | `label_present ['O']` |
| `geo-m4-t2-l4-a41-cone-net-1` | `pythagorean_sides` | `('slant_height', 's')` | `label_present ['s']` |
| `geo-m4-t2-l4-a41-cylinder-net-1` | `rectangle_width_equals_circumference` | `('circumference_label', 'rectangle_top')` | Remove (not a verifiable visual mark) |

---

## Section 2: Handled in `to_benchmark.py` — no action needed

The following 19 properties use non-canonical but recognizable mark type names.
`curriculum/to_benchmark.py` normalizes all of these to clear rubric questions
automatically. No changes required in the scenario data, but future regenerations
should use canonical names (see Section 1a).

| Scenario | Tier | Property | Args | Normalized to |
|----------|------|----------|------|---------------|
| `geo-m1-t3-l3-act33-angle-bisector-construction-1` | 1 | `mark_angle_ABD` | `('arc', 'B')` | "Is an angle arc mark drawn at …?" |
| `geo-m1-t3-l4-gs-rotation-function-1` | 1 | `mark_rotation_angle` | `('arc', 'E')` | "Is an angle arc mark drawn at …?" |
| `geo-m1-t3-l4-ttt-270-rotation-triangle-1` | 2 | `mark_rotation_arc` | `('arc', 'O')` | "Is an angle arc mark drawn at …?" |
| `geo-m1-t4-l1-equilateral-triangle-symmetry-1` | 2 | `tick_marks_equal_sides` | `('tick1', 'A')` | "Is a single tick mark drawn on the segment at …?" |
| `geo-m1-t4-l1-scalene-right-triangle-symmetry-1` | 1 | `all_sides_different_AC` | `('tick1', 'A')` | "Is a single tick mark drawn on the segment at …?" |
| `geo-m1-t4-l1-scalene-right-triangle-symmetry-1` | 1 | `all_sides_different_BC` | `('tick2', 'B')` | "Is a double tick mark drawn on the segment at …?" |
| `geo-m2-t2-l3-a33-exterior-angles-polygon-1` | 2 | `exterior_angle_at_A` | `('arc', 'A')` | "Is an angle arc mark drawn at …?" |
| `geo-m2-t2-l3-a33-exterior-angles-polygon-1` | 2 | `exterior_angle_at_B` | `('arc', 'B')` | "Is an angle arc mark drawn at …?" |
| `geo-m2-t2-l3-a33-exterior-angles-polygon-1` | 2 | `exterior_angle_at_C` | `('arc', 'C')` | "Is an angle arc mark drawn at …?" |
| `geo-m2-t2-l3-a33-exterior-angles-polygon-1` | 2 | `exterior_angle_at_D` | `('arc', 'D')` | "Is an angle arc mark drawn at …?" |
| `geo-m2-t2-l3-a33-exterior-angles-polygon-1` | 2 | `exterior_angle_at_E` | `('arc', 'E')` | "Is an angle arc mark drawn at …?" |
| `geo-m3-t1-l1-act14-similar-triangles-corresponding-parts-1` | 2 | `mark_present_A` | `('angle_single', 'A')` | "Is an angle arc mark drawn at …?" |
| `geo-m3-t1-l1-act14-similar-triangles-corresponding-parts-1` | 2 | `mark_present_D` | `('angle_single', 'D')` | "Is an angle arc mark drawn at …?" |
| `geo-m3-t1-l1-act14-similar-triangles-corresponding-parts-1` | 2 | `mark_present_B` | `('angle_double', 'B')` | "Is a double angle arc mark drawn at …?" |
| `geo-m3-t1-l1-act14-similar-triangles-corresponding-parts-1` | 2 | `mark_present_E` | `('angle_double', 'E')` | "Is a double angle arc mark drawn at …?" |
| `geo-m3-t1-l2-act22-sss-similarity-proportional-sides-1` | 2 | `mark_AB_DE_equal_ratio` | `('tick_single', 'AB')` | "Is a single tick mark drawn on the segment at …?" |
| `geo-m3-t1-l2-act22-sss-similarity-proportional-sides-1` | 2 | `mark_DE_single` | `('tick_single', 'DE')` | "Is a single tick mark drawn on the segment at …?" |
| `geo-m3-t1-l2-act22-sss-similarity-proportional-sides-1` | 2 | `mark_BC_double` | `('tick_double', 'BC')` | "Is a double tick mark drawn on the segment at …?" |
| `geo-m3-t1-l2-act22-sss-similarity-proportional-sides-1` | 2 | `mark_EF_double` | `('tick_double', 'EF')` | "Is a double tick mark drawn on the segment at …?" |
| `geo-m3-t1-l2-act22-sss-similarity-proportional-sides-1` | 2 | `mark_AC_triple` | `('tick_triple', 'AC')` | "Is a triple tick mark drawn on the segment at …?" |
| `geo-m3-t1-l2-act22-sss-similarity-proportional-sides-1` | 2 | `mark_DF_triple` | `('tick_triple', 'DF')` | "Is a triple tick mark drawn on the segment at …?" |
| `geo-m3-t1-l2-act23-sas-similarity-included-angle-1` | 2 | `mark_angle_A` | `('angle_single', 'A')` | "Is an angle arc mark drawn at …?" |
| `geo-m3-t1-l2-act23-sas-similarity-included-angle-1` | 2 | `mark_angle_D` | `('angle_single', 'D')` | "Is an angle arc mark drawn at …?" |
| `geo-m3-t1-l2-act23-sas-similarity-included-angle-1` | 2 | `mark_AB_single` | `('tick_single', 'AB')` | "Is a single tick mark drawn on the segment at …?" |
| `geo-m3-t1-l2-act23-sas-similarity-included-angle-1` | 2 | `mark_DE_single` | `('tick_single', 'DE')` | "Is a single tick mark drawn on the segment at …?" |
| `geo-m3-t1-l2-act23-sas-similarity-included-angle-1` | 2 | `mark_AC_double` | `('tick_double', 'AC')` | "Is a double tick mark drawn on the segment at …?" |
| `geo-m3-t1-l2-act23-sas-similarity-included-angle-1` | 2 | `mark_DF_double` | `('tick_double', 'DF')` | "Is a double tick mark drawn on the segment at …?" |

---

## Section 3: Keeping by design — tautological `point_on_segment`

13 properties assert that a point is an endpoint of a segment
(e.g. `point_on_segment(C, C, D)`). These are trivially true for our pipeline,
but are kept intentionally: they provide meaningful signal when evaluating
other generators (diffusion models, etc.) that may not reliably place endpoints
on their own segments. This is consistent with GenExam rubric items like
"Is there a triangle drawn?" which serve the same purpose.

| Scenario | Tier | Property | Args |
|----------|------|----------|------|
| `geo-m1-t1-l1-a12-ray-vs-segment-1` | 1 | `C_endpoint_of_segment` | `[C, C, D]` |
| `geo-m1-t1-l1-a12-ray-vs-segment-1` | 1 | `D_endpoint_of_segment` | `[D, C, D]` |
| `geo-m1-t1-l3-a33-three-squares-diagonals-1` | 2 | `AP_segment_drawn` | `[P, A, P]` |
| `geo-m1-t1-l3-a33-three-squares-diagonals-1` | 2 | `AQ_segment_drawn` | `[Q, A, Q]` |
| `geo-m1-t1-l3-a33-three-squares-diagonals-1` | 2 | `AR_segment_drawn` | `[R, A, R]` |
| `geo-m1-t1-l3-a35-auxiliary-lines-grid-1` | 3 | `AI_segment_auxiliary` | `[I, A, I]` |
| `geo-m1-t1-l3-a35-auxiliary-lines-grid-1` | 3 | `AK_segment_auxiliary` | `[K, A, K]` |
| `geo-m1-t4-l1-isosceles-trapezoid-symmetry-1` | 1 | `M_on_line_MN` | `[M, M, N]` |
| `geo-m1-t4-l1-isosceles-trapezoid-symmetry-1` | 1 | `N_on_line_MN` | `[N, M, N]` |
| `geo-m2-t2-l3-a32-polygon-diagonals-1` | 2 | `diagonal_AC_quad` | `[A, A, C]` |
| `geo-m2-t2-l3-a32-polygon-diagonals-1` | 2 | `diagonal_AC_pent` | `[A, A, C]` |
| `geo-m2-t2-l3-a32-polygon-diagonals-1` | 2 | `diagonal_AD_pent` | `[A, A, D]` |
| `geo-m2-t3-l3-a4-proving-parallelogram-from-sides-1` | 2 | `diagonal_AC_drawn` | `[A, A, C]` |
