/**
 * Avatar GUI types — widget modes, bust states, avatar configuration.
 */

export type WidgetMode = 'fab' | 'compact' | 'fullscreen'

export type BustState = 'idle' | 'thinking' | 'speaking' | 'error'

export interface AvatarPoses {
  idle: string | 'auto'       // 'idle.webp' or 'auto' (= speaking frame[0])
  thinking?: string            // 'thinking.webp' — fallback to idle if missing
  error?: string               // 'error.webp' — fallback to idle if missing
  speaking?: string            // 'speaking.webp' — sprite sheet for mouth animation
}

export interface AvatarConfig {
  id: string
  name: string
  poses: AvatarPoses
  speakingFrames: number       // number of frames in sprite sheet (default 4)
  speakingFps: number          // speaking animation fps (default 8)
}

export interface CompactDimensions {
  width: number
  height: number
}

// localStorage keys
export const LS_BUST_VISIBLE = 'avatar-engine-bust-visible'
export const LS_WIDGET_MODE = 'avatar-engine-widget-mode'
export const LS_COMPACT_HEIGHT = 'avatar-engine-compact-height'
export const LS_COMPACT_WIDTH = 'avatar-engine-compact-width'
export const LS_SELECTED_AVATAR = 'avatar-engine-selected-avatar'
export const LS_HINTS_SHOWN = 'avatar-engine-hints-shown'
