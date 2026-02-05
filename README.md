# Avatar Engine — Headless AI CLI Bridges

Unified Python bridge for **Gemini CLI** and **Claude Code**.
No PTY, no ANSI parsing, no ASCII art. Clean JSON communication.

## Warm Session Architecture

Both providers now support **true warm sessions** (one persistent process):

```
                    CLAUDE CODE (persistent via stream-json)
                    ════════════════════════════════════════
start()  →  spawn: claude -p --input-format stream-json --output-format stream-json
            process starts, warms up, emits init event → READY

chat()   →  stdin:  {"type":"user","message":{"role":"user","content":[...]}}
         ←  stdout: {"type":"assistant",...}
         ←  stdout: {"type":"result",...}     ← turn complete

chat()   →  stdin:  JSONL line on same process → instant!

stop()   →  close stdin → process exits


                    GEMINI CLI (persistent via ACP + OAuth)
                    ════════════════════════════════════════
start()  →  spawn: gemini --experimental-acp --yolo --model gemini-3-pro-preview
            → initialize (JSON-RPC 2.0)
            → authenticate(methodId="oauth-personal")   ← Google account!
            → new_session(cwd, mcp_servers)
            → READY (warm)

chat()   →  prompt(session_id, [text_block("Ahoj!")])
         ←  session/update notifications (streaming text)
         ←  prompt result → turn complete

chat()   →  prompt(session_id, [...])  ← same process, same session!

stop()   →  exit ACP context manager → process exits


                    GEMINI CLI FALLBACK (oneshot, if ACP fails)
                    ════════════════════════════════════════════
chat()   →  spawn: gemini -p "[history]\nUser: prompt" --output-format stream-json --yolo
         ←  stdout: JSONL events → process exits   ← cold start each time
```

### Comparison

| | Claude Code | Gemini CLI (ACP) | Gemini CLI (oneshot fallback) |
|---|---|---|---|
| **Mode** | Persistent (warm) | Persistent (warm) | Oneshot (cold) |
| **Protocol** | JSONL stream-json | JSON-RPC 2.0 (ACP) | CLI headless JSON |
| **Auth** | API key / OAuth | OAuth (Google account) | OAuth (cached) |
| **Warm-up** | Once at start() | Once at start() | Every call |
| **Session** | Native | Native (ACP session) | Context injection |
| **SDK** | Custom JSONL | `agent-client-protocol` | None |
| **Tool approval** | `--allowedTools` | `--yolo` | `--yolo` |

## Prerequisites

```bash
# Gemini CLI >= v0.23.0 (includes OAuth ACP fix PR #9410)
npm install -g @google/gemini-cli
gemini   # Run once interactively to cache OAuth credentials

# Claude Code
npm install -g @anthropic-ai/claude-code

# Python dependencies
pip install agent-client-protocol>=0.6.0 pyyaml mcp
```

## Quick Start

```bash
./install.sh && source activate.sh
nano config.yaml              # Set provider, model, MCP servers
gemini                        # Authenticate with Google (one-time)
python examples.py basic
```

## Usage

```python
from avatar_engine import AvatarEngine

engine = AvatarEngine("config.yaml")
await engine.start()           # Both providers: warms up process

print(engine.is_warm)          # True for both (ACP for Gemini)

resp = await engine.chat("Ahoj!")
print(resp.content)            # Clean text
print(resp.session_id)         # ACP session or Claude session
print(resp.duration_ms)        # Response time

# Multi-turn — model remembers everything (same process)
resp2 = await engine.chat("Co jsem ti právě řekl?")

# Streaming
async for chunk in engine.chat_stream("Vyprávěj příběh"):
    print(chunk, end="", flush=True)

# Switch provider at runtime
await engine.switch_provider("claude")

# Raw JSON events
engine.on_event(lambda ev: print("EVENT:", ev))
```

## Configuration

```yaml
provider: "gemini"

gemini:
  # Latest preview: gemini-3-pro-preview (best MCP support)
  # Stable: gemini-2.5-pro
  model: "gemini-3-pro-preview"
  approval_mode: "yolo"
  acp_enabled: true                    # ← ACP warm session
  auth_method: "oauth-personal"        # ← Google account, no API key
  mcp_servers:
    avatar-tools:
      command: "python"
      args: ["mcp_tools.py"]

claude:
  # Models: claude-opus-4-5 (best), claude-sonnet-4-5 (fast), claude-haiku-3-5
  model: "claude-sonnet-4-5"
  permission_mode: "acceptEdits"
  allowed_tools:
    - "mcp__avatar-tools__*"
  mcp_servers:
    avatar-tools:
      command: "python"
      args: ["mcp_tools.py"]
```

### Auth Methods

| Method | Config | Notes |
|--------|--------|-------|
| Google account (Pro) | `auth_method: "oauth-personal"` | Default. Run `gemini` once to cache creds. |
| API key | `auth_method: "gemini-api-key"` | Set `GEMINI_API_KEY` env var. |
| Vertex AI | `auth_method: "vertex-ai"` | Requires GCP project + ADC. |

## Project Structure

```
avatar-engine/
├── config.yaml           # Main configuration
├── avatar_engine.py      # High-level AvatarEngine class
├── bridges/
│   ├── base_bridge.py    # Abstract bridge (subprocess + event parsing)
│   ├── gemini_bridge.py  # ACP warm session + oneshot fallback
│   └── claude_bridge.py  # stream-json warm session
├── mcp_tools.py          # Example MCP tools
├── examples.py           # Usage examples
├── install.sh            # Arch Linux installer (uv)
└── README.md
```

## ACP Protocol Details

The Gemini bridge uses the [Agent Client Protocol](https://agentclientprotocol.com/)
via the `agent-client-protocol` Python SDK. The flow:

1. **spawn**: `gemini --experimental-acp --yolo`
2. **initialize**: JSON-RPC `initialize` request (protocol version 1)
3. **authenticate**: `authenticate(methodId="oauth-personal")` — uses cached Google OAuth credentials
4. **new_session**: Creates a session with MCP servers and working directory
5. **prompt**: Send user messages, receive streaming `session/update` notifications
6. **prompt** (repeat): Same session, same process — no cold start!

Bug #7549 (OAuth cached credentials not used in ACP subprocess mode) was fixed
in [PR #9410](https://github.com/google-gemini/gemini-cli/pull/9410) (merged Dec 2025).
Gemini CLI >= v0.23.0 includes this fix.

## Important Notes

### Model Selection

| Provider | Recommended Model | Notes |
|----------|-------------------|-------|
| Gemini | `gemini-3-pro-preview` | Best MCP tool support, latest reasoning |
| Gemini | `gemini-2.5-pro` | Stable, but may have MCP visibility issues |
| Claude | `claude-opus-4-5` | Best quality, slower |
| Claude | `claude-sonnet-4-5` | Fast, good for most use cases |
| Claude | `claude-haiku-3-5` | Fastest, lowest cost |

### Requirements

- **Gemini CLI >= 0.27.0** — Install via npm for auto-updates:
  ```bash
  sudo npm install -g @google/gemini-cli@latest
  gemini --version  # Should show 0.27.0+
  ```
- **MCP SDK 1.26+** — Requires `InitializationOptions` with `ServerCapabilities`
- **agent-client-protocol >= 0.6.0** — For ACP warm sessions

### MCP Server Notes

MCP servers in ACP mode require `env` field (can be empty list):
```python
entry = {
    "name": name,
    "command": srv["command"],
    "args": srv.get("args", []),
    "env": [{"name": k, "value": v} for k, v in srv.get("env", {}).items()]
}
```

## Testing

```bash
# Activate environment
source .venv/bin/activate

# Test Gemini ACP warm session
python -c "
import asyncio
from avatar_engine import AvatarEngine

async def test():
    engine = AvatarEngine('config.yaml')
    await engine.start()
    print(f'Warm: {engine.is_warm}')
    print(f'Session: {engine.session_id}')

    resp = await engine.chat('Ahoj!')
    print(f'Response: {resp.content}')

    # Test MCP tools
    resp2 = await engine.chat('Kolik je hodin? Pouzij system_time.')
    print(f'Time: {resp2.content}')

    await engine.stop()

asyncio.run(test())
"

# Test Claude stream-json (change provider in config.yaml first)
# provider: "claude"
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| ACP falls back to oneshot | Update Gemini CLI to >= 0.27.0 |
| MCP tools not visible | Use `gemini-3-pro-preview` model |
| OAuth authentication fails | Run `gemini` interactively first to cache credentials |
| MCP server validation error | Ensure `env` field is a list of `{name, value}` objects |

## License

This project is licensed under the **Apache License 2.0** — see the [LICENSE](LICENSE) file for details.

## Legal Notice — External Tools

**Important:** This project is a **wrapper/bridge** that communicates with external AI CLI tools via their documented public interfaces. It does **not** include, embed, or redistribute any code from these tools.

### External Tools Used

| Tool | License | Terms |
|------|---------|-------|
| [Gemini CLI](https://github.com/google-gemini/gemini-cli) | Apache 2.0 | [License](https://github.com/google-gemini/gemini-cli/blob/main/LICENSE) |
| [Claude Code](https://github.com/anthropics/claude-code) | Proprietary | [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms) |
| [ACP Python SDK](https://github.com/agentclientprotocol/python-sdk) | Apache 2.0 | [License](https://github.com/agentclientprotocol/python-sdk/blob/main/LICENSE) |

### User Responsibilities

By using Avatar Engine, you agree to:

1. **Install the external tools separately** — This project does not distribute Gemini CLI or Claude Code
2. **Accept the terms of service** of each tool you use:
   - Gemini CLI: [Google Terms of Service](https://policies.google.com/terms)
   - Claude Code: [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms)
3. **Obtain proper authentication** — You need your own Google account or Anthropic API access
4. **Use responsibly** — Follow the usage policies of each provider

### What This Project Does

- Spawns external CLI processes (`gemini`, `claude`) as subprocesses
- Communicates via documented stdin/stdout JSON protocols
- Does **not** access internal APIs, bypass authentication, or modify the tools
- Does **not** include any proprietary code from Anthropic or Google

### No Warranty

This software is provided "as is" without warranty. The authors are not responsible for any issues arising from the use of external tools or violations of their terms of service.

## Contributing

Contributions are welcome! Please ensure any contributions:
- Do not include code from Gemini CLI or Claude Code
- Respect the licenses of all dependencies
- Follow the existing code style

## Author

Antonin Stefanutti ([@raven2cz](https://github.com/raven2cz))
