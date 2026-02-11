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
}: CompactChatProps) {
  return (
    <div className="flex-1 flex flex-col min-w-0 overflow-hidden rounded-t-2xl bg-[rgba(12,12,20,0.92)] backdrop-blur-[24px] border-t border-l border-white/[0.05]">
      <CompactHeader
        provider={provider}
        model={model}
        connected={connected}
        engineState={engineState}
        onFullscreen={onFullscreen}
        onClose={onClose}
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
