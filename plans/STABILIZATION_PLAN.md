# Avatar Engine — Stabilization Plan

> Created: 2026-02-05
> Updated: 2026-02-13
> Phase 1–6 (Testing): ✅ COMPLETED — **290** testů
> Phase 7 (Bridge Observability): 🟡 IN PROGRESS — kroky 1–3 DONE, kroky 4–6 OPEN
> Phase 8 (Slow Startup): ✅ RESOLVED — nanobanana uninstall
> Phase 9 (Integration Test Fixes): ✅ COMPLETED
> Phase 10 (GUI Compact Mode Round 3): ✅ COMPLETED
> Phase 11 (Final Integration Verification): 🟡 BLOCKED — Gemini Pro kvóta vyčerpaná

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

---

# Phase 8: Slow ACP/CLI Startup Investigation

> Added: 2026-02-12
> Updated: 2026-02-13
> Status: ✅ RESOLVED — nanobanana extension uninstall (disable nestačil)
> Priority: **HIGH**

## Problém

ACP `initialize()` i oneshot `gemini -p "..."` trvají **~53 sekund**.
Uživatel čeká téměř minutu, než engine odpoví. Dříve to bylo výrazně rychlejší.

## Benchmark výsledky (2026-02-12)

| Operace | Čas | Poznámka |
|---------|-----|----------|
| `node -e 'ok'` | **15ms** | Node.js cold start — OK |
| `gemini --help` | **800ms** | Module load — OK |
| `gemini --version` | **790ms** | — OK |
| `gemini -p "Say ok" --yolo` | **53–66s** | ← PROBLÉM |
| ACP subprocess spawn | **0ms** | OK |
| ACP `connect_to_agent()` | **0ms** | OK |
| ACP `initialize()` | **52s** | ← BOTTLENECK (stejný jako oneshot) |
| ACP `new_session()` | **274ms** | OK |

## Klíčový nález: 53s ticho před prvním HTTP voláním

Pomocí `NODE_DEBUG=http` jsme zjistili timeline:

```
     0ms  — gemini-cli spuštěno
53 543ms  — PRVNÍ HTTP volání: oauth2.googleapis.com/tokeninfo
53 543ms  — loadCodeAssist volání na cloudcode-pa.googleapis.com
58 807ms  — další API volání
66 470ms  — odpověď
```

**53.5 sekund absolutního ticha** — žádné síťové volání, žádný stderr output.
Vše se děje lokálně uvnitř gemini-cli.

## Root Cause: nanobanana extension

**`extensions disable` nestačil, `extensions uninstall` vyřešil problém.**

Gemini-cli v0.28.2 při `disable` stále skenoval extension directory a
inicializoval extension systém. Teprve po `uninstall` (smazání souborů
z ~/.gemini/extensions/nanobanana/) se startup vrátil na normální časy.

## Výsledky po uninstall (2026-02-13)

| Operace | Před (s nanobanana) | Po (bez) | Zrychlení |
|---------|---------------------|----------|-----------|
| `gemini -p "Say ok"` | 53s | **13s** | 4x |
| ACP `initialize()` | 52s | **~10s** | 5x |
| ACP test basic | 39s | **11s** | 3.5x |
| CLI chat test | 42s | **12s** | 3.5x |

## Poučení

- `gemini extensions disable` nebrání extension inicializaci — bug v gemini-cli
- Extension s MCP serverem (nanobanana) přidává ~40s k KAŽDÉMU startu
- Pro produkci nikdy neinstalovat zbytečné extensions

## Diagnostický skript

Benchmark skript: `tests/integration/bench_acp_startup.py`
Měří každou fázi ACP startupu + oneshot baseline + Node.js baseline.

---

# Phase 9: Integration Test Fixes (2026-02-12)

> Added: 2026-02-12
> Status: ✅ COMPLETED

## Opravy

| Oprava | Soubory | Detail |
|--------|---------|--------|
| Fix `-p` ordering | test_real_cli.py, test_real_cli_features.py, test_real_repl_pty.py | `-p` patří na subcommand (chat/repl), ne na group |
| Rewrite PromptSession → Console.input | test_repl_prompt_toolkit_integration.py | repl.py přepsáno bez prompt_toolkit |
| Rewrite PTY child script | test_real_repl_pty.py | Odstranění neexistujících PromptSession/patch_stdout |
| Přidání @pytest.mark.slow | test_real_cli_features.py, test_real_chat.py | Testy s reálným API nemají běžet bez -m slow |
| health → --help v non-slow testech | test_real_cli_features.py | Zabránění spuštění reálného engine |
| Instalace chybějících deps | pip install | agent-client-protocol, pytest-asyncio, pytest-timeout |

## Výsledky

| Kategorie | Počet | Stav |
|-----------|-------|------|
| Unit testy | 966 | ✅ 966/966 passed |
| Frontend testy | 97 | ✅ 97/97 passed |
| Non-slow integrační | 33 | ✅ 33/33 passed |
| Slow integrační (ověřeno) | ~19 | ✅ Vše prošlo individuálně |
| Slow integrační (celkem) | 134 | Většina neověřena (30-60s per test) |

---

# Phase 10: GUI Compact Mode Polish — Round 3 (2026-02-13)

> Added: 2026-02-13
> Status: ✅ COMPLETED
> Commit: `566c794`

## Změny

| Změna | Soubory | Detail |
|-------|---------|--------|
| Code block font size | index.css | `0.7rem` → `0.65rem` (pre), `0.75em` → `0.7em` (inline code), `.group` margin override |
| SVG ikony místo U/A | CompactMessages.tsx | Import `User` (lucide) + `AvatarLogo`, `rounded-lg` → `rounded-full` |
| Konzistentní bubliny | CompactMessages.tsx | Odstranění `rounded-tr-sm` / `rounded-tl-sm` → `rounded-xl` |
| Landing page mode selector | LandingPage.tsx, types/avatar.ts, useWidgetMode.ts | 3 tlačítka FAB/Compact/Fullscreen, `LS_DEFAULT_MODE` v localStorage |
| Docs odkaz | LandingPage.tsx | "Documentation & README →" link |
| Wiring | AvatarWidget.tsx | Propojení `defaultMode` / `setDefaultMode` do LandingPage |

## Nové testy (14)

| Soubor | Testů | Popis |
|--------|-------|-------|
| useWidgetMode.test.ts | +7 | defaultMode state, persistence, loadMode fallback, priorita |
| widget-integration.test.tsx | +7 | Mode selector UI, docs link, SVG ikony, zaoblení bublin |

**Frontend testy: 111/111 pass** (z původních 97)

---

# Phase 11: Final Integration Verification (2026-02-13)

> Added: 2026-02-13
> Status: 🟡 BLOCKED — Gemini Pro model kvóta vyčerpaná
> Commit: `f424b08`

## Bug fixy v integračních testech

| Bug | Soubor | Oprava |
|-----|--------|--------|
| `thinking_level: "medium"` nepodporován Pro modelem | test_real_acp.py:88 | `"medium"` → `"low"` |
| JSON parsing s trailing log outputem | test_real_cli.py:151-155 | Přidán `rfind("}")` pro správné ohraničení JSON |
| Zastaralá aserce na model v ACP settings | test_real_acp.py:374 | `"model" not in settings` → `settings.get("model", {}).get("name") == "gemini-3-pro-preview"` |

## Celkový stav testů

| Kategorie | Počet | Stav |
|-----------|-------|------|
| Python unit testy | 966 | ✅ 966 passed, 2 skipped |
| Frontend testy (vitest) | 111 | ✅ 111/111 passed |
| Non-slow integrační | 33 | ✅ 33/33 passed |
| Gemini integrační (API) | 78 | 🟡 BLOCKED — Pro kvóta vyčerpaná |

## Gemini Pro kvóta — analýza

**Problém:** Všech 78 gemini-marked integračních testů selhává na `TerminalQuotaError` (HTTP 429)
z `cloudcode-pa.googleapis.com`.

**Root cause:** Denní kvóta Pro modelů (`gemini-3-pro-preview`, `gemini-2.5-pro`) na free-tier
`cloudcode-pa` API je velmi nízká (~50-100 API callů/den). Každý ACP request generuje 2-10+
interních API callů. Kvóta byla vyčerpaná z běžného používání, ne z testů samotných.

**Flash modely fungují** — mají separátní, vyšší kvótový pool.

**Reset:** ~20:33 UTC (13. 2. 2026)

## Testy k ověření po resetu kvóty

Spustit: `pytest tests/integration/ -m gemini -v --timeout=120`

**78 testů ve 13 souborech:**

### test_real_acp.py (19 testů)
- `TestGeminiACP::test_acp_session_basic`
- `TestGeminiACP::test_acp_multi_turn`
- `TestGeminiACP::test_acp_with_thinking`
- `TestGeminiACP::test_acp_fallback_to_oneshot`
- `TestGeminiBridgeDirect::test_bridge_oneshot_mode`
- `TestGeminiBridgeDirect::test_bridge_state_transitions`
- `TestGeminiBridgeDirect::test_bridge_stats`
- `TestGenerationConfig::test_temperature_setting`
- `TestGenerationConfig::test_top_p_setting`
- `TestACPGenerationConfig::test_acp_default_model_no_error`
- `TestACPGenerationConfig::test_acp_with_thinking_level_low`
- `TestACPGenerationConfig::test_acp_with_thinking_level_high`
- `TestACPGenerationConfig::test_acp_with_temperature`
- `TestACPGenerationConfig::test_acp_with_model_and_config`
- `TestACPGenerationConfig::test_acp_gemini_25_flash`
- `TestACPGenerationConfig::test_acp_multi_turn_with_config`
- `TestACPImageGeneration::test_image_model_settings_structure`
- `TestACPImageGeneration::test_image_model_strips_thinking_config`
- `TestACPImageGeneration::test_default_model_image_generation`

### test_acp_settings_diagnostic.py (21 testů)
- `TestACPSettingsDiagnostic::test_A_no_settings` .. `test_T_thinking_minimal` (20 testů)
- `TestACPSettingsAllAtOnce::test_all_experiments`

### test_real_chat.py (6 testů)
- `TestGeminiRealChat::test_simple_chat`
- `TestGeminiRealChat::test_streaming_chat`
- `TestGeminiRealChat::test_multi_turn_conversation`
- `TestGeminiRealChat::test_events_fire_during_chat`
- `TestGeminiRealChat::test_health_check`
- `TestGeminiRealChat::test_unicode_content`

### test_real_cli.py (4 testy)
- `TestGeminiCLI::test_chat_command_basic`
- `TestGeminiCLI::test_chat_command_json`
- `TestGeminiCLI::test_chat_command_streaming`
- `TestHealthCLI::test_health_gemini`

### test_real_cli_display_rewrite.py (4 testy)
- `TestGeminiThinkingIsComplete::test_thinking_complete_emitted`
- `TestGeminiThinkingIsComplete::test_thinking_not_in_response_text`
- `TestGeminiStreamErrorPropagation::test_stream_chat_delivers_text`
- `TestDisplaySpinner::test_spinner_advances_during_chat`

### test_real_cli_features.py (7 testů)
- `TestWorkingDirFlag::test_working_dir_propagated_to_chat`
- `TestBridgeGetUsage::test_gemini_get_usage_after_chat`
- `TestBridgeGetUsageAccumulation::test_usage_accumulates`
- `TestReplShowFunctions::test_show_usage_real_gemini`
- `TestReplShowFunctions::test_show_tools_with_mcp`
- `TestReplShowFunctions::test_show_mcp_status`
- `TestReplShowFunctions::test_show_tool_detail_not_found`

### test_real_display.py (6 testů)
- `TestGeminiDisplay::test_display_receives_events_during_chat`
- `TestGeminiDisplay::test_display_during_streaming`
- `TestGeminiDisplay::test_status_line_renders_without_error`
- `TestDisplayLifecycle::test_multiple_turns_with_display`
- `TestDisplayLifecycle::test_unregister_stops_tracking`
- `TestDisplayLifecycle::test_verbose_display_no_crash`

### test_real_mcp.py (2 testy)
- `TestMCPWithGemini::test_chat_with_mcp_tools`
- `TestMCPWithGemini::test_mcp_tool_events`

### test_real_repl_display.py (3 testy)
- `TestReplDisplayLifecycleGemini::test_stream_with_display_events`
- `TestReplDisplayLifecycleGemini::test_multiple_turns_display_lifecycle`
- `TestDisplayOutputVerification::test_response_text_captured_fully`

### test_real_capabilities.py (2 testy)
- `TestGeminiCapabilities::test_capabilities_after_start`
- `TestGeminiCapabilities::test_diagnostic_events_from_stderr`

### test_real_sessions.py (2 testy)
- `TestGeminiSessionCapabilities::test_capabilities_detected`
- `TestGeminiSessionCapabilities::test_resume_nonexistent_falls_back`

### test_real_system_prompt.py (2 testy)
- `TestGeminiSystemPrompt::test_system_prompt_affects_response`
- `TestGeminiSystemPrompt::test_system_prompt_only_first_message`
