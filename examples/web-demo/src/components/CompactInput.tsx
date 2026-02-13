/**
 * Compact mode input — textarea with send/attach buttons.
 * Supports Enter-to-send, Shift+Enter for newline, paste + drag-drop.
 */

import { useCallback, useRef, useState, type DragEvent } from 'react'
import { useTranslation } from 'react-i18next'
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
  const { t } = useTranslation()
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
    el.style.height = Math.min(el.scrollHeight, 120) + 'px'
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
      className={`px-3 pb-3 pt-1.5 border-t flex-shrink-0 transition-colors ${dragOver ? 'border-synapse/50 bg-synapse/5' : 'border-white/[0.05]'}`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      {/* Pending files (compact) */}
      {pendingFiles.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-1.5">
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

      {/* Input container */}
      <div className={`flex items-end gap-2 rounded-2xl border px-3.5 py-2 transition-all duration-200 ${
        !connected
          ? 'border-red-500/20 opacity-40'
          : 'border-white/[0.12] hover:border-white/[0.18] focus-within:border-synapse/50 focus-within:shadow-[0_0_0_1px_rgba(99,102,241,0.2),0_2px_8px_rgba(99,102,241,0.08)]'
      }`}
        style={{ background: 'rgba(8,8,20,0.7)', backdropFilter: 'blur(8px)' }}
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
          placeholder={!connected ? t('compact.input.waitingConnection') : isStreaming ? t('compact.input.waitingResponse') : t('compact.input.placeholder')}
          disabled={!connected || isStreaming}
          rows={1}
          className="flex-1 bg-transparent text-text-primary placeholder:text-text-muted/70 text-sm resize-none outline-none min-h-[28px] max-h-[120px] py-0.5 leading-relaxed disabled:cursor-not-allowed"
        />

        <div className="flex items-center gap-1 flex-shrink-0 pb-0.5">
          {!isStreaming && onUpload && (
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={!connected}
              className="w-7 h-7 rounded-lg flex items-center justify-center text-text-muted hover:text-text-secondary hover:bg-white/[0.05] transition-colors disabled:opacity-30"
              title={t('compact.input.attachFile')}
            >
              <Paperclip className="w-4 h-4" />
            </button>
          )}
          {isStreaming ? (
            <button
              onClick={onStop}
              className="w-8 h-8 rounded-full flex items-center justify-center bg-red-500/80 text-white hover:bg-red-500 transition-all hover:scale-105 active:scale-95 shadow-lg shadow-red-500/20"
              title={t('compact.input.stop')}
            >
              <Square className="w-3 h-3" fill="currentColor" />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim() || !connected}
              className="w-8 h-8 rounded-full flex items-center justify-center bg-gradient-to-r from-synapse to-pulse text-white shadow-lg shadow-synapse/20 disabled:opacity-30 disabled:cursor-not-allowed disabled:shadow-none hover:scale-105 active:scale-95 transition-all"
              title={t('compact.input.send')}
            >
              <ArrowUp className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
