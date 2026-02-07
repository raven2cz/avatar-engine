# Avatar Engine — Library Architecture & Implementation Plan

> Created: 2026-02-05
> Status: DONE
> Version: 3.0
> Closed: 2026-02-07

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
| C9 | Add `--json-schema` structured output support | MEDIUM | 15 min | WON'T DO |
| C10 | Add `--continue` / `--resume` session support | MEDIUM | 15 min | DONE (SESSION_MANAGEMENT_PLAN) |
| C11 | Add `--fallback-model` for Claude overload | LOW | 5 min | WON'T DO |
| C12 | Add `--debug` flag for troubleshooting | LOW | 5 min | WON'T DO |

### Group D: Developer Experience

| Task | Description | Priority | Effort |
|------|-------------|----------|--------|
| D1 | Create CLI for testing (`cli/__main__.py`) | MEDIUM | 2.5h |
| D2 | Add example scripts | LOW | 30 min |
| D3 | Write tests | MEDIUM | 60 min |
| D4 | Update documentation | LOW | 30 min |

### Group E: Production Features (Robustness & Observability)

| Task | Description | Priority | Effort |
|------|-------------|----------|--------|
| E1 | **ThinkingEvent emission** — Gemini bridge emituje ThinkingEvent při `include_thoughts=True` | HIGH | 30 min |
| E2 | **Auto-restart** — Engine automaticky restartuje bridge při pádu (configurable) | HIGH | 45 min |
| E3 | **Logging configuration** — Nastavení loggingu z YAML configu (level, file, format) | MEDIUM | 20 min |
| E4 | **Rate limiting** — Ochrana proti přetížení API (requests/min, configurable) | MEDIUM | 30 min |
| E5 | **Metrics export** — Prometheus/OpenTelemetry metriky pro monitoring | LOW | 45 min |
| E6 | **Graceful shutdown** — Čisté ukončení při SIGTERM/SIGINT | MEDIUM | 15 min |

#### E1: ThinkingEvent Details

```python
# V GeminiBridge._handle_acp_update():
if hasattr(update, "thinking") or "thinking" in str(update):
    self.emit(ThinkingEvent(
        provider="gemini",
        thought=extract_thinking(update),
    ))
```

#### E2: Auto-restart Details

```python
# V AvatarEngine:
class AvatarEngine:
    def __init__(self, ..., auto_restart: bool = True, max_restarts: int = 3):
        self._restart_count = 0

    async def _check_and_restart(self):
        """Periodicky kontroluje health a restartuje při problému."""
        if not self._bridge.is_healthy() and self._restart_count < self.max_restarts:
            logger.warning("Bridge unhealthy, restarting...")
            await self._bridge.stop()
            await self._bridge.start()
            self._restart_count += 1
```

#### E3: Logging Configuration

```yaml
# config.yaml
logging:
  level: "INFO"           # DEBUG, INFO, WARNING, ERROR
  file: "avatar.log"      # Optional log file
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  max_bytes: 10485760     # 10MB rotation
  backup_count: 3
```

#### E4: Rate Limiting

```python
# avatar_engine/utils/rate_limit.py
class RateLimiter:
    def __init__(self, requests_per_minute: int = 60):
        self._requests = []
        self._rpm = requests_per_minute

    async def acquire(self):
        """Wait if rate limit exceeded."""
        now = time.time()
        self._requests = [t for t in self._requests if now - t < 60]
        if len(self._requests) >= self._rpm:
            wait_time = 60 - (now - self._requests[0])
            await asyncio.sleep(wait_time)
        self._requests.append(time.time())
```

#### E5: Metrics Export

```python
# avatar_engine/utils/metrics.py
from prometheus_client import Counter, Histogram, Gauge

REQUESTS_TOTAL = Counter("avatar_requests_total", "Total requests", ["provider", "status"])
REQUEST_DURATION = Histogram("avatar_request_duration_seconds", "Request duration")
ACTIVE_SESSIONS = Gauge("avatar_active_sessions", "Active sessions", ["provider"])
COST_TOTAL = Counter("avatar_cost_usd_total", "Total cost in USD", ["provider"])
```

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

### Phase 8: Production Features (3h) 🚀
```
E1 → E2 → E6 → E3 → E4 → E5
ThinkingEvent → Auto-restart → Graceful shutdown → Logging → Rate limiting → Metrics
```

**Priority order:**
1. **E1 ThinkingEvent** — Gemini 3 thinking je důležitá feature
2. **E2 Auto-restart** — Kritické pro production stability
3. **E6 Graceful shutdown** — Nutné pro containerized deployments
4. **E3 Logging** — Debugging v production
5. **E4 Rate limiting** — Ochrana proti API limits
6. **E5 Metrics** — Nice to have pro monitoring

---

**Celkem: ~12.5h práce** (původně 9.5h + 3h production features)

> **DŮLEŽITÉ:** Phase 3 (Group C0) obsahuje kritické technické opravy!
> Bez nich Gemini 3 a Claude streaming nebudou fungovat správně.

> **POZNÁMKA:** Phase 8 (Group E) je pro production-ready deployment.
> Bez těchto features je library funkční, ale méně robustní.

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

# === Logging (E3) ===
logging:
  level: "INFO"                # DEBUG, INFO, WARNING, ERROR
  file: "avatar.log"           # Optional log file (empty = stdout only)
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  max_bytes: 10485760          # 10MB rotation
  backup_count: 3

# === Rate Limiting (E4) ===
rate_limit:
  enabled: true
  requests_per_minute: 60      # Max requests per minute
  burst: 10                    # Allow short bursts

# === Metrics (E5) ===
metrics:
  enabled: false
  type: "prometheus"           # prometheus | opentelemetry
  port: 9090                   # Prometheus metrics port
  endpoint: "/metrics"
```

---

## 10. Success Criteria

### Library Requirements
- [x] Installable via `pip install .`
- [x] Clean public API (`from avatar_engine import AvatarEngine`)
- [~] Full type hints (mypy --strict passes) — WON'T DO: not needed for current scope
- [x] Both async and sync interfaces
- [x] Event system working for GUI callbacks

### Functional Requirements
- [x] Gemini ACP warm session working
- [x] Claude stream-json bidirectional working
- [x] Streaming shows real-time text
- [x] Health checks detect dead processes
- [x] Fallback works when primary mode fails

### Quality Requirements
- [x] Core tests pass (184 tests)
- [x] Bridge tests pass (mocks required)
- [x] No security vulnerabilities
- [x] Documentation complete
- [x] Examples work

### Production Requirements (Group E)
- [x] ThinkingEvent emitted from Gemini bridge
- [x] Auto-restart on bridge failure
- [x] Graceful shutdown on SIGTERM/SIGINT
- [x] Configurable logging from YAML
- [x] Rate limiting protection
- [x] Prometheus/OpenTelemetry metrics (simple + optional)

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

---

## Appendix D: Gemini CLI Bug Report — customAliases breaks ACP

### Issue: ACP mode fails with "Internal error" when settings.json contains modelConfigs.customAliases

**Repository:** [google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli/issues)

**Status:** Not yet reported (to be filed)

---

### Title

```
ACP mode fails with "Internal error" when settings.json contains modelConfigs.customAliases
```

### Description

When using Gemini CLI in ACP (Agent Client Protocol) mode via `--experimental-acp`, the `prompt()` call fails with `RequestError: Internal error` if `.gemini/settings.json` contains a `modelConfigs.customAliases` section.

This prevents using `generateContentConfig` parameters (temperature, thinkingConfig, topP, topK) in ACP mode.

### Environment

- **Gemini CLI version:** 0.27.2
- **OS:** Linux / macOS / Windows
- **Python:** 3.10+
- **ACP SDK:** `agent-client-protocol>=0.6.0`

### Steps to Reproduce

1. Create `.gemini/settings.json` with `customAliases`:

```json
{
  "model": {"name": "gemini-3-pro-preview"},
  "previewFeatures": true,
  "modelConfigs": {
    "customAliases": {
      "gemini-3-pro-preview": {
        "modelConfig": {
          "generateContentConfig": {
            "temperature": 0.7
          }
        }
      }
    }
  }
}
```

2. Run Gemini CLI in ACP mode:

```python
from acp import spawn_agent_process, text_block

async with spawn_agent_process(client, "gemini", "--experimental-acp", "--yolo") as (conn, proc):
    await conn.initialize(protocol_version=1)
    await conn.authenticate(method_id="oauth-personal")
    session = await conn.new_session(cwd="/path/to/project")

    # This fails with "Internal error":
    result = await conn.prompt(
        session_id=session.session_id,
        prompt=[text_block("Hello")]
    )
```

3. Observe error:

```
acp.exceptions.RequestError: Internal error
```

### Expected Behavior

The `prompt()` call should succeed with the specified `generateContentConfig` parameters applied.

### Actual Behavior

The `prompt()` call fails with `RequestError: Internal error`.

### Workaround

Remove `modelConfigs.customAliases` from settings.json when using ACP mode:

```json
{
  "model": {"name": "gemini-3-pro-preview"},
  "previewFeatures": true
}
```

**Note:** This workaround prevents using custom generation parameters (temperature, thinkingLevel, etc.) in ACP mode.

### Additional Tests Performed

| Configuration | Result |
|--------------|--------|
| No `customAliases` | ✅ Works |
| Empty `customAliases: {}` | ❌ Internal error |
| Only `temperature` in customAliases | ❌ Internal error |
| `thinkingConfig` in customAliases | ❌ Internal error |
| Any `generateContentConfig` content | ❌ Internal error |

### Impact

- Cannot configure `temperature` in ACP mode
- Cannot configure `thinkingLevel` (HIGH/MEDIUM/LOW) in ACP mode
- Cannot configure `includeThoughts` in ACP mode
- Cannot configure `topP`, `topK`, `maxOutputTokens` in ACP mode

### Related Issues

- [#5373 - Hardcoded DEFAULT_GEMINI_MODEL overrides settings.json](https://github.com/google-gemini/gemini-cli/issues/5373)
- [#13543 - Additive model configs issue](https://github.com/google-gemini/gemini-cli/issues/13543)
- [#2831 (avante.nvim) - ACP fails with gemini-cli >= 0.14](https://github.com/yetone/avante.nvim/issues/2831)

### Labels

`bug`, `acp`, `configuration`

---

## Appendix E: Zero Footprint Configuration Architecture

> **Priorita:** PRIO 1 — Kritická změna pro knihovnu
> **Status:** Plán schválen, připraveno k implementaci

### E.1 Problém

Avatar Engine je **knihovna**, která se integruje do libovolné hostitelské aplikace.
Hostitelská aplikace **může mít vlastní**:

- `.gemini/settings.json` — konfigurace pro vývoj
- `GEMINI.md` — kontextové instrukce
- `.claude/settings.json` — Claude permissions
- `CLAUDE.md` — Claude kontextové instrukce
- `mcp_servers.json` — vlastní MCP servery

**Aktuální stav:** Avatar Engine tyto soubory **přepisuje** v `working_dir`, čímž ničí
konfiguraci hostitelské aplikace. Navíc po ukončení zanechává "smetí" v projektu.

### E.2 Cíl

**Zero Footprint** — avatar engine nezapíše žádný soubor do adresáře hostitelské
aplikace. Veškerá konfigurace se předá přes:

1. **Environment variables** (izolované na subprocess)
2. **CLI flags** (předané na příkazové řádce)
3. **ACP protokol** (MCP servery přes `newSession`)
4. **Temp soubory** (v systémovém `/tmp`, nikdy v projektu)

### E.3 Technické řešení

#### E.3.1 ConfigSandbox — třída pro správu temp souborů

```python
# avatar_engine/config_sandbox.py

import json
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional

class ConfigSandbox:
    """Isolated temp directory for avatar engine config files.

    Zero Footprint: no files are written to the host project directory.
    All config files live in /tmp/avatar-<session>/ and are cleaned up on exit.
    """

    def __init__(self, session_id: Optional[str] = None):
        self._session_id = session_id or uuid4().hex[:8]
        self._root = Path(tempfile.mkdtemp(prefix=f"avatar-{self._session_id}-"))

    @property
    def root(self) -> Path:
        return self._root

    # --- Gemini ---

    def write_gemini_settings(self, settings: Dict[str, Any]) -> Path:
        """Write settings.json for GEMINI_CLI_SYSTEM_SETTINGS_PATH."""
        path = self._root / "gemini-settings.json"
        path.write_text(json.dumps(settings, indent=2, ensure_ascii=False))
        return path

    def write_system_prompt(self, prompt: str) -> Path:
        """Write system prompt for GEMINI_SYSTEM_MD."""
        path = self._root / "system.md"
        path.write_text(prompt, encoding="utf-8")
        return path

    # --- Claude ---

    def write_mcp_config(self, servers: Dict[str, Any]) -> Path:
        """Write MCP config for Claude --mcp-config flag."""
        path = self._root / "mcp_servers.json"
        mcp_file = {"mcpServers": {}}
        for name, srv in servers.items():
            entry = {"command": srv["command"], "args": srv.get("args", [])}
            if "env" in srv:
                entry["env"] = srv["env"]
            mcp_file["mcpServers"][name] = entry
        path.write_text(json.dumps(mcp_file, indent=2, ensure_ascii=False))
        return path

    def write_claude_settings(self, settings: Dict[str, Any]) -> Path:
        """Write settings JSON for Claude --settings flag."""
        path = self._root / "claude-settings.json"
        path.write_text(json.dumps(settings, indent=2, ensure_ascii=False))
        return path

    def write_json_schema(self, schema: Dict[str, Any]) -> Path:
        """Write JSON schema for Claude --json-schema flag."""
        path = self._root / "schema.json"
        path.write_text(json.dumps(schema, indent=2))
        return path

    # --- Cleanup ---

    def cleanup(self):
        """Remove all temp files."""
        shutil.rmtree(self._root, ignore_errors=True)
```

#### E.3.2 Gemini Bridge — nový `_setup_config_files()` a `_start_acp()`

**Princip:** Env vars předané subprocesu, žádné soubory v projektu.

```python
def _setup_config_files(self) -> None:
    """Write config to sandbox (temp dir), NOT to working_dir.

    Zero Footprint: uses env vars to point Gemini CLI to temp config.
    """
    self._sandbox = ConfigSandbox()

    # Gemini settings (system-level = highest priority)
    settings: Dict[str, Any] = {}
    if self.model:
        settings["model"] = {"name": self.model}
    settings["previewFeatures"] = True

    # customAliases for oneshot mode only (ACP bug workaround)
    if not self.acp_enabled and (self.model or self.generation_config):
        gen_cfg = self._build_generation_config()
        if gen_cfg:
            settings["modelConfigs"] = {
                "customAliases": {
                    self.model: {
                        "modelConfig": {"generateContentConfig": gen_cfg}
                    }
                }
            }

    # MCP servers in settings (for oneshot mode)
    if not self.acp_enabled and self.mcp_servers:
        mcp = {}
        for name, srv in self.mcp_servers.items():
            mcp[name] = {"command": srv["command"], "args": srv.get("args", [])}
            if "env" in srv:
                mcp[name]["env"] = srv["env"]
        settings["mcpServers"] = mcp

    self._gemini_settings_path = self._sandbox.write_gemini_settings(settings)

    # System prompt
    if self.system_prompt:
        self._system_prompt_path = self._sandbox.write_system_prompt(
            self.system_prompt
        )
    else:
        self._system_prompt_path = None

def _build_env(self) -> Dict[str, str]:
    """Build subprocess environment with sandbox config paths."""
    env = {**os.environ, **self.env}

    # GEMINI_CLI_SYSTEM_SETTINGS_PATH = highest priority settings
    # Overrides workspace + user settings, but ONLY for avatar subprocess
    env["GEMINI_CLI_SYSTEM_SETTINGS_PATH"] = str(self._gemini_settings_path)

    # GEMINI_SYSTEM_MD = custom system prompt (replaces default)
    if self._system_prompt_path:
        env["GEMINI_SYSTEM_MD"] = str(self._system_prompt_path)

    return env
```

**ACP start — s env vars:**
```python
async def _start_acp(self) -> None:
    self._set_state(BridgeState.WARMING_UP)
    gemini_bin = shutil.which(self.executable)
    if not gemini_bin:
        raise FileNotFoundError(...)

    cmd_args = [gemini_bin, "--experimental-acp"]
    if self.approval_mode == "yolo":
        cmd_args.append("--yolo")

    env = self._build_env()  # <-- sandbox env vars

    self._acp_ctx = spawn_agent_process(
        client, *cmd_args,
        cwd=self.working_dir,  # Host project dir (for file access)
        env=env,               # Sandbox config paths
    )
    # ... authenticate, new_session(cwd=self.working_dir, mcpServers=...)
```

**Oneshot command — s env vars:**
```python
def _build_oneshot_command(self, prompt: str) -> List[str]:
    cmd = [self.executable]
    if self.model:
        cmd.extend(["--model", self.model])  # --model = highest priority
    if self.approval_mode == "yolo":
        cmd.append("--yolo")
    cmd.extend(["--output-format", "stream-json"])
    effective = self._build_effective_prompt(prompt)
    cmd.extend(["-p", effective])
    return cmd
    # Note: env vars (GEMINI_CLI_SYSTEM_SETTINGS_PATH, GEMINI_SYSTEM_MD)
    # are set in _build_env() and passed to create_subprocess_exec()
```

#### E.3.3 Claude Bridge — nový `_setup_config_files()` a `_build_persistent_command()`

**Princip:** Vše přes CLI flags, žádné soubory v projektu.

```python
def _setup_config_files(self) -> None:
    """Write config to sandbox. Zero Footprint — no files in working_dir."""
    self._sandbox = ConfigSandbox()

    # MCP servers → temp file for --mcp-config
    if self.mcp_servers:
        self._mcp_config_path = self._sandbox.write_mcp_config(self.mcp_servers)
    else:
        self._mcp_config_path = None

    # Settings → temp file for --settings
    settings: Dict[str, Any] = {}
    if self.allowed_tools:
        settings["permissions"] = {"allow": self.allowed_tools}
    self._claude_settings_path = self._sandbox.write_claude_settings(settings)

    # JSON schema → temp file for --json-schema
    if self.json_schema:
        self._schema_path = self._sandbox.write_json_schema(self.json_schema)
    else:
        self._schema_path = None

def _build_persistent_command(self) -> List[str]:
    cmd = [self.executable, "-p"]
    if self.model:
        cmd.extend(["--model", self.model])
    cmd.extend(["--input-format", "stream-json"])
    cmd.extend(["--output-format", "stream-json"])
    cmd.append("--verbose")
    cmd.append("--include-partial-messages")

    # Settings via --settings flag (NOT .claude/settings.json!)
    cmd.extend(["--settings", str(self._claude_settings_path)])

    # Permission mode
    if self.permission_mode:
        cmd.extend(["--permission-mode", self.permission_mode])

    # System prompt via CLI flag (NOT CLAUDE.md!)
    if self.system_prompt:
        cmd.extend(["--append-system-prompt", self.system_prompt])

    # MCP config from sandbox temp file
    if self._mcp_config_path:
        cmd.extend(["--mcp-config", str(self._mcp_config_path)])
        if self.strict_mcp_config:
            cmd.append("--strict-mcp-config")

    # Cost control, session management, schema, fallback...
    if self.max_turns:
        cmd.extend(["--max-turns", str(self.max_turns)])
    if self.continue_session:
        cmd.append("--continue")
    elif self.resume_session_id:
        cmd.extend(["--resume", self.resume_session_id])
    if self._schema_path:
        cmd.extend(["--json-schema", str(self._schema_path)])
    if self.fallback_model:
        cmd.extend(["--fallback-model", self.fallback_model])
    if self.debug:
        cmd.append("--debug")
    return cmd
```

**Klíčové změny:**
- `--settings <file>` nahrazuje zápis do `.claude/settings.json`
- `--append-system-prompt` nahrazuje zápis `CLAUDE.md`
- `--mcp-config` ukazuje na temp soubor (ne `working_dir/mcp_servers.json`)
- `--json-schema` ukazuje na temp soubor (ne `working_dir/.claude_schema.json`)
- Odstraněn duplicitní system prompt (dříve: CLAUDE.md + --append-system-prompt)

#### E.3.4 BaseBridge — cleanup v `stop()`

```python
async def stop(self) -> None:
    # ... existing process cleanup ...

    # Cleanup sandbox temp files
    if hasattr(self, '_sandbox') and self._sandbox:
        self._sandbox.cleanup()
        self._sandbox = None
```

### E.4 Přehled změn

| Mechanismus | Gemini (teď) | Gemini (nově) | Claude (teď) | Claude (nově) |
|-------------|-------------|---------------|--------------|---------------|
| Settings | `.gemini/settings.json` v projektu | `GEMINI_CLI_SYSTEM_SETTINGS_PATH` → temp | `.claude/settings.json` v projektu | `--settings` → temp |
| System prompt | `GEMINI.md` v projektu | `GEMINI_SYSTEM_MD` → temp | `CLAUDE.md` v projektu + `--append-system-prompt` (2x!) | `--append-system-prompt` pouze |
| MCP servers | `settings.json` v projektu | ACP protokol `newSession(mcpServers=)` / `settings.json` v temp | `mcp_servers.json` v projektu | `--mcp-config` → temp |
| Model | `settings.json` | `--model` flag | `--model` flag | `--model` flag (beze změny) |
| JSON schema | — | — | `.claude_schema.json` v projektu | `--json-schema` → temp |
| Souborů v projektu | **3** (.gemini/settings.json, GEMINI.md, MCP v settings) | **0** | **4** (.claude/settings.json, mcp_servers.json, CLAUDE.md, .claude_schema.json) | **0** |
| Cleanup | žádný | `sandbox.cleanup()` | žádný | `sandbox.cleanup()` |

### E.5 Unit testy

#### E.5.1 TestConfigSandbox

```python
class TestConfigSandbox:
    """Test ConfigSandbox temp file management."""

    def test_creates_temp_dir(self):
        sandbox = ConfigSandbox()
        assert sandbox.root.exists()
        assert sandbox.root.is_dir()
        assert "avatar-" in sandbox.root.name
        sandbox.cleanup()

    def test_cleanup_removes_all(self):
        sandbox = ConfigSandbox()
        root = sandbox.root
        sandbox.write_gemini_settings({"previewFeatures": True})
        sandbox.write_system_prompt("test")
        sandbox.cleanup()
        assert not root.exists()

    def test_write_gemini_settings(self):
        sandbox = ConfigSandbox()
        path = sandbox.write_gemini_settings({"model": {"name": "test"}, "previewFeatures": True})
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["model"]["name"] == "test"
        assert data["previewFeatures"] is True
        sandbox.cleanup()

    def test_write_system_prompt(self):
        sandbox = ConfigSandbox()
        path = sandbox.write_system_prompt("Jsi AI avatar.")
        assert path.exists()
        assert path.read_text() == "Jsi AI avatar."
        sandbox.cleanup()

    def test_write_mcp_config(self):
        sandbox = ConfigSandbox()
        servers = {"tools": {"command": "python", "args": ["mcp.py"], "env": {"K": "V"}}}
        path = sandbox.write_mcp_config(servers)
        data = json.loads(path.read_text())
        assert "mcpServers" in data
        assert data["mcpServers"]["tools"]["command"] == "python"
        assert data["mcpServers"]["tools"]["env"]["K"] == "V"
        sandbox.cleanup()

    def test_write_claude_settings(self):
        sandbox = ConfigSandbox()
        path = sandbox.write_claude_settings({"permissions": {"allow": ["Read"]}})
        data = json.loads(path.read_text())
        assert data["permissions"]["allow"] == ["Read"]
        sandbox.cleanup()

    def test_write_json_schema(self):
        sandbox = ConfigSandbox()
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        path = sandbox.write_json_schema(schema)
        data = json.loads(path.read_text())
        assert data["type"] == "object"
        sandbox.cleanup()

    def test_multiple_sandboxes_isolated(self):
        s1 = ConfigSandbox(session_id="aaa")
        s2 = ConfigSandbox(session_id="bbb")
        assert s1.root != s2.root
        s1.write_gemini_settings({"x": 1})
        s2.write_gemini_settings({"x": 2})
        assert json.loads((s1.root / "gemini-settings.json").read_text())["x"] == 1
        assert json.loads((s2.root / "gemini-settings.json").read_text())["x"] == 2
        s1.cleanup()
        s2.cleanup()
```

#### E.5.2 TestGeminiBridgeZeroFootprint

```python
class TestGeminiBridgeZeroFootprint:
    """Verify Gemini bridge writes ZERO files to working_dir."""

    def test_no_files_in_working_dir(self, tmp_path):
        """_setup_config_files must not create any files in working_dir."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=True,
            system_prompt="Test prompt",
            generation_config={"temperature": 0.7},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        # working_dir must be completely untouched
        assert not (tmp_path / ".gemini").exists()
        assert not (tmp_path / "GEMINI.md").exists()
        assert list(tmp_path.iterdir()) == []

    def test_sandbox_has_settings(self, tmp_path):
        """Sandbox must contain gemini-settings.json."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=True,
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        assert bridge._sandbox is not None
        settings_path = bridge._sandbox.root / "gemini-settings.json"
        assert settings_path.exists()
        data = json.loads(settings_path.read_text())
        assert data["model"]["name"] == "gemini-3-pro-preview"
        assert data["previewFeatures"] is True

    def test_sandbox_has_system_prompt(self, tmp_path):
        """Sandbox must contain system.md when system_prompt is set."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            system_prompt="Jsi avatar.",
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        prompt_path = bridge._sandbox.root / "system.md"
        assert prompt_path.exists()
        assert prompt_path.read_text() == "Jsi avatar."

    def test_env_has_system_settings_path(self, tmp_path):
        """_build_env must set GEMINI_CLI_SYSTEM_SETTINGS_PATH."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()
        env = bridge._build_env()

        assert "GEMINI_CLI_SYSTEM_SETTINGS_PATH" in env
        assert Path(env["GEMINI_CLI_SYSTEM_SETTINGS_PATH"]).exists()

    def test_env_has_system_md_when_prompt_set(self, tmp_path):
        """_build_env must set GEMINI_SYSTEM_MD when system_prompt is provided."""
        bridge = GeminiBridge(
            system_prompt="Hello",
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()
        env = bridge._build_env()

        assert "GEMINI_SYSTEM_MD" in env
        assert Path(env["GEMINI_SYSTEM_MD"]).exists()

    def test_env_no_system_md_when_no_prompt(self, tmp_path):
        """_build_env must NOT set GEMINI_SYSTEM_MD when no system_prompt."""
        bridge = GeminiBridge(working_dir=str(tmp_path))
        bridge._setup_config_files()
        env = bridge._build_env()

        assert "GEMINI_SYSTEM_MD" not in env

    def test_oneshot_settings_have_custom_aliases(self, tmp_path):
        """Oneshot mode sandbox settings must include customAliases."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=False,
            generation_config={"temperature": 0.5},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        data = json.loads(
            (bridge._sandbox.root / "gemini-settings.json").read_text()
        )
        assert "modelConfigs" in data
        assert "customAliases" in data["modelConfigs"]

    def test_acp_settings_no_custom_aliases(self, tmp_path):
        """ACP mode sandbox settings must NOT include customAliases."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=True,
            generation_config={"temperature": 0.5},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        data = json.loads(
            (bridge._sandbox.root / "gemini-settings.json").read_text()
        )
        assert "modelConfigs" not in data

    def test_oneshot_settings_have_mcp_servers(self, tmp_path):
        """Oneshot mode must include MCP servers in sandbox settings."""
        bridge = GeminiBridge(
            acp_enabled=False,
            mcp_servers={"tools": {"command": "python", "args": ["t.py"]}},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        data = json.loads(
            (bridge._sandbox.root / "gemini-settings.json").read_text()
        )
        assert "mcpServers" in data

    def test_acp_settings_no_mcp_servers(self, tmp_path):
        """ACP mode must NOT include MCP servers in settings (passed via protocol)."""
        bridge = GeminiBridge(
            acp_enabled=True,
            mcp_servers={"tools": {"command": "python", "args": ["t.py"]}},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        data = json.loads(
            (bridge._sandbox.root / "gemini-settings.json").read_text()
        )
        assert "mcpServers" not in data
```

#### E.5.3 TestClaudeBridgeZeroFootprint

```python
class TestClaudeBridgeZeroFootprint:
    """Verify Claude bridge writes ZERO files to working_dir."""

    def test_no_files_in_working_dir(self, tmp_path):
        """_setup_config_files must not create any files in working_dir."""
        bridge = ClaudeBridge(
            model="claude-sonnet-4-5",
            system_prompt="Test",
            allowed_tools=["Read", "Grep"],
            mcp_servers={"tools": {"command": "python", "args": ["t.py"]}},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        # working_dir must be completely untouched
        assert not (tmp_path / ".claude").exists()
        assert not (tmp_path / "CLAUDE.md").exists()
        assert not (tmp_path / "mcp_servers.json").exists()
        assert not (tmp_path / ".claude_schema.json").exists()
        assert list(tmp_path.iterdir()) == []

    def test_command_has_settings_flag(self, tmp_path):
        """Persistent command must use --settings flag."""
        bridge = ClaudeBridge(
            allowed_tools=["Read"],
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()
        cmd = bridge._build_persistent_command()

        assert "--settings" in cmd
        settings_idx = cmd.index("--settings")
        settings_path = cmd[settings_idx + 1]
        assert Path(settings_path).exists()
        assert str(tmp_path) not in settings_path  # not in working_dir!

    def test_command_has_mcp_config_in_sandbox(self, tmp_path):
        """--mcp-config must point to sandbox, not working_dir."""
        bridge = ClaudeBridge(
            mcp_servers={"tools": {"command": "python", "args": ["t.py"]}},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()
        cmd = bridge._build_persistent_command()

        assert "--mcp-config" in cmd
        mcp_idx = cmd.index("--mcp-config")
        mcp_path = cmd[mcp_idx + 1]
        assert str(tmp_path) not in mcp_path  # not in working_dir!

    def test_no_claude_md_written(self, tmp_path):
        """CLAUDE.md must NOT be written (--append-system-prompt used instead)."""
        bridge = ClaudeBridge(
            system_prompt="Test prompt",
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        assert not (tmp_path / "CLAUDE.md").exists()

    def test_command_has_append_system_prompt(self, tmp_path):
        """System prompt must be passed via --append-system-prompt flag."""
        bridge = ClaudeBridge(
            system_prompt="Jsi avatar.",
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()
        cmd = bridge._build_persistent_command()

        assert "--append-system-prompt" in cmd
        idx = cmd.index("--append-system-prompt")
        assert cmd[idx + 1] == "Jsi avatar."

    def test_json_schema_in_sandbox(self, tmp_path):
        """--json-schema must point to sandbox temp file."""
        bridge = ClaudeBridge(
            json_schema={"type": "object"},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()
        cmd = bridge._build_persistent_command()

        assert "--json-schema" in cmd
        idx = cmd.index("--json-schema")
        schema_path = cmd[idx + 1]
        assert str(tmp_path) not in schema_path  # not in working_dir!
```

### E.6 Integrační testy

Integrační testy ověřují skutečný běh s reálnými CLI nástroji.

#### E.6.1 TestGeminiZeroFootprintIntegration

```python
@pytest.mark.integration
class TestGeminiZeroFootprintIntegration:
    """Integration tests: Gemini bridge with zero footprint config.

    These tests verify that:
    1. No files are created in the host project directory
    2. Gemini CLI correctly reads config from env vars
    3. ACP and oneshot modes work with sandbox config
    """

    @pytest.fixture
    def host_project(self, tmp_path):
        """Simulate a host application with its own Gemini config."""
        # Host app has its own .gemini/settings.json
        gemini_dir = tmp_path / ".gemini"
        gemini_dir.mkdir()
        (gemini_dir / "settings.json").write_text(json.dumps({
            "model": {"name": "gemini-2-flash"},
            "previewFeatures": False,
        }))
        # Host app has its own GEMINI.md
        (tmp_path / "GEMINI.md").write_text("Host app instructions")
        # Host app has a .git dir (project root marker)
        (tmp_path / ".git").mkdir()
        return tmp_path

    @pytest.mark.asyncio
    async def test_host_files_untouched_after_acp_session(self, host_project):
        """Host app's config files must not be modified by avatar engine."""
        original_settings = (host_project / ".gemini" / "settings.json").read_text()
        original_gemini_md = (host_project / "GEMINI.md").read_text()

        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=True,
            system_prompt="Jsi avatar.",
            generation_config={"temperature": 0.5},
            working_dir=str(host_project),
        )

        try:
            await bridge.start()
            resp = await bridge.send("Řekni 'test'")
            assert resp.success
        finally:
            await bridge.stop()

        # Verify host files unchanged
        assert (host_project / ".gemini" / "settings.json").read_text() == original_settings
        assert (host_project / "GEMINI.md").read_text() == original_gemini_md

        # Verify no new files created in host project
        host_files = set(p.name for p in host_project.iterdir())
        assert "mcp_servers.json" not in host_files
        assert ".claude" not in host_files

    @pytest.mark.asyncio
    async def test_sandbox_cleaned_after_stop(self, host_project):
        """Sandbox temp dir must be cleaned up after bridge.stop()."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            working_dir=str(host_project),
        )
        bridge._setup_config_files()
        sandbox_root = bridge._sandbox.root
        assert sandbox_root.exists()

        await bridge.stop()
        assert not sandbox_root.exists()

    @pytest.mark.asyncio
    async def test_acp_uses_correct_model(self, host_project):
        """ACP must use avatar's model, not host's model."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",  # Avatar wants this
            acp_enabled=True,
            working_dir=str(host_project),  # Host has gemini-2-flash
        )

        try:
            await bridge.start()
            resp = await bridge.send("Jaký jsi model? Odpověz jedním slovem.")
            # Should be gemini-3-pro-preview, not gemini-2-flash
            assert "gemini-3" in resp.text.lower() or "pro" in resp.text.lower()
        finally:
            await bridge.stop()

    @pytest.mark.asyncio
    async def test_oneshot_uses_correct_model(self, host_project):
        """Oneshot must use avatar's model via --model flag."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=False,
            working_dir=str(host_project),
        )

        try:
            await bridge.start()
            resp = await bridge.send("Jaký jsi model? Odpověz jedním slovem.")
            assert resp.success
        finally:
            await bridge.stop()

    @pytest.mark.asyncio
    async def test_concurrent_avatars_isolated(self, tmp_path):
        """Two avatar instances must not interfere with each other."""
        project_a = tmp_path / "app_a"
        project_b = tmp_path / "app_b"
        project_a.mkdir()
        project_b.mkdir()

        bridge_a = GeminiBridge(
            model="gemini-3-pro-preview",
            system_prompt="Jsi Avatar A.",
            working_dir=str(project_a),
        )
        bridge_b = GeminiBridge(
            model="gemini-3-pro-preview",
            system_prompt="Jsi Avatar B.",
            working_dir=str(project_b),
        )

        bridge_a._setup_config_files()
        bridge_b._setup_config_files()

        # Sandboxes must be different
        assert bridge_a._sandbox.root != bridge_b._sandbox.root

        # No files in either project
        assert list(project_a.iterdir()) == []
        assert list(project_b.iterdir()) == []

        bridge_a._sandbox.cleanup()
        bridge_b._sandbox.cleanup()
```

#### E.6.2 TestClaudeZeroFootprintIntegration

```python
@pytest.mark.integration
class TestClaudeZeroFootprintIntegration:
    """Integration tests: Claude bridge with zero footprint config."""

    @pytest.fixture
    def host_project(self, tmp_path):
        """Simulate a host app with its own Claude config."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text(json.dumps({
            "permissions": {"allow": ["Bash(git:*)"]},
        }))
        (tmp_path / "CLAUDE.md").write_text("Host app Claude instructions")
        (tmp_path / ".git").mkdir()
        return tmp_path

    @pytest.mark.asyncio
    async def test_host_files_untouched_after_session(self, host_project):
        """Host app's Claude config must not be modified."""
        original_settings = (host_project / ".claude" / "settings.json").read_text()
        original_claude_md = (host_project / "CLAUDE.md").read_text()

        bridge = ClaudeBridge(
            model="claude-sonnet-4-5",
            system_prompt="Jsi avatar.",
            allowed_tools=["Read", "Grep"],
            working_dir=str(host_project),
        )

        try:
            await bridge.start()
            resp = await bridge.send("Řekni 'test'")
            assert resp.success
        finally:
            await bridge.stop()

        # Host files unchanged
        assert (host_project / ".claude" / "settings.json").read_text() == original_settings
        assert (host_project / "CLAUDE.md").read_text() == original_claude_md

        # No new files
        assert not (host_project / "mcp_servers.json").exists()
        assert not (host_project / ".claude_schema.json").exists()

    @pytest.mark.asyncio
    async def test_sandbox_cleaned_after_stop(self, host_project):
        """Sandbox must be cleaned after bridge.stop()."""
        bridge = ClaudeBridge(working_dir=str(host_project))
        bridge._setup_config_files()
        sandbox_root = bridge._sandbox.root
        assert sandbox_root.exists()

        await bridge.stop()
        assert not sandbox_root.exists()
```

### E.7 Migrační kroky (pořadí implementace)

1. **`config_sandbox.py`** — nová třída `ConfigSandbox` + unit testy
2. **`gemini.py`** — refaktor `_setup_config_files()`, nový `_build_env()`, úprava `_start_acp()` a oneshot env
3. **`claude.py`** — refaktor `_setup_config_files()` a `_build_persistent_command()`
4. **`base.py`** — cleanup sandboxu v `stop()`
5. **Aktualizace existujících testů** — `TestSettingsJsonConfig` přizpůsobit sandboxu
6. **Nové unit testy** — `TestConfigSandbox`, `TestGeminiBridgeZeroFootprint`, `TestClaudeBridgeZeroFootprint`
7. **Integrační testy** — `TestGeminiZeroFootprintIntegration`, `TestClaudeZeroFootprintIntegration`

### E.8 Rizika a omezení

| Riziko | Dopad | Mitigace |
|--------|-------|----------|
| `GEMINI_SYSTEM_MD` nahrazuje celý systémový prompt Gemini CLI | Ztráta default instructions (tool usage, safety) | Zvážit zda nezůstat u GEMINI.md v sandboxu nebo do promptu zahrnout klíčové instrukce |
| Host app má `customAliases` ve workspace settings → ACP crash | ACP spadne s "Internal error" | Nemůžeme ovlivnit — je to bug Gemini CLI, host app si musí opravit |
| `--settings` flag ve starší verzi Claude Code neexistuje | Claude bridge selže | Detekce verze + fallback na starý způsob (zápis .claude/settings.json) |
| Temp soubory přežijí crash (SIGKILL) | Drobné znečištění /tmp | OS čistí /tmp; prefix `avatar-` pro ruční identifikaci |
| ACP `newSession(cwd=X)` načte workspace settings z X | Host settings přebijí naše | `GEMINI_CLI_SYSTEM_SETTINGS_PATH` má **nejvyšší prioritu** (level 5) |

### E.9 Implementační stav

> **Status:** IMPLEMENTOVÁNO A OTESTOVÁNO
> **Datum:** 2026-02-06

#### Provedené změny

| Soubor | Změna |
|--------|-------|
| `avatar_engine/config_sandbox.py` | **NOVÝ** — třída `ConfigSandbox` pro správu temp souborů |
| `avatar_engine/bridges/gemini.py` | Refaktor `_setup_config_files()` → sandbox; nový `_build_subprocess_env()` s env vars |
| `avatar_engine/bridges/claude.py` | Refaktor `_setup_config_files()` → sandbox; `_build_persistent_command()` → `--settings` flag |
| `avatar_engine/bridges/base.py` | Nová metoda `_build_subprocess_env()`; sandbox cleanup v `stop()` |
| `tests/test_zero_footprint.py` | **NOVÝ** — 39 unit testů (ConfigSandbox, Gemini ZF, Claude ZF, lifecycle) |
| `tests/test_gemini_acp.py` | Aktualizace `TestSettingsJsonConfig` pro sandbox místo working_dir |
| `tests/test_bridges.py` | Aktualizace `test_command_with_allowed_tools` pro --settings flag |

#### Výsledky testů

```
tests/test_zero_footprint.py    39 passed
tests/test_gemini_acp.py        52 passed
tests/test_bridges.py           22 passed
---
CELKEM                         334 passed, 0 failed
```

#### Klíčové technické rozhodnutí

1. **`GEMINI_CLI_SYSTEM_SETTINGS_PATH`** (level 5 = nejvyšší priorita v Gemini CLI) → přebije workspace i user settings
2. **`GEMINI_SYSTEM_MD`** → custom systémový prompt bez zápisu GEMINI.md
3. **`--settings <file>`** pro Claude → nahrazuje `.claude/settings.json`
4. **`--mcp-config <temp_file>`** pro Claude → MCP config v temp adresáři
5. **`_build_subprocess_env()`** jako overridable metoda v BaseBridge → Gemini přidává env vars
6. Sandbox cleanup v `BaseBridge.stop()` → sdílený pro oba bridgy

---

## Plan Status: CLOSED (2026-02-07)

Všechny klíčové cíle plánu byly splněny:

| Oblast | Stav |
|--------|------|
| Group A: Package Structure | DONE |
| Group B: Event System | DONE |
| Group C0: Kritické opravy | DONE (ověřeno testováním — streaming funguje) |
| Group C: Bridge Improvements (C1-C8) | DONE |
| Group C9-C12 | WON'T DO — low priority, nepotřebné |
| Group D: Developer Experience (CLI, examples, tests, docs) | DONE |
| Group E: Production Features | DONE |
| Appendix E: Zero Footprint | DONE (implementováno + otestováno) |
| Session Management | DONE (viz SESSION_MANAGEMENT_PLAN.md) |
| Codex Provider | DONE (viz CODEX_INTEGRATION_PLAN.md) |
| mypy --strict | WON'T DO — mimo scope |

**Finální stav testů:** 561+ testů, all PASS.
