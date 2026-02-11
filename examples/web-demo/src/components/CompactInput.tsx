/**
 * Compact mode input — smaller textarea with send/attach buttons.
 * Supports Enter-to-send, Shift+Enter for newline, paste + drag-drop.
 */

import { useCallback, useRef, useState, type DragEvent } from 'react'
import { ArrowUp, Paperclip, Square } from 'lucide-react'
import type { UploadedFile } from '../api/types'

interface CompactInputProps {
  onSend: (text: string) => void
  onStop: () => void
  isStreaming: boolean
  connected: boolean
  pendingFiles?: UploadedFile[]
  onUpload?: (file: File) => Promise<unknown>
  onRemoveFile?: (fileId: string) => void
}

export function CompactInput({ onSend, onStop, isStreaming, connected, pendingFiles = [], onUpload, onRemoveFile }: CompactInputProps) {
  const [input, setInput] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleDrop = useCallback((e: DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    if (!onUpload) return
    Array.from(e.dataTransfer.files).forEach((f) => onUpload(f))
  }, [onUpload])

  const handleSend = useCallback(() => {
    const trimmed = input.trim()
    if (!trimmed || isStreaming || !connected) return
    onSend(trimmed)
    setInput('')
    if (inputRef.current) inputRef.current.style.height = 'auto'
  }, [input, isStreaming, connected, onSend])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 80) + 'px'
  }

  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    if (!onUpload) return
    const items = Array.from(e.clipboardData.items)
    for (const item of items) {
      if (item.kind === 'file') {
        const file = item.getAsFile()
        if (file) { e.preventDefault(); onUpload(file); return }
      }
    }
  }, [onUpload])

  return (
    <div
      className={`px-3 pb-2 pt-1 border-t flex-shrink-0 transition-colors ${dragOver ? 'border-synapse/50 bg-synapse/5' : 'border-slate-mid/25'}`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      {/* Pending files (compact) */}
      {pendingFiles.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-1">
          {pendingFiles.map((f) => (
            <span key={f.fileId} className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-slate-mid/30 text-[0.6rem] text-text-secondary">
              {f.filename.length > 20 ? f.filename.slice(0, 17) + '...' : f.filename}
              {onRemoveFile && (
                <button onClick={() => onRemoveFile(f.fileId)} className="text-text-muted hover:text-red-400 ml-0.5">&times;</button>
              )}
            </span>
          ))}
        </div>
      )}

      {/* Input row */}
      <div className={`flex items-end gap-1.5 rounded-2xl border px-3 py-1.5 transition-colors ${
        !connected ? 'border-red-500/20 opacity-50' : 'border-slate-mid/40 focus-within:border-synapse/40'
      }`}
        style={{ background: 'rgba(26,26,46,0.35)', backdropFilter: 'blur(8px)' }}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="image/*,.pdf,.md,.txt,audio/*"
          className="hidden"
          onChange={(e) => {
            if (!onUpload || !e.target.files) return
            Array.from(e.target.files).forEach((f) => onUpload(f))
            e.target.value = ''
          }}
        />

        <textarea
          ref={inputRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder={!connected ? 'Connecting...' : isStreaming ? 'Waiting...' : 'Type a message...'}
          disabled={!connected || isStreaming}
          rows={1}
          className="flex-1 bg-transparent text-text-primary placeholder:text-text-muted text-[0.78rem] resize-none outline-none min-h-[22px] max-h-[80px] py-0.5 disabled:cursor-not-allowed"
        />

        <div className="flex items-center gap-0.5 flex-shrink-0">
          {!isStreaming && onUpload && (
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={!connected}
              className="w-6 h-6 rounded-lg flex items-center justify-center text-text-muted hover:text-text-secondary transition-colors disabled:opacity-30"
              title="Attach file"
            >
              <Paperclip className="w-3.5 h-3.5" />
            </button>
          )}
          {isStreaming ? (
            <button
              onClick={onStop}
              className="w-7 h-7 rounded-full flex items-center justify-center bg-red-500/80 text-white hover:bg-red-500 transition-colors"
              title="Stop"
            >
              <Square className="w-3 h-3" fill="currentColor" />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim() || !connected}
              className="w-7 h-7 rounded-full flex items-center justify-center bg-gradient-to-r from-synapse to-pulse text-white shadow-sm disabled:opacity-30 disabled:cursor-not-allowed hover:scale-105 active:scale-95 transition-transform"
              title="Send (Enter)"
            >
              <ArrowUp className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
