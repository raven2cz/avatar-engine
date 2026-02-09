/**
 * Chat message bubble — user (right, gradient) / assistant (left, glass).
 *
 * Supports streaming state, tool activity display, thinking info,
 * cost/duration metadata, and formatted text content.
 */

import { User } from 'lucide-react'
import type { ChatMessage } from '../api/types'
import { ThinkingIndicator } from './ThinkingIndicator'
import { ToolActivity } from './ToolActivity'
import { MarkdownContent } from './MarkdownContent'
import { AvatarLogo } from './AvatarLogo'

interface MessageBubbleProps {
  message: ChatMessage
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'

  return (
    <div
      className={`flex gap-3 animate-slide-up ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
    >
      {/* Avatar — aligned to top of message */}
      <div
        className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center mt-1 ${
          isUser
            ? 'bg-gradient-to-br from-synapse to-pulse'
            : 'bg-slate-dark border border-slate-mid/50'
        }`}
      >
        {isUser ? (
          <User className="w-5 h-5 text-white" />
        ) : (
          <AvatarLogo className="w-7 h-7" />
        )}
      </div>

      {/* Message body */}
      <div className={`flex-1 max-w-[80%] ${isUser ? 'items-end' : 'items-start'}`}>
        <div
          className={`rounded-2xl px-4 py-3 ${
            isUser
              ? 'bg-gradient-to-r from-synapse/20 to-pulse/20 border border-synapse/20'
              : 'glass border border-slate-mid/30'
          }`}
        >
          {/* Thinking indicator */}
          {message.thinking && !message.thinking.isComplete && (
            <ThinkingIndicator
              active={!message.thinking.isComplete}
              phase={message.thinking.phase}
              subject={message.thinking.subject}
              startedAt={message.thinking.startedAt}
            />
          )}

          {/* Tool activity */}
          {message.tools.length > 0 && <ToolActivity tools={message.tools} />}

          {/* Text content */}
          {message.content && (
            <div className="text-sm text-text-primary break-words">
              {isUser ? (
                <div className="whitespace-pre-wrap">{message.content}</div>
              ) : (
                <MarkdownContent content={message.content} />
              )}
            </div>
          )}

          {/* Streaming cursor */}
          {message.isStreaming && !message.content && !message.thinking && (
            <div className="flex items-center gap-1.5 py-1">
              <div className="w-1.5 h-1.5 rounded-full bg-synapse animate-pulse" />
              <div className="w-1.5 h-1.5 rounded-full bg-pulse animate-pulse" style={{ animationDelay: '0.15s' }} />
              <div className="w-1.5 h-1.5 rounded-full bg-neural animate-pulse" style={{ animationDelay: '0.3s' }} />
            </div>
          )}
        </div>

        {/* Metadata line */}
        {!message.isStreaming && message.role === 'assistant' && (message.durationMs || message.costUsd) && (
          <div className="flex items-center gap-3 mt-1 px-1">
            {message.durationMs !== undefined && (
              <span className="text-xs text-text-muted">
                {(message.durationMs / 1000).toFixed(1)}s
              </span>
            )}
            {message.costUsd !== undefined && message.costUsd > 0 && (
              <span className="text-xs text-text-muted">${message.costUsd.toFixed(4)}</span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
