"""Sandbox child gets a minimal environment; a dying child yields a failure result."""
from __future__ import annotations

import sys
import textwrap

from geometry_diagrams.pydsl.sandbox import _build_child_env, run_script

_FAKE_CHILD_REPORTS_ITS_ENV = textwrap.dedent("""
    import json, os, sys
    sys.stdin.readline()
    print(json.dumps({"kind": "error", "payload": [
        "ENV=" + json.dumps(dict(os.environ)), "sandbox_setup_error", "env dump",
    ]}), flush=True)
""")


def test_build_child_env_drops_secrets_and_keeps_basics():
    source = {
        "PATH": "/bin",
        "HOME": "/home/x",
        "LANG": "en_US.UTF-8",
        "LC_ALL": "C",
        "PYTHONHASHSEED": "0",
        "MPLCONFIGDIR": "/tmp/mpl",
        "ANTHROPIC_API_KEY": "sk-secret",
        "OPENAI_API_KEY": "sk-secret2",
        "GITHUB_TOKEN": "ghp",
        "MY_SECRET": "s",
        "LANGFUSE_SECRET_KEY": "lf",
        "AWS_ACCESS_KEY_ID": "aws",
        "AWS_REGION": "us-east-1",
        "SOMETHING_ELSE": "x",
    }
    env = _build_child_env(source)
    for kept in ("PATH", "HOME", "LANG", "LC_ALL", "PYTHONHASHSEED", "MPLCONFIGDIR"):
        assert env[kept] == source[kept]
    for dropped in (
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GITHUB_TOKEN", "MY_SECRET",
        "LANGFUSE_SECRET_KEY", "AWS_ACCESS_KEY_ID", "AWS_REGION", "SOMETHING_ELSE",
    ):
        assert dropped not in env
    assert "PYTHONPATH" in env


def test_sentinel_secret_is_not_visible_to_child_process(monkeypatch):
    monkeypatch.setenv("SANDBOX_TEST_API_KEY", "sentinel-secret-value")
    monkeypatch.setenv("LANGFUSE_HOST_SENTINEL", "sentinel-lf")
    result = run_script(
        "ignored", timeout_seconds=1.0,
        _child_argv=[sys.executable, "-c", _FAKE_CHILD_REPORTS_ITS_ENV],
    )
    assert result.diagram_ir is None
    assert "ENV=" in (result.error or "")
    assert "sentinel-secret-value" not in result.error
    assert "sentinel-lf" not in result.error
    assert "PYTHONPATH" in result.error


def test_instantly_dying_child_yields_failure_not_exception():
    big_script = "x = 1\n" * 200_000  # larger than a pipe buffer, forcing a broken pipe
    result = run_script(
        big_script, timeout_seconds=1.0,
        _child_argv=[sys.executable, "-c", "import sys; sys.exit(3)"],
    )
    assert result.diagram_ir is None
    assert result.error
