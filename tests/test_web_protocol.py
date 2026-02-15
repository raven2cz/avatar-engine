"""Tests for avatar_engine.web.protocol — event serialization."""

import pytest
from avatar_engine.events import (
    ActivityEvent,
    ActivityStatus,
    CostEvent,
    DiagnosticEvent,
    ErrorEvent,
    PermissionRequestEvent,
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
from avatar_engine.web.protocol import (
    EVENT_TYPE_MAP,
    capabilities_to_dict,
    event_to_dict,
    health_to_dict,
    parse_client_message,
    response_to_dict,
)


class TestEventTypeMap:
    """EVENT_TYPE_MAP covers all 9 event types."""

    def test_has_all_event_types(self):
        assert len(EVENT_TYPE_MAP) == 9

    def test_text_event(self):
        assert EVENT_TYPE_MAP[TextEvent] == "text"

    def test_thinking_event(self):
        assert EVENT_TYPE_MAP[ThinkingEvent] == "thinking"

    def test_tool_event(self):
        assert EVENT_TYPE_MAP[ToolEvent] == "tool"

    def test_state_event(self):
        assert EVENT_TYPE_MAP[StateEvent] == "state"

    def test_cost_event(self):
        assert EVENT_TYPE_MAP[CostEvent] == "cost"

    def test_error_event(self):
        assert EVENT_TYPE_MAP[ErrorEvent] == "error"

    def test_diagnostic_event(self):
        assert EVENT_TYPE_MAP[DiagnosticEvent] == "diagnostic"

    def test_activity_event(self):
        assert EVENT_TYPE_MAP[ActivityEvent] == "activity"


class TestEventToDict:
    """event_to_dict serializes events correctly."""

    def test_text_event(self):
        event = TextEvent(text="Hello", is_complete=False, provider="gemini")
        result = event_to_dict(event)
        assert result is not None
        assert result["type"] == "text"
        assert result["data"]["text"] == "Hello"
        assert result["data"]["is_complete"] is False
        assert result["data"]["provider"] == "gemini"

    def test_thinking_event_enums_serialized(self):
        event = ThinkingEvent(
            thought="Analyzing code",
            phase=ThinkingPhase.ANALYZING,
            subject="imports",
            is_start=True,
            block_id="b1",
            provider="gemini",
        )
        result = event_to_dict(event)
        assert result is not None
        assert result["type"] == "thinking"
        assert result["data"]["phase"] == "analyzing"  # Enum -> string
        assert result["data"]["subject"] == "imports"
        assert result["data"]["is_start"] is True

    def test_tool_event(self):
        event = ToolEvent(
            tool_name="Read",
            tool_id="t1",
            parameters={"file_path": "/foo/bar.py"},
            status="started",
            provider="claude",
        )
        result = event_to_dict(event)
        assert result is not None
        assert result["type"] == "tool"
        assert result["data"]["tool_name"] == "Read"
        assert result["data"]["parameters"]["file_path"] == "/foo/bar.py"

    def test_state_event_enum_serialized(self):
        event = StateEvent(
            old_state=BridgeState.WARMING_UP,
            new_state=BridgeState.READY,
            provider="gemini",
        )
        result = event_to_dict(event)
        assert result is not None
        assert result["data"]["old_state"] == "warming_up"
        assert result["data"]["new_state"] == "ready"

    def test_cost_event(self):
        event = CostEvent(cost_usd=0.0123, input_tokens=500, output_tokens=200)
        result = event_to_dict(event)
        assert result["type"] == "cost"
        assert result["data"]["cost_usd"] == 0.0123

    def test_error_event(self):
        event = ErrorEvent(error="Something broke", recoverable=False)
        result = event_to_dict(event)
        assert result["type"] == "error"
        assert result["data"]["error"] == "Something broke"
        assert result["data"]["recoverable"] is False

    def test_diagnostic_event(self):
        event = DiagnosticEvent(message="Warning text", level="warning", source="stderr")
        result = event_to_dict(event)
        assert result["type"] == "diagnostic"
        assert result["data"]["level"] == "warning"

    def test_activity_event_enum_serialized(self):
        event = ActivityEvent(
            activity_id="a1",
            name="Read file",
            status=ActivityStatus.RUNNING,
            progress=0.5,
        )
        result = event_to_dict(event)
        assert result["type"] == "activity"
        assert result["data"]["status"] == "running"  # Enum -> string

    def test_unknown_event_returns_none(self):
        """Unknown event types return None (not crash)."""
        from avatar_engine.events import AvatarEvent
        # Create a direct AvatarEvent (not a known subclass)
        # Since AvatarEvent is ABC, we test with a mock subclass
        class UnknownEvent(AvatarEvent):
            pass

        event = UnknownEvent()
        assert event_to_dict(event) is None

    def test_timestamp_is_float(self):
        event = TextEvent(text="x")
        result = event_to_dict(event)
        assert isinstance(result["data"]["timestamp"], float)


class TestResponseToDict:
    """response_to_dict serializes BridgeResponse."""

    def test_success_response(self):
        resp = BridgeResponse(
            content="Hello world",
            success=True,
            duration_ms=1234,
            cost_usd=0.05,
        )
        result = response_to_dict(resp)
        assert result["type"] == "chat_response"
        assert result["data"]["content"] == "Hello world"
        assert result["data"]["success"] is True
        assert result["data"]["duration_ms"] == 1234

    def test_error_response(self):
        resp = BridgeResponse(content="", success=False, error="Timeout")
        result = response_to_dict(resp)
        assert result["data"]["success"] is False
        assert result["data"]["error"] == "Timeout"


class TestHealthToDict:
    def test_health_serialization(self):
        health = HealthStatus(
            healthy=True,
            state="ready",
            provider="gemini",
            session_id="s123",
        )
        result = health_to_dict(health)
        assert result["healthy"] is True
        assert result["provider"] == "gemini"


class TestCapabilitiesToDict:
    def test_capabilities_serialization(self):
        caps = ProviderCapabilities(
            thinking_supported=True,
            cost_tracking=True,
            streaming=True,
        )
        result = capabilities_to_dict(caps)
        assert result["thinking_supported"] is True
        assert result["cost_tracking"] is True


class TestParseClientMessage:
    def test_chat_message(self):
        result = parse_client_message({"type": "chat", "data": {"message": "Hello"}})
        assert result is not None
        assert result["type"] == "chat"
        assert result["data"]["message"] == "Hello"

    def test_ping_message(self):
        result = parse_client_message({"type": "ping"})
        assert result is not None
        assert result["type"] == "ping"

    def test_clear_history(self):
        result = parse_client_message({"type": "clear_history"})
        assert result is not None

    def test_stop_message(self):
        result = parse_client_message({"type": "stop"})
        assert result is not None

    def test_unknown_type_returns_none(self):
        result = parse_client_message({"type": "invalid"})
        assert result is None

    def test_missing_type_returns_none(self):
        result = parse_client_message({})
        assert result is None

    def test_missing_data_defaults_to_empty(self):
        result = parse_client_message({"type": "ping"})
        assert result["data"] == {}

    def test_permission_response_message(self):
        result = parse_client_message({
            "type": "permission_response",
            "data": {"request_id": "abc", "option_id": "allow_once", "cancelled": False},
        })
        assert result is not None
        assert result["type"] == "permission_response"
        assert result["data"]["request_id"] == "abc"
        assert result["data"]["option_id"] == "allow_once"


class TestPermissionRequestEvent:
    """PermissionRequestEvent serialization via event_to_dict."""

    def test_serialization(self):
        event = PermissionRequestEvent(
            provider="gemini",
            request_id="req-123",
            tool_name="bash",
            tool_input="rm -rf /tmp/test",
            options=[
                {"option_id": "opt1", "kind": "allow_once"},
                {"option_id": "opt2", "kind": "reject_once"},
            ],
        )
        result = event_to_dict(event)
        assert result is not None
        assert result["type"] == "permission_request"
        assert result["data"]["request_id"] == "req-123"
        assert result["data"]["tool_name"] == "bash"
        assert result["data"]["tool_input"] == "rm -rf /tmp/test"
        assert len(result["data"]["options"]) == 2
        assert result["data"]["options"][0]["kind"] == "allow_once"

    def test_event_type_in_map(self):
        assert PermissionRequestEvent in EVENT_TYPE_MAP
        assert EVENT_TYPE_MAP[PermissionRequestEvent] == "permission_request"
