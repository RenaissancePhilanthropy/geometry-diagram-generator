# geometry_diagrams/pydsl/_sandbox_child.py
"""Entrypoint for the sandboxed script's own child process.

Invoked via `python -m geometry_diagrams.pydsl._sandbox_child` from
sandbox.py's run_script(), using subprocess.Popen — deliberately NOT
multiprocessing. multiprocessing's "spawn" start method re-executes
whatever module happens to be the CALLING process's __main__ in the
child (per Python's own "Safe importing of main module" docs) — on a
Vercel/AWS Lambda deployment, that's Vercel's own vc_init.py, whose top
level unconditionally re-execs the entire downstream app's handler
module (confirmed by reading vc_init.py's source, 2026-08-13). That
re-executed app bootstrap can block indefinitely (e.g. re-entering a
server/event-loop setup), hanging the child forever before any of this
module's own code ever ran — confirmed empirically: production saw the
sandbox "never send ready" with zero progress pings ever, on every
single invocation, warm or cold, exactly matching a child stuck in that
unrelated re-executed bootstrap rather than a slow import.

subprocess.Popen with this file as an explicit `-m` target sidesteps that
category of bug entirely: exec() fully replaces the process image with
`python -m geometry_diagrams.pydsl._sandbox_child`, so nothing about
whatever module was the parent's __main__ is ever touched, imported, or
re-run — there is no mechanism by which it could be.

Protocol: reads a single line of JSON from stdin — {"script": str,
"timeout_seconds": float} — then writes newline-delimited JSON objects to
stdout, one per line, always in this order: zero or more
{"kind": "progress", "payload": str} pings during setup, then either
{"kind": "ready", "payload": null} once harness setup is done or an early
{"kind": "error", "payload": [message, error_type, retry_message]} if
setup itself crashed, and finally {"kind": "ok"|"error", "payload": ...}
once the script has run (or failed).
"""
from __future__ import annotations

import json
import math
import resource
import sys

from geometry_diagrams.pydsl.builder import Builder, _current_builder
from geometry_diagrams.pydsl.retry import build_retry_message, classify_failure


def _send(kind: str, payload) -> None:
    sys.stdout.write(json.dumps({"kind": kind, "payload": payload}) + "\n")
    sys.stdout.flush()


def _bind_to_builder(fn, builder: Builder):
    def wrapped(*args, **kwargs):
        token = _current_builder.set(builder)
        try:
            return fn(*args, **kwargs)
        finally:
            _current_builder.reset(token)

    return wrapped


def main() -> None:
    request = json.loads(sys.stdin.readline())
    script = request["script"]
    timeout_seconds = request["timeout_seconds"]

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
    # ever reached a try/except that could report back — the parent would
    # just see the child die with no "ready" sentinel and no way to tell
    # "harness crashed" from "harness is still importing," both surfacing
    # as the same opaque "sandbox failed to start" message. Report the real
    # exception instead so a genuine environment problem is diagnosable
    # from the caller's last_error rather than looking identical to a slow
    # cold start.
    #
    # Progress pings, not just the final "ready" sentinel: a bootstrap that
    # merely exceeds the parent's bootstrap budget (still alive, never
    # crashed) gives the parent no way to tell WHICH import is slow/stuck
    # without these.
    _send("progress", "importing smolagents")
    try:
        from smolagents import LocalPythonExecutor
        from smolagents.local_python_executor import ExecutionTimeoutError

        _send("progress", "importing geometry_diagrams.pydsl")
        import geometry_diagrams.pydsl as pydsl_module
    except Exception as exc:  # noqa: BLE001 — must report every failure kind to the parent
        import traceback
        _send("error", [traceback.format_exc(), "sandbox_setup_error", str(exc)])
        return
    _send("progress", "imports done, setting resource limits")

    try:
        # RLIMIT_CPU caps *cumulative* CPU time consumed by the process since
        # it started, not time elapsed since this setrlimit call — moving the
        # harness imports above this call only excludes their CPU cost from
        # the script's budget if the limit itself is adjusted for CPU already
        # spent. Confirmed empirically (2026-08-13, real Linux container, not
        # macOS): a process that burns 1s of CPU and only *then* calls
        # setrlimit(RLIMIT_CPU, (3, 3)) is killed at ~3s of *total* cumulative
        # CPU, i.e. with only ~2s left for whatever ran after the call —
        # identical to calling setrlimit with the same limit at process
        # start. Without this adjustment, the import-reordering above is a
        # no-op: the harness's own import cost is still charged against the
        # script's timeout_seconds budget either way, just measured from a
        # different starting line.
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
    _send("ready", None)

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
        _send("ok", {"diagram_ir": diagram_ir.model_dump(), "variable_ids": variable_ids})
    except ExecutionTimeoutError as exc:
        _send("error", [str(exc), "timeout", None])
    except Exception as exc:  # noqa: BLE001 — must report every failure kind to the parent
        message = str(exc)
        error_type = classify_failure(message)
        retry_message = build_retry_message(message, script)
        _send("error", [message, error_type, retry_message])


if __name__ == "__main__":
    main()
