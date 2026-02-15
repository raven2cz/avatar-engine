/**
 * Chat panel — message list with auto-scroll + input.
 *
 * Glassmorphism container, gradient input bar, Enter-to-send.
 * Shows breathing orb as empty state.
 * Stop button replaces Send during streaming.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowUp, FileText, Image, Paperclip, Square, Trash2, X } from 'lucide-react'
import type { ChatMessage, UploadedFile } from '@avatar-engine/core'
import { MessageBubble } from './MessageBubble'
import { BreathingOrb } from './BreathingOrb'

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

interface ChatPanelProps {
  messages: ChatMessage[]
  onSend: (message: string) => void
  onStop: () => void
  onClear: () => void
  isStreaming: boolean
  connected: boolean
  pendingFiles?: UploadedFile[]
  uploading?: boolean
  onUpload?: (file: File) => Promise<unknown>
  onRemoveFile?: (fileId: string) => void
}

export function ChatPanel({ messages, onSend, onStop, onClear, isStreaming, connected, pendingFiles = [], uploading = false, onUpload, onRemoveFile }: ChatPanelProps) {
  const { t } = useTranslation()
  const [input, setInput] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // Drag & drop handler
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    if (!onUpload) return
    const files = Array.from(e.dataTransfer.files)
    files.forEach((f) => onUpload(f))
  }, [onUpload])

  // Paste handler (Ctrl+V images)
  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    if (!onUpload) return
    const items = Array.from(e.clipboardData.items)
    for (const item of items) {
      if (item.kind === 'file') {
        const file = item.getAsFile()
        if (file) {
          e.preventDefault()
          onUpload(file)
          return
        }
      }
    }
  }, [onUpload])

  const handleSend = useCallback(() => {
    const trimmed = input.trim()
    if (!trimmed || isStreaming || !connected) return
    onSend(trimmed)
    setInput('')
    // Reset textarea height
    if (inputRef.current) {
      inputRef.current.style.height = 'auto'
    }
  }, [input, isStreaming, connected, onSend])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Auto-resize textarea
  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 200) + 'px'
  }

  return (
    <div
      className="flex flex-col h-full relative"
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      {/* Drop overlay */}
      {dragOver && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-slate-dark/80 border-2 border-dashed border-synapse/50 rounded-lg">
          <div className="text-center">
            <Paperclip className="w-10 h-10 text-synapse mx-auto mb-2" />
            <p className="text-text-primary font-medium">{t('fullscreen.chat.dropFiles')}</p>
            <p className="text-text-muted text-sm">{t('fullscreen.chat.dropHint')}</p>
          </div>
        </div>
      )}

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-6 py-4 scroll-smooth">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-6 animate-fade-in">
            <BreathingOrb size="lg" phase="general" />
            <div className="text-center">
              <h2 className="text-xl font-semibold gradient-text mb-2">{t('fullscreen.chat.title')}</h2>
              <p className="text-text-secondary text-sm max-w-sm">
                {t('fullscreen.chat.subtitle')}
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-4 max-w-4xl mx-auto">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input area */}
      <div className="px-6 pb-6 pt-2">
        <div className="max-w-4xl mx-auto">
          {/* Clear button */}
          {messages.length > 0 && !isStreaming && (
            <div className="flex justify-center mb-2">
              <button
                onClick={onClear}
                className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs
                  text-text-muted hover:text-red-400 hover:bg-red-500/10
                  border border-transparent hover:border-red-500/20
                  transition-all duration-200"
              >
                <Trash2 className="w-3 h-3" />
                {t('fullscreen.chat.clear')}
              </button>
            </div>
          )}

          {/* Pending attachments preview */}
          {pendingFiles.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2">
              {pendingFiles.map((f) => (
                <div
                  key={f.fileId}
                  className="relative group rounded-xl bg-slate-dark/50 border border-slate-mid/30 overflow-hidden"
                >
                  {f.mimeType.startsWith('image/') && f.previewUrl ? (
                    <div className="relative">
                      <img
                        src={f.previewUrl}
                        alt={f.filename}
                        className="max-h-32 max-w-48 min-w-16 min-h-12 object-cover rounded-xl"
                      />
                      <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/70 to-transparent px-2 py-1">
                        <div className="flex items-center gap-1 text-[10px] text-white/80">
                          <span className="truncate max-w-[120px]">{f.filename}</span>
                          <span className="text-white/50 flex-shrink-0">{formatSize(f.size)}</span>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 px-3 py-2">
                      <FileText className="w-5 h-5 text-amber-400 flex-shrink-0" />
                      <div className="min-w-0">
                        <div className="text-xs text-text-secondary truncate max-w-[160px]">{f.filename}</div>
                        <div className="text-[10px] text-text-muted">{formatSize(f.size)}</div>
                      </div>
                    </div>
                  )}
                  {onRemoveFile && (
                    <button
                      onClick={() => onRemoveFile(f.fileId)}
                      className="absolute top-1 right-1 w-5 h-5 rounded-full bg-black/60 flex items-center justify-center
                        text-white/70 hover:text-red-400 hover:bg-black/80 transition-colors
                        opacity-0 group-hover:opacity-100"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  )}
                </div>
              ))}
              {uploading && (
                <div className="flex items-center gap-1.5 px-3 py-2 text-xs text-text-muted">
                  <div className="w-3 h-3 border-2 border-synapse/50 border-t-synapse rounded-full animate-spin" />
                  {t('fullscreen.chat.uploading')}
                </div>
              )}
            </div>
          )}

          {/* Input container */}
          <div
            className={`relative glass rounded-2xl border transition-all duration-200 ${
              !connected
                ? 'border-red-500/30 opacity-50'
                : isStreaming
                ? 'border-synapse/30'
                : 'border-slate-mid/50 focus-within:border-synapse/50 focus-within:shadow-lg focus-within:shadow-synapse/5'
            }`}
          >
            {/* Hidden file input */}
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
              placeholder={
                !connected
                  ? t('fullscreen.chat.connecting')
                  : isStreaming
                  ? t('fullscreen.chat.waitingResponse')
                  : t('fullscreen.chat.placeholder')
              }
              disabled={!connected || isStreaming}
              rows={1}
              className="w-full bg-transparent text-text-primary placeholder:text-text-muted
                text-sm px-4 py-3 pr-20 resize-none outline-none
                disabled:cursor-not-allowed"
            />

            {/* Attach + Send / Stop buttons */}
            <div className="absolute right-2 bottom-2 flex items-center gap-1">
              {!isStreaming && onUpload && (
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={!connected}
                  className="w-8 h-8 rounded-xl flex items-center justify-center transition-all duration-200
                    text-text-muted hover:text-text-secondary hover:bg-slate-mid/30
                    disabled:opacity-30 disabled:cursor-not-allowed"
                  title={t('fullscreen.chat.attachFile')}
                >
                  <Paperclip className="w-4 h-4" />
                </button>
              )}
              {isStreaming ? (
                <button
                  onClick={onStop}
                  className="w-8 h-8 rounded-xl flex items-center justify-center transition-all duration-200
                    bg-red-500/80 text-white shadow-lg shadow-red-500/25
                    hover:bg-red-500 hover:shadow-xl hover:shadow-red-500/30 hover:scale-105 active:scale-95"
                  title={t('fullscreen.chat.stopResponse')}
                >
                  <Square className="w-3.5 h-3.5" fill="currentColor" />
                </button>
              ) : (
                <button
                  onClick={handleSend}
                  disabled={!input.trim() || !connected}
                  className="w-8 h-8 rounded-xl flex items-center justify-center transition-all duration-200
                    disabled:opacity-30 disabled:cursor-not-allowed
                    bg-gradient-to-r from-synapse to-pulse text-white
                    shadow-lg shadow-synapse/25 hover:shadow-xl hover:shadow-synapse/30 hover:scale-105 active:scale-95"
                >
                  <ArrowUp className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>

          <p className="text-center text-xs text-text-muted mt-2">
            <kbd className="px-1.5 py-0.5 rounded bg-slate-dark border border-slate-mid/50 text-text-secondary">Enter</kbd> {t('fullscreen.chat.enterToSend')}, <kbd className="px-1.5 py-0.5 rounded bg-slate-dark border border-slate-mid/50 text-text-secondary">Shift+Enter</kbd> {t('fullscreen.chat.shiftEnterNewLine')}
          </p>
        </div>
      </div>
    </div>
  )
}
