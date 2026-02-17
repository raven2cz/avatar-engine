import { useState, useEffect } from 'react'

/**
 * Fetches available AI providers from the backend.
 *
 * Returns `null` while loading or on error (graceful fallback: show all providers).
 * Once loaded, returns a `Set` of provider IDs that are available on the server.
 *
 * @param apiBase - REST API base URL (default: "/api/avatar").
 * @returns A Set of available provider IDs, or null while loading.
 *
 * @example
 * ```tsx
 * const available = useAvailableProviders('/api/avatar');
 *
 * // null = still loading, show all providers
 * // Set = filter provider list to only available ones
 * const providers = available
 *   ? ALL_PROVIDERS.filter(p => available.has(p.id))
 *   : ALL_PROVIDERS;
 * ```
 */
export function useAvailableProviders(apiBase?: string): Set<string> | null {
  const resolvedApiBase = apiBase ?? '/api/avatar'

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
