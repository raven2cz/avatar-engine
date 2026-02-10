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
    manager.prepare = AsyncMock()
    manager.start_engine = AsyncMock()
    manager.is_ready = True
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


    def test_providers_endpoint(self):
        manager = _make_mock_manager()
        app = _make_test_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/avatar/providers")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) == 3
            ids = {p["id"] for p in data}
            assert ids == {"gemini", "claude", "codex"}
            for p in data:
                assert "available" in p
                assert isinstance(p["available"], bool)
                assert "executable" in p

    def test_providers_endpoint_availability(self):
        """Providers endpoint correctly reports CLI availability."""
        manager = _make_mock_manager()
        app = _make_test_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            with patch("avatar_engine.web.server.shutil.which") as mock_which:
                mock_which.side_effect = lambda exe: "/usr/bin/gemini" if exe == "gemini" else None
                resp = client.get("/api/avatar/providers")
                assert resp.status_code == 200
                data = {p["id"]: p["available"] for p in resp.json()}
                assert data["gemini"] is True
                assert data["claude"] is False
                assert data["codex"] is False


class TestSessionTitle:
    """Session title PUT endpoint tests."""

    def test_set_session_title(self):
        """PUT sets a custom title and returns it."""
        manager = _make_mock_manager()
        with patch(
            "avatar_engine.web.server.title_registry"
        ) as mock_registry:
            mock_registry.get.return_value = None
            app = _make_test_app(manager)
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    "/api/avatar/sessions/sess-1/title",
                    json={"title": "My Custom Title"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["session_id"] == "sess-1"
                assert data["title"] == "My Custom Title"
                mock_registry.set.assert_called_once_with("sess-1", "My Custom Title")

    def test_clear_session_title(self):
        """PUT with empty title clears the custom title."""
        manager = _make_mock_manager()
        with patch(
            "avatar_engine.web.server.title_registry"
        ) as mock_registry:
            app = _make_test_app(manager)
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    "/api/avatar/sessions/sess-1/title",
                    json={"title": ""},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["title"] is None
                mock_registry.delete.assert_called_once_with("sess-1")

    def test_set_title_broadcasts_ws(self):
        """PUT broadcasts session_title_updated to WS clients."""
        manager = _make_mock_manager()
        with patch(
            "avatar_engine.web.server.title_registry"
        ) as mock_registry:
            mock_registry.get.return_value = None
            app = _make_test_app(manager)
            with TestClient(app, raise_server_exceptions=False) as client:
                # Reset call history (lifespan may have called broadcast_message)
                manager.ws_bridge.broadcast_message.reset_mock()
                client.put(
                    "/api/avatar/sessions/test-session-123/title",
                    json={"title": "New Title"},
                )
                manager.ws_bridge.broadcast_message.assert_called_once_with({
                    "type": "session_title_updated",
                    "data": {
                        "session_id": "test-session-123",
                        "title": "New Title",
                        "is_current_session": True,
                    },
                })

    def test_set_title_broadcasts_non_current(self):
        """PUT broadcasts is_current_session=False for non-current session."""
        manager = _make_mock_manager()
        with patch(
            "avatar_engine.web.server.title_registry"
        ) as mock_registry:
            mock_registry.get.return_value = None
            app = _make_test_app(manager)
            with TestClient(app, raise_server_exceptions=False) as client:
                manager.ws_bridge.broadcast_message.reset_mock()
                client.put(
                    "/api/avatar/sessions/other-session/title",
                    json={"title": "Other Title"},
                )
                manager.ws_bridge.broadcast_message.assert_called_once_with({
                    "type": "session_title_updated",
                    "data": {
                        "session_id": "other-session",
                        "title": "Other Title",
                        "is_current_session": False,
                    },
                })

    def test_whitespace_title_treated_as_empty(self):
        """PUT with whitespace-only title clears it."""
        manager = _make_mock_manager()
        with patch(
            "avatar_engine.web.server.title_registry"
        ) as mock_registry:
            app = _make_test_app(manager)
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    "/api/avatar/sessions/sess-1/title",
                    json={"title": "   "},
                )
                assert resp.status_code == 200
                assert resp.json()["title"] is None
                mock_registry.delete.assert_called_once_with("sess-1")

    def test_put_missing_title_key(self):
        """PUT with no 'title' key in body treats as clear."""
        manager = _make_mock_manager()
        with patch(
            "avatar_engine.web.server.title_registry"
        ) as mock_registry:
            app = _make_test_app(manager)
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    "/api/avatar/sessions/sess-1/title",
                    json={},
                )
                assert resp.status_code == 200
                assert resp.json()["title"] is None
                mock_registry.delete.assert_called_once_with("sess-1")

    def test_put_invalid_json_body(self):
        """PUT with non-JSON body returns 400."""
        manager = _make_mock_manager()
        with patch("avatar_engine.web.server.title_registry"):
            app = _make_test_app(manager)
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    "/api/avatar/sessions/sess-1/title",
                    content=b"not json",
                    headers={"Content-Type": "application/json"},
                )
                assert resp.status_code == 400
                assert "error" in resp.json()

    def test_put_title_no_ws_bridge(self):
        """PUT works even when no WS bridge is connected."""
        manager = _make_mock_manager()
        manager.ws_bridge = None
        with patch(
            "avatar_engine.web.server.title_registry"
        ) as mock_registry:
            mock_registry.get.return_value = None
            app = _make_test_app(manager)
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.put(
                    "/api/avatar/sessions/sess-1/title",
                    json={"title": "No WS Title"},
                )
                assert resp.status_code == 200
                assert resp.json()["title"] == "No WS Title"
                mock_registry.set.assert_called_once_with("sess-1", "No WS Title")

    def test_list_sessions_merges_custom_titles(self):
        """GET /sessions returns custom title when one is set."""
        manager = _make_mock_manager()

        # Mock list_sessions return — use same ID as engine.session_id
        session_info = MagicMock()
        session_info.session_id = "test-session-123"
        session_info.provider = "gemini"
        session_info.cwd = "/home/user"
        session_info.title = "Original provider title"
        session_info.updated_at = "2025-01-01T00:00:00"
        manager.engine.list_sessions = AsyncMock(return_value=[session_info])

        with patch(
            "avatar_engine.web.server.title_registry"
        ) as mock_registry:
            mock_registry.get.return_value = "My Custom Title"
            app = _make_test_app(manager)
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/api/avatar/sessions")
                assert resp.status_code == 200
                data = resp.json()
                assert len(data) == 1
                assert data[0]["title"] == "My Custom Title"
                assert data[0]["is_current"] is True

    def test_list_sessions_uses_provider_title_when_no_custom(self):
        """GET /sessions uses provider title when no custom title exists."""
        manager = _make_mock_manager()

        session_info = MagicMock()
        session_info.session_id = "sess-2"
        session_info.provider = "gemini"
        session_info.cwd = "/home/user"
        session_info.title = "Provider title from first message"
        session_info.updated_at = None
        manager.engine.list_sessions = AsyncMock(return_value=[session_info])

        with patch(
            "avatar_engine.web.server.title_registry"
        ) as mock_registry:
            mock_registry.get.return_value = None
            app = _make_test_app(manager)
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/api/avatar/sessions")
                assert resp.status_code == 200
                data = resp.json()
                assert data[0]["title"] == "Provider title from first message"
                assert data[0]["is_current"] is False


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
