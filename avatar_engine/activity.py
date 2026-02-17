"""
Activity tracker for concurrent operation management.

Tracks parallel tool executions, background tasks, and agent sub-processes.
Emits ActivityEvents for GUI visualization (tree of operations with progress).
"""

import threading
import time

from .events import (
    ActivityEvent,
    ActivityStatus,
    EventEmitter,
)


class ActivityTracker:
    """
    Tracks concurrent activities and emits ActivityEvents.

    Thread-safe: all state mutations protected by lock.

    Usage:
        tracker = ActivityTracker(engine)  # engine is an EventEmitter
        tracker.start_activity("tool-1", name="Read file", activity_type="tool_use")
        tracker.complete_activity("tool-1")
    """

    def __init__(self, emitter: EventEmitter, provider: str = "") -> None:
        self._activities: dict[str, ActivityEvent] = {}
        self._emitter = emitter
        self._provider = provider
        self._lock = threading.Lock()

    def start_activity(
        self,
        activity_id: str,
        *,
        name: str = "",
        activity_type: str = "tool_use",
        parent_activity_id: str = "",
        concurrent_group: str = "",
        is_cancellable: bool = False,
        detail: str = "",
    ) -> ActivityEvent:
        """Start tracking a new activity."""
        now = time.time()
        event = ActivityEvent(
            timestamp=now,
            provider=self._provider,
            activity_id=activity_id,
            parent_activity_id=parent_activity_id,
            activity_type=activity_type,
            name=name,
            status=ActivityStatus.RUNNING,
            detail=detail,
            concurrent_group=concurrent_group,
            is_cancellable=is_cancellable,
            started_at=now,
        )
        with self._lock:
            self._activities[activity_id] = event
        self._emitter.emit(event)
        return event

    def update_activity(
        self,
        activity_id: str,
        *,
        progress: float | None = None,
        detail: str | None = None,
    ) -> None:
        """Update progress or detail of a running activity."""
        with self._lock:
            if activity_id not in self._activities:
                return
            event = self._activities[activity_id]
            if progress is not None:
                event.progress = progress
            if detail is not None:
                event.detail = detail
        self._emitter.emit(event)

    def complete_activity(
        self,
        activity_id: str,
        *,
        detail: str = "",
    ) -> None:
        """Mark an activity as completed."""
        with self._lock:
            event = self._activities.pop(activity_id, None)
        if event:
            event.status = ActivityStatus.COMPLETED
            event.completed_at = time.time()
            event.progress = 1.0
            if detail:
                event.detail = detail
            self._emitter.emit(event)

    def fail_activity(
        self,
        activity_id: str,
        *,
        detail: str = "",
    ) -> None:
        """Mark an activity as failed."""
        with self._lock:
            event = self._activities.pop(activity_id, None)
        if event:
            event.status = ActivityStatus.FAILED
            event.completed_at = time.time()
            if detail:
                event.detail = detail
            self._emitter.emit(event)

    def cancel_activity(self, activity_id: str) -> None:
        """Mark an activity as cancelled."""
        with self._lock:
            event = self._activities.pop(activity_id, None)
        if event:
            event.status = ActivityStatus.CANCELLED
            event.completed_at = time.time()
            self._emitter.emit(event)

    @property
    def active_count(self) -> int:
        """Number of currently active activities."""
        with self._lock:
            return len(self._activities)

    @property
    def active_activities(self) -> list[ActivityEvent]:
        """Snapshot of all currently active activities."""
        with self._lock:
            return list(self._activities.values())

    def get_activity(self, activity_id: str) -> ActivityEvent | None:
        """Get a specific activity by ID."""
        with self._lock:
            return self._activities.get(activity_id)

    def clear(self) -> None:
        """Clear all tracked activities (e.g., on turn end)."""
        with self._lock:
            self._activities.clear()
