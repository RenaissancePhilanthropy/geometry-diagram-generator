# Templated Eval Scenarios

A deterministic, template-based generator for geometry eval scenarios across
three difficulty tiers (easy / medium / hard).

- **Generator**: `evals/generate_scenarios.py`
- **Default output**: `evals/scenarios_generated.yaml`
- **Default scale**: 600 scenarios (200 per tier), drawn from a pool of 766
- **Templates**: 30 (9 tier-1, 10 tier-2, 11 tier-3)
- **Validation**: every scenario passes `evals.scenarios._validate_scenarios` before write

## Why templates instead of LLM-authored prompts

Each template defines the **prompt prose and the `expected_properties`
together** from the same source. That means:

- Ground truth is provably consistent with the prompt — no LLM-hallucinated
  check args.
- Reproducible — same seed produces same output across runs.
- Cheap — generation runs in ~250ms with no API calls.
- Easy to extend — new constructions are added as small Python functions.

This complements (rather than replaces) `curriculum/generate_prompts.py`,
which produces LLM-authored scenarios from textbook content — those are
broader in topic coverage but can have noisier ground truth.

## Difficulty tiers

| Tier | Description | Examples |
|---|---|---|
| **1 — easy** | Single named shape, no auxiliary construction | right triangle, equilateral, isosceles, square, rectangle, segment + midpoint, parallel/perpendicular segments, circle with point |
| **2 — medium** | One shape plus one auxiliary construction | triangle + altitude / median / angle bisector / circumcircle / incircle, perpendicular bisector, parallelogram, rhombus, trapezoid, chord in circle |
| **3 — hard** | Multi-step or composed construction | right triangle altitude to hypotenuse, medial triangle, centroid + medians, parallel lines + transversal, isosceles altitude bisects base, tangent to circle, cyclic quadrilateral, two intersecting circles, Thales' theorem (right angle inscribed in semicircle), triangle with two altitudes, inscribed angle in semicircle |

## Variation axes

Each template multiplies along one or more of:

- **Label sets** — 10 vertex triples, 6 quads, 8 pairs (e.g. `ABC`, `PQR`, `XYZ`, `EFG`, …) so prompts don't always read "ABC".
- **Numeric parameters** — Pythagorean leg pairs `[(3,4), (5,12), (6,8), …]`, equilateral side lengths, isosceles `(leg, base)` pairs, square sides, rectangle `width × height`, acute-triangle angle specs, circle radii.
- **Phrasing** — rotates 7 openers: `Draw`, `Sketch`, `Construct`, `Make a diagram of`, `Show`, `Create a diagram showing`, `I need a drawing of`.

The aux-point picker `_free_label(used, prefer=[…])` automatically chooses a
non-conflicting single-letter name (e.g. `H` for an altitude foot when the
triangle is `ABC`, but `M` when the triangle is `XYZ`).

## Property-check coverage

The generator emits scenarios using these check types from
`evals/scenarios.py`:

`right_angle`, `midpoint`, `collinear`, `equal_lengths`, `parallel`,
`perpendicular`, `point_on_line`, `point_on_segment`, `point_on_circle`,
`tangent`, `angle_equal`, `angle_bisector`, `mark_present`,
`equidistant_from_sides`, `centroid`.

All check argument shapes match the signatures expected by
`evals/sympy_checks.py` and `util/tikz_geometry.py`.

## Usage

```bash
# Default — 600 scenarios into evals/scenarios_generated.yaml
.venv/bin/python evals/generate_scenarios.py

# Validate without writing
.venv/bin/python evals/generate_scenarios.py --dry-run

# Single tier
.venv/bin/python evals/generate_scenarios.py --tier 2

# All raw scenarios (no cap; ~766 total)
.venv/bin/python evals/generate_scenarios.py --cap-per-tier 0

# Three separate files: scenarios_easy/medium/hard.yaml
.venv/bin/python evals/generate_scenarios.py --split-by-tier

# Custom path + custom cap
.venv/bin/python evals/generate_scenarios.py \
    --output evals/scenarios_quick.yaml --cap-per-tier 30
```

## Running evals against the generated set

```bash
uv run python -m evals.run \
  --scenarios evals/scenarios_generated.yaml \
  --strategies recipe \
  --model anthropic:claude-sonnet-4-6 \
  --repeats 1 \
  --output evals/results
```

For a quick smoke check, prefer a single tier or a small cap — running 600
scenarios against an LLM strategy is non-trivial in time and tokens.

## Adding a new template

A template is a function that yields scenario dicts. Add the function near
its tier section in `evals/generate_scenarios.py` and append it to the
`_TEMPLATES` list.

Skeleton:

```python
def t2_my_construction() -> Iterator[dict]:
    idx = 0
    for (a, b, c) in _TRIPLE_LABELS:
        for param in [...]:
            aux = _free_label({a, b, c}, prefer=["H", "K"])
            yield _scenario(
                id=f"tpl-t2-mycon-{a}{b}{c}-{aux}-{param}",
                tier=2,
                tags=["triangle", "my-construction"],
                prompt=(
                    f"{_opener(idx)} a triangle {a}{b}{c} with [param]={param}. "
                    f"... full description ..."
                ),
                required_labels=[a, b, c, aux],
                expected_properties=[
                    {"name": "...", "type": "right_angle", "args": [a, aux, b]},
                    # one entry per geometric invariant the construction guarantees
                ],
            )
            idx += 1
```

Then:

```python
_TEMPLATES: list[Callable[[], Iterator[dict]]] = [
    ...,
    t2_my_construction,
    ...,
]
```

Run `--dry-run` after adding — `_validate_scenarios()` will surface any
schema mistakes (unsupported property type, malformed args, duplicate id,
etc.) before the YAML is written.

### Tips for writing good templates

- Use only check types listed in `evals/scenarios.py::_SUPPORTED_PROPERTY_TYPES`.
- Match the exact argument signatures in `evals/sympy_checks.py` (e.g. `right_angle` takes `[arm1, vertex, arm2]`; `midpoint` takes `[M, A, B]`; `point_on_circle` takes `[P, center, radius_point]`).
- For altitudes, prefer **acute** triangles so the foot lies on the segment (not on the extended line).
- IDs must be unique across the entire output; embed the parameter values that vary so the IDs are distinct.
- Keep prompts specific enough to verify — concrete labels, lengths, angles, or relationships (parallel, perpendicular, equal). Vague prompts can't be checked.

## Files

- `evals/generate_scenarios.py` — generator (~30 templates)
- `evals/scenarios_generated.yaml` — generated output (600 scenarios)
- `evals/scenarios.py` — schema validation (shared with all scenario files)
- `evals/sympy_checks.py` — geometric check implementations
- `util/tikz_geometry.py` — `mark_present` / `label_present` validators
