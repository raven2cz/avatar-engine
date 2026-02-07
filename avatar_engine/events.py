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
import re
import threading
from abc import ABC
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar
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
    ACTIVITY = "activity"


class ThinkingPhase(Enum):
    """Phase of AI thinking — drives avatar animation in GUI."""
    GENERAL = "general"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    CODING = "coding"
    REVIEWING = "reviewing"
    TOOL_PLANNING = "tool_planning"


class ActivityStatus(Enum):
    """Status of a concurrent activity (tool, agent, background task)."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EngineState(Enum):
    """High-level engine state — drives CLI display and GUI avatar animations."""
    IDLE = "idle"
    THINKING = "thinking"
    RESPONDING = "responding"
    TOOL_EXECUTING = "tool_executing"
    WAITING_APPROVAL = "waiting_approval"
    ERROR = "error"


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
    Model thinking event — structured for GUI visualization.

    Emitted during model's internal reasoning process (Gemini thinking,
    Codex reasoning, or synthetic events for Claude).

    GUI should use phase/subject to drive avatar animations and status display.
    """
    thought: str = ""
    phase: ThinkingPhase = ThinkingPhase.GENERAL
    subject: str = ""          # Extracted bold header (e.g. "Analyzing imports")
    is_start: bool = False     # First chunk of thinking block
    is_complete: bool = False  # Last chunk of thinking block
    block_id: str = ""         # Groups chunks into logical blocks
    token_count: int = 0       # Tokens consumed by thinking
    category: str = ""         # Freeform category hint


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


@dataclass
class DiagnosticEvent(AvatarEvent):
    """
    Diagnostic information from subprocess stderr, warnings, deprecations.

    GUI can show in debug panel or status bar.
    CLI can show in verbose mode.
    """
    message: str = ""
    level: str = "info"     # "info", "warning", "error", "debug"
    source: str = ""        # "stderr", "acp", "health_check"


@dataclass
class ActivityEvent(AvatarEvent):
    """
    Tracks concurrent activities — tool executions, background tasks, agents.

    GUI uses this to show a tree of parallel operations with progress.
    """
    activity_id: str = ""
    parent_activity_id: str = ""
    activity_type: str = ""           # "tool_use", "agent", "background_task"
    name: str = ""
    status: ActivityStatus = ActivityStatus.PENDING
    progress: float = 0.0             # 0.0-1.0 (if estimable)
    detail: str = ""
    concurrent_group: str = ""        # Groups parallel activities
    is_cancellable: bool = False
    started_at: float = 0.0
    completed_at: float = 0.0


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
        self._lock = threading.Lock()  # Thread-safe for GUI integration (RC-2)

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
            with self._lock:
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
        with self._lock:
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
        with self._lock:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler)

    def emit(self, event: AvatarEvent) -> None:
        """
        Emit an event to all registered handlers.

        Thread-safe: snapshots handler lists under lock, then calls
        handlers WITHOUT lock so handlers can safely register new handlers.

        Args:
            event: The event to emit
        """
        # Snapshot handlers under lock (RC-2 fix)
        with self._lock:
            global_snapshot = list(self._global_handlers)
            specific_snapshot = list(self._handlers.get(type(event), []))

        # Call handlers WITHOUT lock — handler may register/remove handlers
        for handler in global_snapshot:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler error (global): {e}")

        for handler in specific_snapshot:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler error ({type(event).__name__}): {e}")

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
        with self._lock:
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
        with self._lock:
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
        with self._lock:
            if event_type is not None:
                return len(self._handlers.get(event_type, []))
            return sum(len(h) for h in self._handlers.values()) + len(self._global_handlers)


# =========================================================================
# Thinking utilities — bold parser + phase classifier
# Pattern adopted from Gemini CLI (parseThought) and Codex (extract_first_bold)
# =========================================================================

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")

# Pre-compiled regex for classification (GAP-10 optimization)
_PHASE_PATTERNS = [
    (ThinkingPhase.ANALYZING, re.compile(r"analyz|look at|examin|reading|inspect", re.I)),
    (ThinkingPhase.PLANNING, re.compile(r"plan|approach|strategy|steps|design", re.I)),
    (ThinkingPhase.CODING, re.compile(r"write|implement|code|function|class|def ", re.I)),
    (ThinkingPhase.REVIEWING, re.compile(r"check|verify|review|test|validate", re.I)),
    (ThinkingPhase.TOOL_PLANNING, re.compile(r"tool|call|execut|run |invok", re.I)),
]


def extract_bold_subject(text: str) -> Tuple[str, str]:
    """
    Extract the first **bold** subject from thinking text.

    Both Gemini CLI and Codex use this pattern: the first ``**bold text**``
    in a thinking/reasoning stream is used as a status header in the UI.

    Args:
        text: Raw thinking text from model

    Returns:
        (subject, description) — subject is the bold text,
        description is everything else (stripped).
        If no bold marker found, subject is empty, description is the full text.
    """
    match = _BOLD_RE.search(text)
    if match:
        subject = match.group(1).strip()
        # Description = text with the bold marker removed
        desc = (text[:match.start()] + text[match.end():]).strip()
        return subject, desc
    return "", text.strip()


def classify_thinking(thought: str) -> ThinkingPhase:
    """
    Heuristic classification of thinking content for GUI display.

    Providers don't send explicit phases, so we classify based on keywords.
    (GAP-10: Optimized using pre-compiled regex)
    """
    for phase, pattern in _PHASE_PATTERNS:
        if pattern.search(thought):
            return phase
    return ThinkingPhase.GENERAL
