/**
 * Shared utility functions.
 */

let messageIdCounter = 0

/** Generate a unique message ID. */
export function nextId(): string {
  return `msg-${++messageIdCounter}-${Date.now()}`
}

/** Summarize tool parameters for compact display. */
export function summarizeParams(params: Record<string, unknown>): string {
  const keys = ['file_path', 'path', 'filename', 'command', 'query', 'pattern', 'url']
  for (const key of keys) {
    if (params[key]) {
      const val = String(params[key])
      return val.length > 60 ? val.slice(0, 57) + '...' : val
    }
  }
  for (const val of Object.values(params)) {
    if (typeof val === 'string' && val) {
      return val.length > 60 ? val.slice(0, 57) + '...' : val
    }
  }
  return ''
}
