"""Retry-loop support: classifies executor failures and produces a retry
prompt message, including did-you-mean suggestions for hallucinated API
names. Lives here, not in the shim, because LocalPythonExecutor's own name
resolution never consults a module-level __getattr__ — see the design doc.

classify_failure/build_retry_message accept EITHER a raw Exception (for
direct/unit-test use) OR a bare message string (for the real sandboxed path
in Task 10/11, where LocalPythonExecutor wraps every tool-raised exception —
including our own ValueError/OpCapExceededError — into a single
InterpreterError whose message embeds the original type name as text, and
only that string survives crossing the subprocess queue). Both call sites
use this one implementation so the two paths can't classify differently.
"""
from __future__ import annotations

import difflib
import inspect
import re

import geometry_diagrams.pydsl as pydsl_module
from geometry_diagrams.pydsl.builder import OpCapExceededError

# The did-you-mean candidate pool must match what Task 10 actually injects as
# executor tools: functions only, not handle classes (Point, Triangle, ...
# are never callable in a script, so suggesting one would be worse than no
# suggestion at all).
PUBLIC_API_FUNCTION_NAMES = [
    name for name in pydsl_module.__all__
    if inspect.isfunction(getattr(pydsl_module, name))
]

_NAME_ERROR_PATTERN = re.compile(r"variable `([^`]+)`")
_FORBIDDEN_CALL_PATTERN = re.compile(r"Forbidden function evaluation: '([^']+)' is not among")
_IMPORT_PATTERN = re.compile(r"Import of (\S+) is not allowed")
_WRAPPED_TYPE_PATTERN = re.compile(r"due to: (\w+):")
_DANGEROUS_NAMES = {"exec", "eval", "open", "compile", "__import__"}


def suggest_name(bad_name: str, candidates: list[str]) -> str | None:
    matches = difflib.get_close_matches(bad_name, candidates, n=1)
    return matches[0] if matches else None


def classify_failure(exc_or_message: "Exception | str") -> str:
    if isinstance(exc_or_message, NameError):
        return "hallucinated_api"
    if isinstance(exc_or_message, OpCapExceededError):
        return "syntax_or_timeout"
    if isinstance(exc_or_message, ValueError):
        return "structural_precondition"
    if isinstance(exc_or_message, MemoryError):
        return "memory_limit"

    message = str(exc_or_message)
    if _IMPORT_PATTERN.search(message):
        return "import_error"
    forbidden = _FORBIDDEN_CALL_PATTERN.search(message)
    if forbidden:
        return "dangerous_call" if forbidden.group(1) in _DANGEROUS_NAMES else "hallucinated_api"
    if _NAME_ERROR_PATTERN.search(message):
        # A bare undefined-variable reference (not a call) — verified against
        # the real library that this raises with the message
        # "...due to: InterpreterError: The variable `x` is not defined.",
        # NOT a wrapped NameError, so the _WRAPPED_TYPE_PATTERN branch below
        # would never catch it without this explicit check.
        return "hallucinated_api"
    wrapped = _WRAPPED_TYPE_PATTERN.search(message)
    if wrapped:
        type_name = wrapped.group(1)
        if type_name == "NameError":
            return "hallucinated_api"
        if type_name == "OpCapExceededError":
            return "syntax_or_timeout"
        if type_name == "ValueError":
            return "structural_precondition"
        if type_name == "MemoryError":
            return "memory_limit"
    return "syntax_or_timeout"


def _extract_bad_name(message: str) -> "str | None":
    match = _FORBIDDEN_CALL_PATTERN.search(message) or _NAME_ERROR_PATTERN.search(message)
    return match.group(1) if match else None


def build_retry_message(exc_or_message: "Exception | str", script: str) -> str:
    message = str(exc_or_message)
    if classify_failure(exc_or_message) in ("hallucinated_api", "dangerous_call"):
        bad_name = _extract_bad_name(message)
        if bad_name:
            suggestion = suggest_name(bad_name, PUBLIC_API_FUNCTION_NAMES)
            if suggestion:
                message = f"{message} — did you mean '{suggestion}'?"
    return message
