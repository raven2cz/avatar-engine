/**
 * Compact chat container — header + messages + input.
 *
 * Glassmorphism panel with rounded top corners.
 * Receives all chat data from parent (AvatarWidget).
 */

import type { ChatMessage, EngineState, UploadedFile } from '../api/types'
import { CompactHeader } from './CompactHeader'
import { CompactMessages } from './CompactMessages'
import { CompactInput } from './CompactInput'

interface CompactChatProps {
  messages: ChatMessage[]
  provider: string
  model: string | null
  connected: boolean
  engineState: EngineState | string
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
  connected,
  engineState,
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
  return (
    <div className="flex-1 flex flex-col min-w-0 overflow-hidden rounded-t-2xl bg-[rgba(18,18,35,0.96)] backdrop-blur-[24px] border-t border-l border-white/[0.08] shadow-[0_-8px_40px_rgba(0,0,0,0.6)]">
      {/* Accent gradient line at top edge for visual separation from background */}
      <div className="h-[1.5px] w-full bg-gradient-to-r from-transparent via-synapse/40 to-transparent flex-shrink-0" />
      <CompactHeader
        provider={provider}
        model={model}
        connected={connected}
        engineState={engineState}
        onFullscreen={onFullscreen}
        onClose={onClose}
        switching={switching}
        activeOptions={activeOptions}
        availableProviders={availableProviders}
        onSwitchProvider={onSwitchProvider}
        showExpandHint={showExpandHint}
      />
      <CompactMessages messages={messages} />
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
