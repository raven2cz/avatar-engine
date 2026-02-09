/**
 * Chat panel — message list with auto-scroll + input.
 *
 * Glassmorphism container, gradient input bar, Enter-to-send.
 * Shows breathing orb as empty state.
 * Stop button replaces Send during streaming.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowUp, Square, Trash2 } from 'lucide-react'
import type { ChatMessage } from '../api/types'
import { MessageBubble } from './MessageBubble'
import { BreathingOrb } from './BreathingOrb'

interface ChatPanelProps {
  messages: ChatMessage[]
  onSend: (message: string) => void
  onStop: () => void
  onClear: () => void
  isStreaming: boolean
  connected: boolean
}

export function ChatPanel({ messages, onSend, onStop, onClear, isStreaming, connected }: ChatPanelProps) {
  const [input, setInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

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
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-6 py-4 scroll-smooth">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-6 animate-fade-in">
            <BreathingOrb size="lg" phase="general" />
            <div className="text-center">
              <h2 className="text-xl font-semibold gradient-text mb-2">Avatar Engine</h2>
              <p className="text-text-secondary text-sm max-w-sm">
                AI-powered assistant ready to help. Type a message to start.
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
                Clear
              </button>
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
            <textarea
              ref={inputRef}
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              placeholder={
                !connected
                  ? 'Connecting...'
                  : isStreaming
                  ? 'Waiting for response...'
                  : 'Type your message...'
              }
              disabled={!connected || isStreaming}
              rows={1}
              className="w-full bg-transparent text-text-primary placeholder:text-text-muted
                text-sm px-4 py-3 pr-12 resize-none outline-none
                disabled:cursor-not-allowed"
            />

            {/* Send / Stop button */}
            {isStreaming ? (
              <button
                onClick={onStop}
                className="absolute right-2 bottom-2 w-8 h-8 rounded-xl
                  flex items-center justify-center transition-all duration-200
                  bg-red-500/80 text-white
                  shadow-lg shadow-red-500/25
                  hover:bg-red-500 hover:shadow-xl hover:shadow-red-500/30 hover:scale-105
                  active:scale-95"
                title="Stop response"
              >
                <Square className="w-3.5 h-3.5" fill="currentColor" />
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!input.trim() || !connected}
                className="absolute right-2 bottom-2 w-8 h-8 rounded-xl
                  flex items-center justify-center transition-all duration-200
                  disabled:opacity-30 disabled:cursor-not-allowed
                  bg-gradient-to-r from-synapse to-pulse text-white
                  shadow-lg shadow-synapse/25
                  hover:shadow-xl hover:shadow-synapse/30 hover:scale-105
                  active:scale-95"
              >
                <ArrowUp className="w-4 h-4" />
              </button>
            )}
          </div>

          <p className="text-center text-xs text-text-muted mt-2">
            Press <kbd className="px-1.5 py-0.5 rounded bg-slate-dark border border-slate-mid/50 text-text-secondary">Enter</kbd> to send, <kbd className="px-1.5 py-0.5 rounded bg-slate-dark border border-slate-mid/50 text-text-secondary">Shift+Enter</kbd> for new line
          </p>
        </div>
      </div>
    </div>
  )
}
