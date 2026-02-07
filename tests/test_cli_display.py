"""Tests for avatar_engine.cli.display module — CLI display layer."""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from avatar_engine.events import (
    ActivityEvent,
    ActivityStatus,
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
from avatar_engine.cli.display import (
    DisplayManager,
    ThinkingDisplay,
    ToolGroupDisplay,
    PHASE_LABELS,
    PHASE_STYLES,
    STATUS_ICONS,
    _summarize_params,
    _ToolEntry,
)


# =============================================================================
# EngineState enum
# =============================================================================


class TestEngineState:
    """Tests for EngineState enum values."""

    def test_all_states_exist(self):
        assert EngineState.IDLE.value == "idle"
        assert EngineState.THINKING.value == "thinking"
        assert EngineState.RESPONDING.value == "responding"
        assert EngineState.TOOL_EXECUTING.value == "tool_executing"
        assert EngineState.WAITING_APPROVAL.value == "waiting_approval"
        assert EngineState.ERROR.value == "error"

    def test_state_count(self):
        assert len(EngineState) == 6


# =============================================================================
# ThinkingDisplay
# =============================================================================


class TestThinkingDisplay:
    """Tests for ThinkingDisplay component."""

    def test_inactive_by_default(self):
        td = ThinkingDisplay()
        assert td.active is False
        assert td.render() is None

    def test_start_activates(self):
        td = ThinkingDisplay()
        event = ThinkingEvent(
            phase=ThinkingPhase.ANALYZING,
            subject="code structure",
        )
        td.start(event)
        assert td.active is True

    def test_stop_deactivates(self):
        td = ThinkingDisplay()
        td.start(ThinkingEvent(subject="test"))
        td.stop()
        assert td.active is False
        assert td.render() is None

    def test_render_contains_subject(self):
        td = ThinkingDisplay()
        td.start(ThinkingEvent(
            phase=ThinkingPhase.CODING,
            subject="implement function",
        ))
        rendered = td.render()
        assert rendered is not None
        assert "implement function" in rendered.plain

    def test_render_contains_elapsed_time(self):
        td = ThinkingDisplay()
        td.start(ThinkingEvent(subject="test"))
        rendered = td.render()
        assert rendered is not None
        assert "s)" in rendered.plain  # "(Xs)" pattern

    def test_render_without_subject_shows_phase_label(self):
        td = ThinkingDisplay()
        td.start(ThinkingEvent(phase=ThinkingPhase.PLANNING))
        rendered = td.render()
        assert rendered is not None
        # Should show phase label when no subject
        assert "Planning" in rendered.plain or "planning" in rendered.plain.lower()

    def test_phase_update_on_new_event(self):
        td = ThinkingDisplay()
        td.start(ThinkingEvent(phase=ThinkingPhase.ANALYZING, subject="first"))
        td.start(ThinkingEvent(phase=ThinkingPhase.CODING, subject="second"))
        rendered = td.render()
        assert "second" in rendered.plain

    def test_render_verbose(self):
        td = ThinkingDisplay()
        td.start(ThinkingEvent(
            phase=ThinkingPhase.ANALYZING,
            subject="imports",
        ))
        rendered = td.render_verbose("Looking at the import structure")
        assert rendered is not None
        plain = rendered.plain
        assert "imports" in plain
        assert "Looking at the import structure" in plain

    def test_thread_safety(self):
        """ThinkingDisplay should be safe under concurrent access."""
        td = ThinkingDisplay()
        errors = []

        def worker(i):
            try:
                event = ThinkingEvent(subject=f"task-{i}", phase=ThinkingPhase.GENERAL)
                td.start(event)
                td.render()
                if i % 2 == 0:
                    td.stop()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []


# =============================================================================
# ToolGroupDisplay
# =============================================================================


class TestToolGroupDisplay:
    """Tests for ToolGroupDisplay component."""

    def test_empty_by_default(self):
        tg = ToolGroupDisplay()
        assert tg.has_active is False
        assert tg.tool_count == 0
        assert tg.render() is None

    def test_tool_started(self):
        tg = ToolGroupDisplay()
        event = ToolEvent(tool_name="Read", tool_id="t1", status="started")
        tg.tool_started(event)
        assert tg.has_active is True
        assert tg.tool_count == 1

    def test_tool_completed(self):
        tg = ToolGroupDisplay()
        tg.tool_started(ToolEvent(tool_name="Read", tool_id="t1", status="started"))
        tg.tool_completed(ToolEvent(tool_name="Read", tool_id="t1", status="completed"))
        assert tg.has_active is False
        assert tg.tool_count == 1  # still tracked until cleared

    def test_tool_failed(self):
        tg = ToolGroupDisplay()
        tg.tool_started(ToolEvent(tool_name="Write", tool_id="t2", status="started"))
        tg.tool_completed(ToolEvent(
            tool_name="Write", tool_id="t2", status="failed", error="permission denied",
        ))
        assert tg.has_active is False

    def test_clear_completed(self):
        tg = ToolGroupDisplay()
        tg.tool_started(ToolEvent(tool_name="Read", tool_id="t1", status="started"))
        tg.tool_completed(ToolEvent(tool_name="Read", tool_id="t1", status="completed"))
        tg.clear_completed()
        assert tg.tool_count == 0

    def test_multiple_concurrent_tools(self):
        tg = ToolGroupDisplay()
        tg.tool_started(ToolEvent(tool_name="Read", tool_id="t1", status="started"))
        tg.tool_started(ToolEvent(tool_name="Grep", tool_id="t2", status="started"))
        tg.tool_started(ToolEvent(tool_name="Glob", tool_id="t3", status="started"))
        assert tg.has_active is True
        assert tg.tool_count == 3

    def test_render_returns_panel(self):
        tg = ToolGroupDisplay()
        tg.tool_started(ToolEvent(tool_name="Read", tool_id="t1", status="started"))
        panel = tg.render()
        assert isinstance(panel, Panel)

    def test_render_inline(self):
        tg = ToolGroupDisplay()
        tg.tool_started(ToolEvent(tool_name="Read", tool_id="t1", status="started"))
        tg.tool_started(ToolEvent(tool_name="Grep", tool_id="t2", status="started"))
        tg.tool_completed(ToolEvent(tool_name="Read", tool_id="t1", status="completed"))
        inline = tg.render_inline()
        assert inline is not None
        assert "[1/2]" in inline.plain
        assert "Grep" in inline.plain

    def test_render_inline_empty(self):
        tg = ToolGroupDisplay()
        assert tg.render_inline() is None

    def test_uses_tool_name_as_id_when_no_tool_id(self):
        tg = ToolGroupDisplay()
        tg.tool_started(ToolEvent(tool_name="Read", tool_id="", status="started"))
        assert tg.tool_count == 1
        tg.tool_completed(ToolEvent(tool_name="Read", tool_id="", status="completed"))
        assert tg.has_active is False

    def test_thread_safety(self):
        """ToolGroupDisplay should be safe under concurrent access."""
        tg = ToolGroupDisplay()
        errors = []

        def worker(i):
            try:
                tid = f"tool-{i}"
                tg.tool_started(ToolEvent(tool_name=f"Tool{i}", tool_id=tid, status="started"))
                tg.render()
                tg.render_inline()
                tg.tool_completed(ToolEvent(tool_name=f"Tool{i}", tool_id=tid, status="completed"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []


# =============================================================================
# _ToolEntry
# =============================================================================


class TestToolEntry:
    """Tests for _ToolEntry rendering."""

    def test_running_entry(self):
        entry = _ToolEntry(tool_id="t1", name="Read", status="running", started_at=time.time())
        line = entry.render_line()
        assert "Read" in line.plain

    def test_completed_entry_shows_duration(self):
        entry = _ToolEntry(tool_id="t1", name="Read", status="completed", started_at=time.time() - 2.5)
        entry.completed_at = time.time()
        line = entry.render_line()
        assert "Read" in line.plain
        assert "s)" in line.plain  # elapsed time

    def test_failed_entry_shows_error(self):
        entry = _ToolEntry(
            tool_id="t1", name="Write", status="failed",
            started_at=time.time(), error="permission denied",
        )
        line = entry.render_line()
        assert "Write" in line.plain
        assert "permission denied" in line.plain

    def test_running_entry_with_params(self):
        entry = _ToolEntry(
            tool_id="t1", name="Read", status="running",
            started_at=time.time(), params="src/main.py",
        )
        line = entry.render_line()
        assert "src/main.py" in line.plain


# =============================================================================
# DisplayManager
# =============================================================================


class TestDisplayManager:
    """Tests for the main DisplayManager class."""

    def _make_emitter(self):
        return EventEmitter()

    def test_construction(self):
        emitter = self._make_emitter()
        dm = DisplayManager(emitter)
        assert dm.state == EngineState.IDLE
        assert dm.thinking.active is False
        assert dm.tools.tool_count == 0

    def test_registers_handlers(self):
        emitter = self._make_emitter()
        dm = DisplayManager(emitter)
        # Should have handlers for ThinkingEvent, ToolEvent, ErrorEvent, StateEvent
        assert emitter.handler_count(ThinkingEvent) == 1
        assert emitter.handler_count(ToolEvent) == 1
        assert emitter.handler_count(ErrorEvent) == 1
        assert emitter.handler_count(StateEvent) == 1

    def test_unregister_removes_handlers(self):
        emitter = self._make_emitter()
        dm = DisplayManager(emitter)
        dm.unregister()
        assert emitter.handler_count(ThinkingEvent) == 0
        assert emitter.handler_count(ToolEvent) == 0
        assert emitter.handler_count(ErrorEvent) == 0
        assert emitter.handler_count(StateEvent) == 0

    def test_thinking_event_changes_state(self):
        emitter = self._make_emitter()
        dm = DisplayManager(emitter, console=Console(file=MagicMock()))
        emitter.emit(ThinkingEvent(
            phase=ThinkingPhase.ANALYZING,
            subject="code",
        ))
        assert dm.state == EngineState.THINKING
        assert dm.thinking.active is True

    def test_thinking_complete_resets_state(self):
        emitter = self._make_emitter()
        dm = DisplayManager(emitter, console=Console(file=MagicMock()))
        emitter.emit(ThinkingEvent(subject="test"))
        emitter.emit(ThinkingEvent(is_complete=True))
        assert dm.state == EngineState.IDLE
        assert dm.thinking.active is False

    def test_tool_started_changes_state(self):
        emitter = self._make_emitter()
        dm = DisplayManager(emitter, console=Console(file=MagicMock()))
        emitter.emit(ToolEvent(tool_name="Read", tool_id="t1", status="started"))
        assert dm.state == EngineState.TOOL_EXECUTING
        assert dm.tools.tool_count == 1

    def test_tool_completed_returns_to_responding(self):
        emitter = self._make_emitter()
        dm = DisplayManager(emitter, console=Console(file=MagicMock()))
        emitter.emit(ToolEvent(tool_name="Read", tool_id="t1", status="started"))
        emitter.emit(ToolEvent(tool_name="Read", tool_id="t1", status="completed"))
        assert dm.state == EngineState.RESPONDING

    def test_error_event_changes_state(self):
        emitter = self._make_emitter()
        dm = DisplayManager(emitter, console=Console(file=MagicMock()))
        emitter.emit(ErrorEvent(error="something went wrong"))
        assert dm.state == EngineState.ERROR

    def test_state_event_ready_resets_to_idle(self):
        emitter = self._make_emitter()
        dm = DisplayManager(emitter, console=Console(file=MagicMock()))
        dm._set_state(EngineState.ERROR)
        emitter.emit(StateEvent(new_state=BridgeState.READY))
        assert dm.state == EngineState.IDLE

    def test_state_event_bridge_error(self):
        emitter = self._make_emitter()
        dm = DisplayManager(emitter, console=Console(file=MagicMock()))
        emitter.emit(StateEvent(new_state=BridgeState.ERROR))
        assert dm.state == EngineState.ERROR

    def test_on_response_start_end_lifecycle(self):
        emitter = self._make_emitter()
        dm = DisplayManager(emitter, console=Console(file=MagicMock()))
        dm.on_response_start()
        assert dm.state == EngineState.THINKING
        dm.on_response_end()
        assert dm.state == EngineState.IDLE
        assert dm.thinking.active is False

    def test_verbose_mode(self):
        """Verbose mode should print full thinking text."""
        emitter = self._make_emitter()
        mock_file = MagicMock()
        dm = DisplayManager(emitter, console=Console(file=mock_file), verbose=True)
        emitter.emit(ThinkingEvent(
            subject="imports",
            thought="Analyzing the import structure...",
            phase=ThinkingPhase.ANALYZING,
        ))
        # In verbose mode, render_verbose is called and printed
        assert dm.thinking.active is True

    def test_full_lifecycle(self):
        """Test a realistic sequence: thinking -> tool -> tool complete -> response."""
        emitter = self._make_emitter()
        dm = DisplayManager(emitter, console=Console(file=MagicMock()))

        # Start response
        dm.on_response_start()
        assert dm.state == EngineState.THINKING

        # Thinking event
        emitter.emit(ThinkingEvent(subject="analyze", phase=ThinkingPhase.ANALYZING))
        assert dm.state == EngineState.THINKING

        # Tool execution starts
        emitter.emit(ToolEvent(tool_name="Read", tool_id="t1", status="started"))
        assert dm.state == EngineState.TOOL_EXECUTING

        # Tool completes
        emitter.emit(ToolEvent(tool_name="Read", tool_id="t1", status="completed"))
        assert dm.state == EngineState.RESPONDING

        # Thinking completes
        emitter.emit(ThinkingEvent(is_complete=True))

        # Response ends
        dm.on_response_end()
        assert dm.state == EngineState.IDLE


# =============================================================================
# Rendering: render_status_line
# =============================================================================


class TestRenderStatusLine:
    """Tests for DisplayManager.render_status_line()."""

    def test_idle_state(self):
        emitter = EventEmitter()
        dm = DisplayManager(emitter, console=Console(file=MagicMock()))
        line = dm.render_status_line()
        assert "> " in line.plain

    def test_thinking_state(self):
        emitter = EventEmitter()
        dm = DisplayManager(emitter, console=Console(file=MagicMock()))
        emitter.emit(ThinkingEvent(subject="testing", phase=ThinkingPhase.GENERAL))
        line = dm.render_status_line()
        assert "testing" in line.plain

    def test_tool_executing_state(self):
        emitter = EventEmitter()
        dm = DisplayManager(emitter, console=Console(file=MagicMock()))
        emitter.emit(ToolEvent(tool_name="Grep", tool_id="t1", status="started"))
        line = dm.render_status_line()
        assert "Grep" in line.plain

    def test_error_state(self):
        emitter = EventEmitter()
        dm = DisplayManager(emitter, console=Console(file=MagicMock()))
        emitter.emit(ErrorEvent(error="test error"))
        line = dm.render_status_line()
        assert "Error" in line.plain


# =============================================================================
# Helper: _summarize_params
# =============================================================================


class TestSummarizeParams:
    """Tests for _summarize_params helper."""

    def test_empty_params(self):
        assert _summarize_params({}) == ""

    def test_file_path(self):
        assert _summarize_params({"file_path": "/src/main.py"}) == "/src/main.py"

    def test_command(self):
        assert _summarize_params({"command": "git status"}) == "git status"

    def test_query(self):
        assert _summarize_params({"query": "search term"}) == "search term"

    def test_long_value_truncated(self):
        long_path = "/very/long/path/" + "x" * 100
        result = _summarize_params({"file_path": long_path})
        assert len(result) <= 63  # 57 + "..."
        assert result.endswith("...")

    def test_fallback_to_first_string(self):
        result = _summarize_params({"custom_key": "custom_value"})
        assert result == "custom_value"

    def test_non_string_values_skipped(self):
        result = _summarize_params({"count": 42})
        assert result == ""


# =============================================================================
# Constants
# =============================================================================


class TestConstants:
    """Tests for display constants."""

    def test_status_icons_complete(self):
        assert "pending" in STATUS_ICONS
        assert "running" in STATUS_ICONS
        assert "completed" in STATUS_ICONS
        assert "failed" in STATUS_ICONS
        assert "cancelled" in STATUS_ICONS

    def test_phase_labels_complete(self):
        for phase in ThinkingPhase:
            assert phase in PHASE_LABELS

    def test_phase_styles_complete(self):
        for phase in ThinkingPhase:
            assert phase in PHASE_STYLES
