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

/** Registry of all available avatar configurations. */
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

/** Default avatar identifier used when no preference is set. */
export const DEFAULT_AVATAR_ID = 'af_bella'

/**
 * Look up an avatar configuration by its identifier.
 *
 * @param id - Avatar identifier (e.g. "af_bella", "astronaut").
 * @returns The matching avatar config, or undefined if not found.
 */
export function getAvatarById(id: string): AvatarConfig | undefined {
  return AVATARS.find((a) => a.id === id)
}

/**
 * Construct the base asset path for an avatar's image files.
 *
 * @param id - Avatar identifier.
 * @param basePath - Root avatars directory (defaults to "/avatars").
 * @returns Full path to the avatar's asset directory (e.g. "/avatars/af_bella").
 */
export function getAvatarBasePath(id: string, basePath: string = '/avatars'): string {
  return `${basePath}/${id}`
}
