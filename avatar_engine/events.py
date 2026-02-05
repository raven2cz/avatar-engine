"""
Avatar Engine event system.

Provides event-driven architecture for GUI integration.
Events are emitted during AI interactions for:
- Text streaming (avatar speaking)
- Tool execution (show in GUI)
- State changes (update status)
- Errors (handle gracefully)
- Cost tracking (usage monitoring)
"""

import logging
from abc import ABC
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar
import time

from .types import BridgeState

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Event type categories."""
    TEXT = "text"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    STATE_CHANGE = "state_change"
    ERROR = "error"
    THINKING = "thinking"
    COST = "cost"


@dataclass
class AvatarEvent(ABC):
    """Base event class for all Avatar Engine events."""
    timestamp: float = field(default_factory=time.time)
    provider: str = ""


@dataclass
class TextEvent(AvatarEvent):
    """
    Text chunk received from AI.

    Use this for real-time display, TTS, avatar animation.
    """
    text: str = ""
    is_complete: bool = False


@dataclass
class ToolEvent(AvatarEvent):
    """
    Tool execution event.

    Use this to show tool usage in GUI.
    """
    tool_name: str = ""
    tool_id: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    status: str = "started"  # started, completed, failed
    result: Optional[str] = None
    error: Optional[str] = None


@dataclass
class StateEvent(AvatarEvent):
    """
    Bridge state change event.

    Use this to update status indicators in GUI.
    """
    old_state: Optional[BridgeState] = None
    new_state: Optional[BridgeState] = None


@dataclass
class ThinkingEvent(AvatarEvent):
    """
    Model thinking event (Gemini 3 with include_thoughts=True).

    Use this to show AI reasoning process.
    """
    thought: str = ""


@dataclass
class ErrorEvent(AvatarEvent):
    """
    Error event.

    Use this for error handling and user feedback.
    """
    error: str = ""
    recoverable: bool = True


@dataclass
class CostEvent(AvatarEvent):
    """
    Cost/usage update event.

    Use this for usage monitoring and budget tracking.
    """
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


# Type variable for event handlers
E = TypeVar("E", bound=AvatarEvent)


class EventEmitter:
    """
    Event emitter for Avatar Engine.

    Provides a simple pub/sub mechanism for event-driven architecture.

    Usage:
        emitter = EventEmitter()

        @emitter.on(TextEvent)
        def on_text(event: TextEvent):
            print(event.text)

        emitter.emit(TextEvent(text="Hello!"))
    """

    def __init__(self) -> None:
        self._handlers: Dict[Type[AvatarEvent], List[Callable[..., None]]] = {}
        self._global_handlers: List[Callable[[AvatarEvent], None]] = []

    def on(self, event_type: Type[E]) -> Callable[[Callable[[E], None]], Callable[[E], None]]:
        """
        Decorator to register an event handler.

        Args:
            event_type: The event class to handle

        Returns:
            Decorator function

        Example:
            @engine.on(TextEvent)
            def handle_text(event: TextEvent):
                gui.update_text(event.text)
        """
        def decorator(func: Callable[[E], None]) -> Callable[[E], None]:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(func)
            return func
        return decorator

    def on_any(self, func: Callable[[AvatarEvent], None]) -> Callable[[AvatarEvent], None]:
        """
        Register a handler for all events.

        Args:
            func: Handler function that receives any event

        Returns:
            The handler function (for decorator use)
        """
        self._global_handlers.append(func)
        return func

    def add_handler(
        self,
        event_type: Type[E],
        handler: Callable[[E], None],
    ) -> None:
        """
        Add an event handler programmatically.

        Args:
            event_type: The event class to handle
            handler: Handler function
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def emit(self, event: AvatarEvent) -> None:
        """
        Emit an event to all registered handlers.

        Args:
            event: The event to emit
        """
        # Global handlers first
        for handler in self._global_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler error (global): {e}")

        # Type-specific handlers
        event_type = type(event)
        if event_type in self._handlers:
            for handler in self._handlers[event_type]:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Event handler error ({event_type.__name__}): {e}")

    def remove_handler(
        self,
        event_type: Type[E],
        handler: Callable[[E], None],
    ) -> None:
        """
        Remove a specific handler.

        Args:
            event_type: The event class
            handler: The handler function to remove
        """
        if event_type in self._handlers:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h != handler
            ]

    def clear_handlers(self, event_type: Optional[Type[E]] = None) -> None:
        """
        Clear handlers.

        Args:
            event_type: If provided, clear only handlers for this type.
                       If None, clear all handlers.
        """
        if event_type is not None:
            self._handlers[event_type] = []
        else:
            self._handlers.clear()
            self._global_handlers.clear()

    def handler_count(self, event_type: Optional[Type[E]] = None) -> int:
        """
        Get the number of registered handlers.

        Args:
            event_type: If provided, count only handlers for this type.
                       If None, count all handlers.

        Returns:
            Number of handlers
        """
        if event_type is not None:
            return len(self._handlers.get(event_type, []))
        return sum(len(h) for h in self._handlers.values()) + len(self._global_handlers)
