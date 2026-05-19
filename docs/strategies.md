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

LLM generates `DiagramIR` JSON directly. Compile errors and check failures are fed back as retry context via a LangGraph `StateGraph` retry loop (up to `MAX_RETRIES=3`).

```mermaid
flowchart TD
    A([User Prompt]) --> B[LLM\nSTRUCTURED_STRATEGY_IR_INSTRUCTIONS\nwith_structured_output=DiagramIR]
    B --> C{IR Pipeline\ncompile → checks → render}
    C -->|success| D([SVG + DiagramIR + SymPy table])
    C -->|failure + error context| B
    B -->|max 3 attempts| E([Failure])
```

---

### `RecipeStrategy` (`strategies/recipe.py`)

The primary production strategy. Uses a cheap selector model to pick relevant recipes from a catalog, then generates a `RecipeDSL` that is lowered to `DiagramIR`. Orchestrated via a LangGraph `StateGraph`.

```mermaid
flowchart TD
    A([User Prompt]) --> C[Selector Node\ncheap model e.g. haiku\nselects recipe IDs from catalog]
    C --> D[Load matching\nRecipe objects]

    D --> F[DSL Generation Node\nRECIPE_GENERATION_SYSTEM\nwith_structured_output=RecipeDSL]

    F --> G{lower_to_ir\nRecipeDSL → DiagramIR}
    G -->|LoweringError| H[Re-prompt with\nerror + targeted hints]
    H --> F
    F -->|max 3 attempts| Z([Failure])

    G -->|success| I{IR Pipeline\ncompile → checks → render}
    I -->|compile/check/render error| H
    I -->|success| J([SVG + DiagramIR + recipe_metadata])
```

---

## Base Class (`strategies/base.py`)

```mermaid
classDiagram
    class SubstanceStrategy {
        +enable_cache: bool
        +build_agent(model) CompiledStateGraph
        +run(prompt, model, renderer) StructuredRunResult
    }

    SubstanceStrategy <|-- RawCodeStrategy
    SubstanceStrategy <|-- RawCodeWithReviseStrategy
    SubstanceStrategy <|-- RawSVGStrategy
    SubstanceStrategy <|-- RawSVGWithReviseStrategy
    SubstanceStrategy <|-- StructureStrategy
    SubstanceStrategy <|-- RecipeStrategy
```
