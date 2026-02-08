"""Tests for avatar_engine.web.bridge — WebSocket event adapter."""

import asyncio
import pytest

from avatar_engine.events import (
    EngineState,
    ErrorEvent,
    EventEmitter,
    StateEvent,
    TextEvent,
    ThinkingEvent,
    ThinkingPhase,
    ToolEvent,
)
from avatar_engine.types import BridgeState
from avatar_engine.web.bridge import WebSocketBridge


class FakeWebSocket:
    """Fake WebSocket for testing broadcast behavior."""

    def __init__(self, fail: bool = False):
        self.sent: list = []
        self.fail = fail

    async def send_json(self, data: dict) -> None:
        if self.fail:
            raise ConnectionError("Dead client")
        self.sent.append(data)


def _run(coro):
    """Helper to run async code in tests without pytest-asyncio."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestWebSocketBridgeRegistration:
    """Handler registration and unregistration."""

    def test_registers_handlers(self):
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        assert emitter.handler_count() >= 8
        bridge.unregister()

    def test_unregister_cleans_up(self):
        emitter = EventEmitter()
        initial = emitter.handler_count()
        bridge = WebSocketBridge(emitter)
        registered = emitter.handler_count()
        assert registered > initial
        bridge.unregister()
        assert emitter.handler_count() == initial


class TestWebSocketBridgeClientManagement:
    """Client add/remove and broadcast."""

    def test_add_client(self):
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        ws = FakeWebSocket()
        _run(bridge.add_client(ws))
        assert bridge.client_count == 1
        bridge.unregister()

    def test_remove_client(self):
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        ws = FakeWebSocket()
        _run(bridge.add_client(ws))
        _run(bridge.remove_client(ws))
        assert bridge.client_count == 0
        bridge.unregister()

    def test_remove_nonexistent_client_ok(self):
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        ws = FakeWebSocket()
        _run(bridge.remove_client(ws))
        assert bridge.client_count == 0
        bridge.unregister()

    def test_broadcast_to_multiple_clients(self):
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        ws1 = FakeWebSocket()
        ws2 = FakeWebSocket()
        _run(bridge.add_client(ws1))
        _run(bridge.add_client(ws2))

        msg = {"type": "test", "data": {"x": 1}}
        _run(bridge._async_broadcast(msg))

        assert len(ws1.sent) == 1
        assert len(ws2.sent) == 1
        assert ws1.sent[0]["type"] == "test"
        bridge.unregister()

    def test_dead_client_removed(self):
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        ws_good = FakeWebSocket()
        ws_dead = FakeWebSocket(fail=True)
        _run(bridge.add_client(ws_good))
        _run(bridge.add_client(ws_dead))
        assert bridge.client_count == 2

        _run(bridge._async_broadcast({"type": "test", "data": {}}))

        assert bridge.client_count == 1
        assert len(ws_good.sent) == 1
        bridge.unregister()


class TestWebSocketBridgeEngineState:
    """Engine state tracking mirrors DisplayManager."""

    def test_initial_state_is_idle(self):
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        assert bridge.engine_state == EngineState.IDLE
        bridge.unregister()

    def test_thinking_event_sets_thinking(self):
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        emitter.emit(ThinkingEvent(phase=ThinkingPhase.ANALYZING, is_start=True))
        assert bridge.engine_state == EngineState.THINKING
        bridge.unregister()

    def test_thinking_complete_sets_responding(self):
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        emitter.emit(ThinkingEvent(is_start=True))
        assert bridge.engine_state == EngineState.THINKING
        emitter.emit(ThinkingEvent(is_complete=True))
        assert bridge.engine_state == EngineState.RESPONDING
        bridge.unregister()

    def test_tool_started_sets_executing(self):
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        emitter.emit(ToolEvent(tool_name="Read", status="started"))
        assert bridge.engine_state == EngineState.TOOL_EXECUTING
        bridge.unregister()

    def test_error_event_sets_error(self):
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        emitter.emit(ErrorEvent(error="boom"))
        assert bridge.engine_state == EngineState.ERROR
        bridge.unregister()

    def test_state_event_ready_sets_idle(self):
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        bridge._engine_state = EngineState.ERROR
        emitter.emit(StateEvent(new_state=BridgeState.READY))
        assert bridge.engine_state == EngineState.IDLE
        bridge.unregister()

    def test_state_event_error_sets_error(self):
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        emitter.emit(StateEvent(new_state=BridgeState.ERROR))
        assert bridge.engine_state == EngineState.ERROR
        bridge.unregister()


class TestWebSocketBridgeBroadcast:
    """Event broadcasts produce correct JSON messages."""

    def test_text_event_broadcast(self):
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        ws = FakeWebSocket()
        _run(bridge.add_client(ws))

        _run(bridge._async_broadcast({"type": "text", "data": {"text": "Hello"}}))

        assert len(ws.sent) == 1
        assert ws.sent[0]["type"] == "text"
        assert ws.sent[0]["data"]["text"] == "Hello"
        bridge.unregister()

    def test_broadcast_message_public_api(self):
        emitter = EventEmitter()
        bridge = WebSocketBridge(emitter)
        ws = FakeWebSocket()
        _run(bridge.add_client(ws))

        msg = {"type": "chat_response", "data": {"content": "Done"}}
        _run(bridge._async_broadcast(msg))

        assert len(ws.sent) == 1
        assert ws.sent[0]["type"] == "chat_response"
        bridge.unregister()
