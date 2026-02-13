/**
 * Compact mode message list — smaller fonts, avatars, and padding.
 * Shows tool names + thinking phase for event visibility.
 */

import { useEffect, useRef } from 'react'
import { User } from 'lucide-react'
import type { ChatMessage } from '../api/types'
import { MarkdownContent } from './MarkdownContent'
import { BreathingOrb } from './BreathingOrb'
import { AvatarLogo } from './AvatarLogo'

interface CompactMessagesProps {
  messages: ChatMessage[]
  version?: string | null
}

function CompactBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'
  const activeTool = message.tools.find((t) => t.status === 'started')

  return (
    <div className={`flex gap-2 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      {/* Avatar icon — sized to match a single line of text */}
      <div
        className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center mt-[1px] ${
          isUser
            ? 'bg-gradient-to-br from-synapse to-pulse text-white'
            : 'bg-synapse/15 border border-synapse/25 text-synapse'
        }`}
      >
        {isUser ? <User className="w-3 h-3" /> : <AvatarLogo className="w-4 h-4" />}
      </div>

      {/* Message body */}
      <div className={`max-w-[85%] min-w-0 ${isUser ? 'text-right' : 'text-left'}`}>
        <div
          className={`inline-block rounded-xl px-2.5 py-1.5 text-left ${
            isUser
              ? 'bg-gradient-to-r from-synapse/15 to-pulse/15 border border-synapse/15'
              : 'bg-slate-mid/40 border border-slate-mid/20'
          }`}
        >
          {/* Thinking indicator — shows phase + subject for visibility */}
          {message.thinking && !message.thinking.isComplete && (
            <div className="flex items-center gap-1.5 py-0.5">
              <span className="text-[0.65rem] text-synapse font-medium">
                {message.thinking.phase && message.thinking.phase !== 'general'
                  ? message.thinking.phase.charAt(0).toUpperCase() + message.thinking.phase.slice(1)
                  : 'Thinking'}
              </span>
              {message.thinking.subject && (
                <span className="text-[0.6rem] text-text-muted truncate max-w-[180px]">
                  {message.thinking.subject}
                </span>
              )}
              <div className="flex gap-0.5 flex-shrink-0">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="w-1 h-1 rounded-full bg-synapse animate-pulse"
                    style={{ animationDelay: `${i * 0.15}s` }}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Tool display — shows active tool name + params for visibility */}
          {message.tools.length > 0 && (
            <div className="text-[0.6rem] text-neural mb-0.5 space-y-0.5">
              {activeTool ? (
                <div className="flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-neural animate-pulse flex-shrink-0" />
                  <span className="font-medium">{activeTool.name}</span>
                  {activeTool.params && (
                    <span className="text-text-muted truncate max-w-[180px]">{activeTool.params}</span>
                  )}
                </div>
              ) : (
                <div className="flex items-center gap-1">
                  <svg className="w-2.5 h-2.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" d="M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l5.652-4.655M17.5 6.5l-1 1" />
                    <path d="M15.5 8.5l4.586-4.586a2 2 0 0 1 2.828 2.828L18.33 11.41" />
                  </svg>
                  <span>{message.tools.length} tool{message.tools.length > 1 ? 's' : ''} used</span>
                </div>
              )}
            </div>
          )}

          {/* Text content */}
          {message.content && (
            <div className="text-[0.75rem] leading-relaxed text-text-primary break-words compact-markdown">
              {isUser ? (
                <div className="whitespace-pre-wrap">{message.content}</div>
              ) : (
                <MarkdownContent content={message.content} />
              )}
            </div>
          )}

          {/* Streaming cursor */}
          {message.isStreaming && !message.content && !message.thinking && (
            <div className="flex items-center gap-1 py-0.5">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="w-1 h-1 rounded-full bg-synapse animate-pulse"
                  style={{ animationDelay: `${i * 0.15}s` }}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function CompactMessages({ messages, version }: CompactMessagesProps) {
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="compact-messages flex-1 min-h-0 overflow-y-auto px-3 py-2 flex flex-col gap-1.5 scroll-smooth">
      {messages.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="flex flex-col items-center gap-3 animate-fade-in">
            <BreathingOrb size="sm" phase="general" />
            <div className="text-center">
              <h3 className="text-sm font-semibold gradient-text mb-0.5">
                Avatar Engine
                {version && <span className="text-[0.6rem] text-text-muted/60 font-mono font-normal ml-1.5">v{version}</span>}
              </h3>
              <p className="text-[0.65rem] text-text-muted max-w-[200px]">
                Ready to help. Type a message below.
              </p>
            </div>
          </div>
        </div>
      ) : (
        messages.map((msg) => <CompactBubble key={msg.id} message={msg} />)
      )}
      <div ref={endRef} />
    </div>
  )
}
