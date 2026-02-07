# Codex CLI — Reference for Avatar Engine Integration

> Source: https://github.com/openai/codex
> License: Apache-2.0
> Language: Rust (with TypeScript npm wrapper)

## Overview

Codex is OpenAI's official AI coding agent CLI. It runs locally as a native
binary, executing shell commands and file modifications in a sandboxed
environment with approval workflows.

## Installation

```bash
npm i -g @openai/codex
# or
brew install --cask codex
```

## Authentication

Two methods — **no traditional API key required** for ChatGPT auth:

### ChatGPT OAuth (Recommended)

```bash
codex login
```

- Opens browser for Google/ChatGPT OAuth flow
- Tokens cached in `~/.codex/credentials` (encrypted via keyring)
- Works with ChatGPT Plus/Pro subscription
- Auto-refresh of tokens

### API Key

```bash
export CODEX_API_KEY=sk-...
# or
export OPENAI_API_KEY=sk-...
```

## Execution Modes

### Interactive TUI

```bash
codex
```

Full-screen terminal UI (ratatui-based).

### Non-Interactive (Headless)

```bash
codex exec "write a function that reverses a string"
codex exec --ephemeral "fix the tests"
```

Flags:
- `--ephemeral` — don't persist session to disk
- `--sandbox read-only|workspace-write|danger-full-access` — sandbox policy
- Can pipe via stdin: `echo "do this" | codex exec`

### App Server (IDE Integration)

```bash
codex app-server
```

JSON-RPC 2.0 server over stdio or websocket for IDE clients.

### MCP Server

```bash
codex mcp-server
```

Exposes Codex as an MCP server for other agents.

## Architecture

```
CLI/TUI Layer
    ↓
App Server (JSON-RPC 2.0)
    ↓
Core Agent Logic (codex-core)
    ↓
Protocol Layer (codex-protocol)
    ↓
Backend Clients (Responses API)
```

### Monorepo Structure

```
codex/
├── codex-rs/                # Main Rust implementation (40+ crates)
│   ├── core/                # Core agent logic (library crate)
│   ├── cli/                 # CLI multitool (TUI, exec, app-server, mcp-server)
│   ├── app-server/          # JSON-RPC server for clients
│   ├── app-server-protocol/ # JSON-RPC protocol definitions
│   ├── protocol/            # Core protocol types (Op, Event, Item)
│   ├── tui/                 # Terminal UI (ratatui)
│   ├── exec/                # Headless non-interactive mode
│   ├── mcp-server/          # Codex as MCP server
│   ├── login/               # OAuth/API key authentication
│   ├── state/               # Session persistence (SQLite)
│   ├── exec-server/         # Sandboxed shell execution
│   └── ...                  # file-search, execpolicy, sandbox, etc.
├── codex-cli/               # Legacy TypeScript wrapper (superseded by Rust)
└── sdk/typescript/          # TypeScript SDK for programmatic access
```

## App Server Protocol (JSON-RPC 2.0)

Transport: **stdio** (JSONL) or **websocket**

Note: Wire format omits `"jsonrpc": "2.0"` field.

### Session Lifecycle

```
Client                        Codex App Server
  │                                │
  ├─ initialize ──────────────────→│
  │←─ InitializeResult ───────────┤
  ├─ initialized (notification) ──→│
  │                                │
  ├─ account/login/start ─────────→│  (ChatGPT or API key)
  │←─ account/login/completed ────┤
  │                                │
  ├─ thread/start ────────────────→│  (create new conversation)
  │←─ ThreadStartResult ─────────┤
  │                                │
  ├─ turn/start ──────────────────→│  (send user message)
  │←─ turn/started (notification) ┤
  │←─ item/started ───────────────┤  (streaming begins)
  │←─ item/agentMessage/delta ────┤  (text chunks)
  │←─ item/commandExecution/* ────┤  (tool calls)
  │←─ item/completed ─────────────┤
  │←─ turn/completed ─────────────┤
  │                                │
  ├─ turn/start ──────────────────→│  (next turn, same thread)
  │  ...                           │
```

### Key Methods

| Method | Description |
|--------|-------------|
| `initialize` | Protocol handshake, capabilities exchange |
| `account/login/start` | Trigger auth (chatgpt or apiKey) |
| `account/read` | Check current auth status |
| `thread/start` | Create new conversation thread |
| `thread/resume` | Reopen existing thread by ID |
| `thread/list` | List saved threads (paginated) |
| `turn/start` | Send user message, streams response |
| `turn/interrupt` | Cancel in-flight turn |
| `thread/compact/start` | Compress conversation history |

### Streaming Event Types

During a turn, the server emits these notifications:

| Event | Description |
|-------|-------------|
| `turn/started` | Turn initialized |
| `item/started` | New item (message, command, file change) |
| `item/agentMessage/delta` | Text response chunk |
| `item/commandExecution/outputDelta` | Shell command output |
| `item/commandExecution/requestApproval` | Permission request |
| `item/fileChange/requestApproval` | File edit permission |
| `item/completed` | Item finalized |
| `turn/completed` | Turn done (with StopReason) |
| `turn/plan/updated` | Agent's plan changed |
| `thread/tokenUsage/updated` | Token count update |

### Item Types

| Type | Description |
|------|-------------|
| `userMessage` | User input |
| `agentMessage` | LLM text response |
| `plan` | Agent's proposed steps |
| `reasoning` | LLM reasoning (o1/o3 models) |
| `commandExecution` | Shell command with approval |
| `fileChange` | File edit with approval |
| `mcpToolCall` | MCP tool invocation |
| `webSearch` | Web search |

### Approval Flow

```json
← Server: {"method": "item/commandExecution/requestApproval",
            "params": {"command": "npm test", ...}}
→ Client: {"id": 5, "result": {"decision": "accept"}}
```

Decisions: `accept`, `decline`

## Configuration

### Config File

Location: `~/.codex/config.toml`

```toml
model = "gpt-5.3-codex"
sandbox_mode = "workspace-write"
approval_policy = "on-failure"

[mcp_servers.my-server]
command = "npx"
args = ["-y", "@my/mcp-server"]

[features]
shell_tool = true
web_search = true
```

### Session Persistence

- Sessions stored as JSONL rollout files in `~/.codex/sessions/`
- Archived sessions in `~/.codex/archived_sessions/`
- SQLite state database: `~/.codex/state.db`

### Environment Variables

| Variable | Description |
|----------|-------------|
| `CODEX_API_KEY` | Codex service API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `CODEX_HOME` | Config directory (default: `~/.codex`) |
| `RUST_LOG` | Logging level (debug, info, etc.) |

## MCP Support

### As MCP Client

Codex connects to configured MCP servers via `config.toml`:

```toml
[mcp_servers.avatar-tools]
command = "python"
args = ["mcp_tools.py"]
```

### As MCP Server

```bash
codex mcp-server
```

Exposes Codex agent capabilities as MCP tools.

## Sandbox Modes

| Mode | Description |
|------|-------------|
| `read-only` | Can read files, no writes or shell |
| `workspace-write` | Can modify workspace files |
| `danger-full-access` | Full filesystem and shell access |

## Key Differences from Gemini/Claude CLI

| Aspect | Codex | Gemini | Claude |
|--------|-------|--------|--------|
| Language | Rust | Node.js | Node.js |
| Auth | ChatGPT OAuth / API key | Google OAuth / API key | Anthropic API key |
| Protocol | JSON-RPC 2.0 (custom) | ACP | stream-json |
| Session | Thread-based, SQLite | ACP sessions | Persistent subprocess |
| Sandbox | Built-in (Linux/macOS) | N/A | Permission modes |
| MCP | Client + Server | Client | Client |

## Sources

- Repository: https://github.com/openai/codex
- Documentation: https://developers.openai.com/codex
- Config reference: https://developers.openai.com/codex/local-config
