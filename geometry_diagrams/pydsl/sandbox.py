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

_POLL_INTERVAL_SECONDS = 0.05
_MAX_CHILD_RSS_BYTES = 512 * 1024 * 1024  # 512MB; well below a typical dev machine's headroom
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


@dataclass
class ScriptResult:
    diagram_ir: "DiagramIR | None"
    error: "str | None"
    error_type: "str | None"  # see classify_failure's return values, plus "timeout"
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


def _run_in_subprocess(script: str, timeout_seconds: float, queue: "multiprocessing.Queue") -> None:
    """Runs entirely inside the child process. Puts a (kind, payload) tuple on the queue."""
    try:
        resource.setrlimit(
            resource.RLIMIT_CPU, (int(timeout_seconds) + 1, int(timeout_seconds) + 1)
        )
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

    from smolagents import LocalPythonExecutor
    from smolagents.local_python_executor import ExecutionTimeoutError

    import geometry_diagrams.pydsl as pydsl_module

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
        queue.put(("ok", {"diagram_ir": diagram_ir.model_dump(), "variable_ids": variable_ids}))
    except ExecutionTimeoutError as exc:
        queue.put(("error", (str(exc), "timeout", None)))
    except Exception as exc:  # noqa: BLE001 — must report every failure kind to the parent
        message = str(exc)
        error_type = classify_failure(message)
        retry_message = build_retry_message(message, script)
        queue.put(("error", (message, error_type, retry_message)))


def run_script(script: str, timeout_seconds: float = 5.0) -> ScriptResult:
    ctx = multiprocessing.get_context("spawn")
    queue: multiprocessing.Queue = ctx.Queue()
    process = ctx.Process(
        target=_run_in_subprocess, args=(script, timeout_seconds, queue)
    )
    process.start()

    deadline = time.monotonic() + timeout_seconds + 2.0  # wall-clock backstop, independent of the child
    killed_for_memory = False
    while process.is_alive() and time.monotonic() < deadline:
        rss = _child_rss_bytes(process.pid)
        if rss is not None and rss > _MAX_CHILD_RSS_BYTES:
            killed_for_memory = True
            break
        process.join(timeout=_POLL_INTERVAL_SECONDS)

    if killed_for_memory or process.is_alive():
        process.kill()
        process.join()
        if killed_for_memory:
            msg = "script exceeded memory limit"
            return ScriptResult(diagram_ir=None, error=msg, error_type="memory_limit", retry_message=msg)
        msg = "script exceeded wall-clock timeout"
        return ScriptResult(diagram_ir=None, error=msg, error_type="timeout", retry_message=msg)

    try:
        kind, payload = queue.get(timeout=1.0)
    except Exception:
        # process exited but the queue feeder thread hadn't flushed yet, or the
        # child died without putting anything (e.g. OOM-killed by the OS) —
        # either way, treat as a timeout-class failure, not "no error".
        msg = "subprocess exited without a result"
        return ScriptResult(diagram_ir=None, error=msg, error_type="timeout", retry_message=msg)

    if kind == "ok":
        return ScriptResult(
            diagram_ir=DiagramIR.model_validate(payload["diagram_ir"]),
            variable_ids=payload["variable_ids"],
            error=None,
            error_type=None,
        )
    message, error_type, retry_message = payload
    return ScriptResult(diagram_ir=None, error=message, error_type=error_type, retry_message=retry_message)
