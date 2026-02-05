# Agent Client Protocol (ACP) Python SDK

> Source: https://agentclientprotocol.github.io/python-sdk/
> Repository: https://github.com/agentclientprotocol/python-sdk

## Overview

The ACP Python SDK enables building ACP-compliant agents and clients. ACP is "the stdio protocol that lets 'clients' (editors, shells, CLIs) orchestrate AI 'agents.'"

## Installation

```bash
pip install agent-client-protocol
# or
uv add agent-client-protocol
```

**Current version:** 0.7.1

## Package Structure

The package installs as `acp` (not `agent_client_protocol`):

```python
from acp import spawn_agent_process, text_block
from acp.interfaces import Client as ACPClient
from acp.schema import NewSessionRequest, PromptRequest
```

## Core Components

### 1. `acp.schema` — Pydantic Models

Validates payloads against the ACP specification:

- `NewSessionRequest` — Create a new session
- `PromptRequest` — Send a prompt
- `TextContentBlock` — Text content
- `McpServerStdio` — MCP server configuration

### 2. `acp.agent` / `acp.client` — Async Base Classes

Handle JSON-RPC supervision and lifecycle orchestration.

### 3. `acp.helpers` — Builders

Content blocks, tool calls, permissions, and notifications:

```python
from acp import text_block

# Create a text content block
block = text_block("Hello, world!")
```

### 4. `acp.contrib` — Utilities

Session accumulators, permission brokers, tool trackers.

## Basic Usage with Gemini CLI

```python
import asyncio
from acp import spawn_agent_process, text_block

async def main():
    # Spawn Gemini CLI in ACP mode
    async with spawn_agent_process(
        "gemini",
        "--experimental-acp",
        "--yolo",
        "--model", "gemini-3-pro-preview"
    ) as conn:
        # Initialize
        await conn.initialize()

        # Authenticate (uses cached OAuth credentials)
        await conn.authenticate(method_id="oauth-personal")

        # Create session
        session = await conn.new_session(
            cwd="/path/to/project",
            mcp_servers=[
                {
                    "name": "my-tools",
                    "command": "python",
                    "args": ["mcp_tools.py"],
                    "env": []  # Required! List of {name, value} objects
                }
            ]
        )

        # Send prompt
        result = await conn.prompt(
            session_id=session.session_id,
            prompt=[text_block("Hello!")]
        )

        print(result)

asyncio.run(main())
```

## Key Schemas

### NewSessionRequest

```python
class NewSessionRequest:
    cwd: str  # Working directory
    mcp_servers: List[McpServerStdio]  # MCP servers
    field_meta: Optional[Dict[str, Any]]  # Metadata
```

### McpServerStdio

```python
class McpServerStdio:
    name: str
    command: str
    args: List[str]
    env: List[EnvVariable]  # REQUIRED! List of {name, value}
```

**Important:** The `env` field is required and must be a list of `{"name": k, "value": v}` objects, not a dict!

### PromptRequest

```python
class PromptRequest:
    session_id: str
    prompt: List[ContentBlock]  # TextContentBlock, ImageContentBlock, etc.
    field_meta: Optional[Dict[str, Any]]
```

## Client Interface Methods

```python
# Session management
await conn.new_session(cwd, mcp_servers)

# Prompting
result = await conn.prompt(session_id, prompt)

# File operations
await conn.read_text_file(path, session_id, limit, line)
await conn.write_text_file(content, path, session_id)

# Terminal operations
await conn.create_terminal(command, session_id, args, cwd, env)
await conn.terminal_output(session_id, terminal_id)
await conn.kill_terminal(session_id, terminal_id)

# Extensions
await conn.ext_method(method, params)
await conn.ext_notification(method, params)

# Permissions
await conn.request_permission(options, session_id, tool_call)
```

## Streaming Updates

Subscribe to session updates for streaming responses:

```python
async for update in conn.session_updates(session_id):
    # update can be:
    # - UserMessageChunk
    # - AgentMessageChunk  (contains TextContentBlock)
    # - AgentThoughtChunk
    # - ToolCallStart / ToolCallProgress
    # - AgentPlanUpdate
    # - SessionInfoUpdate

    if hasattr(update, "content"):
        content = update.content
        if hasattr(content, "text"):
            print(content.text, end="", flush=True)
```

## Known Issues with Gemini CLI ACP

From GitHub issues:

1. **#18355** — `--experimental-acp` not working in newest version
2. **#17952** — Tool confirmations delayed by ~30s (MessageBus timeout)
3. **#17854** — v26.0 ACP lacks MCP server tools
4. **#15502** — `--resume` not working in ACP mode

**Workaround for #7549** (OAuth not using cached creds): Fixed in Gemini CLI >= v0.23.0 (PR #9410)

## Development

```bash
# Install with dev dependencies
make install

# Run tests
make test

# Lint and type check
make check

# Regenerate schema from ACP spec
ACP_SCHEMA_VERSION=<ref> make gen-all
```
