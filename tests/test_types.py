"""Tests for avatar_engine.types module."""

import time
import pytest

from avatar_engine.types import (
    ProviderType,
    BridgeState,
    Message,
    BridgeResponse,
    HealthStatus,
)


class TestProviderType:
    """Tests for ProviderType enum."""

    def test_gemini_value(self):
        """GEMINI should have correct value."""
        assert ProviderType.GEMINI.value == "gemini"

    def test_claude_value(self):
        """CLAUDE should have correct value."""
        assert ProviderType.CLAUDE.value == "claude"

    def test_from_string(self):
        """Should be constructable from string."""
        assert ProviderType("gemini") == ProviderType.GEMINI
        assert ProviderType("claude") == ProviderType.CLAUDE

    def test_invalid_provider(self):
        """Should raise ValueError for invalid provider."""
        with pytest.raises(ValueError):
            ProviderType("invalid")


class TestBridgeState:
    """Tests for BridgeState enum."""

    def test_all_states(self):
        """All states should have correct values."""
        assert BridgeState.DISCONNECTED.value == "disconnected"
        assert BridgeState.WARMING_UP.value == "warming_up"
        assert BridgeState.READY.value == "ready"
        assert BridgeState.BUSY.value == "busy"
        assert BridgeState.ERROR.value == "error"

    def test_from_string(self):
        """Should be constructable from string."""
        assert BridgeState("ready") == BridgeState.READY


class TestMessage:
    """Tests for Message dataclass."""

    def test_required_fields(self):
        """Message requires role and content."""
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_default_timestamp(self):
        """Message should have auto-generated timestamp."""
        before = time.time()
        msg = Message(role="user", content="test")
        after = time.time()

        assert before <= msg.timestamp <= after

    def test_default_tool_calls(self):
        """Message should have empty tool_calls by default."""
        msg = Message(role="user", content="test")
        assert msg.tool_calls == []

    def test_with_tool_calls(self):
        """Message can include tool calls."""
        tools = [{"tool": "Read", "parameters": {"file": "test.py"}}]
        msg = Message(role="assistant", content="", tool_calls=tools)
        assert msg.tool_calls == tools

    def test_user_role(self):
        """User messages should work."""
        msg = Message(role="user", content="Hi")
        assert msg.role == "user"

    def test_assistant_role(self):
        """Assistant messages should work."""
        msg = Message(role="assistant", content="Hello!")
        assert msg.role == "assistant"


class TestBridgeResponse:
    """Tests for BridgeResponse dataclass."""

    def test_minimal_response(self):
        """BridgeResponse with just content should have defaults."""
        resp = BridgeResponse(content="Hello")

        assert resp.content == "Hello"
        assert resp.success is True
        assert resp.error is None
        assert resp.tool_calls == []
        assert resp.raw_events == []
        assert resp.duration_ms == 0
        assert resp.session_id is None
        assert resp.cost_usd is None
        assert resp.token_usage is None

    def test_bool_success(self):
        """BridgeResponse should be truthy when success=True."""
        resp = BridgeResponse(content="test", success=True)
        assert bool(resp) is True

    def test_bool_failure(self):
        """BridgeResponse should be falsy when success=False."""
        resp = BridgeResponse(content="", success=False, error="failed")
        assert bool(resp) is False

    def test_if_response_pattern(self):
        """Should work with `if response:` pattern."""
        success = BridgeResponse(content="ok", success=True)
        failure = BridgeResponse(content="", success=False)

        result = "yes" if success else "no"
        assert result == "yes"

        result = "yes" if failure else "no"
        assert result == "no"

    def test_full_response(self):
        """BridgeResponse with all fields."""
        resp = BridgeResponse(
            content="Test response",
            success=True,
            error=None,
            tool_calls=[{"tool": "Read"}],
            raw_events=[{"type": "message"}],
            duration_ms=150,
            session_id="abc-123",
            cost_usd=0.002,
            token_usage={"input": 50, "output": 100},
        )

        assert resp.content == "Test response"
        assert resp.tool_calls == [{"tool": "Read"}]
        assert resp.duration_ms == 150
        assert resp.session_id == "abc-123"
        assert resp.cost_usd == 0.002
        assert resp.token_usage["input"] == 50

    def test_error_response(self):
        """Error response should have success=False and error message."""
        resp = BridgeResponse(
            content="",
            success=False,
            error="Timeout after 120s",
            duration_ms=120000,
        )

        assert resp.success is False
        assert resp.error == "Timeout after 120s"
        assert not resp  # Should be falsy


class TestHealthStatus:
    """Tests for HealthStatus dataclass."""

    def test_minimal_status(self):
        """HealthStatus with required fields."""
        status = HealthStatus(
            healthy=True,
            state="ready",
            provider="gemini",
        )

        assert status.healthy is True
        assert status.state == "ready"
        assert status.provider == "gemini"

    def test_default_values(self):
        """HealthStatus should have sensible defaults."""
        status = HealthStatus(healthy=True, state="ready", provider="claude")

        assert status.session_id is None
        assert status.history_length == 0
        assert status.pid is None
        assert status.returncode is None
        assert status.total_cost_usd == 0.0
        assert status.uptime_seconds == 0.0

    def test_full_status(self):
        """HealthStatus with all fields."""
        status = HealthStatus(
            healthy=True,
            state="ready",
            provider="gemini",
            session_id="xyz-789",
            history_length=10,
            pid=12345,
            returncode=None,
            total_cost_usd=1.50,
            uptime_seconds=3600.5,
        )

        assert status.session_id == "xyz-789"
        assert status.history_length == 10
        assert status.pid == 12345
        assert status.returncode is None
        assert status.total_cost_usd == 1.50
        assert status.uptime_seconds == 3600.5

    def test_unhealthy_status(self):
        """Unhealthy status with error state."""
        status = HealthStatus(
            healthy=False,
            state="error",
            provider="claude",
            returncode=1,
        )

        assert status.healthy is False
        assert status.state == "error"
        assert status.returncode == 1
