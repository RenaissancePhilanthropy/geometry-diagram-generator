"""use_pre_assert_step and verify_labels_in_canvas, the python_full strategy's two opt-in
quality steps, are reachable from the public facade (config fields, env vars, per-call
kwargs). Neither applies to other strategies, and neither runs on an edit turn."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from geometry_diagrams import GeometryConfig, render_geometry_diagram
from geometry_diagrams.config import resolve_config
from geometry_diagrams.strategies.python_full import PythonFullStrategy

MODEL = "anthropic:claude-sonnet-4-6"


class _Captured(Exception):
    pass


def _cfg(strategy="python_full", **kw) -> GeometryConfig:
    return GeometryConfig(strategy=strategy, renderer="svg", model=MODEL, **kw)


async def _run_kwargs(config=None, **call_kwargs) -> dict:
    """The kwargs the facade hands PythonFullStrategy.run."""
    run = AsyncMock(side_effect=_Captured)
    with patch.object(PythonFullStrategy, "run", run):
        with pytest.raises(_Captured):
            await render_geometry_diagram("a triangle", config=config or _cfg(), **call_kwargs)
    return run.call_args.kwargs


@pytest.mark.asyncio
async def test_off_by_default_and_call_shape_unchanged():
    kwargs = await _run_kwargs()
    assert "use_pre_assert_step" not in kwargs and "verify_labels_in_canvas" not in kwargs


@pytest.mark.asyncio
async def test_config_fields_reach_the_strategy():
    kwargs = await _run_kwargs(_cfg(use_pre_assert_step=True, verify_labels_in_canvas=True))
    assert kwargs["use_pre_assert_step"] is True and kwargs["verify_labels_in_canvas"] is True


@pytest.mark.asyncio
async def test_per_call_kwargs_override_config():
    kwargs = await _run_kwargs(_cfg(verify_labels_in_canvas=True), verify_labels_in_canvas=False,
                               use_pre_assert_step=True)
    assert "verify_labels_in_canvas" not in kwargs and kwargs["use_pre_assert_step"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["recipe", "structured"])
@pytest.mark.parametrize("option", ["use_pre_assert_step", "verify_labels_in_canvas"])
async def test_other_strategies_reject_the_options(strategy, option):
    with pytest.raises(ValueError, match=f"{option}.*python_full"):
        await render_geometry_diagram("a triangle", config=_cfg(strategy), **{option: True})


@pytest.mark.asyncio
async def test_edit_turns_do_not_run_them_and_do_not_fail():
    edit = AsyncMock(side_effect=_Captured)
    with patch.object(PythonFullStrategy, "edit", edit):
        with pytest.raises(_Captured):
            await render_geometry_diagram(
                "move c", previous_script="a = point(0, 0)",
                config=_cfg(use_pre_assert_step=True, verify_labels_in_canvas=True),
            )
    assert "use_pre_assert_step" not in edit.call_args.kwargs
    assert "verify_labels_in_canvas" not in edit.call_args.kwargs


def test_env_vars(monkeypatch):
    monkeypatch.setenv("GEOMETRY_USE_PRE_ASSERT_STEP", "yes")
    monkeypatch.setenv("GEOMETRY_VERIFY_LABELS_IN_CANVAS", "1")
    cfg = GeometryConfig.from_env()
    assert cfg.use_pre_assert_step is True and cfg.verify_labels_in_canvas is True
    monkeypatch.delenv("GEOMETRY_USE_PRE_ASSERT_STEP")
    monkeypatch.delenv("GEOMETRY_VERIFY_LABELS_IN_CANVAS")
    cfg = GeometryConfig.from_env()
    assert cfg.use_pre_assert_step is False and cfg.verify_labels_in_canvas is False


def test_resolve_config_merges_and_keeps_the_base():
    base = GeometryConfig(use_pre_assert_step=True)
    assert resolve_config(base).use_pre_assert_step is True
    assert resolve_config(base, use_pre_assert_step=False).use_pre_assert_step is False
    assert resolve_config(base, verify_labels_in_canvas=True).verify_labels_in_canvas is True
