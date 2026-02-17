/**
 * AvatarBust — renders the character bust with CSS state animations.
 *
 * Uses canvas/image from useAvatarBust hook.
 * Applies data-state attribute for CSS keyframe animations
 * (bust-breathe, bust-thinking, bust-speaking, bust-shake).
 */

import { useEffect, useRef } from 'react'
import type { AvatarConfig } from '@avatar-engine/core'
import { useAvatarBust } from '../hooks/useAvatarBust'

interface AvatarBustProps {
  avatar: AvatarConfig | undefined
  engineState: string
  /** True when the current assistant message has non-empty text content. */
  hasText?: boolean
  className?: string
}

export function AvatarBust({ avatar, engineState, hasText = false, className = '' }: AvatarBustProps) {
  const { bustState, currentFrame, loading } = useAvatarBust(avatar, engineState, hasText)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  // Render current frame to canvas
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !currentFrame) return

    const source = currentFrame
    const w = source instanceof HTMLCanvasElement ? source.width : source.naturalWidth
    const h = source instanceof HTMLCanvasElement ? source.height : source.naturalHeight

    // Set canvas dimensions to match source
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w
      canvas.height = h
    }

    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.clearRect(0, 0, w, h)
    ctx.drawImage(source, 0, 0)
  }, [currentFrame])

  if (!avatar || loading) {
    return (
      <div className={`flex items-center justify-center ${className}`}>
        <div className="w-8 h-8 border-2 border-synapse/30 border-t-synapse rounded-full animate-spin" />
      </div>
    )
  }

  if (!currentFrame) {
    return (
      <div className={`flex items-center justify-center ${className}`}>
        <span className="text-text-muted text-[0.6rem]">No avatar</span>
      </div>
    )
  }

  return (
    <div
      className={className}
      data-state={bustState}
    >
      <canvas
        ref={canvasRef}
        className="w-[200px] h-auto block"
        style={{
          filter: bustState === 'thinking'
            ? 'drop-shadow(0 0 18px rgb(var(--ae-accent-rgb) / 0.45)) drop-shadow(3px 3px 12px rgba(0,0,0,0.6))'
            : bustState === 'speaking'
            ? 'drop-shadow(0 0 22px rgb(var(--ae-pulse-rgb) / 0.45)) drop-shadow(3px 3px 12px rgba(0,0,0,0.6))'
            : bustState === 'error'
            ? 'drop-shadow(0 0 16px rgb(var(--ae-error-rgb) / 0.5)) drop-shadow(3px 3px 12px rgba(0,0,0,0.6))'
            : 'drop-shadow(3px 3px 12px rgba(0,0,0,0.6))',
          transition: 'filter 0.5s ease',
        }}
      />
    </div>
  )
}
