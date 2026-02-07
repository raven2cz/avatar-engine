"""
Real integration tests for REPL display lifecycle.

Tests the full pipeline with real providers to ensure the display
event handling doesn't break actual provider communication.

The current REPL uses no Live — events print directly via console.
These tests verify that the display lifecycle (on_response_start,
events, on_response_end) works correctly with real streaming.

Run with: pytest tests/integration/test_real_repl_display.py -v
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
# Display lifecycle with real streaming (no Live)
# =============================================================================


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestReplDisplayLifecycleGemini:
    """Test REPL display lifecycle with real Gemini streaming."""

    @pytest.mark.asyncio
    async def test_stream_with_display_events(self, skip_if_no_gemini):
        """
        Simulate the REPL flow without Live:
        on_response_start → stream text → on_response_end.
        Display events fire correctly alongside streaming.
        """
        engine = AvatarEngine(provider="gemini", timeout=60)
        console = _make_quiet_console()
        display = DisplayManager(engine, console=console)

        try:
            await engine.start()

            display.on_response_start()
            assert display.state == EngineState.THINKING

            chunks = []
            async for chunk in engine.chat_stream("What is 2+2? Reply briefly."):
                chunks.append(chunk)

            display.on_response_end()

            # Assertions
            assert display.state == EngineState.IDLE
            assert len(chunks) > 0, "Should have received text chunks"
            full_text = "".join(chunks)
            assert len(full_text) > 0, "Response should not be empty"

        finally:
            display.unregister()
            await engine.stop()

    @pytest.mark.asyncio
    async def test_multiple_turns_display_lifecycle(self, skip_if_no_gemini):
        """Multiple turns should each properly start/end display."""
        engine = AvatarEngine(provider="gemini", timeout=60)
        console = _make_quiet_console()
        display = DisplayManager(engine, console=console)

        try:
            await engine.start()

            for msg in ["Say hello.", "Say goodbye."]:
                assert display.state == EngineState.IDLE

                display.on_response_start()
                assert display.state == EngineState.THINKING

                async for chunk in engine.chat_stream(msg):
                    pass  # consume stream

                display.on_response_end()
                assert display.state == EngineState.IDLE

        finally:
            display.unregister()
            await engine.stop()


@pytest.mark.integration
@pytest.mark.claude
@pytest.mark.slow
class TestReplDisplayLifecycleClaude:
    """Test REPL display lifecycle with real Claude streaming."""

    @pytest.mark.asyncio
    async def test_stream_with_display_events(self, skip_if_no_claude):
        """
        Claude streaming with display lifecycle: events fire,
        text chunks arrive, state transitions work.
        """
        engine = AvatarEngine(provider="claude", timeout=120)
        console = _make_quiet_console()
        display = DisplayManager(engine, console=console)

        try:
            await engine.start()

            display.on_response_start()
            assert display.state == EngineState.THINKING

            chunks = []
            async for chunk in engine.chat_stream("What is 2+2? Reply with just the number."):
                chunks.append(chunk)

            display.on_response_end()

            assert display.state == EngineState.IDLE
            assert len(chunks) > 0

        finally:
            display.unregister()
            await engine.stop()


# =============================================================================
# Display output verification
# =============================================================================


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestDisplayOutputVerification:
    """Verify that display output is clean and complete."""

    @pytest.mark.asyncio
    async def test_response_text_captured_fully(self, skip_if_no_gemini):
        """
        All text chunks from stream should be captured — nothing lost
        by the display event handling.
        """
        engine = AvatarEngine(provider="gemini", timeout=60)
        console = _make_quiet_console()
        display = DisplayManager(engine, console=console)

        try:
            await engine.start()

            # Also get the non-streaming response for comparison
            non_stream = await engine.chat("What is the capital of France? Reply with just the city name.")

            # Now stream the same question
            display.on_response_start()

            stream_chunks = []
            async for chunk in engine.chat_stream("What is the capital of France? Reply with just the city name."):
                stream_chunks.append(chunk)

            display.on_response_end()

            stream_text = "".join(stream_chunks)
            # Both should mention Paris
            assert "Paris" in non_stream.content or "paris" in non_stream.content.lower()
            assert "Paris" in stream_text or "paris" in stream_text.lower()

        finally:
            display.unregister()
            await engine.stop()
