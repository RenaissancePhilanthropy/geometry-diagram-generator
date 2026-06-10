import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def reset_tracing():
    """Reset tracing module singleton before each test."""
    from geometry_diagrams.util import tracing
    tracing._reset()
    yield
    tracing._reset()


def test_disabled_when_no_host(monkeypatch):
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    from geometry_diagrams.util.tracing import get_callback_handler
    assert get_callback_handler() is None


def test_second_call_returns_same_none(monkeypatch):
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    from geometry_diagrams.util.tracing import get_callback_handler
    assert get_callback_handler() is None
    assert get_callback_handler() is None


def test_fatal_when_host_set_public_key_missing(monkeypatch):
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.example.com")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    from geometry_diagrams.util.tracing import get_callback_handler
    with pytest.raises(RuntimeError, match="LANGFUSE_PUBLIC_KEY"):
        get_callback_handler()


def test_fatal_when_host_set_secret_key_missing(monkeypatch):
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.example.com")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    from geometry_diagrams.util.tracing import get_callback_handler
    with pytest.raises(RuntimeError, match="LANGFUSE_SECRET_KEY"):
        get_callback_handler()


def test_fatal_when_host_set_both_keys_missing(monkeypatch):
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.example.com")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    from geometry_diagrams.util.tracing import get_callback_handler
    with pytest.raises(RuntimeError, match="LANGFUSE_PUBLIC_KEY.*LANGFUSE_SECRET_KEY"):
        get_callback_handler()


def test_returns_handler_when_all_vars_set(monkeypatch):
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.example.com")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    mock_handler = MagicMock()
    mock_cls = MagicMock(return_value=mock_handler)
    with patch.dict("sys.modules", {"langfuse": MagicMock(), "langfuse.callback": MagicMock(CallbackHandler=mock_cls)}):
        from geometry_diagrams.util.tracing import get_callback_handler
        result = get_callback_handler()
    mock_cls.assert_called_once_with(
        public_key="pk-test",
        secret_key="sk-test",
        host="https://langfuse.example.com",
    )
    assert result is mock_handler


def test_returns_cached_handler_on_second_call(monkeypatch):
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.example.com")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    mock_handler = MagicMock()
    mock_cls = MagicMock(return_value=mock_handler)
    with patch.dict("sys.modules", {"langfuse": MagicMock(), "langfuse.callback": MagicMock(CallbackHandler=mock_cls)}):
        from geometry_diagrams.util.tracing import get_callback_handler
        r1 = get_callback_handler()
        r2 = get_callback_handler()
    assert r1 is r2
    assert mock_cls.call_count == 1


def test_helpful_error_when_langfuse_not_installed(monkeypatch):
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.example.com")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    with patch.dict("sys.modules", {"langfuse": None, "langfuse.callback": None}):
        from geometry_diagrams.util.tracing import get_callback_handler
        with pytest.raises(RuntimeError, match="package is not installed"):
            get_callback_handler()
