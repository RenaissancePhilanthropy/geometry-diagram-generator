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
| `AngleRef` | `Triangle.angle_at(V)`, `Polygon.angle_at(V)` | none — holds the `(a, o, b)` point-handle triple; only consumed as an argument to `mark_angle` and angle-equality checks, never introspected further |

Design rules:
- **`side()` is order-independent** (`T.side(A, B) is T.side(B, A)`), matching the DSL's existing side-key aliasing and removing a documented model-confusion source outright.
- **Output points are never named by the model.** `circ.center` / `alt.foot` are computed properties resolved to a hidden internal id when the op is recorded. The model's own variable name (`O = circ.center`) is a local Python binding for its own convenience — it never has to match a string threaded through two separate calls, and Python's own name-before-assignment semantics make "referenced before defined" structurally impossible, rather than a documented rule to remember (as it is in the DSL today).
- **Eager validation is structural only, never geometric — no exceptions, including in the builder itself (§2).** `Polygon.side()`'s adjacency check only needs the vertex-order list, not coordinates, so it can run at call time. Self-intersecting/bowtie polygon order (the CLAUDE.md-documented failure mode) is NOT checked here — whether an order produces a bowtie depends on resolved coordinates, which don't exist yet when the Python script runs. That check stays exactly where it lives today, in `checks.py`/`to_sympy.py` post-lowering, for both the DSL and this new surface. Phase 1a does **not** attempt opportunistic geometric checks even when inputs happen to be concrete (e.g. checking `intersection(L1, L2)` for parallelism when `L1`/`L2` come from literal fixed points) — that would require the shim to partially re-implement coordinate resolution and tolerance policy, duplicating and risking divergence from `checks.py`'s existing tolerance-based comparisons. All geometric validation, concrete or symbolic, happens exactly once, downstream, unchanged.
- Not in scope for Phase 1a: `centroid`, `angle_bisector`, `perpendicular_bisector`, `regular_polygon` and other catalog composite ops not needed by the recipes being translated. Extend the table above only if Phase 1b bench cases require it.

### 2. Builder shim (Task 1)

- **Ambient builder context:** a `contextvar`-backed builder instance, freshly created and reset before each script execution (one builder per `LocalPythonExecutor` call). Every public API function reads the current builder from the contextvar and appends the corresponding entry — no explicit builder argument threading in generated scripts.
- **Op-count cap:** enforced by the builder itself (not the AST layer) — every recorded call increments a counter; exceeding a generous ceiling (~2000, tunable) raises a clean error. This is the primary practical bound on script size; it's independent of and looser than the executor's own `MAX_OPERATIONS`/`MAX_WHILE_ITERATIONS`, which stay at library defaults as a backstop, not the main control.
- **Eager precondition validation — structural only, per the Task 0 rule above.** The builder validates things like argument arity, that referenced handles belong to the right op (e.g. `T.side(A, B)` requires `A`, `B` to be vertices of `T`), and adjacency for `Polygon.side()`. It performs no geometric checks (no parallelism, no distance, no angle comparison) regardless of whether inputs happen to be concrete — that's out of scope for 1a and stays downstream in `checks.py`, for both concrete and symbolic inputs alike.
- **Did-you-mean lives in the retry layer, not the shim.** A module-level `__getattr__` on the API namespace would never fire: generated scripts call bare names resolved through `LocalPythonExecutor`'s own tool/variable lookup, which never consults Python's normal module-attribute machinery. Instead, the retry loop (§5) catches the executor's own "name not defined" `InterpreterError`, runs `difflib.get_close_matches` against the registered `static_tools` name list, and appends the suggestion to the retry prompt — self-repairing on the first retry for the most common hallucination class, implemented where name resolution actually happens.
- **Output contract:** the builder assembles a `DiagramIR` object directly as ops are recorded — functionally the live-call equivalent of what `recipe/lower.py` does today from a parsed DSL structure. Stage 4 onward (SymPy resolution in `to_sympy.py`, `checks.py`, rendering) receives an identical input shape and requires no changes.

### 3. Stub generator (Task 2)

Since the "op definitions" are now the builder API functions and handle classes themselves (not a separate IR-definition list feeding a docs generator), the stub generator is pure introspection: walk the public API module via `inspect`, emit each function's signature + one-line docstring, and do the same for handle classes' public methods/properties (so `Triangle.side(P, Q) -> Segment` appears alongside `triangle(A, B, C) -> Triangle`). Output is signatures-and-docstrings text injected in place of `DSL_DOCS` during prompt assembly (Phase 1b) — LLM-readable stub text, not a strictly importable `.pyi` file. Single source of truth: a docstring or signature change updates the prompt automatically.

### 4. Executor & sandbox (Task 3)

- **Exec engine:** `smolagents.LocalPythonExecutor`, pinned `>=1.17.0` (fixes CVE-2025-5120 / GHSA-6v92-r5mx-h5fx). Constructor takes `additional_authorized_imports`, which is **unioned onto** a fixed `BASE_BUILTIN_MODULES` set (`collections`, `datetime`, `itertools`, `math`, `queue`, `random`, `re`, `stat`, `statistics`, `time`, `unicodedata`) — there is no public-API way to restrict below that 11-module base. We pass `additional_authorized_imports=[]` and accept the base set for 1a (no file/network access in it); if any of those modules prove exploitable or just noisy for this domain, revisit via subclassing. API functions injected via `send_tools()` as `static_tools` (the script cannot reassign them).
- **`while`, `Lambda`, `ClassDef` are left enabled.** No security reason to restrict them: `MAX_WHILE_ITERATIONS` (1M) and `MAX_OPERATIONS` (10M AST-eval steps) already bound runaway loops with a clean, catchable error, and lambdas only execute within the already-restricted namespace — there's no exploit surface they open that the executor's own dangerous-function blocklist and import allowlist don't already close.
- **Timeout is real but not a hard kill — this is the actual resource-exhaustion gap.** `LocalPythonExecutor(timeout_seconds=...)` runs the script in a `ThreadPoolExecutor` and raises on `future.result(timeout=...)`, but that only unblocks the *caller* — Python cannot forcibly terminate a running thread, so a script executing e.g. `math.factorial(10**8)` or allocating a huge list (one or two "operations," so invisible to `MAX_OPERATIONS`/`MAX_WHILE_ITERATIONS`) keeps consuming CPU/memory indefinitely as an orphaned thread even after the caller sees a timeout. Under this design's own threat model (LLM-generated code is untrusted, possibly adversarially steered), this kind of single-expression resource bomb is the realistic attack, not a sandbox escape. **Fix: run `LocalPythonExecutor` inside a subprocess with OS-level resource limits** (`RLIMIT_CPU`, `RLIMIT_AS` via `resource.setrlimit`, or an equivalent `multiprocessing` worker) and a hard `SIGKILL` on timeout, for both the live-chat and offline-batch paths — not a thread-based timeout alone.
- **Isolation applies to both paths, not just batch.** The original proposal put Docker-with-no-network only on the offline-batch path, reasoning that live chat needed lower latency. Given CVE-2025-5120 is exactly the "whitelisted-module sandbox escape" bug class, and live chat is the path exposed to adversarial prompt injection, both paths run the executor in the subprocess+rlimits sandbox above at minimum; the offline-batch path additionally runs inside existing Docker infra with no network, as a second layer beyond (not instead of) subprocess isolation.
- **Our `ast.walk()` pre-pass's line-tagging job may be redundant — verify before building it.** `LocalPythonExecutor`'s own `InterpreterError`s already carry source/line context from the AST node being evaluated. Build the pre-pass's fast-fail job (rejecting known-bad imports/dangerous calls with a friendlier message before spinning up the interpreter) as planned, but only add explicit line-tagging on top if the executor's native error context proves insufficient in practice. Either way, this pre-pass is UX only, never the security boundary — `LocalPythonExecutor`'s own whitelist is.

### 5. Retry loop (Task 4)

On AST pre-pass fast-fail, op precondition failure, an executor "name not defined" error, or executor timeout: one retry (Phase 1a validates the mechanism with hand-authored failing scripts, not a live model), appending the exception message (plus a did-you-mean suggestion for name errors, per §2) to the prompt verbatim. Retry cause is logged by category (hallucinated API / structural precondition / syntax-or-timeout) — this feeds the Phase 1b attribution analysis. Caps (informational for Phase 1a, load-bearing once prompt assembly exists in Phase 1b): **2 for live chat**, **5 for offline batch**.

## Testing (Phase 1a exit criteria)

Per project convention, each unit above is tested independently before integration:
- Handle/accessor unit tests: order-independence of `side()`, adjacency validation on `Polygon.side()`, correct hidden-id resolution for computed outputs (`circ.center`, `alt.foot`), membership validation raises for handles from the wrong construction.
- Builder shim tests: op-count cap triggers correctly; structural precondition checks fire for arity/membership/adjacency violations and never attempt a geometric check regardless of whether inputs are concrete; **contextvar/builder isolation across sequential executions** — running script N then script N+1 in the same process produces two independent `DiagramIR`s with no leaked ops from N into N+1 (a plausible failure mode of the ambient-builder design, not exercised by any other test here).
- Executor tests: import of a module outside `BASE_BUILTIN_MODULES` is rejected; `exec`/`eval`/`open` calls are rejected; a deliberately infinite `while` loop is caught by the iteration cap; **a CPU-bomb (`math.factorial(10**8)` or similar) and a memory-bomb (large list allocation) are both killed by the subprocess rlimit/timeout wrapper**, not just by the executor's own counters, which don't cover single-expression cost; a valid hand-written script produces the correct `DiagramIR` end-to-end (verified by feeding it through unchanged `to_sympy.py`/`checks.py` and comparing to the equivalent DSL-authored diagram's output); did-you-mean is tested **through the executor** (a typo'd op name in a real script produces the suggested-name message via the retry-layer catch, not just via a unit-level `difflib` call).
- Stub generator tests: generated stub text includes every public API function and handle accessor in the Phase 1a scope table; a function *not* registered as public API does not appear in the stub (the meaningful direction of the staleness check — the reverse, "renaming doesn't leave stale entries," is vacuous under pure introspection and isn't a useful test).
- Retry loop tests (previously missing from this section): exception message and did-you-mean suggestion actually land in the constructed retry prompt text; retry-cause category logging matches the actual failure type across a representative set of AST/precondition/name/timeout failures; retry cap is enforced (a script that fails every attempt stops after the configured cap, not before or after).

Phase 1a is done when a hand-written Python script exercising every handle/op in the scope table above produces a `DiagramIR` that passes the existing SymPy checks identically to the equivalent hand-written DSL recipe — with no changes required to `to_sympy.py`, `checks.py`, `to_tikz.py`, or `to_svg.py`.

## Out of scope for this doc (Phase 1b)

Recipe translation (Task 5), bench integration and the `strategy: python_full` A/B run, mixed-mode/edit-sequence bench cases, majority-vote Tier 1 judge. See the original experiment proposal for the full evaluation plan and success criteria — unchanged by anything in this doc.
