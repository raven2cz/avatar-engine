<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/banner.svg">
    <source media="(prefers-color-scheme: light)" srcset="assets/banner-light.svg">
    <img alt="Avatar Engine" src="assets/banner.svg" width="840">
  </picture>
</p>

<p align="center">
  <strong>Python library for building application-specific AI avatars with configurable behavior, context-aware reasoning, and MCP-powered task execution.</strong>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-green.svg" alt="License: Apache 2.0"></a>
</p>

## Project Intent

Avatar Engine is designed for embedding a dedicated AI avatar into a specific application domain, not as a generic chatbot wrapper.

- **Application-defined behavior** — Your app controls avatar behavior through explicit configuration (model, prompts, permissions, tool policy, safety limits).
- **Application-provided context** — Your app supplies domain context and source data so the avatar can reason over real project information.
- **MCP for complex operations** — For tasks that are hard to encode as deterministic algorithms, the avatar can call MCP tools to inspect data, run analyses, and assist with larger changes.
- **Provider abstraction as infrastructure** — Gemini CLI, Claude Code, and Codex CLI support is an implementation layer that enables the avatar runtime, not the product goal itself.

## Features

- **Avatar Runtime API** — Stable interface for embedding a domain-specific avatar into your app
- **Configurable Behavior** — Fine-grained control of model, prompts, permissions, and execution policy
- **Context-Aware Operation** — Designed to consume application context and source data
- **MCP Orchestration** — Tool-based execution path for complex analysis and non-trivial edits
- **Provider Abstraction** — Single integration surface for Gemini CLI, Claude Code, and Codex CLI
- **Warm Sessions** — ACP / stream-json persistent subprocess for instant responses
- **Zero Footprint** — No config files written to your project directory
- **Event System** — Callbacks for GUI integration (text, tools, state changes)
- **Streaming** — Real-time response streaming
- **Production Ready** — Rate limiting, metrics, auto-restart, graceful shutdown

## Installation

```bash
pip install avatar-engine

# With CLI tools
pip install avatar-engine[cli]

# Development
pip install avatar-engine[dev,cli]
```

### Prerequisites

Install only the providers you need. All providers use **account-based authentication** (no API keys required):

```bash
# Gemini CLI (Google account — free tier available)
npm install -g @google/gemini-cli
gemini  # Run once to authenticate with Google account

# Claude Code (Anthropic account)
npm install -g @anthropic-ai/claude-code
claude  # Run once to authenticate

# Codex CLI (ChatGPT account via ACP adapter)
# Auto-fetched via npx on first use, or pre-cache:
npx @zed-industries/codex-acp --help
codex  # Run once to authenticate with ChatGPT account
```

Or use the interactive install script:

```bash
./install.sh          # Interactive — choose which providers to install
./install.sh --all    # Install everything
./install.sh --check  # Check what's installed
```

## Quick Start

### Library Usage

```python
from avatar_engine import AvatarEngine

# Synchronous — any provider: "gemini", "claude", or "codex"
engine = AvatarEngine(provider="gemini")
engine.start_sync()
response = engine.chat_sync("Hello!")
print(response.content)
engine.stop_sync()

# Asynchronous
import asyncio

async def main():
    engine = AvatarEngine(provider="codex")  # or "claude", "gemini"
    await engine.start()

    # Streaming
    async for chunk in engine.chat_stream("Tell me a story"):
        print(chunk, end="", flush=True)

    await engine.stop()

asyncio.run(main())
```

### CLI Usage

```bash
# Single message (provider flag -p goes BEFORE the subcommand)
avatar chat "What is 2+2?"
avatar -p claude chat "Write a haiku"
avatar -p codex chat "Refactor this function"

# Interactive REPL
avatar repl
avatar -p codex repl

# With config file: -p overrides config's provider
avatar -p codex chat "Hello"     # uses codex even if .avatar.yaml says gemini

# Health check
avatar health --check-cli

# MCP server management
avatar mcp list
avatar mcp add calc python calc_server.py
avatar mcp test calc
```

## Event-Driven GUI Integration

```python
from avatar_engine import AvatarEngine
from avatar_engine.events import TextEvent, ToolEvent, StateEvent

engine = AvatarEngine(provider="gemini")

@engine.on(TextEvent)
def on_text(event):
    """Avatar speaks — update GUI, trigger TTS"""
    gui.update_speech_bubble(event.text)
    tts.speak(event.text)

@engine.on(ToolEvent)
def on_tool(event):
    """Tool execution — show in GUI"""
    gui.show_tool_status(event.tool_name, event.status)

@engine.on(StateEvent)
def on_state(event):
    """State change — update status bar"""
    gui.set_status(event.new_state.value)

engine.start_sync()
engine.chat_async("Analyze this file", callback=gui.show_result)
```

## Configuration

### YAML Config File

```yaml
provider: "gemini"

gemini:
  model: ""  # Empty = CLI default
  approval_mode: "yolo"
  acp_enabled: true
  mcp_servers:
    tools:
      command: "python"
      args: ["mcp_server.py"]

claude:
  model: "claude-sonnet-4-5"
  permission_mode: "acceptEdits"
  cost_control:
    max_turns: 10
    max_budget_usd: 5.0

codex:
  model: ""  # Empty = CLI default
  auth_method: "chatgpt"  # chatgpt | codex-api-key | openai-api-key
  approval_mode: "auto"
  sandbox_mode: "workspace-write"

engine:
  auto_restart: true
  max_restarts: 3
  health_check_interval: 30

rate_limit:
  enabled: true
  requests_per_minute: 60

logging:
  level: "INFO"
  file: "avatar.log"
```

### Programmatic Config

```python
from avatar_engine import AvatarEngine, AvatarConfig

# From file
engine = AvatarEngine.from_config("config.yaml")

# Programmatic
engine = AvatarEngine(
    provider="claude",
    model="claude-sonnet-4-5",
    timeout=120,
    system_prompt="You are a helpful assistant.",
)
```

## Architecture

```
avatar-engine/
├── avatar_engine/
│   ├── __init__.py      # Public API
│   ├── engine.py        # AvatarEngine class
│   ├── config.py        # Configuration
│   ├── events.py        # Event system
│   ├── types.py         # Type definitions
│   ├── config_sandbox.py # Zero Footprint config (temp files)
│   ├── bridges/         # Provider implementations
│   │   ├── base.py      # Abstract bridge
│   │   ├── claude.py    # Claude Code bridge
│   │   ├── gemini.py    # Gemini CLI bridge
│   │   └── codex.py     # Codex CLI bridge (ACP)
│   ├── utils/           # Utilities
│   │   ├── logging.py   # Logging configuration
│   │   ├── metrics.py   # Metrics collection
│   │   └── rate_limit.py# Rate limiting
│   └── cli/             # CLI application
│       ├── app.py       # Main CLI
│       └── commands/    # CLI commands
├── examples/            # Usage examples
├── tests/               # Test suite
└── plans/               # Design documents
```

## Warm Session Architecture

All three providers support **persistent warm sessions**:

```
CLAUDE CODE (stream-json)
─────────────────────────
start()  →  spawn: claude -p --input-format stream-json
chat()   →  stdin: JSONL message → stdout: JSONL events
chat()   →  same process, instant response
stop()   →  close stdin → process exits

GEMINI CLI (ACP)
────────────────
start()  →  spawn: gemini --experimental-acp
         →  initialize → authenticate → new_session
chat()   →  prompt(session_id, message)
chat()   →  same session, same process
stop()   →  exit ACP context

CODEX CLI (ACP via codex-acp)
─────────────────────────────
start()  →  spawn: npx @zed-industries/codex-acp
         →  initialize → authenticate → new_session
chat()   →  prompt(session_id, message) + session_update stream
chat()   →  same session, same process
stop()   →  exit ACP context
```

## Examples

See the `examples/` directory:

- `basic_chat.py` — Simple sync/async usage (supports `--provider gemini|claude|codex`)
- `gui_integration.py` — Event-driven GUI pattern
- `streaming_avatar.py` — Real-time avatar with TTS
- `avatar.example.yaml` — Full configuration reference with all providers

Run examples:

```bash
python examples/basic_chat.py
python examples/basic_chat.py --provider claude --async
python examples/basic_chat.py --provider codex
python examples/streaming_avatar.py --provider codex --interactive
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=avatar_engine

# Current: 517 tests (unit + integration)
```

## API Reference

### AvatarEngine

```python
class AvatarEngine:
    # Lifecycle
    async def start() -> None
    async def stop() -> None
    def start_sync() -> None
    def stop_sync() -> None

    # Chat
    async def chat(message: str) -> BridgeResponse
    async def chat_stream(message: str) -> AsyncIterator[str]
    def chat_sync(message: str) -> BridgeResponse

    # Events
    def on(event_type) -> Callable  # Decorator
    def emit(event: AvatarEvent) -> None

    # Health
    def is_healthy() -> bool
    def get_health() -> HealthStatus

    # History
    def get_history() -> List[Message]
    def clear_history() -> None

    # Properties
    session_id: Optional[str]
    current_provider: str
    is_warm: bool
```

### Events

```python
TextEvent      # Text chunk from AI
ToolEvent      # Tool execution (started/completed/failed)
StateEvent     # Bridge state change
ThinkingEvent  # AI thinking (Gemini 3 / Codex)
CostEvent      # Cost/usage update
ErrorEvent     # Error occurred
```

### Types

```python
BridgeResponse  # Chat response with content, success, duration, etc.
HealthStatus    # Health check result
Message         # Conversation message
ProviderType    # GEMINI | CLAUDE | CODEX
BridgeState     # DISCONNECTED | WARMING_UP | READY | BUSY | ERROR
```

## License

Apache License 2.0 — see [LICENSE](LICENSE).

## Legal Notice

This project is a **wrapper** that communicates with external AI CLI tools via their documented interfaces. It does not include or redistribute code from these tools.

**User Responsibilities:**
- Install external tools separately (`gemini`, `claude`, `codex-acp`)
- Accept terms of service for each provider
- Authenticate with your account (Google / Anthropic / OpenAI-ChatGPT)

**External Tools:**
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) — Apache 2.0
- [Claude Code](https://github.com/anthropics/claude-code) — Anthropic Terms
- [Codex CLI](https://github.com/openai/codex) — Apache 2.0
- [codex-acp](https://github.com/nicolo-ribaudo/codex-acp) — ACP wrapper for Codex
- [ACP SDK](https://github.com/agentclientprotocol/python-sdk) — Apache 2.0

## Author
[@raven2cz](https://github.com/raven2cz)
