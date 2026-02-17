/**
 * Avatar bust hook — maps engineState to bust visual state,
 * handles sprite sheet frame extraction and ping-pong animation.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { AvatarConfig, BustState } from '@avatar-engine/core'
import { getAvatarBasePath } from '@avatar-engine/core'

interface LoadedPoses {
  idle: HTMLImageElement | null
  thinking: HTMLImageElement | null
  error: HTMLImageElement | null
  speakingFrames: HTMLCanvasElement[]
}

export interface UseAvatarBustReturn {
  bustState: BustState
  currentFrame: HTMLCanvasElement | HTMLImageElement | null
  loading: boolean
}

function engineStateToBustState(engineState: string, hasText: boolean): BustState {
  switch (engineState) {
    case 'thinking':
    case 'tool_executing':
      return 'thinking'
    case 'responding':
      return hasText ? 'speaking' : 'thinking'
    case 'error':
      return 'error'
    default:
      return 'idle'
  }
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error(`Failed to load: ${src}`))
    img.src = src
  })
}

function extractFrames(img: HTMLImageElement, frameCount: number): HTMLCanvasElement[] {
  const frameW = Math.floor(img.width / frameCount)
  const frameH = img.height
  const frames: HTMLCanvasElement[] = []

  for (let i = 0; i < frameCount; i++) {
    const canvas = document.createElement('canvas')
    canvas.width = frameW
    canvas.height = frameH
    const ctx = canvas.getContext('2d')!
    ctx.drawImage(img, i * frameW, 0, frameW, frameH, 0, 0, frameW, frameH)
    frames.push(canvas)
  }
  return frames
}

export function useAvatarBust(
  avatar: AvatarConfig | undefined,
  engineState: string,
  hasText: boolean = false,
  avatarBasePath: string = '/avatars',
): UseAvatarBustReturn {
  const [loading, setLoading] = useState(true)
  const posesRef = useRef<LoadedPoses>({ idle: null, thinking: null, error: null, speakingFrames: [] })
  const [currentFrame, setCurrentFrame] = useState<HTMLCanvasElement | HTMLImageElement | null>(null)
  const animFrameRef = useRef(0)
  const animDirectionRef = useRef(1)
  const animIntervalRef = useRef<number>()

  const bustState = engineStateToBustState(engineState, hasText)

  useEffect(() => {
    if (!avatar) { setLoading(false); return }

    const basePath = getAvatarBasePath(avatar.id, avatarBasePath)
    let cancelled = false

    async function load() {
      setLoading(true)
      const poses: LoadedPoses = { idle: null, thinking: null, error: null, speakingFrames: [] }

      if (avatar!.poses.speaking) {
        try {
          const img = await loadImage(`${basePath}/${avatar!.poses.speaking}`)
          const frames = extractFrames(img, avatar!.speakingFrames || 4)
          poses.speakingFrames = frames
        } catch { /* no sprite sheet available */ }
      }

      if (avatar!.poses.idle === 'auto') {
        // Idle = first frame of speaking sprite sheet
      } else if (avatar!.poses.idle) {
        try {
          poses.idle = await loadImage(`${basePath}/${avatar!.poses.idle}`)
        } catch { /* fallback handled below */ }
      }

      if (avatar!.poses.thinking) {
        try {
          poses.thinking = await loadImage(`${basePath}/${avatar!.poses.thinking}`)
        } catch { /* fallback to idle */ }
      }

      if (avatar!.poses.error) {
        try {
          poses.error = await loadImage(`${basePath}/${avatar!.poses.error}`)
        } catch { /* fallback to idle */ }
      }

      if (!cancelled) {
        posesRef.current = poses
        setLoading(false)
      }
    }

    load()
    return () => { cancelled = true }
  }, [avatar?.id, avatarBasePath])

  const getIdlePose = useCallback((): HTMLCanvasElement | HTMLImageElement | null => {
    const poses = posesRef.current
    if (poses.idle) return poses.idle
    if (poses.speakingFrames.length > 0) return poses.speakingFrames[0]
    return null
  }, [])

  const getPoseForState = useCallback((state: BustState): HTMLCanvasElement | HTMLImageElement | null => {
    const poses = posesRef.current
    switch (state) {
      case 'thinking':
        return poses.thinking || getIdlePose()
      case 'error':
        return poses.error || getIdlePose()
      case 'idle':
        return getIdlePose()
      case 'speaking':
        return getIdlePose()
      default:
        return getIdlePose()
    }
  }, [getIdlePose])

  useEffect(() => {
    if (animIntervalRef.current) {
      clearInterval(animIntervalRef.current)
      animIntervalRef.current = undefined
    }

    if (loading || !avatar) return

    const poses = posesRef.current

    if (bustState === 'speaking' && poses.speakingFrames.length > 1) {
      const speakFrames = poses.speakingFrames.slice(1)
      if (speakFrames.length === 0) {
        setCurrentFrame(getIdlePose())
        return
      }

      animFrameRef.current = 0
      animDirectionRef.current = 1
      const fps = avatar.speakingFps || 8
      const interval = 1000 / fps

      setCurrentFrame(speakFrames[0])

      animIntervalRef.current = window.setInterval(() => {
        let frame = animFrameRef.current + animDirectionRef.current
        if (frame >= speakFrames.length) {
          animDirectionRef.current = -1
          frame = speakFrames.length - 2
        } else if (frame < 0) {
          animDirectionRef.current = 1
          frame = 1
        }
        animFrameRef.current = frame
        setCurrentFrame(speakFrames[frame])
      }, interval)
    } else {
      setCurrentFrame(getPoseForState(bustState))
    }

    return () => {
      if (animIntervalRef.current) {
        clearInterval(animIntervalRef.current)
        animIntervalRef.current = undefined
      }
    }
  }, [bustState, loading, avatar?.id, getIdlePose, getPoseForState])

  return { bustState, currentFrame, loading }
}
