# tests/test_pydsl_sandbox.py
"""Tests for the pydsl sandbox: import lockdown, dangerous calls, resource limits."""
import inspect
import io
import json
import logging
import multiprocessing
import subprocess
import sys
import textwrap
from unittest.mock import MagicMock, patch

import pytest

from geometry_diagrams.pydsl import _sandbox_child, sandbox
from geometry_diagrams.pydsl.sandbox import run_script

# Fake child scripts, run via `_child_argv=[sys.executable, "-c", <script>]` —
# see sandbox.py's run_script for why the real child is a plain
# subprocess.Popen (not multiprocessing) and speaks newline-delimited JSON
# over stdin/stdout rather than pickled Python objects.
_FAKE_CHILD_READS_REQUEST = "import json, sys\nsys.stdin.readline()\n"
# Python source (not JSON) for a minimal valid DiagramIR dict — None, not
# null, since this text is spliced into a Python -c script, not embedded
# as literal JSON. json.dumps() serializes it to real JSON at the fake
# child's own runtime, same as the real _sandbox_child does.
_MINIMAL_DIAGRAM_IR_JSON = (
    '{"params": None, "canvas": None, "define": [], "checks": [], '
    '"render": [], "pending_angle_pairs": [], "styles": {}}'
)

_FAKE_SLOW_IMPORT_THEN_QUICK_SCRIPT = _FAKE_CHILD_READS_REQUEST + textwrap.dedent(f"""
    import time
    time.sleep(3.0)
    print(json.dumps({{"kind": "ready", "payload": None}}), flush=True)
    print(json.dumps({{"kind": "ok", "payload": {{
        "diagram_ir": {_MINIMAL_DIAGRAM_IR_JSON}, "variable_ids": {{}},
    }}}}), flush=True)
""")

_FAKE_CHILD_WITH_PROGRESS_PINGS_THEN_READY = _FAKE_CHILD_READS_REQUEST + textwrap.dedent(f"""
    import time
    time.sleep(0.1)
    print(json.dumps({{"kind": "progress", "payload": "step 1"}}), flush=True)
    time.sleep(0.1)
    print(json.dumps({{"kind": "progress", "payload": "step 2"}}), flush=True)
    time.sleep(0.1)
    print(json.dumps({{"kind": "ready", "payload": None}}), flush=True)
    print(json.dumps({{"kind": "ok", "payload": {{
        "diagram_ir": {_MINIMAL_DIAGRAM_IR_JSON}, "variable_ids": {{}},
    }}}}), flush=True)
""")

_FAKE_CHILD_THAT_NEVER_SENDS_ANYTHING = _FAKE_CHILD_READS_REQUEST + textwrap.dedent("""
    import time
    time.sleep(5.0)
""")

_FAKE_CHILD_THAT_CRASHES_DURING_SETUP = _FAKE_CHILD_READS_REQUEST + textwrap.dedent("""
    print(json.dumps({"kind": "error", "payload": [
        "full traceback here", "sandbox_setup_error",
        "ImportError: no module named 'fake'",
    ]}), flush=True)
""")

_FAKE_CHILD_THAT_GETS_KILLED_BY_A_SIGNAL = _FAKE_CHILD_READS_REQUEST + textwrap.dedent("""
    import os, signal
    os.kill(os.getpid(), signal.SIGKILL)
""")


def _run_fake(script: str, *, timeout_seconds: float = 1.0, **kwargs):
    return run_script(
        "irrelevant — the fake child ignores this",
        timeout_seconds=timeout_seconds,
        _child_argv=[sys.executable, "-c", script],
        **kwargs,
    )


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


def test_importing_sandbox_child_does_not_force_langgraph_or_langchain():
    """Regression test: geometry_diagrams/__init__.py used to eagerly import
    .facade and .strategies.recipe, which transitively pull in LangGraph/
    LangChain — needed only by the strategy layer, never by the sandboxed
    child itself. Python always imports a package's __init__.py before any
    submodule, so `python -m geometry_diagrams.pydsl._sandbox_child` (the
    real child command run_script spawns) forces that whole chain to import
    just to locate the entrypoint — confirmed empirically (2026-08-13):
    eagerly importing geometry_diagrams cost ~1450 modules and ~0.7s warm on
    a local dev machine, plausibly far worse on a cold, resource-constrained
    container. Fixed via PEP 562 lazy exports in geometry_diagrams/__init__.py.

    Run in a fresh subprocess, not in-process: other tests in this session
    have already imported langgraph/langchain, which would make an
    in-process sys.modules check pass regardless of whether this fix works."""
    result = subprocess.run(
        [sys.executable, "-c", (
            "import sys\n"
            "import geometry_diagrams.pydsl._sandbox_child\n"
            "print('langgraph' in sys.modules, 'langchain_core' in sys.modules)\n"
        )],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False False"


def test_harness_imports_precede_rlimit_cpu_in_sandbox_child_main():
    """Regression test: smolagents/geometry_diagrams.pydsl (which transitively
    pull in sympy/numpy/matplotlib — real CPU-bound import cost, not I/O)
    must be imported BEFORE RLIMIT_CPU is set, not after. Setting the limit
    first would charge that fixed harness-startup cost against the same
    budget meant to bound the untrusted script's own solving time, on a
    cold interpreter (e.g. a cold AWS Lambda container) that import cost is
    plausibly the dominant cost, silently shrinking the margin
    timeout_seconds is supposed to leave for the script itself. This can't
    be verified by timing on a warm local dev machine (import cost there is
    negligible either way — that's exactly why the bug was invisible
    locally), so this checks source order directly instead."""
    source = inspect.getsource(_sandbox_child.main)
    import_pos = source.index("import geometry_diagrams.pydsl")
    rlimit_cpu_pos = source.index("resource.RLIMIT_CPU")
    assert import_pos < rlimit_cpu_pos


def test_rlimit_cpu_accounts_for_cpu_already_used_by_harness_imports(monkeypatch):
    """Regression test: RLIMIT_CPU caps *cumulative* process CPU time since
    process start, not time elapsed since the setrlimit call — confirmed
    empirically (2026-08-13, real Linux container): a process that burns 1s
    of CPU and only then calls setrlimit(RLIMIT_CPU, (3, 3)) is killed at
    ~3s of TOTAL cumulative CPU, leaving only ~2s for whatever ran after the
    call, identical to setting the same limit at process start. So moving
    the harness's smolagents/geometry_diagrams.pydsl imports (real
    sympy/numpy/matplotlib import cost) before this setrlimit call only
    excludes their cost from the script's budget if the limit itself is
    widened by however much CPU those imports already burned — otherwise
    the reordering is a no-op. Runs _sandbox_child.main() in-process (not
    spawned) with setrlimit mocked out, so it never touches this test
    process's real CPU limit; only the computed limit value is checked."""
    fake_usage = MagicMock(ru_utime=1.5, ru_stime=0.3)  # 1.8s of CPU "already used"
    request = json.dumps({"script": "a = point(0, 0)\ndraw_points(a)", "timeout_seconds": 2.0})
    monkeypatch.setattr(sys, "stdin", io.StringIO(request + "\n"))
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    with patch.object(_sandbox_child.resource, "getrusage", return_value=fake_usage), \
         patch.object(_sandbox_child.resource, "setrlimit") as mock_setrlimit:
        _sandbox_child.main()
    cpu_calls = [c for c in mock_setrlimit.call_args_list if c.args[0] == _sandbox_child.resource.RLIMIT_CPU]
    assert len(cpu_calls) == 1
    limit = cpu_calls[0].args[1]
    # int(1.8) [already used] + int(2.0) + 1 [this call's own budget] = 1 + 3 = 4
    assert limit == (4, 4)


def test_sandbox_child_reports_a_real_import_crash_over_stdout(monkeypatch):
    """Same as the fake-child test below, but exercises _sandbox_child.main's
    own try/except directly: forcing `from smolagents import ...` to raise
    (via the standard "None in sys.modules" import-blocking mechanism, not
    a fake) must print an {"kind": "error", "payload": [...]} JSON line
    rather than letting an unhandled exception propagate out of main().
    Runs in-process (not spawned), same pattern as the RLIMIT_CPU
    accounting test above."""
    monkeypatch.setitem(sys.modules, "smolagents", None)
    request = json.dumps({"script": "a = point(0, 0)\ndraw_points(a)", "timeout_seconds": 2.0})
    monkeypatch.setattr(sys, "stdin", io.StringIO(request + "\n"))
    fake_stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", fake_stdout)
    _sandbox_child.main()
    # The import crash is the LAST line — a "progress" ping precedes it.
    lines = [line for line in fake_stdout.getvalue().splitlines() if line]
    kind_payload = json.loads(lines[-1])
    assert kind_payload["kind"] == "error"
    message, error_type, retry_message = kind_payload["payload"]
    assert error_type == "sandbox_setup_error"
    assert "smolagents" in message
    assert "smolagents" in retry_message


@pytest.mark.timeout(30)
def test_bootstrap_wait_excludes_cold_start_import_time_from_the_script_deadline():
    """Regression test: the wall-clock deadline used to start counting at
    process spawn, so slow cold-start import time (sympy/numpy/matplotlib
    on a cold container) ate directly into timeout_seconds's budget with no
    way to distinguish "still importing" from "script is actually running
    long." A fake child that sleeps 3s (simulating a slow import) before
    sending its "ready" sentinel, then finishes in well under a second,
    must still succeed with timeout_seconds=1.0 — pre-fix, the deadline
    (spawn + timeout_seconds + 2.0 = 3.0s) would have killed it mid-sleep,
    before it ever got a chance to run."""
    result = _run_fake(_FAKE_SLOW_IMPORT_THEN_QUICK_SCRIPT, timeout_seconds=1.0)
    assert result.error is None
    assert result.diagram_ir is not None


def test_run_script_treats_a_bootstrap_hang_as_a_start_failure(monkeypatch):
    """If the child never sends its "ready" sentinel (an ImportError or
    crash during harness setup, or a genuine hang), run_script must not
    wait forever — it should give up once _BOOTSTRAP_TIMEOUT_SECONDS
    elapses and report a start failure rather than hanging or silently
    treating it as script success."""
    monkeypatch.setattr(sandbox, "_BOOTSTRAP_TIMEOUT_SECONDS", 0.3)
    result = _run_fake(_FAKE_CHILD_THAT_NEVER_SENDS_ANYTHING)
    assert result.diagram_ir is None
    assert result.error_type == "timeout"
    assert "failed to start" in result.error


def test_run_script_surfaces_a_reported_setup_crash_instead_of_the_generic_message():
    """Regression test: a child that crashes during import (missing shared
    library, matplotlib's font-cache dir being unwritable on a read-only
    Lambda filesystem, etc.) used to die silently before "ready" — the
    parent had no way to distinguish "harness crashed with a specific,
    diagnosable reason" from "harness is still importing" or "harness
    hung," and reported the same opaque "sandbox failed to start" message
    either way. When the child DOES manage to report why (via its own
    try/except around the imports), run_script must surface that specific
    message/error_type instead of masking it with the generic one."""
    result = _run_fake(_FAKE_CHILD_THAT_CRASHES_DURING_SETUP)
    assert result.diagram_ir is None
    assert result.error_type == "sandbox_setup_error"
    assert result.error == "full traceback here"
    assert result.retry_message == "ImportError: no module named 'fake'"


def test_run_script_reports_signal_when_child_dies_on_its_own_without_a_report():
    """Regression test: when the child dies on its own during bootstrap
    (e.g. OOM-killed by the OS) severe enough that not even its own
    try/except gets to run, run_script must capture its exitcode/signal
    BEFORE issuing its own proc.kill() — which would otherwise overwrite
    the one diagnostic signal available (the child's actual death reason)
    with -9 from OUR kill — and surface it in the error message so a real
    OOM-kill is distinguishable from a genuine "still importing" hang."""
    result = _run_fake(_FAKE_CHILD_THAT_GETS_KILLED_BY_A_SIGNAL)
    assert result.diagram_ir is None
    assert result.error_type == "timeout"
    assert "SIGKILL" in result.error
    assert "died with no report" in result.error


def test_progress_pings_during_bootstrap_do_not_end_the_wait_and_get_logged(caplog):
    """Regression test: "progress" pings are NOT terminal — the bootstrap
    wait must keep waiting for "ready"/"error" after receiving one (a naive
    implementation that breaks the loop on any message would misreport a
    slow-but-succeeding import as a failure), and each one must get logged
    so production has a trail of which import step is slow instead of the
    old binary "still alive at the deadline, no other information." Direct
    motivation: production logged "pid=80 never sent 'ready' within 20.0s
    bootstrap budget, killed" with the child confirmed still alive (not
    crashed) — progress pings are what would narrow down WHERE in that
    window it's stuck, next time this happens."""
    with caplog.at_level(logging.INFO, logger="geometry_diagrams.pydsl.sandbox"):
        result = _run_fake(_FAKE_CHILD_WITH_PROGRESS_PINGS_THEN_READY, timeout_seconds=2.0)
    assert result.error is None
    assert result.diagram_ir is not None
    progress_messages = [r.message for r in caplog.records if "progress:" in r.message]
    assert any("step 1" in m for m in progress_messages)
    assert any("step 2" in m for m in progress_messages)


def test_bootstrap_timeout_budget_was_raised_from_the_original_20s():
    """Regression test: production hit the OLD 20.0s bootstrap budget with
    the child still alive (not crashed) — 20s genuinely wasn't enough
    headroom on that container. Pins the raised value so a future
    refactor can't silently drop back to the too-tight original."""
    assert sandbox._BOOTSTRAP_TIMEOUT_SECONDS == 60.0


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
def test_large_diagram_result_does_not_deadlock_or_misreport_as_timeout():
    """Regression test: a result payload bigger than one OS pipe buffer
    (~16-64KB) is written by the child across multiple os.write() calls.
    The background stdout-reader thread's readline() only ever returns a
    complete line (or empty at EOF), so this is handled automatically — no
    special "drain immediately on poll()" dance is needed the way it was
    for the old multiprocessing.Pipe-based implementation (see git history
    for that class of bug and its fix)."""
    script = (
        "pts = []\n"
        "for i in range(1500):\n"
        "    p = point(i * 0.001, (i % 7) * 0.001)\n"
        "    pts.append(p)\n"
        "draw_points(*pts)\n"
    )
    result = run_script(script, timeout_seconds=8.0)
    assert result.error is None
    assert result.diagram_ir is not None
    assert len(result.diagram_ir.define) == 1500


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
    # Module-level, not nested: multiprocessing's "spawn" context pickles
    # the target function by reference, and a closure defined inside the
    # test function isn't picklable. This test is independent of the
    # sandbox's own IPC mechanism (which no longer uses multiprocessing at
    # all — see sandbox.py's module docstring) — it just uses
    # multiprocessing as a convenient way to spawn an isolated process to
    # check a general OS/resource-module fact.
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
    # _sandbox_child.main: confirms the OS-level guarantee it relies on
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
