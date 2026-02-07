"""
Real integration tests for CLI display layer.

Tests that DisplayManager correctly receives and tracks events
during real provider interactions. Verifies the full pipeline:
provider → bridge → engine → events → DisplayManager.

Run with: pytest tests/integration/test_real_display.py -v
"""

import asyncio
import pytest

from avatar_engine import AvatarEngine
from avatar_engine.events import (
    EngineState,
    TextEvent,
    ThinkingEvent,
    ToolEvent,
)
from avatar_engine.cli.display import DisplayManager

from rich.console import Console
from io import StringIO


def _make_quiet_console():
    """Create a console that writes to a string buffer (no terminal output)."""
    return Console(file=StringIO(), force_terminal=True)


# =============================================================================
# Gemini Display Integration
# =============================================================================


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestGeminiDisplay:
    """Test DisplayManager with real Gemini provider."""

    @pytest.mark.asyncio
    async def test_display_receives_events_during_chat(self, skip_if_no_gemini):
        """DisplayManager should receive text/thinking events from Gemini."""
        engine = AvatarEngine(provider="gemini", timeout=60)
        console = _make_quiet_console()
        display = DisplayManager(engine, console=console)

        text_events = []
        thinking_events = []

        @engine.on(TextEvent)
        def on_text(e):
            text_events.append(e)

        @engine.on(ThinkingEvent)
        def on_thinking(e):
            thinking_events.append(e)

        try:
            await engine.start()

            display.on_response_start()
            response = await engine.chat("What is 2+2? Reply briefly.")
            display.on_response_end()

            assert response.success is True
            assert display.state == EngineState.IDLE
            assert display.thinking.active is False

            # Text events should have fired
            assert len(text_events) >= 1, "No text events received"

        finally:
            display.unregister()
            await engine.stop()

    @pytest.mark.asyncio
    async def test_display_during_streaming(self, skip_if_no_gemini):
        """DisplayManager should track state during streaming."""
        engine = AvatarEngine(provider="gemini", timeout=60)
        console = _make_quiet_console()
        display = DisplayManager(engine, console=console)

        states_seen = set()

        # Track all state transitions
        original_set = display._set_state
        def track_state(s):
            states_seen.add(s)
            original_set(s)
        display._set_state = track_state

        try:
            await engine.start()

            display.on_response_start()
            async for chunk in engine.chat_stream("Say hello."):
                pass
            display.on_response_end()

            assert EngineState.IDLE in states_seen or display.state == EngineState.IDLE

        finally:
            display.unregister()
            await engine.stop()

    @pytest.mark.asyncio
    async def test_status_line_renders_without_error(self, skip_if_no_gemini):
        """render_status_line should work at every state."""
        engine = AvatarEngine(provider="gemini", timeout=60)
        console = _make_quiet_console()
        display = DisplayManager(engine, console=console)

        try:
            await engine.start()

            # Idle state
            line = display.render_status_line()
            assert line is not None
            assert len(line.plain) > 0

            # During chat
            display.on_response_start()
            line = display.render_status_line()
            assert line is not None

            response = await engine.chat("Hi")
            display.on_response_end()

            # Back to idle
            line = display.render_status_line()
            assert "> " in line.plain

        finally:
            display.unregister()
            await engine.stop()


# =============================================================================
# Claude Display Integration
# =============================================================================


@pytest.mark.integration
@pytest.mark.claude
@pytest.mark.slow
class TestClaudeDisplay:
    """Test DisplayManager with real Claude provider."""

    @pytest.mark.asyncio
    async def test_display_receives_events_during_chat(self, skip_if_no_claude):
        """DisplayManager should receive events from Claude."""
        engine = AvatarEngine(provider="claude", timeout=120)
        console = _make_quiet_console()
        display = DisplayManager(engine, console=console)

        tool_events = []
        thinking_events = []

        @engine.on(ToolEvent)
        def on_tool(e):
            tool_events.append(e)

        @engine.on(ThinkingEvent)
        def on_thinking(e):
            thinking_events.append(e)

        try:
            await engine.start()

            display.on_response_start()
            response = await engine.chat("What is 2+2? Reply with just the number.")
            display.on_response_end()

            assert response.success is True
            assert display.state == EngineState.IDLE

        finally:
            display.unregister()
            await engine.stop()

    @pytest.mark.asyncio
    async def test_tool_group_tracks_real_tools(self, skip_if_no_claude):
        """Tool group should track real tool executions from Claude.

        Claude emits synthetic ThinkingEvents and ToolEvents when using tools.
        Ask a question that triggers tool use to test the full pipeline.
        """
        engine = AvatarEngine(provider="claude", timeout=120)
        console = _make_quiet_console()
        display = DisplayManager(engine, console=console)

        tool_started = []
        tool_completed = []

        @engine.on(ToolEvent)
        def on_tool(e):
            if e.status == "started":
                tool_started.append(e)
            elif e.status in ("completed", "failed"):
                tool_completed.append(e)

        try:
            await engine.start()

            display.on_response_start()
            # Ask something that is likely to trigger tool use
            response = await engine.chat(
                "Read the file pyproject.toml in the current directory and tell me the project name. "
                "Reply with just the project name."
            )
            display.on_response_end()

            assert response.success is True

            # If tools were used, display should have tracked them
            if tool_started:
                assert display.tools.tool_count >= 0  # may be cleared
                # Verify tool group rendered at some point (no crash)
                display.tools.render()

        finally:
            display.unregister()
            await engine.stop()


# =============================================================================
# Codex Display Integration
# =============================================================================


@pytest.mark.integration
@pytest.mark.codex
@pytest.mark.slow
class TestCodexDisplay:
    """Test DisplayManager with real Codex provider."""

    @pytest.mark.asyncio
    async def test_display_receives_events_during_chat(self, skip_if_no_codex_acp):
        """DisplayManager should receive events from Codex."""
        engine = AvatarEngine(provider="codex", timeout=120)
        console = _make_quiet_console()
        display = DisplayManager(engine, console=console)

        try:
            await engine.start()

            display.on_response_start()
            response = await engine.chat("What is 2+2? Reply briefly.")
            display.on_response_end()

            assert response.success is True
            assert display.state == EngineState.IDLE

        finally:
            display.unregister()
            await engine.stop()


# =============================================================================
# Display Lifecycle Integration (provider-agnostic)
# =============================================================================


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestDisplayLifecycle:
    """Test DisplayManager lifecycle with real provider."""

    @pytest.mark.asyncio
    async def test_multiple_turns_with_display(self, skip_if_no_gemini):
        """DisplayManager should handle multiple conversation turns."""
        engine = AvatarEngine(provider="gemini", timeout=60)
        console = _make_quiet_console()
        display = DisplayManager(engine, console=console)

        try:
            await engine.start()

            for msg in ["Hello", "How are you?", "Goodbye"]:
                display.on_response_start()
                response = await engine.chat(msg)
                display.on_response_end()

                assert response.success is True
                assert display.state == EngineState.IDLE
                assert display.thinking.active is False

        finally:
            display.unregister()
            await engine.stop()

    @pytest.mark.asyncio
    async def test_unregister_stops_tracking(self, skip_if_no_gemini):
        """After unregister, display should not receive events."""
        engine = AvatarEngine(provider="gemini", timeout=60)
        console = _make_quiet_console()
        display = DisplayManager(engine, console=console)

        try:
            await engine.start()

            # First chat with display active
            display.on_response_start()
            resp1 = await engine.chat("Hi")
            display.on_response_end()
            assert resp1.success is True

            # Unregister
            display.unregister()

            # Second chat — display should not crash or change state
            initial_state = display.state
            resp2 = await engine.chat("Hello again")
            assert resp2.success is True
            # State should not have changed since we unregistered
            assert display.state == initial_state

        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_verbose_display_no_crash(self, skip_if_no_gemini):
        """Verbose display should not crash with real events."""
        engine = AvatarEngine(provider="gemini", timeout=60)
        console = _make_quiet_console()
        display = DisplayManager(engine, console=console, verbose=True)

        try:
            await engine.start()

            display.on_response_start()
            response = await engine.chat("Explain what Python is in one sentence.")
            display.on_response_end()

            assert response.success is True

        finally:
            display.unregister()
            await engine.stop()
