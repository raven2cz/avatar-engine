/**
 * Avatar Engine Web Demo — Main application.
 *
 * Architecture:
 *   useAvatarChat is called ONCE here. Its state is shared between
 *   compact mode (via AvatarWidget props) and fullscreen mode (via
 *   children rendered as overlay). Mode transitions never reconnect
 *   the WebSocket or reinitialize any state.
 *
 * Integration guide:
 *   AvatarWidget wraps your app. Pass chat data as props for compact
 *   mode, and render your fullscreen UI as children. Replace the
 *   <LandingPage> (inside AvatarWidget) with your own background.
 */

import { StatusBar } from './components/StatusBar'
import { ChatPanel } from './components/ChatPanel'
import { CostTracker } from './components/CostTracker'
import { AvatarWidget } from './components/AvatarWidget'
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
    <AvatarWidget
      // Shared chat data — used by compact mode components
      messages={messages}
      sendMessage={sendMessage}
      stopResponse={stopResponse}
      isStreaming={isStreaming}
      connected={connected}
      wasConnected={wasConnected}
      initDetail={initDetail}
      error={error}
      provider={provider}
      model={model}
      engineState={engineState}
      pendingFiles={pendingFiles}
      uploading={uploading}
      uploadFile={uploadFile}
      removeFile={removeFile}
      // Provider switching — enables ⋯ dropdown in compact header
      switching={switching}
      activeOptions={activeOptions}
      availableProviders={availableProviders}
      switchProvider={switchProvider}
    >
      {/* ============================================================ */}
      {/* FULLSCREEN CONTENT — rendered as overlay by AvatarWidget     */}
      {/* This is the existing full app UI (StatusBar + ChatPanel).    */}
      {/* It stays in the DOM at all times to avoid remounting.        */}
      {/* ============================================================ */}
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
    </AvatarWidget>
  )
}
