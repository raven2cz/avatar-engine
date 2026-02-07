# Avatar Engine — Codex Provider Integration Plan

> Created: 2026-02-07
> Status: DONE
> Version: 1.0
> Closed: 2026-02-07

---

## 1. Executive Summary

Add **Codex (OpenAI GPT-5.3-Codex)** as the third provider to avatar-engine,
completing the "holy trinity" of AI providers: **Gemini + Claude + Codex**.

Codex integrates via the **codex-acp** adapter from Zed Industries, which
exposes Codex CLI as an ACP agent. Since avatar-engine already has a working
ACP integration for Gemini, the Codex bridge follows the same pattern —
`spawn_agent_process()` from the Python ACP SDK.

### Key Decision: ACP-First (No Oneshot Fallback)

Unlike GeminiBridge which has an ACP + oneshot hybrid approach, CodexBridge
will be **ACP-only**. Rationale:
- Codex CLI has no `--output-format stream-json` headless mode like Gemini
- The codex-acp adapter IS the headless integration layer
- Codex's native app-server protocol is JSON-RPC, not simple JSONL
- The ACP adapter already handles all the protocol translation

### Architecture Fit

```
avatar-engine
├── GeminiBridge  → ACP (Python SDK) → gemini --experimental-acp
├── ClaudeBridge  → stream-json (persistent subprocess)
└── CodexBridge   → ACP (Python SDK) → codex-acp (Rust binary)
                    ↑ SAME ACP SDK, different agent binary
```

---

## 2. Integration Architecture

### 2.1 Communication Flow

```
AvatarEngine
    ↓
CodexBridge (avatar_engine/bridges/codex.py)
    ↓ Python ACP SDK (acp package)
    ↓ spawn_agent_process(client, "npx", "@zed-industries/codex-acp")
    ↓ stdin/stdout JSON-RPC (ACP protocol)
codex-acp (Rust binary)
    ↓ codex-core (in-process)
    ↓ HTTP
OpenAI Responses API
```

### 2.2 ACP Lifecycle (mirrors GeminiBridge)

```python
# 1. Spawn
ctx = spawn_agent_process(client, *cmd, cwd=working_dir, env=env)
conn, proc = await ctx.__aenter__()

# 2. Initialize
await conn.initialize(protocol_version=1)

# 3. Authenticate
await conn.authenticate(method_id=auth_method)
# auth_method: "chatgpt" | "codex-api-key" | "openai-api-key"

# 4. Create session
session = await conn.new_session(cwd=working_dir, mcp_servers=mcp_config)
# Returns: session_id, modes, models, config_options

# 5. Prompt (repeatable — warm session)
response = await conn.prompt(session_id=session.id, prompt=message)
# Streams: AgentMessageChunk, ToolCall, ToolCallUpdate, RequestPermission

# 6. Cleanup
await ctx.__aexit__(None, None, None)
```

### 2.3 Key Differences from GeminiBridge

| Aspect | GeminiBridge | CodexBridge |
|--------|-------------|-------------|
| Command | `gemini --experimental-acp --yolo` | `npx @zed-industries/codex-acp` |
| Auth method | `oauth-personal` | `chatgpt` / `codex-api-key` |
| Fallback | Oneshot if ACP fails | No fallback (ACP-only) |
| Approval mode | `--yolo` (auto-approve) | `auto-approve` in client callback |
| Session features | Basic (prompt/response) | Rich (modes, models, config, list, resume) |
| Text extraction | Custom `_extract_text_from_update()` | `AgentMessageChunk.content.text` |
| Thinking | `include_thoughts` in settings | `AgentThoughtChunk` updates |
| Tool calls | Gemini tool format | `ToolCall` + `ToolCallUpdate` |
| MCP servers | Via settings.json | Per-session in `new_session()` |

---

## 3. Implementation Plan

### Phase 1: CodexBridge Core (HIGH priority)

**File: `avatar_engine/bridges/codex.py`**

```python
class CodexBridge(BaseBridge):
    """
    Codex CLI bridge via ACP adapter (codex-acp).

    Uses the same ACP Python SDK as GeminiBridge but communicates
    with the codex-acp Rust binary instead of Gemini CLI.

    Lifecycle::

        bridge = CodexBridge(...)
        await bridge.start()     # Spawns codex-acp, authenticates, creates session
        resp = await bridge.send("Hello!")   # Instant (warm session)
        resp = await bridge.send("More?")    # Same session
        await bridge.stop()
    """
```

#### Constructor Parameters

```python
def __init__(
    self,
    executable: str = "npx",           # or path to codex-acp binary
    executable_args: list = ["@zed-industries/codex-acp"],
    model: str = "",                    # Empty = Codex default
    working_dir: str = "",
    timeout: int = 120,
    system_prompt: str = "",
    auth_method: str = "chatgpt",       # chatgpt | codex-api-key | openai-api-key
    approval_mode: str = "auto",        # auto-approve tool calls
    sandbox_mode: str = "workspace-write",
    env: Optional[Dict[str, str]] = None,
    mcp_servers: Optional[Dict[str, Any]] = None,
):
```

#### Key Implementation Points

1. **ACP Client callback**: Handle `RequestPermission` by auto-approving
   (similar to GeminiBridge `_AvatarACPClient`), configurable per bridge
2. **Text extraction**: Parse `AgentMessageChunk` from session notifications
3. **Thinking extraction**: Parse `AgentThoughtChunk` for ThinkingEvent
4. **Tool calls**: Map `ToolCall` / `ToolCallUpdate` to ToolEvent
5. **Session ID**: From `new_session()` response
6. **Cost tracking**: From token usage notifications (if available)

#### Abstract Method Implementations

```python
@property
def provider_name(self) -> str:
    return "codex"

@property
def is_persistent(self) -> bool:
    return True  # Always ACP warm session

async def start(self) -> None:
    # spawn codex-acp → initialize → authenticate → new_session

async def stop(self) -> None:
    # cleanup ACP context

async def send(self, message: str) -> BridgeResponse:
    # conn.prompt(session_id, message) → parse response

async def send_stream(self, message: str) -> AsyncIterator[str]:
    # Use on_update callback for streaming text chunks
```

### Phase 2: Engine Integration (HIGH priority)

#### 2a. Provider Registration

**File: `avatar_engine/types.py`**

```python
class ProviderType(str, Enum):
    GEMINI = "gemini"
    CLAUDE = "claude"
    CODEX = "codex"       # NEW
```

**File: `avatar_engine/engine.py`** — `_create_bridge()`

```python
elif self._provider == ProviderType.CODEX:
    pcfg = self._config.codex_config if self._config else self._kwargs
    return CodexBridge(
        executable=pcfg.get("executable", "npx"),
        executable_args=pcfg.get("executable_args", ["@zed-industries/codex-acp"]),
        model=self._model or pcfg.get("model", ""),
        auth_method=pcfg.get("auth_method", "chatgpt"),
        approval_mode=pcfg.get("approval_mode", "auto"),
        sandbox_mode=pcfg.get("sandbox_mode", "workspace-write"),
        **common,
    )
```

#### 2b. Configuration Support

**File: `avatar_engine/config.py`** — Add `codex_config` section

**File: `.avatar.yaml`** — Add Codex section

```yaml
codex:
  executable: "npx"
  executable_args: ["@zed-industries/codex-acp"]
  model: ""  # Empty = Codex default (gpt-5.3-codex)
  timeout: 120

  # Authentication: "chatgpt" (browser OAuth), "codex-api-key", "openai-api-key"
  auth_method: "chatgpt"

  # Auto-approve tool calls (required for non-interactive use)
  approval_mode: "auto"

  # Sandbox: "read-only", "workspace-write", "danger-full-access"
  sandbox_mode: "workspace-write"

  # System prompt
  system_prompt: |
    You are an AI avatar. Respond concisely and naturally.
    Use MCP tools to control the avatar.

  # MCP servers (passed per-session to codex-acp)
  mcp_servers:
    avatar-tools:
      command: "/path/to/.venv/bin/python"
      args: ["/path/to/mcp_tools.py"]

  env: {}
```

#### 2c. Bridge Exports

**File: `avatar_engine/bridges/__init__.py`**

```python
from .codex import CodexBridge
```

**File: `avatar_engine/__init__.py`**

```python
from .bridges import BaseBridge, ClaudeBridge, GeminiBridge, CodexBridge
```

### Phase 3: CLI Support (MEDIUM priority)

**File: `avatar_engine/cli/app.py`** — Add `codex` as provider choice

```python
@click.option("--provider", "-p", type=click.Choice(["gemini", "claude", "codex"]))
```

**File: `avatar_engine/cli/commands/health.py`** — Add Codex CLI check

```python
# Check codex-acp availability
if shutil.which("npx"):
    # Try: npx @zed-industries/codex-acp --version
```

### Phase 4: Tests (MEDIUM priority)

**File: `tests/test_codex_bridge.py`** — Unit tests

- Test CodexBridge constructor with all parameter combinations
- Test ACP lifecycle mocking (initialize → authenticate → new_session → prompt)
- Test text extraction from AgentMessageChunk
- Test thinking extraction from AgentThoughtChunk
- Test tool call event mapping
- Test approval auto-accept callback
- Test error handling (auth failure, session failure, timeout)
- Test cleanup on stop

**File: `tests/integration/test_real_codex.py`** — Integration tests

- Real codex-acp communication (requires installed binary + auth)
- Marked with `@pytest.mark.codex`

### Phase 5: Documentation (LOW priority)

- Update README.md with Codex provider
- Update examples/ with Codex usage
- Update install.sh with Codex CLI check

---

## 4. Dependency Changes

### pyproject.toml

No new dependencies needed — uses the same `agent-client-protocol` package
already required for Gemini ACP.

### Prerequisites (user-installed)

```bash
# codex-acp adapter (the ACP bridge)
npm install -g @zed-industries/codex-acp

# Authenticate (one-time, browser login)
codex login
```

---

## 5. Config Sandbox (Zero Footprint)

Codex ACP does NOT require writing config files to the project directory.
Configuration is passed through:

1. **Environment variables** — `CODEX_API_KEY`, `OPENAI_API_KEY`
2. **ACP protocol** — MCP servers passed in `new_session()`, not files
3. **CLI arguments** — Config overrides via `-c key=value`

The Zero Footprint pattern is naturally satisfied — no ConfigSandbox needed
for Codex (unlike Gemini which requires `.gemini/settings.json` in sandbox).

---

## 6. Event Mapping

### Codex ACP → Avatar Engine Events

| Codex ACP Update | Avatar Engine Event | Notes |
|------------------|-------------------|-------|
| `AgentMessageChunk` | `TextEvent` | Streaming text |
| `AgentThoughtChunk` | `ThinkingEvent` | Reasoning/thinking |
| `ToolCall` (started) | `ToolEvent(status="started")` | Tool invocation |
| `ToolCallUpdate` (completed) | `ToolEvent(status="completed")` | Tool result |
| `ToolCallUpdate` (failed) | `ToolEvent(status="failed")` | Tool error |
| `RequestPermission` | `ToolEvent(status="approval")` | Permission request |
| `Plan` | (logged, not emitted) | Agent's task plan |
| StopReason::EndTurn | `StateEvent(READY)` | Turn complete |
| Error | `ErrorEvent` | Error |

---

## 7. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| codex-acp requires Rust build from source | HIGH | Use npm distribution: `npx @zed-industries/codex-acp` |
| ChatGPT auth requires browser | MEDIUM | Support `codex-api-key` and `openai-api-key` as alternatives |
| ACP protocol version mismatch | MEDIUM | Pin `agent-client-protocol` version, test compatibility |
| codex-acp is external dependency (Zed) | LOW | It's open-source Apache-2.0, can fork if needed |
| No oneshot fallback | LOW | codex-acp IS the integration layer; no fallback needed |
| Approval flow blocks non-interactive use | HIGH | Auto-approve callback in ACP client (like GeminiBridge yolo) |

---

## 8. Implementation Order

1. `avatar_engine/bridges/codex.py` — CodexBridge class
2. `avatar_engine/types.py` — Add `CODEX` to ProviderType
3. `avatar_engine/engine.py` — Add Codex to `_create_bridge()`
4. `avatar_engine/config.py` — Add `codex_config` property
5. `avatar_engine/bridges/__init__.py` — Export CodexBridge
6. `avatar_engine/__init__.py` — Public API export
7. `.avatar.yaml` — Add codex section (commented out)
8. `avatar_engine/cli/app.py` — Add codex to provider choices
9. `tests/test_codex_bridge.py` — Unit tests
10. `tests/integration/test_real_codex.py` — Integration tests
11. `plans/docs/README.md` — Already updated
12. `README.md` — Add Codex to provider list
13. `install.sh` — Add codex-acp check

---

## 9. Reference: GeminiBridge as Template

The CodexBridge implementation should closely mirror GeminiBridge's ACP code
path (`_start_acp`, `_send_acp`, `_cleanup_acp`) with these substitutions:

| GeminiBridge | CodexBridge |
|-------------|-------------|
| `gemini --experimental-acp --yolo` | `npx @zed-industries/codex-acp` |
| `authenticate(oauth-personal)` | `authenticate(chatgpt)` |
| `_extract_text_from_update()` | Parse `AgentMessageChunk.content.text` |
| `_extract_thinking_from_update()` | Parse `AgentThoughtChunk.content.text` |
| `_handle_acp_update()` | Handle `SessionNotification` typed updates |
| generation_config → settings.json | Config via `-c key=value` args or session options |

---

## 10. Success Criteria

- [x] `avatar chat -p codex "Hello"` works end-to-end
- [x] `avatar repl -p codex` supports multi-turn conversation
- [x] Streaming text output works in real-time
- [x] Tool calls (exec, patch) emit ToolEvent with correct status
- [x] Thinking/reasoning emits ThinkingEvent
- [x] Auto-approval works for non-interactive use
- [x] MCP servers are passed to codex-acp session
- [x] All existing tests pass (no regressions)
- [x] New unit tests cover CodexBridge lifecycle
- [x] Integration test confirms real codex-acp communication

---

## Implementation Status: DONE (2026-02-07)

Všechny fáze implementovány:

| Fáze | Soubor | Stav |
|------|--------|------|
| 1 | `avatar_engine/bridges/codex.py` — CodexBridge (ACP-only) | DONE |
| 2a | `avatar_engine/types.py` — ProviderType.CODEX | DONE |
| 2b | `avatar_engine/engine.py` — _create_bridge() + config | DONE |
| 2c | `avatar_engine/bridges/__init__.py` + `__init__.py` — exports | DONE |
| 3 | `avatar_engine/cli/` — codex as provider choice + health | DONE |
| 4 | `tests/test_codex_bridge.py` + `tests/integration/test_real_codex.py` | DONE |
| 5 | `README.md`, `examples/`, `install.sh` | DONE |

Session management (resume, continue, list) for Codex also implemented — see SESSION_MANAGEMENT_PLAN.md.

**Finální stav testů:** 561+ testů, all PASS.
