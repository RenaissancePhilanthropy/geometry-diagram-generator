"""Unit tests for the renderer container's server (renderer/app/main.py).

The TeX toolchain is mocked out: these tests cover the queue/worker logic,
request limits and subprocess handling, not rendering. When FastAPI is not
installed (it is only a container dependency) a minimal stand-in lets the
module import, and the HTTP-level tests are skipped.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

_MAIN = Path(__file__).parent.parent / "renderer" / "app" / "main.py"
_HAS_FASTAPI = importlib.util.find_spec("fastapi") is not None


def _load_server():
    """Import renderer/app/main.py as a fresh module."""
    saved = {k: sys.modules.get(k) for k in ("fastapi",)}
    if not _HAS_FASTAPI:
        fake = types.ModuleType("fastapi")

        class HTTPException(Exception):
            def __init__(self, status_code, detail=None):
                self.status_code, self.detail = status_code, detail

        class FastAPI:
            def __init__(self, **kw):
                self.state = types.SimpleNamespace()

            def post(self, *_a, **_k):
                return lambda f: f

            get = post

        fake.FastAPI, fake.HTTPException = FastAPI, HTTPException
        sys.modules["fastapi"] = fake
    try:
        spec = importlib.util.spec_from_file_location("renderer_server_under_test", _MAIN)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if not _HAS_FASTAPI:
            if saved["fastapi"] is None:
                sys.modules.pop("fastapi", None)


@pytest.fixture
def server():
    return _load_server()


def test_request_fields_are_size_capped(server):
    from pydantic import ValidationError

    server.RenderReq(tikz="x" * server.MAX_FIELD_CHARS)
    with pytest.raises(ValidationError):
        server.RenderReq(tikz="x" * (server.MAX_FIELD_CHARS + 1))
    with pytest.raises(ValidationError):
        server.RenderReq(tikz="x", tkzelements="x" * (server.MAX_FIELD_CHARS + 1))


def test_run_cmd_does_not_block_and_kills_on_timeout(server, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "TIMEOUT_S", 0.3)

    async def scenario():
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.02)
                ticks += 1

        t = asyncio.create_task(ticker())
        with pytest.raises(server.CommandTimeout):
            await server.run_cmd([sys.executable, "-c", "import time; time.sleep(30)"], str(tmp_path))
        t.cancel()
        return ticks

    assert asyncio.run(scenario()) >= 5  # the loop kept running meanwhile


def test_run_cmd_returns_code_and_output(server, tmp_path):
    code, out = asyncio.run(
        server.run_cmd([sys.executable, "-c", "print('hi'); raise SystemExit(3)"], str(tmp_path))
    )
    assert code == 3 and out.strip() == "hi"


def test_render_svg_passes_no_shell_escape_and_returns_svg(server, monkeypatch):
    calls = []

    async def fake_run_cmd(cmd, cwd):
        calls.append(cmd)
        if cmd[0] == "dvisvgm":
            (Path(cwd) / "out.svg").write_text("<svg/>")
        return 0, "ok"

    monkeypatch.setattr(server, "run_cmd", fake_run_cmd)

    async def scenario():
        server.sem = asyncio.Semaphore(1)
        return await server.render_svg(server.RenderReq(tikz="\\draw (0,0)--(1,1);"))

    res = asyncio.run(scenario())
    assert res["ok"] and res["svg"] == "<svg/>"
    assert "--no-shell-escape" in calls[0]


def test_render_svg_reports_stage_timeout(server, monkeypatch):
    async def fake_run_cmd(cmd, cwd):
        raise server.CommandTimeout("lualatex timed out after 15s")

    monkeypatch.setattr(server, "run_cmd", fake_run_cmd)

    async def scenario():
        server.sem = asyncio.Semaphore(1)
        return await server.render_svg(server.RenderReq(tikz="x"))

    res = asyncio.run(scenario())
    assert res["ok"] is False and res["stage"] == "lualatex"


def test_workers_run_concurrently_and_survive_cancelled_requests(server, monkeypatch):
    """MAX_CONCURRENT workers run in parallel; a request whose future was
    cancelled while queued or rendering does not kill its worker."""
    running = 0
    peak = 0

    async def fake_render(req):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.1)
        running -= 1
        return {"ok": True, "svg": req.tikz}

    monkeypatch.setattr(server, "render_svg", fake_render)

    async def scenario():
        server.queue = asyncio.Queue(maxsize=16)
        loop = asyncio.get_running_loop()
        workers = [asyncio.create_task(server.worker()) for _ in range(2)]
        futs = []
        for i in range(4):
            fut = loop.create_future()
            await server.queue.put((server.RenderReq(tikz=str(i)), fut))
            futs.append(fut)
        futs[0].cancel()  # cancelled while its render is in flight
        futs[3].cancel()  # cancelled while still queued
        results = await asyncio.wait_for(asyncio.gather(futs[1], futs[2]), 5)
        await asyncio.wait_for(server.queue.join(), 5)
        alive = [not w.done() for w in workers]
        for w in workers:
            w.cancel()
        return results, alive

    results, alive = asyncio.run(scenario())
    assert [r["svg"] for r in results] == ["1", "2"]
    assert all(alive)
    assert peak == 2


@pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi is only installed in the renderer container")
def test_http_render_roundtrip_and_oversize_rejected(server, monkeypatch):
    from fastapi.testclient import TestClient

    async def fake_render(req):
        return {"ok": True, "svg": "<svg/>", "log": ""}

    monkeypatch.setattr(server, "render_svg", fake_render)
    with TestClient(server.app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        r = client.post("/render", json={"tikz": "x"})
        assert r.status_code == 200 and r.json()["svg"] == "<svg/>"
        r = client.post("/render", json={"tikz": "x" * (server.MAX_FIELD_CHARS + 1)})
        assert r.status_code == 422
