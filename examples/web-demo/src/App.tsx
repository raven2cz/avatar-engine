/**
 * Avatar Engine Web Demo — Main application.
 *
 * Imports all UI from @avatar-engine/react package.
 * Only demo-specific components (LandingPage, PromoModal) remain local.
 */

import { useCallback, useRef, useState } from 'react'
import {
  StatusBar,
  ChatPanel,
  CostTracker,
  AvatarWidget,
  PermissionDialog,
  useAvatarChat,
  useAvailableProviders,
  LS_PROMO_DISMISSED,
} from '@avatar-engine/react'
import { LandingPage } from './components/LandingPage'
import { PromoModal } from './components/PromoModal'

// WebSocket URL — uses Vite proxy in dev, direct in production
const WS_URL =
  import.meta.env.DEV
    ? `ws://${window.location.hostname}:5173/api/avatar/ws`
    : `ws://${window.location.host}/api/avatar/ws`

export default function App() {
  const compactModeRef = useRef<(() => void) | null>(null)
  const handleCompactMode = useCallback(() => compactModeRef.current?.(), [])

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
    thinking,
    toolName,
    cost,
    capabilities,
    error,
    diagnostic,
    permissionRequest,
    sendPermissionResponse,
  } = useAvatarChat(WS_URL)

  // --- Promo modal state (demo-specific) ---
  const [promoOpen, setPromoOpen] = useState(() =>
    localStorage.getItem(LS_PROMO_DISMISSED) !== 'true'
  )
  const [promoShowNextTime, setPromoShowNextTime] = useState(true)

  const handlePromoClose = useCallback(() => {
    setPromoOpen(false)
    if (!promoShowNextTime) {
      localStorage.setItem(LS_PROMO_DISMISSED, 'true')
    } else {
      localStorage.removeItem(LS_PROMO_DISMISSED)
    }
  }, [promoShowNextTime])

  return (
    <>
    <PermissionDialog request={permissionRequest} onRespond={sendPermissionResponse} />
    <AvatarWidget
      messages={messages}
      sendMessage={sendMessage}
      stopResponse={stopResponse}
      isStreaming={isStreaming}
      connected={connected}
      wasConnected={wasConnected}
      initDetail={initDetail}
      error={error}
      diagnostic={diagnostic}
      provider={provider}
      model={model}
      version={version}
      engineState={engineState}
      thinkingSubject={thinking.active ? thinking.subject : ''}
      toolName={toolName}
      pendingFiles={pendingFiles}
      uploading={uploading}
      uploadFile={uploadFile}
      removeFile={removeFile}
      switching={switching}
      activeOptions={activeOptions}
      availableProviders={availableProviders}
      switchProvider={switchProvider}
      onCompactModeRef={compactModeRef}
      renderBackground={({ showFabHint, version: v, defaultMode, onDefaultModeChange }) => (
        <LandingPage
          showFabHint={showFabHint}
          version={v}
          defaultMode={defaultMode}
          onDefaultModeChange={onDefaultModeChange}
          onOpenPromo={() => setPromoOpen(true)}
        />
      )}
    >
      <div className="h-full bg-obsidian flex flex-col overflow-hidden">
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
          onCompactMode={handleCompactMode}
        />

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
        {diagnostic && connected && !error && (
          <div className="mx-6 mt-2 px-4 py-1.5 rounded-xl bg-amber-500/8 border border-amber-500/20 text-amber-400/80 text-xs font-mono animate-slide-up truncate">
            {diagnostic}
          </div>
        )}

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

        {capabilities?.cost_tracking && (
          <footer className="px-6 pb-2">
            <div className="max-w-4xl mx-auto">
              <CostTracker cost={cost} visible={capabilities.cost_tracking} />
            </div>
          </footer>
        )}
      </div>
    </AvatarWidget>
    <PromoModal
      open={promoOpen}
      onClose={handlePromoClose}
      showNextTime={promoShowNextTime}
      onShowNextTimeChange={setPromoShowNextTime}
      version={version}
    />
    </>
  )
}
