"""Tests for ir/font.py FontConfig."""
from __future__ import annotations

import base64
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from geometry_diagrams.ir.font import FontConfig, FONT_VARIANTS, default_font_config, _FONTS_DIR


def test_font_variants_tuple():
    assert FONT_VARIANTS == ("Regular", "Bold", "Italic", "BoldItalic")


def test_font_config_url():
    cfg = FontConfig(family="NunitoSans")
    assert cfg.url("Regular") == "/fonts/NunitoSans-Regular.ttf"
    assert cfg.url("Bold") == "/fonts/NunitoSans-Bold.ttf"
    assert cfg.url("Italic") == "/fonts/NunitoSans-Italic.ttf"
    assert cfg.url("BoldItalic") == "/fonts/NunitoSans-BoldItalic.ttf"


def test_font_config_url_custom_family():
    cfg = FontConfig(family="MyFont")
    assert cfg.url("Regular") == "/fonts/MyFont-Regular.ttf"


def test_font_config_file_path():
    cfg = FontConfig(family="NunitoSans")
    p = cfg.file_path("Regular")
    assert p == _FONTS_DIR / "NunitoSans-Regular.ttf"
    assert isinstance(p, Path)


def test_font_config_data_uri(tmp_path):
    # Write a fake font file and patch _FONTS_DIR
    fake_ttf = b"\x00\x01\x02\x03fake font data"
    family = "TestFont"
    (tmp_path / f"{family}-Regular.ttf").write_bytes(fake_ttf)

    cfg = FontConfig(family=family)
    with patch("geometry_diagrams.ir.font._FONTS_DIR", tmp_path):
        uri = cfg.data_uri("Regular")

    expected_b64 = base64.b64encode(fake_ttf).decode("ascii")
    assert uri == f"data:font/ttf;base64,{expected_b64}"


def test_font_config_data_uri_missing_file():
    cfg = FontConfig(family="DoesNotExist")
    with pytest.raises(FileNotFoundError):
        cfg.data_uri("Regular")


def test_default_font_config_default():
    with patch.dict(os.environ, {}, clear=True):
        cfg = default_font_config()
    assert cfg.family == "NunitoSans"


def test_default_font_config_env_override():
    with patch.dict(os.environ, {"DIAGRAM_FONT_FAMILY": "Roboto"}):
        cfg = default_font_config()
    assert cfg.family == "Roboto"
