"""Tests for GeometryConfig.hash_algorithm (geometry_diagrams/config.py)."""
from __future__ import annotations

import os
from unittest.mock import patch

from geometry_diagrams.config import GeometryConfig, resolve_config


def test_default_hash_algorithm_is_blake2s():
    cfg = GeometryConfig()
    assert cfg.hash_algorithm == "blake2s"


def test_from_env_reads_geometry_hash_algorithm():
    with patch.dict(os.environ, {"GEOMETRY_HASH_ALGORITHM": "xxhash"}, clear=False):
        cfg = GeometryConfig.from_env()
    assert cfg.hash_algorithm == "xxhash"


def test_resolve_config_overrides_hash_algorithm():
    base = GeometryConfig(hash_algorithm="blake2s")
    cfg = resolve_config(base, hash_algorithm="xxhash")
    assert cfg.hash_algorithm == "xxhash"


def test_resolve_config_keeps_base_when_not_overridden():
    base = GeometryConfig(hash_algorithm="xxhash")
    cfg = resolve_config(base)
    assert cfg.hash_algorithm == "xxhash"
