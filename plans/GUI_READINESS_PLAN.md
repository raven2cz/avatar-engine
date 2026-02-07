# Avatar Engine — GUI Readiness Plan: Critical Gaps for Avatar Integration

> Created: 2026-02-07
> Updated: 2026-02-07
> Status: Draft — rozšířeno o analýzu referenčních projektů, CLI display a demo GUI
> Priority: HIGHEST — bez oprav v tomto plánu avatar v GUI nebude fungovat správně
> Version: 2.0

---

## 1. Executive Summary

Avatar Engine je navržen jako **knihovna pro GUI aplikace s AI avatarem** — postavičkou,
která mluví, myslí, používá nástroje, a reaguje na uživatele vizuálně. Aktuální
implementace funguje pro CLI, ale **pro GUI integraci má 9 kritických mezer**.

Tento plán detailně popisuje každou mezeru, její dopad na GUI, a navrhuje řešení.

### Celkový dopad na GUI avatara

| Mezera | Dopad na avatara | Priorita |
|--------|-----------------|----------|
| GAP-1: ThinkingEvent je primitivní | Avatar nemůže vizuálně ukazovat "co si myslí" | CRITICAL |
| GAP-2: Paralelní operace nelze zobrazit | Avatar zamrzne při multi-tool execution | CRITICAL |
| GAP-3: Thinking leak v Gemini oneshot | Avatar řekne nahlas své vnitřní myšlenky | HIGH |
| GAP-4: Thread safety — race conditions | GUI crashne při souběžných operacích | HIGH |
| GAP-5: System prompt nekonzistentní | Avatar se chová jinak u každého providera | HIGH |
| GAP-6: Budget control pasivní | Avatar utratí víc peněz, než má povoleno | MEDIUM |
| GAP-7: Stderr není surfaceován | Avatar mlčí o problémech na pozadí | MEDIUM |
| GAP-8: MCP tool policy all-or-nothing | Avatar nemůže mít granulární permissions | MEDIUM |
| GAP-9: Chybí runtime capabilities API | GUI neví, co provider podporuje | LOW |

---

## 2. GAP-1: ThinkingEvent je primitivní — Avatar neumí vizuálně myslet

### 2.1 Aktuální stav

**ThinkingEvent** (`events.py:81`) je prostý dataclass s jedním polem:

```python
@dataclass
class ThinkingEvent(AvatarEvent):
    thought: str = ""
```

**Jak se zobrazuje:**

| Kontext | Kód | Chování |
|---------|-----|---------|
| REPL (`repl.py:160-163`) | `event.thought[:80]...` | Zobrazí jen s `--verbose`, šedá kurzíva, 80 znaků |
| Chat (`chat.py:181-183`) | `THINKING: {event.thought[:100]}...` | Vždy zobrazí, 100 znaků |
| GUI example (`gui_integration.py:59-64`) | `gui.show_thinking(event.thought)` | 100 znaků, jeden string |

**Jak se extrahuje z providerů:**

| Provider | Extrakce | Soubor | Řádky |
|----------|----------|--------|-------|
| Gemini ACP | `_extract_thinking_from_update()` — 6 vzorů (thinking attr, content blocks, agent_message, dict) | `gemini.py` | 720-767 |
| Codex ACP | `_extract_thinking_from_update()` — 5 vzorů (thought attr, content blocks, AgentThoughtChunk, dict) | `codex.py` | 573-614 |
| Claude | **ŽÁDNÁ EXTRAKCE** — Claude neemituje thinking events | `claude.py` | (nikde) |

### 2.2 Proč je to problém pro GUI avatara

GUI avatar potřebuje vizuálně rozlišovat **fáze myšlení**:

1. **"Přemýšlím nad problémem"** — avatar si drbne na hlavě, animace otazníku
2. **"Analyzuji kód"** — avatar čte dokumenty, animace lupy
3. **"Plánuji řešení"** — avatar kreslí na tabuli, animace diagramu
4. **"Kontroluji výsledek"** — avatar kývá hlavou, animace ✓

Ale ThinkingEvent poskytuje jen **holý string** bez jakékoli struktury.
GUI nemá jak rozlišit typ myšlení → avatar může jen genericky "přemýšlet".

**Konkrétní chybějící vlastnosti:**

| Vlastnost | Popis | Proč chybí |
|-----------|-------|------------|
| `phase` | Fáze myšlení (analyzing, planning, reviewing, coding) | ThinkingEvent nemá pole |
| `is_start` / `is_complete` | Začátek/konec myšlenkového bloku | Chybí lifecycle signalizace |
| `progress` | Pokrok (0.0–1.0) | Žádný indikátor |
| `category` | Typ (reasoning, code_analysis, tool_planning, reflection) | Flat string |
| `depth` | Hloubka vnoření (thinking o thinking) | Chybí |
| `duration_hint` | Předpokládaná délka | Chybí |
| `token_count` | Počet thinking tokenů | Chybí — důležité pro cost tracking |

**TextEvent má `is_complete: bool`** — ThinkingEvent ne. GUI neví kdy thinking skončil.

### 2.3 Další problém: Claude neemituje thinking vůbec

Claude Code CLI v stream-json formátu neposílá "thinking" eventy ve smyslu Gemini.
To znamená, že **třetina providerů thinking vůbec neprodukuje**. GUI musí:

1. Buď ukazovat generické "AI pracuje..." pro Claude
2. Nebo extrahovat pseudo-thinking z Claude's tool_use/result events
3. Nebo detekovat provider a přizpůsobit UX

### 2.4 Vzory z referenčních projektů

**Gemini CLI i Codex používají identický vzor** pro extrakci thinking subject:
oba parsují `**Bold Text**` markery z thinking/reasoning streamu jako status header.
Viz **sekce 15.1** (Gemini `ThoughtSummary`) a **sekce 15.2** (Codex `extract_first_bold()`).

Codex navíc používá **dual-buffer pattern** (`reasoning_buffer` + `full_reasoning_buffer`)
pro oddělení live display od transcript recording — viz **sekce 15.2**.

### 2.5 Navrhované řešení

#### A) Rozšíření ThinkingEvent

```python
@dataclass
class ThinkingEvent(AvatarEvent):
    """
    Model thinking event — structured for GUI visualization.

    Emitted during model's internal reasoning process.
    GUI should use phase/category to drive avatar animations.
    """
    thought: str = ""
    phase: ThinkingPhase = ThinkingPhase.GENERAL  # NEW
    is_start: bool = False                         # NEW — first chunk of thinking block
    is_complete: bool = False                      # NEW — last chunk of thinking block
    block_id: str = ""                             # NEW — groups chunks into blocks
    token_count: int = 0                           # NEW — tokens consumed by thinking
    category: str = ""                             # NEW — freeform category hint


class ThinkingPhase(Enum):
    GENERAL = "general"           # Obecné přemýšlení
    ANALYZING = "analyzing"       # Analýza vstupu/kódu
    PLANNING = "planning"         # Plánování řešení
    CODING = "coding"             # Generování kódu
    REVIEWING = "reviewing"       # Kontrola výsledku
    TOOL_PLANNING = "tool_planning"  # Rozhodování o tool_use
```

#### B) Heuristická klasifikace

Protože providery neposílají fáze explicitně, přidat klasifikátor:

```python
def _classify_thinking(thought: str) -> ThinkingPhase:
    """Heuristic classification of thinking content for GUI display."""
    lower = thought.lower()
    if any(w in lower for w in ["analyze", "look at", "examining", "reading"]):
        return ThinkingPhase.ANALYZING
    if any(w in lower for w in ["plan", "approach", "strategy", "steps"]):
        return ThinkingPhase.PLANNING
    if any(w in lower for w in ["write", "implement", "code", "function"]):
        return ThinkingPhase.CODING
    if any(w in lower for w in ["check", "verify", "review", "test"]):
        return ThinkingPhase.REVIEWING
    if any(w in lower for w in ["tool", "call", "use", "execute"]):
        return ThinkingPhase.TOOL_PLANNING
    return ThinkingPhase.GENERAL
```

#### C) Syntetický thinking pro Claude

Generovat ThinkingEvent z Claude tool_use/result eventů:

```python
# V engine._handle_raw_event():
if event_type == "tool_use":
    self.emit(ThinkingEvent(
        thought=f"Deciding to use {event['tool_name']}",
        phase=ThinkingPhase.TOOL_PLANNING,
        is_start=True,
        is_complete=True,
    ))
```

### 2.6 Dotčené soubory

| Soubor | Změna |
|--------|-------|
| `avatar_engine/events.py` | Rozšíření ThinkingEvent, nový ThinkingPhase enum |
| `avatar_engine/bridges/gemini.py:290-316` | `_handle_acp_update()` — emit structured ThinkingEvent |
| `avatar_engine/bridges/codex.py:573-614` | `_extract_thinking_from_update()` — emit structured ThinkingEvent |
| `avatar_engine/engine.py:595-616` | `_handle_raw_event()` — syntetický thinking pro Claude |
| `avatar_engine/bridges/gemini.py:720-767` | Extrakce + klasifikace |
| `avatar_engine/bridges/codex.py:573-614` | Extrakce + klasifikace |
| `examples/gui_integration.py` | Ukázat phase-based avatar animation |

---

## 3. GAP-2: Paralelní operace — Avatar zamrzne při multi-tool execution

### 3.1 Kontext: Moderní AI modely pracují paralelně

Modely jako Claude Opus 4.6 a Gemini 3 umějí:

1. **Paralelní tool_use** — spustit 3-5 nástrojů současně (Read + Grep + Glob)
2. **Paralelní agenty** — Task tool spustí podproces, hlavní kontext pokračuje
3. **Background operace** — Bash s `run_in_background=true`, výsledek později
4. **Přerušitelné operace** — uživatel může psát zatímco AI pracuje

**Reálný příklad z Claude Opus 4.6:**
```
User: "Analyzuj tento codebase"
AI: [současně spustí]
  ├── Task agent 1: "Research file structure"
  ├── Task agent 2: "Search for patterns"
  ├── Bash (background): "find . -name '*.py' | wc -l"
  └── Read: "README.md"
```

VSCode s tímto občas **selhává** — UI neví, jak zobrazit 4 paralelní operace
a uživatel vidí jen "Claude is thinking..." bez detailů.

### 3.2 Aktuální stav v Avatar Engine

**Diagnóza: Avatar Engine NEMŮŽE zobrazit paralelní operace.**

#### A) Jeden send() = jeden výsledek

`BaseBridge.send()` (`base.py:390-408`) je sekvenční:

```python
async def _send_persistent(self, prompt: str) -> List[Dict[str, Any]]:
    self._proc.stdin.write((line + "\n").encode())
    await self._proc.stdin.drain()
    return await self._read_until_turn_complete()  # Čeká na CELÝ výsledek
```

Není možnost paralelně číst dílčí výsledky z více tool_use operací.

#### B) ToolEvent nemá paralelní kontext

`ToolEvent` (`events.py:55-68`) neříká, které operace běží současně:

```python
@dataclass
class ToolEvent(AvatarEvent):
    tool_name: str = ""
    tool_id: str = ""
    status: str = "started"  # started, completed, failed
    # CHYBÍ: parallel_group, concurrent_count, is_background
```

GUI dostane 3× `ToolEvent(status="started")` ale neví:
- Jsou tyto 3 tools **paralelní** nebo **sekvenční**?
- Kolik jich celkem běží?
- Může uživatel mezitím interagovat?

#### C) Žádný progress tracking pro dlouhé operace

Když AI spustí Bash příkaz, který trvá 30 sekund:
- GUI nevidí žádný progress
- Není možnost cancel z GUI
- Uživatel neví, co se děje

#### D) stdin write bez zámku

`base.py:395,403` — stdin zápisy **nejsou chráněny zámkem**:

```python
# _send_persistent:
self._proc.stdin.write((line + "\n").encode())  # NO LOCK
# _stream_persistent:
self._proc.stdin.write((line + "\n").encode())  # NO LOCK
```

Pokud by GUI povolilo uživateli psát zatímco AI pracuje (interrupt pattern),
dva souběžné zápisy do stdin by se proplétly → garbled input → process error.

#### E) ACP text buffer race condition

`gemini.py:310,352` — `_acp_text_buffer` se zapisuje z ACP callbacku a čte z hlavního vlákna:

```python
# Callback (potenciálně z jiného vlákna):
self._acp_text_buffer += text  # RACE — žádný zámek

# Hlavní vlákno:
self._acp_text_buffer = ""  # RACE — clear zatímco callback píše
```

### 3.3 Proč je to kritické pro GUI

GUI avatar musí umět:

1. **Zobrazit více aktivit současně**:
   - "Avatar čte 3 soubory" (animace lupy × 3)
   - Progress bar pro každou operaci
   - Celkový progress "2 z 5 dokončeno"

2. **Reagovat na přerušení uživatelem**:
   - Uživatel napíše novou zprávu → avatar přeruší aktuální práci
   - Nebo: uživatel klikne "Cancel" → zastaví běžící tool
   - Nebo: uživatel upřesní zadání → avatar adjustuje plán

3. **Rozlišit pozadí vs popředí**:
   - Pozadí: Agent běží, avatar ukazuje malý spinner
   - Popředí: Avatar aktivně mluví, TTS aktivní
   - GUI nesmí blokovat interakci

4. **Zobrazit strom operací**:
   ```
   ┌─ Hlavní prompt: "Analyzuj codebase"
   │  ├─ [DONE] Read README.md
   │  ├─ [RUNNING] Task: Search patterns (3 files found)
   │  ├─ [RUNNING] Task: Explore structure
   │  └─ [PENDING] Synthesis
   ```

### 3.4 Vzory z referenčních projektů

**Gemini CLI** má sofistikovaný `useToolExecutionScheduler` s MessageBus pub/sub
a tool groups vizualizované v `ToolGroupMessage.tsx` — viz **sekce 15.4**.
Tools jsou groupovány podle `schedulerId` a mají 6-stavový lifecycle
(Pending→Confirming→Executing→Success/Error/Cancelled).

**Codex** používá `running_commands: HashMap<String, RunningCommand>` pro tracking
paralelních procesů a `active_cell` pattern pro coalescing operací do skupin —
viz **sekce 15.3**.

**Gemini CLI `useTurnActivityMonitor`** sleduje operation start time a detekuje
shell redirections — viz **sekce 15.4**.

### 3.5 Navrhované řešení

#### A) Nový ActivityEvent

```python
@dataclass
class ActivityEvent(AvatarEvent):
    """
    Tracks concurrent activities — tool executions, background tasks, agents.

    GUI uses this to show a tree of parallel operations with progress.
    """
    activity_id: str = ""              # Unique ID for this activity
    parent_activity_id: str = ""       # Parent (for nested agents/tasks)
    activity_type: str = ""            # "tool_use", "agent", "background_task"
    name: str = ""                     # Human-readable name
    status: ActivityStatus = ActivityStatus.PENDING
    progress: float = 0.0             # 0.0-1.0 (if estimable)
    detail: str = ""                  # Current status detail
    concurrent_group: str = ""        # Groups parallel activities
    is_cancellable: bool = False      # Can GUI cancel this?
    started_at: float = 0.0
    completed_at: float = 0.0


class ActivityStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

#### B) ActivityTracker v Engine

```python
class ActivityTracker:
    """Tracks concurrent activities and emits ActivityEvents."""

    def __init__(self, emitter: EventEmitter):
        self._activities: Dict[str, ActivityEvent] = {}
        self._emitter = emitter
        self._lock = asyncio.Lock()

    async def start_activity(self, activity_id: str, **kwargs) -> None:
        async with self._lock:
            event = ActivityEvent(activity_id=activity_id, status=ActivityStatus.RUNNING, **kwargs)
            self._activities[activity_id] = event
            self._emitter.emit(event)

    async def complete_activity(self, activity_id: str, **kwargs) -> None:
        async with self._lock:
            if activity_id in self._activities:
                event = self._activities[activity_id]
                event.status = ActivityStatus.COMPLETED
                self._emitter.emit(event)
                del self._activities[activity_id]

    @property
    def active_count(self) -> int:
        return len(self._activities)

    @property
    def active_activities(self) -> List[ActivityEvent]:
        return list(self._activities.values())
```

#### C) Paralelní tool tracking z raw events

```python
# V engine._handle_raw_event():
if event_type == "tool_use":
    tool_id = event.get("tool_id", "")
    await self._activity_tracker.start_activity(
        activity_id=tool_id,
        activity_type="tool_use",
        name=event.get("tool_name", ""),
        concurrent_group=event.get("parallel_group", ""),  # z providera
    )
elif event_type == "tool_result":
    tool_id = event.get("tool_id", "")
    await self._activity_tracker.complete_activity(tool_id)
```

#### D) Zámek na stdin pro bezpečný concurrent přístup

```python
# V BaseBridge.__init__():
self._stdin_lock = asyncio.Lock()

# V _send_persistent() a _stream_persistent():
async with self._stdin_lock:
    self._proc.stdin.write((line + "\n").encode())
    await self._proc.stdin.drain()
```

#### E) Interrupt/Cancel API

```python
# V AvatarEngine:
async def cancel_activity(self, activity_id: str) -> bool:
    """Cancel a running activity (tool, agent, background task)."""
    # Send cancellation to bridge if supported
    pass

async def interrupt(self) -> bool:
    """Interrupt current AI processing — user wants to type new message."""
    # For Claude: send Ctrl+C equivalent via stdin
    # For ACP: cancel current prompt
    pass
```

### 3.6 Dotčené soubory

| Soubor | Změna |
|--------|-------|
| `avatar_engine/events.py` | Nový ActivityEvent, ActivityStatus |
| `avatar_engine/engine.py` | ActivityTracker, interrupt(), cancel_activity() |
| `avatar_engine/bridges/base.py:395,403` | stdin zámek |
| `avatar_engine/bridges/base.py` | cancel() metoda na BaseBridge |
| `avatar_engine/bridges/gemini.py:310,352` | Zámek na `_acp_text_buffer` a `_acp_events` |
| `avatar_engine/bridges/claude.py` | Paralelní tool_use parsing z stream-json |
| `examples/gui_integration.py` | Ukázka ActivityEvent handling |

---

## 4. GAP-3: Thinking leak v Gemini oneshot režimu

### 4.1 Aktuální stav

**ACP režim:** Thinking se správně extrahuje přes `_extract_thinking_from_update()` a emituje
jako `ThinkingEvent`. Text odpovědi neobsahuje thinking — `_extract_text_from_update()`
explicitně přeskakuje `type == "thinking"` bloky.

**Oneshot režim:** Thinking se **NEFILTRUJE** z textového výstupu!

V `BaseBridge._send_oneshot()` (`base.py:452-484`) se čte raw stdout ze subprocesu
a parsuje jako stream-json eventy. Ale **neexistuje filtr**, který by oddělil thinking
content od response content.

Když Gemini CLI vrátí stream-json s thinking bloky:
```json
{"type": "thinking", "text": "Let me analyze this carefully..."}
{"type": "text", "text": "The answer is 42."}
```

Oneshot režim přečte OBĚ jako text → avatar řekne nahlas:
> "Let me analyze this carefully... The answer is 42."

### 4.2 Dopad na GUI avatara

- Avatar **řekne nahlas své vnitřní myšlenky** → confusing pro uživatele
- TTS engine přehraje thinking text → zvuková kaše
- Odpověď je delší, než má být → pomalejší UX
- Uživatel vidí "raw AI" místo clean odpovědi

### 4.3 Kde přesně je problém

`GeminiBridge` používá v oneshot režimu `BaseBridge._send_oneshot()` (`base.py:452-484`),
která volá `_parse_stream_events()` (`base.py:495-520`). Tato metoda parsuje JSON lines
ale **nerozlišuje thinking od text**:

```python
# base.py:495-520 (_parse_stream_events)
for line in raw_output.splitlines():
    data = json.loads(line)
    events.append(data)  # Vše se přidá bez filtru
```

Žádný kód nefiltruje `{"type": "thinking", ...}` eventy v oneshot režimu.

### 4.4 Navrhované řešení

#### A) Filtr v `_send_oneshot()` výsledku

```python
# V GeminiBridge — override _send_oneshot nebo v _process_oneshot_response:
def _filter_thinking_from_events(self, events: List[Dict]) -> Tuple[List[Dict], List[str]]:
    """Separate thinking events from response events."""
    clean_events = []
    thinking_chunks = []
    for event in events:
        if event.get("type") == "thinking":
            thinking_chunks.append(event.get("text", ""))
            # Emit ThinkingEvent
            if self._on_event:
                self._on_event({"type": "thinking", "thought": event.get("text", "")})
        else:
            clean_events.append(event)
    return clean_events, thinking_chunks
```

#### B) BaseBridge: obecný thinking filtr

Přidat do `BaseBridge._send_oneshot()` obecný filtr:

```python
# V base.py _send_oneshot() po parsování:
if self._should_filter_thinking():
    events = [e for e in events if e.get("type") != "thinking"]
```

### 4.5 Dotčené soubory

| Soubor | Změna |
|--------|-------|
| `avatar_engine/bridges/gemini.py` | Override oneshot processing, thinking filter |
| `avatar_engine/bridges/base.py:452-520` | Obecný thinking filtr v `_send_oneshot()` |

---

## 5. GAP-4: Thread Safety — Race Conditions

### 5.1 Aktuální stav

Avatar Engine má **13 identifikovaných race conditions** různé závažnosti.
Pro GUI integraci (kde events přicházejí z ACP callbacků, stderr monitorů,
health check tasků a hlavního vlákna současně) jsou tyto problémy **kritické**.

### 5.2 Kompletní seznam race conditions

#### CRITICAL severity

| # | Problém | Soubor | Řádky | Popis |
|---|---------|--------|-------|-------|
| RC-1 | `asyncio.set_event_loop()` not thread-safe | `engine.py` | 215-216 | `_get_sync_loop()` vytvoří event loop a nastaví ho globálně. Pokud více vláken volá sync wrappery (`chat_sync()`, `start_sync()`), můžou si navzájem přepsat event loop. **Crash v multi-threaded GUI frameworku (Qt, GTK).** |
| RC-2 | EventEmitter.emit() nemá zámek | `events.py` | 188-209 | `emit()` iteruje přes `_handlers` a `_global_handlers` bez synchronizace. Pokud jiné vlákno volá `add_handler()` nebo `remove_handler()` současně → `RuntimeError: dictionary changed size during iteration` nebo missed events. **Přímo relevantní pro GUI — handler registrace z GUI threadu, emit z async vlákna.** |

#### HIGH severity

| # | Problém | Soubor | Řádky | Popis |
|---|---------|--------|-------|-------|
| RC-3 | `_acp_text_buffer` concurrent write | `gemini.py` | 310, 352 | ACP callback (`_handle_acp_update`) píše do `_acp_text_buffer`, hlavní vlákno ho čte a clearuje v `_send_acp()`. String concatenation v Pythonu není atomická pro přidání. |
| RC-4 | `_acp_events` concurrent access | `gemini.py` | 314, 352, 376 | Stejný problém — list append z callbacku, clear z hlavního vlákna. |
| RC-5 | Signal handler volá `asyncio.create_task()` | `engine.py` | 689 | Signal handler (`handle_signal`) volá `_initiate_shutdown()`, která volá `asyncio.create_task()`. **create_task() bere interní zámky event loopu — volat ze signal handleru je undefined behavior.** |
| RC-6 | Signal handler volá `asyncio.run()` | `engine.py` | 693 | Fallback v signal handleru — `asyncio.run()` vytvoří nový event loop uprostřed běžícího programu. |
| RC-7 | stdin zápisy bez zámku | `base.py` | 395, 403 | `_send_persistent()` a `_stream_persistent()` píšou do stdin bez mutual exclusion. Dva souběžné `send()` → garbled input → process error. |

#### MEDIUM severity

| # | Problém | Soubor | Řádky | Popis |
|---|---------|--------|-------|-------|
| RC-8 | `_stderr_buffer` concurrent access | `base.py` | 293, 174-180 | `_monitor_stderr()` task appenduje, `get_stderr_buffer()` čte ve stejný čas. |
| RC-9 | History list not protected | `base.py` | 326-327 | `history.append()` v `send()` bez zámku, `get_history()` čte z jiného kontextu. |
| RC-10 | `_stats` dict not protected | `base.py` | 577-589 | `_update_stats()` modifikuje dict, `check_health()` ho čte. Dictionary mutations aren't atomic. |
| RC-11 | Health check races with stop() | `engine.py` | 603-620 | Health check task může spustit `_restart()` ve stejný okamžik, kdy hlavní vlákno volá `stop()`. |
| RC-12 | `RateLimiterSync` nemá zámky | `rate_limit.py` | 230-250 | Sync rate limiter modifikuje `_tokens` a `_last_update` bez `threading.Lock()`. |
| RC-13 | EventEmitter dict mutations v `add_handler`/`remove_handler` | `events.py` | 172-186, 211-226 | List/dict modifikace bez synchronizace. |

### 5.3 Dopad na GUI avatara

GUI frameworky (Qt, GTK, Tauri) mají **vlastní event loop** na hlavním vlákně.
Avatar Engine běží v **async event loop** na jiném vlákně. To znamená:

1. **Event handlery registrované z GUI vlákna** (`engine.on(TextEvent, gui_callback)`)
   budou volány z async vlákna → RC-2 způsobí crash
2. **`chat_sync()` volaný z GUI vlákna** → RC-1 přepíše event loop
3. **ACP callback z SDK vlákna** → RC-3, RC-4 poškodí data
4. **SIGINT z terminálu** → RC-5, RC-6 undefined behavior

### 5.4 Navrhované řešení

#### A) EventEmitter — threading.Lock

```python
import threading

class EventEmitter:
    def __init__(self):
        self._handlers = {}
        self._global_handlers = []
        self._lock = threading.Lock()  # Thread-safe pro GUI integrace

    def emit(self, event):
        with self._lock:
            handlers = list(self._global_handlers)  # Snapshot
            specific = list(self._handlers.get(type(event), []))
        # Volání handlerů BEZ zámku — handler může registrovat další handler
        for h in handlers:
            try: h(event)
            except Exception as e: logger.error(...)
        for h in specific:
            try: h(event)
            except Exception as e: logger.error(...)

    def add_handler(self, event_type, handler):
        with self._lock:
            self._handlers.setdefault(event_type, []).append(handler)
```

#### B) Thread-safe volání z GUI vlákna

```python
# V AvatarEngine:
def emit_threadsafe(self, event: AvatarEvent) -> None:
    """Emit event from any thread (GUI thread, signal handler, etc)."""
    try:
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(self.emit, event)
    except RuntimeError:
        self.emit(event)  # No running loop — direct emit
```

#### C) Signal handler fix

```python
def _initiate_shutdown(self) -> None:
    self._shutting_down = True  # Atomic flag (CPython GIL)
    # Signal handlers MUST NOT call create_task or asyncio.run
    # Instead, just set flag — health check loop will detect it
```

#### D) ACP buffer locks

```python
# V GeminiBridge:
self._acp_buffer_lock = asyncio.Lock()

def _handle_acp_update(self, session_id, update):
    # Use lock for buffer access
    with self._acp_buffer_lock:
        self._acp_text_buffer += text
        self._acp_events.append(event)
```

### 5.5 Dotčené soubory

| Soubor | Změna |
|--------|-------|
| `avatar_engine/events.py` | threading.Lock v EventEmitter |
| `avatar_engine/engine.py:215-216` | Oprava `_get_sync_loop()` |
| `avatar_engine/engine.py:635-708` | Oprava signal handler |
| `avatar_engine/bridges/base.py` | Zámky na stdin, stderr_buffer, history, stats |
| `avatar_engine/bridges/gemini.py` | Zámky na ACP buffers |
| `avatar_engine/utils/rate_limit.py:191-265` | threading.Lock v RateLimiterSync |

---

## 6. GAP-5: System Prompt nekonzistentní napříč providery

### 6.1 Aktuální stav

| Provider | Mechanismus | Funguje? |
|----------|-------------|----------|
| Claude | `--append-system-prompt <text>` CLI flag (`claude.py:230-231`) | ANO |
| Gemini ACP | `GEMINI_SYSTEM_MD` env var → temp soubor (`gemini.py:568`) | ANO |
| Gemini oneshot | Injekce do prompt textu přes `_build_effective_prompt()` (`gemini.py:576-603`) | ČÁSTEČNĚ — prompt injection není system prompt |
| Codex | **NEPODPORUJE** — `_setup_config_files()` je no-op (`codex.py:450-458`) | NE |

### 6.2 Proč je to problém pro GUI avatara

System prompt definuje **osobnost avatara**:

```yaml
system_prompt: |
  Jsi Avatar jménem Aria. Jsi přátelská, vtipná, a mluvíš česky.
  Když nevíš odpověď, řekni to upřímně.
  Nikdy nepoužívej emoji.
  Tvoje odpovědi jsou krátké a výstižné.
```

Pokud Codex tento prompt **ignoruje**, avatar se chová úplně jinak než u Claude/Gemini:
- Mluví anglicky místo česky
- Nemá jméno "Aria"
- Používá emoji
- Odpovídá rozvláčně

Uživatel přepne provider → avatar změní osobnost → confusing UX.

### 6.3 Gemini oneshot — prompt injection problém

V oneshot režimu (`gemini.py:593-602`) se system prompt injektuje do user promptu:

```python
parts = []
if self.system_prompt:
    parts.append(f"[System: {self.system_prompt}]")
parts.append(f"User: {prompt}")
effective = "\n".join(parts)
```

Toto **není system prompt** — je to text v user message. Model může:
- Ignorovat "System:" prefix
- Vypisovat system prompt zpět uživateli
- Chovat se jinak než se skutečným system promptem

### 6.4 Navrhované řešení

#### A) Codex: system prompt přes ACP instruction

Prověřit, zda ACP `prompt()` podporuje `instruction` parametr. Pokud ano:

```python
# V CodexBridge._send_acp():
result = await self._acp_conn.prompt(
    session_id=self._session_id,
    prompt=[text_block(message)],
    instruction=self.system_prompt,  # ACP instruction field
)
```

Pokud ACP nepodporuje `instruction`, prepend system prompt do prvního promptu:

```python
# V CodexBridge.send():
if self._message_count == 0 and self.system_prompt:
    message = f"[SYSTEM INSTRUCTIONS]\n{self.system_prompt}\n[END INSTRUCTIONS]\n\n{message}"
```

#### B) Provider capabilities flag

```python
@dataclass
class ProviderCapabilities:
    supports_system_prompt: bool = False
    system_prompt_method: str = ""  # "native", "injected", "unsupported"
    # ... more capabilities
```

GUI pak může zobrazit varování: "Codex nepodporuje system prompt — avatar nebude mít nastavenou osobnost."

### 6.5 Dotčené soubory

| Soubor | Změna |
|--------|-------|
| `avatar_engine/bridges/codex.py` | System prompt support (ACP instruction nebo prepend) |
| `avatar_engine/bridges/gemini.py:576-603` | Oprava oneshot system prompt |
| `avatar_engine/types.py` | Nový ProviderCapabilities |
| `avatar_engine/bridges/base.py` | `provider_capabilities` property |

---

## 7. GAP-6: Budget Control je pasivní — Avatar utratí víc, než má

### 7.1 Aktuální stav

`max_budget_usd` se nastavuje v configu (`claude.py:76`) a předává Claude CLI přes
`--max-turns` (ne přes budget flag). Ale:

1. **Žádná pre-request kontrola** — Engine nezkontroluje, jestli je budget překročen PŘED odesláním dalšího promptu
2. **Tracking je post-hoc** — `_track_cost()` (`claude.py:432-440`) extrahuje cost z odpovědi AŽ PO její přijetí
3. **`is_over_budget()`** (`claude.py:455-459`) jen **vrací bool** — nic neblokuje
4. **Gemini a Codex** nemají cost tracking vůbec — cost je vždy 0

```python
# claude.py:455-459
def is_over_budget(self) -> bool:
    if self._max_budget_usd and self._total_cost_usd > 0:
        return self._total_cost_usd >= self._max_budget_usd
    return False
# Nikde se nevolá jako guard!
```

### 7.2 Dopad na GUI avatara

- Avatar utratí $5 místo limit $1 → uživatel je naštvaný
- GUI zobrazuje cost tracker, ale nebrání překročení
- Automatické konverzace (agent loops) můžou rychle vyčerpat budget

### 7.3 Navrhované řešení

```python
# V AvatarEngine.chat():
async def chat(self, message: str) -> BridgeResponse:
    # Pre-request budget check
    if self._bridge.is_over_budget():
        self.emit(ErrorEvent(
            error=f"Budget exceeded: ${self._bridge._total_cost_usd:.2f} / ${self._bridge._max_budget_usd:.2f}",
            recoverable=False,
        ))
        return BridgeResponse(
            content="",
            success=False,
            error="Budget limit exceeded",
        )
    # ... normal flow
```

### 7.4 Dotčené soubory

| Soubor | Změna |
|--------|-------|
| `avatar_engine/engine.py:252+` | Pre-request budget check v `chat()` |
| `avatar_engine/bridges/base.py` | `is_over_budget()` metoda pro všechny bridgy |
| `avatar_engine/bridges/gemini.py` | Cost estimation (Gemini API cost model) |
| `avatar_engine/bridges/codex.py` | Cost estimation (OpenAI cost model) |

---

## 8. GAP-7: Stderr není surfaceován jako events

### 8.1 Aktuální stav

stderr je zpracováno třemi různými způsoby:

| Režim | Zachycení | Kam jde | Surfaceováno? |
|-------|-----------|---------|---------------|
| Persistent (`base.py:284-300`) | `_monitor_stderr()` async task | `_stderr_buffer` + logger.debug + `_on_stderr` callback | Callback jen — NE event |
| Oneshot (`base.py:459-469`) | `proc.communicate()` | logger.debug | NE |
| ACP (Gemini, Codex) | ACP SDK interně | Neznámo | NE |
| Claude startup (`claude.py:143-147`) | `proc.stderr.read()` | RuntimeError message | Jen při startup failure |

**ErrorEvent se emituje pouze pro 3 kritické případy** (`engine.py:184, 588, 612`):
start failure, restart failure, health check failure. Nikdy pro stderr output.

### 8.2 Dopad na GUI avatara

- Subprocess vypíše varování → GUI nevidí
- Auth token vyprší, stderr říká "Token expired" → avatar jen přestane odpovídat
- Gemini CLI upgrade změní API → stderr říká "Deprecated" → nikdo neví
- Uživatel nevidí diagnostiku → nemůže vyřešit problém

### 8.3 Navrhované řešení

#### Nový DiagnosticEvent

```python
@dataclass
class DiagnosticEvent(AvatarEvent):
    """
    Diagnostic information from subprocess stderr, warnings, deprecations.
    GUI can show in debug panel or status bar.
    """
    message: str = ""
    level: str = "info"  # "info", "warning", "error", "debug"
    source: str = ""     # "stderr", "acp", "health_check"
```

#### Emitovat z _monitor_stderr

```python
async def _monitor_stderr(self) -> None:
    while self._proc and self._proc.returncode is None:
        line = await self._proc.stderr.readline()
        if not line:
            break
        text = line.decode(errors="replace").strip()
        if text:
            self._stderr_buffer.append(text)
            level = self._classify_stderr(text)
            if self._on_event:
                self._on_event({
                    "type": "diagnostic",
                    "message": text,
                    "level": level,
                    "source": "stderr",
                })
```

### 8.4 Dotčené soubory

| Soubor | Změna |
|--------|-------|
| `avatar_engine/events.py` | Nový DiagnosticEvent |
| `avatar_engine/bridges/base.py:284-300` | Emit DiagnosticEvent z `_monitor_stderr()` |
| `avatar_engine/engine.py` | Handle DiagnosticEvent v `_handle_raw_event()` |

---

## 9. GAP-8: MCP Tool Policy je all-or-nothing

### 9.1 Aktuální stav

| Provider | Tool Policy | Granularita |
|----------|------------|-------------|
| Claude | `allowed_tools` list → `--settings` flag (`claude.py:172-174`) | Per-tool allowlist |
| Gemini ACP | MCP servers passed via ACP protocol (`gemini.py:265-276`) | Per-server (všechny tools serveru) |
| Codex ACP | MCP servers passed via ACP protocol (`codex.py:256-270`) | Per-server (všechny tools serveru) |

Pro Gemini a Codex: buď **celý MCP server** je povolený, nebo ne.
Nelze říct: "Z serveru 'file-tools' povol Read a Grep, ale ne Write a Bash."

### 9.2 Dopad na GUI avatara

Avatar GUI má různé "režimy":
- **Read-only mode** — avatar jen čte a analyzuje
- **Edit mode** — avatar může upravovat soubory
- **Admin mode** — avatar může spouštět příkazy

Bez granulárních permissions musí GUI vybrat celé MCP servery → méně bezpečné.

### 9.3 Navrhované řešení

Engine-level tool filter:

```python
class ToolPolicy:
    """Per-tool allow/deny rules applied at engine level."""
    def __init__(self, allow: List[str] = None, deny: List[str] = None):
        self._allow = set(allow or [])
        self._deny = set(deny or [])

    def is_allowed(self, tool_name: str) -> bool:
        if self._deny and tool_name in self._deny:
            return False
        if self._allow:
            return tool_name in self._allow
        return True
```

### 9.4 Dotčené soubory

| Soubor | Změna |
|--------|-------|
| `avatar_engine/engine.py` | ToolPolicy class, apply before tool execution |
| `avatar_engine/types.py` | ToolPolicy dataclass |
| `avatar_engine/config.py` | Parse tool_policy from YAML |

---

## 10. GAP-9: Chybí Runtime Capabilities API

### 10.1 Aktuální stav

GUI může dotazovat pouze `session_capabilities` (`types.py:70-79`):
```python
@dataclass
class SessionCapabilitiesInfo:
    can_list: bool = False
    can_load: bool = False
    can_continue_last: bool = False
```

Chybí informace o:
- Podporuje provider thinking? (`thinking_supported: bool`)
- Podporuje provider cost tracking? (`cost_tracking_supported: bool`)
- Podporuje provider system prompt? (`system_prompt_method: str`)
- Podporuje provider streaming? (`streaming_supported: bool`)
- Podporuje provider MCP? (`mcp_supported: bool`)
- Podporuje provider paralelní tool_use? (`parallel_tools: bool`)
- Podporuje provider cancel/interrupt? (`cancellable: bool`)

### 10.2 Dopad na GUI avatara

GUI neví, co může zobrazit:
- Zobrazit thinking panel? → Záleží na provideru
- Zobrazit cost widget? → Jen pro Claude
- Zobrazit cancel button? → Záleží na provideru
- Zobrazit session browser? → `session_capabilities`

### 10.3 Navrhované řešení

```python
@dataclass
class ProviderCapabilities:
    """Full provider capability declaration for GUI adaptation."""
    # Session
    can_list_sessions: bool = False
    can_load_session: bool = False
    can_continue_last: bool = False

    # Thinking
    thinking_supported: bool = False
    thinking_structured: bool = False  # True pokud má phases/categories

    # Cost
    cost_tracking: bool = False
    budget_enforcement: bool = False

    # System prompt
    system_prompt: str = "unsupported"  # "native" | "injected" | "unsupported"

    # Streaming
    streaming: bool = True
    parallel_tools: bool = False

    # Control
    cancellable: bool = False
    interruptible: bool = False

    # MCP
    mcp_supported: bool = False
    tool_policy_granularity: str = "server"  # "server" | "tool" | "none"
```

### 10.4 Dotčené soubory

| Soubor | Změna |
|--------|-------|
| `avatar_engine/types.py` | Nový ProviderCapabilities |
| `avatar_engine/bridges/base.py` | `provider_capabilities` property |
| `avatar_engine/bridges/claude.py` | Set capabilities (thinking=False, cost=True, ...) |
| `avatar_engine/bridges/gemini.py` | Set capabilities (thinking=True, cost=False, ...) |
| `avatar_engine/bridges/codex.py` | Set capabilities |
| `avatar_engine/engine.py` | Expose `capabilities` property |

---

## 11–14. Přesunuto do sekcí 18–21

> Implementační plán, souhrnná tabulka souborů, rizika a kritéria úspěchu
> byly aktualizovány a přesunuty do sekcí 18–21 s ohledem na nové poznatky
> z analýzy referenčních projektů, CLI display požadavky a demo GUI specifikaci.

---

## 15. Analýza referenčních projektů — Jak to řeší Gemini CLI, Codex a Claude Code

Prostudovali jsme zdrojové kódy všech 3 referenčních projektů. Claude Code nemá
veřejný zdrojový kód (kompilovaný npm balíček), ale Gemini CLI a Codex mají
vynikající implementace, ze kterých se můžeme poučit.

### 15.1 Gemini CLI — Thinking / ThoughtSummary

**Architektura:** Gemini CLI používá strukturovaný `ThoughtSummary` typ
s dvěma poli (`packages/core/src/utils/thoughtUtils.ts`):

```typescript
type ThoughtSummary = {
  subject: string;      // Krátký název — "Analyzing code structure"
  description: string;  // Zbytek thinking textu
};
```

**Parsování:** `parseThought()` extrahuje subject z bold markdown markeru `**Subject**`:

```typescript
function parseThought(rawText: string): ThoughtSummary {
  // Hledá **Subject** pattern ve streamu thinking textu
  // Subject = text mezi ** a ** markery
  // Description = vše ostatní
}
```

**Zobrazení v TUI (`LoadingIndicator.tsx`):**
- Spinner + `thought.subject` jako primární text
- Timer: `(esc to cancel, 42s)`
- Thinking subject se mění dynamicky jak model přemýšlí
- Podpora inline i block layout, adaptivní šířka

**Stream processing (`useGeminiStream.ts:1070-1073`):**
```typescript
case ServerGeminiEventType.Thought:
  setLastGeminiActivityTime(Date.now());
  setThought(event.value);  // ThoughtSummary objekt
  break;
```

**Klíčové poznatky pro avatar-engine:**
- `ThoughtSummary.subject` = odpovídá našemu navrhovanému `ThinkingPhase` — dá se extrahovat z bold markeru
- Gemini CLI aktualizuje thinking v reálném čase jak delta chunky přicházejí
- Thinking se zobrazuje jako **shimmer/spinner text**, ne jako plný text — GUI ukazuje jen subject
- Thinking se resetuje na `null` při cancel nebo chybě

### 15.2 Codex — Reasoning jako first-class koncept

**Architektura:** Codex má reasoning jako **dedikovaný typ ve protokolu**
(`app-server-protocol/schema/typescript/`):

```typescript
// ResponseItem union má explicitní "reasoning" typ:
type ResponseItem = { type: "message" | "reasoning" | "local_shell_call" }

// Reasoning content:
type ReasoningItemContent = {
  type: "reasoning_text" | "text";
  text: string;
}

// Token tracking:
type TokenUsage = {
  input_tokens: number;
  output_tokens: number;
  reasoning_output_tokens: number;  // Samostatné reasoning tokeny!
}
```

**TUI implementace (`chatwidget.rs:544-547, 1249-1288`):**

Codex používá **dual-buffer pattern** pro reasoning:

```rust
// Akumuluje aktuální reasoning blok pro extrakci headeru
reasoning_buffer: String,
// Akumuluje celý reasoning content pro transcript záznam
full_reasoning_buffer: String,
```

**Reasoning flow v chatwidget.rs:**

1. `on_agent_reasoning_delta(delta)` — přijde chunk reasoning textu:
   - Přidá do `reasoning_buffer`
   - Extrahuje **first bold header** z textu (stejný `**Header**` pattern jako Gemini!)
   - Nastaví header jako shimmer status text
   - Pokud běží exec operace, exec status má přednost

2. `on_reasoning_section_break()` — konec jedné sekce reasoning:
   - Akumuluje `reasoning_buffer` do `full_reasoning_buffer`
   - Resetuje `reasoning_buffer` pro další sekci

3. `on_agent_reasoning_final()` — konec celého reasoning bloku:
   - Vytvoří `history_cell::new_reasoning_summary_block()` z `full_reasoning_buffer`
   - Přidá do historie (transcript-only, ne do main output)
   - Vymaže oba buffery

**extract_first_bold() (chatwidget.rs:7018-7044):**
```rust
fn extract_first_bold(s: &str) -> Option<String> {
    // Najde první **text** pattern v reasoning streamu
    // Vrací text uvnitř bold markerů jako status header
}
```

**Shimmer efekt (`shimmer.rs`):**
- Animovaný shimmer efekt (cosine wave RGB blending) pro "thinking" indikátor
- Status header se zobrazuje se shimmer animací
- Fallback na DIM/BOLD modifikátory bez true color

**Reasoning effort (`ReasoningEffort`):**
- Low / Medium / High / XHigh — konfigurovatelné
- Popup pro výběr reasoning effort
- `model_reasoning_summary` — konfigurovatelná sumarizace

**Klíčové poznatky pro avatar-engine:**
- **Bold header extraction** = identický pattern s Gemini! Oba extrahují `**Subject**` z thinking/reasoning textu
- **Dual buffer** = elegantní řešení pro live display + transcript recording
- **Reasoning jako ResponseItem typ** = reasoning je first-class, ne side-channel
- **reasoning_output_tokens** = samostatný tracking thinking tokenů — důležité pro cost!
- **Section breaks** = reasoning přichází v sekcích, ne jako jeden blob
- **Status header priority** = exec waiting > reasoning header > "Working" fallback

### 15.3 Codex — Paralelní operace a event dispatch

**Event architektura (`chatwidget.rs:3876-3950`):**

Codex používá centrální `dispatch_event_msg()` pro všechny eventy:

```rust
fn dispatch_event_msg(&mut self, id: Option<String>, msg: EventMsg, from_replay: bool) {
    match msg {
        EventMsg::TurnStarted(_) => self.on_task_started(),
        EventMsg::TurnComplete(_) => self.on_task_complete(...),
        EventMsg::AgentReasoningDelta(_) => self.on_agent_reasoning_delta(delta),
        EventMsg::ExecCommandBegin(_) => /* spustí exec cell */,
        EventMsg::ExecCommandOutputDelta(_) => /* stream output */,
        EventMsg::ExecCommandEnd(_) => /* ukončí exec cell */,
        EventMsg::McpToolCallBegin(_) => /* MCP tool tracking */,
        EventMsg::McpToolCallEnd(_) => /* MCP tool complete */,
        EventMsg::WebSearchBegin(_) => /* web search tracking */,
        EventMsg::WebSearchEnd(_) => /* web search complete */,
        // ... 30+ event typů
    }
}
```

**Active cell pattern (`chatwidget.rs:488-498`):**
- `active_cell: Option<Box<dyn HistoryCell>>` — in-flight operace
- `active_cell_revision: u64` — monotonicky rostoucí revize pro cache invalidaci
- Operace se "coalesce" do skupin (exec group, tool group)
- Transcript overlay synchronizuje live tail z active_cell

**Unified exec wait (`chatwidget.rs:522-529`):**
- `running_commands: HashMap<String, RunningCommand>` — paralelní příkazy
- `unified_exec_wait_streak` — grupuje po sobě jdoucí exec operace
- `unified_exec_processes: Vec<UnifiedExecProcessSummary>` — souhrn procesů
- Status se přepíná mezi exec waiting a reasoning header

**Task running state (`chatwidget.rs:783-789`):**
```rust
fn update_task_running_state(&mut self) {
    self.bottom_pane.set_task_running(
        self.agent_turn_running || self.mcp_startup_status.is_some()
    );
}
```
- Dva nezávislé lifecycle: agent turn + MCP startup
- Bottom pane má jeden "task running" indikátor = derived state z obou

### 15.4 Gemini CLI — Parallel Tool Scheduling

**Scheduler + MessageBus (`useToolExecutionScheduler.ts`):**

Gemini CLI má sofistikovaný event-driven scheduler:

```typescript
// Tool calls grouped by schedulerId:
const [toolCallsMap, setToolCallsMap] = useState<
  Record<string, TrackedToolCall[]>
>({});

// Subscribe to tool updates via MessageBus:
messageBus.subscribe(MessageBusType.TOOL_CALLS_UPDATE, handler);
```

**Tool call states:**
- `scheduled` → `validating` → `awaiting_approval` → `executing` → `success`/`error`/`cancelled`
- Event-driven scheduler skrývá `scheduled`/`validating`/`awaiting_approval` z historie
- Jen `executing` a terminal stavy se zobrazují v UI

**Tool groups (`useGeminiStream.ts:360-425`, `ToolGroupMessage.tsx`):**

```typescript
// Filtruje a grupuje tool calls do vizuálních skupin:
const pendingToolGroupItems = useMemo((): HistoryItemWithoutId[] => {
  const remainingTools = toolCalls.filter(
    (tc) => !pushedToolCallIds.has(tc.request.callId),
  );
  // Vytvoří tool_group history item se všemi aktuálními tools
  return [{ type: 'tool_group', tools: [...], borderTop, borderBottom }];
}, [toolCalls, pushedToolCallIds]);
```

**ToolGroupMessage.tsx — vizuální rendering:**
- Renderuje border box kolem skupiny nástrojů
- Každý tool má vlastní `ToolMessage` nebo `ShellToolMessage`
- Shell tools mají embedded PTY s live output
- AskUser tools mají vlastní dialog UI (vyloučené z group)
- Event-driven mode skrývá Pending/Confirming tools (jsou v Global Queue)

**Turn Activity Monitor (`useTurnActivityMonitor.ts`):**
```typescript
// Sleduje čas začátku operace a detekci redirections:
export interface TurnActivityStatus {
  operationStartTime: number;     // Kdy operace začala
  isRedirectionActive: boolean;   // Potlačí inactivity prompts
}
```
- Resetuje timer při přechodu do Responding state nebo změně PTY
- Detekuje shell redirections v příkazech tool calls

**Klíčové poznatky pro avatar-engine:**
- **Scheduler s MessageBus** = pub/sub pattern pro tool updates je čistý design
- **Tool groups** = vizuální grupování paralelních nástrojů do border boxu
- **schedulerId** = tools patří ke scheduleru, ne ke globálnímu seznamu
- **Event-driven visibility** = skrýt tools v pre-execution stavu, ukazovat jen running/done
- **Activity monitoring** = sledovat operation start time pro inactivity detection
- **Background shells** = `backgroundShellCount`, `toggleBackgroundShell` — explicitní API pro pozadí

### 15.5 Gemini CLI — StreamingState a typy

**StreamingState enum (`types.ts`):**
```typescript
enum StreamingState {
  Idle,                     // Čeká na uživatele
  Responding,               // Model generuje odpověď
  WaitingForConfirmation,   // Čeká na potvrzení (tool approval)
}
```

**ToolCallStatus enum:**
```typescript
enum ToolCallStatus {
  Pending,     // Scheduled, waiting
  Canceled,    // User cancelled
  Confirming,  // Awaiting approval
  Executing,   // Running
  Success,     // Done OK
  Error,       // Done with error
}
```

**HistoryItem union — 20+ typů:**
```typescript
type HistoryItem =
  | HistoryItemUser
  | HistoryItemModel
  | HistoryItemToolGroup      // Skupina paralelních tools
  | HistoryItemThinking       // Thinking display
  | HistoryItemCompression    // Context compression event
  | HistoryItemMCPStatus      // MCP server status
  | HistoryItemConsole        // Console output
  | HistoryItemError          // Error display
  // ... a další
```

**Klíčové poznatky:** Bohatý typový systém umožňuje GUI přesně vědět, co zobrazit.
Avatar-engine by měl mít podobně bohatou event taxonomii.

### 15.6 Claude Code — Není zdrojový kód

Claude Code (`/home/box/git/github/claude-code/`) je **kompilovaný npm balíček**.
Obsahuje pouze: CHANGELOG.md, README.md, LICENSE.md, demo.gif, plugins/, examples/.

**Žádný TypeScript/JavaScript zdrojový kód k prostudování.**

Z CHANGELOG a README lze odvodit:
- Podporuje `--continue`, `--resume <id>`, `--session-id`, `--fork-session`
- Má Task tool pro paralelní agenty
- Status line zobrazuje stav operací
- Má hooks system (pre/post tool use)
- Thinking je interní (extended thinking API), ne veřejné

### 15.7 Shrnutí vzorů pro avatar-engine

| Pattern | Gemini CLI | Codex | Avatar-engine |
|---------|-----------|-------|---------------|
| Thinking structure | `ThoughtSummary{subject, description}` | `ReasoningItemContent` + dual buffer | **Navrhujeme: ThinkingEvent s phase, block_id** |
| Thinking extraction | `parseThought()` — `**bold**` parser | `extract_first_bold()` — `**bold**` parser | **Adoptovat: bold parser pro subject extrakci** |
| Thinking display | Spinner + subject text + timer | Shimmer animation + status header | **CLI: spinner + subject; GUI: avatar animace** |
| Parallel tools | `ToolGroupMessage` + `schedulerId` groups | `running_commands` HashMap + active_cell | **Navrhujeme: ActivityEvent + ActivityTracker** |
| Tool states | 6 stavů (Pending→Executing→Success/Error) | ExecCell lifecycle (begin→output→end) | **Adoptovat: 6-state ToolEvent** |
| Event dispatch | `useGeminiStream` — async iterator + switch | `dispatch_event_msg()` — match on EventMsg | **Máme: _handle_raw_event() — rozšířit** |
| Token tracking | Implicitní | `TokenUsage.reasoning_output_tokens` | **Přidat: reasoning token tracking** |
| Activity monitor | `useTurnActivityMonitor` — operation timer | `agent_turn_running` + `mcp_startup_status` | **Přidat: operation timer + activity state** |
| Background ops | `backgroundShells[]` + toggle/dismiss | `suppressed_exec_calls` HashSet | **Přidat: background activity API** |
| Status states | `StreamingState` (3 stavy) | `task_running` boolean | **Přidat: EngineState enum** |

---

## 16. Požadavky na CLI zobrazení — Testování a validace

Pro správné testování GUI integrace musí naše CLI umět zobrazit všechny eventy,
které budou GUI aplikace potřebovat. CLI slouží jako **referenční implementace**
a **testovací nástroj**.

### 16.1 Thinking zobrazení v CLI

**Aktuální stav:**
- REPL: `event.thought[:80]...` — jen s `--verbose`, šedá kurzíva
- Chat: `THINKING: {event.thought[:100]}...` — vždy, ale primitivní

**Požadovaný stav (inspirováno Gemini CLI + Codex):**

#### A) Spinner + thinking subject (jako Gemini CLI LoadingIndicator)

```
⠋ Analyzing code structure (12s)
⠙ Planning implementation approach (18s)
⠹ Reviewing solution (22s)
```

Implementace:
- Extrahovat `subject` z thinking textu pomocí **bold parser** (vzor z Gemini + Codex)
- Zobrazit jako spinner + subject + elapsed time
- Aktualizovat v reálném čase jak přicházejí thinking delta chunky
- Timer: `(esc to cancel, Xs)` pokud je cancellation podporovaný

#### B) Verbose mode — plný thinking text

```
💭 **Analyzing code structure**
   Looking at the file structure, I see three main modules...
   The authentication module needs refactoring because...
💭 **Planning implementation approach**
   I'll start with the database schema changes...
```

Implementace:
- `--verbose` nebo `--show-thinking` flag zobrazí plný thinking text
- Odlišení od response textu barvou (dim/italic) a prefixem (💭)
- Thinking bloky oddělené visuálně od response bloků

#### C) Thinking lifecycle signalizace

```
[THINKING START] block_id=abc123
⠋ Analyzing code structure...
[THINKING END] block_id=abc123, tokens=342, duration=4.2s
```

Jen v debug/verbose mode — ukazuje lifecycle events pro testování.

### 16.2 Paralelní operace zobrazení v CLI

**Aktuální stav:** Žádné — `ToolEvent` se zobrazí sekvenčně bez paralelního kontextu.

**Požadovaný stav (inspirováno Gemini CLI ToolGroupMessage + Codex active_cell):**

#### A) Tool group display

```
┌─ Tools ───────────────────────────────
│ ✓ Read: README.md (0.3s)
│ ⠋ Grep: searching for "auth" patterns
│ ⠋ Glob: finding *.py files
│ ⏳ Write: pending approval
└────────────────────────────────────────
```

Implementace:
- Grupovat paralelní tool calls do vizuálního border boxu
- Každý tool má ikonu stavu: ⏳ pending, ⠋ running, ✓ success, ✗ error, ⊘ cancelled
- Running tools mají spinner animaci
- Elapsed time pro dokončené tools

#### B) Activity tree (pro background agenty)

```
┌─ Main: "Analyzuj codebase" ────────────
│  ✓ Read README.md (0.3s)
│  ⠋ Task: "Research patterns" (agent-1)
│  │  ⠋ Grep: searching src/
│  │  ✓ Read: config.py
│  ⠋ Task: "Explore structure" (agent-2)
│  │  ⠋ Glob: finding files
│  ⏳ Synthesis (waiting for agents)
└────────────────────────────────────────
```

Implementace:
- `ActivityEvent.parent_activity_id` umožní vnořené zobrazení
- Background agenti se zobrazí jako podstrom
- Celkový progress: "2/5 completed"

#### C) Concurrent progress bar

```
[2/5] ████░░░░░░ 40% — Reading files, searching patterns
```

Pro inline mode (non-verbose): kompaktní progress bar.

### 16.3 Status states v CLI

**Požadovaný EngineState enum (inspirováno Gemini StreamingState):**

```
Idle          → "> " prompt (čeká na uživatele)
Thinking      → "⠋ thinking subject (Xs)" spinner
Responding    → "⠋ Generating..." spinner + streaming text
ToolExecuting → "┌─ Tools ─" border box se stavem nástrojů
WaitingApproval → "? Approve tool_name? [y/n]" approval prompt
Error         → "✗ Error: message" error display
```

CLI zobrazí odpovídající vizuál pro každý stav.

### 16.4 CLI implementační soubory

| Soubor | Změna |
|--------|-------|
| `avatar_engine/cli/commands/repl.py` | Spinner + thinking subject, tool group display, activity tree |
| `avatar_engine/cli/commands/chat.py` | Thinking display v non-interactive mode |
| `avatar_engine/cli/display.py` (NEW) | Shared CLI display components: spinner, tool group, progress bar |
| `avatar_engine/events.py` | EngineState enum |

---

## 17. Demo GUI aplikace — Testování a tutorial

### 17.1 Účel

Demo GUI aplikace slouží jako:
1. **Test** — ověření, že všechny eventy se správně propagují do GUI
2. **Tutorial** — ukázka, jak integrovat avatar-engine do reálné GUI aplikace
3. **Showcase** — vizuální demonstrace avatara s postavičkou, thinking, tools

### 17.2 Technologie

- **Python + Textual** (TUI framework) — jednoduché, žádné nativní závislosti
- Alternativně: **Python + PyQt6** nebo **Python + tkinter** pro desktop GUI
- Textual je preferovaný — běží v terminálu, easy to test, rich widgets

### 17.3 Layout

```
┌─────────────────────────────────────────────────────────┐
│  Avatar Engine Demo GUI                    [Claude ▼]   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────┐                                           │
│  │  (◕‿◕)   │  Ahoj! Jsem Aria, tvůj AI asistent.     │
│  │  Avatar   │  Jak ti mohu pomoci?                     │
│  │  [idle]   │                                           │
│  └──────────┘                                           │
│                                                         │
│  User: Analyzuj tento soubor                            │
│                                                         │
│  ┌──────────┐  💭 Analyzing code structure...           │
│  │  (°_°)   │                                           │
│  │  Avatar   │  ┌─ Tools ─────────────────────┐         │
│  │ [thinking]│  │ ⠋ Read: main.py             │         │
│  └──────────┘  │ ⠋ Grep: searching patterns   │         │
│                 └──────────────────────────────┘         │
│                                                         │
│  ┌──────────┐  Soubor main.py obsahuje 3 funkce:       │
│  │  (◕‿◕)   │  1. `process_data()` — zpracování dat   │
│  │  Avatar   │  2. `validate_input()` — validace       │
│  │ [talking] │  3. `main()` — entry point              │
│  └──────────┘                                           │
│                                                         │
├─────────────────────────────────────────────────────────┤
│ Status: idle | Model: claude | Cost: $0.02 | Tokens: 1.2k │
├─────────────────────────────────────────────────────────┤
│ > [Enter your message...]                               │
└─────────────────────────────────────────────────────────┘
```

### 17.4 Avatar stavy a animace

Avatar postavička vizuálně reflektuje stav engine:

| EngineState | Avatar | Popis |
|-------------|--------|-------|
| Idle | `(◕‿◕)` | Usmívá se, čeká |
| Thinking | `(°_°)` | Zamyšlený, thinking subject vedle |
| Thinking:analyzing | `(⊙_⊙)` | Zvědavý, lupa animace |
| Thinking:planning | `(ᐛ)` | Plánuje, tabule animace |
| Thinking:coding | `(⌐■_■)` | Cool, kóduje |
| Responding | `(◕‿◕)💬` | Mluví, bublina |
| ToolExecuting | `(◕‿◕)🔧` | Pracuje s nástroji |
| WaitingApproval | `(°_°)?` | Ptá se, otazník |
| Error | `(×_×)` | Chyba, křížky |

### 17.5 Vizuální animace a efekty

Demo GUI musí být vizuálně atraktivní — ne jen funkční. Textual framework
podporuje všechny potřebné efekty přes CSS engine, timery a Rich rendering.

#### A) Streaming text cursor

Během streamování odpovědi se na konci textu zobrazuje blikající cursor:

```
Soubor main.py obsahuje 3 funkce:▌
                                  ↑ bliká 500ms interval
```

Implementace:
```python
class StreamingCursor(Static):
    """Blikající cursor na konci streamovaného textu."""
    visible = reactive(True)

    def on_mount(self):
        self.blink_timer = self.set_interval(0.5, self.toggle_cursor)

    def toggle_cursor(self):
        self.visible = not self.visible

    def render(self):
        return "▌" if self.visible else " "
```

Cursor zmizí po `TextEvent(is_complete=True)`.

#### B) Thinking shimmer efekt (vzor z Codex shimmer.rs)

Status text během thinking má shimmer animaci — gradient sweep zleva doprava:

```
⠋ ░░▒▓█ Analyzing code structure █▓▒░░  (12s)
      ↑ gradient sweep, 1.5s cyklus
```

Implementace:
```python
class ShimmerText(Static):
    """Shimmer animation pro thinking status (vzor z Codex)."""
    phase = reactive(0.0)

    def on_mount(self):
        self.set_interval(1/30, self.advance_phase)  # 30 FPS

    def advance_phase(self):
        self.phase = (self.phase + 0.05) % 1.0

    def render(self):
        text = self.status_text
        styled = Text()
        for i, char in enumerate(text):
            # Cosine wave sweep — barva se mění podle pozice + fáze
            t = (i / max(len(text), 1) + self.phase) % 1.0
            brightness = 0.4 + 0.6 * (0.5 + 0.5 * math.cos(2 * math.pi * t))
            r, g, b = int(120 * brightness), int(180 * brightness), int(255 * brightness)
            styled.append(char, style=Style(color=Color.from_rgb(r, g, b)))
        return styled
```

#### C) Avatar přechody — plynulé přepínání stavů

Avatar nemění obličej skokem — fade-out starý → fade-in nový:

```
Frame 1: (◕‿◕)     ← idle, plná opacity
Frame 2: (◕‿◕)     ← dim (fade out)
Frame 3: (·_·)      ← transition frame
Frame 4: (°_°)      ← dim (fade in)
Frame 5: (°_°)      ← thinking, plná opacity
```

Implementace: 5-frame transition přes `set_interval(0.08)`, Rich Style dimming.

#### D) Typing indikátor — "..." bublina

Před prvním tokenem odpovědi (po odeslání promptu):

```
┌──────────┐
│  (°_°)   │  ·  · ·
│  Avatar   │   ↑ animované tečky
│ [loading] │
└──────────┘
```

3 tečky s postupným fade-in (0→1→2→3 tečky, cyklus 800ms).

#### E) Tool status animace

```
│ ⠋ Read: main.py             │  ← spinner se otáčí (⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏)
│ ✓ Read: main.py (0.3s)      │  ← check-mark flash (zelená → normální)
│ ✗ Write: permission denied   │  ← cross flash (červená → normální)
```

Při přechodu z running → success: krátký zelený flash (200ms) na celém řádku.
Při přechodu z running → error: krátký červený flash (200ms).

#### F) Syntax highlighting v odpovědích

Kódové bloky v markdown odpovědích mají plný syntax highlighting:

```python
# Rich + Textual toto podporují nativně:
from rich.syntax import Syntax
from rich.markdown import Markdown

# Markdown rendering s theme:
md = Markdown(response_text, code_theme="monokai")
```

#### G) Toast notifikace

Pro diagnostiku, budget warning, session events:

```
┌─────────────────────────────────────┐
│                         ┌─────────┐ │
│                         │ ⚠ Budget │ │
│                         │ 80% used│ │
│  (chat content)         └─────────┘ │
│                                     │
└─────────────────────────────────────┘
```

Textual má built-in `self.notify()` metodu pro toast notifikace.

#### H) Activity tree živá aktualizace

Strom operací se rozbaluje/sbaluje plynule s animací:

```
▼ Main: "Analyzuj codebase"         ← kliknutí sbalí/rozbalí
  ✓ Read README.md (0.3s)
  ▼ Task: "Research patterns"        ← automaticky rozbalený dokud běží
    ⠋ Grep: searching src/
    ✓ Read: config.py
  ► Task: "Explore structure"        ← sbalený, kliknutí rozbalí
```

Textual `Tree` widget podporuje expand/collapse s animací nativně.

### 17.6 Vizuální parita CLI ↔ GUI

Každá funkce má CLI i GUI variantu — duální implementace:

| Feature | CLI (terminál) | GUI (Textual) |
|---------|---------------|---------------|
| Thinking status | `⠋ subject (Xs)` plain text spinner | Shimmer text + avatar animace |
| Streaming text | Postupný tisk na stdout | Streaming + blikající cursor `▌` |
| Tool progress | `⠋`/`✓`/`✗` unicode ikony | Spinner + flash animace + progress bar |
| Activity tree | Box-drawing characters `┌│└` | Expandable Tree widget |
| Budget warning | `⚠ Budget: 80%` print | Toast notifikace s countdown |
| Error display | `✗ Error: msg` červeně | Error panel + avatar `(×_×)` stav |
| Thinking verbose | `💭 text` dim/italic | Dedicated thinking sidebar panel |
| Code blocks | Plain text (no highlighting) | Rich syntax highlighting (Monokai) |
| Parallel ops | `┌│└` tree + counter text | Interactive tree + cancel buttons + collapsed mode |
| Background tasks | Inline status text | Live output snippet + toast on completion |
| User interrupt | N/A (stdin blocked) | Always-active input + interrupt dialog |
| Stall detect | Timeout warning text | Yellow/orange warning badge + timer |
| Multi-agent | Numbered agent labels | Color-coded agent indicators + split output |

### 17.7 Panely demo GUI

#### A) Chat panel (hlavní)
- Historie konverzace s avatar ikonami
- Streaming text s cursor blikáním
- Thinking bloky vizuálně oddělené (šedá/italic)

#### B) Thinking panel (sidebar)
- Real-time thinking stream (pokud je verbose)
- Thinking phase indikátor s ikonou
- Token count pro thinking

#### C) Activity panel — Řízení paralelních procesů (sidebar)

Toto je **klíčový panel** celého GUI. Moderní modely (Opus 4.6, Gemini 3)
rutinně spouštějí 5-10+ paralelních operací. VSCode s tímhle selhává —
ukazuje jen "Claude is thinking..." bez detailů o paralelních agentech.
Náš GUI to musí řešit lépe.

**Problém VSCode:** Když Claude spustí 3 Task agenty + 2 Bash na pozadí,
VSCode ukáže jen spinner a text posledního eventu. Uživatel nevidí, že
běží 5 věcí najednou, nemůže cancel jednu z nich, nevidí progress.

**Naše řešení — Activity panel s plnou kontrolou:**

```
┌─ Activity ──────────────────────────┐
│                                      │
│ ⠋ Main turn (45s)            [⏸][✗] │
│ ├─ ✓ Read README.md (0.3s)          │
│ ├─ ⠋ Task: "Research" (agent-1)     │
│ │   ├─ ⠋ Grep: src/**/*.py          │
│ │   ├─ ✓ Read: config.py (0.2s)     │
│ │   └─ ⏳ Read: utils.py            │
│ ├─ ⠋ Task: "Explore" (agent-2)      │
│ │   └─ ⠋ Glob: finding files        │
│ ├─ ⠋ Bash (bg): npm test     [✗]   │
│ │   └─ ░░▓▓▓▓░░ stdout: "42 pass"  │
│ └─ ⏳ Synthesis (waiting)            │
│                                      │
│ ─── Summary ───────────────────────  │
│ Running: 4  Completed: 2  Pending: 1│
│ [Cancel All] [Pause] [Details ▼]    │
└──────────────────────────────────────┘
```

**Detailní chování:**

**1. Hierarchické zobrazení (Activity Tree)**
- Každý `ActivityEvent` s `parent_activity_id` se vnořuje pod rodiče
- Kořen = main turn, children = tool calls a sub-agenty
- Automatický expand: running uzly jsou rozbalené, completed se sbalí po 2s
- Kliknutí na uzel → detail panel s plným výstupem

**2. Agregovaný progress counter**
- `Running: 4  Completed: 2  Pending: 1` — vždy viditelný
- Kompaktní summary i když je strom sbalený
- Barvy: zelená=completed, modrá=running, šedá=pending, červená=failed

**3. Cancel per-operace**
- Každý running uzel má `[✗]` cancel button
- Cancel pošle `engine.cancel_activity(activity_id)`
- Cancelled uzel → `⊘` ikona + dim text + "(cancelled)" label
- "Cancel All" → zastaví celý turn

**4. Background process output**
- Bash s `run_in_background=true` ukazuje live output snippet
- Poslední řádek stdout se zobrazuje inline (truncated)
- Kliknutí → full output v popup overlay
- Notifikace toast když background task dokončí

**5. Status prioritizace (vzor z Codex chatwidget.rs:1255-1258)**
```
Priority řazení pro status header:
1. Exec waiting (příkaz běží) — nejvyšší
2. Tool approval waiting — potřebuje interakci
3. Reasoning/thinking header — co AI přemýšlí
4. "Working" fallback — generický stav
```
GUI status bar ukazuje vždy **nejdůležitější** stav, ne poslední event.

**6. Detekce "uvíznutí" (stalled operations)**
- Pokud operace neemituje event > 30s → žlutý warning indikátor ⚠
- Po 60s → orange "Possible stall: tool_name running for 60s"
- Uživatel může cancel nebo počkat

**7. Notifikace pro background dokončení**
- Background agent dokončí → toast: "✓ Task 'Research' completed (12 results)"
- Background Bash error → toast: "✗ npm test failed (exit code 1)"
- Toasty jsou klikatelné → otevřou detail

**8. Interakce během paralelních operací**
- Input box je **vždy aktivní** — uživatel může psát i když AI pracuje
- Odeslání nové zprávy → interrupt dialog: "AI is working. Send anyway?"
- Možnosti: "Send & interrupt", "Send after current turn", "Cancel"
- Toto řeší problém, který VSCode nemá — uživatel musí čekat

**9. Multi-agent vizualizace**
Když model spustí 3+ Task agenty:

```
┌─ Agents ─────────────────────┐
│ 🤖 agent-1: "Research"  ⠋   │ ← vlastní barva
│ 🤖 agent-2: "Explore"   ⠋   │ ← vlastní barva
│ 🤖 agent-3: "Analyze"   ⏳   │ ← čeká na slot
│                               │
│ Agent output:                 │
│ ┌─ agent-1 ────────────────┐ │
│ │ Found 3 matching files:  │ │
│ │ • src/auth.py             │ │
│ │ • src/users.py            │ │
│ └──────────────────────────┘ │
└───────────────────────────────┘
```

Každý agent má vlastní barevný indikátor. Output agentů se streamuje
do společného nebo odděleného panelu (přepínatelné).

**10. Collapsed mode pro mnoho operací**

Když běží 10+ operací, strom by zabral celou obrazovku.
Automatický collapsed mode:

```
┌─ Activity (12 ops) ─────────┐
│ ⠋ 5 running │ ✓ 4 done │ ⏳ 3 pending │
│ [Expand] [Cancel All]       │
└──────────────────────────────┘
```

Expand přepne na plný strom. Auto-expand se vrátí když < 5 operací.

#### D) Status bar (bottom)
- Provider + model
- Cost tracking
- Token usage (input/output/reasoning)
- Session ID
- EngineState

#### E) Capabilities panel (debug)
- ProviderCapabilities zobrazení
- Feature matrix: co provider podporuje
- Diagnostické zprávy (DiagnosticEvent)

### 17.8 Event handling v demo GUI

```python
# examples/demo_gui.py

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Input, RichLog
from avatar_engine import AvatarEngine, ThinkingEvent, TextEvent, ToolEvent, ActivityEvent

class AvatarDemoApp(App):
    """Demo GUI pro avatar-engine — testování a tutorial."""

    async def on_mount(self):
        self.engine = AvatarEngine(provider="claude")

        # Registrace event handlerů
        self.engine.on(ThinkingEvent, self.on_thinking)
        self.engine.on(TextEvent, self.on_text)
        self.engine.on(ToolEvent, self.on_tool)
        self.engine.on(ActivityEvent, self.on_activity)

        await self.engine.start()

    async def on_thinking(self, event: ThinkingEvent):
        """Update avatar state + thinking panel."""
        self.avatar.set_state("thinking", phase=event.phase)
        self.thinking_panel.write(f"💭 {event.thought}")

        if event.is_complete:
            # Thinking block finished — update avatar
            self.avatar.set_state("responding")

    async def on_text(self, event: TextEvent):
        """Stream response text to chat panel."""
        self.chat_panel.write(event.text)
        self.avatar.set_state("talking")

        if event.is_complete:
            self.avatar.set_state("idle")

    async def on_tool(self, event: ToolEvent):
        """Update tool group display."""
        self.activity_panel.update_tool(event)
        self.avatar.set_state("tool_executing")

    async def on_activity(self, event: ActivityEvent):
        """Update activity tree."""
        self.activity_panel.update_activity(event)
```

### 17.9 Demo GUI implementační soubory

| Soubor | Popis |
|--------|-------|
| `examples/demo_gui.py` (NEW) | Hlavní Textual aplikace |
| `examples/demo_gui_avatar.py` (NEW) | Avatar widget — ASCII art stavová postavička |
| `examples/demo_gui_panels.py` (NEW) | Chat, thinking, activity, status panely |
| `examples/demo_gui_config.yaml` (NEW) | Ukázková konfigurace pro demo |
| `requirements-demo.txt` (NEW) | `textual>=0.50`, `avatar-engine` |

### 17.10 Testovací scénáře pro demo GUI

| Scénář | Co testuje | Očekávaný výsledek |
|--------|-----------|-------------------|
| Simple chat | TextEvent streaming | Avatar: idle → talking → idle, text se streamuje |
| Thinking model | ThinkingEvent lifecycle | Avatar: idle → thinking (s fází) → talking → idle |
| Parallel tools | ActivityEvent + ToolEvent | Tool group box s multiple running tools |
| Background agent | ActivityEvent s parent_id | Vnořený activity tree |
| Cancel operation | Interrupt API | Tools se cancelled, avatar → idle |
| Provider switch | ProviderCapabilities | UI se adaptuje (thinking panel visible/hidden) |
| Error handling | ErrorEvent | Avatar → error state, error message |
| Session resume | SessionInfo | Chat history se načte |
| Cost tracking | Budget enforcement | Status bar ukazuje cost, warning při limitu |
| System prompt | Provider consistency | Avatar se chová stejně u všech providerů |
| Heavy parallel | 10+ concurrent ops | Collapsed mode, progress counter, no freeze |
| User interrupt | Input during AI work | Interrupt dialog, send after turn option |
| Background complete | Bg task finishes | Toast notification, tree update |
| Stalled operation | Tool hangs 60s+ | Warning indicator, cancel option |
| Multi-agent | 3+ Task agents | Color-coded agents, separate output streams |

---

## 18. Aktualizovaný implementační plán

### Fáze 0: Předpoklady
```
Prostudovat referenční projekty ✓ (tato sekce)
```

### Fáze 1: Thread Safety (základ pro vše)
```
RC-2 → RC-1 → RC-7 → RC-3/4 → RC-5/6 → RC-8..13
```

### Fáze 2: ThinkingEvent + Thinking Display
```
ThinkingPhase enum → bold parser (vzor z Gemini+Codex) →
ThinkingEvent rozšíření → thinking filtr oneshot →
klasifikátor → syntetický thinking pro Claude →
CLI spinner + subject display → testy
```
Reference: `gemini-cli/packages/core/src/utils/thoughtUtils.ts`,
`codex/codex-rs/tui/src/chatwidget.rs:1249-1288`

### Fáze 3: Paralelní operace
```
EngineState enum → ActivityEvent → ActivityTracker →
stdin lock → tool group display (vzor ToolGroupMessage) →
background activity API → interrupt/cancel API → testy
```
Reference: `gemini-cli/packages/cli/src/ui/hooks/useToolExecutionScheduler.ts`,
`gemini-cli/packages/cli/src/ui/components/messages/ToolGroupMessage.tsx`

### Fáze 4: CLI Display Layer
```
cli/display.py (spinner, tool group, progress) →
repl.py integration → chat.py integration → testy
```

### Fáze 5: System Prompt + Budget
```
Codex system prompt → Gemini oneshot fix →
pre-request budget check → cost estimation → testy
```

### Fáze 6: Diagnostics + Capabilities
```
DiagnosticEvent → stderr surfacing → ProviderCapabilities →
ToolPolicy → testy
```

### Fáze 7: Demo GUI
```
Avatar widget → Chat panel → Thinking panel →
Activity panel → Status bar → integration testy →
dokumentace
```
Reference: `codex/codex-rs/tui/src/shimmer.rs` (shimmer animace),
`gemini-cli/packages/cli/src/ui/components/LoadingIndicator.tsx`

---

## 19. Souhrnná tabulka všech dotčených souborů (aktualizováno)

| Soubor | GAP-1 | GAP-2 | GAP-3 | GAP-4 | GAP-5 | GAP-6 | GAP-7 | GAP-8 | GAP-9 | CLI | GUI |
|--------|-------|-------|-------|-------|-------|-------|-------|-------|-------|-----|-----|
| `events.py` | X | X | | X | | | X | | | | |
| `engine.py` | X | X | | X | | X | X | X | X | | |
| `bridges/base.py` | | X | X | X | X | X | X | | X | | |
| `bridges/gemini.py` | X | X | | X | X | X | | | X | | |
| `bridges/codex.py` | X | | | | X | X | | | X | | |
| `bridges/claude.py` | X | X | | | | | | | X | | |
| `types.py` | X | X | | | X | | | X | X | | |
| `utils/rate_limit.py` | | | | X | | | | | | | |
| `config.py` | | | | | | | | X | | | |
| `cli/display.py` (NEW) | | | | | | | | | | X | |
| `cli/commands/repl.py` | | | | | | | | | | X | |
| `cli/commands/chat.py` | | | | | | | | | | X | |
| `examples/demo_gui.py` (NEW) | | | | | | | | | | | X |
| `examples/demo_gui_avatar.py` (NEW) | | | | | | | | | | | X |
| `examples/demo_gui_panels.py` (NEW) | | | | | | | | | | | X |
| `examples/gui_integration.py` | X | X | | | | | | | | | X |

---

## 20. Rizika a omezení (aktualizováno)

| Riziko | Dopad | Mitigace |
|--------|-------|----------|
| ACP SDK nemá thread-safe callbacks | RC-3/4 nelze plně opravit | `asyncio.Lock` + dokumentace |
| Claude CLI neexportuje thinking | GAP-1 syntetický thinking je jen heuristika | Dokumentovat limitaci |
| Claude Code nemá zdrojový kód | Nemůžeme studovat jeho implementaci | Použít Gemini + Codex vzory |
| Codex ACP nemá instruction field | GAP-5 system prompt je jen prepend | Prověřit ACP spec |
| Paralelní tool_use není v ACP spec | GAP-2 activity tracking jen z raw events | Best-effort tracking |
| Budget estimation pro Gemini/Codex je přibližný | GAP-6 cost tracking není přesný | Konzervativní odhady |
| `threading.Lock` v EventEmitter může zpomalit | GAP-4 performance overhead | Benchmark, zvážit RLock |
| Textual pro demo GUI limituje vizuální možnosti | GUI demo není plný desktop app | Je to proof-of-concept |
| Bold marker pattern nemusí fungovat pro všechny modely | Thinking subject extrakce selže | Fallback na celý text |

---

## 21. Kritéria úspěchu (aktualizováno)

### Must-have pro GUI avatar

- [ ] ThinkingEvent má `phase`, `is_start`, `is_complete`, `block_id`
- [ ] Bold parser extrahuje thinking subject (vzor z Gemini + Codex)
- [ ] GUI může rozlišit typ myšlení (analyzing, planning, coding, ...)
- [ ] Paralelní tool_use je viditelný jako ActivityEvent
- [ ] GUI může zobrazit strom aktivních operací
- [ ] Thinking content NEPROSAKUJE do text response (žádný provider)
- [ ] EventEmitter je thread-safe
- [ ] System prompt funguje u všech 3 providerů
- [ ] Budget check PŘED odesláním promptu

### Must-have pro CLI

- [ ] CLI zobrazuje thinking subject jako spinner + text + timer
- [ ] CLI zobrazuje paralelní tools v tool group border boxu
- [ ] CLI má EngineState-based status display
- [ ] `--verbose` mode ukazuje plný thinking text

### Must-have pro Demo GUI

- [ ] Demo GUI s avatar postavičkou reagující na stavy
- [ ] Plynulé přechody mezi avatar stavy (fade-in/fade-out)
- [ ] Streaming text cursor `▌` blikající během response
- [ ] Thinking shimmer efekt na status textu (vzor z Codex)
- [ ] Thinking panel s real-time thinking stream
- [ ] Activity panel s hierarchickým stromem paralelních operací
- [ ] Cancel per-operace + Cancel All
- [ ] Agregovaný progress counter (running/completed/pending)
- [ ] Background task output snippet + toast notifikace při dokončení
- [ ] Stall detection (warning po 30s inaktivity operace)
- [ ] Input vždy aktivní — uživatel může psát během AI práce
- [ ] Collapsed mode pro 10+ operací
- [ ] Multi-agent vizualizace s barevným rozlišením
- [ ] Tool status animace (spinner → flash → ikona)
- [ ] Syntax highlighting v code blocks (Rich/Monokai)
- [ ] Toast notifikace pro diagnostiku a budget warnings
- [ ] Status bar s provider info, cost, tokens
- [ ] Typing indikátor ("..." bublina) před prvním tokenem
- [ ] Vizuální parita s CLI (každá CLI funkce má GUI ekvivalent)
- [ ] Funguje se všemi 3 providery

### Nice-to-have

- [ ] Interrupt/Cancel API pro GUI
- [ ] DiagnosticEvent pro stderr
- [ ] ProviderCapabilities pro adaptivní GUI
- [ ] ToolPolicy pro granulární permissions
- [ ] Shimmer animace pro thinking (vzor z Codex)
- [ ] Reasoning token tracking (vzor z Codex)

---

> **POZNÁMKA:** Tento plán navazuje na PLAN.md (DONE), SESSION_MANAGEMENT_PLAN.md (DONE),
> CODEX_INTEGRATION_PLAN.md (DONE), a CLI_PLAN.md. Implementuje se na větvi `gui-readiness`
> nebo přímo na `cli-plan`.
>
> **Reference projekty:**
> - Gemini CLI: `/home/box/git/github/gemini-cli/` — TypeScript, Ink/React TUI
> - Codex: `/home/box/git/github/codex/` — Rust, ratatui TUI
> - Claude Code: `/home/box/git/github/claude-code/` — kompilovaný, bez zdrojového kódu
