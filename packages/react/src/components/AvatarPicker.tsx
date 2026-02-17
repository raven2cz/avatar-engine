/**
 * AvatarPicker — grid popup for selecting characters.
 *
 * Shows portrait thumbnails (48×72px) in a 3-column grid.
 * Renders top ~65% of character for face-focused thumbnail.
 * Click to switch avatar, closes on selection or outside click.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { AvatarConfig } from '@avatar-engine/core'
import { AVATARS, getAvatarBasePath } from '@avatar-engine/core'

interface AvatarPickerProps {
  selectedId: string
  onSelect: (id: string) => void
  onClose: () => void
}

function AvatarThumb({ avatar, selected, onSelect }: {
  avatar: AvatarConfig
  selected: boolean
  onSelect: () => void
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const basePath = getAvatarBasePath(avatar.id)
    const img = new Image()
    img.crossOrigin = 'anonymous'

    img.onload = () => {
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      // For sprite sheets, use first frame
      const frameW = avatar.speakingFrames > 0 ? img.width / avatar.speakingFrames : img.width
      const frameH = img.height

      // Crop top ~65% for face-focused portrait
      const cropH = Math.floor(frameH * 0.65)

      canvas.width = 48
      canvas.height = 72

      // Scale to fit 48×72 maintaining aspect ratio
      const scale = Math.max(48 / frameW, 72 / cropH)
      const drawW = frameW * scale
      const drawH = cropH * scale
      const dx = (48 - drawW) / 2
      const dy = 0 // top-aligned

      ctx.clearRect(0, 0, 48, 72)
      ctx.drawImage(img, 0, 0, frameW, cropH, dx, dy, drawW, drawH)
      setLoaded(true)
    }

    // Try idle first, then speaking
    if (avatar.poses.idle !== 'auto' && avatar.poses.idle) {
      img.src = `${basePath}/${avatar.poses.idle}`
    } else if (avatar.poses.speaking) {
      img.src = `${basePath}/${avatar.poses.speaking}`
    }
  }, [avatar.id])

  return (
    <button
      onClick={onSelect}
      className={`relative w-12 h-[72px] rounded-[10px] overflow-hidden cursor-pointer border-2 transition-all duration-200 ${
        selected
          ? 'border-synapse shadow-[0_0_12px_rgb(var(--ae-accent-rgb)_/_0.3)]'
          : 'border-transparent hover:border-synapse hover:scale-105'
      }`}
    >
      <canvas
        ref={canvasRef}
        width={48}
        height={72}
        className={`w-full h-full object-cover ${loaded ? 'opacity-100' : 'opacity-0'}`}
        style={{ transition: 'opacity 0.3s ease' }}
      />
      {!loaded && (
        <div className="absolute inset-0 bg-slate-mid/50 flex items-center justify-center">
          <div className="w-3 h-3 border border-synapse/40 border-t-synapse rounded-full animate-spin" />
        </div>
      )}
      <div className="absolute bottom-0 inset-x-0 bg-black/60 text-[0.45rem] text-text-secondary text-center py-px font-medium">
        {avatar.name}
      </div>
    </button>
  )
}

export function AvatarPicker({ selectedId, onSelect, onClose }: AvatarPickerProps) {
  const ref = useRef<HTMLDivElement>(null)

  const handleSelect = useCallback((id: string) => {
    onSelect(id)
    onClose()
  }, [onSelect, onClose])

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose()
      }
    }
    // Delay to avoid immediate close from the button click that opened us
    const timer = setTimeout(() => {
      document.addEventListener('mousedown', handleClick)
    }, 50)
    return () => {
      clearTimeout(timer)
      document.removeEventListener('mousedown', handleClick)
    }
  }, [onClose])

  // Close on Escape
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      }
    }
    document.addEventListener('keydown', handleKey, true)
    return () => document.removeEventListener('keydown', handleKey, true)
  }, [onClose])

  return (
    <div
      ref={ref}
      className="absolute bottom-[12%] left-[13px] z-[1003] p-2.5 rounded-[14px]
        bg-[rgba(12,12,20,0.92)] backdrop-blur-[24px] border border-white/[0.06]
        shadow-[0_12px_40px_rgba(0,0,0,0.5)]
        animate-fade-in"
      style={{ maxWidth: 220 }}
    >
      <div className="grid grid-cols-3 gap-2">
        {AVATARS.map((avatar) => (
          <AvatarThumb
            key={avatar.id}
            avatar={avatar}
            selected={avatar.id === selectedId}
            onSelect={() => handleSelect(avatar.id)}
          />
        ))}
      </div>
    </div>
  )
}
