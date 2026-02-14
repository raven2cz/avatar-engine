"""Tests for bridge implementations with mocks."""

import asyncio
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from avatar_engine.bridges.base import BaseBridge, BridgeState
from avatar_engine.bridges.claude import ClaudeBridge
from avatar_engine.bridges.gemini import GeminiBridge
from avatar_engine.types import BridgeResponse, Message


# =============================================================================
# Mock Helpers
# =============================================================================


def make_mock_process(
    stdout_lines: List[str],
    returncode: int = 0,
) -> MagicMock:
    """Create a mock asyncio subprocess."""
    proc = MagicMock()
    proc.pid = 12345
    proc.returncode = returncode

    # Mock stdin
    proc.stdin = MagicMock()
    proc.stdin.write = MagicMock()
    proc.stdin.drain = AsyncMock()
    proc.stdin.close = MagicMock()

    # Mock stdout as async readline
    stdout_iter = iter(stdout_lines)

    async def mock_readline():
        try:
            line = next(stdout_iter)
            return line.encode() if line else b""
        except StopIteration:
            return b""

    async def mock_read(_n=None):
        try:
            line = next(stdout_iter)
            return line.encode() if line else b""
        except StopIteration:
            return b""

    proc.stdout = MagicMock()
    proc.stdout.readline = mock_readline
    proc.stdout.read = mock_read

    # Mock stderr
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(return_value=b"")

    # Mock wait
    proc.wait = AsyncMock(return_value=returncode)
    proc.terminate = MagicMock()
    proc.kill = MagicMock()

    # Mock communicate for oneshot
    async def mock_communicate():
        return (b"\n".join(line.encode() for line in stdout_lines), b"")

    proc.communicate = mock_communicate

    return proc


# =============================================================================
# ClaudeBridge Tests
# =============================================================================


class TestClaudeBridgeInit:
    """Tests for ClaudeBridge initialization."""

    def test_default_values(self):
        """Should have sensible defaults."""
        bridge = ClaudeBridge()
        assert bridge.executable == "claude"
        assert bridge.model == "claude-sonnet-4-5"
        assert bridge.timeout == 600
        assert bridge.state == BridgeState.DISCONNECTED
        assert bridge.debug is False

    def test_custom_values(self):
        """Should accept custom values."""
        bridge = ClaudeBridge(
            executable="/usr/bin/claude",
            model="claude-opus-4",
            timeout=60,
            permission_mode="plan",
            debug=True,
        )
        assert bridge.executable == "/usr/bin/claude"
        assert bridge.model == "claude-opus-4"
        assert bridge.timeout == 60
        assert bridge.permission_mode == "plan"
        assert bridge.debug is True

    def test_provider_name(self):
        """Should return correct provider name."""
        bridge = ClaudeBridge()
        assert bridge.provider_name == "claude"


class TestClaudeBridgeCommands:
    """Tests for ClaudeBridge command building."""

    def test_persistent_command(self):
        """Should build correct persistent command."""
        bridge = ClaudeBridge(model="claude-sonnet-4-5")
        cmd = bridge._build_persistent_command()

        assert "claude" in cmd
        assert "-p" in cmd
        assert "--input-format" in cmd
        assert "stream-json" in cmd[cmd.index("--input-format") + 1]
        assert "--output-format" in cmd
        assert "--verbose" in cmd
        assert "--model" in cmd
        assert "claude-sonnet-4-5" in cmd

    def test_oneshot_command(self):
        """Should build correct oneshot command."""
        bridge = ClaudeBridge(model="claude-sonnet-4-5")
        cmd = bridge._build_oneshot_command("Hello")

        assert "claude" in cmd
        assert "-p" in cmd
        assert "--output-format" in cmd
        assert "Hello" in cmd

    def test_command_with_allowed_tools(self):
        """Should include allowed tools via --settings flag (Zero Footprint)."""
        bridge = ClaudeBridge(allowed_tools=["Read", "Grep"])
        bridge._setup_config_files()
        cmd = bridge._build_persistent_command()

        # Zero Footprint: permissions are in --settings file, not --allowedTools
        assert "--settings" in cmd
        bridge._sandbox.cleanup()

    def test_persistent_command_with_debug(self):
        """Should include --debug flag in persistent command when debug=True."""
        bridge = ClaudeBridge(model="claude-sonnet-4-5", debug=True)
        cmd = bridge._build_persistent_command()
        assert "--debug" in cmd

    def test_persistent_command_without_debug(self):
        """Should not include --debug flag when debug=False (default)."""
        bridge = ClaudeBridge(model="claude-sonnet-4-5")
        cmd = bridge._build_persistent_command()
        assert "--debug" not in cmd

    def test_oneshot_command_with_debug(self):
        """Should include --debug flag in oneshot command when debug=True."""
        bridge = ClaudeBridge(model="claude-sonnet-4-5", debug=True)
        cmd = bridge._build_oneshot_command("Hello")
        assert "--debug" in cmd

    def test_oneshot_command_without_debug(self):
        """Should not include --debug flag in oneshot command when debug=False."""
        bridge = ClaudeBridge(model="claude-sonnet-4-5")
        cmd = bridge._build_oneshot_command("Hello")
        assert "--debug" not in cmd


class TestClaudeBridgeParsing:
    """Tests for ClaudeBridge response parsing."""

    def test_parse_assistant_message(self):
        """Should parse assistant message event."""
        bridge = ClaudeBridge()
        events = [
            {"type": "assistant", "message": {"content": "Hello!"}},
        ]
        content = bridge._parse_content(events)
        assert content == "Hello!"

    def test_parse_content_blocks(self):
        """Should parse content blocks."""
        bridge = ClaudeBridge()
        events = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "Part 1"},
                        {"type": "text", "text": "Part 2"},
                    ]
                },
            },
        ]
        content = bridge._parse_content(events)
        assert content == "Part 1Part 2"

    def test_parse_session_id(self):
        """Should extract session ID."""
        bridge = ClaudeBridge()
        events = [
            {"type": "system", "session_id": "sess-123"},
        ]
        sid = bridge._parse_session_id(events)
        assert sid == "sess-123"

    def test_parse_usage(self):
        """Should extract usage metrics."""
        bridge = ClaudeBridge()
        events = [
            {
                "type": "result",
                "total_cost_usd": 0.01,
                "duration_ms": 1500,
            },
        ]
        usage = bridge._parse_usage(events)
        assert usage["total_cost_usd"] == 0.01
        assert usage["duration_ms"] == 1500

    def test_is_turn_complete(self):
        """Should detect turn completion."""
        bridge = ClaudeBridge()
        assert bridge._is_turn_complete({"type": "result"}) is True
        assert bridge._is_turn_complete({"type": "assistant"}) is False


# =============================================================================
# GeminiBridge Tests
# =============================================================================


class TestGeminiBridgeInit:
    """Tests for GeminiBridge initialization."""

    def test_default_values(self):
        """Should have sensible defaults."""
        bridge = GeminiBridge()
        assert bridge.executable == "gemini"
        assert bridge.model == ""
        assert bridge.timeout == 600
        assert bridge.approval_mode == "yolo"
        assert bridge.state == BridgeState.DISCONNECTED
        assert bridge.debug is False

    def test_custom_values(self):
        """Should accept custom values."""
        bridge = GeminiBridge(
            model="gemini-2.0-flash",
            timeout=60,
            approval_mode="default",
            acp_enabled=False,
            debug=True,
        )
        assert bridge.model == "gemini-2.0-flash"
        assert bridge.timeout == 60
        assert bridge.approval_mode == "default"
        assert bridge.acp_enabled is False
        assert bridge.debug is True

    def test_provider_name(self):
        """Should return correct provider name."""
        bridge = GeminiBridge()
        assert bridge.provider_name == "gemini"


class TestGeminiBridgeCommands:
    """Tests for GeminiBridge command building."""

    def test_oneshot_command(self):
        """Should build correct oneshot command."""
        bridge = GeminiBridge(model="gemini-2.0-flash", approval_mode="yolo")
        cmd = bridge._build_oneshot_command("Hello")

        assert "gemini" in cmd
        assert "--model" in cmd
        assert "gemini-2.0-flash" in cmd
        assert "--yolo" in cmd
        assert "--output-format" in cmd
        assert "stream-json" in cmd[cmd.index("--output-format") + 1]

    def test_oneshot_command_without_model(self):
        """Should work without explicit model."""
        bridge = GeminiBridge(model="")
        cmd = bridge._build_oneshot_command("Hello")

        assert "gemini" in cmd
        assert "--model" not in cmd

    def test_oneshot_command_with_debug(self):
        """Should include --debug flag in oneshot command when debug=True."""
        bridge = GeminiBridge(model="gemini-2.0-flash", debug=True)
        cmd = bridge._build_oneshot_command("Hello")
        assert "--debug" in cmd

    def test_oneshot_command_without_debug(self):
        """Should not include --debug flag in oneshot command when debug=False."""
        bridge = GeminiBridge(model="gemini-2.0-flash")
        cmd = bridge._build_oneshot_command("Hello")
        assert "--debug" not in cmd

    def test_effective_prompt_with_history(self):
        """Should inject history context."""
        bridge = GeminiBridge()
        bridge.history = [
            Message(role="user", content="Hi"),
            Message(role="assistant", content="Hello!"),
        ]
        prompt = bridge._build_effective_prompt("How are you?")

        assert "[Previous conversation:]" in prompt
        assert "User: Hi" in prompt
        assert "Assistant: Hello!" in prompt
        assert "User: How are you?" in prompt


class TestGeminiBridgeParsing:
    """Tests for GeminiBridge response parsing."""

    def test_parse_assistant_message(self):
        """Should parse assistant message event."""
        bridge = GeminiBridge()
        events = [
            {"type": "message", "role": "assistant", "content": "Hello!"},
        ]
        content = bridge._parse_content(events)
        assert content == "Hello!"

    def test_parse_session_id(self):
        """Should extract session ID."""
        bridge = GeminiBridge()
        events = [
            {"type": "init", "session_id": "gemini-sess-123"},
        ]
        sid = bridge._parse_session_id(events)
        assert sid == "gemini-sess-123"

    def test_parse_usage(self):
        """Should extract token usage from stats."""
        bridge = GeminiBridge()
        events = [
            {
                "type": "result",
                "stats": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                },
            },
        ]
        usage = bridge._parse_usage(events)
        # Returns raw stats dict
        assert usage["input_tokens"] == 100
        assert usage["output_tokens"] == 50
        assert usage["total_tokens"] == 150

    def test_is_turn_complete(self):
        """Should detect turn completion."""
        bridge = GeminiBridge()
        assert bridge._is_turn_complete({"type": "result"}) is True
        assert bridge._is_turn_complete({"type": "message"}) is False


# =============================================================================
# Bridge State Tests
# =============================================================================


class TestBridgeState:
    """Tests for bridge state management."""

    def test_initial_state(self):
        """Should start disconnected."""
        bridge = ClaudeBridge()
        assert bridge.state == BridgeState.DISCONNECTED

    def test_state_change_callback(self):
        """Should call state change callback."""
        bridge = ClaudeBridge()
        states = []

        def on_state(state: BridgeState, detail: str = "") -> None:
            states.append(state)

        bridge.on_state_change(on_state)
        bridge._set_state(BridgeState.READY)
        bridge._set_state(BridgeState.BUSY)

        assert states == [BridgeState.READY, BridgeState.BUSY]


class TestBridgeHistory:
    """Tests for conversation history."""

    def test_empty_history(self):
        """Should start with empty history."""
        bridge = ClaudeBridge()
        assert bridge.get_history() == []

    def test_clear_history(self):
        """Should clear history."""
        bridge = ClaudeBridge()
        bridge.history.append(Message(role="user", content="Test"))
        assert len(bridge.history) == 1

        bridge.clear_history()
        assert len(bridge.history) == 0


class TestBridgeHealth:
    """Tests for health check functionality."""

    def test_unhealthy_when_disconnected(self):
        """Should be unhealthy when disconnected."""
        bridge = ClaudeBridge()
        assert bridge.is_healthy() is False

    def test_check_health_disconnected(self):
        """Should return health dict when disconnected."""
        bridge = ClaudeBridge()
        health = bridge.check_health()

        assert health["healthy"] is False
        assert health["state"] == "disconnected"
        assert health["provider"] == "claude"


class TestBridgeStats:
    """Tests for usage statistics."""

    def test_initial_stats(self):
        """Should have zero stats initially."""
        bridge = ClaudeBridge()
        stats = bridge.get_stats()

        assert stats["total_requests"] == 0
        assert stats["successful_requests"] == 0
        assert stats["failed_requests"] == 0

    def test_reset_stats(self):
        """Should reset stats."""
        bridge = ClaudeBridge()
        bridge._stats["total_requests"] = 10
        bridge.reset_stats()

        assert bridge._stats["total_requests"] == 0


# =============================================================================
# Integration Tests with Mocks
# =============================================================================


class TestClaudeBridgeWithMock:
    """Integration tests for ClaudeBridge with mocked subprocess."""

    @pytest.mark.asyncio
    async def test_oneshot_send(self):
        """Should send message in oneshot mode."""
        bridge = ClaudeBridge()

        # Mock response events
        stdout_lines = [
            json.dumps({"type": "system", "session_id": "test-session"}),
            json.dumps({"type": "assistant", "message": {"content": "Hello!"}}),
            json.dumps({"type": "result", "usage": {"input_tokens": 10, "output_tokens": 5}}),
        ]

        mock_proc = make_mock_process(stdout_lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/claude"):
                await bridge.start()
                response = await bridge.send("Hi")

        assert response.success is True
        assert response.content == "Hello!"
        assert response.session_id == "test-session"


class TestGeminiBridgeWithMock:
    """Integration tests for GeminiBridge with mocked subprocess."""

    @pytest.mark.asyncio
    async def test_oneshot_send(self):
        """Should send message in oneshot mode."""
        bridge = GeminiBridge(acp_enabled=False)

        # Mock response events
        stdout_lines = [
            json.dumps({"type": "init", "session_id": "gemini-test"}),
            json.dumps({"type": "message", "role": "user", "content": "Hi"}),
            json.dumps({"type": "message", "role": "assistant", "content": "Hello!"}),
            json.dumps({"type": "result", "status": "success", "stats": {"input_tokens": 10, "output_tokens": 5}}),
        ]

        mock_proc = make_mock_process(stdout_lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                await bridge.start()
                response = await bridge.send("Hi")

        assert response.success is True
        assert response.content == "Hello!"
        assert response.session_id == "gemini-test"
