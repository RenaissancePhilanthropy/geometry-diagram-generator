# tests/test_pydsl_sandbox.py
"""Tests for the pydsl sandbox: import lockdown, dangerous calls, resource limits."""
import inspect
import io
import multiprocessing
import sys

import pytest

from geometry_diagrams.pydsl import sandbox
from geometry_diagrams.pydsl.sandbox import run_script, _run_in_subprocess

# RLIMIT_DATA is a documented no-op on macOS (resource.setrlimit itself
# raises ValueError there — confirmed directly: soft/hard both report as
# RLIM_INFINITY yet setting even a generous limit fails outright) and
# doesn't exist as a real per-process concept on Windows either. Verified
# empirically inside a memory-capped Linux Docker container that it DOES
# enforce there: a real over-limit allocation raises MemoryError
# immediately. Only meaningfully testable on Linux.
_rlimit_data_unsupported = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="RLIMIT_DATA is a no-op on this platform (confirmed on macOS; only enforces on Linux)",
)


def test_harness_imports_precede_rlimit_cpu_in_run_in_subprocess():
    """Regression test: smolagents/geometry_diagrams.pydsl (which transitively
    pull in sympy/numpy/matplotlib — real CPU-bound import cost, not I/O)
    must be imported BEFORE RLIMIT_CPU is set, not after. Setting the limit
    first would charge that fixed harness-startup cost against the same
    budget meant to bound the untrusted script's own solving time — on a
    cold interpreter (e.g. a cold AWS Lambda container) that import cost is
    plausibly the dominant cost, silently shrinking the margin
    timeout_seconds is supposed to leave for the script itself. This can't
    be verified by timing on a warm local dev machine (import cost there is
    negligible either way — that's exactly why the bug was invisible
    locally), so this checks source order directly instead."""
    source = inspect.getsource(_run_in_subprocess)
    import_pos = source.index("import geometry_diagrams.pydsl")
    rlimit_cpu_pos = source.index("resource.RLIMIT_CPU")
    assert import_pos < rlimit_cpu_pos


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
def test_incremental_memory_growth_is_killed_by_the_memory_watchdog():
    # A loop that keeps growing a list forever, one chunk at a time —
    # unlike test_single_huge_allocation_is_killed_by_the_memory_watchdog's
    # single giant allocation, this ramps RSS gradually across many small
    # ones. In practice this still crosses _MAX_CHILD_RSS_BYTES well before
    # the 2s wall-clock timeout, so error_type is "memory_limit", not
    # "timeout" — before error_type distinguished the two kill paths, this
    # assertion couldn't tell the difference and the test's own name/comment
    # (incorrectly) assumed the wall-clock kill was what fired.
    script = "acc = []\nwhile True:\n    acc.append([0] * 10**6)"
    result = run_script(script, timeout_seconds=2.0)
    assert result.diagram_ir is None
    assert result.error_type == "memory_limit"


@pytest.mark.timeout(30)
def test_single_huge_allocation_is_caught_as_memory_limit_one_way_or_another():
    # Which of two mechanisms catches this is platform/memory-pressure
    # dependent, confirmed empirically on both: on this dev machine (macOS,
    # generous virtual memory), CPython's list-fill touches real pages
    # incrementally, ramping RSS fast enough for the parent's
    # _MAX_CHILD_RSS_BYTES watchdog to win the race and kill the child
    # before it ever raises MemoryError itself. Inside a memory-capped Linux
    # container (docker run --memory=1g), the allocation instead fails fast
    # with a real MemoryError raised in-process, before the watchdog's next
    # poll. Either way the script never keeps consuming host memory for the
    # full wall-clock timeout, and either way error_type is "memory_limit"
    # (see classify_failure's MemoryError branch, added for the container
    # case) — that consistency, not which mechanism fires, is what this
    # test actually guards.
    result = run_script("x = [0] * (10**12)", timeout_seconds=5.0)
    assert result.diagram_ir is None
    assert result.error_type == "memory_limit"


def _rlimit_data_probe_worker(conn):
    # Module-level, not nested: multiprocessing's "spawn" context (same one
    # run_script itself uses) pickles the target function by reference, and
    # a closure defined inside the test function isn't picklable.
    #
    # Reports back over a Pipe, not a Queue: Queue.put() starts a background
    # feeder thread on first use, and under a 10MB RLIMIT_DATA there isn't
    # enough headroom left for a new thread's own bookkeeping to start at
    # all ("RuntimeError: can't start new thread") — confirmed by hitting
    # exactly that failure with a Queue in an earlier version of this test.
    # Pipe.send() is synchronous, no extra thread required.
    import resource
    resource.setrlimit(resource.RLIMIT_DATA, (10 * 1024 * 1024, 10 * 1024 * 1024))
    try:
        buf = bytearray(50 * 1024 * 1024)
        buf[0] = 1  # touch it so it isn't optimized away
        conn.send(("allocation_succeeded", len(buf)))
    except MemoryError:
        conn.send(("memory_error", None))


@_rlimit_data_unsupported
@pytest.mark.timeout(30)
def test_rlimit_data_actually_enforces_on_linux():
    # Regression test for the RLIMIT_DATA setrlimit call added to
    # _run_in_subprocess: confirms the OS-level guarantee it relies on
    # actually holds, independent of run_script's own watchdog/timeout
    # machinery. Runs in its own subprocess (not the test runner's process)
    # so a real over-limit allocation can't affect anything else.
    ctx = multiprocessing.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe()
    process = ctx.Process(target=_rlimit_data_probe_worker, args=(child_conn,))
    process.start()
    process.join(timeout=10)
    kind, _ = parent_conn.recv()
    assert kind == "memory_error"


def test_child_rss_bytes_reads_proc_statm_on_linux(monkeypatch):
    """Dev machine is macOS (no /proc), so this can't exercise the real file
    system path — it forces _IS_LINUX and mocks open() to verify the statm
    field parsing (field index 1 = resident, in pages) is correct."""
    monkeypatch.setattr(sandbox, "_IS_LINUX", True)
    monkeypatch.setattr(sandbox, "_PAGE_SIZE", 4096)

    statm_contents = "1000 250 10 5 0 900 0\n"  # size resident shared text lib data dt

    def fake_open(path, mode="r"):
        assert path == "/proc/1234/statm"
        return io.StringIO(statm_contents)

    monkeypatch.setattr("builtins.open", fake_open)
    assert sandbox._child_rss_bytes(1234) == 250 * 4096


def test_child_rss_bytes_returns_none_when_proc_statm_is_unreadable(monkeypatch):
    """Covers the already-exited-child race: /proc/<pid>/statm is gone by
    the time we try to read it — must report "no reading available", not
    raise, and never be mistaken for a zero-usage reading."""
    monkeypatch.setattr(sandbox, "_IS_LINUX", True)

    def fake_open(path, mode="r"):
        raise FileNotFoundError(path)

    monkeypatch.setattr("builtins.open", fake_open)
    assert sandbox._child_rss_bytes(1234) is None


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
