"""Tests for avatar_engine.events module."""

import threading
import pytest
from avatar_engine.events import (
    EventEmitter,
    AvatarEvent,
    TextEvent,
    ToolEvent,
    StateEvent,
    ThinkingEvent,
    ErrorEvent,
    CostEvent,
    EventType,
    ThinkingPhase,
    ActivityEvent,
    ActivityStatus,
    extract_bold_subject,
    classify_thinking,
)
from avatar_engine.activity import ActivityTracker
from avatar_engine.types import BridgeState


class TestEventTypes:
    """Tests for event dataclasses."""

    def test_text_event_defaults(self):
        """TextEvent should have sensible defaults."""
        event = TextEvent()
        assert event.text == ""
        assert event.is_complete is False
        assert event.provider == ""
        assert event.timestamp > 0

    def test_text_event_with_values(self):
        """TextEvent should accept custom values."""
        event = TextEvent(text="Hello", is_complete=True, provider="gemini")
        assert event.text == "Hello"
        assert event.is_complete is True
        assert event.provider == "gemini"

    def test_tool_event_defaults(self):
        """ToolEvent should have sensible defaults."""
        event = ToolEvent()
        assert event.tool_name == ""
        assert event.tool_id == ""
        assert event.parameters == {}
        assert event.status == "started"
        assert event.result is None
        assert event.error is None

    def test_tool_event_with_values(self):
        """ToolEvent should accept custom values."""
        event = ToolEvent(
            tool_name="Read",
            tool_id="abc123",
            parameters={"file": "test.py"},
            status="completed",
            result="file contents",
        )
        assert event.tool_name == "Read"
        assert event.tool_id == "abc123"
        assert event.parameters == {"file": "test.py"}
        assert event.status == "completed"
        assert event.result == "file contents"

    def test_state_event(self):
        """StateEvent should store old and new state."""
        event = StateEvent(
            old_state=BridgeState.READY,
            new_state=BridgeState.BUSY,
            provider="claude",
        )
        assert event.old_state == BridgeState.READY
        assert event.new_state == BridgeState.BUSY

    def test_thinking_event(self):
        """ThinkingEvent should store thought text."""
        event = ThinkingEvent(thought="Let me analyze this...", provider="gemini")
        assert event.thought == "Let me analyze this..."

    def test_error_event(self):
        """ErrorEvent should store error and recoverable flag."""
        event = ErrorEvent(error="Connection failed", recoverable=True)
        assert event.error == "Connection failed"
        assert event.recoverable is True

    def test_cost_event(self):
        """CostEvent should store cost and token usage."""
        event = CostEvent(
            cost_usd=0.05,
            input_tokens=100,
            output_tokens=200,
            provider="claude",
        )
        assert event.cost_usd == 0.05
        assert event.input_tokens == 100
        assert event.output_tokens == 200


class TestEventEmitter:
    """Tests for EventEmitter class."""

    def test_on_decorator(self):
        """@emitter.on(EventType) should register handler."""
        emitter = EventEmitter()
        received = []

        @emitter.on(TextEvent)
        def handler(event: TextEvent):
            received.append(event)

        emitter.emit(TextEvent(text="test"))

        assert len(received) == 1
        assert received[0].text == "test"

    def test_on_specific_type(self):
        """Handler should only receive events of registered type."""
        emitter = EventEmitter()
        text_received = []
        tool_received = []

        @emitter.on(TextEvent)
        def text_handler(event: TextEvent):
            text_received.append(event)

        @emitter.on(ToolEvent)
        def tool_handler(event: ToolEvent):
            tool_received.append(event)

        emitter.emit(TextEvent(text="hello"))
        emitter.emit(ToolEvent(tool_name="Read"))
        emitter.emit(TextEvent(text="world"))

        assert len(text_received) == 2
        assert len(tool_received) == 1

    def test_on_any(self):
        """on_any should receive all events."""
        emitter = EventEmitter()
        all_events = []

        @emitter.on_any
        def handler(event: AvatarEvent):
            all_events.append(event)

        emitter.emit(TextEvent(text="1"))
        emitter.emit(ToolEvent(tool_name="2"))
        emitter.emit(ErrorEvent(error="3"))

        assert len(all_events) == 3

    def test_add_handler(self):
        """add_handler should register handler programmatically."""
        emitter = EventEmitter()
        received = []

        def handler(event: TextEvent):
            received.append(event)

        emitter.add_handler(TextEvent, handler)
        emitter.emit(TextEvent(text="test"))

        assert len(received) == 1

    def test_multiple_handlers(self):
        """Multiple handlers for same event type should all be called."""
        emitter = EventEmitter()
        results = []

        @emitter.on(TextEvent)
        def handler1(event):
            results.append("h1")

        @emitter.on(TextEvent)
        def handler2(event):
            results.append("h2")

        emitter.emit(TextEvent(text="test"))

        assert results == ["h1", "h2"]

    def test_remove_handler(self):
        """remove_handler should unregister specific handler."""
        emitter = EventEmitter()
        received = []

        def handler(event: TextEvent):
            received.append(event)

        emitter.add_handler(TextEvent, handler)
        emitter.emit(TextEvent(text="1"))

        emitter.remove_handler(TextEvent, handler)
        emitter.emit(TextEvent(text="2"))

        assert len(received) == 1

    def test_clear_handlers_specific(self):
        """clear_handlers with type should clear only that type."""
        emitter = EventEmitter()
        text_count = [0]
        tool_count = [0]

        @emitter.on(TextEvent)
        def text_handler(e):
            text_count[0] += 1

        @emitter.on(ToolEvent)
        def tool_handler(e):
            tool_count[0] += 1

        emitter.emit(TextEvent())
        emitter.emit(ToolEvent())

        emitter.clear_handlers(TextEvent)

        emitter.emit(TextEvent())
        emitter.emit(ToolEvent())

        assert text_count[0] == 1  # Only first one
        assert tool_count[0] == 2  # Both

    def test_clear_handlers_all(self):
        """clear_handlers without args should clear all handlers."""
        emitter = EventEmitter()
        count = [0]

        @emitter.on(TextEvent)
        def handler(e):
            count[0] += 1

        @emitter.on_any
        def any_handler(e):
            count[0] += 1

        emitter.emit(TextEvent())
        assert count[0] == 2

        emitter.clear_handlers()
        emitter.emit(TextEvent())
        assert count[0] == 2  # No change

    def test_handler_count(self):
        """handler_count should return correct counts."""
        emitter = EventEmitter()

        assert emitter.handler_count() == 0
        assert emitter.handler_count(TextEvent) == 0

        @emitter.on(TextEvent)
        def h1(e):
            pass

        @emitter.on(TextEvent)
        def h2(e):
            pass

        @emitter.on(ToolEvent)
        def h3(e):
            pass

        @emitter.on_any
        def h4(e):
            pass

        assert emitter.handler_count(TextEvent) == 2
        assert emitter.handler_count(ToolEvent) == 1
        assert emitter.handler_count() == 4  # 2 + 1 + 1 global

    def test_handler_exception_does_not_break_others(self):
        """Exception in one handler should not prevent others from running."""
        emitter = EventEmitter()
        results = []

        @emitter.on(TextEvent)
        def bad_handler(e):
            raise ValueError("oops")

        @emitter.on(TextEvent)
        def good_handler(e):
            results.append("ok")

        # Should not raise, should call good_handler
        emitter.emit(TextEvent())

        assert results == ["ok"]

    def test_global_handler_exception_does_not_break_specific(self):
        """Exception in global handler should not break specific handlers."""
        emitter = EventEmitter()
        results = []

        @emitter.on_any
        def bad_global(e):
            raise RuntimeError("global fail")

        @emitter.on(TextEvent)
        def good_specific(e):
            results.append("specific ok")

        emitter.emit(TextEvent())

        assert results == ["specific ok"]


class TestEventType:
    """Tests for EventType enum."""

    def test_event_type_values(self):
        """EventType should have expected values."""
        assert EventType.TEXT.value == "text"
        assert EventType.TOOL_START.value == "tool_start"
        assert EventType.TOOL_END.value == "tool_end"
        assert EventType.STATE_CHANGE.value == "state_change"
        assert EventType.ERROR.value == "error"
        assert EventType.THINKING.value == "thinking"
        assert EventType.COST.value == "cost"
        assert EventType.ACTIVITY.value == "activity"


class TestThinkingPhase:
    """Tests for ThinkingPhase enum."""

    def test_all_phases_exist(self):
        assert ThinkingPhase.GENERAL.value == "general"
        assert ThinkingPhase.ANALYZING.value == "analyzing"
        assert ThinkingPhase.PLANNING.value == "planning"
        assert ThinkingPhase.CODING.value == "coding"
        assert ThinkingPhase.REVIEWING.value == "reviewing"
        assert ThinkingPhase.TOOL_PLANNING.value == "tool_planning"


class TestExtendedThinkingEvent:
    """Tests for extended ThinkingEvent fields."""

    def test_default_fields(self):
        event = ThinkingEvent(thought="test")
        assert event.phase == ThinkingPhase.GENERAL
        assert event.subject == ""
        assert event.is_start is False
        assert event.is_complete is False
        assert event.block_id == ""
        assert event.token_count == 0
        assert event.category == ""

    def test_full_thinking_event(self):
        event = ThinkingEvent(
            thought="**Analyzing imports** Let me look at the file...",
            phase=ThinkingPhase.ANALYZING,
            subject="Analyzing imports",
            is_start=True,
            is_complete=False,
            block_id="block-1",
            token_count=42,
            category="code_analysis",
            provider="gemini",
        )
        assert event.phase == ThinkingPhase.ANALYZING
        assert event.subject == "Analyzing imports"
        assert event.is_start is True
        assert event.is_complete is False
        assert event.block_id == "block-1"
        assert event.token_count == 42


class TestExtractBoldSubject:
    """Tests for extract_bold_subject() — bold parser."""

    def test_simple_bold(self):
        subject, desc = extract_bold_subject("**Analyzing code** Let me look...")
        assert subject == "Analyzing code"
        assert desc == "Let me look..."

    def test_bold_at_start(self):
        subject, desc = extract_bold_subject("**Planning approach**")
        assert subject == "Planning approach"
        assert desc == ""

    def test_bold_in_middle(self):
        subject, desc = extract_bold_subject("I need to **review tests** carefully")
        assert subject == "review tests"
        assert "I need to" in desc
        assert "carefully" in desc

    def test_no_bold(self):
        subject, desc = extract_bold_subject("Just plain text without markers")
        assert subject == ""
        assert desc == "Just plain text without markers"

    def test_empty_string(self):
        subject, desc = extract_bold_subject("")
        assert subject == ""
        assert desc == ""

    def test_multiple_bold_takes_first(self):
        subject, desc = extract_bold_subject("**First** and **Second**")
        assert subject == "First"

    def test_nested_asterisks(self):
        subject, desc = extract_bold_subject("**Bold text** with *italic*")
        assert subject == "Bold text"


class TestClassifyThinking:
    """Tests for classify_thinking() — heuristic phase classifier."""

    def test_analyzing(self):
        assert classify_thinking("Let me analyze this code") == ThinkingPhase.ANALYZING
        assert classify_thinking("Examining the function") == ThinkingPhase.ANALYZING
        assert classify_thinking("Reading the file contents") == ThinkingPhase.ANALYZING

    def test_planning(self):
        assert classify_thinking("My plan is to refactor") == ThinkingPhase.PLANNING
        assert classify_thinking("The approach should be") == ThinkingPhase.PLANNING
        assert classify_thinking("Steps to implement") == ThinkingPhase.PLANNING

    def test_coding(self):
        assert classify_thinking("I'll implement the function") == ThinkingPhase.CODING
        assert classify_thinking("Writing the code now") == ThinkingPhase.CODING

    def test_reviewing(self):
        assert classify_thinking("Let me check the output") == ThinkingPhase.REVIEWING
        assert classify_thinking("Verifying the results") == ThinkingPhase.REVIEWING
        assert classify_thinking("I need to test this") == ThinkingPhase.REVIEWING

    def test_tool_planning(self):
        assert classify_thinking("I'll use the tool to") == ThinkingPhase.TOOL_PLANNING
        assert classify_thinking("Let me execute the command") == ThinkingPhase.TOOL_PLANNING
        assert classify_thinking("Invoking the search") == ThinkingPhase.TOOL_PLANNING

    def test_general_fallback(self):
        assert classify_thinking("Hmm, interesting question") == ThinkingPhase.GENERAL
        assert classify_thinking("") == ThinkingPhase.GENERAL


class TestActivityEvent:
    """Tests for ActivityEvent dataclass."""

    def test_defaults(self):
        event = ActivityEvent()
        assert event.activity_id == ""
        assert event.status == ActivityStatus.PENDING
        assert event.progress == 0.0
        assert event.is_cancellable is False

    def test_full_activity(self):
        event = ActivityEvent(
            activity_id="tool-1",
            activity_type="tool_use",
            name="Read file",
            status=ActivityStatus.RUNNING,
            progress=0.5,
            concurrent_group="group-1",
        )
        assert event.activity_id == "tool-1"
        assert event.status == ActivityStatus.RUNNING
        assert event.progress == 0.5
        assert event.concurrent_group == "group-1"


class TestActivityTracker:
    """Tests for ActivityTracker."""

    def test_start_and_complete(self):
        emitter = EventEmitter()
        events = []
        emitter.on_any(lambda e: events.append(e))

        tracker = ActivityTracker(emitter, provider="gemini")
        tracker.start_activity("t1", name="Read", activity_type="tool_use")

        assert tracker.active_count == 1
        assert len(events) == 1
        assert events[0].status == ActivityStatus.RUNNING

        tracker.complete_activity("t1")

        assert tracker.active_count == 0
        assert len(events) == 2
        assert events[1].status == ActivityStatus.COMPLETED
        assert events[1].progress == 1.0

    def test_fail_activity(self):
        emitter = EventEmitter()
        tracker = ActivityTracker(emitter)
        tracker.start_activity("t1", name="Bash")
        tracker.fail_activity("t1", detail="exit code 1")
        assert tracker.active_count == 0

    def test_cancel_activity(self):
        emitter = EventEmitter()
        tracker = ActivityTracker(emitter)
        tracker.start_activity("t1", name="Grep")
        tracker.cancel_activity("t1")
        assert tracker.active_count == 0

    def test_update_progress(self):
        emitter = EventEmitter()
        events = []
        emitter.on_any(lambda e: events.append(e))

        tracker = ActivityTracker(emitter)
        tracker.start_activity("t1", name="Build")
        tracker.update_activity("t1", progress=0.5, detail="compiling")

        assert len(events) == 2
        assert events[1].progress == 0.5
        assert events[1].detail == "compiling"

    def test_multiple_concurrent_activities(self):
        emitter = EventEmitter()
        tracker = ActivityTracker(emitter)
        tracker.start_activity("t1", name="Read A")
        tracker.start_activity("t2", name="Read B")
        tracker.start_activity("t3", name="Read C")

        assert tracker.active_count == 3
        assert len(tracker.active_activities) == 3

        tracker.complete_activity("t2")
        assert tracker.active_count == 2

    def test_clear(self):
        emitter = EventEmitter()
        tracker = ActivityTracker(emitter)
        tracker.start_activity("t1", name="A")
        tracker.start_activity("t2", name="B")
        tracker.clear()
        assert tracker.active_count == 0

    def test_get_activity(self):
        emitter = EventEmitter()
        tracker = ActivityTracker(emitter)
        tracker.start_activity("t1", name="Read")
        act = tracker.get_activity("t1")
        assert act is not None
        assert act.name == "Read"
        assert tracker.get_activity("nonexistent") is None


class TestEventEmitterThreadSafety:
    """Tests for thread-safe EventEmitter (RC-2 fix)."""

    def test_concurrent_emit_and_add(self):
        """Concurrent emit + add_handler should not crash."""
        emitter = EventEmitter()
        errors = []

        def add_handlers():
            for i in range(100):
                emitter.add_handler(TextEvent, lambda e: None)

        def emit_events():
            for i in range(100):
                try:
                    emitter.emit(TextEvent(text=f"event-{i}"))
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=add_handlers)
        t2 = threading.Thread(target=emit_events)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0

    def test_handler_can_register_new_handler_during_emit(self):
        """Handler registering new handler during emit should not deadlock."""
        emitter = EventEmitter()
        second_received = []

        def first_handler(event):
            # Register a new handler from within a handler
            emitter.add_handler(ToolEvent, lambda e: second_received.append(e))

        emitter.add_handler(TextEvent, first_handler)
        emitter.emit(TextEvent(text="trigger"))

        # The newly registered handler should work
        emitter.emit(ToolEvent(tool_name="Read"))
        assert len(second_received) == 1
