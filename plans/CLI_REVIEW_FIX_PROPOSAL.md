# CLI REPL Review + Návrh Oprav

> Status: DONE (2026-02-08) — all fixes applied, see CLI_DISPLAY_REWRITE_PLAN.md

Datum: 2026-02-07
Branch: `cli-plan`
Scope: `avatar_engine/cli/commands/repl.py`, `avatar_engine/cli/display.py`, související testy

## Findings (seřazeno podle závažnosti)

1. `HIGH` Konflikt `Live` renderu s textovým vstupem způsobuje blikání promptu a poškozený echo vstupu.
- Důkaz: `display.start_live()` se zapíná před vstupem (`avatar_engine/cli/commands/repl.py:172`), zatímco vstup běží přes `Prompt.ask(...)` (`avatar_engine/cli/commands/repl.py:180`).
- `Live` současně průběžně refreshuje terminál (`avatar_engine/cli/display.py:454-460`) a navíc běží vlastní update loop (`avatar_engine/cli/commands/repl.py:156-160`, `173`).
- Praktický dopad odpovídá reportu: blikající `You:` a nekorektní zobrazení psaného textu (viditelný jen první znak).

2. `HIGH` Stream odpovědi se tiskne mimo bezpečný render pipeline během aktivního `Live`, takže odpověď může být přepisována/neviditelná.
- Důkaz: při aktivním live režimu (`repl.py`) se chunky tisknou přes `console.print(chunk, end="")` (`avatar_engine/cli/commands/repl.py:286-287`), zatímco `display.update_live()` dál mění stejný terminální prostor.
- Praktický dopad odpovídá reportu: běží thinking, ale text odpovědi se uživateli nezobrazí.

3. `MEDIUM` Dvojité refreshování (`Live` auto refresh + vlastní async loop) zbytečně zvyšuje flicker a race okno.
- Důkaz: `Live(..., refresh_per_second=8)` (`avatar_engine/cli/display.py:454-458`) + vlastní smyčka `await asyncio.sleep(0.125)` a `display.update_live()` (`avatar_engine/cli/commands/repl.py:156-160`).
- Riziko: i při částečném fixu vstupu zůstane UI nestabilní (zbytečné redrawe).

4. `MEDIUM` Chybí testy pro interakci `Prompt.ask` + `Live` + stream výstup; regresi současné testy neodhalí.
- Důkaz: `tests/test_cli_display.py` testuje interní stav `DisplayManager`, ne REPL I/O lifecycle (není pokryta sekvence live-on -> prompt -> stream text -> live-update).
- Důsledek: změna prošla se zelenými testy, ale selhává v reálném TTY scénáři.

## Root Cause Shrnutí

REPL kombinuje interaktivní vstup (`Prompt.ask`) a průběžně překreslovaný `Live` output ve stejném terminálovém prostoru bez explicitní synchronizace lifecycle:
- vstupní fáze (user typing),
- status fáze (thinking/tools),
- textová fáze (assistant stream).

Současná implementace tyto fáze míchá současně, což vede k přepisování řádku promptu a ztrátě výstupu.

## Návrh oprav

### A. Oddělit fáze REPL lifecycle (doporučeno)

1. Před čtením uživatelského vstupu vždy `display.stop_live()`.
2. Načíst vstup (`Prompt.ask` nebo `console.input`).
3. Před voláním modelu znovu `display.start_live()`, `display.on_response_start()`.
4. Během streamu:
- buď dočasně pozastavit live redraw a tisknout čistý transcript,
- nebo tisknout přes konzoli spojenou s live kontextem a status render držet odděleně.
5. Po dokončení streamu `display.on_response_end()` a návrat do input fáze.

Poznámka: nejstabilnější varianta pro TTY je live status zobrazovat jen během čekání/thinking/tool eventů a během samotného textového streamu live vypnout.

### B. Zrušit dvojitý refresh mechanismus

Zvolit jen jednu strategii:
- buď `Live` auto-refresh,
- nebo vlastní update task.

Nedržet obě najednou.

### C. Zajistit robustní cleanup

- Při `update_task.cancel()` doplnit await/potlačení `CancelledError`, aby nevznikaly varování.
- Garantovat `display.on_response_end()` i při chybě uprostřed streamu (např. `try/finally` kolem stream loop).

### D. Doplnit testy proti regresi

1. Unit/integration test REPL lifecycle:
- live off během input,
- live on během thinking/tool state,
- validní transcript výstup při streamu.
2. Test s fake streamem po znacích/slovech ověřující, že odpověď je v output bufferu kompletní.
3. Test, že prompt echo neobsahuje artefakty při aktivním display režimu.

## Minimální implementační plán

1. Upravit `repl.py` na explicitní fázový režim (input vs response).
2. Upravit `display.py`, aby live režim nevyžadoval paralelní externí refresh loop (nebo naopak).
3. Doplnit testy v `tests/test_cli.py` nebo nový `tests/test_cli_repl_io.py`.
4. Ruční smoke test v reálném TTY:
- `avatar repl`
- napsat delší větu (ověřit echo všech znaků),
- ověřit že odpověď se vypíše celá,
- ověřit že prompt po odpovědi zůstane stabilní.

## Poznámka k plánu (`plans/GUI_READINESS_PLAN.md`)

Tento bug je prakticky blocker pro část „CLI display layer“. Návrh výše je konzistentní s cílem plánu (spinner + tool display), ale přidává nutnou podmínku: **striktní oddělení input a live-render fáze**, jinak je UX REPL nestabilní i při správných eventech.
