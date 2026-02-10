# ACP Generation Config Propagation

**Status:** DONE
**Branch:** `fix/acp-generation-config`
**Datum:** 2026-02-10

## Problem

V ACP mode se `generation_config` (thinking_level, temperature, response_modalities
atd.) **vubec nepredava** do Gemini CLI. Bridge parametry prijme, ale nikam je neposle.
UI vizualizuje zmeny (dropdown "High", "Medium"), ale model bezi na defaults.

## Kriticke nalezy z gemini-cli zdrojoveho kodu

### 1. Gemini CLI NEIMPLEMENTUJE `setSessionConfigOption`

Trida `GeminiAgent` implementuje POUZE:
- `initialize()`, `authenticate()`, `newSession()`, `loadSession()`, `cancel()`, `prompt()`

**NEIMPLEMENTUJE:**
- `setSessionConfigOption` — vrati "method not found" error
- `setSessionMode` — vrati "method not found" error
- `setSessionModel` (unstable) — vrati "method not found" error

### 2. VSECHNA konfigurace jde pres settings soubory

`GEMINI_CLI_SYSTEM_SETTINGS_PATH` env var → `settings.json` v temp dir (sandbox).
Uroven 5 v 6-urovnove hierarchii = druha nejvyssi priorita.

### 3. Built-in alias chain

```
base                    → temperature: 0, topP: 1
  └─ chat-base          → temperature: 1, topP: 0.95, topK: 64, includeThoughts: true
      ├─ chat-base-2.5  → thinkingBudget: 8192
      └─ chat-base-3    → thinkingLevel: HIGH
```

### 4. model.name v settings = Internal error

`model.name` na urovni system settings bypasuje cely alias chain → API vrati "Internal error".
**Nikdy nepsat `model.name` pro ACP.**

## Reseni: customOverrides + customAliases

Po systematickem testovani 21 experimentu (A–T) proti realnememu gemini-cli:

### Dva mechanismy

| Mechanismus | Ucel | Kdy pouzit |
|-------------|------|------------|
| `customOverrides` (pole) | generateContentConfig (thinking, temp, modalities) | VZDY kdyz je generation_config |
| `customAliases` | Model routing (presmerovani z default aliasu) | JEN pro non-default modely |

### Proc customOverrides misto customAliases pro config

`customAliases` NAHRAZUJE built-in alias na urovni klice (JS spread operator).
I s `extends` to zpusobovalo problemy. `customOverrides` se aplikuje AZ PO
alias resolution → zachovava celou built-in chain beze zmeny.

### Vysledna settings struktura

**Default model (gemini-3-pro-preview):**
```json
{
  "modelConfigs": {
    "customOverrides": [{
      "match": {"model": "gemini-3-pro-preview"},
      "modelConfig": {
        "generateContentConfig": {
          "temperature": 1.0,
          "thinkingConfig": {"thinkingLevel": "LOW"}
        }
      }
    }]
  }
}
```

**Non-default model (gemini-2.5-flash):**
```json
{
  "modelConfigs": {
    "customAliases": {
      "gemini-3-pro-preview": {
        "extends": "chat-base-2.5",
        "modelConfig": {"model": "gemini-2.5-flash"}
      }
    },
    "customOverrides": [{
      "match": {"model": "gemini-2.5-flash"},
      "modelConfig": {
        "generateContentConfig": {
          "temperature": 0.5
        }
      }
    }]
  }
}
```

### thinkingLevel omezeni na cloudcode-pa API

| Hodnota | gemini-3-pro-preview (Pro) | gemini-3-flash-preview (Flash) |
|---------|---------------------------|-------------------------------|
| HIGH | OK | OK |
| LOW | OK | OK |
| MEDIUM | "Internal error" | OK |
| MINIMAL | "Internal error" | ? |

Frontend zobrazuje MEDIUM/MINIMAL jen pro Flash modely (`modelPattern: 'flash'`).

## Implementace

### Zmenene soubory

| Soubor | Zmena |
|--------|-------|
| `avatar_engine/bridges/gemini.py` | `_setup_config_files()`: customOverrides pro ACP, customAliases jen pro routing |
| `avatar_engine/bridges/gemini.py` | `_get_base_alias()`: urcuje extends target (chat-base-3 / chat-base-2.5 / None) |
| `avatar_engine/bridges/gemini.py` | `_build_generation_config()`: skip thinkingConfig pro image modely |
| `tests/test_acp_generation_config.py` | **NOVY** — 981 unit testu pro config propagation |
| `tests/test_gemini_acp.py` | Aktualizovane settings assertions |
| `tests/test_zero_footprint.py` | Aktualizovane ACP settings testy |
| `tests/integration/test_real_acp.py` | 10 integracnich testu proti realnemu gemini-cli |
| `tests/integration/test_acp_settings_diagnostic.py` | **NOVY** — diagnosticky nastroj (21 experimentu) |
| `examples/web-demo/src/config/providers.ts` | Model-aware thinking levels, hideForModelPattern |
| `examples/web-demo/src/components/ProviderModelSelector.tsx` | Filtrovani options podle modelu, sanitizeOptions |
| `examples/web-demo/src/hooks/useAvatarChat.ts` | Auto-inject response_modalities pro image modely |

### Testy

- **981 unit testu** — vsechny prochazi
- **18/19 integracnich testu** — 1 failure je timeout/rate-limit (pre-existing)
- **7/7 ACP generation config** testu proti realnemu gemini-cli
- **3/3 image generation** settings testu

## Reference

### gemini-cli zdrojovy kod
- `packages/core/src/services/modelConfigService.ts` — alias chain resolution, overrides
- `packages/core/src/config/defaultModelConfigs.ts` — built-in aliases
- `packages/cli/src/config/settings.ts` — settings loading hierarchy
- `packages/cli/src/config/settingsSchema.ts` — customOverrides: type 'array'
- `packages/core/src/code_assist/converter.ts` — request payload building (no validation)
