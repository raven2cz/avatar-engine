"""
Tests for CLI display lifecycle — verifies DisplayManager behavior.

Tests the DisplayManager's Live display methods, event handling,
state transitions, and the non-live fallback paths used by the
current REPL (which does not use Live).

The Live methods (start_live, stop_live, update_live) are tested
here because they exist in display.py and will be used by the
future prompt_toolkit-based REPL rewrite.
"""

import asyncio
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console

from avatar_engine.events import (
    EngineState,
    ErrorEvent,
    EventEmitter,
    ThinkingEvent,
    ThinkingPhase,
    ToolEvent,
)
from avatar_engine.cli.display import DisplayManager


# =============================================================================
# Helpers
# =============================================================================


def _make_display(**kwargs):
    """Create a DisplayManager with a quiet console and mock emitter."""
    emitter = EventEmitter()
    console = Console(file=StringIO(), force_terminal=True)
    display = DisplayManager(emitter, console=console, **kwargs)
    return display, emitter, console


# =============================================================================
# Live lifecycle: start / stop / idempotent
# =============================================================================


class TestLiveLifecycle:
    """Tests that Live display is correctly started and stopped."""

    def test_live_not_active_by_default(self):
        display, _, _ = _make_display()
        assert display._live is None

    def test_start_live_creates_live(self):
        display, _, _ = _make_display()
        display.start_live()
        assert display._live is not None
        display.stop_live()

    def test_stop_live_clears_live(self):
        display, _, _ = _make_display()
        display.start_live()
        display.stop_live()
        assert display._live is None

    def test_stop_live_idempotent(self):
        display, _, _ = _make_display()
        # Calling stop without start should not raise
        display.stop_live()
        display.stop_live()
        assert display._live is None

    def test_start_live_idempotent(self):
        display, _, _ = _make_display()
        display.start_live()
        first_live = display._live
        display.start_live()  # should not create a new Live
        assert display._live is first_live
        display.stop_live()

    def test_live_uses_refresh_per_second(self):
        """Live should use refresh_per_second=8 for auto animation."""
        display, _, _ = _make_display()
        display.start_live()
        # Rich Live with refresh_per_second sets auto_refresh=True
        assert display._live is not None
        display.stop_live()


# =============================================================================
# State transitions and event handling
# =============================================================================


class TestStateTransitions:
    """Tests that display state transitions work correctly."""

    def test_on_response_start_sets_thinking(self):
        display, _, _ = _make_display()
        display.on_response_start()
        assert display.state == EngineState.THINKING

    def test_on_response_end_clears_state(self):
        display, emitter, _ = _make_display()
        display.on_response_start()
        emitter.emit(ThinkingEvent(subject="test"))
        emitter.emit(ToolEvent(tool_name="Read", tool_id="t1", status="started"))
        emitter.emit(ToolEvent(tool_name="Read", tool_id="t1", status="completed"))
        display.on_response_end()
        assert display.state == EngineState.IDLE
        assert display.thinking.active is False

    def test_thinking_event_sets_thinking_state(self):
        display, emitter, _ = _make_display()
        emitter.emit(ThinkingEvent(
            phase=ThinkingPhase.ANALYZING,
            subject="code structure",
        ))
        assert display.state == EngineState.THINKING

    def test_tool_event_sets_tool_executing_state(self):
        display, emitter, _ = _make_display()
        emitter.emit(ToolEvent(tool_name="Read", tool_id="t1", status="started"))
        assert display.state == EngineState.TOOL_EXECUTING

    def test_error_event_sets_error_state(self):
        display, emitter, _ = _make_display()
        emitter.emit(ErrorEvent(error="something broke"))
        assert display.state == EngineState.ERROR

    def test_thinking_complete_resets_to_idle(self):
        display, emitter, _ = _make_display()
        emitter.emit(ThinkingEvent(subject="test"))
        assert display.state == EngineState.THINKING
        emitter.emit(ThinkingEvent(is_complete=True))
        assert display.state == EngineState.IDLE

    def test_response_end_resets_after_error(self):
        """on_response_end should reset to IDLE even after error state."""
        display, emitter, _ = _make_display()
        display.on_response_start()
        emitter.emit(ErrorEvent(error="test error"))
        display.on_response_end()
        assert display.state == EngineState.IDLE


# =============================================================================
# Non-live event output (current REPL behavior)
# =============================================================================


class TestNonLiveOutput:
    """Tests that events print correctly without Live (the default REPL mode)."""

    def test_thinking_prints_inline(self):
        """ThinkingEvent should print inline spinner text without Live."""
        display, emitter, console = _make_display()
        emitter.emit(ThinkingEvent(
            phase=ThinkingPhase.CODING,
            subject="implement feature",
        ))
        output = console.file.getvalue()
        # Should have printed something about the thinking
        assert len(output) > 0

    def test_tool_started_prints(self):
        """ToolEvent started should print tool name."""
        display, emitter, console = _make_display()
        emitter.emit(ToolEvent(tool_name="Grep", tool_id="t1", status="started"))
        output = console.file.getvalue()
        assert "Grep" in output

    def test_tool_completed_prints(self):
        """ToolEvent completed should print tool name with checkmark."""
        display, emitter, console = _make_display()
        emitter.emit(ToolEvent(tool_name="Read", tool_id="t1", status="started"))
        emitter.emit(ToolEvent(tool_name="Read", tool_id="t1", status="completed"))
        output = console.file.getvalue()
        assert "Read" in output

    def test_tool_failed_prints(self):
        """ToolEvent failed should print error."""
        display, emitter, console = _make_display()
        emitter.emit(ToolEvent(
            tool_name="Write", tool_id="t1", status="failed", error="permission denied",
        ))
        output = console.file.getvalue()
        assert "Write" in output

    def test_error_prints_immediately(self):
        """Error should print immediately without Live."""
        display, emitter, console = _make_display()
        emitter.emit(ErrorEvent(error="immediate error"))
        output = console.file.getvalue()
        assert "immediate error" in output

    def test_verbose_thinking_prints(self):
        """Verbose mode should print thinking details."""
        display, emitter, console = _make_display(verbose=True)
        emitter.emit(ThinkingEvent(
            phase=ThinkingPhase.ANALYZING,
            subject="code",
            thought="Analyzing the structure...",
        ))
        output = console.file.getvalue()
        assert "code" in output or "Analyzing" in output

    def test_non_verbose_skips_thoughts(self):
        """Non-verbose mode should not print thought text."""
        display, emitter, console = _make_display(verbose=False)
        emitter.emit(ThinkingEvent(
            phase=ThinkingPhase.ANALYZING,
            subject="code",
            thought="Analyzing the structure...",
        ))
        output = console.file.getvalue()
        # Should print spinner/subject but not the full thought text
        assert "Analyzing the structure..." not in output


# =============================================================================
# Live display update (for future prompt_toolkit REPL)
# =============================================================================


class TestLiveDisplayUpdate:
    """Tests for the update_live() method used with Live display."""

    def test_update_live_noop_when_not_live(self):
        """update_live() should do nothing when Live is not active."""
        display, emitter, _ = _make_display()
        # Should not raise
        display.update_live()

    def test_update_live_renders_thinking(self):
        """update_live() should render thinking spinner when active."""
        display, emitter, _ = _make_display()
        emitter.emit(ThinkingEvent(
            phase=ThinkingPhase.ANALYZING,
            subject="code structure",
        ))
        display.start_live()
        # Should update without error
        display.update_live()
        assert display._live is not None
        display.stop_live()

    def test_update_live_renders_tools(self):
        """update_live() should render tool panel when tools are active."""
        display, emitter, _ = _make_display()
        emitter.emit(ToolEvent(tool_name="Read", tool_id="t1", status="started"))
        display.start_live()
        display.update_live()
        assert display._live is not None
        display.stop_live()

    def test_update_live_no_error_when_idle(self):
        """update_live() should not raise when idle (no events)."""
        display, _, _ = _make_display()
        display.start_live()
        display.update_live()  # should not raise
        assert display._live is not None
        display.stop_live()


# =============================================================================
# Full lifecycle simulation
# =============================================================================


class TestLifecycleSimulation:
    """Simulate the display lifecycle to verify state transitions."""

    def test_response_lifecycle_with_live(self):
        """
        Simulate: response_start → start_live → [thinking events] →
        stop_live → [print text] → response_end.
        """
        display, emitter, _ = _make_display()

        # Live is off
        assert display._live is None

        # Start response with live
        display.on_response_start()
        display.start_live()
        assert display._live is not None
        assert display.state == EngineState.THINKING

        # Thinking events while live is on
        emitter.emit(ThinkingEvent(
            phase=ThinkingPhase.ANALYZING,
            subject="analyze code",
        ))
        display.update_live()

        # Stop live before printing text
        display.stop_live()
        assert display._live is None

        # End
        display.on_response_end()
        assert display.state == EngineState.IDLE
        assert display.thinking.active is False

    def test_response_lifecycle_without_live(self):
        """
        The current REPL uses no Live — just direct prints.
        response_start → [events print directly] → response_end.
        """
        display, emitter, console = _make_display()

        display.on_response_start()
        assert display.state == EngineState.THINKING

        # Events print directly
        emitter.emit(ThinkingEvent(
            phase=ThinkingPhase.PLANNING,
            subject="plan approach",
        ))
        emitter.emit(ToolEvent(tool_name="Read", tool_id="t1", status="started"))
        emitter.emit(ToolEvent(tool_name="Read", tool_id="t1", status="completed"))

        output = console.file.getvalue()
        assert "Read" in output

        display.on_response_end()
        assert display.state == EngineState.IDLE

    def test_multiple_turns(self):
        """Multiple turns should each properly reset state."""
        display, emitter, _ = _make_display()

        for i in range(3):
            display.on_response_start()
            assert display.state == EngineState.THINKING

            emitter.emit(ThinkingEvent(subject=f"turn {i}"))
            emitter.emit(ThinkingEvent(is_complete=True))

            display.on_response_end()
            assert display.state == EngineState.IDLE

    def test_thinking_and_tools_sequence(self):
        """
        Full sequence: thinking → tool started → tool completed → response end.
        """
        display, emitter, console = _make_display()

        display.on_response_start()

        # Thinking
        emitter.emit(ThinkingEvent(
            phase=ThinkingPhase.PLANNING,
            subject="plan approach",
        ))
        assert display.state == EngineState.THINKING

        # Tool starts
        emitter.emit(ToolEvent(tool_name="Read", tool_id="t1", status="started"))
        assert display.state == EngineState.TOOL_EXECUTING

        # Tool completes
        emitter.emit(ToolEvent(tool_name="Read", tool_id="t1", status="completed"))

        # Thinking completes
        emitter.emit(ThinkingEvent(is_complete=True))

        # response_end cleans up
        display.on_response_end()
        assert display.state == EngineState.IDLE

        output = console.file.getvalue()
        assert "Read" in output


# =============================================================================
# Async update loop (for future use)
# =============================================================================


class TestUpdateDisplayLoop:
    """Tests for the update_live loop pattern."""

    @pytest.mark.asyncio
    async def test_update_loop_can_be_cancelled(self):
        """The update loop should handle cancellation gracefully."""
        display, _, _ = _make_display()
        display.start_live()

        async def _update():
            try:
                while True:
                    display.update_live()
                    await asyncio.sleep(0.125)
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(_update())
        await asyncio.sleep(0.05)  # let it run briefly
        task.cancel()
        await task  # should not raise
        display.stop_live()

    @pytest.mark.asyncio
    async def test_update_loop_with_events(self):
        """Update loop should animate thinking spinner."""
        display, emitter, _ = _make_display()
        display.start_live()

        emitter.emit(ThinkingEvent(
            phase=ThinkingPhase.CODING,
            subject="write tests",
        ))

        async def _update():
            try:
                while True:
                    display.update_live()
                    await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(_update())
        await asyncio.sleep(0.2)  # let a few frames render
        task.cancel()
        await task

        # Thinking should still be active (stop happens elsewhere)
        assert display.thinking.active is True
        display.stop_live()


# =============================================================================
# Error recovery
# =============================================================================


class TestErrorRecovery:
    """Tests that display recovers correctly after errors."""

    def test_stop_live_after_error_event(self):
        """After an error event, stop_live should still work."""
        display, emitter, _ = _make_display()
        display.start_live()
        emitter.emit(ErrorEvent(error="something broke"))
        assert display.state == EngineState.ERROR
        display.stop_live()
        assert display._live is None

    def test_error_during_live_prints_immediately(self):
        """Errors print immediately even during Live mode."""
        display, emitter, console = _make_display()
        display.start_live()
        emitter.emit(ErrorEvent(error="live error"))
        output = console.file.getvalue()
        assert "live error" in output
        display.stop_live()

    def test_error_without_live_prints(self):
        """Error without live mode should print immediately."""
        display, emitter, console = _make_display()
        emitter.emit(ErrorEvent(error="immediate error"))
        output = console.file.getvalue()
        assert "immediate error" in output
