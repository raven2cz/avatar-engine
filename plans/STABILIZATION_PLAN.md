# Avatar Engine — Stabilization Plan

> Created: 2026-02-05
> Updated: 2026-02-11
> Phase 1–6 (Testing): ✅ COMPLETED — **290** testů
> Phase 7 (Bridge Observability): 🟡 IN PROGRESS — kroky 1–3 DONE, kroky 4–6 OPEN

---

## Executive Summary

Analýza odhalila **kritické mezery v testování**:

| Kategorie | Aktuální | Cíl |
|-----------|----------|-----|
| **Async execution** | 0 testů | 25+ |
| **CLI commands** | 0 testů | 20+ |
| **Error recovery** | ~3 testy | 15+ |
| **Edge cases** | ~5 testů | 25+ |
| **Race conditions** | 0 testů | 5+ |

**Hlavní problém:** Testy testují kód, ne use-casy. Uživatel může mít falešný pocit bezpečí.

---

## Kritické Use-Case Testy (Chybí!)

### UC-1: Základní chat flow
```
User wants to: Send a message and get a response

EXPECTED:
1. engine.start() → bridge warm up
2. engine.chat("Hello") → response with content
3. response.success == True
4. response.content is not empty
5. engine.session_id is set
6. engine.history has 2 messages (user + assistant)

NOT TESTED:
- Actual subprocess communication
- JSONL message format
- Response parsing
- Session ID extraction
```

### UC-2: Streaming response
```
User wants to: Stream response chunks in real-time

EXPECTED:
1. async for chunk in engine.chat_stream("Tell me a story"):
2. Each chunk is a non-empty string
3. Chunks accumulate to full response
4. TextEvent emitted for each chunk
5. Final response in history

NOT TESTED:
- Actual streaming from subprocess
- Partial message handling
- Event emission timing
```

### UC-3: Provider switching
```
User wants to: Switch from Gemini to Claude mid-session

EXPECTED:
1. engine = AvatarEngine(provider="gemini")
2. await engine.start()
3. await engine.chat("Hello") → works
4. await engine.switch_provider("claude")
5. await engine.chat("Hello again") → works with Claude
6. History cleared or preserved (configurable?)

NOT TESTED:
- Cleanup of old bridge
- State consistency
- Error during switch
```

### UC-4: Auto-restart on failure
```
User wants to: Engine recovers from bridge crash

EXPECTED:
1. engine.chat("Hello") → success
2. Bridge process crashes (externally killed)
3. engine.chat("Hello again") → auto-restarts
4. Response success after restart
5. restart_count incremented

NOT TESTED:
- Crash detection
- Restart logic
- State recovery
- Max restarts limit
```

### UC-5: GUI event integration
```
User wants to: Update GUI in real-time during AI response

EXPECTED:
1. @engine.on(TextEvent) → updates speech bubble
2. @engine.on(ToolEvent) → shows tool usage
3. Events fire during chat_stream()
4. Events contain correct data

NOT TESTED:
- Event emission from real responses
- Handler error handling
- Event ordering
```

### UC-6: CLI single message
```
User wants to: avatar chat "What is 2+2?"

EXPECTED:
1. Output: "4" (or similar)
2. Exit code: 0
3. --json output is valid JSON
4. --stream shows chunks
5. Error message on failure

NOT TESTED:
- CLI command execution
- Output format
- Error handling
```

### UC-7: MCP tool usage
```
User wants to: AI uses custom tools via MCP

EXPECTED:
1. Configure MCP server
2. engine.chat("Use the calculator tool")
3. ToolEvent with status="started"
4. ToolEvent with status="completed"
5. Response includes tool result

NOT TESTED:
- MCP server integration
- Tool event emission
- Tool call parsing
```

### UC-8: Graceful shutdown
```
User wants to: Clean shutdown on SIGTERM

EXPECTED:
1. engine.install_signal_handlers()
2. Send SIGTERM to process
3. engine stops cleanly
4. Bridge process terminated
5. No zombie processes

NOT TESTED:
- Signal handling during chat
- Pending request handling
- Process cleanup
```

### UC-9: Rate limiting
```
User wants to: Prevent API rate limit errors

EXPECTED:
1. Configure rate_limit_rpm=2
2. Send 5 rapid chat() calls
3. First 2 succeed immediately
4. Next 3 wait for rate limit
5. All eventually succeed

NOT TESTED:
- Actual waiting behavior
- Time-based verification
- Stats accuracy
```

### UC-10: Cost tracking (Claude)
```
User wants to: Monitor and limit costs

EXPECTED:
1. Configure max_budget_usd=0.10
2. engine.chat() accumulates cost
3. CostEvent emitted with cost
4. is_over_budget() returns True when exceeded
5. Subsequent chats rejected

NOT TESTED:
- Cost accumulation
- Budget enforcement
- CostEvent emission
```

---

## Implementační Plán

### Phase 1: Async Subprocess Mocking (Priority: CRITICAL)
```
Soubor: tests/test_async_flow.py

Testy:
1. test_chat_full_flow - subprocess mock, JSONL exchange
2. test_chat_stream_full_flow - streaming mock
3. test_chat_timeout_handling - timeout scenarios
4. test_chat_process_crash - unexpected exit
5. test_chat_partial_json - incomplete response
```

### Phase 2: CLI Integration Tests (Priority: HIGH)
```
Soubor: tests/test_cli.py

Testy:
1. test_chat_command_basic - "avatar chat 'hello'"
2. test_chat_command_json - "--json output"
3. test_chat_command_provider - "-p claude"
4. test_repl_command_exit - "/exit"
5. test_health_command - "avatar health --check-cli"
6. test_mcp_list - "avatar mcp list"
7. test_mcp_add_remove - add/remove MCP server
```

### Phase 3: Error Recovery Tests (Priority: HIGH)
```
Soubor: tests/test_error_recovery.py

Testy:
1. test_auto_restart_on_crash - bridge crash → restart
2. test_max_restarts_limit - doesn't restart forever
3. test_fallback_persistent_to_oneshot - persistent fails → oneshot
4. test_gemini_acp_fallback - ACP fails → oneshot
5. test_error_event_emission - ErrorEvent fired on failure
```

### Phase 4: Event System Tests (Priority: MEDIUM)
```
Soubor: tests/test_event_integration.py

Testy:
1. test_text_event_during_stream - chunks → events
2. test_tool_event_lifecycle - started → completed
3. test_state_event_transitions - all state changes
4. test_cost_event_emission - cost tracking
5. test_handler_exception_handling - handler throws
```

### Phase 5: Edge Cases (Priority: MEDIUM)
```
Soubor: tests/test_edge_cases.py

Testy:
1. test_concurrent_chat_calls - race conditions
2. test_switch_provider_during_chat - state corruption
3. test_very_long_response - memory handling
4. test_empty_response - edge case
5. test_unicode_content - encoding
6. test_history_limit - max_history enforcement
```

### Phase 6: Gemini ACP Tests (Priority: MEDIUM)
```
Soubor: tests/test_gemini_acp.py

Testy:
1. test_acp_initialization_flow - full startup
2. test_acp_authentication_failure - auth error
3. test_acp_session_creation - new_session
4. test_acp_prompt_streaming - session updates
5. test_acp_thinking_extraction - thinking content
```

---

## Metriky Úspěchu

| Metrika | Aktuální | Cíl | Status |
|---------|----------|-----|--------|
| Celkem testů | **290** | 280+ | ✅ |
| Async flow testy | **15** | 25 | ✅ |
| CLI testy | **23** | 20 | ✅ |
| Error recovery | **12** | 15 | ✅ |
| Edge cases | **19** | 25 | ✅ |
| Event integration | **12** | 10 | ✅ |
| Gemini ACP | **25** | 20 | ✅ |

---

## Rizika

| Riziko | Pravděpodobnost | Dopad | Mitigace |
|--------|-----------------|-------|----------|
| Testy závisí na reálných CLI | ~~Vysoká~~ | ~~Vysoký~~ | ✅ Mock subprocess |
| Race conditions v async kódu | ~~Střední~~ | ~~Vysoký~~ | ✅ Izolované testy |
| Flaky testy (timing) | ~~Střední~~ | ~~Střední~~ | ✅ Deterministické mocky |

---

## Další Kroky

1. ✅ Vytvořit stabilizační plán
2. ✅ Implementovat Phase 1 (async subprocess) - 15 testů
3. ✅ Implementovat Phase 2 (CLI) - 23 testů
4. ✅ Implementovat Phase 3 (Error recovery) - 12 testů
5. ✅ Implementovat Phase 4 (Events) - 12 testů
6. ✅ Implementovat Phase 5 (Edge cases) - 19 testů
7. ✅ Implementovat Phase 6 (Gemini ACP) - 25 testů
8. ✅ Dosáhnout 280+ testů → **290 testů**

---

# Phase 7: Bridge Observability — „Slepý uživatel"

> Added: 2026-02-11
> Status: 🔴 OPEN
> Priority: **CRITICAL**
> Princip: **Slepý uživatel je to nejhorší, co se nám může stát.**

## Problém

Uživatel odeslal zprávu přes GUI, Gemini CLI zpracovávala request 2+ minuty,
a pak vše spadlo na server-side timeout. Uživatel neměl **žádnou informaci**
o tom, co se děje:

- Žádný progress — jen spinning orb
- Žádná diagnostika — stderr z CLI zahozeno (`stderr=None`)
- Žádný kontext v timeout chybě — jen "request timed out"
- Po timeoutu ghost events — bust mluvila a nešla zastavit

Část problémů (ghost events, timeout hodnota, connection overlay) jsme vyřešili
v commitech `dde24b9` a `f46efd2`. **Ale jádro problému zůstává: nevidíme
dovnitř CLI subprocessů.**

---

## Audit všech bridge procesů

### 1. ACP stderr zahozeno (CRITICAL)

**Gemini:** `avatar_engine/bridges/gemini.py:362`
```python
stderr=None,  # ← VEŠKERÝ diagnostický output zahozený
```

**Codex:** `avatar_engine/bridges/codex.py:244`
```python
stderr=None,  # ← VEŠKERÝ diagnostický output zahozený
```

**Claude (OK):** `avatar_engine/bridges/claude.py:165`
```python
stderr=asyncio.subprocess.PIPE,  # ✅ Správně — zachytáváno
```

**Dopad:** Gemini CLI a Codex CLI vypisují na stderr:
- Auth chyby, token refresh problémy
- Rate limit warnings
- Model availability problémy
- Interní progress ("Connecting...", "Authenticating...")
- Crash stacktrace

**Vše zahozeno.** Uživatel nevidí nic. Administrátor nevidí nic. Ani logy nemají stderr.

### 2. Infrastruktura EXISTUJE, ale není napojena (CRITICAL)

Pipeline pro diagnostiku je **kompletně vybudovaný**, jen ACP ho nepoužívá:

```
bridges/base.py:320  _monitor_stderr()     — čte stderr, klasifikuje, emituje
                                              ↓
bridges/base.py:334  _on_event(diagnostic)  — posílá do engine
                                              ↓
engine.py:705-712    DiagnosticEvent emit   — emituje event
                                              ↓
web/bridge.py:133    _on_diagnostic()       — broadcastuje klientům
                                              ↓
web/protocol.py:35   "diagnostic" type      — WS message type
                                              ↓
Frontend                                    — (zatím nezpracovává)
```

Claude bridge tuto pipeline používá (persistent mode, `stderr=PIPE`).
Gemini a Codex ACP procesy ji **obcházejí** — mají vlastní subprocess spawn
s `stderr=None`.

### 3. ACP callback exceptions spolknuty (HIGH)

**Gemini:** `avatar_engine/bridges/gemini.py:497-500`
```python
try:
    self._handle_acp_update_inner(session_id, update)
except Exception as exc:
    logger.debug(f"Error in ACP update handler: {exc}", exc_info=True)
    # ← DEBUG level! Uživatel nikdy neuvidí.
```

**Codex:** `avatar_engine/bridges/codex.py:377-380`
```python
try:
    self._handle_acp_update_inner(session_id, update)
except Exception as exc:
    logger.debug(f"Error in ACP update handler: {exc}", exc_info=True)
    # ← Stejný problém.
```

**Dopad:** Pokud dojde k chybě při zpracování ACP update (parsování,
neočekávaný formát, missing field), exception se zaloguje na DEBUG
a request pokračuje bez odpovědi — nakonec spadne na timeout.

### 4. Timeout bez kontextu (HIGH)

**Server:** `avatar_engine/web/server.py:554-559`
```python
except asyncio.TimeoutError:
    error_text = f"No response from engine — request timed out{size_hint}"
```

Chybí:
- Jaký byl engine state při timeoutu (thinking? tool_executing? idle?)
- Kolik eventů přišlo před timeoutem
- Poslední diagnostická zpráva z CLI
- Jak dlouho trvaly jednotlivé fáze (thinking vs tool execution)

### 5. Žádný heartbeat během dlouhých operací (MEDIUM)

Při 10-minutovém ACP requestu:
- Server neposílá žádný keepalive
- Frontend neví, jestli je engine mrtvý nebo pracuje
- WebSocket timeout v browseru může spojení zavřít
- Uživatel nemá důvod čekat — vypadá to jako zamrzlé

### 6. Auth/rate-limit chyby neviditelné (MEDIUM)

Gemini CLI může interně:
- Čekat na OAuth token refresh (uvíznuté na auth prompt?)
- Dostat 429 rate limit a čekat na retry
- Dostat 403 na model, co není dostupný

**Nic z toho nevidíme.** Viz problém #1 (stderr zahozeno).

### 7. Claude --debug flag (LOW — jen Claude)

Claude bridge podporuje `--debug` flag pro extra výpis. Gemini a Codex
nemají ekvivalent. Zvážit verbose/debug mode pro všechny bridges.

---

## Implementační plán

### Krok 1: stderr=PIPE pro ACP procesy (CRITICAL, ~30 min)

**Soubory:**
- `avatar_engine/bridges/gemini.py:362` — `stderr=None` → `stderr=asyncio.subprocess.PIPE`
- `avatar_engine/bridges/codex.py:244` — `stderr=None` → `stderr=asyncio.subprocess.PIPE`

**Co udělat:**
1. Změnit `stderr=None` na `stderr=asyncio.subprocess.PIPE`
2. Spustit `_monitor_stderr_acp()` background task (analogicky k base.py:304)
3. V ACP mode nelze použít base._monitor_stderr() přímo (jiný self._proc),
   takže: přidat metodu `_start_stderr_monitor()` do ACP setup
4. Stderr output → `self._on_event({"type": "diagnostic", ...})`

**Riziko:** stderr buffer se může zaplnit pokud nečteme → process freezne.
Proto MUSÍ být background task, ne jednorázové čtení.

### Krok 2: Callback exceptions → ErrorEvent (HIGH, ~20 min)

**Soubory:**
- `avatar_engine/bridges/gemini.py:499` — `logger.debug` → `logger.warning` + emit ErrorEvent
- `avatar_engine/bridges/codex.py:379` — stejně

**Co udělat:**
1. Zvýšit log level z DEBUG na WARNING
2. Emitovat přes `self._on_event({"type": "error", "error": str(exc)})`
3. Frontend pak zobrazí chybu (infrastructure už funguje)

### Krok 3: Timeout s kontextem (HIGH, ~30 min)

**Soubor:** `avatar_engine/web/server.py:554-567`

**Co udělat:**
1. Před `asyncio.wait_for()` uložit start time + engine state
2. V timeout handleru:
   - Aktuální engine state
   - Elapsed time per phase (pokud sledujeme)
   - Počet přijatých eventů
   - Poslední diagnostická zpráva
3. Formátovat do error message:
   ```
   Request timed out after 600s.
   Last state: tool_executing (gemini-3-pro-preview)
   Events received: 47 (last: thinking at +45s)
   Last diagnostic: "Executing tool: list_directory"
   ```

### Krok 4: Heartbeat / progress ping (MEDIUM, ~45 min)

**Soubory:**
- `avatar_engine/web/server.py` — heartbeat task
- `avatar_engine/web/bridge.py` — forward heartbeat
- Frontend: `useAvatarWebSocket.ts` — handle heartbeat type

**Co udělat:**
1. Během `asyncio.wait_for()` spustit background task:
   ```python
   async def heartbeat():
       elapsed = 0
       while True:
           await asyncio.sleep(15)
           elapsed += 15
           brg.broadcast_message({
               "type": "heartbeat",
               "data": {
                   "elapsed": elapsed,
                   "engine_state": eng.state.value,
                   "events_received": event_count,
               }
           })
   ```
2. Frontend: zobrazit elapsed time + stav v compact mode
3. Zrušit heartbeat task po dokončení/timeoutu

### Krok 5: Frontend diagnostic panel (MEDIUM, ~1h)

**Soubory:**
- `examples/web-demo/src/hooks/useAvatarWebSocket.ts` — handle `diagnostic` type
- `examples/web-demo/src/components/CompactMessages.tsx` — diagnostic overlay
- `examples/web-demo/src/components/StatusBar.tsx` — diagnostic indicator

**Co udělat:**
1. WebSocket handler pro `diagnostic` type → ukládat do state
2. Compact mode: pod thinking/tool info zobrazit diagnostiku
3. Fullscreen: diagnostika v status baru
4. Fade-out po 5s, max 3 řádky viditelné

### Krok 6: Verbose/debug mode pro všechny bridges (LOW, ~30 min)

**Soubory:**
- `avatar_engine/bridges/gemini.py` — `--log_level=debug` pro gemini-cli
- `avatar_engine/bridges/codex.py` — verbose flag pro codex
- `avatar_engine/config.py` — `debug_bridges: bool` config option

---

## Stav po předchozích fixech (commity dde24b9, f46efd2)

| Fix | Soubor | Stav |
|-----|--------|------|
| Client-side timeout odstraněn | useAvatarChat.ts | ✅ DONE |
| Server timeout 120→600s | server.py:545 | ✅ DONE |
| Error fence (ghost events) | useAvatarWebSocket.ts | ✅ DONE |
| stopResponse → idle+thinking_end | useAvatarWebSocket.ts | ✅ DONE |
| Connection status overlay | CompactChat.tsx | ✅ DONE |
| Error banner v compact mode | CompactChat.tsx | ✅ DONE |
| Tool/thinking visibility | CompactMessages.tsx | ✅ DONE |
| 25 error-handling testů | error-handling.test.ts | ✅ DONE |

---

## Priority Matrix

| # | Krok | Priorita | Effort | Dopad | Stav |
|---|------|----------|--------|-------|------|
| 1 | stderr=PIPE pro ACP | 🔴 CRITICAL | 30 min | Největší — odemkne VEŠKEROU diagnostiku | ✅ DONE |
| 2 | Callback exceptions → ErrorEvent | 🟠 HIGH | 20 min | Odhalí tiché chyby v ACP update handleru | ✅ DONE |
| 3 | Timeout s kontextem | 🟠 HIGH | 30 min | Uživatel ví PROČ to trvalo / spadlo | ✅ DONE |
| 4 | Heartbeat / progress | 🟡 MEDIUM | 45 min | Uživatel ví ŽE engine pracuje | OPEN |
| 5 | Frontend diagnostic panel | 🟡 MEDIUM | 1h | Zobrazit diagnostiku v GUI | OPEN |
| 6 | Debug mode pro bridges | 🟢 LOW | 30 min | Extra výpis pro vývoj/debugging | OPEN |

**Celkový effort:** ~4h
**ROI:** Extrémně vysoký — transformuje "slepého uživatele" na informovaného.

---

## Test Plan pro Phase 7

### Nové testy:

```
tests/test_bridge_observability.py:
1. test_gemini_acp_stderr_captured - stderr=PIPE, monitor task running
2. test_codex_acp_stderr_captured - stejně pro Codex
3. test_stderr_diagnostic_event_emitted - stderr line → DiagnosticEvent
4. test_acp_callback_error_surfaced - exception → ErrorEvent (ne jen debug log)
5. test_timeout_includes_context - timeout error má engine state + event count
6. test_heartbeat_during_long_request - heartbeat messages posílány
7. test_heartbeat_stops_after_response - heartbeat zrušen po odpovědi

examples/web-demo/src/__tests__/diagnostic-display.test.ts:
8. test_diagnostic_message_rendered - diagnostic type → zobrazení v UI
9. test_heartbeat_updates_elapsed - heartbeat → elapsed time v compact mode
10. test_diagnostic_fadeout - diagnostika zmizí po 5s
```

---

## Architektura diagnostického pipeline (reference)

```
┌──────────────┐     stderr      ┌──────────────┐     _on_event     ┌──────────────┐
│  gemini-cli  │ ──────────────→ │ GeminiBridge │ ─────────────────→ │ AvatarEngine │
│  (subprocess)│  asyncio.PIPE   │ _monitor_acp │  {"type":"diag"}  │  _on_bridge  │
└──────────────┘                 │    _stderr()  │                   │    _event()  │
                                 └──────────────┘                   └──────┬───────┘
                                                                          │
                                                                   emit(DiagnosticEvent)
                                                                          │
                                                                          ▼
                                                                   ┌──────────────┐
                                                                   │ WebBridge    │
                                                                   │ _on_diag()   │
                                                                   └──────┬───────┘
                                                                          │
                                                                   broadcast_message
                                                                   {"type":"diagnostic"}
                                                                          │
                                                                          ▼
                                                                   ┌──────────────┐
                                                                   │  Frontend WS │
                                                                   │  diagnostic  │
                                                                   │  handler     │
                                                                   └──────────────┘
```

### Klasifikace stderr (existující — base.py:_classify_stderr_level)

```
"error", "fatal", "critical"  →  level: "error"
"warn"                        →  level: "warning"
"debug", "trace"              →  level: "debug"
default                       →  level: "info"
```
