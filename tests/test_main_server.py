"""main.py request validation, error hygiene, concurrency cap and session state."""
import asyncio
import importlib

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("GEOMETRY_STRATEGY", raising=False)
    monkeypatch.delenv("STRATEGY", raising=False)
    main = importlib.import_module("main")
    built = []

    def fake_build():
        graph = object()
        built.append(graph)
        return graph

    monkeypatch.setattr(main, "_build_agent_for_strategy", fake_build)
    monkeypatch.setattr(main, "_agent", "shared")
    monkeypatch.setattr(main, "_session_agents", main.OrderedDict())
    return main, built, TestClient(main.app)


def test_invalid_json_is_400(server):
    _, _, client = server
    for path in ("/api/invoke", "/api/"):
        resp = client.post(path, content=b"{not json", headers={"content-type": "application/json"})
        assert resp.status_code == 400


def test_wrong_types_are_400(server):
    _, _, client = server
    assert client.post("/api/invoke", json=[1, 2]).status_code == 400
    assert client.post("/api/invoke", json={"prompt": 5}).status_code == 400
    assert client.post("/api/", json={"messages": "hi"}).status_code == 400
    assert client.post("/api/", json={"messages": ["x"]}).status_code == 400
    assert client.post("/api/", json={"messages": [{"role": "user", "content": 3}]}).status_code == 400
    assert client.post("/api/", json={"messages": [], "session_id": 7}).status_code == 400
    assert client.post("/api/", json={"messages": [], "session_id": "bad id!"}).status_code == 400


def test_prompt_length_cap(server):
    main, _, client = server
    resp = client.post("/api/invoke", json={"prompt": "x" * (main.MAX_PROMPT_CHARS + 1)})
    assert resp.status_code == 413


def test_internal_error_text_not_leaked(server, monkeypatch):
    main, _, client = server

    class Boom:
        async def run(self, prompt, **kwargs):
            raise RuntimeError("secret-internal-detail /etc/path")

    monkeypatch.setattr(main, "_strategy", Boom())
    resp = client.post("/api/invoke", json={"prompt": "draw"})
    assert resp.status_code == 500
    assert "secret-internal-detail" not in resp.text
    assert resp.json()["error"] == main.GENERIC_ERROR


def test_invoke_success(server, monkeypatch):
    main, _, client = server

    class Ok:
        async def run(self, prompt, **kwargs):
            class R:
                svg = "<svg/>"

            return R()

    monkeypatch.setattr(main, "_strategy", Ok())
    resp = client.post("/api/invoke", json={"prompt": "draw"})
    assert resp.status_code == 200
    assert resp.json() == {"svg": "<svg/>"}


def test_agent_stream_error_is_generic(server):
    main, _, client = server

    class BadGraph:
        def astream_events(self, *a, **k):
            raise RuntimeError("secret-internal-detail")

    main._agent = BadGraph()
    resp = client.post("/api/", json={"messages": [{"role": "user", "content": "hi"}]})
    assert resp.status_code == 200
    assert "secret-internal-detail" not in resp.text
    assert "RUN_ERROR" in resp.text


def test_no_session_id_uses_shared_agent(server):
    main, built, _ = server
    assert main._agent_for_session(None) == "shared"
    assert main._agent_for_session(None) == "shared"
    assert built == []


def test_sessions_are_separate_and_lru_capped(server, monkeypatch):
    main, built, _ = server
    monkeypatch.setattr(main, "MAX_SESSIONS", 2)
    a = main._agent_for_session("a")
    assert main._agent_for_session("a") is a
    b = main._agent_for_session("b")
    assert b is not a
    main._agent_for_session("a")  # refresh a; b is now least recent
    main._agent_for_session("c")
    assert list(main._session_agents) == ["a", "c"]
    assert main._agent_for_session("b") is not b  # rebuilt after eviction


def test_concurrency_semaphore_bounds_runs(server, monkeypatch):
    main, _, _ = server
    state = {"active": 0, "peak": 0}

    class Slow:
        async def run(self, prompt, **kwargs):
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
            await asyncio.sleep(0.02)
            state["active"] -= 1

            class R:
                svg = ""

            return R()

    monkeypatch.setattr(main, "_strategy", Slow())

    async def go():
        monkeypatch.setattr(main, "_llm_semaphore", asyncio.Semaphore(2))

        class Req:
            async def body(self):
                return b'{"prompt": "x"}'

        await asyncio.gather(*(main.invoke(Req()) for _ in range(6)))

    asyncio.run(go())
    assert state["peak"] == 2
