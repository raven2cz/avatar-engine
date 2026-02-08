"""Integration tests for Avatar Engine Web GUI.

Tests end-to-end flows that exercise the full stack:
  Server (FastAPI) → SessionManager → Engine (mocked) → Bridge → WebSocket → Client

Uses httpx TestClient for REST and FastAPI's WS test support for WebSocket.
"""

import asyncio
import time

import pytest

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from avatar_engine.events import (
    CostEvent,
    DiagnosticEvent,
    EngineState,
    ErrorEvent,
    EventEmitter,
    StateEvent,
    TextEvent,
    ThinkingEvent,
    ThinkingPhase,
    ToolEvent,
)
from avatar_engine.types import (
    BridgeResponse,
    BridgeState,
    HealthStatus,
    ProviderCapabilities,
)
from avatar_engine.web.bridge import WebSocketBridge
from avatar_engine.web.protocol import event_to_dict, response_to_dict


# ============================================================================
# Fixtures / Helpers
# ============================================================================


def _make_mock_manager(provider="gemini"):
    """Create a fully-wired mock EngineSessionManager."""
    manager = MagicMock()
    manager.is_started = True

    engine = MagicMock()
    engine.session_id = "integ-session-001"
    engine.current_provider = provider
    engine.capabilities = ProviderCapabilities(
        thinking_supported=True,
        streaming=True,
        cost_tracking=(provider == "claude"),
    )
    engine.get_health.return_value = HealthStatus(
        healthy=True,
        state="ready",
        provider=provider,
        session_id="integ-session-001",
    )
    engine.get_history.return_value = []
    engine._bridge = MagicMock()
    engine._bridge.get_usage.return_value = {
        "total_cost_usd": 0.0,
        "total_requests": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
    }
    engine._started = True
    engine.clear_history = MagicMock()
    engine.list_sessions = AsyncMock(return_value=[])

    manager.engine = engine
    manager.ws_bridge = MagicMock()
    manager.ws_bridge.engine_state = MagicMock()
    manager.ws_bridge.engine_state.value = "idle"
    manager.ws_bridge.add_client = AsyncMock()
    manager.ws_bridge.remove_client = AsyncMock()
    manager.ws_bridge.broadcast_message = MagicMock()
    manager.ensure_started = AsyncMock(return_value=engine)
    manager.start = AsyncMock()
    manager.shutdown = AsyncMock()

    return manager


def _make_app(manager):
    """Create FastAPI app with mock manager injected via patch."""
    with patch(
        "avatar_engine.web.server.EngineSessionManager",
        return_value=manager,
    ):
        from avatar_engine.web.server import create_app
        return create_app(provider="gemini", serve_static=False)


class FakeWebSocket:
    """Fake WS client for bridge-level tests."""

    def __init__(self, fail=False):
        self.sent: list = []
        self.fail = fail

    async def send_json(self, data: dict) -> None:
        if self.fail:
            raise ConnectionError("Dead")
        self.sent.append(data)


def _run(coro):
    """Run async in sync tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ============================================================================
# REST: Full flow — health → capabilities → chat → history → clear
# ============================================================================


class TestRESTFullFlow:
    """Simulate a complete REST client session."""

    def test_full_rest_session_flow(self):
        """Health → Capabilities → Chat → Usage → Clear."""
        manager = _make_mock_manager("claude")
        manager.engine.chat = AsyncMock(
            return_value=BridgeResponse(
                content="I can help with that!",
                success=True,
                duration_ms=850,
                cost_usd=0.003,
            )
        )
        app = _make_app(manager)

        with TestClient(app, raise_server_exceptions=False) as client:
            # 1. Health check
            resp = client.get("/api/avatar/health")
            assert resp.status_code == 200
            health = resp.json()
            assert health["healthy"] is True
            assert health["provider"] == "claude"

            # 2. Capabilities
            resp = client.get("/api/avatar/capabilities")
            assert resp.status_code == 200
            caps = resp.json()
            assert caps["thinking_supported"] is True
            assert caps["cost_tracking"] is True

            # 3. Chat
            resp = client.post("/api/avatar/chat", json={"message": "Hello"})
            assert resp.status_code == 200
            chat = resp.json()
            assert chat["content"] == "I can help with that!"
            assert chat["success"] is True
            assert chat["cost_usd"] == 0.003

            # 4. Usage
            resp = client.get("/api/avatar/usage")
            assert resp.status_code == 200
            assert "total_cost_usd" in resp.json()

            # 5. Clear
            resp = client.post("/api/avatar/clear")
            assert resp.status_code == 200
            assert resp.json()["status"] == "cleared"
            manager.engine.clear_history.assert_called_once()

    def test_multiple_chat_requests(self):
        """Sequential chat requests maintain engine state."""
        manager = _make_mock_manager()
        call_count = 0

        async def _chat(msg):
            nonlocal call_count
            call_count += 1
            return BridgeResponse(
                content=f"Reply #{call_count} to: {msg}",
                success=True,
                duration_ms=100 * call_count,
            )

        manager.engine.chat = AsyncMock(side_effect=_chat)
        app = _make_app(manager)

        with TestClient(app, raise_server_exceptions=False) as client:
            r1 = client.post("/api/avatar/chat", json={"message": "First"})
            r2 = client.post("/api/avatar/chat", json={"message": "Second"})
            r3 = client.post("/api/avatar/chat", json={"message": "Third"})

            assert r1.json()["content"] == "Reply #1 to: First"
            assert r2.json()["content"] == "Reply #2 to: Second"
            assert r3.json()["content"] == "Reply #3 to: Third"
            assert manager.engine.chat.call_count == 3


# ============================================================================
# REST: Engine not started (503 responses)
# ============================================================================


class TestRESTEngineNotStarted:
    """All endpoints handle engine=None gracefully."""

    def _make_no_engine_manager(self):
        manager = _make_mock_manager()
        manager.engine = None
        manager.ws_bridge = None
        return manager

    def test_health_503(self):
        manager = self._make_no_engine_manager()
        app = _make_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/avatar/health")
            assert resp.status_code == 503
            assert resp.json()["healthy"] is False

    def test_capabilities_503(self):
        manager = self._make_no_engine_manager()
        app = _make_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/avatar/capabilities")
            assert resp.status_code == 503

    def test_history_empty_when_no_engine(self):
        manager = self._make_no_engine_manager()
        app = _make_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/avatar/history")
            assert resp.status_code == 200
            assert resp.json() == []

    def test_sessions_empty_when_no_engine(self):
        manager = self._make_no_engine_manager()
        app = _make_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/avatar/sessions")
            assert resp.status_code == 200
            assert resp.json() == []

    def test_clear_ok_when_no_engine(self):
        manager = self._make_no_engine_manager()
        app = _make_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/avatar/clear")
            assert resp.status_code == 200


# ============================================================================
# REST: Input validation
# ============================================================================


class TestRESTValidation:
    """Input validation edge cases."""

    def test_chat_empty_message(self):
        manager = _make_mock_manager()
        app = _make_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/avatar/chat", json={"message": ""})
            assert resp.status_code == 400

    def test_chat_missing_message_key(self):
        manager = _make_mock_manager()
        app = _make_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/avatar/chat", json={"text": "hello"})
            assert resp.status_code == 400

    def test_stop_endpoint(self):
        manager = _make_mock_manager()
        app = _make_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/avatar/stop")
            assert resp.status_code == 200
            assert resp.json()["status"] == "stopped"
            manager.shutdown.assert_called_once()


# ============================================================================
# WebSocket: Full lifecycle
# ============================================================================


class TestWebSocketLifecycle:
    """WebSocket connect → exchange messages → disconnect."""

    def test_ws_connect_receives_connected_message(self):
        """Client connects and immediately gets session info."""
        manager = _make_mock_manager("gemini")
        app = _make_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            with client.websocket_connect("/api/avatar/ws") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "connected"
                assert msg["data"]["session_id"] == "integ-session-001"
                assert msg["data"]["provider"] == "gemini"
                assert msg["data"]["engine_state"] == "idle"
                assert "capabilities" in msg["data"]
                assert msg["data"]["capabilities"]["thinking_supported"] is True

    def test_ws_ping_pong(self):
        """Ping receives pong with timestamp."""
        manager = _make_mock_manager()
        app = _make_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            with client.websocket_connect("/api/avatar/ws") as ws:
                ws.receive_json()  # consume connected
                ws.send_json({"type": "ping"})
                msg = ws.receive_json()
                assert msg["type"] == "pong"
                assert "ts" in msg["data"]
                assert isinstance(msg["data"]["ts"], float)

    def test_ws_clear_history(self):
        """Clear history via WS."""
        manager = _make_mock_manager()
        app = _make_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            with client.websocket_connect("/api/avatar/ws") as ws:
                ws.receive_json()  # connected
                ws.send_json({"type": "clear_history"})
                msg = ws.receive_json()
                assert msg["type"] == "history_cleared"
                manager.engine.clear_history.assert_called_once()

    def test_ws_unknown_message_type_returns_error(self):
        """Unknown message types get error response."""
        manager = _make_mock_manager()
        app = _make_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            with client.websocket_connect("/api/avatar/ws") as ws:
                ws.receive_json()  # connected
                ws.send_json({"type": "invalid_action"})
                msg = ws.receive_json()
                assert msg["type"] == "error"
                assert "Unknown message type" in msg["data"]["error"]

    def test_ws_empty_chat_message_rejected(self):
        """Empty chat message returns error."""
        manager = _make_mock_manager()
        app = _make_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            with client.websocket_connect("/api/avatar/ws") as ws:
                ws.receive_json()  # connected
                ws.send_json({"type": "chat", "data": {"message": ""}})
                msg = ws.receive_json()
                assert msg["type"] == "error"
                assert "Empty message" in msg["data"]["error"]

    def test_ws_engine_not_started_closes_connection(self):
        """WS endpoint closes if engine is None."""
        manager = _make_mock_manager()
        manager.engine = None
        manager.ws_bridge = None
        app = _make_app(manager)
        with TestClient(app, raise_server_exceptions=False) as client:
            with client.websocket_connect("/api/avatar/ws") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "error"
                assert "not started" in msg["data"]["error"].lower()


# ============================================================================
# WebSocketBridge: Event → JSON broadcast pipeline
# ============================================================================


class TestEventBroadcastPipeline:
    """Events emitted on the engine arrive as JSON at WS clients."""

    def test_text_event_broadcasts_to_client(self):
        """TextEvent → JSON → client.sent[]."""
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        ws = FakeWebSocket()
        _run(bridge.add_client(ws))

        event = TextEvent(text="Hello world", is_complete=False, provider="gemini")
        msg = event_to_dict(event)
        _run(bridge._async_broadcast(msg))

        assert len(ws.sent) == 1
        assert ws.sent[0]["type"] == "text"
        assert ws.sent[0]["data"]["text"] == "Hello world"
        assert ws.sent[0]["data"]["is_complete"] is False
        bridge.unregister()

    def test_thinking_event_broadcasts_with_phase(self):
        """ThinkingEvent with phase/subject serialized correctly."""
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        ws = FakeWebSocket()
        _run(bridge.add_client(ws))

        event = ThinkingEvent(
            thought="Analyzing imports",
            phase=ThinkingPhase.ANALYZING,
            subject="imports",
            is_start=True,
            provider="gemini",
        )
        msg = event_to_dict(event)
        _run(bridge._async_broadcast(msg))

        assert ws.sent[0]["data"]["phase"] == "analyzing"
        assert ws.sent[0]["data"]["subject"] == "imports"
        bridge.unregister()

    def test_tool_event_broadcasts_with_params(self):
        """ToolEvent includes tool name, status, and parameters."""
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        ws = FakeWebSocket()
        _run(bridge.add_client(ws))

        event = ToolEvent(
            tool_name="Read",
            tool_id="t-42",
            parameters={"file_path": "/src/main.py"},
            status="started",
            provider="claude",
        )
        msg = event_to_dict(event)
        _run(bridge._async_broadcast(msg))

        data = ws.sent[0]["data"]
        assert data["tool_name"] == "Read"
        assert data["status"] == "started"
        assert data["parameters"]["file_path"] == "/src/main.py"
        bridge.unregister()

    def test_cost_event_broadcasts(self):
        """CostEvent with USD and token counts."""
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        ws = FakeWebSocket()
        _run(bridge.add_client(ws))

        event = CostEvent(cost_usd=0.0456, input_tokens=1200, output_tokens=800)
        msg = event_to_dict(event)
        _run(bridge._async_broadcast(msg))

        data = ws.sent[0]["data"]
        assert data["cost_usd"] == 0.0456
        assert data["input_tokens"] == 1200
        assert data["output_tokens"] == 800
        bridge.unregister()

    def test_error_event_broadcasts(self):
        """ErrorEvent with recoverable flag."""
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        ws = FakeWebSocket()
        _run(bridge.add_client(ws))

        event = ErrorEvent(error="Rate limit exceeded", recoverable=True)
        msg = event_to_dict(event)
        _run(bridge._async_broadcast(msg))

        data = ws.sent[0]["data"]
        assert data["error"] == "Rate limit exceeded"
        assert data["recoverable"] is True
        bridge.unregister()

    def test_state_event_enum_serialized(self):
        """StateEvent enums serialized to strings."""
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        ws = FakeWebSocket()
        _run(bridge.add_client(ws))

        event = StateEvent(
            old_state=BridgeState.WARMING_UP,
            new_state=BridgeState.READY,
        )
        msg = event_to_dict(event)
        _run(bridge._async_broadcast(msg))

        data = ws.sent[0]["data"]
        assert data["old_state"] == "warming_up"
        assert data["new_state"] == "ready"
        bridge.unregister()

    def test_diagnostic_event_broadcasts(self):
        """DiagnosticEvent forwarded with level and source."""
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        ws = FakeWebSocket()
        _run(bridge.add_client(ws))

        event = DiagnosticEvent(
            message="Deprecated API call",
            level="warning",
            source="stderr",
        )
        msg = event_to_dict(event)
        _run(bridge._async_broadcast(msg))

        data = ws.sent[0]["data"]
        assert data["message"] == "Deprecated API call"
        assert data["level"] == "warning"
        bridge.unregister()

    def test_chat_response_broadcast(self):
        """BridgeResponse serialized as chat_response message."""
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        ws = FakeWebSocket()
        _run(bridge.add_client(ws))

        response = BridgeResponse(
            content="Here is the answer",
            success=True,
            duration_ms=1500,
            cost_usd=0.01,
        )
        msg = response_to_dict(response)
        _run(bridge._async_broadcast(msg))

        assert ws.sent[0]["type"] == "chat_response"
        data = ws.sent[0]["data"]
        assert data["content"] == "Here is the answer"
        assert data["success"] is True
        assert data["duration_ms"] == 1500
        bridge.unregister()


# ============================================================================
# WebSocketBridge: Engine state transitions
# ============================================================================


class TestEngineStateTransitions:
    """Full state machine: idle → thinking → responding → tool → idle."""

    def test_full_thinking_to_responding_cycle(self):
        """IDLE → THINKING → RESPONDING (thinking complete)."""
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        assert bridge.engine_state == EngineState.IDLE

        emitter.emit(ThinkingEvent(
            thought="Let me think...",
            phase=ThinkingPhase.ANALYZING,
            is_start=True,
        ))
        assert bridge.engine_state == EngineState.THINKING

        emitter.emit(ThinkingEvent(is_complete=True))
        assert bridge.engine_state == EngineState.RESPONDING
        bridge.unregister()

    def test_thinking_to_tool_execution(self):
        """THINKING → TOOL_EXECUTING when tool starts."""
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)

        emitter.emit(ThinkingEvent(is_start=True))
        assert bridge.engine_state == EngineState.THINKING

        emitter.emit(ToolEvent(tool_name="Bash", status="started"))
        assert bridge.engine_state == EngineState.TOOL_EXECUTING
        bridge.unregister()

    def test_error_then_recovery(self):
        """ERROR → IDLE on state=READY."""
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)

        emitter.emit(ErrorEvent(error="Network timeout"))
        assert bridge.engine_state == EngineState.ERROR

        emitter.emit(StateEvent(new_state=BridgeState.READY))
        assert bridge.engine_state == EngineState.IDLE
        bridge.unregister()

    def test_bridge_error_state_sets_engine_error(self):
        """BridgeState.ERROR → EngineState.ERROR."""
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)

        emitter.emit(StateEvent(new_state=BridgeState.ERROR))
        assert bridge.engine_state == EngineState.ERROR
        bridge.unregister()

    def test_multiple_thinking_phases(self):
        """Multiple thinking events keep state as THINKING."""
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)

        emitter.emit(ThinkingEvent(
            phase=ThinkingPhase.ANALYZING, is_start=True,
        ))
        assert bridge.engine_state == EngineState.THINKING

        emitter.emit(ThinkingEvent(
            thought="Now planning...",
            phase=ThinkingPhase.PLANNING,
        ))
        assert bridge.engine_state == EngineState.THINKING

        emitter.emit(ThinkingEvent(
            thought="Reviewing...",
            phase=ThinkingPhase.REVIEWING,
        ))
        assert bridge.engine_state == EngineState.THINKING

        emitter.emit(ThinkingEvent(is_complete=True))
        assert bridge.engine_state == EngineState.RESPONDING
        bridge.unregister()


# ============================================================================
# WebSocketBridge: Multi-client scenarios
# ============================================================================


class TestMultiClientBroadcast:
    """Multiple WebSocket clients receive broadcasts correctly."""

    def test_all_clients_receive_same_message(self):
        """N clients all get the same event."""
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        clients = [FakeWebSocket() for _ in range(5)]
        for ws in clients:
            _run(bridge.add_client(ws))

        msg = {"type": "text", "data": {"text": "broadcast test"}}
        _run(bridge._async_broadcast(msg))

        for ws in clients:
            assert len(ws.sent) == 1
            assert ws.sent[0]["data"]["text"] == "broadcast test"
        bridge.unregister()

    def test_dead_client_removed_others_unaffected(self):
        """Dead client is removed; healthy clients keep receiving."""
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)

        ws_good1 = FakeWebSocket()
        ws_dead = FakeWebSocket(fail=True)
        ws_good2 = FakeWebSocket()

        _run(bridge.add_client(ws_good1))
        _run(bridge.add_client(ws_dead))
        _run(bridge.add_client(ws_good2))
        assert bridge.client_count == 3

        _run(bridge._async_broadcast({"type": "test", "data": {}}))
        assert bridge.client_count == 2
        assert len(ws_good1.sent) == 1
        assert len(ws_good2.sent) == 1

        # Second broadcast still works
        _run(bridge._async_broadcast({"type": "test2", "data": {}}))
        assert len(ws_good1.sent) == 2
        assert len(ws_good2.sent) == 2
        bridge.unregister()

    def test_client_add_remove_during_session(self):
        """Clients can join and leave mid-session."""
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)

        ws1 = FakeWebSocket()
        _run(bridge.add_client(ws1))
        _run(bridge._async_broadcast({"type": "msg1", "data": {}}))
        assert len(ws1.sent) == 1

        # Second client joins
        ws2 = FakeWebSocket()
        _run(bridge.add_client(ws2))
        _run(bridge._async_broadcast({"type": "msg2", "data": {}}))
        assert len(ws1.sent) == 2  # got both
        assert len(ws2.sent) == 1  # got only second

        # First client leaves
        _run(bridge.remove_client(ws1))
        _run(bridge._async_broadcast({"type": "msg3", "data": {}}))
        assert len(ws1.sent) == 2  # no more
        assert len(ws2.sent) == 2  # still receiving
        bridge.unregister()

    def test_zero_clients_broadcast_is_noop(self):
        """Broadcasting with no clients doesn't crash."""
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        _run(bridge._async_broadcast({"type": "lonely", "data": {}}))
        assert bridge.client_count == 0
        bridge.unregister()


# ============================================================================
# Protocol: Full event round-trip
# ============================================================================


class TestProtocolRoundTrip:
    """Verify every event type produces valid JSON with all fields."""

    def _assert_valid_message(self, msg, expected_type):
        assert msg is not None
        assert "type" in msg
        assert "data" in msg
        assert msg["type"] == expected_type
        assert isinstance(msg["data"], dict)

    def test_all_8_event_types_serialize(self):
        """Every event type produces a valid message dict."""
        events = [
            (TextEvent(text="Hi"), "text"),
            (ThinkingEvent(thought="hmm", phase=ThinkingPhase.ANALYZING), "thinking"),
            (ToolEvent(tool_name="Read", status="started"), "tool"),
            (StateEvent(new_state=BridgeState.READY), "state"),
            (CostEvent(cost_usd=0.01, input_tokens=100, output_tokens=50), "cost"),
            (ErrorEvent(error="oops"), "error"),
            (DiagnosticEvent(message="info", level="info"), "diagnostic"),
        ]
        # ActivityEvent needs import
        from avatar_engine.events import ActivityEvent, ActivityStatus
        events.append((
            ActivityEvent(
                activity_id="a1",
                name="Reading file",
                status=ActivityStatus.RUNNING,
            ),
            "activity",
        ))

        for event, expected_type in events:
            msg = event_to_dict(event)
            self._assert_valid_message(msg, expected_type)

    def test_response_to_dict_includes_all_fields(self):
        """BridgeResponse serialization includes all fields."""
        resp = BridgeResponse(
            content="answer",
            success=True,
            error=None,
            duration_ms=123,
            session_id="s1",
            cost_usd=0.005,
            tool_calls=3,
        )
        msg = response_to_dict(resp)
        self._assert_valid_message(msg, "chat_response")
        data = msg["data"]
        assert data["content"] == "answer"
        assert data["success"] is True
        assert data["error"] is None
        assert data["duration_ms"] == 123
        assert data["session_id"] == "s1"
        assert data["cost_usd"] == 0.005
        assert data["tool_calls"] == 3


# ============================================================================
# Session Manager lifecycle (unit-level but exercises the real class)
# ============================================================================


class TestSessionManagerLifecycle:
    """EngineSessionManager create → start → shutdown."""

    def test_create_manager_does_not_start_engine(self):
        from avatar_engine.web.session_manager import EngineSessionManager
        with patch("avatar_engine.web.session_manager.AvatarEngine"):
            mgr = EngineSessionManager(provider="gemini")
            assert mgr.engine is None
            assert mgr.ws_bridge is None
            assert mgr.is_started is False

    def test_shutdown_without_start_is_safe(self):
        from avatar_engine.web.session_manager import EngineSessionManager
        with patch("avatar_engine.web.session_manager.AvatarEngine"):
            mgr = EngineSessionManager(provider="gemini")
            _run(mgr.shutdown())  # should not raise

    def test_double_start_is_idempotent(self):
        from avatar_engine.web.session_manager import EngineSessionManager
        mock_engine_cls = MagicMock()
        mock_engine = MagicMock()
        mock_engine._started = True
        mock_engine.start = AsyncMock()
        mock_engine_cls.return_value = mock_engine

        with patch("avatar_engine.web.session_manager.AvatarEngine", mock_engine_cls):
            mgr = EngineSessionManager(provider="gemini")
            _run(mgr.start())
            _run(mgr.start())  # second call should be no-op
            mock_engine.start.assert_called_once()

    def test_shutdown_cleans_up_bridge(self):
        from avatar_engine.web.session_manager import EngineSessionManager
        mock_engine_cls = MagicMock()
        mock_engine = MagicMock()
        mock_engine._started = True
        mock_engine.start = AsyncMock()
        mock_engine.stop = AsyncMock()
        mock_engine_cls.return_value = mock_engine

        with patch("avatar_engine.web.session_manager.AvatarEngine", mock_engine_cls):
            with patch("avatar_engine.web.session_manager.WebSocketBridge") as mock_bridge_cls:
                mock_bridge = MagicMock()
                mock_bridge_cls.return_value = mock_bridge

                mgr = EngineSessionManager(provider="gemini")
                _run(mgr.start())
                assert mgr.ws_bridge is not None

                _run(mgr.shutdown())
                mock_bridge.unregister.assert_called_once()
                mock_engine.stop.assert_called_once()
                assert mgr.engine is None
                assert mgr.ws_bridge is None
