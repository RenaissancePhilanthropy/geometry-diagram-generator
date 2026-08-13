# geometry_diagrams/pydsl/sandbox.py
"""Executes untrusted pydsl scripts inside a resource-limited subprocess,
using smolagents.LocalPythonExecutor as the restricted interpreter.

Security posture (see design doc): LocalPythonExecutor's own AST
whitelist/import-allowlist/dangerous-function-blocklist is the primary
control. This module adds process-level isolation on top: RLIMIT_CPU
(reliable on macOS and Linux) plus a parent-side RSS-polling watchdog.

The watchdog, not the wall-clock join alone, is the real memory-bomb
backstop on macOS: RLIMIT_AS is a documented no-op there, and a script like
`while True: acc.append([0] * 10**6)` can grow resident memory by GB/s (list
allocation is a single fast C call even though the surrounding interpreter
loop is slow), which can exhaust a memory-constrained host in well under a
single wall-clock timeout period. Polling the child's RSS every
_POLL_INTERVAL_SECONDS and killing as soon as it crosses _MAX_CHILD_RSS_BYTES
bounds the damage to one poll interval's worth of growth instead of the full
timeout window.

Tool functions are wrapped with _bind_to_builder rather than relying on the
ambient contextvar alone: LocalPythonExecutor runs the entire script inside
its own ThreadPoolExecutor worker thread, so a contextvar set on the calling
thread before invoking the executor is NOT visible inside tool calls (verified
empirically against smolagents 1.26.0). Each wrapper re-sets the contextvar
immediately before calling the real function, in the same call frame the
tool actually executes in, which works regardless of which thread that is.
"""
from __future__ import annotations

import logging
import math
import multiprocessing
import resource
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Callable

from geometry_diagrams.ir.ir import DiagramIR
from geometry_diagrams.pydsl.builder import Builder, _current_builder
from geometry_diagrams.pydsl.retry import build_retry_message, classify_failure

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 0.05
_MAX_CHILD_RSS_BYTES = 512 * 1024 * 1024  # 512MB; well below a typical dev machine's headroom
# Generous on purpose: covers cold-start smolagents/sympy/numpy/matplotlib
# import time on a cold container (e.g. a cold AWS Lambda invocation), which
# is trusted harness setup, not the untrusted script's own execution budget.
# The child sends a "ready" sentinel once setup is done and only then does
# run_script() start the real timeout_seconds-based deadline — so this value
# only bounds "is the harness hung/dead," not "is this taking a while."
#
# Raised from 20.0 to 60.0 (2026-08-13): production logged "pid=80 never
# sent 'ready' within 20.0s bootstrap budget, killed" — the child was still
# ALIVE (not crashed/OOM-killed, which would have shown a signal instead),
# meaning 20s genuinely wasn't enough headroom for whatever's slow on that
# container. Import-time "progress" pings (see _run_in_subprocess) narrow
# down which step, if this still isn't enough.
_BOOTSTRAP_TIMEOUT_SECONDS = 60.0
_PAGE_SIZE = resource.getpagesize()
_IS_LINUX = sys.platform.startswith("linux")


def _child_rss_bytes(pid: int) -> "int | None":
    """Resident set size of `pid` in bytes, or None if it can't be read
    (already exited, `ps` unavailable, etc.) — treated as "no reading
    available", never as "zero usage", by the caller.

    On Linux (the real deployment target — this repo's dev machine is macOS,
    where none of this applies), reads /proc/<pid>/statm directly: a plain
    file read, versus spawning a whole `ps` subprocess on every single poll
    (every _POLL_INTERVAL_SECONDS, for the lifetime of every sandboxed
    script). That's real per-poll latency and its own process overhead this
    watchdog was adding on top of the workload it's supposed to be guarding —
    faster reads mean a memory bomb is caught sooner, not just cheaper to
    watch for. macOS has no /proc, so it keeps the subprocess-based path."""
    if _IS_LINUX:
        try:
            with open(f"/proc/{pid}/statm", "r") as f:
                fields = f.read().split()
            return int(fields[1]) * _PAGE_SIZE  # field 1 = resident, in pages
        except (OSError, IndexError, ValueError):
            return None

    try:
        out = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True, text=True, timeout=1.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = out.stdout.strip()
    if not text:
        return None
    try:
        return int(text) * 1024  # ps reports RSS in KB
    except ValueError:
        return None


def _describe_exitcode(exitcode: "int | None") -> str:
    """Human-readable summary of a dead multiprocessing.Process's exitcode:
    negative means killed by signal -exitcode (e.g. -9 = SIGKILL, often OOM
    or our own process.kill()); non-negative means it exited on its own
    (0 = clean, nonzero = an uncaught exception's default exit(1) or similar).
    None means still running (only meaningful before we've killed it ourselves)."""
    if exitcode is None:
        return "still running"
    if exitcode < 0:
        import signal
        try:
            return f"killed by signal {-exitcode} ({signal.Signals(-exitcode).name})"
        except ValueError:
            return f"killed by signal {-exitcode}"
    return f"exited with code {exitcode}"


@dataclass
class ScriptResult:
    diagram_ir: "DiagramIR | None"
    error: "str | None"
    error_type: "str | None"  # see classify_failure's return values, plus "timeout" and "sandbox_setup_error"
    retry_message: "str | None" = None
    variable_ids: dict = field(default_factory=dict)


def _bind_to_builder(fn: Callable, builder: Builder) -> Callable:
    def wrapped(*args, **kwargs):
        token = _current_builder.set(builder)
        try:
            return fn(*args, **kwargs)
        finally:
            _current_builder.reset(token)

    return wrapped


def _run_in_subprocess(script: str, timeout_seconds: float, conn: "multiprocessing.connection.Connection") -> None:
    """Runs entirely inside the child process. Sends zero or more
    ("progress", str) pings during setup, then either ("ready", None) once
    harness setup is done or an early ("error", ...) if setup itself
    crashed, and finally a (kind, payload) tuple over the pipe once the
    script has run (or failed).

    Uses Pipe rather than Queue: Queue is backed by a POSIX named semaphore
    (multiprocessing.Lock -> SemLock), which requires a writable /dev/shm.
    That's absent on AWS Lambda, so Queue() construction fails before the
    child even starts. Pipe needs only a plain OS pipe/socketpair, and this
    is one-writer/one-reader IPC (always in the order above), so it's a
    drop-in replacement with no other behavioral change.
    """
    # Imported before the RLIMIT_CPU setrlimit call below: smolagents and
    # geometry_diagrams.pydsl transitively pull in sympy/numpy/matplotlib,
    # real CPU-bound import cost that a cold interpreter (e.g. a cold AWS
    # Lambda container) can't amortize away. Setting the limit first would
    # charge that fixed harness-startup cost against the same budget meant
    # to bound the untrusted script's own solving time, shrinking the
    # margin `timeout_seconds` is supposed to leave for it.
    #
    # Wrapped in its own try/except: an import-time crash here (missing
    # shared library, matplotlib's font-cache directory being unwritable on
    # a read-only Lambda filesystem, etc.) used to kill the child before it
    # ever reached a try/except that could report back over the pipe — the
    # parent would just see the child die with no "ready" sentinel and no
    # way to tell "harness crashed" from "harness is still importing," both
    # surfacing as the same opaque "sandbox failed to start" message. Report
    # the real exception instead so a genuine environment problem is
    # diagnosable from the caller's last_error rather than looking identical
    # to a slow cold start.
    # Progress pings, not just the final "ready" sentinel: a bootstrap that
    # merely exceeds _BOOTSTRAP_TIMEOUT_SECONDS (still alive, never crashed)
    # gives the parent no way to tell WHICH import is slow/stuck without
    # these — confirmed in production (2026-08-13) that the child is still
    # alive at the full 20s bootstrap deadline, ruling out a crash/OOM-kill
    # but leaving "which step" and "slow vs. truly hung" both unknown.
    conn.send(("progress", "importing smolagents"))
    try:
        from smolagents import LocalPythonExecutor
        from smolagents.local_python_executor import ExecutionTimeoutError

        conn.send(("progress", "importing geometry_diagrams.pydsl"))
        import geometry_diagrams.pydsl as pydsl_module
    except Exception as exc:  # noqa: BLE001 — must report every failure kind to the parent
        import traceback
        conn.send(("error", (traceback.format_exc(), "sandbox_setup_error", str(exc))))
        return
    conn.send(("progress", "imports done, setting resource limits"))

    try:
        # RLIMIT_CPU caps *cumulative* CPU time consumed by the process since
        # it started, not time elapsed since this setrlimit call — moving the
        # harness imports above this call (see this function's comment above)
        # only excludes their CPU cost from the script's budget if the limit
        # itself is adjusted for CPU already spent. Confirmed empirically
        # (2026-08-13, real Linux container, not macOS — see RLIMIT_DATA's
        # note below on why macOS isn't representative here): a process that
        # burns 1s of CPU and only *then* calls setrlimit(RLIMIT_CPU, (3, 3))
        # is killed at ~3s of *total* cumulative CPU, i.e. with only ~2s left
        # for whatever ran after the call — identical to calling setrlimit
        # with the same limit at process start. Without this adjustment, the
        # import-reordering fix is a no-op: the harness's own import cost is
        # still charged against the script's timeout_seconds budget either
        # way, just measured from a different starting line.
        cpu_already_used = 0
        try:
            usage = resource.getrusage(resource.RUSAGE_SELF)
            cpu_already_used = int(usage.ru_utime + usage.ru_stime)
        except (ValueError, OSError):
            pass  # best-effort; worst case the limit is tighter than intended
        cpu_limit = cpu_already_used + int(timeout_seconds) + 1
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
    except (ValueError, OSError):
        pass  # best-effort; the parent's wall-clock kill is the real backstop
    try:
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    except (ValueError, OSError):
        pass  # documented no-op on macOS; effective on Linux
    try:
        # RLIMIT_DATA: same no-op-on-macOS/effective-on-Linux story as
        # RLIMIT_AS (confirmed empirically in a memory-capped Docker
        # container — setrlimit fails outright on macOS, and a real
        # over-limit allocation raises MemoryError immediately on Linux).
        # Kept alongside RLIMIT_AS, not instead of it: on Linux both apply,
        # and a single massive allocation (e.g. `[0] * 10**12`) can raise
        # MemoryError in-process fast enough to beat the parent's RSS-poll
        # watchdog to the punch — this is the in-process backstop for that
        # race, not a replacement for the watchdog (which is still the only
        # real defense against many-small-allocations growth on macOS).
        resource.setrlimit(resource.RLIMIT_DATA, (2 * 1024**3, 2 * 1024**3))
    except (ValueError, OSError):
        pass

    # Harness is fully imported and resource-limited — tell the parent so it
    # can stop counting cold-start/import time against timeout_seconds and
    # start the real per-script deadline from here instead.
    conn.send(("ready", None))

    builder = Builder()
    tools = {
        name: _bind_to_builder(getattr(pydsl_module, name), builder)
        for name in pydsl_module.__all__
        if callable(getattr(pydsl_module, name)) and not isinstance(getattr(pydsl_module, name), type)
    }

    try:
        executor = LocalPythonExecutor(
            additional_authorized_imports=[], timeout_seconds=timeout_seconds
        )
        executor.send_tools(tools)
        # `math` is already in smolagents' BASE_BUILTIN_MODULES (import math
        # works today regardless of additional_authorized_imports), but a
        # weaker model reading the system prompt's "no imports" line has no
        # way to know that and never tries. Pre-inject it directly so
        # math.pi/math.sqrt/etc. work with zero import statement at all —
        # `import math` remains equally valid (rebinds the same module
        # object, a harmless no-op) for a model that ignores the prompt and
        # imports it anyway.
        executor.send_variables({"math": math})
        executor(script)
        diagram_ir = builder.build()
        # Names bound to a container (a tuple from regular_sectors(), a list
        # built in a loop) never have a `.id` themselves, so they're excluded
        # here automatically — editing can't ground a request against a
        # container's identity across turns (see design doc, Component 1).
        variable_ids = {
            name: value.id
            for name, value in executor.state.items()
            if hasattr(value, "id") and isinstance(getattr(value, "id", None), str)
        }
        conn.send(("ok", {"diagram_ir": diagram_ir.model_dump(), "variable_ids": variable_ids}))
    except ExecutionTimeoutError as exc:
        conn.send(("error", (str(exc), "timeout", None)))
    except Exception as exc:  # noqa: BLE001 — must report every failure kind to the parent
        message = str(exc)
        error_type = classify_failure(message)
        retry_message = build_retry_message(message, script)
        conn.send(("error", (message, error_type, retry_message)))


def run_script(
    script: str, timeout_seconds: float = 5.0, _target: Callable = _run_in_subprocess
) -> ScriptResult:
    # _target is a testing-only seam for substituting a fake child process
    # (e.g. one that sleeps before sending "ready") to exercise the
    # bootstrap-wait/deadline protocol below without a real multi-second
    # sympy/numpy/matplotlib import — production code always uses the
    # default and should never pass this.
    ctx = multiprocessing.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    process = ctx.Process(
        target=_target, args=(script, timeout_seconds, child_conn)
    )
    process.start()
    child_conn.close()  # parent doesn't write; close its copy of the write end
    logger.info("sandbox: spawned pid=%s for a %.1fs script timeout", process.pid, timeout_seconds)

    # Wait for the child's "ready" sentinel (sent once smolagents/sympy/numpy/
    # matplotlib are imported and rlimits are set) before starting the real
    # timeout_seconds-based deadline below — otherwise cold-start import time
    # on a cold container eats directly into the script's own execution
    # budget with no way to tell the difference from the outside. This
    # bootstrap wait is deliberately generous (_BOOTSTRAP_TIMEOUT_SECONDS) and
    # bounds only "is the harness hung or dead," e.g. an ImportError or crash
    # during setup that exits the child before it ever sends anything.
    bootstrap_start = time.monotonic()
    bootstrap_deadline = bootstrap_start + _BOOTSTRAP_TIMEOUT_SECONDS
    ready = False
    setup_error = None  # (message, error_type, retry_message) if the child reported why it never got to "ready"
    while process.is_alive() and time.monotonic() < bootstrap_deadline:
        if parent_conn.poll(_POLL_INTERVAL_SECONDS):
            try:
                kind, payload = parent_conn.recv()
            except (EOFError, OSError):
                break
            if kind == "ready":
                ready = True
                break
            if kind == "error":
                setup_error = payload
                break
            if kind == "progress":
                # Not terminal — log and keep waiting for "ready"/"error".
                # This is what actually distinguishes "which import step is
                # slow" from just "still alive," which a single "ready" (or
                # nothing at all, if it never arrives) can't tell apart.
                logger.info(
                    "sandbox: pid=%s progress: %s (+%.2fs)",
                    process.pid, payload, time.monotonic() - bootstrap_start,
                )
                continue
            break
    bootstrap_elapsed = time.monotonic() - bootstrap_start

    if ready:
        logger.info("sandbox: pid=%s ready after %.2fs", process.pid, bootstrap_elapsed)
    else:
        # Snapshot exitcode/aliveness BEFORE we kill it ourselves — once we
        # call process.kill(), exitcode always just reflects OUR SIGKILL,
        # destroying the one signal that distinguishes "died on its own for
        # a diagnosable reason" from "was still alive when we gave up."
        died_on_its_own = not process.is_alive()
        exitcode_before_our_kill = process.exitcode if died_on_its_own else None
        process.kill()
        process.join()
        if setup_error is not None:
            message, error_type, retry_message = setup_error
            logger.warning(
                "sandbox: pid=%s reported a setup error after %.2fs: %s",
                process.pid, bootstrap_elapsed, retry_message,
            )
            return ScriptResult(diagram_ir=None, error=message, error_type=error_type, retry_message=retry_message)
        if died_on_its_own:
            reason = _describe_exitcode(exitcode_before_our_kill)
            logger.warning(
                "sandbox: pid=%s died with no report after %.2fs (%s)",
                process.pid, bootstrap_elapsed, reason,
            )
            msg = (
                f"sandbox failed to start: child process died with no report after "
                f"{bootstrap_elapsed:.1f}s ({reason}) — likely OOM-killed or crashed "
                f"before its own error handling could run"
            )
        else:
            logger.warning(
                "sandbox: pid=%s never sent 'ready' within %.1fs bootstrap budget, killed",
                process.pid, _BOOTSTRAP_TIMEOUT_SECONDS,
            )
            msg = (
                f"sandbox failed to start: child never sent 'ready' within the "
                f"{_BOOTSTRAP_TIMEOUT_SECONDS:.0f}s bootstrap budget (still importing/"
                f"setting up when killed)"
            )
        return ScriptResult(diagram_ir=None, error=msg, error_type="timeout", retry_message=msg)

    deadline = time.monotonic() + timeout_seconds + 2.0  # wall-clock backstop, independent of the child
    killed_for_memory = False
    received = None  # (kind, payload) once a result has actually been read off the pipe
    while process.is_alive() and time.monotonic() < deadline:
        # poll() only means "at least one byte is readable" (it's a bare
        # select() under the hood, see multiprocessing.connection.Connection._poll)
        # — NOT "a full message has arrived." A result payload larger than
        # one OS pipe buffer (~16-64KB) is written by the child across
        # multiple os.write() calls, so recv() (which blocks until the whole
        # framed message is in) must be called as soon as poll() fires,
        # not deferred behind a process.join() — join() doesn't read
        # anything, so a child still mid-send would sit blocked waiting for
        # us to drain the pipe while we sit blocked waiting for it to exit:
        # a deadlock that used to resolve itself only via the 2s join
        # timeout below killing the child mid-write, truncating the message
        # into an EOFError and misreporting a large-but-successful result as
        # "subprocess exited without a result."
        if parent_conn.poll(0):
            try:
                received = parent_conn.recv()
            except (EOFError, OSError):
                received = None
            break
        rss = _child_rss_bytes(process.pid)
        if rss is not None and rss > _MAX_CHILD_RSS_BYTES:
            killed_for_memory = True
            break
        process.join(timeout=_POLL_INTERVAL_SECONDS)

    if killed_for_memory or (received is None and process.is_alive()):
        # Note: the non-memory branch only fires when process.is_alive() is
        # still True (that's required by the `or` above), so there's no
        # "died on its own" exitcode to capture here — unlike the bootstrap
        # wait above, this is always a genuine still-running timeout.
        process.kill()
        process.join()
        if killed_for_memory:
            logger.warning("sandbox: pid=%s exceeded the RSS watchdog threshold, killed", process.pid)
            msg = "script exceeded memory limit"
            return ScriptResult(diagram_ir=None, error=msg, error_type="memory_limit", retry_message=msg)
        logger.warning(
            "sandbox: pid=%s exceeded the %.1fs wall-clock deadline, killed",
            process.pid, timeout_seconds + 2.0,
        )
        msg = "script exceeded wall-clock timeout"
        return ScriptResult(diagram_ir=None, error=msg, error_type="timeout", retry_message=msg)

    if received is None:
        # The child exited on its own (e.g. between our last poll and the
        # is_alive() check above) without us catching it via poll() in the
        # loop — give the pipe one last chance before giving up.
        try:
            if not parent_conn.poll(timeout=1.0):
                raise EOFError
            received = parent_conn.recv()
        except (EOFError, OSError):
            received = None

    # Reap the process regardless of which branch produced `received` — it
    # should finish tearing down almost immediately once done sending;
    # bound the wait so a trusted-code hang during cleanup can't block the
    # caller indefinitely.
    process.join(timeout=2.0)
    if process.is_alive():
        process.kill()
        process.join()

    if received is None:
        # process exited but never sent anything (e.g. OOM-killed by the OS
        # before reaching conn.send) — treat as a timeout-class failure,
        # not "no error".
        msg = "subprocess exited without a result"
        return ScriptResult(diagram_ir=None, error=msg, error_type="timeout", retry_message=msg)
    kind, payload = received

    if kind == "ok":
        return ScriptResult(
            diagram_ir=DiagramIR.model_validate(payload["diagram_ir"]),
            variable_ids=payload["variable_ids"],
            error=None,
            error_type=None,
        )
    message, error_type, retry_message = payload
    return ScriptResult(diagram_ir=None, error=message, error_type=error_type, retry_message=retry_message)
