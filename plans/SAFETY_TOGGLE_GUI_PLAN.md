# Plan: Safety Toggle v GUI s potvrzovacím modálem

## Stav implementace

| Fáze | Stav |
|------|------|
| **Fáze 1: Safety toggle + modál** | ✅ HOTOVO (commit 74d97c5) |
| **Fáze 1b: Race condition fix** | ✅ HOTOVO (startup task cancellation při switchi) |
| **Fáze 2: Dotazovací režim (Ask)** | ❌ BUDOUCÍ — popsáno níže |

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

## BUDOUCÍ FÁZE: Dotazovací režim (Permission Dialog)

> Tato sekce popisuje budoucí rozšíření. Implementace proběhne v samostatné branch.

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

### Ask režim — architektura

#### 1. Safety instrukce pro "ask" režim (`safety.py`)

Nová konstanta `ASK_MODE_SAFETY_INSTRUCTIONS`:
```
Before executing any potentially destructive operation, you MUST ask the user
for explicit permission. Destructive operations include:
- Deleting, removing, or overwriting files/directories
- Dropping databases or tables
- Killing system processes
- Modifying system configuration
- Accessing credentials or sensitive data
- Running sudo/su commands

Format your request as:
⚠️ PERMISSION REQUEST: [description of what you want to do and why]

Wait for the user to explicitly approve before proceeding.
```

#### 2. ACP `request_permission` protokol

Pro Gemini ACP bridge — Gemini CLI podporuje `request_permission` event:

```python
# bridges/gemini.py — v ACP event loop
if event.type == "request_permission":
    # Emitovat PermissionEvent do GUI
    self._emit_event({
        "type": "permission_request",
        "tool_name": event.tool_name,
        "description": event.description,
        "request_id": event.id,
    })
    # Čekat na odpověď z frontendu
    approved = await self._permission_future
    await event.respond(approved=approved)
```

#### 3. Frontend permission dialog

Nový komponent `PermissionDialog.tsx`:
- Zobrazí se uprostřed obrazovky (jako modál)
- Ikona štítu + popis operace
- Tři tlačítka: **Allow Once**, **Allow All** (pro tuto session), **Deny**
- Auto-deny po 30s timeoutu (bezpečnostní fallback)
- WebSocket message: `{ type: "permission_response", data: { request_id, approved, allow_all } }`

#### 4. WebSocket protokol

Nové message typy:

**Server → Client:**
```json
{
  "type": "permission_request",
  "data": {
    "request_id": "abc123",
    "tool_name": "bash",
    "description": "rm -rf /tmp/test_dir",
    "risk_level": "high"
  }
}
```

**Client → Server:**
```json
{
  "type": "permission_response",
  "data": {
    "request_id": "abc123",
    "approved": true,
    "allow_all": false
  }
}
```

#### 5. Engine-level permission handler

```python
# engine.py
class AvatarEngine:
    async def _handle_permission_request(self, request):
        """Route permission request to GUI via events."""
        future = asyncio.Future()
        self._pending_permissions[request["request_id"]] = future
        self.emit(PermissionRequestEvent(...))
        return await asyncio.wait_for(future, timeout=30)

    def approve_permission(self, request_id: str, approved: bool):
        """Called by GUI/WebSocket when user responds."""
        future = self._pending_permissions.pop(request_id, None)
        if future and not future.done():
            future.set_result(approved)
```

#### 6. GUI selector — 3 režimy místo checkboxu

V `ProviderModelSelector.tsx` nahradit checkbox trojitým selektorem:
```tsx
<div className="flex gap-0.5 rounded-lg bg-obsidian/50 p-0.5 border border-slate-mid/30">
  <button className={mode === 'safe' ? active : inactive}>🛡️ Safe</button>
  <button className={mode === 'ask' ? active : inactive}>❓ Ask</button>
  <button className={mode === 'unrestricted' ? active : inactive}>⚡ Unrestricted</button>
</div>
```

Přechod do `unrestricted` stále vyžaduje potvrzovací modál.
Přechod do `ask` nevyžaduje modál (je to bezpečný režim).

### Soubory budoucí fáze

| Soubor | Akce |
|--------|------|
| `avatar_engine/safety.py` | EDIT — přidat `ASK_MODE_SAFETY_INSTRUCTIONS` |
| `avatar_engine/config.py` | EDIT — `safety_instructions: str = "safe"` |
| `avatar_engine/engine.py` | EDIT — permission handler, 3 režimy |
| `avatar_engine/types.py` | EDIT — `PermissionRequestEvent` |
| `avatar_engine/web/server.py` | EDIT — WS permission routing |
| `examples/web-demo/src/components/PermissionDialog.tsx` | NOVÝ |
| `examples/web-demo/src/components/ProviderModelSelector.tsx` | EDIT — trojitý selektor |
| `examples/web-demo/src/hooks/useAvatarWebSocket.ts` | EDIT — permission messages |
| `examples/web-demo/src/i18n/locales/*.json` | EDIT — překlady pro 3 režimy |
