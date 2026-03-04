# Plan: New Session Button (Compact + Fullscreen)

> Status: DONE (2026-03-02)
> Created: 2026-03-02

## Context

Users need a quick way to start a new session without opening the SessionPanel modal. Currently the only way is: click session button in StatusBar → modal opens → click "New Session" inside modal. This is 2 clicks for a critical action. The button should be subtle but discoverable in both compact and fullscreen modes.

## Design

### Fullscreen: StatusBar — icon button before Session button

Add a `Plus` icon button (from lucide-react) in the right controls section of StatusBar, positioned **between the Info button and the Session management button**. This follows the existing icon button pattern (`p-1.5 rounded-lg text-text-muted hover:text-text-secondary`).

- Icon: `Plus` (lucide-react, already imported in SessionPanel — just add to StatusBar)
- Hover: `hover:text-synapse hover:bg-synapse/10` — subtle accent on hover, distinct from destructive red of "clear"
- Disabled when `!connected` or `isStreaming`
- Tooltip: "New session" (i18n key)
- No confirmation dialog — direct action (consistent with how it works in SessionPanel)

### Compact: CompactHeader — icon button before ⋯ menu

Add matching `Plus` icon button in the right controls section of CompactHeader, positioned as the **first button** (before the ⋯ menu button). Same `w-6 h-6 rounded-md` sizing as other compact controls.

- SVG Plus icon (inline, matching compact style — no lucide import needed, keep it lightweight)
- Hover: `hover:text-synapse hover:bg-synapse/10`
- Disabled when `!connected` or streaming
- Tooltip: "New session"

### Prop Threading

```
useAvatarChat → newSession callback
  ↓
AvatarWidget → CompactChat (add onNewSession prop)
  ↓
CompactChat → CompactHeader (add onNewSession prop)
```

StatusBar already receives `onNewSession` — no changes needed there.

## Files Modified ✅

1. **`packages/react/src/components/StatusBar.tsx`** — Plus icon button before session management button
2. **`packages/react/src/components/CompactHeader.tsx`** — onNewSession + isStreaming props, Plus icon button
3. **`packages/react/src/components/CompactChat.tsx`** — onNewSession prop pass-through
4. **`packages/react/src/components/AvatarWidget.tsx`** — newSession prop → onNewSession to CompactChat

## Verification ✅

1. `npm run build -w packages/core && npm run build -w packages/react` — no TS errors
2. `npm test -w packages/core` — existing tests pass
3. Manual test in web-demo: button visible in both modes, calls newSession on click
