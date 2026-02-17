# @avatar-engine/core

[![npm](https://img.shields.io/npm/v/@avatar-engine/core?label=%40avatar-engine%2Fcore)](https://www.npmjs.com/package/@avatar-engine/core)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-blue?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![License](https://img.shields.io/github/license/raven2cz/avatar-engine)](https://github.com/raven2cz/avatar-engine/blob/main/LICENSE)

Framework-agnostic core for [Avatar Engine](https://github.com/raven2cz/avatar-engine) — TypeScript types, WebSocket protocol state machine, and a ready-to-use client class.

Use this package directly when building with Vue, Svelte, vanilla JS, or any non-React framework. React users should install [`@avatar-engine/react`](../react/) instead (it re-exports everything from core).

## Installation

```bash
npm install @avatar-engine/core
```

## Quick Start

### AvatarClient (recommended)

The simplest way to connect — a batteries-included WebSocket client with auto-reconnect and state management:

```ts
import { AvatarClient } from '@avatar-engine/core'

const client = new AvatarClient('ws://localhost:8420/api/avatar/ws', {
  onStateChange(state) {
    console.log(`[${state.provider}] ${state.engineState}`)
    if (state.error) console.error(state.error)
  },
  onMessage(msg) {
    if (msg.type === 'text') process.stdout.write(msg.data.text)
    if (msg.type === 'chat_response') console.log('\n--- done ---')
  },
})

client.connect()
client.sendChat('Hello, what can you do?')
```

### Vue 3 composable

```ts
import { reactive, onMounted, onUnmounted } from 'vue'
import { AvatarClient, type AvatarState } from '@avatar-engine/core'

export function useAvatar(url: string) {
  const state = reactive<AvatarState>({} as AvatarState)
  const client = new AvatarClient(url, {
    onStateChange: (s) => Object.assign(state, s),
  })

  onMounted(() => client.connect())
  onUnmounted(() => client.disconnect())

  return { state, client }
}
```

### Svelte store

```ts
import { writable } from 'svelte/store'
import { AvatarClient, initialAvatarState } from '@avatar-engine/core'

export function createAvatarStore(url: string) {
  const state = writable(initialAvatarState)
  const client = new AvatarClient(url, {
    onStateChange: (s) => state.set({ ...s }),
  })

  client.connect()
  return { state, client }
}
```

### Low-level: reducer + message builders

For full control, use the pure-function state machine directly:

```ts
import {
  avatarReducer,
  initialAvatarState,
  parseServerMessage,
  createChatMessage,
} from '@avatar-engine/core'

let state = initialAvatarState

const ws = new WebSocket('ws://localhost:8420/api/avatar/ws')

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data)
  const { action } = parseServerMessage(msg)
  if (action) {
    state = avatarReducer(state, action)
    console.log('New state:', state.engineState)
  }
}

ws.onopen = () => {
  ws.send(createChatMessage('Hello!'))
}
```

## API Reference

### AvatarClient

High-level WebSocket client with auto-reconnect.

| Method | Description |
|--------|-------------|
| `connect()` | Connect to the WebSocket server |
| `disconnect()` | Disconnect and stop reconnecting |
| `getState()` | Get current `AvatarState` snapshot |
| `sendChat(text, attachments?)` | Send a chat message |
| `stop()` | Cancel the current response |
| `switchProvider(provider, model?, options?)` | Switch AI provider/model |
| `resumeSession(sessionId)` | Resume a previous session |
| `newSession()` | Start a new session |
| `sendPermissionResponse(requestId, optionId, cancelled)` | Respond to a permission request |
| `clearHistory()` | Clear conversation history |

### State Machine

| Export | Description |
|--------|-------------|
| `avatarReducer(state, action)` | Pure reducer: `AvatarState` + `AvatarAction` → `AvatarState` |
| `parseServerMessage(msg)` | Parse a `ServerMessage` into an `AvatarAction` |
| `initialAvatarState` | Default state (disconnected, idle) |

### Message Builders

| Function | Description |
|----------|-------------|
| `createChatMessage(text, attachments?)` | Build a chat request JSON string |
| `createStopMessage()` | Build a stop request |
| `createSwitchMessage(provider, model?, options?)` | Build a provider switch request |
| `createPermissionResponse(requestId, optionId, cancelled)` | Build a permission response |
| `createResumeSessionMessage(sessionId)` | Build a session resume request |
| `createNewSessionMessage()` | Build a new session request |
| `createClearHistoryMessage()` | Build a clear history request |

### Configuration

| Export | Description |
|--------|-------------|
| `PROVIDERS` | Default provider configurations (Gemini, Claude, Codex) |
| `AVATARS` | Default avatar visual configurations |
| `buildOptionsDict(providerId, values)` | Convert flat key-value options to nested provider options |
| `getModelDisplayName(providerId, model)` | Get display name for a model |
| `isImageModel(model)` | Check if a model supports image generation |

### i18n

| Export | Description |
|--------|-------------|
| `initAvatarI18n(reactModule?)` | Initialize i18n (call before rendering) |
| `changeLanguage(lang)` | Switch language (`'en'`, `'cs'`) |
| `getCurrentLanguage()` | Get current language code |
| `AVAILABLE_LANGUAGES` | Supported language list |

### Types

All TypeScript types for the WebSocket protocol are exported:

**State types:** `AvatarState`, `EngineState`, `BridgeState`, `SafetyMode`, `ThinkingPhase`

**Server messages:** `ServerMessage`, `ConnectedMessage`, `TextMessage`, `ThinkingMessage`, `ToolMessage`, `CostMessage`, `ErrorMessage`, `ChatResponseMessage`, `PermissionRequestMessage`, ...

**Client messages:** `ClientMessage`, `ChatRequest`, `SwitchRequest`, `PermissionResponseRequest`, ...

**UI state:** `ChatMessage`, `ToolInfo`, `ThinkingInfo`, `CostInfo`, `UploadedFile`, `SessionInfo`

**Widget types:** `WidgetMode`, `BustState`, `AvatarConfig`, `AvatarPoses`, `PermissionRequest`

**Provider config:** `ProviderConfig`, `ProviderOption`, `ProviderCapabilities`

## Backend

This package is the frontend client for [Avatar Engine](https://github.com/raven2cz/avatar-engine) — a Python backend that wraps Gemini CLI, Claude Code, and Codex CLI into a unified WebSocket API. See the [main README](https://github.com/raven2cz/avatar-engine) for backend setup.

## License

Apache-2.0
