import { useState, useEffect } from 'react'

export interface ModelDiscoveryError {
  provider: string
  message: string
  error: string
}

/**
 * Hook that listens for model discovery errors.
 *
 * When {@link useDynamicModels} detects scraping failures,
 * it emits `avatar-engine:model-error` CustomEvents on window.
 * This hook collects them for display in the UI.
 *
 * @example
 * ```tsx
 * const errors = useModelDiscoveryErrors()
 *
 * {errors.length > 0 && (
 *   <Toast type="warning">
 *     {errors.map(e => e.message).join('; ')}
 *   </Toast>
 * )}
 * ```
 */
export function useModelDiscoveryErrors(): ModelDiscoveryError[] {
  const [errors, setErrors] = useState<ModelDiscoveryError[]>([])

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<ModelDiscoveryError>).detail
      setErrors(prev => [...prev, detail])
    }
    window.addEventListener('avatar-engine:model-error', handler)
    return () => window.removeEventListener('avatar-engine:model-error', handler)
  }, [])

  return errors
}
