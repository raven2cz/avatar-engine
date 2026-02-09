# Phase 7: Web GUI Demo — Avatar Engine Web Bridge + Reference React App

> Created: 2026-02-07
> Status: DONE (2026-02-09)
> Replaces: GUI_READINESS_PLAN.md section 17 (Textual TUI) + Fáze 7

---

## Context

Phase 7 was originally planned as a Python Textual TUI. This is **wrong** — the primary consumer of Avatar Engine is **Synapse** (and similar web apps), which uses:
- **Backend:** Python FastAPI + uvicorn
- **Frontend:** React 18 + Vite + TanStack Query + TailwindCSS + Lucide icons
- **Communication:** REST API (fetch), useQuery/useMutation hooks

Avatar Engine needs a **web bridge** that exposes AvatarEngine over HTTP/WebSocket, and a **reference React demo** showing how to consume the event stream. This is the library's primary use case.

Phases 1-6 (events, activity tracking, CLI display, system prompt, budget, diagnostics, capabilities) are done and correct — the event system is exactly what a web GUI needs. Phase 7 adds the transport layer.

---

## Shared Components from CLI Display Rewrite (CRITICAL — reuse, don't reimplement)

The CLI display rewrite (`cli/display.py`) built **transport-agnostic state machines** that
the web bridge MUST reuse. The event → state logic is identical; only the rendering differs
(Rich terminal vs JSON/WebSocket).

### What exists in `cli/display.py`

| Component | Class | State it manages | Events consumed |
|-----------|-------|-----------------|----------------|
| Thinking state | `ThinkingDisplay` | `active`, `subject`, `phase`, `start_time`, spinner frame | `ThinkingEvent` (start/update/complete) |
| Tool groups | `ToolGroupDisplay` | `tools` dict (name→status), `group_start_time`, `active_count` | `ToolEvent` (started/completed/failed) |
| Engine state | `DisplayManager` | `state: EngineState`, `has_active_status`, registered handlers | `ThinkingEvent`, `ToolEvent`, `ErrorEvent`, `StateEvent` |

### How the web bridge should consume them

The `DisplayManager` pattern is **subscribe to events → update internal state → render**.
The web bridge follows the same pattern but renders to JSON over WebSocket:

```
CLI:     Engine → EventEmitter → DisplayManager → Rich Console (terminal)
Web:     Engine → EventEmitter → WebSocketBridge → JSON → WebSocket → React
```

**`WebSocketBridge._on_event()` should mirror `DisplayManager`'s event handlers:**

```python
# cli/display.py (existing):
@engine.on(ThinkingEvent)
def _on_thinking(self, event):
    if event.is_complete:
        self.thinking.deactivate()
    else:
        self.thinking.activate(event.subject, event.phase)

# web/bridge.py (new — same logic, different output):
@engine.on(ThinkingEvent)
def _on_thinking(self, event):
    self._broadcast({
        "type": "thinking",
        "data": {
            "thought": event.thought,
            "subject": event.subject,
            "phase": event.phase.value if event.phase else "general",
            "is_start": event.is_start,
            "is_complete": event.is_complete,
            "block_id": event.block_id,
        }
    })
```

### Shared state machines to extract (consider refactoring)

During implementation, consider extracting the **state logic** from `DisplayManager` into
a transport-agnostic base that both CLI and web can inherit:

```python
# Possible future refactor (not required for v1):
class BaseDisplayState:
    """Transport-agnostic event → state machine."""
    thinking: ThinkingDisplay
    tools: ToolGroupDisplay
    state: EngineState

    def _on_thinking(self, event: ThinkingEvent): ...
    def _on_tool(self, event: ToolEvent): ...
    def _on_error(self, event: ErrorEvent): ...

class TerminalDisplay(BaseDisplayState):
    """Rich terminal rendering."""
    def render(self): ...  # Rich Console output

class WebSocketDisplay(BaseDisplayState):
    """JSON/WebSocket rendering."""
    def render(self): ...  # broadcast JSON
```

For v1, just mirror the handlers. Refactor to shared base in v2 if needed.

### Key implementation notes from CLI experience

1. **ThinkingEvent lifecycle**: `is_start=True` → N updates with `subject` → `is_complete=True`.
   The web client needs to handle missing `is_start` (Codex sometimes skips it).
2. **ThinkingEvent.subject**: Extracted from `**Bold Text**` markers in thinking stream.
   Both Gemini and Codex use this pattern. The subject changes dynamically during thinking.
3. **Fallback "Thinking..."**: When no `ThinkingEvent` is emitted (some providers skip it),
   `DisplayManager.advance_spinner()` shows generic "Thinking..." — web should do the same.
4. **Codex thinking-as-response**: Codex sends entire responses as `AgentThoughtChunk` only
   (no `AgentMessageChunk`). The bridge reconstructs content from thinking events.
   Web client should handle `chat_response` with content that came from thinking.
5. **ToolEvent grouping**: Tools arrive as individual events but should be displayed as groups.
   `ToolGroupDisplay` handles this with a dict keyed by `tool_id`. React `ToolActivity`
   component should use the same grouping logic.
6. **EngineState transitions**: IDLE → THINKING → RESPONDING → IDLE (normal flow).
   Can also go THINKING → ERROR. Web `StatusBar` should show these states.
7. **Event order**: ThinkingEvent always comes before TextEvent. ToolEvent can interleave.
   `is_complete=True` on ThinkingEvent fires before first text chunk.

---

## Architecture

```
avatar_engine/
  web/                          # NEW — Web bridge module
    __init__.py                 # create_app() factory, exports
    protocol.py                 # Event → JSON serialization
    bridge.py                   # AvatarEngine events → WebSocket adapter
    session_manager.py          # Engine lifecycle for web server
    server.py                   # FastAPI app with REST + WebSocket routes
    __main__.py                 # python -m avatar_engine.web

examples/
  web-demo/                     # NEW — Reference React app
    package.json                # React 18 + Vite + Tailwind + Lucide
    vite.config.ts
    tailwind.config.js
    index.html
    src/
      main.tsx
      App.tsx
      api/
        types.ts                # TypeScript event types (mirrors protocol.py)
        client.ts               # REST API client
      hooks/
        useAvatarWebSocket.ts   # WS connection + event dispatch (useReducer)
        useAvatarChat.ts        # Chat state management (messages array)
      components/
        ChatPanel.tsx           # Message list + input
        MessageBubble.tsx       # Single message (user/assistant)
        ThinkingIndicator.tsx   # AI thinking phase + subject + spinner
        ToolActivity.tsx        # Tool executions with status icons
        StatusBar.tsx           # Connection, provider, engine state, capabilities
        CostTracker.tsx         # Usage/budget (only when cost_tracking=true)
```

---

## WebSocket Protocol

### Server → Client

Every message: `{"type": "<event_type>", "data": {...}}`

| type | data | source |
|------|------|--------|
| `connected` | `{session_id, provider, capabilities}` | on WS open |
| `text` | `{text, is_complete, timestamp, provider}` | TextEvent |
| `thinking` | `{thought, phase, subject, is_start, is_complete, block_id, ...}` | ThinkingEvent |
| `tool` | `{tool_name, tool_id, parameters, status, result, error}` | ToolEvent |
| `state` | `{old_state, new_state}` | StateEvent |
| `cost` | `{cost_usd, input_tokens, output_tokens}` | CostEvent |
| `error` | `{error, recoverable}` | ErrorEvent |
| `diagnostic` | `{message, level, source}` | DiagnosticEvent |
| `activity` | `{activity_id, name, status, progress, ...}` | ActivityEvent |
| `chat_response` | `{content, success, error, duration_ms}` | after chat() completes |

### Client → Server

| type | data |
|------|------|
| `chat` | `{message: "..."}` |
| `stop` | `{}` |
| `ping` | `{}` |
| `clear_history` | `{}` |

---

## Python Implementation (avatar_engine/web/)

### Step 1: `protocol.py` — Event serialization

```python
EVENT_TYPE_MAP = {
    TextEvent: "text",
    ThinkingEvent: "thinking",
    ToolEvent: "tool",
    # ... all 8 event types
}

def event_to_ws_message(event: AvatarEvent) -> Optional[dict]:
    """Convert AvatarEvent → {"type": "...", "data": {...}}"""
    # dataclasses.asdict() + enum.value for string serialization
```

### Step 2: `bridge.py` — WebSocket event adapter

- `WebSocketBridge(engine)` — registers per-event-type handlers (mirrors `DisplayManager` pattern from `cli/display.py`)
- Maintains set of connected WS clients
- Handler registration: same `@engine.on(ThinkingEvent)`, `@engine.on(ToolEvent)` pattern as CLI
- `_on_event()` is sync (EventEmitter callback) → uses `asyncio.create_task()` for async WS send
- `_broadcast()` fans out to all clients, removes dead ones
- Thread-safe with `asyncio.Lock`
- **IMPORTANT**: Reference `cli/display.py:DisplayManager.__init__()` for the complete list of event handlers — web bridge needs the same set

### Step 3: `session_manager.py` — Engine lifecycle

- `EngineSessionManager(provider, model, config_path, ...)` — creates & manages AvatarEngine
- `ensure_started()`, `shutdown()` — lifecycle
- Exposes `.engine` and `.ws_bridge` properties

### Step 4: `server.py` — FastAPI routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/avatar/health` | Health check |
| GET | `/api/avatar/capabilities` | Provider capabilities |
| GET | `/api/avatar/sessions` | List sessions |
| GET | `/api/avatar/history` | Conversation history |
| GET | `/api/avatar/usage` | Usage/cost stats |
| POST | `/api/avatar/chat` | Non-streaming chat |
| POST | `/api/avatar/stop` | Stop engine |
| POST | `/api/avatar/clear` | Clear history |
| WS | `/api/avatar/ws` | Bidirectional streaming |

- `create_app()` factory function — configurable provider, CORS origins, etc.
- CORS middleware for React dev server (localhost:5173)
- Startup/shutdown lifecycle hooks

### Step 5: `__main__.py` — CLI entry point

```bash
python -m avatar_engine.web --provider gemini --port 8420
# or
avatar-web --provider claude --port 8420
```

### Step 6: `pyproject.toml` changes

```toml
[project.optional-dependencies]
web = ["fastapi>=0.100", "uvicorn[standard]>=0.20"]

[project.scripts]
avatar-web = "avatar_engine.web.__main__:main"
```

---

## React Implementation (examples/web-demo/)

### Hooks

**`useAvatarWebSocket(url)`** — Core hook:
- Connects to WS, receives events
- `useReducer` for state (connected, thinking, tools, cost, engineState)
- Returns state + `sendMessage()` function
- No external dependencies (pure React)

**`useAvatarChat(wsUrl)`** — Chat layer on top:
- Manages `messages[]` array (user + assistant)
- Accumulates text from TextEvent into current assistant message
- Tracks tools/thinking per message
- Returns `{messages, sendMessage, isStreaming, ...avatarState}`

### Components

- **ChatPanel**: Message list with auto-scroll, input with Enter-to-send
- **MessageBubble**: User (right, blue) / Assistant (left, gray), pre-wrap text
- **ThinkingIndicator**: CSS-animated spinner, phase label, subject, elapsed time, color-coded by phase
- **ToolActivity**: Tool list with status icons, name, params summary, elapsed time
- **StatusBar**: Connection dot, provider badge, engine state, capability pills
- **CostTracker**: Total USD, token counts (hidden when no cost_tracking)

### Dependencies (minimal)

```json
"dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "lucide-react": "^0.300.0"
}
```

TailwindCSS for styling. No TanStack Query (WS hook handles state). Same stack as Synapse.

---

## Implementation Order

| # | What | Files |
|---|------|-------|
| 1 | Event protocol | `web/protocol.py` |
| 2 | WS bridge adapter | `web/bridge.py` |
| 3 | Session manager | `web/session_manager.py` |
| 4 | FastAPI server | `web/server.py`, `web/__init__.py` |
| 5 | CLI entry point | `web/__main__.py` |
| 6 | pyproject.toml | Add `[web]` deps, script |
| 7 | Unit tests (protocol) | `tests/test_web_protocol.py` |
| 8 | Unit tests (bridge) | `tests/test_web_bridge.py` |
| 9 | Unit tests (server) | `tests/test_web_server.py` |
| 10 | Integration tests | `tests/integration/test_real_web.py` |
| 11 | React scaffold | `examples/web-demo/` package.json, vite, tailwind |
| 12 | TS types | `src/api/types.ts` |
| 13 | Hooks | `src/hooks/useAvatarWebSocket.ts`, `useAvatarChat.ts` |
| 14 | Components | `src/components/*.tsx` |
| 15 | App assembly | `src/App.tsx`, `src/main.tsx` |

Steps 1-10 (Python) first, then 11-15 (React). Steps 7-10 can overlap with 4-6.

---

## Testing Strategy

### Unit tests (~25 tests)

- **test_web_protocol.py**: All 8 event types serialize to JSON, enums become strings, unknown events return None, client message parsing
- **test_web_bridge.py**: Client add/remove, broadcast fan-out, dead client cleanup, event forwarding (mock WS)
- **test_web_server.py**: All REST endpoints via httpx TestClient, WS connect/chat/ping via TestClient

### Integration tests (~5 tests)

- **test_real_web.py**: Real provider, real `create_app()`, test health/chat/WS with httpx + websockets lib

---

## Avatar Emotion States & Visual System

The avatar (Galaxy Spiral orb) changes color, spin speed, and glow based on the AI's
current state. This section documents all states, their sources, and visual mappings.

### EngineState (what the AI is doing)

These are the high-level states driven by `EngineState` enum (`avatar_engine/events.py`).
The WebSocket bridge tracks these and emits `engine_state` messages to the frontend.

| EngineState | Description | Visual | When |
|---|---|---|---|
| `idle` | Waiting for user input | Slow spin (14s), indigo-violet | Default / after response complete |
| `thinking` | Model is reasoning | Fast spin (8s), phase-specific color | ThinkingEvent received (Gemini, Codex native) |
| `responding` | Generating text output | Fast spin, light indigo-violet | ThinkingEvent.is_complete → first TextEvent |
| `tool_executing` | Running a tool/function | Fast spin, amber-orange-red | ToolEvent(status=started) |
| `waiting_approval` | Awaiting user tool approval | Slow pulse, amber | ToolPolicy requires approval (defined, rarely used) |
| `error` | Something went wrong | Red-orange-yellow glow | ErrorEvent / StateEvent(ERROR) |

### ThinkingPhase (sub-state of `thinking`)

When `EngineState == thinking`, the `ThinkingPhase` provides finer granularity.
Phases are **heuristically classified** from thinking text content by `classify_thinking()`
in `events.py` — providers don't send explicit phase metadata.

| ThinkingPhase | Keyword triggers | Color scheme (c1, c2, c3) | Example subjects |
|---|---|---|---|
| `general` | (fallback — no match) | `#6366f1, #8b5cf6, #a78bfa` (indigo-violet) | Generic thinking |
| `analyzing` | analyz, look at, examin, reading, inspect | `#06b6d4, #3b82f6, #8b5cf6` (cyan-blue-violet) | "Analyzing error logs", "Reading config" |
| `planning` | plan, approach, strategy, steps, design | `#8b5cf6, #c084fc, #e879f9` (violet-purple-fuchsia) | "Planning implementation", "Design approach" |
| `coding` | write, implement, code, function, class, def | `#10b981, #06b6d4, #34d399` (emerald-cyan-green) | "Writing function", "Implementing handler" |
| `reviewing` | check, verify, review, test, validate | `#f59e0b, #f97316, #fbbf24` (amber-orange-yellow) | "Reviewing changes", "Validating output" |
| `tool_planning` | tool, call, execut, run, invok | `#f59e0b, #f97316, #ef4444` (amber-orange-red) | "Using read_file", "Calling API" |

### Provider Support Matrix

| Provider | Native thinking events | ThinkingPhase classification | Synthetic events |
|---|---|---|---|
| **Gemini** | Yes (`thinking_supported=True`) | Full — all 6 phases via `classify_thinking()` | None |
| **Codex** | Yes (`thinking_supported=True`) | Full — all 6 phases via `classify_thinking()` | None |
| **Claude** | No (`thinking_supported=False`) | N/A — Claude CLI doesn't export thinking | Synthetic `tool_planning` when tools are used (engine.py:649-657) |

### Additional UI States (not from ThinkingPhase)

| State | Color scheme | When | Source |
|---|---|---|---|
| `responding` | `#818cf8, #a78bfa, #c084fc` (light indigo) | AI is generating text | EngineState.RESPONDING |
| `success` | `#22c55e, #10b981, #06b6d4` (green-emerald-cyan) | Chat completed successfully | UI feedback (frontend only) |
| `error` | `#ef4444, #f97316, #fbbf24` (red-orange-yellow) | Error occurred | ErrorEvent |

### Complete Color Map (for avatar bust expansion)

All 11 visual states with their exact hex colors for the Galaxy Spiral avatar:

```typescript
const PHASE_COLORS = {
  // Idle / default
  general:       { c1: '#6366f1', c2: '#8b5cf6', c3: '#a78bfa' },  // indigo-violet
  idle:          { c1: '#6366f1', c2: '#8b5cf6', c3: '#a78bfa' },  // indigo-violet

  // Active thinking phases (heuristic-classified)
  thinking:      { c1: '#3b82f6', c2: '#6366f1', c3: '#06b6d4' },  // blue-indigo-cyan
  analyzing:     { c1: '#06b6d4', c2: '#3b82f6', c3: '#8b5cf6' },  // cyan-blue-violet
  planning:      { c1: '#8b5cf6', c2: '#c084fc', c3: '#e879f9' },  // violet-purple-fuchsia
  coding:        { c1: '#10b981', c2: '#06b6d4', c3: '#34d399' },  // emerald-cyan-green
  reviewing:     { c1: '#f59e0b', c2: '#f97316', c3: '#fbbf24' },  // amber-orange-yellow
  tool_planning: { c1: '#f59e0b', c2: '#f97316', c3: '#ef4444' },  // amber-orange-red

  // Engine states (not thinking sub-phases)
  responding:    { c1: '#818cf8', c2: '#a78bfa', c3: '#c084fc' },  // light indigo
  success:       { c1: '#22c55e', c2: '#10b981', c3: '#06b6d4' },  // green-emerald-cyan
  error:         { c1: '#ef4444', c2: '#f97316', c3: '#fbbf24' },  // red-orange-yellow
}
```

### State Machine Flow

```
User sends message
  └─→ IDLE ─→ THINKING (phase: general/analyzing/planning/coding/reviewing)
                 │
                 ├─→ TOOL_EXECUTING ─→ back to THINKING
                 │     (tool_planning phase before tool starts)
                 │
                 └─→ RESPONDING ─→ IDLE
                       (text generation)     (success)
                                       OR ─→ ERROR
```

### Galaxy Spiral Behavior Per State

| State | Spin speed | Core glow | Star behavior |
|---|---|---|---|
| idle/general | 14s per revolution | Gentle breathe | Slow twinkle |
| thinking/* | 8s per revolution | Faster breathe | Quick twinkle |
| responding | 8s per revolution | Bright glow | Active twinkle |
| error | 8s per revolution | Red pulsing | Agitated twinkle |

### Frontend Dependencies (updated)

```json
"dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "lucide-react": "^0.300.0",
    "react-markdown": "^9.0.0",
    "react-syntax-highlighter": "^15.6.0",
    "remark-gfm": "^4.0.0"
},
"devDependencies": {
    "@types/react-syntax-highlighter": "^15.5.0"
}
```

### Future: Avatar Bust Expansion

The Galaxy Spiral is the Phase 7 logo/avatar. For Phase 8+, actual avatar busts
(face, expression, pose) can be added. The emotion system is ready:

1. **State source**: `EngineState` + `ThinkingPhase` from WebSocket events
2. **Color palette**: 11 distinct schemes (see Complete Color Map above)
3. **Animation speed**: `isActive` flag (idle=slow, all others=fast)
4. **Transition hook**: `phase` prop changes trigger React re-render with new colors
5. **Bust mapping**: Each of the 11 states should map to a distinct facial expression,
   head tilt, eye movement, or other visual cue in the avatar bust

Recommended bust expressions per state:
| State | Expression | Pose | Eyes |
|---|---|---|---|
| idle | Neutral, slight smile | Straight ahead | Open, calm |
| thinking | Focused, slight frown | Slight head tilt | Narrowed, looking up |
| analyzing | Concentrated | Head tilted, hand on chin | Scanning left-right |
| planning | Thoughtful | Looking up-right | Half-closed, contemplating |
| coding | Determined | Leaning forward | Focused, looking down |
| reviewing | Critical | Head slightly back | Squinting, evaluating |
| tool_planning | Alert | Turning to side | Wide, anticipating |
| responding | Friendly | Facing user | Open, warm |
| success | Happy | Slight nod | Bright, satisfied |
| error | Concerned | Slight head shake | Worried, apologetic |

---

## Key Design Decisions

1. **One engine per server** — matches Synapse pattern (one user session). Multi-tenant is out of scope.
2. **WebSocket for streaming** (not SSE) — bidirectional needed for chat + stop + ping.
3. **JSON protocol** — simple, debuggable, small payloads (<1KB per event).
4. **No state management lib** in React demo — pure useReducer. Synapse can wrap in TanStack Query.
5. **Optional dependency** — `pip install avatar-engine[web]` adds FastAPI + uvicorn only.

---

## Verification

1. `uv run pytest tests/test_web_*.py -x -q` — unit tests pass
2. `uv run pytest tests/integration/test_real_web.py -v` — integration tests pass
3. Manual: `python -m avatar_engine.web --provider gemini` → open `http://localhost:8420/api/avatar/health` → JSON response
4. Manual: `cd examples/web-demo && pnpm install && pnpm dev` → open browser → type message → see streaming response with thinking/tool visualization
5. `uv run pytest tests/ -x -q --ignore=tests/integration` — all existing unit tests still pass

---

## Critical Files to Modify/Read

- `avatar_engine/events.py` — All 8 event types (TextEvent, ThinkingEvent, ToolEvent, StateEvent, CostEvent, ErrorEvent, DiagnosticEvent, ActivityEvent) + EventEmitter + EngineState enum
- `avatar_engine/engine.py` — AvatarEngine.chat(), chat_stream(), capabilities, health, on() decorator
- `avatar_engine/types.py` — BridgeResponse, ProviderCapabilities, HealthStatus, ToolPolicy
- `avatar_engine/activity.py` — ActivityTracker, ActivityStatus — needed for activity event serialization
- `avatar_engine/cli/display.py` — **PRIMARY REFERENCE** — ThinkingDisplay, ToolGroupDisplay, DisplayManager show exactly how events drive UI state. Web bridge handlers should mirror these.
- `avatar_engine/cli/commands/repl.py` — Reference for spinner loop pattern (`_animate_spinner()`), response lifecycle (`on_response_start/end`), and how display integrates with chat flow
- `avatar_engine/cli/commands/chat.py` — Reference for one-shot chat with spinner, `_run_async_clean()` for subprocess cleanup
- `pyproject.toml` — Add [web] optional deps
- `avatar_engine/__init__.py` — Add web exports

---

## Implementation Log: Provider & Model Selector (2026-02-09)

### Status: ✅ DONE

Runtime provider/model switching from web UI dropdown.

### What was implemented

#### Backend

**`web/protocol.py`** — Added `"switch"` to allowed client message types:
```python
if msg_type not in ("chat", "stop", "ping", "clear_history", "switch"):
    return None
```

**`web/session_manager.py`** — `switch(provider, model)` method:
- Saves connected WS clients from old bridge before shutdown
- Updates `_provider` / `_model`, calls `shutdown()` + `start()`
- Transfers saved clients to the new bridge via `add_client()`
- On failure: reverts provider/model, restarts old settings, restores clients

**`web/server.py`** — WebSocket `"switch"` handler:
- Calls `manager.switch(provider, model)`
- Re-sets bridge event loop after restart: `bridge.set_loop(asyncio.get_running_loop())`
- Broadcasts `"connected"` message with new provider/model/capabilities to ALL clients
- On error: broadcasts error + recovery `"connected"` message with current state
- `_run_chat` uses `manager.engine` / `manager.ws_bridge` (not stale local vars)
- `asyncio.wait_for(eng.chat(msg), timeout=120)` safety timeout
- Never-silent errors: direct WS fallback when bridge unavailable
- `task.add_done_callback()` for unhandled exceptions in fire-and-forget chat tasks

#### Frontend

**`src/config/providers.ts`** — NEW, centralized provider/model config:
```typescript
export const PROVIDERS: ProviderConfig[] = [
  { id: 'gemini', label: 'Gemini', defaultModel: 'gemini-3-pro-preview',
    models: ['gemini-3-pro-preview', 'gemini-3-flash-preview', 'gemini-2.5-flash', ...] },
  { id: 'claude', label: 'Claude', defaultModel: 'claude-opus-4-6',
    models: ['claude-opus-4-6', 'claude-sonnet-4-5', 'claude-haiku-4-5'] },
  { id: 'codex', label: 'Codex', defaultModel: 'gpt-5.3-codex',
    models: ['gpt-5.3-codex', 'gpt-5.2-codex', 'gpt-5.1-codex-mini'] },
]
```

**`src/components/ProviderModelSelector.tsx`** — NEW, dropdown component:
- Provider rows with colored dots and "current" label
- Model quick-picks from config + custom text input
- "(default)" label next to default model
- Closes on click-outside or Escape
- Loading overlay with spinner during switch

**`src/hooks/useAvatarWebSocket.ts`**:
- Added `switching: boolean` state + `SWITCHING` action
- `CONNECTED` action clears `switching` flag
- `switchProvider(provider, model?)` sends `{type: "switch", data: {...}}`

**`src/hooks/useAvatarChat.ts`**:
- Exposed `switchProvider` + `switching` in return interface
- `switchProvider` clears messages (new engine = new conversation)
- 30s frontend chat timeout (`chatTimeoutRef`)

**`src/components/StatusBar.tsx`**:
- `switching` + `onSwitch` optional props
- Interactive `ProviderModelSelector` replaces static badge when `onSwitch` provided
- Uses `getProvider()` from centralized config
- Removed static "Thinking" capability badge (confusing vs engine state)

**`src/App.tsx`** — Wires `switchProvider` + `switching` to StatusBar

**`src/api/types.ts`** — Added `SwitchRequest` type

**`src/index.css`** — `.glass-panel` class (darker dropdown backgrounds, 0.92 opacity, 32px blur)

#### Tests

**`tests/test_web_integration.py`** — 5 new switch tests:
- `test_ws_switch_sends_connected_message` — switch calls manager + broadcasts connected
- `test_ws_switch_missing_provider_returns_error` — missing provider → error
- `test_ws_switch_failure_broadcasts_error` — switch exception → error + recovery
- `test_switch_preserves_clients` — clients transfer from old to new bridge
- `test_switch_reverts_on_failure` — provider/model revert on start failure

### Bug Fixes

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| **Claude chat hangs forever** | `ClaudeBridge.start()` never creates `_stderr_task` — stderr buffer fills → subprocess blocks → stdout blocks → `_read_until_turn_complete()` hangs | Added `self._stderr_task = asyncio.create_task(self._monitor_stderr())` to `bridges/claude.py:168` |
| **Claude response invisible in GUI** | React 18 automatic batching: `setMessages(updater)` enqueued → `currentAssistantIdRef.current = null` runs sync → updater reads null ref → returns prev unchanged | Capture ref into local variable BEFORE `setMessages` call, not inside updater |
| **Switch broadcasts to empty set** | `session_manager.shutdown()` destroys old bridge (with clients), `start()` creates new bridge with 0 clients | Save clients before shutdown, transfer to new bridge after start |
| **Stale references in server.py** | `_run_chat` closure captured local `engine`/`bridge` vars that become stale after switch | Read from `manager.engine`/`manager.ws_bridge` at execution time |
| **Silent chat failures** | `_run_chat` returned silently when engine/bridge unavailable | Always send error via WS, log error, add task done callback |
| **asyncio deprecation** | `asyncio.get_event_loop()` raises RuntimeError in Python 3.14 | Changed to `asyncio.run()` in test helper |
| **MagicMock in JSON** | Test mock `engine._bridge._model` auto-created as MagicMock, not serializable | Set explicitly to None in mock setup |

### End-to-End Verification

All verified 2026-02-09:
- ✅ Gemini start → chat → switch to Claude → chat with Claude → response displayed
- ✅ Direct WS test on port 8420 (bypassing proxy)
- ✅ Vite proxy WS test on port 5173 (same path as browser)
- ✅ 52 unit tests pass (`test_web_server.py` + `test_web_integration.py`)
- ✅ TypeScript clean (`npx tsc --noEmit`)
- ✅ Provider dropdown UI: select provider → pick model → "Switching..." → new connected

---

## Model Sub-Options Analysis (2026-02-09)

### Status: DONE

User wants model sub-options (thinking mode, temperature, etc.) selectable from the GUI.

### What each provider supports

| Parameter | Claude | Gemini | Codex |
|-----------|--------|--------|-------|
| Temperature | ❌ Not exposed | ✅ `generation_config.temperature` | ❌ Not exposed |
| Max tokens | ❌ Not exposed | ✅ `generation_config.max_output_tokens` | ❌ Not exposed |
| Thinking mode | ❌ `thinking_supported=False` | ✅ `generation_config.thinking_level` (minimal/low/medium/high) | ❌ Sends thinking but no control |
| Include thoughts | — | ✅ `generation_config.include_thoughts` (bool) | — |
| Top-P / Top-K | ❌ | ✅ via `generation_config` | ❌ |
| Reasoning effort | ❌ | — | ❌ Not exposed |
| Max turns | ✅ `max_turns` (cost control) | — | — |
| Budget USD | ✅ `max_budget_usd` | — | — |
| Permission mode | ✅ `permission_mode` | — | — |
| Sandbox mode | — | — | ✅ `sandbox_mode` |

### How parameters flow

```
Config YAML → AvatarConfig → engine._create_bridge() → Bridge constructor → CLI flags / API params
```

Parameters are **set at bridge creation time** and **immutable** during session.
To change them, the entire bridge must be destroyed and recreated (`manager.switch()`).

### What's needed for GUI sub-options

1. **Extend `switch()` to accept `options: dict`** — pass through to engine/bridge constructor
2. **Extend WS `switch` message** — add `data.options` field
3. **Extend `EngineSessionManager`** — store `_options` dict, forward to bridge creation
4. **Frontend: Sub-option panel per provider** — show only relevant options:
   - Gemini: thinking_level dropdown, temperature slider, max_output_tokens
   - Claude: max_turns, max_budget_usd
   - Codex: sandbox_mode
5. **Provider config extension** — add `availableOptions` to `providers.ts`

### Architecture for sub-options

```
ProviderModelSelector dropdown:
  ├── Provider section (existing)
  ├── Model section (existing)
  └── Options section (NEW):
      ├── Gemini: [Thinking: high ▾] [Temp: 1.0] [Max tokens: 8192]
      ├── Claude: [Max turns: ∞] [Budget: $5.00]
      └── Codex:  [Sandbox: workspace-write ▾]
```

WS message becomes:
```json
{
  "type": "switch",
  "data": {
    "provider": "gemini",
    "model": "gemini-3-pro-preview",
    "options": {
      "thinking_level": "high",
      "temperature": 0.7,
      "max_output_tokens": 8192
    }
  }
}
```

### Files to modify

| File | Change |
|------|--------|
| `web/session_manager.py` | `switch()` accepts `options` dict, stores as `_options`, forwards to engine |
| `web/server.py` | Pass `options` from WS switch message to `manager.switch()` |
| `web/protocol.py` | Accept `options` field in switch message |
| `engine.py` | `_create_bridge()` merges options into bridge kwargs |
| `src/config/providers.ts` | Add `availableOptions` per provider |
| `src/components/ProviderModelSelector.tsx` | Options UI section per provider |
| `src/hooks/useAvatarWebSocket.ts` | `switchProvider` accepts options dict |
| `src/hooks/useAvatarChat.ts` | Forward options through |
| `src/api/types.ts` | Extend SwitchRequest with options |

---

## Implementation Log: Session GUI + History Display (2026-02-09)

### Status: DONE

Session management modal, session resume with history display for all 3 providers.

### What was implemented

See `plans/SESSION_GUI_PLAN.md` for full details.

**Summary:**

1. **Session Modal** — Centrovaný modal s backdrop, async loading, tabulkový layout (Title/ID/Updated)
2. **Session Resume** — WS `resume_session` + REST `/api/avatar/sessions/{id}/messages` pro historii
3. **Gemini Filesystem Resume** — `_find_session_file()` s glob-based vyhledáváním (timestamp-based filenames)
4. **Codex Filesystem Store** — NOVÝ `_codex.py` čte `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`
5. **All 3 providers** — session listing, resume, history display funguje pro Gemini, Claude, Codex
6. **Session Title Button** — History ikona + aktuální session title v StatusBar
7. **47 unit testů** pro všechny 3 filesystem stores

### Key bugs fixed

| Bug | Fix |
|-----|-----|
| Gemini filenames use `session-{timestamp}-{shortId}.json` not `session-{uuid}.json` | `_find_session_file()` with glob + JSON verification |
| Modal clipped by header stacking context | Overlays rendered outside `<header>` |
| Codex "Session listing not supported" | Set `can_list_sessions` on `_provider_capabilities` |
| Gemini startup timeout with `can_load=True` | Set AFTER `_create_or_resume_acp_session()` |
| History race condition on slow Gemini restart | Fetch immediately in `resumeSession()`, not on `connected` event |
