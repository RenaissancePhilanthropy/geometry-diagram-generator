"""Shared pytest hooks."""
from __future__ import annotations

import os

# One BLAS thread per process. Under pytest-xdist every worker would otherwise
# spawn a full set of numpy/scipy threads and oversubscribe the cores (the
# sandbox children inherit this too). setdefault leaves an explicit setting alone,
# and this runs before any test module imports numpy.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

from dotenv import load_dotenv  # noqa: E402

from tests.availability import llm_tests_enabled


def pytest_runtest_setup(item):
    # Live (LLM-gated) tests need API keys in os.environ. Load .env only when
    # the live-test flag is on, and at test time rather than at import time.
    if llm_tests_enabled():
        load_dotenv()
