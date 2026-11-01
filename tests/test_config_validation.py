"""GeometryConfig env parsing and validation (bool env, edit mode, sandbox timeout)."""
from __future__ import annotations

import pytest

from geometry_diagrams.config import GeometryConfig, resolve_config
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.strategies.python_full import PythonFullStrategy

SCRIPT = "a = point(0, 0)\nb = point(4, 0)\nc = point(0, 3)\nt = triangle(a, b, c)\ndraw(t)\n"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in (
        "DIAGRAM_EMBED_FONTS", "DIAGRAM_DEBUG_SHOW_IMPLICIT", "GEOMETRY_EDIT_MODE",
        "GEOMETRY_SANDBOX_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("raw", ["1", "true", "True", "TRUE", "yes", "YES", "on", "On", " true "])
def test_bool_env_truthy_values_any_case(monkeypatch, raw):
    monkeypatch.setenv("DIAGRAM_EMBED_FONTS", raw)
    monkeypatch.setenv("DIAGRAM_DEBUG_SHOW_IMPLICIT", raw)
    cfg = GeometryConfig.from_env()
    assert cfg.embed_fonts is True and cfg.debug_show_implicit is True


@pytest.mark.parametrize("raw", ["0", "false", "no", "off", "", "2"])
def test_bool_env_other_values_are_false(monkeypatch, raw):
    monkeypatch.setenv("DIAGRAM_EMBED_FONTS", raw)
    assert GeometryConfig.from_env().embed_fonts is False


def test_unknown_edit_mode_in_env_raises_and_lists_modes(monkeypatch):
    monkeypatch.setenv("GEOMETRY_EDIT_MODE", "serach_replace")
    with pytest.raises(ValueError, match="full_rewrite.*patch.*search_replace.*hashline.*line_number"):
        GeometryConfig.from_env()


def test_unknown_edit_mode_override_raises():
    with pytest.raises(ValueError, match="Unknown edit_generation_mode"):
        resolve_config(GeometryConfig(), edit_generation_mode="nope")


@pytest.mark.parametrize("raw", ["nan", "inf", "-1", "0", "abc", ""])
def test_bad_sandbox_timeout_in_env_raises(monkeypatch, raw):
    monkeypatch.setenv("GEOMETRY_SANDBOX_TIMEOUT_SECONDS", raw)
    with pytest.raises(ValueError, match="sandbox_timeout_seconds"):
        GeometryConfig.from_env()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0, 0.0])
def test_bad_sandbox_timeout_override_raises(value):
    with pytest.raises(ValueError, match="finite number greater than 0"):
        resolve_config(GeometryConfig(), sandbox_timeout_seconds=value)


def test_good_values_pass_through(monkeypatch):
    monkeypatch.setenv("GEOMETRY_EDIT_MODE", "hashline")
    monkeypatch.setenv("GEOMETRY_SANDBOX_TIMEOUT_SECONDS", "4.5")
    cfg = GeometryConfig.from_env()
    assert (cfg.edit_generation_mode, cfg.sandbox_timeout_seconds) == ("hashline", 4.5)


@pytest.mark.asyncio
async def test_edit_with_unknown_mode_raises_before_any_work():
    with pytest.raises(ValueError, match="Unknown edit_generation_mode"):
        await PythonFullStrategy().edit(
            "x", SCRIPT, renderer=SVGRenderer(), edit_generation_mode="bogus",
        )


@pytest.mark.asyncio
async def test_edit_with_nonpositive_sandbox_timeout_raises():
    with pytest.raises(ValueError, match="sandbox_timeout_seconds"):
        await PythonFullStrategy().edit("x", SCRIPT, renderer=SVGRenderer(), sandbox_timeout_seconds=0)


def test_build_agent_validates_mode():
    with pytest.raises(ValueError, match="Unknown edit_generation_mode"):
        PythonFullStrategy().build_agent(model="test", edit_generation_mode="bogus")
