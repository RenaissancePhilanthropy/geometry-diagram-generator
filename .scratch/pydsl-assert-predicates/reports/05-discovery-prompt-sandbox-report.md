# Ticket 05: Auto-discovery verification, prompt nudge, and sandbox proof

## Summary

All four checklist items implemented. Discovery items (1, 2) required zero
changes to `stub.py`/`retry.py` — confirmed via new tests. Item 3 adds one
short Rules paragraph to `instructions_python_full.py` plus a covering test.
Item 4 adds one sandbox-level test proving `GeometricAssertionError` survives
the real `LocalPythonExecutor` boundary classified as `"geometric_assertion"`.

## What was implemented

1. **`tests/test_pydsl_stub.py`** — added
   `test_stub_auto_discovers_all_24_assert_predicates_with_no_stub_code_change`:
   asserts `len(asserts.__all__) == 24`, and for each name asserts it's in
   `pydsl.__all__`, `def {name}(` appears in `generate_stub()`'s output, and
   the function's docstring first line appears in the stub text. Ran against
   the unmodified `stub.py` — passed immediately (no code change).

2. **`tests/test_pydsl_retry.py`** — added
   `test_public_api_function_names_auto_discovers_all_24_assert_predicates`:
   asserts every name in `asserts.__all__` is present in
   `retry.PUBLIC_API_FUNCTION_NAMES`. Ran against the unmodified `retry.py` —
   passed immediately (no code change).

3. **`geometry_diagrams/strategies/instructions_python_full.py`** —
   added one Rules-section paragraph encouraging `assert_*` usage after a
   construction step whose correctness isn't obvious from the construction
   alone, naming several concrete examples (`assert_distinct_points`,
   `assert_not_collinear`, `assert_right_angle`, `assert_equal_length`,
   `assert_similar_triangles`, `assert_in_canvas`) and explaining the
   fail-fast benefit. Placed as the second-to-last bullet, right before the
   closing "script is plain top-level statements" line, matching the
   existing bullet style/voice.

   **`tests/test_instructions_python_full.py`** — added
   `test_python_full_instructions_encourage_assert_usage_after_non_obvious_steps`,
   asserting the presence of the new paragraph's key phrases
   ("isn't obvious from the construction steps", `assert_distinct_points`,
   "raises immediately"). All pre-existing tests in this file (including the
   live-stub-sync test) still pass unchanged.

4. **`tests/test_pydsl_sandbox.py`** — added
   `test_geometric_assertion_error_survives_the_sandbox_boundary_correctly_classified`,
   placed immediately after the existing
   `test_structural_precondition_error_is_classified_correctly_with_no_suggestion`
   (copied its exact pattern: real `run_script()` call, no mocking, no fake
   `_child_argv`). Script constructs two coincident points and calls
   `assert_distinct_points(a, b)`. Asserts: `diagram_ir is None`,
   `"GeometricAssertionError"` appears in the surviving message text,
   `result.error_type == "geometric_assertion"`, and — re-derived directly —
   `classify_failure(result.error) == "geometric_assertion"` (proving the
   distinction survives the subprocess boundary as recoverable text, not
   just as an artifact of how `ScriptResult` was built), and no spurious
   "did you mean" suggestion.

## Tests + results

```
.venv/bin/python -m pytest tests/test_pydsl_stub.py tests/test_pydsl_retry.py -q
22 passed

.venv/bin/python -m pytest tests/test_instructions_python_full.py -q
8 passed

.venv/bin/python -m pytest tests/test_pydsl_sandbox.py -q
28 passed, 1 skipped (pre-existing skip, unrelated)

.venv/bin/python -m pytest tests/ -q
1904 passed, 48 skipped (pre-existing skips, unrelated to this change)
```

No test failures anywhere. The otel exporter connection-refused messages in
the full-suite output are pre-existing telemetry noise (no local collector
running on port 3000), not test failures.

## TDD evidence

- Items 1–2 were run against the *unmodified* `stub.py`/`retry.py` first and
  passed immediately — this is the expected "green without a code change"
  result the ticket predicts, and per the ticket's own instruction this
  confirms no code change was needed (not a red/green cycle, since there was
  nothing to fix).
- Items 3–4 were genuine red→green: I wrote the sandbox test against the
  code as it stood (asserts.py/retry.py from tickets 01–04, no prompt
  paragraph yet), confirmed it passes against the *existing*
  `GeometricAssertionError`/`classify_failure` machinery (already green,
  since that machinery already existed from ticket 02 — this ticket's new
  contribution is the test itself, proving the sandbox path specifically),
  then added the Rules paragraph and its test together and reran.

## Files changed

- `geometry_diagrams/strategies/instructions_python_full.py` — new Rules
  paragraph (prompt nudge)
- `tests/test_pydsl_stub.py` — new discovery test
- `tests/test_pydsl_retry.py` — new discovery test
- `tests/test_instructions_python_full.py` — new test for the nudge paragraph
- `tests/test_pydsl_sandbox.py` — new sandbox-boundary classification test

## Self-review findings

- **Completeness**: all 4 checklist items done; full suite passes.
- **Quality**: the nudge paragraph names concrete, varied `assert_*`
  examples (not just one), reuses vocabulary already established elsewhere
  in the Rules section (e.g. "raises immediately", mirroring the existing
  "raises an error" phrasing pattern used for `canvas()`), and doesn't
  restate any existing bullet's content — it's additive, not duplicative.
- **Testing — sandbox boundary**: verified the new test actually exercises
  `LocalPythonExecutor`, not a shortcut. It calls the real
  `sandbox.run_script()` with no `_child_argv` override (so the real
  `_sandbox_child.py` subprocess runs), and asserts on the *surviving message
  string* (`result.error`) containing `"GeometricAssertionError"` as text —
  which is only possible if `LocalPythonExecutor` actually wrapped the raised
  exception into an `InterpreterError` and the type name crossed the
  subprocess-queue boundary as embedded text, exactly the mechanism
  `retry.py`'s module docstring describes. This is not the same code path as
  the direct-exception unit tests in `test_pydsl_retry.py` (those construct
  `GeometricAssertionError` instances directly, in-process) — the new test
  is the only one in the suite exercising the assert-predicate failure
  through the actual subprocess sandbox.

## Concerns

None blocking. Two minor notes for the record:

- The discovery tests (items 1–2) necessarily can't "fail then pass" in the
  traditional TDD sense, since the underlying auto-discovery already worked
  before this ticket (that's the entire premise the ticket states up front).
  I treated "run first against unmodified code, confirm green with no
  changes" as satisfying the ticket's intent, per its own wording ("this
  ticket's job is to verify that with a test, not to write new discovery
  logic").
- I did not touch `stub.py` or `retry.py`'s candidate-pool logic, matching
  the ticket's explicit constraint.
