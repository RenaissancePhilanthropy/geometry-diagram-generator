# geometry_diagrams/pydsl/retry_loop.py
"""Retry-loop driver: runs successive script attempts through run_script,
stopping on the first success or once `cap` attempts have been made.

Design doc caps: 2 for live chat, 5 for offline batch — callers pass the
cap that matches their context; this module has no opinion on which.
"""
from __future__ import annotations

from typing import Callable

from geometry_diagrams.pydsl.sandbox import ScriptResult, run_script


def run_with_retries(
    make_script: Callable[[list[ScriptResult]], str],
    cap: int,
    timeout_seconds: float = 5.0,
) -> list[ScriptResult]:
    if cap < 1:
        raise ValueError(f"cap must be >= 1, got {cap}")
    history: list[ScriptResult] = []
    for _ in range(cap):
        script = make_script(history)
        result = run_script(script, timeout_seconds=timeout_seconds)
        history.append(result)
        if result.error is None:
            break
    return history
