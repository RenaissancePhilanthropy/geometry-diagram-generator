# tests/test_pydsl_sandbox.py
"""Tests for the pydsl sandbox: import lockdown, dangerous calls, resource limits."""
import pytest

from geometry_diagrams.pydsl.sandbox import run_script


def test_valid_script_produces_a_diagram_ir():
    script = """
a = point(0, 0)
b = point(1, 0)
c = point(0, 1)
t = triangle(a, b, c)
"""
    result = run_script(script)
    assert result.error is None
    assert result.diagram_ir is not None
    assert any(d.kind == "triangle" for d in result.diagram_ir.define)


def test_math_is_usable_with_no_import():
    """math is pre-injected into the sandbox namespace — a script can use
    math.pi/math.sqrt/etc. with no import statement, which matters since the
    system prompt tells the model "no imports" and a weaker model won't try
    importing math even though it's actually always allowed."""
    script = """
a = point(0, 0)
b = walk(a, math.pi / 2, 4.0)
t = triangle(a, b, point(1, 0))
"""
    result = run_script(script)
    assert result.error is None
    assert result.diagram_ir is not None


def test_explicit_import_math_still_works():
    """import math must remain equally valid for a model that ignores the
    "no imports" framing and writes it explicitly — re-binding an
    already-injected module is a harmless no-op."""
    script = """
import math
a = point(0, 0)
b = walk(a, math.pi / 2, 4.0)
t = triangle(a, b, point(1, 0))
"""
    result = run_script(script)
    assert result.error is None
    assert result.diagram_ir is not None


def test_disallowed_import_is_rejected():
    result = run_script("import os\nos.system('echo hi')")
    assert result.diagram_ir is None
    assert result.error_type == "import_error"


def test_dangerous_call_is_rejected():
    result = run_script("open('/etc/passwd')")
    assert result.diagram_ir is None
    assert result.error_type == "dangerous_call"


def test_infinite_while_loop_is_caught_by_iteration_cap():
    result = run_script("i = 0\nwhile True:\n    i = i + 1")
    assert result.diagram_ir is None
    # MAX_WHILE_ITERATIONS raises InterpreterError (falls through classify_failure's
    # catch-all -> "syntax_or_timeout"); if the wall-clock kill wins the race instead,
    # that's "timeout" — either is a correct outcome depending on machine speed.
    assert result.error_type in ("syntax_or_timeout", "timeout")


@pytest.mark.timeout(30)
def test_cpu_bomb_is_killed_by_rlimit_cpu_on_any_platform():
    result = run_script("import math\nmath.factorial(10**8)", timeout_seconds=2.0)
    assert result.diagram_ir is None
    assert result.error_type == "timeout"


@pytest.mark.timeout(30)
def test_incremental_memory_growth_is_eventually_killed_by_wall_clock_timeout():
    # A loop that keeps growing a list forever thrashes long enough to
    # actually exercise the wall-clock kill. A single huge allocation
    # (e.g. `[0] * 10**12`) is the wrong shape for this test — it raises
    # MemoryError immediately and never reaches the timeout path at all,
    # on either platform.
    script = "acc = []\nwhile True:\n    acc.append([0] * 10**6)"
    result = run_script(script, timeout_seconds=2.0)
    assert result.diagram_ir is None
    assert result.error_type == "timeout"


@pytest.mark.timeout(30)
def test_single_huge_allocation_is_killed_by_the_memory_watchdog():
    # Documents the actual (measured) behavior, which contradicts the naive
    # assumption that `[0] * 10**12` raises MemoryError instantly: CPython
    # fills the array as it allocates, so this touches real pages and ramps
    # RSS fast enough to cross the parent's _MAX_CHILD_RSS_BYTES watchdog
    # threshold in well under a second — before the child ever gets to raise
    # MemoryError itself. Without that watchdog this keeps consuming real
    # memory for up to the full wall-clock timeout, which is a genuine
    # host-OOM risk, not just a slow test.
    result = run_script("x = [0] * (10**12)", timeout_seconds=5.0)
    assert result.diagram_ir is None
    assert result.error == "script exceeded memory limit"
    assert result.error_type == "timeout"


def test_undefined_name_error_is_classified_as_hallucinated_api_with_a_suggestion():
    result = run_script("pointt(0, 0)")  # one character off from `point`
    assert result.diagram_ir is None
    assert result.error_type == "hallucinated_api"
    assert result.retry_message is not None
    assert "did you mean 'point'" in result.retry_message


def test_structural_precondition_error_is_classified_correctly_with_no_suggestion():
    script = """
a = point(0, 0)
b = point(1, 0)
c = point(0, 1)
outside = point(9, 9)
t = triangle(a, b, c)
t.side(a, outside)
"""
    result = run_script(script)
    assert result.diagram_ir is None
    assert result.error_type == "structural_precondition"
    assert "not a vertex" in result.retry_message
    assert "did you mean" not in result.retry_message


def test_variable_ids_maps_assigned_names_to_internal_ids():
    script = """
a = point(0, 0)
b = point(1, 0)
c = point(0, 1)
t = triangle(a, b, c)
draw(t)
"""
    result = run_script(script)
    assert result.error is None
    assert set(result.variable_ids) == {"a", "b", "c", "t"}
    tri_def = next(d for d in result.diagram_ir.define if d.kind == "triangle")
    assert result.variable_ids["t"] == tri_def.id


def test_variable_ids_excludes_tuple_valued_names():
    script = """
c = circle(point(0, 0), 5)
sectors = regular_sectors(c, 4)
for s in sectors:
    draw(s)
"""
    result = run_script(script)
    assert result.error is None
    assert "c" in result.variable_ids
    assert "sectors" not in result.variable_ids


def test_variable_ids_empty_on_error():
    result = run_script("this is not valid python +++ ")
    assert result.error is not None
    assert result.variable_ids == {}
