/**
 * Provider & Model selector dropdown.
 *
 * Triggered by clicking the provider badge + model area in StatusBar.
 * Shows provider rows with colored badges and model suggestions per provider.
 *
 * Provider/model lists are configured in `src/config/providers.ts`.
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, Loader2 } from 'lucide-react'
import { PROVIDERS, getModelDisplayName, filterChoicesForModel } from '@avatar-engine/core'
import type { ProviderConfig, ProviderOption } from '@avatar-engine/core'
import { OptionControl } from './OptionControl'
import { SafetyModeSelector } from './SafetyModeSelector'
import type { SafetyMode } from '@avatar-engine/core'

export interface ProviderModelSelectorProps {
  currentProvider: string
  currentModel: string | null
  switching: boolean
  activeOptions?: Record<string, string | number>
  availableProviders?: Set<string> | null
  onSwitch: (provider: string, model?: string, options?: Record<string, string | number>) => void
  /** Custom provider list — overrides built-in PROVIDERS (order = priority) */
  customProviders?: import('@avatar-engine/core').ProviderConfig[]
}

export function ProviderModelSelector({
  currentProvider,
  currentModel,
  switching,
  activeOptions = {},
  availableProviders,
  onSwitch,
  customProviders,
}: ProviderModelSelectorProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [selectedProvider, setSelectedProvider] = useState(currentProvider)
  const [customModel, setCustomModel] = useState('')
  const [optionValues, setOptionValues] = useState<Record<string, string | number>>({})
  const safetyFromOptions = (activeOptions.safety_mode as SafetyMode | undefined) ?? 'safe'
  const [safetyMode, setSafetyMode] = useState<SafetyMode>(safetyFromOptions)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Sync selected provider + options when current changes (after switch completes)
  useEffect(() => {
    setSelectedProvider(currentProvider)
    setOptionValues(activeOptions)
    setSafetyMode((activeOptions.safety_mode as SafetyMode | undefined) ?? 'safe')
  }, [currentProvider, activeOptions])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open])

  // Close on click outside
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  // Provider list — custom or built-in (must be before lookup helpers)
  const providerList = customProviders ?? PROVIDERS
  const visibleProviders = availableProviders
    ? providerList.filter((p) => availableProviders.has(p.id))
    : providerList

  // Local lookup helpers — search providerList, not global PROVIDERS
  const findProvider = (id: string): ProviderConfig | undefined =>
    providerList.find((p) => p.id === id)
  const findModels = (id: string): string[] =>
    findProvider(id)?.models ?? []
  const findOptions = (id: string): ProviderOption[] =>
    findProvider(id)?.options ?? []

  const handleProviderClick = useCallback((providerId: string) => {
    setSelectedProvider(providerId)
    setCustomModel('')
    // Restore active options if switching back to current provider, else reset
    setOptionValues(providerId === currentProvider ? activeOptions : {})
  }, [currentProvider, activeOptions])

  /** Sanitize option values for a target model: reset choices invalid for that model. */
  const sanitizeOptions = useCallback((model: string) => {
    const opts = findOptions(selectedProvider)
    const sanitized = { ...optionValues }
    for (const opt of opts) {
      // Remove hidden options entirely (e.g. thinking_level for image models)
      if (opt.hideForModelPattern && new RegExp(opt.hideForModelPattern, 'i').test(model)) {
        delete sanitized[opt.key]
        continue
      }
      if (opt.type !== 'select' || !opt.choices) continue
      const valid = filterChoicesForModel(opt.choices, model)
      if (sanitized[opt.key] !== undefined && !valid.some((c) => c.value === String(sanitized[opt.key]))) {
        sanitized[opt.key] = opt.defaultValue as string | number
      }
    }
    // Always include safety_mode
    sanitized.safety_mode = safetyMode as unknown as string | number
    return Object.keys(sanitized).length > 0 ? sanitized : undefined
  }, [selectedProvider, optionValues, safetyMode])

  const handleModelClick = useCallback((model: string) => {
    onSwitch(selectedProvider, model, sanitizeOptions(model))
    setOpen(false)
    setCustomModel('')
  }, [selectedProvider, onSwitch, sanitizeOptions])

  const handleCustomSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault()
    const model = customModel.trim()
    if (model) {
      onSwitch(selectedProvider, model, sanitizeOptions(model))
      setOpen(false)
      setCustomModel('')
    }
  }, [selectedProvider, customModel, onSwitch, sanitizeOptions])

  const handleOptionChange = useCallback((key: string, value: string | number) => {
    setOptionValues((prev) => ({ ...prev, [key]: value }))
  }, [])

  const providerConfig = findProvider(currentProvider)
  const selectedConfig = findProvider(selectedProvider)
  const models = findModels(selectedProvider)
  const providerOptions = findOptions(selectedProvider)
  const { modelName: displayModel, featuredLabel } = getModelDisplayName(
    currentProvider, currentModel, providerConfig?.defaultModel, activeOptions,
  )
  // Model used to filter model-specific option choices (e.g. thinking levels)
  const effectiveModel = (selectedProvider === currentProvider ? currentModel : null)
    || selectedConfig?.defaultModel || null

  // Apply options change without switching model (re-apply current provider+model)
  const handleApplyOptions = useCallback(() => {
    const model = effectiveModel || selectedConfig?.defaultModel || undefined
    if (model) {
      onSwitch(selectedProvider, model, sanitizeOptions(model))
      setOpen(false)
    }
  }, [selectedProvider, effectiveModel, selectedConfig, onSwitch, sanitizeOptions])

  // Detect if options differ from currently active ones
  const optionsDirty = selectedProvider === currentProvider && (() => {
    const opts = findOptions(selectedProvider)
    for (const opt of opts) {
      const current = activeOptions[opt.key] ?? opt.defaultValue
      const local = optionValues[opt.key] ?? opt.defaultValue
      if (String(current) !== String(local)) return true
    }
    // Check safety mode change
    const currentSafety = (activeOptions.safety_mode as SafetyMode | undefined) ?? 'safe'
    if (currentSafety !== safetyMode) return true
    return false
  })()

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Trigger: provider badge + model + chevron */}
      <button
        onClick={() => !switching && setOpen(!open)}
        disabled={switching}
        className="flex items-center gap-2 rounded-lg px-1 py-0.5 hover:bg-slate-mid/30 transition-colors disabled:opacity-60"
      >
        {switching ? (
          <div className="flex items-center gap-2 px-2.5 py-1 rounded-lg text-xs font-medium bg-gradient-to-r from-synapse/20 to-pulse/20 border border-synapse/40">
            <Loader2 className="w-3 h-3 animate-spin" />
            {t('provider.switching')}
          </div>
        ) : (
          <>
            {providerConfig && (
              <div className={`px-2.5 py-1 rounded-lg text-xs font-medium bg-gradient-to-r ${providerConfig.gradient} border`}>
                {providerConfig.label}
              </div>
            )}
            {displayModel && (
              <span className="text-xs text-text-secondary font-mono truncate max-w-[200px]">
                {displayModel}
                {featuredLabel && (
                  <span className="text-text-muted font-sans"> ({featuredLabel})</span>
                )}
              </span>
            )}
            <ChevronDown className="w-3 h-3 text-text-muted" />
          </>
        )}
      </button>

      {/* Dropdown */}
      {open && !switching && (
        <div className="absolute top-full left-0 mt-2 z-50 w-72 glass-panel rounded-xl border border-slate-mid/40 shadow-2xl shadow-black/60 animate-slide-up">
          {/* Provider section */}
          <div className="px-3 pt-3 pb-2">
            <span className="text-xs text-text-muted uppercase tracking-wide">{t('provider.label')}</span>
          </div>
          <div className="px-2 pb-2 space-y-0.5">
            {visibleProviders.map((p) => (
              <button
                key={p.id}
                onClick={() => handleProviderClick(p.id)}
                className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm transition-colors ${
                  selectedProvider === p.id
                    ? 'bg-slate-mid/40 text-text-primary'
                    : 'text-text-secondary hover:bg-slate-mid/20 hover:text-text-primary'
                }`}
              >
                <div className={`w-2 h-2 rounded-full ${p.dotColor}`} />
                <span className="font-medium">{p.label}</span>
                {p.id === currentProvider && (
                  <span className="ml-auto text-xs text-text-muted">{t('provider.current')}</span>
                )}
              </button>
            ))}
          </div>

          {/* Divider */}
          <div className="border-t border-slate-mid/30" />

          {/* Model section */}
          <div className="px-3 pt-2 pb-1 flex items-center justify-between">
            <span className="text-xs text-text-muted uppercase tracking-wide">{t('provider.model')}</span>
            {selectedConfig && (
              <span className="text-xs text-text-muted">
                default: <span className="font-mono">{selectedConfig.defaultModel}</span>
              </span>
            )}
          </div>
          <div className="px-2 pb-2 space-y-0.5">
            {models.map((m) => (
              <button
                key={m}
                onClick={() => handleModelClick(m)}
                className={`w-full text-left px-2.5 py-1.5 rounded-lg text-sm transition-colors ${
                  currentModel === m && selectedProvider === currentProvider
                    ? 'bg-synapse/10 text-synapse'
                    : 'text-text-secondary hover:bg-slate-mid/20 hover:text-text-primary'
                } font-mono`}
              >
                {m}
                {m === selectedConfig?.defaultModel && (
                  <span className="ml-2 text-text-muted text-xs font-sans">({t('provider.default')})</span>
                )}
              </button>
            ))}
          </div>

          {/* Custom model input */}
          <div className="px-2 pb-3">
            <form onSubmit={handleCustomSubmit} className="flex gap-1.5">
              <input
                ref={inputRef}
                type="text"
                placeholder={t('provider.customModel')}
                value={customModel}
                onChange={(e) => setCustomModel(e.target.value)}
                className="flex-1 px-2.5 py-1.5 rounded-lg text-sm font-mono bg-obsidian/50 border border-slate-mid/40 text-text-primary placeholder:text-text-muted/50 focus:border-synapse/50 focus:outline-none transition-colors"
              />
              <button
                type="submit"
                disabled={!customModel.trim()}
                className="px-3 py-1.5 rounded-lg text-xs font-medium bg-synapse/20 text-synapse border border-synapse/30 hover:bg-synapse/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {t('provider.go')}
              </button>
            </form>
          </div>

          {/* Provider options */}
          {providerOptions.length > 0 && (
            <>
              <div className="border-t border-slate-mid/30" />
              <div className="px-3 pt-2 pb-1">
                <span className="text-xs text-text-muted uppercase tracking-wide">{t('provider.options')}</span>
              </div>
              <div className="px-2 pb-2 space-y-2.5">
                {providerOptions
                  .filter((opt) => !opt.hideForModelPattern || !effectiveModel || !new RegExp(opt.hideForModelPattern, 'i').test(effectiveModel))
                  .map((opt) => (
                  <OptionControl
                    key={opt.key}
                    option={opt}
                    model={effectiveModel}
                    value={optionValues[opt.key]}
                    onChange={(val) => handleOptionChange(opt.key, val)}
                    compact={false}
                  />
                ))}
              </div>
            </>
          )}

          {/* Safety mode selector (shown for all providers) */}
          <div className="border-t border-slate-mid/30" />
          <SafetyModeSelector
            value={safetyMode}
            onChange={setSafetyMode}
            provider={selectedProvider}
          />

          {optionsDirty && (
            <div className="px-2 pb-3">
              <button
                onClick={handleApplyOptions}
                className="w-full py-1.5 rounded-lg text-xs font-medium bg-synapse/20 text-synapse border border-synapse/30 hover:bg-synapse/30 transition-colors"
              >
                {t('provider.applyOptions')}
              </button>
            </div>
          )}
        </div>
      )}

    </div>
  )
}

