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
import { useAvailableProviders } from './hooks/useAvailableProviders'

// WebSocket URL — uses Vite proxy in dev, direct in production
const WS_URL =
  import.meta.env.DEV
    ? `ws://${window.location.hostname}:5173/api/avatar/ws`
    : `ws://${window.location.host}/api/avatar/ws`

export default function App() {
  const availableProviders = useAvailableProviders()
  const {
    messages,
    sendMessage,
    stopResponse,
    clearHistory,
    switchProvider,
    resumeSession,
    newSession,
    activeOptions,
    initDetail,
    pendingFiles,
    uploading,
    uploadFile,
    removeFile,
    isStreaming,
    switching,
    connected,
    wasConnected,
    sessionId,
    sessionTitle,
    provider,
    model,
    version,
    cwd,
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
        model={model}
        version={version}
        cwd={cwd}
        engineState={engineState as any}
        capabilities={capabilities}
        sessionId={sessionId}
        sessionTitle={sessionTitle}
        cost={cost}
        switching={switching}
        activeOptions={activeOptions}
        availableProviders={availableProviders}
        onSwitch={switchProvider}
        onResume={resumeSession}
        onNewSession={newSession}
      />

      {/* Status banner — initialization or error */}
      {!connected && !wasConnected && (
        <div className="mx-6 mt-2 px-4 py-2 rounded-xl bg-synapse/10 border border-synapse/30 text-synapse text-sm animate-slide-up flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-synapse animate-pulse" />
          {initDetail || 'Initializing provider...'}
        </div>
      )}
      {!connected && wasConnected && (
        <div className="mx-6 mt-2 px-4 py-2 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-400 text-sm animate-slide-up flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
          Reconnecting...
        </div>
      )}
      {error && connected && (
        <div className="mx-6 mt-2 px-4 py-2 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm animate-slide-up">
          {error}
        </div>
      )}

      {/* Main chat area */}
      <main className="flex-1 flex flex-col min-h-0">
        <ChatPanel
          messages={messages}
          onSend={sendMessage}
          onStop={stopResponse}
          onClear={clearHistory}
          isStreaming={isStreaming}
          connected={connected}
          pendingFiles={pendingFiles}
          uploading={uploading}
          onUpload={uploadFile}
          onRemoveFile={removeFile}
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
