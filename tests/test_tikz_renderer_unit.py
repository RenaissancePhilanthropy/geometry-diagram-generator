"""
Unit tests for util/tikz_renderer.py — behavior hard to cover with real Docker.
These mock httpx to test URL/env-var routing and payload construction only.
Real success/failure paths are covered by test_tikz_renderer.py (Docker required).
"""

from unittest.mock import MagicMock, patch

import httpx

from util.tikz_renderer import render_tikz


def _ok_response() -> MagicMock:
    mock = MagicMock(spec=httpx.Response)
    mock.json.return_value = {"ok": True, "svg": "<svg/>", "log": ""}
    mock.raise_for_status = MagicMock()
    return mock


def test_uses_env_var_url(monkeypatch):
    monkeypatch.setenv("TIKZ_RENDERER_URL", "http://custom-host:9999")
    with patch("httpx.post", return_value=_ok_response()) as mock_post:
        render_tikz(r"\tkzDefPoint(0,0){A}")
    called_url = mock_post.call_args[0][0]
    assert "custom-host:9999" in called_url


def test_renderer_url_param_overrides_env(monkeypatch):
    monkeypatch.setenv("TIKZ_RENDERER_URL", "http://env-host:8001")
    with patch("httpx.post", return_value=_ok_response()) as mock_post:
        render_tikz(r"\tkzDefPoint(0,0){A}", renderer_url="http://param-host:7777")
    called_url = mock_post.call_args[0][0]
    assert "param-host:7777" in called_url


def test_includes_tkzelements_in_payload():
    lua = "z.A = point: new (0, 0)"
    with patch("httpx.post", return_value=_ok_response()) as mock_post:
        render_tikz(r"\tkzDefPoint(0,0){A}", tkzelements=lua)
    payload = mock_post.call_args[1]["json"]
    assert "tkzelements" in payload
    assert payload["tkzelements"] == lua


def test_omits_tkzelements_when_none():
    with patch("httpx.post", return_value=_ok_response()) as mock_post:
        render_tikz(r"\tkzDefPoint(0,0){A}")
    payload = mock_post.call_args[1]["json"]
    assert "tikz" in payload
    assert "tkzelements" not in payload
