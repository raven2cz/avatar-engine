# Codex ACP Adapter (codex-acp) — Reference

> Source: https://github.com/zed-industries/codex-acp
> Author: Zed Industries
> License: Apache-2.0
> Language: Rust

## Overview

`codex-acp` is an ACP (Agent Client Protocol) adapter that wraps the Codex CLI,
exposing it as an ACP-compliant agent. This allows any ACP client (Zed editor,
avatar-engine, etc.) to communicate with Codex using the same protocol used
for Gemini CLI.

## Installation

```bash
npx @zed-industries/codex-acp
# or build from source:
cargo build --release
```

## How It Works

```
ACP Client (avatar-engine)
    ↓ stdin/stdout (ACP JSON-RPC)
codex-acp adapter
    ↓ internal Rust API
codex-core (CodexThread)
    ↓ HTTP
OpenAI Responses API
```

Key insight: codex-acp does NOT spawn a separate `codex` CLI process.
Instead, it links against `codex-core`, `codex-protocol`, and `codex-login`
Rust crates directly, creating CodexThread instances in-process.

## Architecture

### Source Files

| File | LOC | Purpose |
|------|-----|---------|
| `src/lib.rs` | ~95 | ACP connection setup (stdin/stdout bridge) |
| `src/main.rs` | ~12 | Entry point |
| `src/codex_agent.rs` | ~630 | ACP Agent trait implementation |
| `src/thread.rs` | ~2300 | ThreadActor: event handling, tool calls, streaming |
| `src/local_spawner.rs` | ~256 | Filesystem sandbox for ACP sessions |
| `src/prompt_args.rs` | ~316 | Custom prompt parameter expansion |

### Key Components

1. **AgentSideConnection** (from `acp` crate) — Reads/writes ACP messages on stdin/stdout
2. **CodexAgent** — Implements ACP `Agent` trait with all lifecycle methods
3. **ThreadActor** — Per-session async actor processing events from CodexThread
4. **LocalSpawner** — Sandboxed filesystem access scoped to session root

## ACP Protocol Implementation

### Protocol Version

Uses `agent-client-protocol = "=0.9.4"` (with unstable features).

### Lifecycle Flow

```
ACP Client                    codex-acp                     codex-core
    │                            │                              │
    ├─ initialize ──────────────→│ verify protocol version      │
    │←─ InitializeResponse ──────┤ capabilities, auth methods   │
    │                            │                              │
    ├─ authenticate ────────────→│ ChatGPT/API key auth         │
    │                            │──→ codex-login crate ────────│
    │←─ AuthenticateResponse ────┤                              │
    │                            │                              │
    ├─ new_session(cwd, mcp) ───→│ build config                 │
    │                            │──→ ThreadManager::start ─────│→ spawn thread
    │                            │←── NewThread ────────────────│
    │                            │ wrap in ThreadActor           │
    │←─ NewSessionResponse ──────┤ {session_id, modes, models}  │
    │                            │                              │
    ├─ prompt(session_id, msg) ─→│ parse slash commands          │
    │                            │──→ thread.submit(Op) ────────│→ LLM call
    │                            │←── Event stream ─────────────│
    │←─ SessionNotification ─────┤ AgentMessageChunk (streaming) │
    │←─ SessionNotification ─────┤ ToolCall (exec/patch)        │
    │←─ RequestPermission ───────┤ approval request             │
    │──→ permission response ───→│                              │
    │←─ SessionNotification ─────┤ ToolCallUpdate (result)      │
    │←─ PromptResponse ─────────┤ StopReason::EndTurn          │
```

### Capabilities Advertised

```json
{
  "prompt_capabilities": {
    "embedded_context": true,
    "image": true
  },
  "mcp_capabilities": {
    "http": true
  },
  "load_session": true,
  "session": {
    "list": true
  }
}
```

### Authentication Methods

| Method ID | Mechanism |
|-----------|-----------|
| `chatgpt` | Browser OAuth flow via `codex-login` |
| `codex-api-key` | `CODEX_API_KEY` env var |
| `openai-api-key` | `OPENAI_API_KEY` env var |

### Session Management

- `new_session(cwd, mcp_servers)` — Creates new CodexThread
- `load_session(session_id, cwd)` — Resumes from rollout history
- `list_sessions(cwd)` — Lists saved sessions (paginated)
- Each session = separate CodexThread (actor-based)

### Streaming Notifications (SessionNotification updates)

| Update Type | Description |
|-------------|-------------|
| `AgentMessageChunk` | Text response chunk (streamed) |
| `AgentThoughtChunk` | Reasoning/thinking chunk |
| `ToolCall` | Tool invocation started (exec, patch, MCP, web search) |
| `ToolCallUpdate` | Tool status update (output delta, completed, failed) |
| `RequestPermission` | Approval request for exec/patch/MCP |
| `Plan` | Agent's task plan (with items) |
| `ConfigOptionsUpdated` | Config changed (model, mode, etc.) |

### Tool Call Kinds

| Kind | Description |
|------|-------------|
| `Execute` | Shell command execution |
| `Patch` | File modification (unified diff) |
| `Fetch` | Web search |
| `McpToolCall` | MCP tool invocation |

### Approval Flow

```
codex-acp → RequestPermissionRequest {
    session_id, permission_id,
    title: "Run: npm test",
    description: "npm test",
    kind: Execute
}

client → RequestPermissionResponse {
    permission_id,
    decision: Approved | ApprovedForSession | Abort
}
```

## Comparison to Gemini ACP (avatar-engine perspective)

| Aspect | Gemini ACP | Codex ACP |
|--------|-----------|-----------|
| **ACP SDK** | `acp` Python (spawn_agent_process) | `acp` Rust (AgentSideConnection) |
| **Process model** | Python spawns `gemini` subprocess | Rust binary with codex-core linked |
| **Auth** | `authenticate(oauth-personal)` | `authenticate(chatgpt)` |
| **Session** | `new_session()` → session_id | `new_session(cwd, mcp)` → session_id + modes + models |
| **Prompt** | `prompt(session_id, text)` | `prompt(session_id, items[])` with images/context |
| **Streaming** | `session_update` notifications | `SessionNotification` with typed updates |
| **Approvals** | Auto-approved (yolo mode) | Full permission request/response flow |
| **MCP servers** | Configured in settings.json | Passed per-session in new_session |
| **Text extraction** | Parse from update object | `AgentMessageChunk.content.text` |
| **Thinking** | Extract from update | `AgentThoughtChunk.content.text` |
| **Cancel** | Not directly supported | `cancel(session_id)` → Op::Cancel |

### Key Difference for Integration

For Gemini, avatar-engine uses the **Python ACP SDK** (`acp` package) to spawn
and communicate with the Gemini CLI subprocess. The SDK handles JSON-RPC
serialization.

For Codex, the same **Python ACP SDK** can be used identically:
```python
from acp import spawn_agent_process
ctx = spawn_agent_process(client, "npx", "@zed-industries/codex-acp")
conn, proc = await ctx.__aenter__()
await conn.initialize(protocol_version=1)
await conn.authenticate(method_id="chatgpt")
session = await conn.new_session(cwd="/project")
response = await conn.prompt(session_id=session.id, prompt="Hello")
```

The protocol is the same — only the agent binary and auth method differ.

## Configuration

### CLI Arguments

```bash
codex-acp [-c key=value]   # Config overrides
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | API key auth |
| `CODEX_API_KEY` | Codex service auth |
| `NO_BROWSER` | Disable browser auth (SSH) |
| `RUST_LOG` | Logging level (stderr) |

## Dependencies

### Key Crates

- `agent-client-protocol = "=0.9.4"` — ACP protocol
- `codex-core` — Thread management, agent logic (git dependency, `acp` branch)
- `codex-protocol` — Op, Event, Item types
- `codex-login` — Authentication
- `tokio` — Async runtime
- `serde_json` — Serialization

## Sources

- Repository: https://github.com/zed-industries/codex-acp
- ACP specification: https://agentclientprotocol.github.io/
- Codex CLI: https://github.com/openai/codex
