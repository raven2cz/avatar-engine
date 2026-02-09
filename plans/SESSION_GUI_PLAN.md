# Plán: Session Modal pro Web GUI + Provider Resume + History Display

> Status: DONE (2026-02-09)
> Vytvořeno: 2026-02-09
> Závisí na: SESSION_MANAGEMENT_PLAN.md (Fáze 15 — filesystem stores)

## Kontext

Session listing z filesystému funguje (Fáze 15 hotová). Ale:

1. **Gemini resume nefunguje** — ACP `load_session` vrací -32601. `session_manager.resume_session()` restartuje engine s `resume_session_id`, ale `_create_or_resume_acp_session` zkusí ACP load (selže) a vytvoří NOVOU session — historie ztracena.
2. **Codex resume nezobrazuje historii** — ACP `load_session` funguje (session se obnoví na straně serveru), ale bridge's `self.history` je prázdný — frontend nevidí starší zprávy.
3. **SessionPanel je příliš malý** — 320px floating panel, utopené titulky, žádný kontext projektu.
4. **Frontend nezná `cwd`** — WebSocket `connected` zpráva neobsahuje working directory, modal nemůže zobrazit název projektu.

## Část 1: Gemini Resume přes historii z filesystému

Když `resume_session_id` je nastaveno ale ACP `load_session` selže, načteme historii konverzace z JSON souboru a injektujeme ji jako kontext do prvního ACP promptu.

### 1.1 `GeminiFileSessionStore.load_session_messages()` + `_find_session_file()`

**Soubor:** `avatar_engine/sessions/_gemini.py`

Klíčový problém: Gemini CLI pojmenovává soubory `session-{timestamp}-{shortId}.json`
(např. `session-2026-02-09T05-53-fa4de119.json`), ale plné UUID (`fa4de119-4771-481b-908f-dd15fde55a86`)
je pouze uvnitř JSON jako `sessionId`.

```python
def _find_session_file(self, session_id: str, working_dir: str) -> Optional[Path]:
    """Glob by short-ID suffix first (fast), then verify sessionId inside."""

def load_session_messages(self, session_id: str, working_dir: str) -> List[Message]:
    """Uses _find_session_file, parses type: user/gemini → role: user/assistant."""
```

### 1.2 GeminiBridge: načtení historie po neúspěšném ACP resume

**Soubor:** `avatar_engine/bridges/gemini.py`

V `_start_acp()` po `_create_or_resume_acp_session`: pokud `resume_session_id` bylo nastaveno ale ACP resume selhal (nová session vytvořena místo load), načteme historii z filesystému.

### 1.3 GeminiBridge: injekce historie do prvního promptu

Override `_prepend_system_prompt()` — když `_fs_resume_pending` je True, přidá konverzační historii jako kontext.

### 1.4 Nastavení `can_load` capabilities

V `_start_acp()` POZOR: `can_load = True` se musí nastavit AŽ PO `_create_or_resume_acp_session()`,
protože jinak by se pokusil ACP `load_session` (timeout na Gemini CLI s -32601).

## Část 2: Codex Filesystem Session Store

**Soubor:** `avatar_engine/sessions/_codex.py` (NOVÝ)

Codex CLI ukládá sessions v `~/.codex/sessions/YYYY/MM/DD/rollout-{timestamp}-{sessionId}.jsonl`.
Formát: JSONL eventy — `session_meta` (ID, cwd), `response_item` (role + content).

ACP `load_session` funguje (Codex obnoví kontext na serveru), ale bridge nemá historii.
Řešení: REST endpoint čte historii z filesystému a frontend ji zobrazí.

Filtrování systémového obsahu: developer role, reasoning typ, `<permissions>`, `# AGENTS.md`,
`<environment_context>` — vše přeskočeno.

## Část 3: Backend — REST endpoint pro session messages + `cwd`

**Soubor:** `avatar_engine/web/server.py`

- `GET /api/avatar/sessions/{session_id}/messages` — REST endpoint pro načtení historie z filesystému
- `cwd` + `session_title` přidáno do `connected` WS zprávy (2 místa)
- `_get_session_title()` helper — čte titulek z filesystem store

## Část 4: Frontend — SessionPanel centrovaný modal + history display

### SessionPanel — centrovaný modal s backdrop

- Z-index `z-[60]`/`z-[70]` — vykresleno MIMO `<header>` (sticky + backdrop-filter vytváří stacking context)
- Async loading sessions při otevření (ne při startu)
- Tabulkový layout: Title | Session ID | Updated
- Klik na řádek obnoví session + zavře modal
- Escape zavře modal

### History loading při resume

`useAvatarChat.ts` → `resumeSession()`:
- Pošle WS `resume_session` zprávu
- Okamžitě fetchne `GET /api/avatar/sessions/{id}/messages`
- Zobrazí historické zprávy jako `history-{i}` ID zprávy

### Session button v StatusBar

- History ikona + session title (font-medium) nebo zkrácené ID (mono)
- Viditelné pro všechny providery

## Část 5: Codex capabilities

**Soubor:** `avatar_engine/bridges/codex.py`

Přidáno `can_list_sessions = True` / `can_load_session = True` na `_provider_capabilities`
po `_store_acp_capabilities()`. Bez toho frontend zobrazoval "Session listing not supported".

## Změny souborů

| # | Soubor | Změna | Status |
|---|--------|-------|--------|
| 1 | `avatar_engine/sessions/_gemini.py` | `_find_session_file()` + `load_session_messages()` | DONE |
| 2 | `avatar_engine/sessions/_codex.py` | **NOVÝ** — CodexFileSessionStore | DONE |
| 3 | `avatar_engine/sessions/_base.py` | `load_session_messages()` default | DONE |
| 4 | `avatar_engine/sessions/__init__.py` | Factory vrací CodexFileSessionStore | DONE |
| 5 | `avatar_engine/bridges/gemini.py` | Filesystem resume, injekce kontextu, `can_load=True` AFTER session | DONE |
| 6 | `avatar_engine/bridges/codex.py` | `can_list_sessions=True`, `can_load_session=True` | DONE |
| 7 | `avatar_engine/bridges/claude.py` | `list_sessions()`, `can_list=True`, `can_load_session=True` | DONE |
| 8 | `avatar_engine/web/server.py` | REST endpoint messages, `cwd`, `session_title` v connected | DONE |
| 9 | `examples/web-demo/src/components/SessionPanel.tsx` | Centrovaný modal, async loading | DONE |
| 10 | `examples/web-demo/src/components/StatusBar.tsx` | Overlays mimo header, session title button | DONE |
| 11 | `examples/web-demo/src/hooks/useAvatarWebSocket.ts` | `cwd`, `sessionTitle` | DONE |
| 12 | `examples/web-demo/src/hooks/useAvatarChat.ts` | `resumeSession` s REST fetch historie | DONE |
| 13 | `examples/web-demo/src/api/types.ts` | `cwd`, `session_title` v ConnectedMessage | DONE |
| 14 | `examples/web-demo/src/App.tsx` | `sessionTitle`, `cwd` prop passing | DONE |
| 15 | `tests/test_session_stores.py` | 47 testů — Gemini, Claude, Codex stores | DONE |

## Opravené bugy

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| Gemini history nezobrazena | Soubory pojmenovány `session-{timestamp}-{shortId}.json`, kód hledal `session-{fullUuid}.json` | `_find_session_file()` s glob-based vyhledáváním |
| Modal oříznutý | `<header sticky z-50 glass>` vytváří stacking context, `fixed` children oříznuty | Overlays vykresleny mimo `<header>` |
| Codex "not supported" | `_provider_capabilities.can_list_sessions` nebylo nastaveno | Přidáno po `_store_acp_capabilities()` |
| History race condition | Fetch při `connected` eventu — Gemini restartuje pomalu | Fetch okamžitě v `resumeSession()` |
| Gemini startup timeout | `can_load=True` před `_create_or_resume_acp_session` → ACP timeout | Přesunuto za session creation |

## Výsledky

- 156 testů PASS (test_session_stores + test_session + test_cli)
- Gemini: session listing + resume s historií funguje
- Claude: session listing + resume s historií funguje
- Codex: session listing + resume s historií funguje
- Web GUI: modal, session title, cwd — vše funkční
