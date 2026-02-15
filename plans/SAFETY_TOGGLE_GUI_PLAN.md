# Plan: Safety Toggle v GUI s potvrzovacím modálem

## Stav implementace

| Fáze | Stav |
|------|------|
| **Fáze 1: Safety toggle + modál** | ✅ HOTOVO (commit 74d97c5) |
| **Fáze 1b: Race condition fix** | ✅ HOTOVO (startup task cancellation při switchi) |
| **Fáze 2: Dotazovací režim (Ask)** | ✅ HOTOVO (commit 8f43259, merged to main) |

## Context

Backend již má `safety_instructions: bool = True` implementované (engine, config, safety.py).
Uživatel potřebuje možnost safety vypnout z GUI — např. když chce legitimně smazat soubory.
Ale nesmí to být „omylem" — při vypnutí se ukáže varovný modál s vysvětlením důsledků.

**Architektura flowu:**
```
ProviderModelSelector toggle
  → potvrzovací modál (pokud vypínáme)
  → switchProvider(..., options: { safety_instructions: false })
  → WS "switch" message
  → EngineSessionManager.switch() → kwargs.update()
  → AvatarEngine(safety_instructions=False)
  → bridge bez safety prefixu
```

Backend nepotřebuje žádné změny — `safety_instructions` už protéká přes `kwargs` do enginu.

---

## Změny

### 1. `examples/web-demo/src/components/SafetyModal.tsx` — NOVÝ

Varovný modál, který se zobrazí když uživatel chce safety vypnout.
Vzor: `PromoModal.tsx` (backdrop + escape + centered panel).

Obsah modálu:
- Ikona štítu (ShieldOff z lucide-react)
- Nadpis: "Disable Safety Instructions?"
- Popis rizik: model bude moci mazat soubory, přistupovat k credentials, eskalovat oprávnění
- Dvě tlačítka: **Cancel** (zruší), **Disable Safety** (červené, potvrdí)
- Escape / click mimo = Cancel

Props: `{ open, onConfirm, onCancel }`

### 2. `examples/web-demo/src/components/ProviderModelSelector.tsx` — EDIT

Přidat safety toggle do sekce Options (pod provider-specific options):

- Nový lokální state: `safetyEnabled` (init z `activeOptions.safety_instructions !== 0`)
- Checkbox s labelem + štítovou ikonou (Shield / ShieldOff)
- Klik na checkbox:
  - Zapnutí (false→true): okamžitě, bez modálu
  - Vypnutí (true→false): otevřít `SafetyModal`, teprve po potvrzení nastavit
- V `sanitizeOptions()` a `handleApplyOptions()`: přidat `safety_instructions: safetyEnabled ? 1 : 0` do options
  (posíláme jako number 1/0 protože options type je `Record<string, string | number>`, v engine se truthy vyhodnotí správně)
- Safety toggle se zobrazí pro VŠECHNY providery (na rozdíl od provider options, které jsou per-provider)

### 3. `examples/web-demo/src/hooks/useAvatarWebSocket.ts` — EDIT

Do reducer `CONNECTED` case přidat:
```ts
safetyInstructions: action.payload.data.safety_instructions ?? true,
```
Do `WsState` interface přidat `safetyInstructions: boolean`.

### 4. `examples/web-demo/src/hooks/useAvatarChat.ts` — EDIT

- Přidat `safetyInstructions` do return (z `state.safetyInstructions`)
- V `switchProvider()`: přenést `safety_instructions` z flat options do built options

### 5. `avatar_engine/web/server.py` — EDIT

V `_broadcast_connected()` přidat do `data`:
```python
"safety_instructions": getattr(eng, '_safety_instructions', True),
```
Tím frontend při (re)connect ví, jestli je safety zapnuté.

### 6. Překlady — i18n

**`en.json`** — přidat klíče:
```json
"safety": {
  "label": "Safety instructions",
  "enabled": "AI will refuse destructive operations",
  "modalTitle": "Disable Safety Instructions?",
  "modalDescription": "Without safety instructions, the AI assistant will be able to:",
  "modalRisk1": "Delete files and directories",
  "modalRisk2": "Access credentials and API keys",
  "modalRisk3": "Run sudo and escalate privileges",
  "modalWarning": "Only disable if you understand the risks and need the AI to perform operations that safety rules block.",
  "cancel": "Cancel",
  "disable": "Disable Safety"
}
```

**`cs.json`** — české překlady:
```json
"safety": {
  "label": "Bezpečnostní instrukce",
  "enabled": "AI odmítne destruktivní operace",
  "modalTitle": "Vypnout bezpečnostní instrukce?",
  "modalDescription": "Bez bezpečnostních instrukcí bude AI asistent moci:",
  "modalRisk1": "Mazat soubory a adresáře",
  "modalRisk2": "Přistupovat k přihlašovacím údajům a API klíčům",
  "modalRisk3": "Spouštět sudo a eskalovat oprávnění",
  "modalWarning": "Vypněte pouze pokud rozumíte rizikům a potřebujete, aby AI provedla operace blokované bezpečnostními pravidly.",
  "cancel": "Zrušit",
  "disable": "Vypnout ochranu"
}
```

---

## Soubory

| Soubor | Akce | Stav |
|--------|------|------|
| `examples/web-demo/src/components/SafetyModal.tsx` | NOVÝ — varovný modál | ✅ |
| `examples/web-demo/src/components/ProviderModelSelector.tsx` | EDIT — safety checkbox (fullscreen) | ✅ |
| `examples/web-demo/src/components/CompactHeader.tsx` | EDIT — safety checkbox (compact mode) | ✅ |
| `examples/web-demo/src/hooks/useAvatarWebSocket.ts` | EDIT — `safetyInstructions` ve stavu | ✅ |
| `examples/web-demo/src/hooks/useAvatarChat.ts` | EDIT — propagace safety stavu | ✅ |
| `examples/web-demo/src/api/types.ts` | EDIT — `safety_instructions` v ConnectedMessage | ✅ |
| `avatar_engine/web/server.py` | EDIT — safety flag v `connected` message + startup race fix | ✅ |
| `avatar_engine/engine.py` | EDIT — safety_instructions v engine + bridge guard | ✅ |
| `avatar_engine/config.py` | EDIT — safety_instructions v AvatarConfig | ✅ |
| `avatar_engine/safety.py` | NOVÝ — DEFAULT_SAFETY_INSTRUCTIONS konstanta | ✅ |
| `examples/web-demo/src/i18n/locales/en.json` | EDIT — anglické překlady | ✅ |
| `examples/web-demo/src/i18n/locales/cs.json` | EDIT — české překlady | ✅ |
| `tests/test_safety.py` | NOVÝ — unit testy safety modulu | ✅ |
| `tests/integration/test_real_safety.py` | NOVÝ — integrační test skeleton | ✅ |

---

## Ověření

1. `npm run build` v `examples/web-demo/` — TypeScript kompilace bez chyb
2. `python -m pytest tests/ -x -q --timeout=30 -k "not slow and not integration"` — regrese
3. Manuální test v prohlížeči:
   - Otevřít dropdown → safety checkbox je zaškrtnutý (default on)
   - Odškrtnout → objeví se varovný modál
   - Cancel → checkbox zůstane zaškrtnutý
   - Disable Safety → checkbox se odškrtne, Apply Options se ukáže
   - Apply → engine se restartne bez safety, model nyní provede destruktivní operace
   - Znovu zaškrtnout → okamžitě (bez modálu), Apply → safety zpět

---

## FÁZE 2: Dotazovací režim — Ask mode (branch `feature/safety-ask-mode`)

### Motivace

Momentálně máme binární volbu: safety ON (model vše odmítne) nebo safety OFF (model vše provede).
To není ideální — uživatel často chce, aby model *mohl* mazat soubory, ale **zeptal se předtím**.
Proto přidáme třetí režim: **dotazovací (ask)**.

### Tři režimy bezpečnosti

| Režim | Hodnota | Chování |
|-------|---------|---------|
| **Safe** | `"safe"` | Model odmítne destruktivní operace (současné `safety_instructions=True`) |
| **Ask** | `"ask"` | Model se zeptá uživatele před destruktivní operací — frontend zobrazí permission dialog |
| **Unrestricted** | `"unrestricted"` | Model provede cokoli bez dotazu (současné `safety_instructions=False`) |

### Změna typu `safety_instructions`

```python
# config.py — z bool na enum/string
safety_instructions: str = "safe"  # "safe" | "ask" | "unrestricted"
```

Zpětná kompatibilita: `True` → `"safe"`, `False` → `"unrestricted"`.

### Aktuální stav ACP infrastruktury (výzkum ze sessions)

> Tato sekce shrnuje výzkum provedený v sessions `cdbfa87c` a `4b8ccfa8`,
> aby příští implementátor nemusel začínat od nuly.

**Klíčové zjištění: ACP SDK `request_permission` je production-ready.**
Gemini i Codex CLI reálně posílají `request_permission` requesty přes ACP protokol.
Avatar Engine je ale zatím vždy auto-approvuje.

**Aktuální kód v bridges:**

- `gemini.py:1248` — `_AvatarACPClient.request_permission()` — pokud `auto_approve=True`
  (default, protože `approval_mode="yolo"`), vždy vrátí `AllowedOutcome`.
  Hledá `allow_once` / `allow_always` v options, fallback na první option.

- `codex.py:851` — `_CodexACPClient.request_permission()` — totéž, `auto_approve=True`
  (default, `approval_mode="auto"`), vždy vrátí `AllowedOutcome`.

- `gemini.py:353` — pokud `approval_mode == "yolo"`, přidá `--yolo` flag do CLI args.
  **Bez `--yolo`** Gemini CLI posílá `request_permission` pro každý tool call.

**ACP PermissionOption typy** (z SDK):
- `allow_once` — schválit jednou
- `allow_always` — schválit vždy (pro tuto session)
- `reject_once` / `reject_always` (implicitně `DeniedOutcome`)

**Co je potřeba změnit pro Ask režim:**
1. `_AvatarACPClient.request_permission()` — místo auto-approve emitovat event a čekat na Future
2. Gemini bridge — při `ask` režimu **nepřidávat `--yolo`** (CLI pak samo posílá permission requesty)
3. Codex bridge — při `ask` režimu nastavit `approval_mode="manual"`
4. Claude bridge — nemá ACP, spoléhá jen na system prompt instrukce
5. Engine — routovat permission requesty přes eventy do WebSocket → frontend

**Třívrstvá obrana (z výzkumu):**
- **Vrstva 1** (IMPLEMENTOVÁNO): System prompt safety instrukce — model odmítne sám
- **Vrstva 2** (TATO FÁZE): Permission dialog — GUI se zeptá uživatele
- **Vrstva 3** (BUDOUCÍ): OS-level sandbox (mimo scope)

### Ask režim — detailní architektura

#### Princip: nezávislá feature

Ask mode je **nezávislá feature**. ACP permission infrastruktura existuje odděleně,
ale aktivuje se **pouze** když `safety_mode == "ask"`. V režimech Safe a Unrestricted
se ACP permission dialog vůbec nepoužívá.

#### 1. Typ `safety_mode` — z bool na string enum

```python
# safety.py
SafetyMode = Literal["safe", "ask", "unrestricted"]
```

Zpětná kompatibilita: `True` → `"safe"`, `False` → `"unrestricted"`.
V engine.py, config.py, WS protokolu: `safety_instructions: bool` → `safety_mode: str`.

#### 2. ACP request_permission — přesná API (z reálného SDK)

```python
# ACP SDK - metoda na ACPClient:
async def request_permission(
    self,
    options: list,              # List[PermissionOption]
    session_id: str,
    tool_call: "ToolCall",      # tool_call.function_name, tool_call.arguments
    **kwargs,
) -> RequestPermissionResponse:
```

**PermissionOption** (z ACP SDK):
- `option_id: str` — unikátní ID volby
- `kind: str` — `"allow_once"`, `"allow_always"`, `"reject_once"`, `"reject_always"`
- (+ popis, metadata dle verze SDK)

**RequestPermissionResponse** — vrací se:
- `AllowedOutcome(option_id=..., outcome="selected")` — schváleno
- `DeniedOutcome(outcome="cancelled")` — zamítnuto

#### 3. Ask mode flow (async Future pattern)

```
Gemini/Codex CLI tool call
  → ACP request_permission(options, session_id, tool_call)
    → [Ask mode] bridge emituje PermissionRequestEvent
      → Engine.emit() → WebSocketBridge → WS client
        → Frontend zobrazí PermissionDialog s options
          → Uživatel vybere option (nebo Esc = cancel)
            → WS "permission_response" → server → engine.resolve_permission()
              → asyncio.Future.set_result(selected_option)
                → request_permission() vrátí AllowedOutcome / DeniedOutcome
                  → CLI provede / odmítne tool call
```

Klíčové: `request_permission()` je async → čekáme na `asyncio.Future` bez timeoutu.
Uživatel může kdykoli Esc = `DeniedOutcome(outcome="cancelled")`.

#### 4. Bridge changes

**Gemini bridge** (`gemini.py`):
- Ask mode: `approval_mode = "ask"` → nepřidá `--yolo` do CLI args
- `_AvatarACPClient.__init__` dostane `permission_handler: Callable` callback
- `request_permission()`: pokud handler existuje, zavolá ho a čeká na výsledek

**Codex bridge** (`codex.py`):
- Ask mode: `approval_mode = "ask"` → nenastaví `auto_approve=True`
- Stejný pattern s `permission_handler` callbackem

**Claude bridge** (`claude.py`):
- Nemá ACP protokol → Ask mode pro Claude = system prompt instrukce
- `ASK_MODE_SAFETY_INSTRUCTIONS` v system promptu (soft enforcement)

#### 5. PermissionRequestEvent — nový event typ

```python
# events.py
@dataclass
class PermissionRequestEvent(AvatarEvent):
    request_id: str         # UUID pro párování request/response
    tool_name: str          # "bash", "write_file", etc.
    tool_input: str         # argumenty tool callu (truncated)
    options: List[Dict]     # [{option_id, kind, description}, ...]
    provider: str           # "gemini" / "codex"
```

#### 6. WebSocket protokol

**Server → Client** (nový typ v protocol.py):
```json
{
  "type": "permission_request",
  "data": {
    "request_id": "uuid-123",
    "tool_name": "run_shell_command",
    "tool_input": "rm -rf /tmp/test",
    "options": [
      {"option_id": "opt-1", "kind": "allow_once", "label": "Allow Once"},
      {"option_id": "opt-2", "kind": "allow_always", "label": "Allow Always"},
      {"option_id": "opt-3", "kind": "reject_once", "label": "Deny"}
    ]
  }
}
```

**Client → Server** (nový typ v parse_client_message):
```json
{
  "type": "permission_response",
  "data": {
    "request_id": "uuid-123",
    "option_id": "opt-1",
    "cancelled": false
  }
}
```

Cancel (Esc): `{ "cancelled": true }` → `DeniedOutcome`.

#### 7. Engine permission handler

```python
# engine.py
self._pending_permissions: Dict[str, asyncio.Future] = {}

async def _handle_permission_request(self, request_id, options, tool_call):
    future = asyncio.get_running_loop().create_future()
    self._pending_permissions[request_id] = future
    self.emit(PermissionRequestEvent(...))
    return await future  # čeká bez timeoutu

def resolve_permission(self, request_id: str, option_id: str = "", cancelled: bool = False):
    future = self._pending_permissions.pop(request_id, None)
    if future and not future.done():
        future.set_result({"option_id": option_id, "cancelled": cancelled})
```

#### 8. GUI — trojitý selektor + PermissionDialog

**Trojitý selektor** (nahrazuje checkbox v ProviderModelSelector + CompactHeader):
```tsx
<SafetyModeSelector mode={safetyMode} onChange={handleModeChange} />
// Safe | Ask | Unrestricted — s ikonami Shield, HelpCircle, Zap
// Přechod na Unrestricted vyžaduje SafetyModal potvrzení
// Přechod na Ask / Safe je okamžitý
```

**PermissionDialog** — modální dialog při Ask mode:
- Zobrazí tool name + argumenty
- Dynamicky renderuje tlačítka dle `options` z ACP
- Esc = cancel (vždy dostupný)
- Nezávislý na SafetyModal (ten je jen pro Unrestricted přepnutí)

### Soubory fáze 2

| Soubor | Akce |
|--------|------|
| `avatar_engine/safety.py` | EDIT — `SafetyMode` type, `ASK_MODE_SAFETY_INSTRUCTIONS` |
| `avatar_engine/events.py` | EDIT — `PermissionRequestEvent` |
| `avatar_engine/config.py` | EDIT — `safety_mode: str = "safe"` (z bool) |
| `avatar_engine/engine.py` | EDIT — permission handler, resolve, 3 režimy |
| `avatar_engine/bridges/gemini.py` | EDIT — `permission_handler` v ACPClient |
| `avatar_engine/bridges/codex.py` | EDIT — `permission_handler` v ACPClient |
| `avatar_engine/web/protocol.py` | EDIT — `PermissionRequestEvent` mapping, parse |
| `avatar_engine/web/server.py` | EDIT — WS permission routing |
| `avatar_engine/web/bridge.py` | EDIT — permission event broadcasting |
| `examples/web-demo/src/components/PermissionDialog.tsx` | NOVÝ |
| `examples/web-demo/src/components/SafetyModeSelector.tsx` | NOVÝ — trojitý selektor |
| `examples/web-demo/src/components/ProviderModelSelector.tsx` | EDIT — use SafetyModeSelector |
| `examples/web-demo/src/components/CompactHeader.tsx` | EDIT — use SafetyModeSelector |
| `examples/web-demo/src/hooks/useAvatarWebSocket.ts` | EDIT — permission messages |
| `examples/web-demo/src/hooks/useAvatarChat.ts` | EDIT — safetyMode typ |
| `examples/web-demo/src/api/types.ts` | EDIT — permission typy |
| `examples/web-demo/src/i18n/locales/en.json` | EDIT — překlady pro 3 režimy |
| `examples/web-demo/src/i18n/locales/cs.json` | EDIT — překlady pro 3 režimy |
| `tests/test_safety.py` | EDIT — testy 3 režimů |
| `tests/test_permission_flow.py` | NOVÝ — testy permission flow |
