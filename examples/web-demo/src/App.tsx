/**
 * Avatar Engine Web Demo — Main application.
 *
 * Synapse-inspired dark theme with glassmorphism, gradient accents,
 * and animated status indicators.
 */

import { StatusBar } from './components/StatusBar'
import { ChatPanel } from './components/ChatPanel'
import { CostTracker } from './components/CostTracker'
import { useAvatarChat } from './hooks/useAvatarChat'

// WebSocket URL — uses Vite proxy in dev, direct in production
const WS_URL =
  import.meta.env.DEV
    ? `ws://${window.location.hostname}:5173/api/avatar/ws`
    : `ws://${window.location.host}/api/avatar/ws`

export default function App() {
  const {
    messages,
    sendMessage,
    clearHistory,
    isStreaming,
    connected,
    provider,
    engineState,
    cost,
    capabilities,
    error,
  } = useAvatarChat(WS_URL)

  return (
    <div className="min-h-screen bg-obsidian flex flex-col">
      <StatusBar
        connected={connected}
        provider={provider}
        engineState={engineState as any}
        capabilities={capabilities}
        sessionId={null}
      />

      {/* Error banner */}
      {error && (
        <div className="mx-6 mt-2 px-4 py-2 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm animate-slide-up">
          {error}
        </div>
      )}

      {/* Main chat area */}
      <main className="flex-1 flex flex-col min-h-0">
        <ChatPanel
          messages={messages}
          onSend={sendMessage}
          onClear={clearHistory}
          isStreaming={isStreaming}
          connected={connected}
        />
      </main>

      {/* Footer: Cost tracker */}
      {capabilities?.cost_tracking && (
        <footer className="px-6 pb-2">
          <div className="max-w-4xl mx-auto">
            <CostTracker cost={cost} visible={capabilities.cost_tracking} />
          </div>
        </footer>
      )}
    </div>
  )
}
