"""Shared pytest hooks."""
from __future__ import annotations

from dotenv import load_dotenv

from tests.availability import llm_tests_enabled


def pytest_runtest_setup(item):
    # Live (LLM-gated) tests need API keys in os.environ. Load .env only when
    # the live-test flag is on, and at test time rather than at import time.
    if llm_tests_enabled():
        load_dotenv()
