# CLI Display Fix v2 — Robustni event pipeline pro CLI i Web GUI

> Created: 2026-02-07
> Rewritten: 2026-02-08
> Status: DONE (2026-02-08)
> Branch: cli-plan

---

## Problem

Codexuv rewrite pridal prompt_toolkit + patch_stdout + _quiet_repl_logs, cimz:
1. Rozbil ANSI barvy (patch_stdout mangles Rich escape codes)
2. Skryl startup logy (bridge info, provider, model)
3. Tise spolkl ACP chyby (_stream_acp error handling)
4. Pridal zbytecnou slozitost (prompt_toolkit neni potreba)

Navic existuji pre-existing bugy:
- _stream_acp() tise spolkne RequestError — uzivatel nevidi chybu
- _extract_text_from_update() nefiltruje thinking bloky -> thinking v outputu
- Gemini bridge nikdy neposle is_complete=True pro thinking eventy

## Cil

Cisty event pipeline znovupouzitelny pro Web GUI:

    Bridge -> Engine._process_event() -> EventEmitter
                                          +-- CLI: DisplayManager (spinner + text)
                                          +-- Web: WebSocket -> React

Vizualni vystup:

    $ avatar repl

    Starting Gemini bridge (ACP enabled: True)
    ACP authenticated via: oauth-personal

    Avatar Engine REPL (gemini)

    You: Analyzuj tento projekt

    * Analyzing (3s)
    * Understanding the project structure (5s)
      * read_file: src/main.py
      v read_file (0.3s)
    * Planning improvements (8s)

    Assistant:
    Projekt ma standardni Python strukturu...

Spinner zmizi, objevi se Assistant: a pod nim JEN finalni odpoved.
Zadny thinking text, zadne reasoning bloky.

---

## 5 implementacnich kroku

### Krok 1: Fix _stream_acp() error handling (gemini.py)

Problem: Kdyz ACP prompt() vyhodi RequestError, _run_prompt() ji zachyti
ve finally a posle None sentinel. Hlavni loop breakne, prazdna odpoved,
chyba ztracena. Uzivatel nevidi nic.

Oprava: Po while loopu zkontrolovat task.exception() a propagovat chybu.
Pridat fallback na oneshot jako ma _send_acp().

### Krok 2: is_complete tracking pro Gemini thinking (gemini.py)

Problem: Gemini bridge emituje thinking eventy bez is_complete=True.
DisplayManager._on_thinking() nikdy nezavola thinking.stop() pres eventy.

Oprava: Pridat _was_thinking flag. Kdyz prijde text PO thinking,
emitovat {type: thinking, is_complete: True}.

### Krok 3: Odstranit _quiet_repl_logs() (repl.py)

Problem: Codex pridal funkci, ktera nastavuje bridge loggery na WARNING.
Skryje 12+ dulezitych startup zprav (provider, model, ACP auth...).

Oprava: Smazat funkci a jeji pouziti. Startup logy budou opet viditelne.

### Krok 4: Zjednodusit REPL (repl.py)

Problem: prompt_toolkit + patch_stdout pridava slozitost a bugs.
patch_stdout mangles ANSI, prompt_toolkit neni nutny.

Oprava: Zpet na asyncio run_in_executor + console.input() pro vstup.
Zachovat async spinner task pattern (funguje). Odstranit prompt_toolkit,
patch_stdout, sys.__stdout__ hack. Psat primo na console.

### Krok 5: Thinking text filtrace (gemini.py) — HOTOVO

Problem: _extract_text_from_update() nevynechavala thinking bloky.

Oprava: Pridana _is_thinking_block() helper, filtrace v obou extraction
funkcich. 13 novych testu, vsechny prochazi.

---

## Co zachovat (funguje)

- Event system: ThinkingEvent, ThinkingPhase, extract_bold_subject, classify_thinking
- Engine._process_event() — konverze raw eventu na typed eventy
- DisplayManager event handler pattern (_on_thinking, _on_tool, _on_error)
- ThinkingDisplay + ToolGroupDisplay data modely
- advance_spinner() + _write_status_rich() + clear_status() pattern
- on_response_start() / on_response_end() lifecycle

## Co odstranit

- prompt_toolkit import a pouziti
- patch_stdout()
- _quiet_repl_logs()
- sys.__stdout__ hack (nebude potreba bez patch_stdout)

## Co pridat

- Error propagace v _stream_acp()
- _was_thinking flag + is_complete emission v Gemini bridge
- asyncio run_in_executor pro neblokujici input
- Codex bridge: stejna _is_thinking_block() filtrace

---

## Testovaci strategie

### Unit testy
- _stream_acp error propagace (mock ACP connection)
- is_complete emission kdyz text nasleduje po thinking
- _is_thinking_block filtrace (13 testu — HOTOVO)
- Provider switch clears model (2 testy — HOTOVO)

### Integracni testy
- Real Gemini: thinking spinner + response text
- Real Claude: spinner + response
- Error scenario: ACP failure zobrazena uzivateli

### Manualni testy
    avatar repl              # Gemini (default)
    avatar -p claude repl    # Claude
    avatar -p codex repl     # Codex

---

## Acceptance Criteria

1. Startup logy viditelne (provider, model, ACP auth)
2. Spinner animuje jednoradkove behem thinking
3. Thinking text NIKDY v response outputu
4. Chyby z ACP zobrazeny uzivateli (ne tise spolknute)
5. Cisty exit bez chybovych hlasek
6. Vsechny providery funguji
7. Vsechny testy prochazi
8. Zadny prompt_toolkit v repl.py

---

## Appendix: ACP Stabilization (2026-02-08)

Po updatu gemini-cli na novou verzi se objevily dalsi problemy:

### Opravene bugy

1. **Gemini ACP "Internal error"** — tri root causes:
   - `spawn_agent_process` → `connect_to_agent` (oficialní SDK API)
   - Chybejici `ClientCapabilities(fs=..., terminal=True)` v `initialize()`
   - Spatny format `request_permission` odpovedi (raw dict → typed Pydantic)
   - `previewFeatures` odstranen z gemini-cli, nenastavujeme v settings
   - ACP mode nepise settings.json vubec (nechava gemini-cli defaults)
   - Detaily viz `plans/acp-bug-analysis.md`

2. **Codex thinking leak** — reasoning text unikal do odpovedi:
   - Skip text extraction kdyz thinking je v tom samem updatu
   - `_was_thinking` flag + `is_complete` emission pri thinking→text prechodu

3. **Cursor blinking** — spinner animace zpusobovala problikavani kurzoru:
   - `\033[?25l` (hide cursor) pri prvnim spinner frame
   - `\033[?25h` (show cursor) v `clear_status()`

### ACP SDK

- Python SDK: `agent-client-protocol==0.8.0`
- TypeScript SDK (gemini-cli): `@agentclientprotocol/sdk ^0.12.0`
- Oficialni vzor: `examples/gemini.py` v python-sdk repu
- Dokumentace: https://agentclientprotocol.github.io/python-sdk/
