/**
 * Predefined avatar configurations.
 *
 * Kokoro speakers: sprite sheet only (idle auto-extracted from frame[0]).
 * Astronaut: individual pose files, no speaking sprite sheet.
 */

import type { AvatarConfig } from '../types'

function kokoroAvatar(id: string, name: string): AvatarConfig {
  return {
    id,
    name,
    poses: { idle: 'auto', speaking: 'speaking.webp' },
    speakingFrames: 4,
    speakingFps: 8,
  }
}

export const AVATARS: AvatarConfig[] = [
  kokoroAvatar('af_bella', 'Bella'),
  kokoroAvatar('af_heart', 'Heart'),
  kokoroAvatar('af_nicole', 'Nicole'),
  kokoroAvatar('af_sky', 'Sky'),
  kokoroAvatar('am_adam', 'Adam'),
  kokoroAvatar('am_michael', 'Michael'),
  kokoroAvatar('bm_george', 'George'),
  {
    id: 'astronaut',
    name: 'Astronautka',
    poses: {
      idle: 'idle.webp',
      thinking: 'thinking.webp',
      error: 'error.webp',
    },
    speakingFrames: 0,
    speakingFps: 0,
  },
]

export const DEFAULT_AVATAR_ID = 'af_bella'

export function getAvatarById(id: string): AvatarConfig | undefined {
  return AVATARS.find((a) => a.id === id)
}

export function getAvatarBasePath(id: string): string {
  return `/avatars/${id}`
}
