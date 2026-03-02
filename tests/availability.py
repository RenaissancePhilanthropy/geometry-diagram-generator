from __future__ import annotations

import os

import httpx
from dotenv import load_dotenv


def renderer_available(base_url: str = "http://localhost:8001") -> bool:
    try:
        httpx.get(f"{base_url}/health", timeout=2.0)
        return True
    except Exception:
        return False


def api_key_available(env_var: str = "ANTHROPIC_API_KEY") -> bool:
    load_dotenv()
    return bool(os.getenv(env_var))
