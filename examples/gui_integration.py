#!/usr/bin/env python3
"""
GUI integration example — demonstrates event-driven architecture for GUI apps.

This example simulates a GUI application that:
- Shows real-time text as the AI responds
- Displays tool usage notifications
- Tracks state changes
- Monitors costs

Usage:
    python examples/gui_integration.py
"""

import asyncio
from dataclasses import dataclass, field
from typing import List

from avatar_engine import AvatarEngine
from avatar_engine.events import (
    TextEvent,
    ToolEvent,
    StateEvent,
    ErrorEvent,
    CostEvent,
    ThinkingEvent,
)


@dataclass
class MockGUI:
    """Simulated GUI for demonstration."""

    speech_bubble: str = ""
    status: str = "idle"
    tool_log: List[str] = field(default_factory=list)
    thinking_log: List[str] = field(default_factory=list)
    total_cost: float = 0.0

    def update_speech_bubble(self, text: str) -> None:
        """Update the avatar's speech bubble."""
        self.speech_bubble += text
        # In real GUI: self.speech_label.setText(self.speech_bubble)
        print(f"[SPEECH] {text}", end="", flush=True)

    def show_tool_usage(self, tool_name: str, status: str) -> None:
        """Show tool usage in GUI."""
        msg = f"{tool_name}: {status}"
        self.tool_log.append(msg)
        # In real GUI: self.tool_list.addItem(msg)
        print(f"\n[TOOL] {msg}")

    def set_status(self, status: str) -> None:
        """Update status bar."""
        self.status = status
        # In real GUI: self.status_bar.setText(status)
        print(f"\n[STATUS] {status}")

    def show_thinking(self, thought: str) -> None:
        """Show AI thinking (Gemini 3)."""
        preview = thought[:100] + "..." if len(thought) > 100 else thought
        self.thinking_log.append(preview)
        # In real GUI: self.thinking_panel.setText(thought)
        print(f"\n[THINKING] {preview}")

    def update_cost(self, cost: float) -> None:
        """Update cost display."""
        self.total_cost += cost
        # In real GUI: self.cost_label.setText(f"${self.total_cost:.4f}")
        print(f"\n[COST] +${cost:.4f} (total: ${self.total_cost:.4f})")

    def show_error(self, error: str, recoverable: bool) -> None:
        """Show error message."""
        level = "Warning" if recoverable else "Error"
        # In real GUI: QMessageBox.warning/critical(...)
        print(f"\n[{level.upper()}] {error}")


async def main() -> None:
    """Run GUI integration demo."""
    print("=== GUI Integration Example ===\n")

    # Create mock GUI
    gui = MockGUI()

    # Create engine
    engine = AvatarEngine(provider="gemini")

    # Register event handlers (this is how you'd connect to real GUI)
    @engine.on(TextEvent)
    def on_text(event: TextEvent) -> None:
        """Avatar speaks — update speech bubble."""
        gui.update_speech_bubble(event.text)

    @engine.on(ToolEvent)
    def on_tool(event: ToolEvent) -> None:
        """Tool execution — show in GUI."""
        gui.show_tool_usage(event.tool_name, event.status)

    @engine.on(StateEvent)
    def on_state(event: StateEvent) -> None:
        """State change — update status bar."""
        gui.set_status(event.new_state.value)

    @engine.on(ThinkingEvent)
    def on_thinking(event: ThinkingEvent) -> None:
        """AI thinking — show thinking panel."""
        gui.show_thinking(event.thought)

    @engine.on(CostEvent)
    def on_cost(event: CostEvent) -> None:
        """Cost update — update cost display."""
        gui.update_cost(event.cost_usd)

    @engine.on(ErrorEvent)
    def on_error(event: ErrorEvent) -> None:
        """Error — show message box."""
        gui.show_error(event.error, event.recoverable)

    # Start engine
    print("Starting engine...")
    await engine.start()
    print(f"Engine ready (session: {engine.session_id})\n")

    # Simulate user interaction
    print("User: Tell me a joke about programming.\n")
    print("Avatar: ", end="")

    # Stream response (events fire automatically)
    async for _ in engine.chat_stream("Tell me a short joke about programming."):
        pass  # Text is handled by event callback

    print("\n")

    # Show final stats
    print("\n=== Session Summary ===")
    print(f"Status: {gui.status}")
    print(f"Tools used: {len(gui.tool_log)}")
    print(f"Thinking events: {len(gui.thinking_log)}")
    print(f"Total cost: ${gui.total_cost:.4f}")

    # Cleanup
    await engine.stop()
    print("\nSession ended.")


if __name__ == "__main__":
    asyncio.run(main())
