# @avatar-engine/react

[![npm](https://img.shields.io/npm/v/@avatar-engine/react?label=%40avatar-engine%2Freact)](https://www.npmjs.com/package/@avatar-engine/react)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-blue?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![License](https://img.shields.io/github/license/raven2cz/avatar-engine)](https://github.com/raven2cz/avatar-engine/blob/main/LICENSE)

React components and hooks for [Avatar Engine](https://github.com/raven2cz/avatar-engine) — a complete AI chat UI with provider switching, session management, avatar animations, and theming.

> This package re-exports everything from [`@avatar-engine/core`](../core/), so you only need to install this one.

## Installation

```bash
npm install @avatar-engine/react
```

**Peer dependencies:** React 18+ or 19+, ReactDOM

## Quick Start

### Minimal setup (3 files)

**1. Configure Tailwind** (`tailwind.config.js`):

```js
import avatarPreset from '@avatar-engine/react/tailwind-preset'

export default {
  presets: [avatarPreset],
  content: [
    './src/**/*.{tsx,ts}',
    './node_modules/@avatar-engine/react/dist/**/*.js',
  ],
}
```

**2. Import styles** (in your entry point):

```tsx
import '@avatar-engine/react/styles.css'
```

**3. Use the widget** (`App.tsx`):

```tsx
import { useAvatarChat, AvatarWidget } from '@avatar-engine/react'

function App() {
  const chat = useAvatarChat('ws://localhost:8420/api/avatar/ws')

  return (
    <div>
      <h1>My App</h1>
      <AvatarWidget {...chat} />
    </div>
  )
}
```

That's it — you get a floating action button (FAB) that expands into a compact chat drawer or fullscreen chat panel.

### With initial configuration

```tsx
import { useAvatarChat, AvatarWidget, PermissionDialog } from '@avatar-engine/react'

function App() {
  const chat = useAvatarChat('ws://localhost:8420/api/avatar/ws', {
    apiBase: '/api/avatar',
    initialProvider: 'gemini',
    initialModel: 'gemini-2.5-flash',
    initialOptions: { thinking_level: 'low' },
    onResponse(message) {
      console.log('AI responded:', message.content.slice(0, 100))
    },
  })

  return (
    <>
      <AvatarWidget {...chat} />
      <PermissionDialog
        request={chat.permissionRequest}
        onRespond={chat.sendPermissionResponse}
      />
    </>
  )
}
```

### Headless mode (custom UI)

Use `useAvatarChat` without any pre-built components:

```tsx
import { useAvatarChat } from '@avatar-engine/react'

function CustomChat() {
  const { messages, sendMessage, isStreaming, connected } = useAvatarChat(
    'ws://localhost:8420/api/avatar/ws'
  )

  return (
    <div>
      {messages.map((msg) => (
        <div key={msg.id} className={msg.role}>
          {msg.content}
          {msg.isStreaming && <span className="cursor" />}
        </div>
      ))}
      <form onSubmit={(e) => {
        e.preventDefault()
        const input = e.currentTarget.elements.namedItem('msg') as HTMLInputElement
        sendMessage(input.value)
        input.value = ''
      }}>
        <input name="msg" disabled={!connected || isStreaming} />
      </form>
    </div>
  )
}
```

## Hooks

### `useAvatarChat(wsUrl, options?)`

Main orchestration hook — manages WebSocket connection, message state, file uploads, and provider switching.

```tsx
const chat = useAvatarChat('ws://localhost:8420/api/avatar/ws', {
  apiBase: '/api/avatar',           // REST API base (default: '/api/avatar')
  initialProvider: 'gemini',        // Auto-switch provider on connect
  initialModel: 'gemini-2.5-flash', // Auto-switch model on connect
  initialOptions: { ... },          // Provider options to apply
  onResponse: (msg) => { ... },     // Called when response completes
})
```

**Returns** (`UseAvatarChatReturn`):

| Property | Type | Description |
|----------|------|-------------|
| `messages` | `ChatMessage[]` | All messages (user + assistant) |
| `sendMessage` | `(text, attachments?) => void` | Send a user message |
| `stopResponse` | `() => void` | Cancel current AI response |
| `clearHistory` | `() => void` | Clear all messages |
| `switchProvider` | `(provider, model?, options?) => void` | Switch AI provider/model |
| `resumeSession` | `(sessionId) => void` | Resume a previous session |
| `newSession` | `() => void` | Start a new session |
| `isStreaming` | `boolean` | Whether AI is currently responding |
| `connected` | `boolean` | WebSocket connected |
| `provider` | `string` | Current provider ID |
| `model` | `string \| null` | Current model name |
| `sessionId` | `string \| null` | Current session ID |
| `sessionTitle` | `string \| null` | Current session title |
| `thinking` | `{ active, phase, subject }` | Thinking state |
| `cost` | `{ totalCostUsd, totalInputTokens, totalOutputTokens }` | Accumulated cost |
| `capabilities` | `ProviderCapabilities \| null` | Provider feature flags |
| `safetyMode` | `SafetyMode` | Current safety mode |
| `permissionRequest` | `PermissionRequest \| null` | Pending permission request |
| `sendPermissionResponse` | `(requestId, optionId, cancelled) => void` | Respond to permission |
| `pendingFiles` | `UploadedFile[]` | Files queued for upload |
| `uploading` | `boolean` | File upload in progress |
| `uploadFile` | `(file: File) => Promise` | Upload a file |
| `removeFile` | `(fileId) => void` | Remove a pending file |
| `error` | `string \| null` | Error message |
| `diagnostic` | `string \| null` | Diagnostic message |

### `useAvatarWebSocket(wsUrl)`

Low-level WebSocket hook — manages connection, state machine, and raw message dispatch. Used internally by `useAvatarChat`.

### `useWidgetMode(options?)`

Widget display mode state machine (FAB → compact → fullscreen).

### `useAvatarBust(engineState, isStreaming)`

Avatar bust animation state derived from engine activity.

### `useFileUpload(apiBase)`

File upload queue with progress tracking.

### `useAvailableProviders(apiBase)`

Fetch available providers from the REST API.

## Components

### Layout

| Component | Description |
|-----------|-------------|
| `AvatarWidget` | Master layout — FAB button, compact drawer, and fullscreen panel |
| `ChatPanel` | Fullscreen chat UI with messages, input, and status bar |
| `CompactChat` | Compact mode chat drawer |
| `StatusBar` | Header bar with provider badge, model name, session info |

### Chat

| Component | Description |
|-----------|-------------|
| `MessageBubble` | Single message (user or assistant) with markdown rendering |
| `MarkdownContent` | Markdown renderer with syntax highlighting |
| `ThinkingIndicator` | AI thinking phase display |
| `ToolActivity` | Tool execution status (started/completed/failed) |
| `BreathingOrb` | Animated orb for empty state |
| `CostTracker` | API cost display |

### Provider & Session

| Component | Description |
|-----------|-------------|
| `ProviderModelSelector` | Provider/model dropdown with options |
| `SessionPanel` | Session list, resume, new session |
| `OptionControl` | Dynamic option inputs (select, slider, number) |

### Safety & Permissions

| Component | Description |
|-----------|-------------|
| `PermissionDialog` | ACP tool permission request modal |
| `SafetyModeSelector` | Safe / Ask / Unrestricted toggle |
| `SafetyModal` | Confirmation dialog for unrestricted mode |

### Avatar

| Component | Description |
|-----------|-------------|
| `AvatarBust` | Animated avatar bust with state-driven animations |
| `AvatarFab` | Floating action button |
| `AvatarPicker` | Avatar selection |
| `AvatarLogo` | Avatar Engine logo |

## Theming

### Tailwind Preset

The preset provides the Avatar Engine design system — dark glassmorphism theme with accent colors:

```js
// tailwind.config.js
import avatarPreset from '@avatar-engine/react/tailwind-preset'

export default {
  presets: [avatarPreset],
  content: [
    './src/**/*.{tsx,ts}',
    './node_modules/@avatar-engine/react/dist/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        // Override accent colors for your brand
        synapse: '#ff6b6b',  // Primary accent (default: indigo)
        pulse: '#ff8e53',    // Secondary accent (default: violet)
        neural: '#ffd93d',   // Tertiary accent (default: cyan)
      },
    },
  },
}
```

### CSS Custom Properties

For runtime theming without Tailwind rebuilds:

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

### Custom Providers

Override the built-in provider list with your own:

```tsx
import { AvatarWidget, useAvatarChat, type ProviderConfig } from '@avatar-engine/react'

const myProviders: ProviderConfig[] = [
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
  return <AvatarWidget {...chat} customProviders={myProviders} />
}
```

## Vite Proxy

When developing with Vite, proxy the Avatar Engine backend:

```ts
// vite.config.ts
export default defineConfig({
  server: {
    proxy: {
      '/api/avatar': {
        target: 'http://localhost:8420',
        ws: true,
      },
    },
  },
})
```

## Backend

This package is the React frontend for [Avatar Engine](https://github.com/raven2cz/avatar-engine) — a Python backend that wraps Gemini CLI, Claude Code, and Codex CLI into a unified WebSocket API. See the [main README](https://github.com/raven2cz/avatar-engine) for backend setup.

## License

Apache-2.0
