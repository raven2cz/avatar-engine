import { useState, useEffect } from 'react'
import type { ProviderConfig } from '@avatar-engine/core'
import { PROVIDERS, createProviders } from '@avatar-engine/core'

const LS_KEY = 'avatar-engine-dynamic-models'

interface ProviderModels {
  models: string[]
  defaultModel: string
  source?: string
  legacyModels?: string[]
}

type ModelsResponse = Record<string, ProviderModels> & {
  errors?: Record<string, string>
  fetched_at?: string
}

/**
 * Hook that fetches dynamic model lists from the backend.
 *
 * Three-tier fallback:
 * 1. Static PROVIDERS from providers.ts (immediate)
 * 2. localStorage cache from last successful fetch (< 1ms, 24h TTL)
 * 3. Backend scraping via GET /api/avatar/models (background)
 *
 * When scraping fails for a provider, emits `avatar-engine:model-error`
 * CustomEvent on window. Use {@link useModelDiscoveryErrors} to display them.
 *
 * @param apiBase - REST API base URL (default: '/api/avatar')
 */
export function useDynamicModels(apiBase?: string): ProviderConfig[] {
  const resolvedBase = apiBase ?? '/api/avatar'

  const [providers, setProviders] = useState<ProviderConfig[]>(() => {
    // Tier 2: Try localStorage cache
    try {
      const cached = localStorage.getItem(LS_KEY)
      if (cached) {
        const { data, ts } = JSON.parse(cached)
        if (Date.now() - ts < 86_400_000) {
          return createProviders(data)
        }
      }
    } catch { /* ignore */ }
    // Tier 1: Static fallback
    return PROVIDERS
  })

  useEffect(() => {
    let cancelled = false
    fetch(`${resolvedBase}/models`)
      .then(r => r.ok ? r.json() : null)
      .then((data: ModelsResponse | null) => {
        if (cancelled || !data) return

        // Report errors for failed providers
        if (data.errors) {
          for (const [provider, msg] of Object.entries(data.errors)) {
            window.dispatchEvent(new CustomEvent('avatar-engine:model-error', {
              detail: {
                provider,
                message: `Model list for ${provider} may be outdated. Parser update needed.`,
                error: msg,
              },
            }))
          }
        }

        // Apply successful overrides
        const overrides: Record<string, Partial<Pick<ProviderConfig, 'defaultModel' | 'models'>>> = {}
        for (const [id, info] of Object.entries(data)) {
          if (id === 'fetched_at' || id === 'errors') continue
          if (typeof info === 'object' && info !== null && 'models' in info) {
            const pm = info as ProviderModels
            if (pm.models?.length) {
              overrides[id] = { models: pm.models, defaultModel: pm.defaultModel }
            }
          }
        }

        if (Object.keys(overrides).length > 0) {
          setProviders(createProviders(overrides))
          localStorage.setItem(LS_KEY, JSON.stringify({
            data: overrides,
            ts: Date.now(),
          }))
        }
      })
      .catch(() => { /* keep static/cached — network error */ })
    return () => { cancelled = true }
  }, [resolvedBase])

  return providers
}
