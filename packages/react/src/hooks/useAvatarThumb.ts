/**
 * Generates a circular face-crop data URL from an avatar config.
 */

import { useEffect, useState } from 'react'
import type { AvatarConfig } from '@avatar-engine/core'
import { getAvatarBasePath } from '@avatar-engine/core'

/**
 * Generates a circular face-crop thumbnail data URL from an avatar configuration.
 *
 * Loads the avatar's idle pose (or first speaking frame), crops the upper half,
 * and renders it into a 72x72 circular canvas. Returns a WebP data URL suitable
 * for use as a FAB icon or avatar badge.
 *
 * @param avatar - Avatar configuration. Returns undefined if not provided.
 * @param avatarBasePath - Base URL path for avatar asset files (default: "/avatars").
 * @returns A WebP data URL string, or undefined while loading or on error.
 *
 * @example
 * ```tsx
 * const thumbUrl = useAvatarThumb(selectedAvatar, '/avatars');
 *
 * return thumbUrl
 *   ? <img src={thumbUrl} className="w-9 h-9 rounded-full" />
 *   : <DefaultIcon />;
 * ```
 */
export function useAvatarThumb(avatar: AvatarConfig | undefined, avatarBasePath: string = '/avatars'): string | undefined {
  const [thumbUrl, setThumbUrl] = useState<string | undefined>()

  useEffect(() => {
    if (!avatar) { setThumbUrl(undefined); return }

    let cancelled = false
    const basePath = getAvatarBasePath(avatar.id, avatarBasePath)

    const img = new Image()
    img.crossOrigin = 'anonymous'

    img.onerror = () => {
      if (!cancelled) setThumbUrl(undefined)
    }

    img.onload = () => {
      if (cancelled) return

      const frameW = avatar.speakingFrames > 0 ? img.width / avatar.speakingFrames : img.width
      const frameH = img.height

      const cropH = Math.floor(frameH * 0.5)

      const canvas = document.createElement('canvas')
      canvas.width = 72
      canvas.height = 72
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      ctx.beginPath()
      ctx.arc(36, 36, 36, 0, Math.PI * 2)
      ctx.closePath()
      ctx.clip()

      const scale = Math.max(72 / frameW, 72 / cropH)
      const drawW = frameW * scale
      const drawH = cropH * scale
      const dx = (72 - drawW) / 2
      const dy = (72 - drawH) / 2

      ctx.drawImage(img, 0, 0, frameW, cropH, dx, dy, drawW, drawH)

      setThumbUrl(canvas.toDataURL('image/webp', 0.8))
    }

    if (avatar.poses.idle !== 'auto' && avatar.poses.idle) {
      img.src = `${basePath}/${avatar.poses.idle}`
    } else if (avatar.poses.speaking) {
      img.src = `${basePath}/${avatar.poses.speaking}`
    }

    return () => {
      cancelled = true
      img.onload = null
      img.onerror = null
      img.src = ''
    }
  }, [avatar?.id, avatarBasePath])

  return thumbUrl
}
