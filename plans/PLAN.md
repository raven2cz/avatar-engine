# Avatar Engine — Library Architecture & Implementation Plan

> Created: 2026-02-05
> Status: Draft
> Version: 3.0

---

## 1. Executive Summary

**Avatar Engine je Python KNIHOVNA** pro integraci AI asistentů (Claude Code, Gemini CLI) do libovolných aplikací.

### Klíčové použití:
- **Synapse** a další vlastní projekty
- **Webové aplikace** s GUI
- **Avatar postavičky** (mluvící, animované)
- **Hlasové moduly** (TTS/STT integrace)
- **CLI** pouze pro testování a development

### Architektonické cíle:
1. **Čisté veřejné API** — jednoduchý import, intuitivní použití
2. **Event systém** — callbacks pro GUI (avatar mluví, tool execution, atd.)
3. **Async-first** — nativně async, sync wrappery pro jednoduchost
4. **Type hints** — plná typová podpora pro IDE a mypy
5. **Proper packaging** — pyproject.toml, pip installable
6. **Zero coupling** — library nezávisí na konkrétní aplikaci

---

## 2. Library Architecture

### 2.1 Package Structure

```
avatar-engine/
├── pyproject.toml              # Package definition
├── README.md
├── LICENSE                     # Apache 2.0
│
├── avatar_engine/              # Main package
│   ├── __init__.py             # Public API exports
│   ├── engine.py               # AvatarEngine class
│   ├── config.py               # Configuration handling
│   ├── events.py               # Event system
│   ├── types.py                # Type definitions
│   │
│   ├── bridges/                # Provider bridges
│   │   ├── __init__.py
│   │   ├── base.py             # BaseBridge ABC
│   │   ├── claude.py           # ClaudeBridge
│   │   └── gemini.py           # GeminiBridge
│   │
│   └── utils/                  # Utilities
│       ├── __init__.py
│       ├── retry.py            # Retry logic
│       └── health.py           # Health checks
│
├── tests/                      # Test suite
│   ├── __init__.py
│   ├── test_engine.py
│   ├── test_bridges.py
│   └── test_events.py
│
├── examples/                   # Usage examples
│   ├── basic_chat.py
│   ├── gui_integration.py
│   └── streaming_avatar.py
│
└── cli/                        # Optional CLI (separate)
    └── __main__.py
```

### 2.2 Public API Design

```python
# avatar_engine/__init__.py — čisté exporty

from .engine import AvatarEngine
from .types import (
    Message,
    BridgeResponse,
    BridgeState,
    ProviderType,
)
from .events import (
    EventEmitter,
    AvatarEvent,
    TextEvent,
    ToolEvent,
    StateEvent,
    ErrorEvent,
)
from .config import AvatarConfig

__version__ = "0.1.0"

__all__ = [
    "AvatarEngine",
    "AvatarConfig",
    "Message",
    "BridgeResponse",
    "BridgeState",
    "ProviderType",
    "EventEmitter",
    "AvatarEvent",
    "TextEvent",
    "ToolEvent",
    "StateEvent",
    "ErrorEvent",
]
```

### 2.3 Usage Examples

#### Základní použití (sync)
```python
from avatar_engine import AvatarEngine

# Jednoduchá inicializace
engine = AvatarEngine.from_config("config.yaml")
engine.start_sync()

# Chat
response = engine.chat_sync("Ahoj!")
print(response.content)

engine.stop_sync()
```

#### Async použití (pro GUI/web)
```python
import asyncio
from avatar_engine import AvatarEngine

async def main():
    engine = AvatarEngine(provider="gemini", model="gemini-3-pro-preview")
    await engine.start()

    # Streaming pro real-time display
    async for chunk in engine.chat_stream("Vysvětli quantum computing"):
        print(chunk, end="", flush=True)

    await engine.stop()

asyncio.run(main())
```

#### Event-driven GUI integration
```python
from avatar_engine import AvatarEngine, TextEvent, ToolEvent, StateEvent

engine = AvatarEngine.from_config("config.yaml")

# GUI callbacks
@engine.on(TextEvent)
def on_text(event: TextEvent):
    """Avatar mluví — update GUI, spusť TTS"""
    gui.update_speech_bubble(event.text)
    tts_engine.speak(event.text)

@engine.on(ToolEvent)
def on_tool(event: ToolEvent):
    """AI používá nástroj — ukázat v GUI"""
    gui.show_tool_usage(event.tool_name, event.status)

@engine.on(StateEvent)
def on_state(event: StateEvent):
    """Změna stavu — update status bar"""
    gui.set_status(event.new_state.value)

# Start a použití
engine.start_sync()
engine.chat_async("Analyzuj tento soubor", callback=lambda r: gui.show_result(r))
```

---

## 3. Event System Design

### 3.1 Event Types

```python
# avatar_engine/events.py

from abc import ABC
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar
import time

class EventType(Enum):
    TEXT = "text"           # Text chunk received
    TOOL_START = "tool_start"  # Tool execution started
    TOOL_END = "tool_end"      # Tool execution finished
    STATE_CHANGE = "state_change"  # Bridge state changed
    ERROR = "error"         # Error occurred
    THINKING = "thinking"   # Model is thinking (Gemini 3)
    COST = "cost"           # Cost/usage update


@dataclass
class AvatarEvent(ABC):
    """Base event class."""
    timestamp: float = field(default_factory=time.time)
    provider: str = ""


@dataclass
class TextEvent(AvatarEvent):
    """Text chunk received from AI."""
    text: str = ""
    is_complete: bool = False


@dataclass
class ToolEvent(AvatarEvent):
    """Tool execution event."""
    tool_name: str = ""
    tool_id: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    status: str = "started"  # started, completed, failed
    result: Optional[str] = None
    error: Optional[str] = None


@dataclass
class StateEvent(AvatarEvent):
    """Bridge state change event."""
    old_state: "BridgeState" = None
    new_state: "BridgeState" = None


@dataclass
class ThinkingEvent(AvatarEvent):
    """Model thinking event (Gemini 3 with include_thoughts=True)."""
    thought: str = ""


@dataclass
class ErrorEvent(AvatarEvent):
    """Error event."""
    error: str = ""
    recoverable: bool = True


@dataclass
class CostEvent(AvatarEvent):
    """Cost/usage update event."""
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
```

### 3.2 EventEmitter

```python
# avatar_engine/events.py (continued)

E = TypeVar("E", bound=AvatarEvent)

class EventEmitter:
    """Event emitter for Avatar Engine."""

    def __init__(self):
        self._handlers: Dict[Type[AvatarEvent], List[Callable]] = {}
        self._global_handlers: List[Callable] = []

    def on(self, event_type: Type[E]) -> Callable:
        """Decorator to register event handler."""
        def decorator(func: Callable[[E], None]) -> Callable[[E], None]:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(func)
            return func
        return decorator

    def on_any(self, func: Callable[[AvatarEvent], None]) -> Callable:
        """Register handler for all events."""
        self._global_handlers.append(func)
        return func

    def emit(self, event: AvatarEvent) -> None:
        """Emit an event to all registered handlers."""
        # Global handlers
        for handler in self._global_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler error: {e}")

        # Type-specific handlers
        event_type = type(event)
        if event_type in self._handlers:
            for handler in self._handlers[event_type]:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Event handler error: {e}")

    def remove_handler(self, event_type: Type[E], handler: Callable) -> None:
        """Remove a specific handler."""
        if event_type in self._handlers:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h != handler
            ]

    def clear_handlers(self, event_type: Optional[Type[E]] = None) -> None:
        """Clear handlers (all or for specific type)."""
        if event_type:
            self._handlers[event_type] = []
        else:
            self._handlers.clear()
            self._global_handlers.clear()
```

---

## 4. Type Definitions

```python
# avatar_engine/types.py

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import time


class ProviderType(Enum):
    GEMINI = "gemini"
    CLAUDE = "claude"


class BridgeState(Enum):
    DISCONNECTED = "disconnected"
    WARMING_UP = "warming_up"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"


@dataclass
class Message:
    """A conversation message."""
    role: str  # "user" | "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class BridgeResponse:
    """Response from AI bridge."""
    content: str
    success: bool = True
    error: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    raw_events: List[Dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0
    session_id: Optional[str] = None
    cost_usd: Optional[float] = None
    token_usage: Optional[Dict[str, Any]] = None

    def __bool__(self) -> bool:
        """Allow if response: checks."""
        return self.success


@dataclass
class HealthStatus:
    """Health check result."""
    healthy: bool
    state: str
    provider: str
    session_id: Optional[str] = None
    history_length: int = 0
    pid: Optional[int] = None
    returncode: Optional[int] = None
    total_cost_usd: float = 0.0
    uptime_seconds: float = 0.0
```

---

## 5. Refactored Engine Class

```python
# avatar_engine/engine.py

import asyncio
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, Optional, Union

from .types import BridgeResponse, BridgeState, HealthStatus, Message, ProviderType
from .events import (
    EventEmitter, AvatarEvent, TextEvent, ToolEvent,
    StateEvent, ErrorEvent, CostEvent
)
from .config import AvatarConfig
from .bridges.base import BaseBridge
from .bridges.claude import ClaudeBridge
from .bridges.gemini import GeminiBridge


class AvatarEngine(EventEmitter):
    """
    Avatar Engine — AI assistant integration library.

    Provides a unified interface to Claude Code and Gemini CLI
    with event-driven architecture for GUI integration.
    """

    def __init__(
        self,
        provider: Union[str, ProviderType] = ProviderType.GEMINI,
        model: Optional[str] = None,
        working_dir: Optional[str] = None,
        timeout: int = 120,
        system_prompt: str = "",
        **kwargs: Any,
    ):
        super().__init__()  # Initialize EventEmitter

        self._provider = ProviderType(provider) if isinstance(provider, str) else provider
        self._model = model
        self._working_dir = working_dir or str(Path.cwd())
        self._timeout = timeout
        self._system_prompt = system_prompt
        self._kwargs = kwargs

        self._bridge: Optional[BaseBridge] = None
        self._started = False
        self._start_time: Optional[float] = None

    @classmethod
    def from_config(cls, config_path: str) -> "AvatarEngine":
        """Create engine from YAML config file."""
        config = AvatarConfig.load(config_path)
        return cls(
            provider=config.provider,
            model=config.model,
            working_dir=config.working_dir,
            timeout=config.timeout,
            system_prompt=config.system_prompt,
            **config.provider_kwargs,
        )

    # === Lifecycle ===

    async def start(self) -> None:
        """Start the engine (async)."""
        if self._started:
            return

        self._bridge = self._create_bridge()
        self._setup_bridge_callbacks()

        await self._bridge.start()
        self._started = True
        self._start_time = time.time()

    def start_sync(self) -> None:
        """Start the engine (sync wrapper)."""
        asyncio.run(self.start())

    async def stop(self) -> None:
        """Stop the engine."""
        if self._bridge:
            await self._bridge.stop()
        self._started = False
        self._bridge = None

    def stop_sync(self) -> None:
        """Stop the engine (sync wrapper)."""
        asyncio.run(self.stop())

    # === Chat API ===

    async def chat(self, message: str) -> BridgeResponse:
        """Send a message and get response (async)."""
        if not self._started:
            await self.start()

        response = await self._bridge.send(message)

        # Emit cost event
        if response.cost_usd:
            self.emit(CostEvent(
                provider=self._provider.value,
                cost_usd=response.cost_usd,
                input_tokens=response.token_usage.get("input", 0) if response.token_usage else 0,
                output_tokens=response.token_usage.get("output", 0) if response.token_usage else 0,
            ))

        return response

    def chat_sync(self, message: str) -> BridgeResponse:
        """Send a message (sync wrapper)."""
        return asyncio.run(self.chat(message))

    async def chat_stream(self, message: str) -> AsyncIterator[str]:
        """Stream response chunks (async generator)."""
        if not self._started:
            await self.start()

        async for chunk in self._bridge.send_stream(message):
            # TextEvent is already emitted by bridge callback
            yield chunk

    def chat_async(
        self,
        message: str,
        callback: Callable[[BridgeResponse], None],
    ) -> asyncio.Task:
        """
        Send message asynchronously with callback (for GUI).

        Returns the Task so it can be cancelled if needed.
        """
        async def _run():
            response = await self.chat(message)
            callback(response)

        return asyncio.create_task(_run())

    # === Health ===

    def is_healthy(self) -> bool:
        """Quick health check."""
        return self._bridge is not None and self._bridge.is_healthy()

    def get_health(self) -> HealthStatus:
        """Detailed health status."""
        if not self._bridge:
            return HealthStatus(
                healthy=False,
                state="not_started",
                provider=self._provider.value,
            )

        health = self._bridge.check_health()
        health["uptime_seconds"] = time.time() - self._start_time if self._start_time else 0
        return HealthStatus(**health)

    # === History ===

    def get_history(self) -> list[Message]:
        """Get conversation history."""
        if self._bridge:
            return self._bridge.get_history()
        return []

    def clear_history(self) -> None:
        """Clear conversation history."""
        if self._bridge:
            self._bridge.clear_history()

    # === Internal ===

    def _create_bridge(self) -> BaseBridge:
        """Create the appropriate bridge for the provider."""
        if self._provider == ProviderType.CLAUDE:
            return ClaudeBridge(
                model=self._model or "claude-sonnet-4-5",
                working_dir=self._working_dir,
                timeout=self._timeout,
                system_prompt=self._system_prompt,
                **self._kwargs,
            )
        else:
            return GeminiBridge(
                model=self._model or "gemini-3-pro-preview",
                working_dir=self._working_dir,
                timeout=self._timeout,
                system_prompt=self._system_prompt,
                **self._kwargs,
            )

    def _setup_bridge_callbacks(self) -> None:
        """Connect bridge callbacks to event emitter."""
        self._bridge.on_output(lambda text: self.emit(TextEvent(
            provider=self._provider.value,
            text=text,
        )))

        self._bridge.on_state_change(lambda old, new: self.emit(StateEvent(
            provider=self._provider.value,
            old_state=old,
            new_state=new,
        )))

        self._bridge.on_event(self._handle_raw_event)

    def _handle_raw_event(self, event: Dict[str, Any]) -> None:
        """Process raw events from bridge and emit typed events."""
        event_type = event.get("type", "")

        # Tool events
        if event_type == "tool_use":
            self.emit(ToolEvent(
                provider=self._provider.value,
                tool_name=event.get("tool_name", event.get("name", "")),
                tool_id=event.get("tool_id", event.get("id", "")),
                parameters=event.get("parameters", event.get("input", {})),
                status="started",
            ))
        elif event_type == "tool_result":
            self.emit(ToolEvent(
                provider=self._provider.value,
                tool_name=event.get("tool_name", ""),
                tool_id=event.get("tool_id", ""),
                status="completed" if event.get("success", True) else "failed",
                result=event.get("result"),
                error=event.get("error"),
            ))
```

---

## 6. Implementation Tasks — Grouped

### Group A: Package Structure (Foundation)

| Task | Description | Priority | Effort |
|------|-------------|----------|--------|
| A1 | Create `pyproject.toml` | HIGH | 15 min |
| A2 | Reorganize into `avatar_engine/` package | HIGH | 30 min |
| A3 | Create proper `__init__.py` with exports | HIGH | 10 min |
| A4 | Create `types.py` with all dataclasses | HIGH | 20 min |
| A5 | Create `config.py` for YAML handling | MEDIUM | 15 min |

### Group B: Event System (Core Feature)

| Task | Description | Priority | Effort |
|------|-------------|----------|--------|
| B1 | Create `events.py` with EventEmitter | HIGH | 30 min |
| B2 | Add event types (Text, Tool, State, etc.) | HIGH | 20 min |
| B3 | Integrate events into Engine class | HIGH | 20 min |
| B4 | Integrate events into bridges | MEDIUM | 30 min |

### Group C0: KRITICKÉ TECHNICKÉ OPRAVY (musí být první!)

| Task | Soubor | Chyba | Oprava |
|------|--------|-------|--------|
| C0-1 | `gemini_bridge.py:450-482` | Chybí `model.name` v settings.json | Přidat `settings["model"] = {"name": self.model}` |
| C0-2 | `gemini_bridge.py:450-482` | Chybí `previewFeatures` | Přidat `settings["previewFeatures"] = True` |
| C0-3 | `gemini_bridge.py:450-482` | Chybí `topP`, `topK` | Přidat do `gen_cfg` |
| C0-4 | `gemini_bridge.py` | Temperature bez default | Default `1.0` (ne 0.7!) |
| C0-5 | `claude_bridge.py:164` | **Chybí `--include-partial-messages`** | **BEZ TOHOTO STREAMING NEFUNGUJE!** |
| C0-6 | `gemini_bridge.py:219-228` | Auth chyba ignorována | Správně ošetřit nebo selhat |

### Group C: Bridge Improvements (From Documentation Review)

| Task | Description | Priority | Effort |
|------|-------------|----------|--------|
| C1 | Add oneshot fallback to Claude bridge | HIGH | 20 min |
| C2 | Add health check methods | HIGH | 15 min |
| C3 | Add `--strict-mcp-config` to Claude | MEDIUM | 5 min |
| C4 | Add cost control (max_turns, max_budget) | MEDIUM | 10 min |
| C5 | Add stderr monitoring | MEDIUM | 20 min |
| C6 | Add retry logic | MEDIUM | 15 min |
| C7 | Add version check (informational) | LOW | 10 min |
| C8 | Add usage stats tracking | LOW | 10 min |
| C9 | Add `--json-schema` structured output support | MEDIUM | 15 min |
| C10 | Add `--continue` / `--resume` session support | MEDIUM | 15 min |
| C11 | Add `--fallback-model` for Claude overload | LOW | 5 min |
| C12 | Add `--debug` flag for troubleshooting | LOW | 5 min |

### Group D: Developer Experience

| Task | Description | Priority | Effort |
|------|-------------|----------|--------|
| D1 | Create CLI for testing (`cli/__main__.py`) | MEDIUM | 20 min |
| D2 | Add example scripts | LOW | 30 min |
| D3 | Write tests | MEDIUM | 60 min |
| D4 | Update documentation | LOW | 30 min |

---

## 7. Implementation Order

### Phase 1: Foundation (2h)
```
A1 → A2 → A3 → A4 → A5
pyproject.toml → reorganize → __init__.py → types.py → config.py
```

### Phase 2: Events (1.5h)
```
B1 → B2 → B3 → B4
EventEmitter → event types → engine integration → bridge integration
```

### Phase 3: KRITICKÉ TECHNICKÉ OPRAVY (30 min) ⚠️
```
C0-1 → C0-2 → C0-3 → C0-4 → C0-5 → C0-6
Gemini settings.json oprava → Claude --include-partial-messages → Auth handling
```
**MUSÍ BÝT PRVNÍ!** Bez těchto oprav streaming a Gemini 3 nebudou fungovat správně!

### Phase 4: Bridge Improvements (1h)
```
C1 → C2 → C3 → C4
oneshot fallback → health check → strict-mcp → cost control
```

### Phase 5: Additional Features (1h)
```
C5 → C6 → C9 → C10
stderr monitoring → retry → json-schema → session management
```

### Phase 6: Polish (1h)
```
C7 → C8 → C11 → C12 → D1
version check → usage stats → fallback-model → debug → CLI
```

### Phase 7: Documentation (1h)
```
D2 → D3 → D4
examples → tests → docs
```

**Celkem: ~9.5h práce**

> **DŮLEŽITÉ:** Phase 3 (Group C0) obsahuje kritické technické opravy!
> Bez nich Gemini 3 a Claude streaming nebudou fungovat správně.

---

## 8. pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "avatar-engine"
version = "0.1.0"
description = "AI assistant integration library for Claude Code and Gemini CLI"
readme = "README.md"
license = "Apache-2.0"
requires-python = ">=3.10"
authors = [
    { name = "Antonin Stefanutti", email = "your@email.cz" }
]
keywords = ["ai", "claude", "gemini", "assistant", "avatar"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: Apache Software License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Scientific/Engineering :: Artificial Intelligence",
]
dependencies = [
    "pyyaml>=6.0",
    "acp>=0.1.0",  # Gemini ACP SDK
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "mypy>=1.0",
    "ruff>=0.1",
]
cli = [
    "rich>=13.0",  # Pretty terminal output
]

[project.scripts]
avatar = "avatar_engine.cli:main"

[project.urls]
Homepage = "https://github.com/raven2cz/avatar-engine"
Repository = "https://github.com/raven2cz/avatar-engine"
Issues = "https://github.com/raven2cz/avatar-engine/issues"

[tool.hatch.build.targets.wheel]
packages = ["avatar_engine"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.mypy]
python_version = "3.10"
strict = true

[tool.ruff]
line-length = 100
target-version = "py310"
```

---

## 9. Config File Structure

### config.yaml (updated)
```yaml
# Avatar Engine Configuration

provider: "gemini"  # gemini | claude

# === Gemini Configuration ===
gemini:
  executable: "gemini"
  model: "gemini-3-pro-preview"
  timeout: 120
  approval_mode: "yolo"
  auth_method: "oauth-personal"
  acp_enabled: true
  preview_features: true  # NEW: May be required for Gemini 3
  debug: false            # NEW: Enable debug output

  generation_config:
    # IMPORTANT: Gemini 3 docs recommend temperature=1.0 (default)
    # Lower values may cause unexpected behavior on complex reasoning
    temperature: 1.0
    top_p: 0.95
    top_k: 64
    thinking_level: "high"
    include_thoughts: false
    max_output_tokens: 8192

  retry:
    max_attempts: 3
    backoff_base: 1.0

  mcp_servers:
    avatar-tools:
      command: "python"
      args: ["mcp_tools.py"]

# === Claude Configuration ===
claude:
  executable: "claude"
  model: "claude-sonnet-4-5"
  timeout: 120
  permission_mode: "acceptEdits"
  strict_mcp_config: true
  debug: false                    # NEW: Enable debug output
  fallback_model: "haiku"         # NEW: Fallback when overloaded

  cost_control:
    max_turns: 10
    max_budget_usd: 5.0

  session:                        # NEW: Session management
    continue_last: false          # Use --continue flag
    resume_id: ""                 # Use --resume with session ID

  structured_output:              # NEW: JSON schema support
    enabled: false
    schema: null                  # JSON schema for --json-schema

  allowed_tools:
    - "Read"
    - "Grep"
    - "Glob"
    - "mcp__avatar-tools__*"

  retry:
    max_attempts: 3
    backoff_base: 1.0

  mcp_servers:
    avatar-tools:
      command: "python"
      args: ["mcp_tools.py"]

# === Engine Settings ===
engine:
  working_dir: ""  # Empty = current directory
  system_prompt: ""
  max_history: 100
  auto_restart: true
  max_restarts: 3
  health_check_interval: 30

# === Logging ===
logging:
  level: "INFO"
  file: ""
```

---

## 10. Success Criteria

### Library Requirements
- [ ] Installable via `pip install .`
- [ ] Clean public API (`from avatar_engine import AvatarEngine`)
- [ ] Full type hints (mypy --strict passes)
- [ ] Both async and sync interfaces
- [ ] Event system working for GUI callbacks

### Functional Requirements
- [ ] Gemini ACP warm session working
- [ ] Claude stream-json bidirectional working
- [ ] Streaming shows real-time text
- [ ] Health checks detect dead processes
- [ ] Fallback works when primary mode fails

### Quality Requirements
- [ ] All tests pass
- [ ] No security vulnerabilities
- [ ] Documentation complete
- [ ] Examples work

---

## 11. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| CLI tools change API | HIGH | Version check, fallback modes |
| Process dies mid-session | HIGH | Oneshot fallback, health monitoring |
| GUI callback blocks event loop | MEDIUM | Document async requirements |
| OAuth token expiration | LOW | Detect and emit error event |

---

## Appendix A: Documentation Reference

- [Gemini CLI Configuration](docs/gemini-cli-configuration.md)
- [Gemini CLI Headless Mode](docs/gemini-cli-headless.md)
- [Gemini 3 Developer Guide](docs/gemini-3-developer-guide.md)
- [Gemini ACP Issues](docs/gemini-acp-issues-and-fixes.md)
- [Claude Code Headless](docs/claude-code-headless.md)
- [Claude Code CLI Reference](docs/claude-code-cli-reference.md)
- [ACP Python SDK](docs/acp-python-sdk.md)

---

## Appendix B: Code Review Findings — TECHNICKÉ CHYBY

### Gemini Bridge (`bridges/gemini_bridge.py`)

| Řádek | Chyba | Správně podle dokumentace |
|-------|-------|---------------------------|
| 450-482 | **Chybí `model.name`** v settings.json | `"model": {"name": "gemini-3-pro-preview"}` |
| 450-482 | **Chybí `previewFeatures: true`** | Požadováno pro Gemini 3! |
| 450-482 | **Chybí `topP`, `topK`** | `"topP": 0.95, "topK": 64` |
| 454 | **Temperature default chybí** | Gemini 3 docs: **1.0 je doporučeno**, ne 0.7! |
| 219-228 | **Ignoruje auth chybu** | Pokračuje i když `authenticate()` selže |
| 373-427 | **Callback vs async iterator** | SDK docs: `async for update in conn.session_updates()` |

**Správný `settings.json` podle dokumentace:**
```json
{
  "model": {"name": "gemini-3-pro-preview"},
  "previewFeatures": true,
  "modelConfigs": {
    "customAliases": {
      "gemini-3-pro-preview": {
        "modelConfig": {
          "generateContentConfig": {
            "temperature": 1.0,
            "topP": 0.95,
            "topK": 64,
            "thinkingConfig": {
              "thinkingLevel": "HIGH",
              "includeThoughts": false
            }
          }
        }
      }
    }
  }
}
```

### Claude Bridge (`bridges/claude_bridge.py`)

| Řádek | Chyba | Správně podle dokumentace |
|-------|-------|---------------------------|
| 164 | **Chybí `--include-partial-messages`** | **BEZ TOHOTO STREAMING NEFUNGUJE!** |
| 164 | Jen `--verbose` nestačí | Musí být `--verbose --include-partial-messages` |

**Správný command podle dokumentace:**
```bash
claude -p --input-format stream-json --output-format stream-json \
  --verbose --include-partial-messages --model claude-sonnet-4-5
```

### ACP SDK Použití

**Dokumentace (`acp-python-sdk.md`):**
```python
# Streaming přes async iterator (doporučeno):
async for update in conn.session_updates(session_id):
    if hasattr(update.content, "text"):
        print(update.content.text)
```

**Naše implementace (callback):**
```python
# Používáme callback session_update() na ACPClient
# Může fungovat, ale není to dokumentovaný způsob!
```

### Base Bridge Issues
1. No retry logic
2. stderr ignored
3. No aggregate cost tracking
4. Same timeout for init and send

---

## Appendix C: Kritické opravy (MUSÍ SE OPRAVIT)

### C-FIX-1: Gemini settings.json
```python
# _setup_config_files() musí generovat:
settings = {
    "model": {"name": self.model},
    "previewFeatures": True,
    "modelConfigs": {...}
}
```

### C-FIX-2: Claude --include-partial-messages
```python
# _build_persistent_command() musí obsahovat:
cmd.append("--verbose")
cmd.append("--include-partial-messages")  # KRITICKÉ!
```

### C-FIX-3: Temperature default
```python
# generation_config musí mít správný default:
if "temperature" not in self.generation_config:
    gen_cfg["temperature"] = 1.0  # Gemini 3 default!
```

> **POZNÁMKA:** GitHub issues je třeba ověřovat vlastním testováním!
> Naše implementace funguje, některé issues mohou být neplatné.
