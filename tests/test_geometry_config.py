"""Tests for geometry_diagrams/config.py's GeometryConfig."""
from __future__ import annotations

import os
from unittest.mock import patch

from geometry_diagrams.config import GeometryConfig, resolve_config


def test_default_edit_generation_mode_is_search_replace():
    cfg = GeometryConfig()
    assert cfg.edit_generation_mode == "search_replace"


def test_from_env_default_edit_generation_mode_is_search_replace(monkeypatch):
    # GeometryConfig.from_env() has its own separate hardcoded fallback
    # (distinct from the dataclass field default above) — this is the
    # path main.py actually goes through, and it had zero test coverage
    # before this plan, which is exactly why a mismatch between the two
    # defaults could previously go unnoticed.
    monkeypatch.delenv("GEOMETRY_EDIT_MODE", raising=False)
    cfg = GeometryConfig.from_env()
    assert cfg.edit_generation_mode == "search_replace"


def test_from_env_reads_geometry_edit_mode():
    with patch.dict(os.environ, {"GEOMETRY_EDIT_MODE": "patch"}, clear=False):
        cfg = GeometryConfig.from_env()
    assert cfg.edit_generation_mode == "patch"


def test_resolve_config_overrides_edit_generation_mode():
    base = GeometryConfig(edit_generation_mode="full_rewrite")
    cfg = resolve_config(base, edit_generation_mode="patch")
    assert cfg.edit_generation_mode == "patch"


def test_resolve_config_keeps_base_when_not_overridden():
    base = GeometryConfig(edit_generation_mode="patch")
    cfg = resolve_config(base)
    assert cfg.edit_generation_mode == "patch"


def test_geometry_config_accepts_line_number_edit_mode():
    from geometry_diagrams.config import GeometryConfig

    cfg = GeometryConfig(edit_generation_mode="line_number")
    assert cfg.edit_generation_mode == "line_number"


def test_default_sandbox_timeout_seconds_is_2_5():
    cfg = GeometryConfig()
    assert cfg.sandbox_timeout_seconds == 2.5


def test_from_env_default_sandbox_timeout_seconds_is_2_5(monkeypatch):
    monkeypatch.delenv("GEOMETRY_SANDBOX_TIMEOUT_SECONDS", raising=False)
    cfg = GeometryConfig.from_env()
    assert cfg.sandbox_timeout_seconds == 2.5


def test_from_env_reads_geometry_sandbox_timeout_seconds():
    with patch.dict(os.environ, {"GEOMETRY_SANDBOX_TIMEOUT_SECONDS": "10"}, clear=False):
        cfg = GeometryConfig.from_env()
    assert cfg.sandbox_timeout_seconds == 10.0


def test_resolve_config_overrides_sandbox_timeout_seconds():
    base = GeometryConfig(sandbox_timeout_seconds=2.5)
    cfg = resolve_config(base, sandbox_timeout_seconds=8.0)
    assert cfg.sandbox_timeout_seconds == 8.0


def test_resolve_config_keeps_base_sandbox_timeout_seconds_when_not_overridden():
    base = GeometryConfig(sandbox_timeout_seconds=8.0)
    cfg = resolve_config(base)
    assert cfg.sandbox_timeout_seconds == 8.0
