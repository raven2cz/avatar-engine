"""
WebSocket event bridge — mirrors CLI DisplayManager pattern.

Registers handlers on AvatarEngine's EventEmitter and broadcasts
JSON-serialized events to all connected WebSocket clients.

Architecture:
    Engine → EventEmitter → WebSocketBridge._on_* → JSON → WebSocket → React

This mirrors cli/display.py:DisplayManager but outputs JSON instead of Rich.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Set

from ..events import (
    ActivityEvent,
    AvatarEvent,
    DiagnosticEvent,
    EngineState,
    ErrorEvent,
    EventEmitter,
    StateEvent,
    ThinkingEvent,
    ToolEvent,
)
from ..types import BridgeState
from .protocol import event_to_dict

logger = logging.getLogger(__name__)


class WebSocketBridge:
    """Adapts AvatarEngine events to WebSocket JSON broadcast.

    Mirrors DisplayManager's event handler pattern but serializes
    to JSON for web clients instead of Rich terminal output.

    Usage:
        bridge = WebSocketBridge(engine)
        # When a WS connects:
        await bridge.add_client(websocket)
        # Events are automatically broadcast to all clients.
        # On disconnect:
        await bridge.remove_client(websocket)
    """

    def __init__(self, emitter: EventEmitter) -> None:
        self._emitter = emitter
        self._clients: Set[Any] = set()  # FastAPI WebSocket objects
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

        # Track engine state (mirrors DisplayManager._state)
        self._engine_state = EngineState.IDLE

        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register event handlers — same set as DisplayManager."""
        self._emitter.add_handler(ThinkingEvent, self._on_thinking)
        self._emitter.add_handler(ToolEvent, self._on_tool)
        self._emitter.add_handler(ActivityEvent, self._on_activity)
        self._emitter.add_handler(DiagnosticEvent, self._on_diagnostic)
        self._emitter.add_handler(ErrorEvent, self._on_error)
        self._emitter.add_handler(StateEvent, self._on_state)
        # TextEvent is forwarded directly (no state logic needed)
        from ..events import TextEvent, CostEvent
        self._emitter.add_handler(TextEvent, self._on_generic)
        self._emitter.add_handler(CostEvent, self._on_generic)

    def unregister(self) -> None:
        """Remove all handlers from the emitter."""
        from ..events import TextEvent, CostEvent
        self._emitter.remove_handler(ThinkingEvent, self._on_thinking)
        self._emitter.remove_handler(ToolEvent, self._on_tool)
        self._emitter.remove_handler(ActivityEvent, self._on_activity)
        self._emitter.remove_handler(DiagnosticEvent, self._on_diagnostic)
        self._emitter.remove_handler(ErrorEvent, self._on_error)
        self._emitter.remove_handler(StateEvent, self._on_state)
        self._emitter.remove_handler(TextEvent, self._on_generic)
        self._emitter.remove_handler(CostEvent, self._on_generic)

    # === Client management ===

    async def add_client(self, ws: Any) -> None:
        """Add a WebSocket client to the broadcast set."""
        async with self._lock:
            self._clients.add(ws)
        logger.info(f"WS client connected (total: {len(self._clients)})")

    async def remove_client(self, ws: Any) -> None:
        """Remove a WebSocket client."""
        async with self._lock:
            self._clients.discard(ws)
        logger.info(f"WS client disconnected (total: {len(self._clients)})")

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @property
    def engine_state(self) -> EngineState:
        return self._engine_state

    # === Event handlers (mirror DisplayManager) ===

    def _on_thinking(self, event: ThinkingEvent) -> None:
        """Mirror DisplayManager._on_thinking — track state + broadcast."""
        if event.is_complete:
            if self._engine_state == EngineState.THINKING:
                self._engine_state = EngineState.RESPONDING
        else:
            self._engine_state = EngineState.THINKING
        self._broadcast_event(event)
        self._broadcast_engine_state()

    def _on_tool(self, event: ToolEvent) -> None:
        """Mirror DisplayManager._on_tool — track state + broadcast."""
        if event.status == "started":
            self._engine_state = EngineState.TOOL_EXECUTING
        # Note: we don't track tool completion here because we don't have
        # ToolGroupDisplay's has_active. The client handles this logic.
        self._broadcast_event(event)
        self._broadcast_engine_state()

    def _on_activity(self, event: ActivityEvent) -> None:
        """Forward activity events."""
        self._broadcast_event(event)

    def _on_diagnostic(self, event: DiagnosticEvent) -> None:
        """Forward diagnostic events."""
        self._broadcast_event(event)

    def _on_error(self, event: ErrorEvent) -> None:
        """Mirror DisplayManager._on_error — set error state + broadcast."""
        self._engine_state = EngineState.ERROR
        self._broadcast_event(event)
        self._broadcast_engine_state()

    def _on_state(self, event: StateEvent) -> None:
        """Mirror DisplayManager._on_state — update engine state from bridge state."""
        if event.new_state == BridgeState.READY:
            self._engine_state = EngineState.IDLE
        elif event.new_state == BridgeState.ERROR:
            self._engine_state = EngineState.ERROR
        self._broadcast_event(event)
        self._broadcast_engine_state()

    def _on_generic(self, event: AvatarEvent) -> None:
        """Forward any event; promote to RESPONDING on first text chunk."""
        from ..events import TextEvent
        if isinstance(event, TextEvent) and self._engine_state != EngineState.RESPONDING:
            self._engine_state = EngineState.RESPONDING
            self._broadcast_engine_state()
        self._broadcast_event(event)

    # === Broadcast ===

    def _broadcast_event(self, event: AvatarEvent) -> None:
        """Serialize event and schedule broadcast to all clients."""
        msg = event_to_dict(event)
        if msg is None:
            return
        self._schedule_broadcast(msg)

    def _broadcast_engine_state(self) -> None:
        """Broadcast current engine state as a separate message."""
        self._schedule_broadcast({
            "type": "engine_state",
            "data": {"state": self._engine_state.value},
        })

    def broadcast_message(self, msg: Dict[str, Any]) -> None:
        """Public API: broadcast an arbitrary JSON message to all clients."""
        self._schedule_broadcast(msg)

    def _schedule_broadcast(self, msg: Dict[str, Any]) -> None:
        """Schedule an async broadcast from sync event handler context."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._async_broadcast(msg))
        except RuntimeError:
            # No running loop — try cached loop
            if self._loop and not self._loop.is_closed():
                self._loop.call_soon_threadsafe(
                    self._loop.create_task,
                    self._async_broadcast(msg),
                )

    async def _async_broadcast(self, msg: Dict[str, Any]) -> None:
        """Send message to all connected clients, removing dead ones."""
        dead: list = []
        async with self._lock:
            clients = list(self._clients)

        for ws in clients:
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)
            logger.debug(f"Removed {len(dead)} dead WS clients")

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Cache the event loop for cross-thread scheduling."""
        self._loop = loop
