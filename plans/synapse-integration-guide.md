# Avatar Engine — Integrace do Synapse

Kompletní návod na integraci `avatar-engine` do Synapse aplikace.

## Co je Avatar Engine

Avatar Engine je AI avatar runtime — Python backend + React frontend knihovna.
Poskytuje kompletní chat UI s podporou tří AI providerů (Gemini CLI, Claude Code, Codex CLI),
session management, MCP tool orchestration a three-mode safety system.

**Publikované balíčky (v1.0.0):**

| Balíček | Registry | Účel |
|---------|----------|------|
| `avatar-engine` | [PyPI](https://pypi.org/project/avatar-engine/) | Python backend — AI engine, bridges, web server |
| `@avatar-engine/core` | [npm](https://www.npmjs.com/package/@avatar-engine/core) | TypeScript — typy, WS protokol, AvatarClient (framework-agnostic) |
| `@avatar-engine/react` | [npm](https://www.npmjs.com/package/@avatar-engine/react) | React — 23 komponent, 7 hooků, Tailwind preset, CSS styly |

GitHub: https://github.com/raven2cz/avatar-engine

---

## 1. Backend — Python

### Instalace

```bash
pip install avatar-engine[web]
```

Nebo s uv:

```bash
uv pip install avatar-engine[web]
```

### Prerekvizity — AI provider CLIs

Nainstaluj alespoň jeden provider (account-based auth, žádné API klíče):

```bash
# Gemini CLI (Google účet)
sudo npm install -g @google/gemini-cli

# Claude Code (Anthropic Pro/Max)
sudo npm install -g @anthropic-ai/claude-code

# Codex CLI (ChatGPT Plus/Pro)
sudo npm install -g @openai/codex
```

### Varianta A: Sidecar (doporučeno pro začátek)

Spusť avatar-engine jako samostatný proces vedle Synapse backendu:

```bash
avatar-web --port 8420 --provider gemini --no-static
```

Flags:
- `--port 8420` — port pro WebSocket + REST API
- `--provider gemini` — výchozí AI provider
- `--no-static` — neservíruj frontend (Synapse má vlastní)
- `--config ~/.synapse/avatar.yaml` — vlastní konfigurace (volitelné)

### Varianta B: FastAPI mount (pro produkci)

Pokud Synapse běží na FastAPI, můžeš avatar API mountnout přímo:

```python
from fastapi import FastAPI
from avatar_engine.web import create_api_app

app = FastAPI()  # Synapse hlavní app

# Mount avatar engine pod /api/avatar
avatar_app = create_api_app(provider="gemini")
app.mount("/api/avatar", avatar_app)
```

`create_api_app()` přijímá parametry:
- `provider` — výchozí provider (`"gemini"`, `"claude"`, `"codex"`)
- `model` — výchozí model (volitelné)
- `config_path` — cesta k YAML konfiguraci
- `system_prompt` — system prompt pro AI
- `timeout` — timeout v sekundách
- `working_dir` — pracovní adresář pro AI

### Konfigurace — avatar.yaml

```yaml
# ~/.synapse/avatar.yaml
provider: "gemini"

gemini:
  model: ""                    # prázdné = default model
  timeout: 120
  approval_mode: "yolo"        # yolo = auto-approve tools
  acp_enabled: true
  mcp_servers:
    synapse-tools:
      command: "python"
      args: ["synapse_mcp_server.py"]

claude:
  model: "claude-sonnet-4-5"
  permission_mode: "acceptEdits"
  cost_control:
    max_turns: 10
    max_budget_usd: 5.0

codex:
  model: ""
  auth_method: "chatgpt"
  approval_mode: "auto"

engine:
  auto_restart: true
  max_restarts: 3
```

### REST API endpointy

| Method | Endpoint | Popis |
|--------|----------|-------|
| GET | `/api/avatar/health` | Health check |
| GET | `/api/avatar/capabilities` | Provider capabilities |
| GET | `/api/avatar/sessions` | Seznam sessions |
| GET | `/api/avatar/providers` | Dostupní provideři |
| POST | `/api/avatar/chat` | Non-streaming chat |
| POST | `/api/avatar/upload` | Upload souboru |

### WebSocket

Connect na `ws://localhost:8420/api/avatar/ws` pro real-time streaming.

---

## 2. Frontend — React

### Instalace

```bash
cd synapse/apps/web  # nebo kde je Synapse frontend
npm install @avatar-engine/react
```

Tím se nainstaluje i `@avatar-engine/core` jako dependency — nepotřebuješ instalovat zvlášť.

### Krok 1: Tailwind konfigurace

```js
// tailwind.config.js
import avatarPreset from '@avatar-engine/react/tailwind-preset'

export default {
  presets: [avatarPreset],
  content: [
    './src/**/*.{tsx,ts}',
    // DŮLEŽITÉ: Tailwind musí skenovat i knihovnu pro purge
    './node_modules/@avatar-engine/react/dist/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        // Přepiš akcenty pro Synapse brand (volitelné)
        // Default: synapse=#6366f1 (indigo), pulse=#8b5cf6 (violet), neural=#06b6d4 (cyan)
        synapse: '#6366f1',
        pulse: '#8b5cf6',
        neural: '#06b6d4',
      },
    },
  },
}
```

### Krok 2: Import stylů

V entry pointu (main.tsx nebo App.tsx):

```tsx
import '@avatar-engine/react/styles.css'
```

### Krok 3: Vite proxy

```ts
// vite.config.ts
import { defineConfig } from 'vite'

export default defineConfig({
  server: {
    proxy: {
      '/api/avatar': {
        target: 'http://localhost:8420',
        ws: true,  // DŮLEŽITÉ: WebSocket proxy
      },
    },
  },
})
```

### Krok 4: Použití v komponentě

#### Nejjednodušší — AvatarWidget (FAB + chat drawer)

```tsx
import { useAvatarChat, AvatarWidget, PermissionDialog } from '@avatar-engine/react'

function App() {
  const chat = useAvatarChat('ws://localhost:8420/api/avatar/ws', {
    apiBase: '/api/avatar',
    initialProvider: 'gemini',
  })

  return (
    <>
      {/* Synapse layout */}
      <SynapseRoutes />

      {/* Avatar widget — floating action button v rohu */}
      <AvatarWidget {...chat} />

      {/* Permission dialog — pro ACP tool approval */}
      <PermissionDialog
        request={chat.permissionRequest}
        onRespond={chat.sendPermissionResponse}
      />
    </>
  )
}
```

AvatarWidget má 3 režimy:
- **FAB** — malé tlačítko v pravém dolním rohu
- **Compact** — malý chat drawer (300x400px)
- **Fullscreen** — celoobrazovkový chat panel

#### S konfigurací (provider, model, callbacks)

```tsx
const chat = useAvatarChat('ws://localhost:8420/api/avatar/ws', {
  apiBase: '/api/avatar',
  initialProvider: 'gemini',
  initialModel: 'gemini-2.5-flash',
  initialOptions: { thinking_level: 'low' },
  onResponse(message) {
    console.log('AI odpověděl:', message.content.slice(0, 100))
  },
})
```

#### Custom providers (přepsat default seznam)

```tsx
import { AvatarWidget, useAvatarChat, type ProviderConfig } from '@avatar-engine/react'

const synapseProviders: ProviderConfig[] = [
  {
    id: 'gemini',
    label: 'Gemini',
    defaultModel: 'gemini-2.5-flash',
    models: ['gemini-2.5-flash', 'gemini-2.5-pro'],
    gradient: 'from-blue-500/20 to-cyan-500/20 border-blue-400/40',
    dotColor: 'bg-blue-400',
  },
]

function App() {
  const chat = useAvatarChat('ws://localhost:8420/api/avatar/ws')
  return <AvatarWidget {...chat} customProviders={synapseProviders} />
}
```

#### Headless — vlastní UI (bez předpřipravených komponent)

```tsx
import { useAvatarChat } from '@avatar-engine/react'

function SynapseChat() {
  const {
    messages,
    sendMessage,
    isStreaming,
    connected,
    thinking,
    cost,
    error,
  } = useAvatarChat('ws://localhost:8420/api/avatar/ws')

  return (
    <div>
      {messages.map((msg) => (
        <div key={msg.id} className={msg.role}>
          {msg.content}
          {msg.isStreaming && <span className="animate-pulse">|</span>}
        </div>
      ))}

      {thinking.active && <div>Přemýšlím: {thinking.subject}</div>}

      <form onSubmit={(e) => {
        e.preventDefault()
        const input = e.currentTarget.elements.namedItem('msg') as HTMLInputElement
        sendMessage(input.value)
        input.value = ''
      }}>
        <input name="msg" disabled={!connected || isStreaming} />
        <button type="submit" disabled={!connected || isStreaming}>
          Odeslat
        </button>
      </form>
    </div>
  )
}
```

---

## 3. useAvatarChat — kompletní API

```tsx
const {
  // Zprávy
  messages,              // ChatMessage[] — všechny zprávy (user + assistant)
  sendMessage,           // (text, attachments?) => void
  stopResponse,          // () => void — zrušit aktuální odpověď
  clearHistory,          // () => void

  // Stav
  isStreaming,            // boolean — AI právě odpovídá
  connected,             // boolean — WebSocket připojen
  error,                 // string | null
  diagnostic,            // string | null

  // Provider
  provider,              // string — aktuální provider ID
  model,                 // string | null — aktuální model
  switchProvider,         // (provider, model?, options?) => void
  capabilities,          // ProviderCapabilities | null

  // Session
  sessionId,             // string | null
  sessionTitle,          // string | null
  resumeSession,         // (sessionId) => void
  newSession,            // () => void

  // AI stav
  thinking,              // { active, phase, subject } — thinking stav
  cost,                  // { totalCostUsd, totalInputTokens, totalOutputTokens }

  // Safety
  safetyMode,            // 'safe' | 'ask' | 'unrestricted'
  permissionRequest,     // PermissionRequest | null
  sendPermissionResponse, // (requestId, optionId, cancelled) => void

  // Soubory
  pendingFiles,          // UploadedFile[]
  uploading,             // boolean
  uploadFile,            // (file: File) => Promise
  removeFile,            // (fileId) => void
} = useAvatarChat(wsUrl, options?)
```

---

## 4. Dostupné komponenty

### Layout
| Komponenta | Popis |
|-----------|-------|
| `AvatarWidget` | Master layout — FAB + compact drawer + fullscreen panel |
| `ChatPanel` | Fullscreen chat UI |
| `CompactChat` | Compact chat drawer |
| `StatusBar` | Header s provider badge, model, session info |

### Chat
| Komponenta | Popis |
|-----------|-------|
| `MessageBubble` | Jednotlivá zpráva (user / assistant) s markdown |
| `MarkdownContent` | Markdown renderer se syntax highlight |
| `ThinkingIndicator` | AI thinking fáze |
| `ToolActivity` | Status MCP tool volání |
| `BreathingOrb` | Animovaný orb (prázdný stav) |
| `CostTracker` | Zobrazení ceny API volání |

### Provider & Session
| Komponenta | Popis |
|-----------|-------|
| `ProviderModelSelector` | Dropdown pro přepínání providera/modelu |
| `SessionPanel` | Seznam sessions, resume, nová session |
| `OptionControl` | Dynamické inputy pro provider options |

### Safety & Permissions
| Komponenta | Popis |
|-----------|-------|
| `PermissionDialog` | ACP tool permission modal |
| `SafetyModeSelector` | Safe / Ask / Unrestricted toggle |
| `SafetyModal` | Potvrzovací dialog pro unrestricted mode |

### Avatar
| Komponenta | Popis |
|-----------|-------|
| `AvatarBust` | Animovaný bust avatara |
| `AvatarFab` | Floating action button |
| `AvatarPicker` | Výběr avatara |
| `AvatarLogo` | Avatar Engine logo |

---

## 5. Theming — CSS Custom Properties

Pro runtime theming bez Tailwind rebuildu:

```css
:root {
  --avatar-accent: #6366f1;
  --avatar-accent-secondary: #8b5cf6;
  --avatar-bg-primary: #0a0a0f;
  --avatar-bg-panel: #13131b;
  --avatar-text-primary: #f8fafc;
  --avatar-text-secondary: #94a3b8;
  --avatar-border-radius: 0.75rem;
}
```

---

## 6. Shrnutí — minimální integrace

### Backend
```bash
pip install avatar-engine[web]
avatar-web --port 8420 --provider gemini --no-static
```

### Frontend
```bash
npm install @avatar-engine/react
```

```tsx
// App.tsx
import { useAvatarChat, AvatarWidget } from '@avatar-engine/react'
import '@avatar-engine/react/styles.css'

function App() {
  const chat = useAvatarChat('ws://localhost:8420/api/avatar/ws')
  return <AvatarWidget {...chat} />
}
```

```js
// tailwind.config.js
import avatarPreset from '@avatar-engine/react/tailwind-preset'
export default {
  presets: [avatarPreset],
  content: ['./src/**/*.{tsx,ts}', './node_modules/@avatar-engine/react/dist/**/*.js'],
}
```

```ts
// vite.config.ts — proxy
server: { proxy: { '/api/avatar': { target: 'http://localhost:8420', ws: true } } }
```

To je vše. 4 soubory, 3 řádky kódu v komponentě.
