from __future__ import annotations

import os

import httpx
from dotenv import dotenv_values

_TRUTHY = {"1", "true", "yes", "on"}


def _env(name: str) -> str:
    """Read ``name`` from the process environment, falling back to ``.env``.

    Reads ``.env`` without mutating ``os.environ`` (unlike ``load_dotenv``), so
    importing a test module never changes the environment other tests see.
    """
    value = os.environ.get(name)
    if value is not None:
        return value
    try:
        return dotenv_values().get(name) or ""
    except Exception:
        return ""


def renderer_available(base_url: str = "http://localhost:8001") -> bool:
    try:
        httpx.get(f"{base_url}/health", timeout=2.0)
        return True
    except Exception:
        return False


def api_key_available(env_var: str = "ANTHROPIC_API_KEY") -> bool:
    return bool(_env(env_var))


def llm_tests_enabled(env_var: str = "RUN_LLM_TESTS") -> bool:
    return _env(env_var).strip().lower() in _TRUTHY
