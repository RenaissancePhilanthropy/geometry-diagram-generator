# Python Code Generation as the DSL Surface — Phase 1a Design (Shim + Executor)

**Status:** Approved for implementation planning
**Scope:** Phase 1a only — the builder shim, composite-op handles, executor/sandbox, stub generator, and retry loop, as standalone, independently testable units. Recipe translation and bench/A-B wiring (Phase 1b) are out of scope for this doc.
**Prereq context:** See the full experiment proposal (Phase 1/2, evaluation plan, success criteria) discussed in conversation; this doc covers only the Phase 1a implementation surface in detail.

## Goal of Phase 1a

Produce a working, testable pipeline stage that takes an LLM-shaped Python script (a sequence of calls into a fluent geometry-construction API) and turns it into a `DiagramIR` object — the exact same output shape `geometry_diagrams/recipe/lower.py` produces from the DSL today. Phase 1a does not touch recipe selection, prompt assembly for real LLM calls, or bench integration; it is validated with hand-written Python scripts standing in for LLM output.

```
Python script (string)
    → AST pre-pass (line tagging, fast-fail on obvious violations)
    → LocalPythonExecutor (restricted exec, import lockdown, timeout, op-count cap)
    → op trace, recorded by the ambient builder as it executes
    → DiagramIR   [same shape lower.py outputs today — Stage 4+ is unchanged]
```

## Components

### 1. Composite-op handles

Handles are thin typed wrappers around an internal, auto-generated id (never seen by the model). Returned by every public API function; composite ops expose their "parts" as accessors rather than requiring the model to re-derive them from raw point references.

In scope for Phase 1a (the ops needed by the recipes slated for Phase 1b translation — `parallel_transversal` plus at least one composite-op recipe):

| Handle | Constructed by | Accessors |
|---|---|---|
| `Point` | `point(x, y)`, or as an output of another op | — |
| `Line` / `Segment` | `line_through(...)`, `.side(...)` | — |
| `Triangle` | `triangle(A, B, C)` | `.vertices`, `.side(P, Q)` (order-independent), `.angle_at(V)` → `AngleRef` |
| `Polygon` | `polygon(A, B, C, ...)` | `.vertices`, `.side(V1, V2)` (raises if `V1`/`V2` not adjacent in vertex order — a structural, not geometric, check), `.angle_at(V)` |
| `Circle` | `circumcircle(T)`, `incircle(T)` | `.center` → `Point`, `.radius` |
| `Altitude` | `altitude(T, from_vertex=A)` | `.foot` → `Point`, `.line` → `Line` |
| `Median` | `median(T, from_vertex=A)` | `.midpoint` → `Point`, `.segment` → `Segment` |

Design rules:
- **`side()` is order-independent** (`T.side(A, B) is T.side(B, A)`), matching the DSL's existing side-key aliasing and removing a documented model-confusion source outright.
- **Output points are never named by the model.** `circ.center` / `alt.foot` are computed properties resolved to a hidden internal id when the op is recorded. The model's own variable name (`O = circ.center`) is a local Python binding for its own convenience — it never has to match a string threaded through two separate calls, and Python's own name-before-assignment semantics make "referenced before defined" structurally impossible, rather than a documented rule to remember (as it is in the DSL today).
- **Eager validation is structural only, never geometric.** `Polygon.side()`'s adjacency check only needs the vertex-order list, not coordinates, so it can run at call time. Self-intersecting/bowtie polygon order (the CLAUDE.md-documented failure mode) is NOT checked here — whether an order produces a bowtie depends on resolved coordinates, which don't exist yet when the Python script runs. That check stays exactly where it lives today, in `checks.py`/`to_sympy.py` post-lowering, for both the DSL and this new surface.
- Not in scope for Phase 1a: `centroid`, `angle_bisector`, `perpendicular_bisector`, `regular_polygon` and other catalog composite ops not needed by the recipes being translated. Extend the table above only if Phase 1b bench cases require it.

### 2. Builder shim (Task 1)

- **Ambient builder context:** a `contextvar`-backed builder instance, freshly created and reset before each script execution (one builder per `LocalPythonExecutor` call). Every public API function reads the current builder from the contextvar and appends the corresponding entry — no explicit builder argument threading in generated scripts.
- **Op-count cap:** enforced by the builder itself (not the AST layer) — every recorded call increments a counter; exceeding a generous ceiling (~2000, tunable) raises a clean error. This is the primary practical bound on script size; it's independent of and looser than the executor's own `MAX_OPERATIONS`/`MAX_WHILE_ITERATIONS`, which stay at library defaults as a backstop, not the main control.
- **Eager precondition validation — opportunistic, not universal.** An op like `intersection(L1, L2)` can be checked for "are these parallel" *only* when its inputs already resolve to concrete coordinates at call time (e.g. both lines were built from literal fixed points). When an input is itself downstream of an unresolved symbolic/constraint-solved point, there's nothing to check yet — same boundary as the polygon case above — and it falls through to the existing post-lowering checks, unchanged. The shim never claims to have validated something it structurally couldn't.
- **Did-you-mean:** module-level `__getattr__` over the public API namespace. On a call to an undefined name, `difflib.get_close_matches` against the real function list, raising `NameError("no function 'itnersection' — did you mean 'intersection'?")`. Self-repairing on the first retry for the most common hallucination class.
- **Output contract:** the builder assembles a `DiagramIR` object directly as ops are recorded — functionally the live-call equivalent of what `recipe/lower.py` does today from a parsed DSL structure. Stage 4 onward (SymPy resolution in `to_sympy.py`, `checks.py`, rendering) receives an identical input shape and requires no changes.

### 3. Stub generator (Task 2)

Since the "op definitions" are now the builder API functions and handle classes themselves (not a separate IR-definition list feeding a docs generator), the stub generator is pure introspection: walk the public API module via `inspect`, emit each function's signature + one-line docstring, and do the same for handle classes' public methods/properties (so `Triangle.side(P, Q) -> Segment` appears alongside `triangle(A, B, C) -> Triangle`). Output is signatures-and-docstrings text injected in place of `DSL_DOCS` during prompt assembly (Phase 1b) — LLM-readable stub text, not a strictly importable `.pyi` file. Single source of truth: a docstring or signature change updates the prompt automatically.

### 4. Executor & sandbox (Task 3)

- **Exec engine:** `smolagents.LocalPythonExecutor`, pinned `>=1.17.0` (fixes CVE-2025-5120 / GHSA-6v92-r5mx-h5fx). Configured with `authorized_imports=["math"]`; API functions injected via `send_tools()` as `static_tools` (the script cannot reassign them).
- **`while`, `Lambda`, `ClassDef` are left enabled.** No security reason to restrict them: `MAX_WHILE_ITERATIONS` (1M) and `MAX_EXECUTION_TIME_SECONDS` already bound runaway loops with a clean, catchable error, and lambdas only execute within the already-restricted namespace (no dunder access, no unauthorized imports) — there's no exploit surface they open that the executor's own dangerous-function blocklist and import allowlist don't already close.
- **Timeout:** `timeout_seconds` set per path — tight for the live-chat 2-retry budget, looser for offline batch.
- **Security posture is defense-in-depth, matching HuggingFace's own framing** ("no local python sandbox can ever be completely secure") — the AST pre-pass + executor whitelist is the primary control; least-privilege process permissions and, for the offline batch path, existing Docker infra with no network, sit behind it. This is unchanged from the original proposal's threat model, just now grounded in the executor's actual documented behavior rather than a hypothetical bespoke one.
- **Our `ast.walk()` pre-pass is UX only, not a security boundary.** Two jobs: (1) tag each API-call node with its source line number, so a downstream precondition error or `NameError` can report `"line 12: intersection(L1, L2): lines are parallel"` in the retry prompt; (2) fast-fail on constructs we already know the executor will reject (disallowed imports, `exec`/`eval`/`open`/`compile`) with a friendlier message before paying the cost of spinning up the interpreter. `LocalPythonExecutor`'s own whitelist remains the actual enforcement layer for everything else.

### 5. Retry loop (Task 4)

On AST pre-pass fast-fail, op precondition failure, `NameError` (including did-you-mean), or executor timeout: one retry (Phase 1a validates the mechanism with hand-authored failing scripts, not a live model), appending the exception message and the offending line (from the pre-pass's line tagging) to the prompt verbatim. Retry cause is logged by category (hallucinated API / geometric precondition / syntax-or-timeout) — this feeds the Phase 1b attribution analysis. Caps (informational for Phase 1a, load-bearing once prompt assembly exists in Phase 1b): **2 for live chat**, **5 for offline batch**.

## Testing (Phase 1a exit criteria)

Per project convention, each unit above is tested independently before integration:
- Handle/accessor unit tests: order-independence of `side()`, adjacency validation on `Polygon.side()`, correct hidden-id resolution for computed outputs (`circ.center`, `alt.foot`).
- Builder shim tests: op-count cap triggers correctly; eager precondition check fires when inputs are concrete and is silently skipped (not falsely passed) when inputs are symbolic; did-you-mean produces a sane suggestion for a representative set of typo'd op names.
- Executor tests: import of a non-`math` module is rejected; `exec`/`eval`/`open` calls are rejected; a deliberately infinite `while` loop is caught by the iteration cap or timeout, not left hanging; a valid hand-written script produces the correct `DiagramIR` end-to-end (verified by feeding it through unchanged `to_sympy.py`/`checks.py` and comparing to the equivalent DSL-authored diagram's output).
- Stub generator tests: generated stub text includes every public API function and handle accessor in the Phase 1a scope table, with no stale entries if a function is renamed.

Phase 1a is done when a hand-written Python script exercising every handle/op in the scope table above produces a `DiagramIR` that passes the existing SymPy checks identically to the equivalent hand-written DSL recipe — with no changes required to `to_sympy.py`, `checks.py`, `to_tikz.py`, or `to_svg.py`.

## Out of scope for this doc (Phase 1b)

Recipe translation (Task 5), bench integration and the `strategy: python_full` A/B run, mixed-mode/edit-sequence bench cases, majority-vote Tier 1 judge. See the original experiment proposal for the full evaluation plan and success criteria — unchanged by anything in this doc.
