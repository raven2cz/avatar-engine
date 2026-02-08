"""Tests for avatar_engine.web.server — FastAPI routes.

Uses httpx TestClient for REST endpoints.
WebSocket tests use FastAPI's built-in WS test support.
"""

import pytest

# Skip all tests if fastapi is not installed
fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from avatar_engine.types import (
    BridgeResponse,
    HealthStatus,
    ProviderCapabilities,
)


def _make_mock_manager():
    """Create a mock EngineSessionManager."""
    manager = MagicMock()
    manager.is_started = True

    # Mock engine
    engine = MagicMock()
    engine.session_id = "test-session-123"
    engine.current_provider = "gemini"
    engine.capabilities = ProviderCapabilities(
        thinking_supported=True,
        streaming=True,
    )
    engine.get_health.return_value = HealthStatus(
        healthy=True,
        state="ready",
        provider="gemini",
        session_id="test-session-123",
    )
    engine.get_history.return_value = []
    engine._bridge = MagicMock()
    engine._bridge.get_usage.return_value = {"total_cost_usd": 0.05}
    engine._started = True

    manager.engine = engine
    manager.ws_bridge = MagicMock()
    manager.ws_bridge.engine_state = MagicMock()
    manager.ws_bridge.engine_state.value = "idle"
    manager.ensure_started = AsyncMock(return_value=engine)
    manager.start = AsyncMock()
    manager.shutdown = AsyncMock()

    return manager


def _make_test_app(manager=None):
    """Create a test app with mocked manager injected into closure.

    We patch EngineSessionManager to return our mock, so that both
    app.state.manager AND the on_startup closure use the same mock.
    """
    from unittest.mock import patch as _patch

    if manager:
        with _patch(
            "avatar_engine.web.server.EngineSessionManager",
            return_value=manager,
        ):
            from avatar_engine.web.server import create_app
            app = create_app(provider="gemini", serve_static=False)
        return app
    else:
        from avatar_engine.web.server import create_app
        return create_app(provider="gemini", serve_static=False)


class TestRESTEndpoints:
    """REST endpoint tests using httpx TestClient."""

    def test_health_endpoint(self):
        manager = _make_mock_manager()
        app = _make_test_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/avatar/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["healthy"] is True
            assert data["provider"] == "gemini"

    def test_capabilities_endpoint(self):
        manager = _make_mock_manager()
        app = _make_test_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/avatar/capabilities")
            assert resp.status_code == 200
            data = resp.json()
            assert data["thinking_supported"] is True
            assert data["streaming"] is True

    def test_history_endpoint_empty(self):
        manager = _make_mock_manager()
        app = _make_test_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/avatar/history")
            assert resp.status_code == 200
            assert resp.json() == []

    def test_usage_endpoint(self):
        manager = _make_mock_manager()
        app = _make_test_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/avatar/usage")
            assert resp.status_code == 200
            assert resp.json()["total_cost_usd"] == 0.05

    def test_clear_endpoint(self):
        manager = _make_mock_manager()
        app = _make_test_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/avatar/clear")
            assert resp.status_code == 200
            assert resp.json()["status"] == "cleared"
            manager.engine.clear_history.assert_called_once()

    def test_chat_endpoint(self):
        manager = _make_mock_manager()
        # Mock chat response
        manager.engine.chat = AsyncMock(
            return_value=BridgeResponse(
                content="Hello back!",
                success=True,
                duration_ms=500,
            )
        )
        app = _make_test_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/api/avatar/chat",
                json={"message": "Hello"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["content"] == "Hello back!"
            assert data["success"] is True

    def test_chat_empty_message_rejected(self):
        manager = _make_mock_manager()
        app = _make_test_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/avatar/chat", json={"message": ""})
            assert resp.status_code == 400


class TestCORS:
    """CORS middleware is configured."""

    def test_cors_headers_present(self):
        manager = _make_mock_manager()
        app = _make_test_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.options(
                "/api/avatar/health",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert "access-control-allow-origin" in resp.headers
