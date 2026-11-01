"""*_sync wrappers work both outside and inside a running event loop."""
from __future__ import annotations

import contextvars
import threading

import pytest

from geometry_diagrams import facade
from geometry_diagrams.strategies import recipe as recipe_mod
from geometry_diagrams.strategies.base import run_sync

_marker: contextvars.ContextVar[str] = contextvars.ContextVar("marker", default="unset")


async def _coro(value):
    return value, threading.current_thread() is threading.main_thread(), _marker.get()


def test_run_sync_without_a_loop_runs_in_place():
    assert run_sync(_coro(1)) == (1, True, "unset")


@pytest.mark.asyncio
async def test_run_sync_inside_a_running_loop_uses_a_worker_thread_and_keeps_context():
    _marker.set("caller")
    value, on_main, marker = run_sync(_coro(2))
    assert value == 2
    assert on_main is False
    assert marker == "caller"


def _install_fakes(monkeypatch):
    async def fake_render(prompt, **kw):
        return ("render", prompt, kw)

    async def fake_edit(prompt, previous_dsl=None, **kw):
        return ("edit", prompt, previous_dsl)

    async def fake_select(prompt, *, model=None):
        return ("select", prompt, model)

    monkeypatch.setattr(facade, "render_geometry_diagram", fake_render)
    monkeypatch.setattr(facade, "edit_geometry_diagram", fake_edit)
    monkeypatch.setattr(recipe_mod, "select_recipes", fake_select)


def test_sync_wrappers_outside_a_loop(monkeypatch):
    _install_fakes(monkeypatch)
    assert facade.render_geometry_diagram_sync("p", renderer="svg")[:2] == ("render", "p")
    assert facade.edit_geometry_diagram_sync("p", {"a": 1}) == ("edit", "p", {"a": 1})
    assert recipe_mod.select_recipes_sync("p", model="m") == ("select", "p", "m")


@pytest.mark.asyncio
async def test_sync_wrappers_inside_a_running_loop(monkeypatch):
    _install_fakes(monkeypatch)
    assert facade.render_geometry_diagram_sync("p", renderer="svg")[:2] == ("render", "p")
    assert facade.edit_geometry_diagram_sync("p", {"a": 1}) == ("edit", "p", {"a": 1})
    assert recipe_mod.select_recipes_sync("p", model="m") == ("select", "p", "m")
