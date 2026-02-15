import { useState, useEffect } from 'react'

/**
 * Fetches available providers from the backend.
 * Returns null while loading, or a Set of available provider IDs.
 */
export function useAvailableProviders(apiBase?: string): Set<string> | null {
  const resolvedApiBase = apiBase ?? (() => {
    if (typeof window !== 'undefined' && import.meta.env?.DEV) {
      return `http://${window.location.hostname}:5173/api/avatar`
    }
    return '/api/avatar'
  })()

  const [available, setAvailable] = useState<Set<string> | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch(`${resolvedApiBase}/providers`)
      .then((r) => r.json())
      .then((data: Array<{ id: string; available: boolean }>) => {
        if (!cancelled) {
          setAvailable(new Set(data.filter((p) => p.available).map((p) => p.id)))
        }
      })
      .catch(() => {
        // null = show all (graceful fallback)
      })
    return () => { cancelled = true }
  }, [resolvedApiBase])

  return available
}
