"""The gate: which of a record's deterministic checks fail it, are skipped, or pass.

Pure functions over the eval record dict (no model, renderer or geometry imports), shared by
the runner (``evals/run.py``) and ``evals/regrade.py``, so a regraded record is judged by the
same rule as a fresh one:

- ``collect_check_outcomes(record)`` -> ``(failures, skipped, had_checks)``;
- ``finalize_gate_status(record)`` sets ``deterministic_pass``, ``gate_failures`` and
  ``gate_status`` (``pass`` / ``soft_pass`` when a check was skipped / ``fail``);
- ``property_gate_failures(results)`` -> the ``property:<name>`` gate entries.
"""
from __future__ import annotations


def property_gate_failures(
    results: list[dict], already_failed: "set[str] | list[str]" = (), gate: bool = True,
) -> tuple[list[str], list[str]]:
    """The ``(failures, skipped)`` gate entries of a record's ``sympy_property_checks``.

    A skipped check (``passed`` None, e.g. an unsupported type) is never a pass. With
    ``gate`` a failed one is ``property:<name>``, plus ``:unresolved`` / ``:ambiguous``
    when a point name was the problem (kept apart from a geometry failure), unless
    ``already_failed`` has the same property's name (the tikz check of it failed too).
    """
    failures: list[str] = []
    skipped: list[str] = []
    for r in results or []:
        name = r.get("name", "")
        if r.get("passed") is None:
            skipped.append(f"property:{name}")
        elif gate and r.get("passed") is False and name not in already_failed:
            failures.append(f"property:{name}" + (f":{r['resolution']}" if r.get("resolution") else ""))
    return failures, skipped


def collect_check_outcomes(
    record: dict, gate_properties: bool = True
) -> tuple[list[str], list[str], bool]:
    """Return (failures, skipped, had_checks) across deterministic checks.

    ``gate_properties``: a failed ``expected_properties`` check on the compiled
    geometry (``sympy_property_checks``) adds a ``property:<name>`` failure;
    off, such a failure is recorded but does not gate (the behaviour before the
    flag, used to compare old runs)."""
    failures: list[str] = []
    skipped: list[str] = []
    had_checks = False

    for name, result in (record.get("tikz_checks") or {}).items():
        if not isinstance(result, dict):
            continue
        had_checks = True
        passed = result.get("passed")
        if passed is False:
            failures.append(name)
        elif passed is not True and result.get("error"):
            # The check could not be evaluated (it raised): a broken check is
            # not a deliberate skip, so it must not soft-pass the gate.
            failures.append(f"{name}:error")
        elif result.get("skipped") is True or passed is None:
            skipped.append(name)

    canvas_checks = record.get("canvas_checks")
    if isinstance(canvas_checks, dict):
        had_checks = True
        if not canvas_checks.get("passed", False):
            missing = canvas_checks.get("missing") or ["required_canvas"]
            failures.extend(f"canvas:{name}" for name in missing)

    expected_point_checks = record.get("expected_point_checks")
    if isinstance(expected_point_checks, dict):
        had_checks = True
        failures.extend(f"point:{name}:missing" for name in expected_point_checks.get("missing", []))
        failures.extend(
            f"point:{name}:mismatch"
            for name in sorted((expected_point_checks.get("mismatches") or {}).keys())
        )

    structural_checks = record.get("structural_checks")
    if isinstance(structural_checks, dict):
        had_checks = True
        for name, result in structural_checks.items():
            if isinstance(result, dict) and result.get("passed") is False:
                failures.append(f"structural:{name}" + (f":{result['resolution']}" if result.get("resolution") else ""))
            elif isinstance(result, dict) and result.get("passed") is None:
                skipped.append(f"structural:{name}")

    # Property checks of an unsupported type: not evaluated, so never a pass.
    property_results = record.get("sympy_property_checks") or []
    prop_failures, prop_skipped = property_gate_failures(property_results, set(failures), gate_properties)
    failures.extend(prop_failures)
    skipped.extend(prop_skipped)
    if property_results and (gate_properties or prop_skipped):
        had_checks = True

    prism_checks = record.get("prism_property_checks")
    if prism_checks:
        had_checks = True
        failures.extend(f"prism:{r['name']}" for r in prism_checks if r.get("passed") is False)

    stack_checks = record.get("stack_property_checks")
    if stack_checks:
        had_checks = True
        failures.extend(f"stack:{r['name']}" for r in stack_checks if r.get("passed") is False)

    query_results = record.get("query_results", [])
    if query_results:
        had_checks = True
        for qidx, qr in enumerate(query_results):
            if qr.get("error"):
                failures.append(f"query:{qidx}:error")
            elif not qr.get("tool_called"):
                failures.append(f"query:{qidx}:tool_not_called")
            elif qr.get("query_type_match") is False:
                failures.append(f"query:{qidx}:wrong_query_type")

    return failures, skipped, had_checks


def finalize_gate_status(
    record: dict, fail_on_warnings: list[str] | None = None, gate_properties: bool = True,
) -> None:
    """Populate deterministic_pass, gate_status, and gate_failures.

    ``fail_on_warnings``: scenario substrings; each one found (case-sensitive)
    in any recorded warning adds one ``warning:<substring>`` gate failure.
    ``gate_properties``: see ``collect_check_outcomes``.
    """
    failures, skipped, had_checks = collect_check_outcomes(record, gate_properties)

    if failures:
        record["deterministic_pass"] = False
    elif skipped:
        record["deterministic_pass"] = None
    else:
        record["deterministic_pass"] = True if had_checks or record.get("tikz_code") else None

    gate_failures: list[str] = []
    if not record.get("generation_success"):
        gate_failures.append("generation")
    if not record.get("svg_rendered"):
        gate_failures.append("svg_render")
    svg_checks = record.get("svg_checks")
    if svg_checks and not svg_checks.get("passed", False):
        for failure in svg_checks.get("failures", []):
            gate_failures.append(f"svg:{failure}")
    gate_failures.extend(failures)
    recorded = record.get("warnings") or []
    for sub in fail_on_warnings or []:
        if any(sub in w for w in recorded):
            gate_failures.append(f"warning:{sub}")
    record["gate_failures"] = gate_failures

    if gate_failures:
        record["gate_status"] = "fail"
    elif skipped:
        record["gate_status"] = "soft_pass"
    elif record.get("svg_rendered"):
        record["gate_status"] = "pass"
    else:
        record["gate_status"] = "fail"
