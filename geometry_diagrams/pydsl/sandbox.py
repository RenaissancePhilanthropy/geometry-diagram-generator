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

The child process is a plain subprocess.Popen running
`python -m geometry_diagrams.pydsl._sandbox_child` (see that module for the
actual script-execution logic and its own extensive comments), NOT a
multiprocessing.Process. Confirmed empirically (2026-08-13): multiprocessing's
"spawn" start method re-executes whatever module happens to be the CALLING
process's __main__ inside the child (per Python's own "Safe importing of
main module" docs) — on this project's Vercel/AWS Lambda deployment, that's
Vercel's own vc_init.py, whose top level unconditionally re-execs the entire
downstream app's own handler module. That re-executed bootstrap can hang
indefinitely, freezing the child forever before any of our own sandbox code
ever runs — reproduced locally (a hang in a __main__ module's top-level code
freezes a spawned child exactly the way production's sandbox did: alive,
zero progress ever reported, 100% reproducible regardless of warm/cold).
subprocess.Popen with this file as an explicit target sidesteps the entire
category: exec() replaces the process image outright, so nothing about
whatever module was the parent's __main__ is ever touched or re-run.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import resource
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field

from geometry_diagrams.ir.ir import DiagramIR

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 0.05
_MAX_CHILD_RSS_BYTES = 512 * 1024 * 1024  # 512MB; well below a typical dev machine's headroom
# Generous on purpose: covers cold-start smolagents/sympy/numpy/matplotlib
# import time on a cold container (e.g. a cold AWS Lambda invocation), which
# is trusted harness setup, not the untrusted script's own execution budget.
# The child sends a "ready" sentinel once setup is done and only then does
# run_script() start the real timeout_seconds-based deadline — so this value
# only bounds "is the harness hung/dead," not "is this taking a while."
_BOOTSTRAP_TIMEOUT_SECONDS = 60.0
_PAGE_SIZE = resource.getpagesize()
_IS_LINUX = sys.platform.startswith("linux")
_STDERR_TAIL_CHARS = 4000  # cap how much accumulated stderr we ever put in an error message

# The default child command: run _sandbox_child.py as an explicit `-m`
# target. Never passed explicitly except by tests (see run_script's
# _child_argv param) — a fake argv there lets the bootstrap-wait/deadline
# protocol be exercised without a real multi-second sympy/numpy/matplotlib
# import.
_DEFAULT_CHILD_ARGV = [sys.executable, "-m", "geometry_diagrams.pydsl._sandbox_child"]

_EOF = object()  # sentinel placed on the message queue when the child's stdout closes


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
    """Human-readable summary of a dead subprocess.Popen's returncode:
    negative means killed by signal -returncode (e.g. -9 = SIGKILL, often OOM
    or our own proc.kill()); non-negative means it exited on its own
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


def _pump_stdout(stdout, q: "queue.Queue") -> None:
    """Runs in a background thread for the lifetime of the child: blocks on
    readline() until a full line (or EOF) is available and puts it on `q`.
    Separating this from the polling loop below means "wait for the next
    message, but give up after N seconds" never has to worry about a partial
    line sitting in the pipe buffer — readline() itself only ever returns a
    complete line (or the empty string at EOF), so a result payload larger
    than one OS pipe buffer is handled automatically: the OS-level read()
    calls inside this thread's readline() drain the pipe as fast as the
    child can write, with no risk of the deadlock/truncation class of bug
    the old multiprocessing.Pipe-based implementation had to work around
    explicitly (see git history)."""
    try:
        for line in stdout:
            q.put(line)
    except (OSError, ValueError):
        pass
    finally:
        q.put(_EOF)


def _pump_stderr(stderr, lines: list, lock: threading.Lock) -> None:
    """Runs in a background thread for the lifetime of the child, accumulating
    stderr for diagnostic purposes. subprocess.Popen gives each child its own
    dedicated pipe for this — unlike the multiprocessing-based predecessor,
    there's no shared-fd risk in capturing it (a dup2-based capture around a
    fork was considered and rejected there specifically because process-wide
    fd 1/2 are shared with other concurrent work in the same process)."""
    try:
        for line in stderr:
            with lock:
                lines.append(line)
    except (OSError, ValueError):
        pass


def _stderr_tail(lines: list, lock: "threading.Lock") -> str:
    with lock:
        text = "".join(lines)
    return text[-_STDERR_TAIL_CHARS:]


def run_script(
    script: str,
    timeout_seconds: float = 5.0,
    _child_argv: "list[str] | None" = None,
) -> ScriptResult:
    # _child_argv is a testing-only seam for substituting a fake child
    # command (e.g. `[sys.executable, "-c", "<script that sleeps before
    # printing ready>"]`) to exercise the bootstrap-wait/deadline protocol
    # below without a real multi-second sympy/numpy/matplotlib import —
    # production code always uses the default and should never pass this.
    argv = _child_argv if _child_argv is not None else _DEFAULT_CHILD_ARGV

    # Forward the current sys.path via PYTHONPATH: multiprocessing's old
    # "spawn" bootstrap used to do this automatically (it explicitly
    # serializes and restores sys.path in the child — see
    # multiprocessing/spawn.py's get_preparation_data), which mattered for
    # deployments (like this one) where a vendored dependency root is added
    # to sys.path at runtime rather than via an actual PYTHONPATH env var. A
    # plain subprocess.Popen has no such protocol, so this replicates it
    # explicitly rather than silently losing it.
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)

    proc = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, env=env,
    )
    # Always set: we passed stdin/stdout/stderr=PIPE above, so Popen always
    # populates these (they're typed Optional only because Popen supports
    # not redirecting a given stream at all).
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
    proc.stdin.write(json.dumps({"script": script, "timeout_seconds": timeout_seconds}) + "\n")
    proc.stdin.flush()
    proc.stdin.close()
    logger.info("sandbox: spawned pid=%s for a %.1fs script timeout", proc.pid, timeout_seconds)

    msg_queue: "queue.Queue" = queue.Queue()
    stderr_lines: list = []
    stderr_lock = threading.Lock()
    threading.Thread(target=_pump_stdout, args=(proc.stdout, msg_queue), daemon=True).start()
    threading.Thread(target=_pump_stderr, args=(proc.stderr, stderr_lines, stderr_lock), daemon=True).start()

    def _next_message(deadline: float):
        """Returns (kind, payload) for the next well-formed message, None if
        the wait timed out with nothing new, or _EOF if the child's stdout
        closed. A line that fails to parse as JSON (a stray print from some
        dependency, not one of ours) is logged and skipped rather than
        treated as fatal."""
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                item = msg_queue.get(timeout=min(remaining, _POLL_INTERVAL_SECONDS))
            except queue.Empty:
                # Nothing new in this short slice — keep waiting up to
                # `deadline`, not give up on the very first empty poll.
                continue
            if item is _EOF:
                return _EOF
            try:
                parsed = json.loads(item)
            except (json.JSONDecodeError, TypeError):
                logger.warning("sandbox: pid=%s unparseable stdout line: %r", proc.pid, item)
                continue
            return parsed.get("kind"), parsed.get("payload")

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
    while proc.poll() is None and time.monotonic() < bootstrap_deadline:
        message = _next_message(bootstrap_deadline)
        if message is None or message is _EOF:
            break
        kind, payload = message
        if kind == "ready":
            ready = True
            break
        if kind == "error":
            setup_error = tuple(payload)
            break
        if kind == "progress":
            # Not terminal — log and keep waiting for "ready"/"error". This
            # is what actually distinguishes "which import step is slow"
            # from just "still alive," which a single "ready" (or nothing at
            # all, if it never arrives) can't tell apart.
            logger.info(
                "sandbox: pid=%s progress: %s (+%.2fs)",
                proc.pid, payload, time.monotonic() - bootstrap_start,
            )
            continue
        break
    bootstrap_elapsed = time.monotonic() - bootstrap_start

    if ready:
        logger.info("sandbox: pid=%s ready after %.2fs", proc.pid, bootstrap_elapsed)
    else:
        # Snapshot exitcode/aliveness BEFORE we kill it ourselves — once we
        # call proc.kill(), the returncode always just reflects OUR SIGKILL,
        # destroying the one signal that distinguishes "died on its own for
        # a diagnosable reason" from "was still alive when we gave up."
        exitcode_before_our_kill = proc.poll()
        died_on_its_own = exitcode_before_our_kill is not None
        proc.kill()
        proc.wait()
        if setup_error is not None:
            message, error_type, retry_message = setup_error
            logger.warning(
                "sandbox: pid=%s reported a setup error after %.2fs: %s",
                proc.pid, bootstrap_elapsed, retry_message,
            )
            return ScriptResult(diagram_ir=None, error=message, error_type=error_type, retry_message=retry_message)
        if died_on_its_own:
            reason = _describe_exitcode(exitcode_before_our_kill)
            stderr_tail = _stderr_tail(stderr_lines, stderr_lock)
            logger.warning(
                "sandbox: pid=%s died with no report after %.2fs (%s); stderr tail: %s",
                proc.pid, bootstrap_elapsed, reason, stderr_tail,
            )
            msg = (
                f"sandbox failed to start: child process died with no report after "
                f"{bootstrap_elapsed:.1f}s ({reason}) — likely OOM-killed or crashed "
                f"before its own error handling could run"
                + (f"; stderr: {stderr_tail}" if stderr_tail else "")
            )
        else:
            logger.warning(
                "sandbox: pid=%s never sent 'ready' within %.1fs bootstrap budget, killed",
                proc.pid, _BOOTSTRAP_TIMEOUT_SECONDS,
            )
            msg = (
                f"sandbox failed to start: child never sent 'ready' within the "
                f"{_BOOTSTRAP_TIMEOUT_SECONDS:.0f}s bootstrap budget (still importing/"
                f"setting up when killed)"
            )
        return ScriptResult(diagram_ir=None, error=msg, error_type="timeout", retry_message=msg)

    deadline = time.monotonic() + timeout_seconds + 2.0  # wall-clock backstop, independent of the child
    killed_for_memory = False
    received = None  # (kind, payload) once a result has actually been read off stdout
    while proc.poll() is None and time.monotonic() < deadline:
        message = _next_message(min(deadline, time.monotonic() + _POLL_INTERVAL_SECONDS))
        if message is not None and message is not _EOF:
            received = message
            break
        if message is _EOF:
            break
        rss = _child_rss_bytes(proc.pid)
        if rss is not None and rss > _MAX_CHILD_RSS_BYTES:
            killed_for_memory = True
            break

    if killed_for_memory or (received is None and proc.poll() is None):
        # Note: the non-memory branch only fires when proc.poll() is still
        # None (still running) — that's required by the `or` above, so
        # there's no "died on its own" exitcode to capture here — unlike the
        # bootstrap wait above, this is always a genuine still-running
        # timeout.
        proc.kill()
        proc.wait()
        if killed_for_memory:
            logger.warning("sandbox: pid=%s exceeded the RSS watchdog threshold, killed", proc.pid)
            msg = "script exceeded memory limit"
            return ScriptResult(diagram_ir=None, error=msg, error_type="memory_limit", retry_message=msg)
        logger.warning(
            "sandbox: pid=%s exceeded the %.1fs wall-clock deadline, killed",
            proc.pid, timeout_seconds + 2.0,
        )
        msg = "script exceeded wall-clock timeout"
        return ScriptResult(diagram_ir=None, error=msg, error_type="timeout", retry_message=msg)

    if received is None:
        # The child exited on its own (e.g. between our last check and the
        # poll() check above) without us catching a final message in the
        # loop — give the queue one last chance before giving up.
        message = _next_message(time.monotonic() + 1.0)
        if message is not None and message is not _EOF:
            received = message

    # Reap the process regardless of which branch produced `received` — it
    # should finish tearing down almost immediately once done sending;
    # bound the wait so a trusted-code hang during cleanup can't block the
    # caller indefinitely.
    try:
        proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

    if received is None:
        # process exited but never sent anything (e.g. OOM-killed by the OS
        # before reaching _send) — treat as a timeout-class failure, not "no
        # error".
        stderr_tail = _stderr_tail(stderr_lines, stderr_lock)
        msg = "subprocess exited without a result" + (f"; stderr: {stderr_tail}" if stderr_tail else "")
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
