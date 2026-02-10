import { useState, useEffect } from 'react'

const API_BASE =
  import.meta.env.DEV
    ? `http://${window.location.hostname}:5173/api/avatar`
    : `/api/avatar`

/**
 * Fetches available providers from the backend (checks CLI availability).
 * Returns null while loading (show all providers as fallback),
 * or a Set of available provider IDs once resolved.
 */
export function useAvailableProviders(): Set<string> | null {
  const [available, setAvailable] = useState<Set<string> | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/providers`)
      .then((r) => r.json())
      .then((data: Array<{ id: string; available: boolean }>) => {
        if (!cancelled) {
          setAvailable(new Set(data.filter((p) => p.available).map((p) => p.id)))
        }
      })
      .catch(() => {
        // If endpoint fails, null = show all (graceful fallback)
      })
    return () => { cancelled = true }
  }, [])

  return available
}
