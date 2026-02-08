"""CLI display layer for REPL-safe status + event output."""

import threading
import time
from typing import Dict, List, Optional

from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from ..events import (
    ActivityEvent,
    ActivityStatus,
    DiagnosticEvent,
    EngineState,
    ErrorEvent,
    EventEmitter,
    StateEvent,
    ThinkingEvent,
    ThinkingPhase,
    ToolEvent,
)

# Status icons per activity/tool state
STATUS_ICONS = {
    ActivityStatus.PENDING: "\u23f3",     # hourglass
    ActivityStatus.RUNNING: "\u280b",     # braille spinner frame
    ActivityStatus.COMPLETED: "\u2713",   # checkmark
    ActivityStatus.FAILED: "\u2717",      # cross
    ActivityStatus.CANCELLED: "\u2298",   # circled slash
    "pending": "\u23f3",
    "running": "\u280b",
    "completed": "\u2713",
    "failed": "\u2717",
    "cancelled": "\u2298",
}

# Spinner frames for animated status
SPINNER_FRAMES = ["\u2801", "\u2809", "\u2819", "\u2838", "\u2830", "\u2826", "\u2807", "\u280f"]

# Phase display labels
PHASE_LABELS = {
    ThinkingPhase.GENERAL: "thinking",
    ThinkingPhase.ANALYZING: "analyzing",
    ThinkingPhase.PLANNING: "planning",
    ThinkingPhase.CODING: "coding",
    ThinkingPhase.REVIEWING: "reviewing",
    ThinkingPhase.TOOL_PLANNING: "preparing tools",
}

# Phase style colors
PHASE_STYLES = {
    ThinkingPhase.GENERAL: "cyan",
    ThinkingPhase.ANALYZING: "blue",
    ThinkingPhase.PLANNING: "magenta",
    ThinkingPhase.CODING: "green",
    ThinkingPhase.REVIEWING: "yellow",
    ThinkingPhase.TOOL_PLANNING: "yellow",
}


class ThinkingDisplay:
    """Tracks and formats the current thinking state for display.

    Thread-safe: all state mutations protected by lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._phase: ThinkingPhase = ThinkingPhase.GENERAL
        self._subject: str = ""
        self._started_at: float = 0.0
        self._spinner_idx: int = 0
        self._block_id: str = ""

    def start(self, event: ThinkingEvent) -> None:
        """Start or update thinking display from a ThinkingEvent."""
        with self._lock:
            if not self._active:
                self._active = True
                self._started_at = time.time()
                self._spinner_idx = 0
            self._phase = event.phase
            if event.subject:
                self._subject = event.subject
            if event.block_id:
                self._block_id = event.block_id

    def stop(self) -> None:
        """Stop the thinking display."""
        with self._lock:
            self._active = False
            self._subject = ""
            self._block_id = ""

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    def render(self) -> Optional[Text]:
        """Render current thinking state as Rich Text (or None if inactive)."""
        with self._lock:
            if not self._active:
                return None
            # Advance spinner
            self._spinner_idx = (self._spinner_idx + 1) % len(SPINNER_FRAMES)
            frame = SPINNER_FRAMES[self._spinner_idx]
            elapsed = time.time() - self._started_at
            phase_label = PHASE_LABELS.get(self._phase, "thinking")
            style = PHASE_STYLES.get(self._phase, "cyan")

        text = Text()
        text.append(f"{frame} ", style="bold " + style)
        if self._subject:
            text.append(self._subject, style=style)
        else:
            text.append(phase_label.capitalize(), style=style)
        text.append(f" ({elapsed:.0f}s)", style="dim")
        return text

    def render_plain(self, frame_index: int) -> str:
        """Render current thinking status as plain text."""
        with self._lock:
            if not self._active:
                return ""
            frame = SPINNER_FRAMES[frame_index % len(SPINNER_FRAMES)]
            elapsed = time.time() - self._started_at
            phase_label = PHASE_LABELS.get(self._phase, "thinking")
            subject = self._subject or phase_label.capitalize()
        return f"{frame} {subject} ({elapsed:.0f}s)"

    def render_verbose(self, thought: str) -> Text:
        """Render verbose thinking with full thought text."""
        style = PHASE_STYLES.get(self._phase, "cyan")
        text = Text()
        text.append("\U0001f4ad ", style=style)  # thought balloon
        if self._subject:
            text.append(f"**{self._subject}**\n", style="bold " + style)
        text.append(f"   {thought}", style="dim italic")
        return text


class ToolGroupDisplay:
    """Tracks and formats concurrent tool executions.

    Thread-safe: all state mutations protected by lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tools: Dict[str, _ToolEntry] = {}
        self._order: List[str] = []  # insertion order

    def tool_started(self, event: ToolEvent) -> None:
        """Register a tool as started."""
        with self._lock:
            tid = event.tool_id or event.tool_name
            self._tools[tid] = _ToolEntry(
                tool_id=tid,
                name=event.tool_name,
                status="running",
                started_at=time.time(),
                params=_summarize_params(event.parameters),
            )
            if tid not in self._order:
                self._order.append(tid)

    def tool_completed(self, event: ToolEvent) -> None:
        """Mark a tool as completed or failed."""
        with self._lock:
            tid = event.tool_id or event.tool_name
            entry = self._tools.get(tid)
            if entry:
                entry.status = event.status  # "completed" or "failed"
                entry.completed_at = time.time()
                if event.error:
                    entry.error = event.error

    def clear_completed(self) -> None:
        """Remove all completed/failed tools from tracking."""
        with self._lock:
            done = [tid for tid, e in self._tools.items()
                    if e.status in ("completed", "failed", "cancelled")]
            for tid in done:
                del self._tools[tid]
                if tid in self._order:
                    self._order.remove(tid)

    @property
    def has_active(self) -> bool:
        with self._lock:
            return any(e.status == "running" for e in self._tools.values())

    @property
    def tool_count(self) -> int:
        with self._lock:
            return len(self._tools)

    def render(self) -> Optional[Panel]:
        """Render tool group as a Rich Panel (or None if empty)."""
        with self._lock:
            if not self._tools:
                return None
            lines = []
            for tid in self._order:
                entry = self._tools.get(tid)
                if not entry:
                    continue
                lines.append(entry.render_line())

        if not lines:
            return None

        content = Group(*lines)
        return Panel(
            content,
            title="Tools",
            title_align="left",
            border_style="dim",
            padding=(0, 1),
        )

    def render_inline(self) -> Optional[Text]:
        """Render a compact one-line summary of active tools."""
        with self._lock:
            active = [e for e in self._tools.values() if e.status == "running"]
            completed = sum(1 for e in self._tools.values() if e.status == "completed")
            total = len(self._tools)

        if total == 0:
            return None

        text = Text()
        text.append(f"[{completed}/{total}] ", style="bold")
        names = ", ".join(e.name for e in active[:3])
        if len(active) > 3:
            names += f" +{len(active) - 3}"
        text.append(names, style="yellow")
        return text


class _ToolEntry:
    """Internal tracking entry for a single tool execution."""

    __slots__ = ("tool_id", "name", "status", "started_at", "completed_at", "params", "error")

    def __init__(
        self,
        tool_id: str,
        name: str,
        status: str,
        started_at: float,
        params: str = "",
        error: str = "",
    ) -> None:
        self.tool_id = tool_id
        self.name = name
        self.status = status
        self.started_at = started_at
        self.completed_at: float = 0.0
        self.params = params
        self.error = error

    def render_line(self) -> Text:
        """Render this tool entry as a single Rich Text line."""
        icon = STATUS_ICONS.get(self.status, "?")
        text = Text()

        if self.status == "running":
            text.append(f"{icon} ", style="bold yellow")
            text.append(self.name, style="yellow")
            if self.params:
                text.append(f": {self.params}", style="dim")
        elif self.status == "completed":
            elapsed = self.completed_at - self.started_at
            text.append(f"{icon} ", style="bold green")
            text.append(self.name, style="green")
            text.append(f" ({elapsed:.1f}s)", style="dim")
        elif self.status == "failed":
            text.append(f"{icon} ", style="bold red")
            text.append(self.name, style="red")
            if self.error:
                text.append(f": {self.error[:60]}", style="dim red")
        else:
            text.append(f"{icon} ", style="dim")
            text.append(self.name, style="dim")

        return text


class DisplayManager:
    """Manages CLI display by listening to engine events."""

    def __init__(
        self,
        emitter: EventEmitter,
        console: Optional[Console] = None,
        verbose: bool = False,
    ) -> None:
        self._emitter = emitter
        self._console = console or Console()
        self._verbose = verbose

        # Display sub-components
        self.thinking = ThinkingDisplay()
        self.tools = ToolGroupDisplay()

        # Engine state tracking
        self._state = EngineState.IDLE
        self._state_lock = threading.Lock()

        # Spinner/status line state for REPL-safe output
        self._status_lock = threading.Lock()
        self._status_active = False
        self._status_width = 0
        self._frame_index = 0

        # Register event handlers
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register event handlers on the emitter."""
        self._emitter.add_handler(ThinkingEvent, self._on_thinking)
        self._emitter.add_handler(ToolEvent, self._on_tool)
        self._emitter.add_handler(ActivityEvent, self._on_activity)
        self._emitter.add_handler(DiagnosticEvent, self._on_diagnostic)
        self._emitter.add_handler(ErrorEvent, self._on_error)
        self._emitter.add_handler(StateEvent, self._on_state)

    def unregister(self) -> None:
        """Remove all handlers from the emitter."""
        self._emitter.remove_handler(ThinkingEvent, self._on_thinking)
        self._emitter.remove_handler(ToolEvent, self._on_tool)
        self._emitter.remove_handler(ActivityEvent, self._on_activity)
        self._emitter.remove_handler(DiagnosticEvent, self._on_diagnostic)
        self._emitter.remove_handler(ErrorEvent, self._on_error)
        self._emitter.remove_handler(StateEvent, self._on_state)

    # === State ===

    @property
    def state(self) -> EngineState:
        with self._state_lock:
            return self._state

    def _set_state(self, new_state: EngineState) -> None:
        with self._state_lock:
            self._state = new_state

    # === Event Handlers ===

    def _on_thinking(self, event: ThinkingEvent) -> None:
        """Handle thinking events — update spinner display."""
        if event.is_complete:
            self.thinking.stop()
            # Transition to responding if not already in a more active state
            with self._state_lock:
                if self._state == EngineState.THINKING:
                    self._state = EngineState.RESPONDING
            self.clear_status()
            return

        self.thinking.start(event)
        self._set_state(EngineState.THINKING)

        if self._verbose and event.thought:
            rendered = self.thinking.render_verbose(event.thought)
            self._console.print(rendered)

    def _on_tool(self, event: ToolEvent) -> None:
        """Handle tool events — update tool group display."""
        # Tool lines are permanent; clear transient spinner first.
        self.clear_status()

        if event.status == "started":
            self.tools.tool_started(event)
            self._set_state(EngineState.TOOL_EXECUTING)
        elif event.status in ("completed", "failed"):
            self.tools.tool_completed(event)

            # If this was the last tool, transition state
            if not self.tools.has_active:
                with self._state_lock:
                    if self._state == EngineState.TOOL_EXECUTING:
                        self._state = EngineState.RESPONDING

        self._print_tool_event(event)

    def _on_activity(self, event: ActivityEvent) -> None:
        """Handle activity events — update tool/activity tracking."""
        # We use ToolGroupDisplay to track activities too for now
        if event.status == ActivityStatus.RUNNING:
            self.tools.tool_started(ToolEvent(
                tool_name=event.name,
                tool_id=event.activity_id,
                status="started"
            ))
            self._set_state(EngineState.TOOL_EXECUTING)
        elif event.status in (ActivityStatus.COMPLETED, ActivityStatus.FAILED, ActivityStatus.CANCELLED):
            status_map = {
                ActivityStatus.COMPLETED: "completed",
                ActivityStatus.FAILED: "failed",
                ActivityStatus.CANCELLED: "cancelled"
            }
            self.tools.tool_completed(ToolEvent(
                tool_name=event.name,
                tool_id=event.activity_id,
                status=status_map[event.status],
                error=event.detail if event.status == ActivityStatus.FAILED else None
            ))
            if not self.tools.has_active:
                with self._state_lock:
                    if self._state == EngineState.TOOL_EXECUTING:
                        self._state = EngineState.RESPONDING

    def _on_diagnostic(self, event: DiagnosticEvent) -> None:
        """Handle diagnostic events."""
        if self._verbose or event.level in ("warning", "error"):
            self.clear_status()
            style = "yellow" if event.level == "warning" else ("red" if event.level == "error" else "dim")
            prefix = "! " if event.level == "warning" else ("x " if event.level == "error" else "  ")
            self._console.print(f"[dim]{event.source}:[/dim] [{style}]{prefix}{event.message}[/{style}]")

    def _on_error(self, event: ErrorEvent) -> None:
        """Handle error events."""
        self._set_state(EngineState.ERROR)
        self.clear_status()
        self._console.print(
            Text.assemble(
                ("\u2717 ", "bold red"),
                ("Error: ", "red"),
                (event.error, ""),
            )
        )

    def _on_state(self, event: StateEvent) -> None:
        """Handle bridge state changes."""
        from ..types import BridgeState
        if event.new_state == BridgeState.READY:
            self._set_state(EngineState.IDLE)
        elif event.new_state == BridgeState.ERROR:
            self._set_state(EngineState.ERROR)

    # === Direct Print Helpers ===

    @property
    def has_active_status(self) -> bool:
        with self._status_lock:
            return self._status_active

    def advance_spinner(self) -> None:
        """Render one colored spinner frame for current state.

        Shows thinking subject, tool progress, or generic generating status.
        """
        if self._verbose:
            return

        rich_text = self.render_status_line()
        self._frame_index += 1

        if rich_text:
            self._write_status_rich(rich_text)

    def clear_status(self) -> None:
        """Clear transient spinner/status line and restore cursor."""
        with self._status_lock:
            if not self._status_active:
                return
            f = self._console.file
            clear = "\r" + (" " * self._status_width) + "\r"
            f.write(clear)
            f.write("\033[?25h")  # Restore cursor visibility
            f.flush()
            self._status_active = False
            self._status_width = 0

    def _write_status_rich(self, text: Text) -> None:
        """Write a colored transient status line (overwritten on next call).

        Uses console.file.write for \\r cursor control and console.print
        for Rich-formatted colored output — avoids capture() ANSI issues.
        Hides cursor during spinner to prevent blinking.
        """
        with self._status_lock:
            visible_width = len(text.plain)
            if self._status_active and self._status_width > visible_width:
                pad = " " * (self._status_width - visible_width)
            else:
                pad = ""
            f = self._console.file
            # Hide cursor + \r to column 0, Rich prints colored text, pad clears leftovers
            if not self._status_active:
                f.write("\033[?25l")  # Hide cursor on first spinner frame
            f.write("\r")
            self._console.print(text, end="", highlight=False)
            if pad:
                f.write(pad)
            f.flush()
            self._status_active = True
            self._status_width = max(visible_width, self._status_width)

    def _print_tool_event(self, event: ToolEvent) -> None:
        """Print a tool event in non-live mode."""
        if event.status == "started":
            icon = STATUS_ICONS["running"]
            text = Text()
            text.append(f"  {icon} ", style="bold yellow")
            text.append(event.tool_name, style="yellow")
            params = _summarize_params(event.parameters)
            if params:
                text.append(f": {params}", style="dim")
            self._console.print(text)
        elif event.status == "completed":
            icon = STATUS_ICONS["completed"]
            self._console.print(
                Text.assemble(
                    (f"  {icon} ", "bold green"),
                    (event.tool_name, "green"),
                )
            )
        elif event.status == "failed":
            icon = STATUS_ICONS["failed"]
            self._console.print(
                Text.assemble(
                    (f"  {icon} ", "bold red"),
                    (event.tool_name, "red"),
                    (f": {event.error or 'failed'}", "dim red") if event.error else ("", ""),
                )
            )

    # === Rendering Helpers ===

    def render_status_line(self) -> Text:
        """Render a status line showing current engine state."""
        state = self.state
        text = Text()

        if state == EngineState.IDLE:
            text.append("> ", style="bold blue")
        elif state == EngineState.THINKING:
            thinking = self.thinking.render()
            if thinking:
                return thinking
            text.append("\u280b thinking...", style="cyan")
        elif state == EngineState.RESPONDING:
            text.append("\u280b Generating...", style="green")
        elif state == EngineState.TOOL_EXECUTING:
            inline = self.tools.render_inline()
            if inline:
                text.append("\u280b ", style="bold yellow")
                text.append_text(inline)
            else:
                text.append("\u280b Executing tools...", style="yellow")
        elif state == EngineState.WAITING_APPROVAL:
            text.append("? Waiting for approval...", style="bold magenta")
        elif state == EngineState.ERROR:
            text.append("\u2717 Error", style="bold red")

        return text

    def on_response_start(self) -> None:
        """Call when a response stream starts (after user sends message)."""
        self.clear_status()
        self._frame_index = 0
        self._set_state(EngineState.THINKING)

    def on_response_end(self) -> None:
        """Call when a response is complete."""
        self.clear_status()
        self.thinking.stop()
        self.tools.clear_completed()
        self._set_state(EngineState.IDLE)


def _summarize_params(params: Dict) -> str:
    """Create a short summary of tool parameters for display."""
    if not params:
        return ""
    # Common patterns: file paths, search queries, commands
    for key in ("file_path", "path", "filename", "command", "query", "pattern", "url"):
        if key in params:
            val = str(params[key])
            if len(val) > 60:
                val = val[:57] + "..."
            return val
    # Fallback: first string value
    for val in params.values():
        if isinstance(val, str) and val:
            if len(val) > 60:
                val = val[:57] + "..."
            return val
    return ""
