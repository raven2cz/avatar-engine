# Plan: Unified Session Management for All 3 Providers

## Context

Avatar-engine wraps 3 AI CLI providers (Gemini, Claude, Codex) but session management is inconsistent:

- **Claude bridge** — ALREADY has `--continue` and `--resume <id>` support (constructor params `continue_session`, `resume_session_id`), config reading in engine.py:424-437
- **Gemini bridge** — Always calls `new_session()` via ACP, ignores `load_session()`/`list_sessions()`/`resume_session()` methods available in ACP SDK
- **Codex bridge** — Same as Gemini — always `new_session()`, no resume support. **But codex-acp itself FULLY supports `load_session` + `list_sessions`** (see below)

Additionally: no CLI flags for session resume, no REPL commands for session browsing, no local session metadata persistence, no `avatar session list/resume` commands.

**Goal**: Unified session API across all providers — list, resume, continue, and persist session metadata.

---

## Key Findings from Research

### ACP Protocol (Gemini + Codex)

The ACP SDK (`acp/interfaces.py`) provides these session methods on `Agent`:
- `new_session(cwd, mcp_servers)` — create new (currently used)
- `load_session(cwd, mcp_servers, session_id)` — load existing session
- `resume_session(cwd, session_id, mcp_servers)` — resume with MCP reconnect
- `list_sessions(cursor, cwd)` — enumerate sessions → `ListSessionsResponse.sessions: List[SessionInfo]`
- `fork_session(cwd, session_id, mcp_servers)` — branch from existing

Agent advertises capabilities in `InitializeResponse.agent_capabilities`:
- `load_session: bool = False` (alias `loadSession`)
- `session_capabilities.list` / `session_capabilities.fork` — optional

`SessionInfo` from ACP: `session_id`, `cwd`, `title`, `updated_at`

### codex-acp Source Code Verification (`codex-acp/src/codex_agent.rs`)

**codex-acp inzeruje a plně implementuje session management:**

InitializeResponse (řádek 219-225):
```rust
let mut agent_capabilities = AgentCapabilities::new()
    .load_session(true);                          // ← load_session POVOLENO
agent_capabilities.session_capabilities =
    SessionCapabilities::new().list(SessionListCapabilities::new());  // ← list POVOLENO
```

Implementované ACP metody:
| Metoda | Řádky | Popis |
|--------|-------|-------|
| `new_session()` | 312-358 | Nová session, `thread_manager.start_thread(config)` |
| `load_session()` | 360-428 | `find_thread_path_by_id_str()` → `RolloutRecorder::get_rollout_history()` → `resume_thread_from_rollout()` → `replay_history()` |
| `list_sessions()` | 430-489 | `RolloutRecorder::list_threads()`, 25/page, pagination, filtr dle cwd, `ThreadSortKey::UpdatedAt` |
| `fork_session()` | — | NEIMPLEMENTOVÁNO |
| `resume_session()` | — | NEIMPLEMENTOVÁNO (řeší se přes `load_session`) |

Session persistence: rollout soubory v `codex_home` adresáři, `RolloutRecorder` pro ukládání/čtení.

**Avatar-engine to kompletně ignoruje a vždy volá jen `new_session()`.**

### Session Persistence — ALL 3 Providers AUTO-SAVE

**Žádný explicitní "save" není potřeba.** Všichni provideři persistují sessions automaticky:

| Provider | Kdy se ukládá | Kam | Formát |
|----------|--------------|-----|--------|
| **Codex** | Okamžitě po každé zprávě (`RolloutRecorder` → `file.flush()` po každém itemu) | `~/.codex/sessions/YYYY/MM/DD/rollout-...{SESSION_ID}.jsonl` | JSONL |
| **Gemini** | Automaticky na pozadí | `~/.gemini/` | Interní formát |
| **Claude** | Automaticky | `~/.claude/projects/<project-path>/` | Session JSON |

Sessions jsou **per-projekt** díky `cwd` parametru:
- `new_session(cwd=self.working_dir)` — uloží se s cestou k projektu
- `list_sessions(cwd=self.working_dir)` — vrátí jen sessions pro daný projekt
- codex-acp filtruje: `if item_cwd != filter_cwd { return None; }`

**Zero Footprint zachován**: sessions se ukládají do provider home dirs (`~/.codex/`, `~/.gemini/`, `~/.claude/`), NE do project directory.

### Claude CLI

Flags: `--continue`, `--resume <id>`, `--session-id <uuid>`, `--fork-session`
Avatar-engine ClaudeBridge already builds these (claude.py:229-233, 299-304).

### Gemini CLI

Has `--resume` flag and `/resume` interactive browser. Sessions auto-saved in `~/.gemini/`.

---

## Implementation Plan

### Phase 1: Types (`types.py`)

Add two new dataclasses:

```python
@dataclass
class SessionInfo:
    """Mirrors ACP SessionInfo — only fields providers actually return."""
    session_id: str
    provider: str          # "gemini" | "claude" | "codex"
    cwd: str = ""
    title: Optional[str] = None
    updated_at: Optional[str] = None   # ISO 8601

@dataclass
class SessionCapabilitiesInfo:
    """What session ops the bridge supports. Detected at runtime from ACP InitializeResponse."""
    can_list: bool = False             # ACP list_sessions / Claude: False
    can_load: bool = False             # ACP load_session / Claude --resume
    can_continue_last: bool = False    # ACP list+load combo / Claude --continue
```

Export from `__init__.py`.

**File**: `avatar_engine/types.py`

---

### Phase 2: Base Bridge Session Interface (`bridges/base.py`)

Add to `BaseBridge.__init__()`:
- `self._session_capabilities = SessionCapabilitiesInfo()`

Add new property + methods (with default implementations, NOT abstract):

```python
@property
def session_capabilities(self) -> SessionCapabilitiesInfo: ...

async def list_sessions(self) -> List[SessionInfo]:
    return []

async def resume_session(self, session_id: str) -> bool:
    raise NotImplementedError(f"{self.provider_name} does not support session resume")
```

**File**: `avatar_engine/bridges/base.py` (lines ~78-80 for init, new methods after line ~497)

---

### Phase 3: ACP Session Mixin (`bridges/_acp_session.py`) — NEW FILE

Since Gemini and Codex share identical ACP session logic, create a shared mixin:

```python
class ACPSessionMixin:
    """Shared ACP session management for Gemini and Codex bridges."""

    def _store_acp_capabilities(self, init_resp) -> None:
        """Parse InitializeResponse.agent_capabilities into SessionCapabilitiesInfo."""

    async def _create_or_resume_acp_session(self, mcp_servers_acp: list) -> str:
        """Session creation cascade: load_session → resume_session → new_session.
        Uses self.resume_session_id and self.continue_last to decide."""

    async def list_sessions(self) -> List[SessionInfo]:
        """ACP list_sessions with provider name injection."""

    async def resume_session(self, session_id: str) -> bool:
        """ACP load_session / resume_session cascade."""
```

The mixin expects `self._acp_conn`, `self._session_capabilities`, `self.working_dir`, `self.timeout`, `self.resume_session_id`, `self.continue_last` on the host class.

**File**: `avatar_engine/bridges/_acp_session.py` (NEW)

---

### Phase 4: GeminiBridge Session Support (`bridges/gemini.py`)

1. Add constructor params: `resume_session_id: Optional[str] = None`, `continue_last: bool = False`
2. Inherit `ACPSessionMixin`
3. In `_start_acp()` after `initialize()` (line ~217): call `self._store_acp_capabilities(init_resp)`
4. Replace unconditional `new_session()` (lines 263-271) with `self._create_or_resume_acp_session(mcp_servers_acp)`

**File**: `avatar_engine/bridges/gemini.py` (lines 70-80 constructor, 212-272 _start_acp)

---

### Phase 5: CodexBridge Session Support (`bridges/codex.py`)

Same pattern as Gemini. **codex-acp already advertises `load_session(true)` and `list_sessions`** — avatar-engine just needs to USE them:

1. Add `resume_session_id`, `continue_last` to constructor
2. Inherit `ACPSessionMixin`
3. In `_start_acp()` after `initialize()` (line ~216): call `self._store_acp_capabilities(init_resp)`
   - This will detect `load_session=true` and `session_capabilities.list` from codex-acp's response
4. Replace `new_session()` (lines 245-254) with `self._create_or_resume_acp_session(mcp_servers_acp)`
   - When `resume_session_id` is set: calls `self._acp_conn.load_session(session_id)` → codex-acp finds rollout file, replays history
   - When `continue_last` is set: calls `self._acp_conn.list_sessions()` → picks most recent → `load_session()`
   - Fallback: `new_session()` as before

Note: codex-acp does NOT implement `fork_session` or `resume_session` — only `load_session` (which internally handles both resumed and forked history).

**File**: `avatar_engine/bridges/codex.py` (lines 64-85 constructor, 210-254 _start_acp)

---

### Phase 6: ClaudeBridge — Set Capabilities (`bridges/claude.py`)

Claude already has `--continue`/`--resume` working. Just set capabilities flags:

In `__init__()` or `start()`:
```python
self._session_capabilities.can_resume = True
self._session_capabilities.can_continue_last = True
```

For `resume_session()` override — must stop and restart the persistent process with the new session ID:
```python
async def resume_session(self, session_id: str) -> bool:
    await self.stop()
    self.resume_session_id = session_id
    self.continue_session = False
    await self.start()
    return True
```

**File**: `avatar_engine/bridges/claude.py` (lines 70-80 init, add override)

---

### Phase 7: Session Store — ZJEDNODUŠENO (žádný vlastní soubor)

**Provideři persistují sessions automaticky** — nepotřebujeme duplicitní SessionStore.

Původní plán počítal s `~/.config/avatar-engine/sessions/` pro lokální metadata. Ale:
- **Codex**: `RolloutRecorder` ukládá okamžitě po každé zprávě do `~/.codex/sessions/`, `list_sessions()` vrací vše
- **Gemini**: auto-save do `~/.gemini/`, `list_sessions()` vrací vše
- **Claude**: auto-save do `~/.claude/projects/`, `--continue` přepínač

**Rozhodnutí**: `session_store.py` NEPOTŘEBUJEME pro první verzi. Stačí delegovat na providery:
- `list_sessions()` → ACP `list_sessions(cwd=working_dir)` (Gemini, Codex) / lokální cache pro Claude
- `load_session()` → ACP `load_session(session_id)` / Claude `--resume <id>`

Pokud se v budoucnu ukáže potřeba cross-provider session indexu (např. `avatar session list --all`),
můžeme přidat lehký metadata cache. Ale to je optimalizace, ne nutnost.

**ŽÁDNÝ nový soubor v této fázi.**

---

### Phase 8: Engine Unified API (`engine.py`)

#### 8a: Pass session params to all bridges in `_create_bridge()`

Currently only Claude gets session params (lines 424, 436-437). Add same pattern for Gemini (line ~454) and Codex (line ~442):

```python
session_cfg = pcfg.get("session", {})
return GeminiBridge(
    ...,
    resume_session_id=session_cfg.get("resume_id") or self._kwargs.get("resume_session_id"),
    continue_last=session_cfg.get("continue_last", False) or self._kwargs.get("continue_last", False),
)
```

#### 8b: New engine methods

```python
@property
def session_capabilities(self) -> SessionCapabilitiesInfo: ...

async def list_sessions(self) -> List[SessionInfo]:
    """Delegate to bridge.list_sessions(). Provider handles persistence."""

async def resume_session(self, session_id: str) -> bool:
    """Delegate to bridge.resume_session()."""
```

Žádný auto-save nepotřebujeme — provideři persistují sessions automaticky (viz Phase 7).

**File**: `avatar_engine/engine.py` (lines 358-380 properties, 405-465 _create_bridge)

---

### Phase 9: CLI — Session Command Group

New file `avatar_engine/cli/commands/session.py`:

```
avatar session list [--provider gemini|claude|codex] [--limit 20]
avatar session info <session-id>
avatar session delete <session-id>
```

Register in `cli/app.py` (line ~101): `cli.add_command(session.session)`

**Files**: `avatar_engine/cli/commands/session.py` (NEW), `avatar_engine/cli/app.py`

---

### Phase 10: CLI — `--resume` / `--continue` flags

Add to both `chat.py` and `repl.py`:

```python
@click.option("--resume", "resume_id", help="Resume session by ID")
@click.option("--continue", "continue_last", is_flag=True, help="Continue last session")
```

Pass through to engine kwargs: `resume_session_id=resume_id`, `continue_last=continue_last`.

**Files**: `avatar_engine/cli/commands/chat.py`, `avatar_engine/cli/commands/repl.py`

---

### Phase 11: REPL Commands

Add to REPL command loop (repl.py, lines ~146-178):

- `/sessions` — list available sessions (calls `engine.list_sessions()`)
- `/session id` — show current session ID
- `/resume <id>` — resume a session (calls `engine.resume_session()`)

Update `/help` output.

**File**: `avatar_engine/cli/commands/repl.py`

---

### Phase 12: Config

Add `session:` block under each provider in `examples/avatar.example.yaml`:

```yaml
gemini:
  session:
    # resume_id: ""          # Resume specific session by ID
    # continue_last: false   # Continue most recent session
claude:
  session:
    # resume_id: ""
    # continue_last: false
codex:
  session:
    # resume_id: ""
    # continue_last: false
```

**File**: `examples/avatar.example.yaml`

---

### Phase 13: Package Exports

Update `avatar_engine/__init__.py` to export `SessionInfo`, `SessionCapabilitiesInfo`.

---

### Phase 14: Tests

#### New test files:
- `tests/test_session.py` — Bridge session capabilities, resume_session_id param storage, ACP capability parsing

#### Updated test files:
- `tests/test_cli.py` — `--resume`/`--continue` flags for chat + repl

---

## Implementation Order

```
1. types.py (SessionInfo, SessionCapabilitiesInfo)
2. bridges/base.py (default session methods)
3. bridges/_acp_session.py (NEW — shared mixin)
4. bridges/gemini.py (add mixin + resume params)
5. bridges/codex.py (add mixin + resume params)
6. bridges/claude.py (set capabilities, resume_session override)
7. engine.py (unified API, pass session params — no auto-save needed)
8. cli/commands/session.py (NEW)
9. cli/app.py (register session command)
10. cli/commands/chat.py (--resume, --continue)
11. cli/commands/repl.py (--resume, --continue, /sessions, /resume)
12. examples/avatar.example.yaml (session config)
13. __init__.py (exports)
14. tests/test_session.py
15. tests/test_cli.py (session flag tests)
```

Poznámka: `session_store.py` odstraněn — provideři persistují sessions automaticky,
nepotřebujeme duplicitní metadata store. `test_session_store.py` tím pádem také odpadá.

---

## Key Design Decisions

1. **Default methods on BaseBridge** (not abstract) — existing code without session params continues working
2. **ACP capabilities checked at runtime** — `InitializeResponse.agent_capabilities.load_session` determines availability; graceful fallback to `new_session()`
3. **Session cascade**: `load_session()` → `resume_session()` → `new_session()` — each wrapped in try/except
4. **`--continue`** = list sessions, pick most recent, resume it. For Claude: `--continue` flag. For ACP: `list_sessions()[0]` → `load_session()`
5. **No custom session store** — provideři persistují sessions automaticky (Codex: RolloutRecorder s okamžitým flush, Gemini: auto-save, Claude: auto-save). Zero Footprint zachován — vše v provider home dirs, ne v projektu.
6. **Sessions per-projekt** — ACP `cwd` parametr zajišťuje filtrování dle working_dir projektu
7. **Claude mid-REPL resume** = stop persistent process, set `resume_session_id`, restart. Handled in `resume_session()` override.
8. **Shared ACP mixin** avoids code duplication between Gemini and Codex bridges

## Verification

1. `python -m pytest tests/test_session.py -v` — Bridge capabilities + session params
2. `python -m pytest tests/test_cli.py -v` — CLI flags (--resume, --continue)
3. `python -m pytest tests/ -q` — Full suite (should be 561+ tests)
4. Manual: `avatar session list`, `avatar -p codex repl --resume <id>`, REPL `/sessions`

---

## Implementation Status

**IMPLEMENTACE DOKONČENA** — všechny fáze implementovány a otestovány.

### Implementované soubory

| Fáze | Soubor | Stav |
|------|--------|------|
| 1 | `avatar_engine/types.py` — SessionInfo, SessionCapabilitiesInfo | DONE |
| 2 | `avatar_engine/bridges/base.py` — session_capabilities, list_sessions, resume_session | DONE |
| 3 | `avatar_engine/bridges/_acp_session.py` — ACPSessionMixin (NEW) | DONE |
| 4 | `avatar_engine/bridges/gemini.py` — mixin + resume_session_id + continue_last | DONE |
| 5 | `avatar_engine/bridges/codex.py` — mixin + resume_session_id + continue_last | DONE |
| 6 | `avatar_engine/bridges/claude.py` — capabilities + resume_session() override | DONE |
| 7 | (žádný SessionStore — provideři persistují automaticky) | N/A |
| 8 | `avatar_engine/engine.py` — session API + _create_bridge session params | DONE |
| 9 | `avatar_engine/cli/commands/session.py` — avatar session list/info (NEW) | DONE |
| 9 | `avatar_engine/cli/app.py` — register session command | DONE |
| 10 | `avatar_engine/cli/commands/chat.py` — --resume, --continue flags | DONE |
| 11 | `avatar_engine/cli/commands/repl.py` — --resume, --continue, /sessions, /session, /resume | DONE |
| 12 | `examples/avatar.example.yaml` — session config blocks | DONE |
| 13 | `avatar_engine/__init__.py` — export SessionInfo, SessionCapabilitiesInfo | DONE |
| 14 | `tests/test_session.py` — 44 unit tests | DONE |
| 14 | `tests/integration/test_real_sessions.py` — integration tests | DONE |
| — | `README.md` — session management documentation | DONE |

### Výsledky testů

- **561 unit testů** — všechny PASS (44 nových session testů)
- **Integrace** — test_real_sessions.py (capabilities, list, resume, continue, fallback)
- **Review** — čistý, žádné problémy nalezeny
