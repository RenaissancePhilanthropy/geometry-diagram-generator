from __future__ import annotations

import os

_handler = None
_initialized = False


def get_callback_handler():
    """Return a LangFuse CallbackHandler when LANGFUSE_BASE_URL is set, else None.

    LANGFUSE_BASE_URL being set is the enable flag. If it is set,
    LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must also be present
    or a RuntimeError is raised.

    The handler is created once and cached for the lifetime of the process.
    """
    global _handler, _initialized
    if _initialized:
        return _handler

    base_url = os.getenv("LANGFUSE_BASE_URL")
    if not base_url:
        _initialized = True
        return None

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    missing = [name for name, val in [
        ("LANGFUSE_PUBLIC_KEY", public_key),
        ("LANGFUSE_SECRET_KEY", secret_key),
    ] if not val]
    if missing:
        raise RuntimeError(
            f"LANGFUSE_BASE_URL is set but required env vars are missing: {', '.join(missing)}"
        )

    try:
        from langfuse.callback import CallbackHandler
    except ImportError:
        raise RuntimeError(
            "LANGFUSE_BASE_URL is set but the 'langfuse' package is not installed. "
            "Install it with: uv sync --group tracing"
        )
    _handler = CallbackHandler(
        public_key=public_key,
        secret_key=secret_key,
        host=base_url,
    )
    _initialized = True
    return _handler


def _reset() -> None:
    """Reset cached handler state. For use in tests only."""
    global _handler, _initialized
    _handler = None
    _initialized = False
