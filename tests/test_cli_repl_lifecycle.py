"""Tests for REPL display lifecycle with transient spinner status."""

import asyncio
from io import StringIO

import pytest
from rich.console import Console

from avatar_engine.cli.display import DisplayManager
from avatar_engine.events import EngineState, ErrorEvent, EventEmitter, ThinkingEvent, ToolEvent


def _make_display(**kwargs):
    emitter = EventEmitter()
    console = Console(file=StringIO(), force_terminal=True)
    display = DisplayManager(emitter, console=console, **kwargs)
    return display, emitter, console


class TestSpinnerStatus:
    def test_status_inactive_by_default(self):
        display, _, _ = _make_display()
        assert display.has_active_status is False

    def test_advance_spinner_writes_status_line(self):
        display, emitter, console = _make_display()
        emitter.emit(ThinkingEvent(subject="analyzing"))
        display.advance_spinner()
        output = console.file.getvalue()
        assert "analyzing" in output
        assert "\r" in output
        assert display.has_active_status is True

    def test_clear_status_resets_status_flag(self):
        display, emitter, _ = _make_display()
        emitter.emit(ThinkingEvent(subject="analyzing"))
        display.advance_spinner()
        assert display.has_active_status is True
        display.clear_status()
        assert display.has_active_status is False

    def test_tool_event_clears_spinner_and_prints_permanent_line(self):
        display, emitter, console = _make_display()
        emitter.emit(ThinkingEvent(subject="analyzing"))
        display.advance_spinner()
        emitter.emit(ToolEvent(tool_name="Read", tool_id="t1", status="started"))
        assert display.has_active_status is False
        output = console.file.getvalue()
        assert "Read" in output

    def test_error_clears_spinner_and_sets_error_state(self):
        display, emitter, _ = _make_display()
        emitter.emit(ThinkingEvent(subject="analyzing"))
        display.advance_spinner()
        emitter.emit(ErrorEvent(error="boom"))
        assert display.has_active_status is False
        assert display.state == EngineState.ERROR


    def test_advance_spinner_fallback_when_no_thinking_event(self):
        """Spinner should show 'Thinking...' even without ThinkingEvent."""
        display, _, console = _make_display()
        display.on_response_start()  # sets state to THINKING
        # No ThinkingEvent emitted — Codex/Claude scenario
        display.advance_spinner()
        output = console.file.getvalue()
        assert "Thinking" in output
        assert display.has_active_status is True


class TestResponseLifecycle:
    def test_response_start_end_resets_state(self):
        display, emitter, _ = _make_display()
        display.on_response_start()
        assert display.state == EngineState.THINKING
        emitter.emit(ThinkingEvent(subject="work"))
        display.advance_spinner()
        display.on_response_end()
        assert display.state == EngineState.IDLE
        assert display.has_active_status is False
        assert display.thinking.active is False

    @pytest.mark.asyncio
    async def test_async_spinner_loop_can_be_cancelled(self):
        display, emitter, _ = _make_display()
        emitter.emit(ThinkingEvent(subject="loop"))

        async def _loop():
            while True:
                display.advance_spinner()
                await asyncio.sleep(0.01)

        task = asyncio.create_task(_loop())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        display.clear_status()
        assert display.has_active_status is False
