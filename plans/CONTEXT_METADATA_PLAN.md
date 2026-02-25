# Context Metadata for Chat Messages

**Status:** Proposed
**Author:** Synapse integration team
**Date:** 2026-02-25

## Problem

Host applications (e.g. Synapse) need to send **page context** (what the user is currently viewing) alongside chat messages so the AI can provide context-aware responses. Currently the only way to do this is to prepend a text prefix to the user's message:

```
[Context: Viewing pack detail, pack: Illustrious-XL]

What does this model do?
```

This causes two problems:

1. **Ugly UI** — the `[Context: ...]` prefix is visible in the user's chat bubble because it's part of `ChatMessage.content`.
2. **Fragile parsing** — the AI sees a formatted string rather than structured metadata.

## Requirements

### R1: Structured context field on the WebSocket chat message

Add an optional `context` field to the `chat` message type:

```typescript
// Client → Server (WebSocket)
{
  "type": "chat",
  "data": {
    "message": "What does this model do?",     // user-visible text only
    "context": {                                // optional, opaque metadata
      "page": "pack-detail",
      "description": "Viewing pack detail",
      "entity": "Illustrious-XL",
      "entityType": "pack",
      "pathname": "/packs/illustrious-xl"
    },
    "attachments": [...]
  }
}
```

The `context` value is an **opaque JSON object** — avatar-engine does not interpret its keys. It just forwards it to the AI provider as part of the prompt context.

### R2: Context sent to AI but NOT stored in message content

When the backend receives a message with `context`:

1. **Build a system/context preamble** for the AI call — e.g. prepend `[Context: ${JSON.stringify(context)}]` to the prompt sent to the bridge, or inject it as a system message segment.
2. **Do NOT include context in the user message content** that is stored in conversation history or echoed back to the client. The `ChatMessage.content` field must contain only the user's actual text.

### R3: React hook API — `sendMessage` accepts context

Update `useAvatarChat` and `useAvatarWebSocket` to accept an optional `context` parameter:

```typescript
// useAvatarWebSocket
sendMessage: (message: string, attachments?: ChatAttachment[], context?: Record<string, unknown>) => void

// useAvatarChat
sendMessage: (text: string, attachments?: UploadedFile[], context?: Record<string, unknown>) => void
```

The context is forwarded over the WebSocket but **not** stored in the local `ChatMessage` object added to `messages[]`.

### R4: Optional `context` field on ChatMessage (for display hints)

Optionally, add a `context?: Record<string, unknown>` field to the `ChatMessage` type so the host app can access it for rendering (e.g. showing a small context badge). This is lower priority than R1-R3.

```typescript
export interface ChatMessage {
  // ... existing fields ...
  context?: Record<string, unknown>  // optional, for host app rendering
}
```

### R5: Backward compatibility

- `context` is optional everywhere — omitting it preserves current behavior.
- Old clients that don't send `context` continue to work unchanged.
- The REST `POST /api/avatar/chat` endpoint should also accept `context` in the request body.

## Implementation Scope

### Files to change

| File | Change |
|------|--------|
| `packages/core/src/types.ts` | Add `context?: Record<string, unknown>` to `ChatMessage` |
| `packages/react/src/hooks/useAvatarWebSocket.ts` | Accept `context` param in `sendMessage`, include in WS payload |
| `packages/react/src/hooks/useAvatarChat.ts` | Accept `context` param in `sendMessage`, pass through to `wsSend`, optionally store on `ChatMessage` |
| `avatar_engine/web/server.py` | Parse `context` from chat message data, pass to `engine.chat()` |
| `avatar_engine/engine.py` | Accept `context` param in `chat()`, pass to `bridge.send()` |
| `avatar_engine/bridges/*.py` | Accept `context` in `send()`, prepend/inject into AI prompt |

### What the host app (Synapse) will do after this lands

```typescript
// Before (current — ugly prefix in chat bubble):
const fullMessage = `[Context: Viewing settings]\n\nChange the theme`
chat.sendMessage(fullMessage)

// After (clean — context sent as metadata):
const context = { page: 'settings', description: 'Viewing settings' }
chat.sendMessage('Change the theme', undefined, context)
```

## Non-goals

- Avatar-engine does NOT need to understand or parse the context keys — it's opaque JSON forwarded to the AI.
- No new UI components in avatar-engine for displaying context.
- No changes to the `AvatarWidget` component props (host apps handle context injection themselves).
