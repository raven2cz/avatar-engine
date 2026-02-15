/**
 * Compact chat container — header + messages + input.
 *
 * Glassmorphism panel with rounded top corners.
 * Receives all chat data from parent (AvatarWidget).
 *
 * Shows a prominent connection status overlay when disconnected,
 * so the user always knows what's happening and when they can type.
 */

import { useTranslation } from 'react-i18next'
import type { ChatMessage, EngineState, UploadedFile } from '@avatar-engine/core'
import { CompactHeader } from './CompactHeader'
import { CompactMessages } from './CompactMessages'
import { CompactInput } from './CompactInput'

interface CompactChatProps {
  messages: ChatMessage[]
  provider: string
  model: string | null
  version?: string | null
  connected: boolean
  wasConnected?: boolean
  initDetail?: string
  error?: string | null
  diagnostic?: string | null
  engineState: EngineState | string
  thinkingSubject?: string
  toolName?: string
  isStreaming: boolean
  pendingFiles?: UploadedFile[]
  uploading?: boolean
  onSend: (text: string) => void
  onStop: () => void
  onUpload?: (file: File) => Promise<unknown>
  onRemoveFile?: (fileId: string) => void
  onFullscreen: () => void
  onClose: () => void
  // Provider/model switching (passed through to CompactHeader dropdown)
  switching?: boolean
  activeOptions?: Record<string, string | number>
  availableProviders?: Set<string> | null
  onSwitchProvider?: (provider: string, model?: string, options?: Record<string, string | number>) => void
  // First-time hint on expand button
  showExpandHint?: boolean
}

export function CompactChat({
  messages,
  provider,
  model,
  version,
  connected,
  wasConnected,
  initDetail,
  error,
  diagnostic,
  engineState,
  thinkingSubject,
  toolName,
  isStreaming,
  pendingFiles,
  uploading,
  onSend,
  onStop,
  onUpload,
  onRemoveFile,
  onFullscreen,
  onClose,
  switching,
  activeOptions,
  availableProviders,
  onSwitchProvider,
  showExpandHint,
}: CompactChatProps) {
  const { t } = useTranslation()

  return (
    <div className="flex-1 flex flex-col min-w-0 overflow-hidden rounded-t-2xl bg-[rgba(18,18,35,0.96)] backdrop-blur-[24px] border-t border-l border-white/[0.08] shadow-[0_-8px_40px_rgba(0,0,0,0.6)]">
      {/* Accent gradient line at top edge for visual separation from background */}
      <div className="h-[1.5px] w-full bg-gradient-to-r from-transparent via-synapse/40 to-transparent flex-shrink-0" />
      <CompactHeader
        provider={provider}
        model={model}
        version={version}
        connected={connected}
        engineState={engineState}
        thinkingSubject={thinkingSubject}
        toolName={toolName}
        onFullscreen={onFullscreen}
        onClose={onClose}
        switching={switching}
        activeOptions={activeOptions}
        availableProviders={availableProviders}
        onSwitchProvider={onSwitchProvider}
        showExpandHint={showExpandHint}
      />

      {/* Connection status overlay — shown when not connected */}
      {!connected && (
        <div className="flex-1 flex flex-col items-center justify-center px-4 py-6 gap-3 animate-fade-in">
          <div className="w-8 h-8 border-2 border-synapse/40 border-t-synapse rounded-full animate-spin" />
          <div className="text-center">
            <p className="text-sm font-medium text-text-primary mb-1">
              {wasConnected ? t('connection.reconnecting') : t('connection.connecting')}
            </p>
            {initDetail && (
              <p className="text-[0.7rem] text-synapse animate-pulse max-w-[250px]">
                {initDetail}
              </p>
            )}
            {!initDetail && !wasConnected && (
              <p className="text-[0.7rem] text-text-muted max-w-[250px]">
                {t('connection.initializing', { provider: provider || 'engine' })}
              </p>
            )}
            {wasConnected && (
              <p className="text-[0.7rem] text-text-muted">
                {t('connection.lost')}
              </p>
            )}
            {diagnostic && (
              <p className="text-[0.6rem] text-amber-400/70 font-mono mt-2 max-w-[280px] truncate">
                {diagnostic}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Error banner — shown above messages when error exists */}
      {connected && error && (
        <div className="mx-3 mt-1 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/25 text-red-400 text-[0.7rem] flex-shrink-0 animate-fade-in">
          {error}
        </div>
      )}

      {/* Diagnostic banner — shows CLI stderr/diagnostic messages */}
      {connected && diagnostic && !error && (
        <div className="mx-3 mt-1 px-3 py-1.5 rounded-lg bg-amber-500/8 border border-amber-500/20 text-amber-400/80 text-[0.65rem] font-mono flex-shrink-0 animate-fade-in truncate">
          {diagnostic}
        </div>
      )}

      {/* Messages area — only shown when connected */}
      {connected && <CompactMessages messages={messages} version={version} />}

      <CompactInput
        onSend={onSend}
        onStop={onStop}
        isStreaming={isStreaming}
        connected={connected}
        pendingFiles={pendingFiles}
        onUpload={onUpload}
        onRemoveFile={onRemoveFile}
      />
    </div>
  )
}
