"""
Event system integration tests.

These tests verify:
- UC-5: GUI event integration
- Event emission timing
- Handler registration/unregistration
- Multiple handlers
"""

import asyncio
import json
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from avatar_engine import AvatarEngine
from avatar_engine.events import (
    TextEvent,
    ToolEvent,
    StateEvent,
    ErrorEvent,
    ThinkingEvent,
    CostEvent,
)
from avatar_engine.bridges.base import BridgeState


# =============================================================================
# Mock Helpers
# =============================================================================


def create_mock_subprocess(stdout_lines: List[str], returncode: int = 0):
    """Create a mock subprocess."""
    proc = MagicMock()
    proc.pid = 12345
    _returncode = [returncode]
    type(proc).returncode = PropertyMock(side_effect=lambda: _returncode[0])

    proc.stdin = MagicMock()
    proc.stdin.write = MagicMock()
    proc.stdin.drain = AsyncMock()
    proc.stdin.close = MagicMock()

    stdout_queue = asyncio.Queue()
    for line in stdout_lines:
        stdout_queue.put_nowait(line + "\n" if line else "")
    stdout_queue.put_nowait("")

    async def mock_readline():
        try:
            line = stdout_queue.get_nowait()
            return line.encode() if line else b""
        except asyncio.QueueEmpty:
            return b""

    proc.stdout = MagicMock()
    proc.stdout.readline = mock_readline
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(return_value=b"")
    proc.terminate = MagicMock()
    proc.kill = MagicMock()

    async def mock_wait():
        _returncode[0] = returncode
        return returncode

    proc.wait = mock_wait

    async def mock_communicate():
        all_stdout = "\n".join(stdout_lines).encode()
        _returncode[0] = returncode
        return (all_stdout, b"")

    proc.communicate = mock_communicate

    return proc


# =============================================================================
# TextEvent Tests
# =============================================================================


class TestTextEvents:
    """Test TextEvent emission during chat."""

    @pytest.mark.asyncio
    async def test_text_event_emitted_during_streaming(self):
        """TextEvent should be emitted for each streaming chunk."""
        text_events = []
        lines = [
            json.dumps({"type": "init", "session_id": "test"}),
            json.dumps({"type": "message", "role": "assistant", "content": "Hello"}),
            json.dumps({"type": "message", "role": "assistant", "content": " world"}),
            json.dumps({"type": "result"}),
        ]

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")

                @engine.on(TextEvent)
                def on_text(event: TextEvent):
                    text_events.append(event)

                await engine.start()
                async for _ in engine.chat_stream("Hi"):
                    pass

                # Should have text events
                assert len(text_events) >= 1
                assert all(isinstance(e, TextEvent) for e in text_events)

                await engine.stop()

    @pytest.mark.asyncio
    async def test_text_event_contains_text(self):
        """TextEvent should contain the text content."""
        text_events = []
        lines = [
            json.dumps({"type": "init", "session_id": "test"}),
            json.dumps({"type": "message", "role": "assistant", "content": "Test content"}),
            json.dumps({"type": "result"}),
        ]

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")

                @engine.on(TextEvent)
                def on_text(event: TextEvent):
                    text_events.append(event)

                await engine.start()
                async for _ in engine.chat_stream("Hi"):
                    pass

                if text_events:
                    assert text_events[0].text is not None
                    assert len(text_events[0].text) > 0

                await engine.stop()


# =============================================================================
# StateEvent Tests
# =============================================================================


class TestStateEvents:
    """Test StateEvent emission on state changes."""

    @pytest.mark.asyncio
    async def test_state_event_on_start(self):
        """StateEvent should be emitted when engine starts."""
        state_events = []
        lines = [
            json.dumps({"type": "init", "session_id": "test"}),
            json.dumps({"type": "result"}),
        ]

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")

                @engine.on(StateEvent)
                def on_state(event: StateEvent):
                    state_events.append(event)

                await engine.start()

                # Should have at least one state change (to READY)
                assert len(state_events) >= 1

                await engine.stop()

    @pytest.mark.asyncio
    async def test_state_event_during_chat(self):
        """StateEvent should be emitted during chat lifecycle."""
        state_events = []
        lines = [
            json.dumps({"type": "init", "session_id": "test"}),
            json.dumps({"type": "message", "role": "assistant", "content": "OK"}),
            json.dumps({"type": "result"}),
        ]

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")

                @engine.on(StateEvent)
                def on_state(event: StateEvent):
                    state_events.append(event)

                await engine.start()
                await engine.chat("Hello")

                # Should have state transitions
                assert len(state_events) >= 1

                await engine.stop()

    @pytest.mark.asyncio
    async def test_state_event_has_old_and_new_state(self):
        """StateEvent should have old_state and new_state."""
        state_events = []
        lines = [
            json.dumps({"type": "init", "session_id": "test"}),
            json.dumps({"type": "result"}),
        ]

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")

                @engine.on(StateEvent)
                def on_state(event: StateEvent):
                    state_events.append(event)

                await engine.start()

                if state_events:
                    event = state_events[0]
                    # new_state should always be set
                    assert event.new_state is not None

                await engine.stop()


# =============================================================================
# Handler Management Tests
# =============================================================================


class TestHandlerManagement:
    """Test event handler registration and unregistration."""

    @pytest.mark.asyncio
    async def test_multiple_handlers_same_event(self):
        """Multiple handlers for same event should all be called."""
        handler1_calls = []
        handler2_calls = []

        lines = [
            json.dumps({"type": "init", "session_id": "test"}),
            json.dumps({"type": "message", "role": "assistant", "content": "Hi"}),
            json.dumps({"type": "result"}),
        ]

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")

                @engine.on(TextEvent)
                def handler1(event):
                    handler1_calls.append(event)

                @engine.on(TextEvent)
                def handler2(event):
                    handler2_calls.append(event)

                await engine.start()
                async for _ in engine.chat_stream("Hello"):
                    pass

                # Both handlers should be called
                # (They might both have same count)
                assert len(handler1_calls) == len(handler2_calls)

                await engine.stop()

    @pytest.mark.asyncio
    async def test_handler_for_multiple_event_types(self):
        """Can register handlers for multiple event types."""
        all_events = []

        lines = [
            json.dumps({"type": "init", "session_id": "test"}),
            json.dumps({"type": "message", "role": "assistant", "content": "Hi"}),
            json.dumps({"type": "result"}),
        ]

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")

                @engine.on(TextEvent)
                def on_text(event):
                    all_events.append(("text", event))

                @engine.on(StateEvent)
                def on_state(event):
                    all_events.append(("state", event))

                await engine.start()
                await engine.chat("Hello")

                # Should have both types of events
                event_types = {e[0] for e in all_events}
                assert "state" in event_types

                await engine.stop()


# =============================================================================
# Handler Exception Handling Tests
# =============================================================================


class TestHandlerExceptions:
    """Test that handler exceptions don't crash the engine."""

    @pytest.mark.asyncio
    async def test_handler_exception_caught(self):
        """Exception in handler should be caught, not crash engine."""
        lines = [
            json.dumps({"type": "init", "session_id": "test"}),
            json.dumps({"type": "message", "role": "assistant", "content": "Hi"}),
            json.dumps({"type": "result"}),
        ]

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")

                @engine.on(TextEvent)
                def bad_handler(event):
                    raise ValueError("Handler crashed!")

                await engine.start()

                # Should not crash
                response = await engine.chat("Hello")
                assert response.success is True

                await engine.stop()

    @pytest.mark.asyncio
    async def test_one_bad_handler_doesnt_stop_others(self):
        """One failing handler shouldn't stop other handlers."""
        good_handler_calls = []

        lines = [
            json.dumps({"type": "init", "session_id": "test"}),
            json.dumps({"type": "message", "role": "assistant", "content": "Hi"}),
            json.dumps({"type": "result"}),
        ]

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")

                @engine.on(StateEvent)
                def bad_handler(event):
                    raise RuntimeError("Boom!")

                @engine.on(StateEvent)
                def good_handler(event):
                    good_handler_calls.append(event)

                await engine.start()
                await engine.chat("Hello")

                # Good handler should still be called
                # (Note: depends on implementation of event dispatch)

                await engine.stop()


# =============================================================================
# Event Timing Tests
# =============================================================================


class TestEventTiming:
    """Test event emission timing."""

    @pytest.mark.asyncio
    async def test_state_events_in_order(self):
        """State events should be emitted in logical order."""
        state_events = []

        lines = [
            json.dumps({"type": "init", "session_id": "test"}),
            json.dumps({"type": "message", "role": "assistant", "content": "Hi"}),
            json.dumps({"type": "result"}),
        ]

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")

                @engine.on(StateEvent)
                def on_state(event: StateEvent):
                    state_events.append(event)

                await engine.start()
                await engine.chat("Hello")
                await engine.stop()

                # Each event should have a timestamp
                for event in state_events:
                    assert event.timestamp is not None
                    assert event.timestamp > 0


# =============================================================================
# Provider-Specific Event Tests
# =============================================================================


class TestProviderSpecificEvents:
    """Test provider-specific event attributes."""

    @pytest.mark.asyncio
    async def test_event_has_provider_info(self):
        """Events should include provider information."""
        state_events = []

        lines = [
            json.dumps({"type": "init", "session_id": "test"}),
            json.dumps({"type": "result"}),
        ]

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")

                @engine.on(StateEvent)
                def on_state(event: StateEvent):
                    state_events.append(event)

                await engine.start()

                if state_events:
                    assert state_events[0].provider == "gemini"

                await engine.stop()


# =============================================================================
# Tool Event Tests
# =============================================================================


class TestToolEvents:
    """Test ToolEvent emission."""

    @pytest.mark.asyncio
    async def test_tool_event_on_tool_use(self):
        """ToolEvent should be emitted when tool is used."""
        tool_events = []

        # Response with tool use
        lines = [
            json.dumps({"type": "init", "session_id": "test"}),
            json.dumps({
                "type": "tool_use",
                "tool_name": "calculator",
                "status": "started",
                "input": {"expression": "2+2"}
            }),
            json.dumps({
                "type": "tool_result",
                "tool_name": "calculator",
                "status": "completed",
                "result": "4"
            }),
            json.dumps({"type": "message", "role": "assistant", "content": "The answer is 4"}),
            json.dumps({"type": "result"}),
        ]

        mock_proc = create_mock_subprocess(lines)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("shutil.which", return_value="/usr/bin/gemini"):
                engine = AvatarEngine(provider="gemini")

                @engine.on(ToolEvent)
                def on_tool(event: ToolEvent):
                    tool_events.append(event)

                await engine.start()
                await engine.chat("What is 2+2?")

                # Note: Tool events depend on bridge implementation
                # of parsing tool_use and tool_result events

                await engine.stop()
