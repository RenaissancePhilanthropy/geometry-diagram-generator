"""Tests for geometry_diagrams/config.py's GeometryConfig."""
from __future__ import annotations

import os
from unittest.mock import patch

from geometry_diagrams.config import GeometryConfig, resolve_config


def test_default_edit_generation_mode_is_full_rewrite():
    cfg = GeometryConfig()
    assert cfg.edit_generation_mode == "full_rewrite"


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
