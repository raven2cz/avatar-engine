"""
Avatar Engine — application-specific AI avatar runtime.

A Python library for embedding configurable AI avatars into applications.
Applications provide behavior configuration, domain context, and source data.
The avatar can orchestrate MCP tools for complex analysis and larger edits.
Claude Code, Gemini CLI, and Codex CLI are supported as provider backends.

Basic Usage:
    from avatar_engine import AvatarEngine

    engine = AvatarEngine(provider="gemini")
    engine.start_sync()
    response = engine.chat_sync("Hello!")
    print(response.content)
    engine.stop_sync()

Event-Driven Usage:
    from avatar_engine import AvatarEngine, TextEvent

    engine = AvatarEngine.from_config("config.yaml")

    @engine.on(TextEvent)
    def on_text(event):
        print(event.text, end="", flush=True)

    engine.start_sync()
    engine.chat_sync("Tell me a story")
    engine.stop_sync()

Async Usage:
    import asyncio
    from avatar_engine import AvatarEngine

    async def main():
        engine = AvatarEngine(provider="claude")
        await engine.start()

        async for chunk in engine.chat_stream("Explain Python"):
            print(chunk, end="", flush=True)

        await engine.stop()

    asyncio.run(main())
"""

__version__ = "0.1.0"

# Main engine class
from .engine import AvatarEngine

# Configuration
from .config import AvatarConfig

# Type definitions
from .types import (
    BridgeResponse,
    BridgeState,
    HealthStatus,
    Message,
    ProviderType,
)

# Event system
from .events import (
    AvatarEvent,
    CostEvent,
    ErrorEvent,
    EventEmitter,
    EventType,
    StateEvent,
    TextEvent,
    ThinkingEvent,
    ToolEvent,
)

# Bridge classes (for advanced usage)
from .bridges import (
    BaseBridge,
    ClaudeBridge,
    CodexBridge,
    GeminiBridge,
)

__all__ = [
    # Version
    "__version__",
    # Main class
    "AvatarEngine",
    # Configuration
    "AvatarConfig",
    # Types
    "BridgeResponse",
    "BridgeState",
    "HealthStatus",
    "Message",
    "ProviderType",
    # Events
    "AvatarEvent",
    "CostEvent",
    "ErrorEvent",
    "EventEmitter",
    "EventType",
    "StateEvent",
    "TextEvent",
    "ThinkingEvent",
    "ToolEvent",
    # Bridges
    "BaseBridge",
    "ClaudeBridge",
    "CodexBridge",
    "GeminiBridge",
]
