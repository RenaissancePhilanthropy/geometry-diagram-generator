"""Tests for retry-layer failure classification and did-you-mean suggestions."""
from geometry_diagrams.pydsl.builder import OpCapExceededError
from geometry_diagrams.pydsl.retry import build_retry_message, classify_failure, suggest_name


def test_suggest_name_finds_close_match():
    assert suggest_name("itnersection", ["intersection", "triangle", "polygon"]) == "intersection"


def test_suggest_name_returns_none_for_no_close_match():
    assert suggest_name("xyzzy", ["intersection", "triangle", "polygon"]) is None


def test_classify_failure_categorizes_name_error_as_hallucinated_api():
    exc = NameError("The variable `itnersection` is not defined")
    assert classify_failure(exc) == "hallucinated_api"


def test_classify_failure_categorizes_value_error_as_structural_precondition():
    exc = ValueError("'p9' is not a vertex of triangle 'tri_1'")
    assert classify_failure(exc) == "structural_precondition"


def test_classify_failure_categorizes_op_cap_directly_as_a_distinct_category():
    exc = OpCapExceededError("script recorded more than 2000 ops")
    assert classify_failure(exc) == "syntax_or_timeout"


def test_classify_failure_categorizes_memory_error_as_memory_limit():
    # On Linux (unlike macOS, where CPython's list-fill touches pages
    # incrementally and the sandbox's own RSS watchdog usually wins the
    # race), a single huge allocation can raise MemoryError inside the
    # child itself before the watchdog ever polls — confirmed empirically
    # in a memory-capped Docker container. Same "memory_limit" label as the
    # watchdog-kill path, so callers see one consistent category regardless
    # of which mechanism actually caught it.
    exc = MemoryError()
    assert classify_failure(exc) == "memory_limit"


def test_classify_failure_reads_embedded_type_name_from_wrapped_interpreter_message():
    # Simulates what actually crosses the subprocess boundary in Task 10/11:
    # LocalPythonExecutor wraps every tool-raised exception into a single
    # InterpreterError whose message embeds the original type name as text
    # (verified against the real library — see this task's Interfaces note).
    # Only a message string survives the queue, not the original exception,
    # so classify_failure must handle a bare string, not just exception instances.
    wrapped_value_error = (
        "Code execution failed at line 'side(a, p9)' due to: "
        "ValueError: 'p9' is not a vertex of triangle 'tri_1'"
    )
    assert classify_failure(wrapped_value_error) == "structural_precondition"

    wrapped_op_cap = (
        "Code execution failed at line 'point(9, 9)' due to: "
        "OpCapExceededError: script recorded more than 2000 ops"
    )
    assert classify_failure(wrapped_op_cap) == "syntax_or_timeout"

    wrapped_memory_error = (
        "Code execution failed at line 'x = [0] * (10**12)' due to: MemoryError: "
    )
    assert classify_failure(wrapped_memory_error) == "memory_limit"


def test_classify_failure_recognizes_bare_undefined_variable_reference():
    # Verified against the real library: referencing an undefined name
    # WITHOUT calling it (e.g. `mark_angle(reff)` where `reff` is a typo)
    # raises with the type name "InterpreterError" embedded, not "NameError"
    # — the interpreter's own bounds check fires directly, so the
    # _WRAPPED_TYPE_PATTERN branch alone would never classify this as
    # hallucinated_api without the dedicated _NAME_ERROR_PATTERN check.
    msg = (
        "Code execution failed at line 'x = reff' due to: "
        "InterpreterError: The variable `reff` is not defined."
    )
    assert classify_failure(msg) == "hallucinated_api"


def test_classify_failure_recognizes_forbidden_call_message_shape():
    # The real message shape for BOTH an undefined name and a call to a
    # dangerous builtin like open()/exec() — distinguishable only by which
    # name was called, not by message shape (verified against the library).
    undefined_name_msg = (
        "Forbidden function evaluation: 'itnersection' is not among the "
        "explicitly allowed tools or defined/imported in the preceding code"
    )
    assert classify_failure(undefined_name_msg) == "hallucinated_api"

    dangerous_call_msg = (
        "Forbidden function evaluation: 'open' is not among the explicitly "
        "allowed tools or defined/imported in the preceding code"
    )
    assert classify_failure(dangerous_call_msg) == "dangerous_call"


def test_classify_failure_recognizes_import_error_message_shape():
    msg = "Import of os is not allowed. Authorized imports are: ['math', 're']"
    assert classify_failure(msg) == "import_error"


def test_build_retry_message_appends_did_you_mean_for_hallucinated_api():
    # Must be a typo of a real Phase 1a API function — "intersection" is
    # NOT part of the Phase 1a API (see the scope table), so a candidate
    # pool built from the real function list would never suggest it.
    exc = NameError("The variable `trianlge` is not defined")
    msg = build_retry_message(exc, script="trianlge(a, b, c)")
    assert "trianlge" in msg
    assert "did you mean 'triangle'" in msg


def test_build_retry_message_appends_did_you_mean_for_wrapped_forbidden_call():
    msg_text = (
        "Forbidden function evaluation: 'pointt' is not among the "
        "explicitly allowed tools or defined/imported in the preceding code"
    )
    msg = build_retry_message(msg_text, script="pointt(0, 0)")
    assert "did you mean 'point'" in msg


def test_build_retry_message_has_no_suggestion_for_structural_errors():
    exc = ValueError("'p9' is not a vertex of triangle 'tri_1'")
    msg = build_retry_message(exc, script="t.side(a, p9)")
    assert "did you mean" not in msg
    assert "not a vertex" in msg
