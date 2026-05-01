# Geometry Diagram Strategies

All strategies implement the `SubstanceStrategy` base class (`strategies/base.py`) and produce SVG output from a natural-language geometry prompt.

---

## Strategy Comparison

| Strategy | LLM Stages | IR Pipeline | Retry / Repair | Geometric Verification |
|---|---|---|---|---|
| `RawCodeStrategy` | 1 | No | Tool retries (3x) | None |
| `RawCodeWithReviseStrategy` | 2 | No | Mandatory revision pass | None |
| `RawSVGStrategy` | 1 | No | Tool retries (3x) | SVG format check |
| `RawSVGWithReviseStrategy` | 2 | No | Mandatory revision pass | SVG format check |
| `StructureStrategy` | 1 (retried) | Yes | Compile/check/render feedback | SymPy checks |
| `RecipeStrategy` | 1–2 (optional selector) | Yes | DSL + lowering feedback | SymPy checks |
| `PlanAndCodeStrategy` | 2 (plan → code) | No | Coordinate self-check | Property validation |
| `StructuredTwoPhaseStrategy` | 2 (plan → IR) | Yes | IR feedback | SymPy checks |
| `StructuredPlusRefineStrategy` | 1 + optional refine | Yes | Base IR + constraint check | Coord/label preservation |
| `ProgressiveToolsStrategy` | 4 (canvas/construct/checks/present) | Yes | Tool-based repair loop | Real-time SymPy checks |

---

## Raw Strategies

### `RawCodeStrategy` (`strategies/raw_code.py`)

The LLM writes TikZ code directly. No IR, no geometric verification.

```mermaid
flowchart TD
    A([User Prompt]) --> B[LLM Agent\nDRAFT_INSTRUCTIONS]
    B --> C{render_diagram tool\nup to 3 retries}
    C -->|TikZ code| D[render_tikz\nDocker container]
    D -->|success| E([SVG Output])
    D -->|error| C
    C -->|max retries| F([Failure])
```

---

### `RawCodeWithReviseStrategy` (`strategies/raw_code_with_revise.py`)

Two-pass TikZ generation: a draft agent followed by a mandatory revision agent that reviews and re-renders.

```mermaid
flowchart TD
    A([User Prompt]) --> B[Draft Agent\nDRAFT_INSTRUCTIONS]
    B --> C[render_diagram tool]
    C --> D[render_tikz\nDocker container]
    D --> E[Draft SVG]

    E --> F[Revision Agent\nREVISION_FORCE_INSTRUCTIONS\n+ message history]
    F --> G[render_diagram tool\nforce_rerender=True]
    G --> H[render_tikz\nDocker container]
    H -->|success| I([SVG Output])
    H -->|error| G
```

---

### `RawSVGStrategy` (`strategies/raw_svg.py`)

The LLM writes SVG directly. Validated only for well-formed `<svg>` element structure.

```mermaid
flowchart TD
    A([User Prompt]) --> B[LLM Agent\nDRAFT_INSTRUCTIONS]
    B --> C{register_svg_render_tool\nup to 3 retries}
    C -->|SVG string| D{Validate\n starts with svg tag}
    D -->|valid| E([SVG Output])
    D -->|invalid| C
    C -->|max retries| F([Failure])
```

---

### `RawSVGWithReviseStrategy` (`strategies/raw_svg_with_revise.py`)

Two-pass SVG generation with a mandatory revision agent.

```mermaid
flowchart TD
    A([User Prompt]) --> B[Draft Agent\nSVG DRAFT_INSTRUCTIONS]
    B --> C[register_svg_render_tool]
    C --> D{SVG valid?}
    D -->|yes| E[Draft SVG]
    D -->|no| C

    E --> F[Revision Agent\nREVISION_FORCE_INSTRUCTIONS\n+ message history]
    F --> G[register_svg_render_tool\nforce_rerender=True]
    G --> H{SVG valid?}
    H -->|yes| I([SVG Output])
    H -->|no| G
```

---

## IR-Based Strategies

These strategies share a common IR compilation pipeline once the LLM produces a `DiagramIR`:

```mermaid
flowchart LR
    IR[DiagramIR\nPydantic model] --> C[compile_defs\nSymPy symbol table]
    C --> K[run_checks\ngeometric invariants]
    K --> R[Renderer.render\nTikZ code generation]
    R --> D[Docker container\nlualatex → SVG]
    D --> SVG([SVG])
```

---

### `StructureStrategy` (`strategies/structured.py`)

LLM generates `DiagramIR` JSON directly. Compile errors and check failures are fed back as retry context.

```mermaid
flowchart TD
    A([User Prompt]) --> B[LLM Agent\nSTRUCTURED_STRATEGY_IR_INSTRUCTIONS\noutput_type=DiagramIR]
    B --> C{IR Pipeline\ncompile → checks → render}
    C -->|success| D([SVG + DiagramIR + SymPy table])
    C -->|failure + error context| B
    B -->|max 3 attempts| E([Failure])
```

---

### `RecipeStrategy` (`strategies/recipe.py`)

The primary production strategy. Optionally uses a cheap selector model to pick relevant recipes from a catalog, then generates a `RecipeDSL` that is lowered to `DiagramIR`.

```mermaid
flowchart TD
    A([User Prompt]) --> B{use_recipes?}

    B -->|yes| C[Selector Agent\ncheap model e.g. haiku\nselects recipe IDs from catalog]
    C --> D[Load matching\nRecipe objects]
    B -->|no| E[No recipes]

    D --> F[Generation Agent\nRECIPE_GENERATION_SYSTEM\noutput_type=RecipeDSL]
    E --> F

    F --> G{lower_to_ir\nRecipeDSL → DiagramIR}
    G -->|LoweringError| H[Re-prompt with\nerror + targeted hints]
    H --> F
    F -->|max 3 attempts| Z([Failure])

    G -->|success| I{IR Pipeline\ncompile → checks → render}
    I -->|compile/check/render error| H
    I -->|success| J([SVG + DiagramIR + recipe_metadata])
```

---

### `PlanAndCodeStrategy` (`strategies/plan_and_code.py`)

Two-stage: a planner produces a `GeometricPlan` with expected properties, then a coder generates TikZ and validates coordinate geometry against the plan.

```mermaid
flowchart TD
    A([User Prompt]) --> B[Planner Agent\noutput_type=GeometricPlan\npoints + constructions\n+ expected_properties]

    B --> C[Coder Agent\nCODE_FROM_PLAN_INSTRUCTIONS\n+ plan context]
    C --> D[render_diagram tool\nwith plan check]
    D --> E[render_tikz → TikZ compiled]
    E --> F[resolve_all_coordinates\nextract point coords]
    F --> G{validate_geometric_property\nfor each expected property}

    G -->|all pass| H([SVG Output])
    G -->|geometry failure\nup to 2 retries| D
    G -->|compile failure\nup to 2 retries| D

    D -->|render error| D
```

---

### `StructuredTwoPhaseStrategy` (`strategies/structured_two_phase.py`)

A natural-language `ConstructionPlan` is produced first, then translated to `DiagramIR`. Designed for head-to-head comparison with `StructureStrategy`.

```mermaid
flowchart TD
    A([User Prompt]) --> B[Phase 1: Planner Agent\nTWO_PHASE_PLANNER_INSTRUCTIONS\noutput_type=ConstructionPlan\nsteps + geometric_checks]

    B --> C[Phase 2: IR Agent\nSTRUCTURED_STRATEGY_IR_INSTRUCTIONS\n+ ConstructionPlan context\noutput_type=DiagramIR]

    C --> D{IR Pipeline\ncompile → checks → render}
    D -->|phase-2 failure| C
    C -->|max 3 attempts| E[Phase 1 retry]
    E --> B
    B -->|max 2 attempts| F([Failure])
    D -->|success| G([SVG + DiagramIR + SymPy table])
```

---

### `StructuredPlusRefineStrategy` (`strategies/structured_plus_refine.py`)

Runs `StructureStrategy` to get a verified TikZ base, then optionally runs a refinement agent to improve visual presentation. Falls back to the base result if refinement violates geometric constraints.

```mermaid
flowchart TD
    A([User Prompt]) --> B[StructureStrategy\nfull IR pipeline]
    B --> C{Refine enabled?}

    C -->|no| D([Base SVG])
    C -->|yes| E[Refinement Agent\nSTRUCTURED_REFINE_INSTRUCTIONS\n+ original TikZ]
    E --> F[render_diagram tool\nup to 2 retries]
    F --> G{Constraint check}

    G --> H{coords match\nlabels preserved\ncanvas features preserved}
    H -->|pass| I([Refined SVG])
    H -->|fail| J[Fall back to\nbase SVG]
    J --> D
```

---

### `ProgressiveToolsStrategy` (`strategies/progressive_tools/`)

A four-phase strategy where each phase has dedicated tools. Geometric checks happen in real-time during construction. A repair loop removes and re-adds failing objects.

```mermaid
flowchart TD
    A([User Prompt]) --> P1

    subgraph P1[Phase 1: Canvas]
        C1[Canvas Agent] --> T1[init_diagram tool\nset coordinate space]
        T1 --> S1[DiagramState.canvas\nxmin/xmax/ymin/ymax\ngrid/axes flags]
    end

    S1 --> P2

    subgraph P2[Phase 2: Construction loop]
        C2[Construction Agent] --> T2["add_point_* tools\nadd_segment / add_line\nadd_circle / add_polygon"]
        T2 --> FC[finalize_construction\ncompile_defs → SymPy SymTable]
        FC -->|compile error| R2[remove_definition\nre-add corrected object]
        R2 --> T2
        FC -->|success| S2[SymPy symbol table]
    end

    S2 --> P3

    subgraph P3[Phase 3: Checks]
        C3[Checks Agent] --> T3["add_*_check tools\ncollinear / parallel\nperpendicular / angle_equal\nequal_length / tangent…"]
        T3 --> FChk[finalize_checks\nrun_checks with SymPy]
        FChk -->|must-check fails\nclear sym + re-enter P2| P2
        FChk -->|all checks pass| S3[Validated geometry]
    end

    S3 --> P4

    subgraph P4[Phase 4: Presentation]
        C4[Presentation Agent] --> T4["draw / fill\nmark_angles / mark_right_angles\nlabel_point / label_segment…"]
        T4 --> FR[finalize_render\nTikZ generation → Docker SVG]
        FR --> SVG([SVG + phase traces\n+ token usage per phase])
    end
```

---

## Base Class (`strategies/base.py`)

```mermaid
classDiagram
    class SubstanceStrategy {
        +enable_cache: bool
        +build_agent(model) Agent
        +run(prompt, model, renderer) RunResult
        #cache_model_settings()
    }

    SubstanceStrategy <|-- RawCodeStrategy
    SubstanceStrategy <|-- RawCodeWithReviseStrategy
    SubstanceStrategy <|-- RawSVGStrategy
    SubstanceStrategy <|-- RawSVGWithReviseStrategy
    SubstanceStrategy <|-- StructureStrategy
    SubstanceStrategy <|-- RecipeStrategy
    SubstanceStrategy <|-- PlanAndCodeStrategy
    SubstanceStrategy <|-- StructuredTwoPhaseStrategy
    SubstanceStrategy <|-- StructuredPlusRefineStrategy
    SubstanceStrategy <|-- ProgressiveToolsStrategy
```
