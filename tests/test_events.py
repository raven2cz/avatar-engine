"""Tests for avatar_engine.events module."""

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
)
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
