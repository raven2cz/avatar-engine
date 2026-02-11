/**
 * Avatar bust hook — maps engineState to bust visual state,
 * handles sprite sheet frame extraction and ping-pong animation.
 *
 * Provides:
 *  - bustState: 'idle' | 'thinking' | 'speaking' | 'error'
 *  - currentFrame: ImageBitmap or null (the frame to render)
 *  - idlePose: ImageBitmap or null (static idle image)
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { AvatarConfig, BustState } from '../types/avatar'
import { getAvatarBasePath } from '../config/avatars'

interface LoadedPoses {
  idle: HTMLImageElement | null
  thinking: HTMLImageElement | null
  error: HTMLImageElement | null
  speakingFrames: HTMLCanvasElement[]  // extracted frames from sprite sheet
}

export interface UseAvatarBustReturn {
  bustState: BustState
  currentFrame: HTMLCanvasElement | HTMLImageElement | null
  loading: boolean
}

function engineStateToBustState(engineState: string): BustState {
  switch (engineState) {
    case 'thinking':
    case 'tool_executing':
      return 'thinking'
    case 'responding':
      return 'speaking'
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
  engineState: string
): UseAvatarBustReturn {
  const [loading, setLoading] = useState(true)
  const posesRef = useRef<LoadedPoses>({ idle: null, thinking: null, error: null, speakingFrames: [] })
  const [currentFrame, setCurrentFrame] = useState<HTMLCanvasElement | HTMLImageElement | null>(null)
  const animFrameRef = useRef(0)
  const animDirectionRef = useRef(1)
  const animIntervalRef = useRef<number>()

  const bustState = engineStateToBustState(engineState)

  // Load avatar assets
  useEffect(() => {
    if (!avatar) { setLoading(false); return }

    const basePath = getAvatarBasePath(avatar.id)
    let cancelled = false

    async function load() {
      setLoading(true)
      const poses: LoadedPoses = { idle: null, thinking: null, error: null, speakingFrames: [] }

      // Load speaking sprite sheet if present
      if (avatar!.poses.speaking) {
        try {
          const img = await loadImage(`${basePath}/${avatar!.poses.speaking}`)
          const frames = extractFrames(img, avatar!.speakingFrames || 4)
          poses.speakingFrames = frames
        } catch { /* no sprite sheet available */ }
      }

      // Load idle pose
      if (avatar!.poses.idle === 'auto') {
        // Idle = first frame of speaking sprite sheet
        // Already extracted above
      } else if (avatar!.poses.idle) {
        try {
          poses.idle = await loadImage(`${basePath}/${avatar!.poses.idle}`)
        } catch { /* fallback handled below */ }
      }

      // Load thinking pose if specified
      if (avatar!.poses.thinking) {
        try {
          poses.thinking = await loadImage(`${basePath}/${avatar!.poses.thinking}`)
        } catch { /* fallback to idle */ }
      }

      // Load error pose if specified
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
  }, [avatar?.id])

  // Get the idle pose (either dedicated image or frame[0] from sprite sheet)
  const getIdlePose = useCallback((): HTMLCanvasElement | HTMLImageElement | null => {
    const poses = posesRef.current
    if (poses.idle) return poses.idle
    if (poses.speakingFrames.length > 0) return poses.speakingFrames[0]
    return null
  }, [])

  // Get pose for current bust state (with fallback chain)
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
        // Speaking animation handled separately
        return getIdlePose()
      default:
        return getIdlePose()
    }
  }, [getIdlePose])

  // Update frame based on bust state
  useEffect(() => {
    // Clear any running animation
    if (animIntervalRef.current) {
      clearInterval(animIntervalRef.current)
      animIntervalRef.current = undefined
    }

    if (loading || !avatar) return

    const poses = posesRef.current

    if (bustState === 'speaking' && poses.speakingFrames.length > 1) {
      // Ping-pong animation through speaking frames (skip frame 0 = idle)
      const speakFrames = poses.speakingFrames.slice(1) // frames 1, 2, 3
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
      // Static pose
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
