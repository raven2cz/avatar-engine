/**
 * Compact mode header — provider badge, state indicator, menu, fullscreen/close.
 *
 * Minimal height (~38px). The ⋯ button opens a provider/model dropdown
 * (portaled to document.body, opens upward) that mirrors the fullscreen
 * ProviderModelSelector in a compact form.
 */

import { useState, useRef, useCallback, useEffect } from 'react'
import { createPortal } from 'react-dom'
import type { EngineState } from '../api/types'
import {
  PROVIDERS,
  getProvider,
  getModelsForProvider,
  getOptionsForProvider,
  getModelDisplayName,
  filterChoicesForModel,
} from '../config/providers'
import { OptionControl } from './OptionControl'

interface CompactHeaderProps {
  provider: string
  model: string | null
  connected: boolean
  engineState: EngineState | string
  onFullscreen: () => void
  onClose: () => void
  // Live activity detail — shown next to state labels
  thinkingSubject?: string
  toolName?: string
  // Provider/model switching — enables the ⋯ menu button
  switching?: boolean
  activeOptions?: Record<string, string | number>
  availableProviders?: Set<string> | null
  onSwitchProvider?: (provider: string, model?: string, options?: Record<string, string | number>) => void
  // First-time hint on the fullscreen button
  showExpandHint?: boolean
}

const STATE_LABELS: Record<string, { label: string; cls: string }> = {
  thinking: { label: 'Thinking...', cls: 'bg-synapse/12 text-synapse' },
  responding: { label: 'Responding...', cls: 'bg-pulse/12 text-pulse' },
  tool_executing: { label: 'Running tool...', cls: 'bg-neural/12 text-neural' },
  error: { label: 'Error', cls: 'bg-red-500/12 text-red-400' },
}

export function CompactHeader({
  provider,
  model,
  connected,
  engineState,
  onFullscreen,
  onClose,
  thinkingSubject,
  toolName,
  switching,
  activeOptions = {},
  availableProviders,
  onSwitchProvider,
  showExpandHint,
}: CompactHeaderProps) {
  const stateInfo = STATE_LABELS[engineState]
  const { modelName, featuredLabel } = getModelDisplayName(
    provider, model, getProvider(provider)?.defaultModel, activeOptions,
  )
  const [menuOpen, setMenuOpen] = useState(false)
  const menuBtnRef = useRef<HTMLButtonElement>(null)
  const menuPosRef = useRef({ bottom: 0, right: 0 })

  const handleMenuOpen = useCallback(() => {
    if (menuBtnRef.current) {
      const rect = menuBtnRef.current.getBoundingClientRect()
      menuPosRef.current = {
        bottom: window.innerHeight - rect.top + 6,
        right: window.innerWidth - rect.right,
      }
    }
    setMenuOpen(true)
  }, [])

  return (
    <div className="flex items-center justify-between px-3 py-1.5 border-b border-slate-mid/30 bg-black/20 min-h-[38px] flex-shrink-0 rounded-t-2xl">
      {/* Left: provider + model + state */}
      <div className="flex items-center gap-2 min-w-0">
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg bg-synapse/10 border border-synapse/20 text-[0.65rem] font-medium text-synapse flex-shrink-0">
          <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-emerald-400 shadow-[0_0_4px_theme(colors.emerald.400)]' : 'bg-red-400'}`} />
          {provider || 'Provider'}
        </span>
        {modelName && (
          <span className="text-[0.65rem] text-text-muted font-mono truncate">
            {modelName}
            {featuredLabel && (
              <span className="font-sans"> ({featuredLabel})</span>
            )}
          </span>
        )}
        {stateInfo && (() => {
          // Dynamic detail: show thinking subject or tool name
          const detail = engineState === 'thinking' && thinkingSubject
            ? thinkingSubject
            : engineState === 'tool_executing' && toolName
              ? toolName
              : ''
          return (
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[0.6rem] font-medium max-w-[180px] ${stateInfo.cls}`}>
              <span className="w-1 h-1 rounded-full bg-current animate-pulse flex-shrink-0" />
              {detail
                ? <span className="truncate">{detail}</span>
                : stateInfo.label}
            </span>
          )
        })()}
      </div>

      {/* Right: controls */}
      <div className="flex items-center gap-0.5 flex-shrink-0">
        {/* Provider/Model menu (⋯ button) */}
        {onSwitchProvider && (
          <button
            ref={menuBtnRef}
            onClick={handleMenuOpen}
            disabled={switching}
            className="w-6 h-6 rounded-md flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-white/8 transition-colors disabled:opacity-40"
            title="Provider & model settings"
            aria-label="Provider and model settings"
          >
            <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
              <circle cx="12" cy="5" r="2" />
              <circle cx="12" cy="12" r="2" />
              <circle cx="12" cy="19" r="2" />
            </svg>
          </button>
        )}

        {/* Fullscreen + optional hint indicator */}
        <div className="relative">
          <button
            onClick={onFullscreen}
            className="w-6 h-6 rounded-md flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-white/8 transition-colors"
            title="Fullscreen (Ctrl+Shift+F)"
            aria-label="Expand to fullscreen"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
              <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
            </svg>
          </button>
          {showExpandHint && (
            <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-synapse animate-ping pointer-events-none" />
          )}
        </div>

        {/* Close */}
        <button
          onClick={onClose}
          className="w-6 h-6 rounded-md flex items-center justify-center text-text-muted hover:text-red-400 hover:bg-red-500/10 transition-colors"
          title="Close (Esc)"
          aria-label="Close chat panel"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Provider/Model dropdown — portaled to body so it escapes overflow clips */}
      {menuOpen && onSwitchProvider && createPortal(
        <CompactProviderMenu
          currentProvider={provider}
          currentModel={model}
          switching={switching || false}
          activeOptions={activeOptions}
          availableProviders={availableProviders}
          onSwitch={(p, m, o) => { onSwitchProvider(p, m, o); setMenuOpen(false) }}
          onClose={() => setMenuOpen(false)}
          position={menuPosRef.current}
        />,
        document.body,
      )}
    </div>
  )
}


/* ------------------------------------------------------------------ */
/*  Compact provider/model dropdown (opens upward from ⋯ button)      */
/* ------------------------------------------------------------------ */

interface CompactProviderMenuProps {
  currentProvider: string
  currentModel: string | null
  switching: boolean
  activeOptions: Record<string, string | number>
  availableProviders?: Set<string> | null
  onSwitch: (provider: string, model?: string, options?: Record<string, string | number>) => void
  onClose: () => void
  position: { bottom: number; right: number }
}

function CompactProviderMenu({
  currentProvider,
  currentModel,
  switching,
  activeOptions,
  availableProviders,
  onSwitch,
  onClose,
  position,
}: CompactProviderMenuProps) {
  const [selectedProvider, setSelectedProvider] = useState(currentProvider)
  const [customModel, setCustomModel] = useState('')
  const [optionValues, setOptionValues] = useState<Record<string, string | number>>(activeOptions)

  // Close on Escape (capture phase so it doesn't also trigger widget mode shortcuts)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.stopPropagation(); onClose() }
    }
    document.addEventListener('keydown', handler, true)
    return () => document.removeEventListener('keydown', handler, true)
  }, [onClose])

  const visibleProviders = availableProviders
    ? PROVIDERS.filter((p) => availableProviders.has(p.id))
    : PROVIDERS

  const selectedConfig = getProvider(selectedProvider)
  const models = getModelsForProvider(selectedProvider)
  const providerOptions = getOptionsForProvider(selectedProvider)
  const effectiveModel = (selectedProvider === currentProvider ? currentModel : null)
    || selectedConfig?.defaultModel || null

  const sanitizeOptions = useCallback((model: string) => {
    const opts = getOptionsForProvider(selectedProvider)
    const sanitized = { ...optionValues }
    for (const opt of opts) {
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
    return Object.keys(sanitized).length > 0 ? sanitized : undefined
  }, [selectedProvider, optionValues])

  const handleModelClick = useCallback((model: string) => {
    onSwitch(selectedProvider, model, sanitizeOptions(model))
  }, [selectedProvider, onSwitch, sanitizeOptions])

  const handleCustomSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault()
    const model = customModel.trim()
    if (model) onSwitch(selectedProvider, model, sanitizeOptions(model))
  }, [selectedProvider, customModel, onSwitch, sanitizeOptions])

  const handleProviderClick = useCallback((providerId: string) => {
    setSelectedProvider(providerId)
    setCustomModel('')
    setOptionValues(providerId === currentProvider ? activeOptions : {})
  }, [currentProvider, activeOptions])

  // Apply options change without switching model (re-apply current provider+model)
  const handleApplyOptions = useCallback(() => {
    const model = effectiveModel || selectedConfig?.defaultModel || undefined
    if (model) {
      onSwitch(selectedProvider, model, sanitizeOptions(model))
    }
  }, [selectedProvider, effectiveModel, selectedConfig, onSwitch, sanitizeOptions])

  // Detect if options differ from currently active ones
  const optionsDirty = selectedProvider === currentProvider && (() => {
    const opts = getOptionsForProvider(selectedProvider)
    for (const opt of opts) {
      const current = activeOptions[opt.key] ?? opt.defaultValue
      const local = optionValues[opt.key] ?? opt.defaultValue
      if (String(current) !== String(local)) return true
    }
    return false
  })()

  return (
    <div className="fixed inset-0 z-[1100]" onClick={onClose}>
      <div
        className="absolute w-72 glass-panel rounded-xl border border-slate-mid/40 shadow-2xl shadow-black/60 animate-slide-up max-h-[70vh] overflow-y-auto compact-scrollbar"
        style={{ bottom: position.bottom, right: position.right }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Provider section */}
        <div className="px-3 pt-3 pb-2">
          <span className="text-[0.65rem] text-text-muted uppercase tracking-wide">Provider</span>
        </div>
        <div className="px-2 pb-2 space-y-0.5">
          {visibleProviders.map((p) => (
            <button
              key={p.id}
              onClick={() => handleProviderClick(p.id)}
              className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs transition-colors ${
                selectedProvider === p.id
                  ? 'bg-slate-mid/40 text-text-primary'
                  : 'text-text-secondary hover:bg-slate-mid/20 hover:text-text-primary'
              }`}
            >
              <div className={`w-2 h-2 rounded-full ${p.dotColor}`} />
              <span className="font-medium">{p.label}</span>
              {p.id === currentProvider && (
                <span className="ml-auto text-[0.6rem] text-text-muted">current</span>
              )}
            </button>
          ))}
        </div>

        <div className="border-t border-slate-mid/30" />

        {/* Model section */}
        <div className="px-3 pt-2 pb-1 flex items-center justify-between">
          <span className="text-[0.65rem] text-text-muted uppercase tracking-wide">Model</span>
          {selectedConfig && (
            <span className="text-[0.6rem] text-text-muted">
              default: <span className="font-mono">{selectedConfig.defaultModel}</span>
            </span>
          )}
        </div>
        <div className="px-2 pb-2 space-y-0.5">
          {models.map((m) => (
            <button
              key={m}
              onClick={() => handleModelClick(m)}
              className={`w-full text-left px-2 py-1 rounded-lg text-xs transition-colors ${
                currentModel === m && selectedProvider === currentProvider
                  ? 'bg-synapse/10 text-synapse'
                  : 'text-text-secondary hover:bg-slate-mid/20 hover:text-text-primary'
              } font-mono`}
            >
              {m}
              {m === selectedConfig?.defaultModel && (
                <span className="ml-1.5 text-text-muted text-[0.6rem] font-sans">(default)</span>
              )}
            </button>
          ))}
        </div>

        {/* Custom model input */}
        <div className="px-2 pb-2">
          <form onSubmit={handleCustomSubmit} className="flex gap-1">
            <input
              type="text"
              placeholder="Custom model..."
              value={customModel}
              onChange={(e) => setCustomModel(e.target.value)}
              className="flex-1 px-2 py-1 rounded-lg text-xs font-mono bg-obsidian/50 border border-slate-mid/40 text-text-primary placeholder:text-text-muted/50 focus:border-synapse/50 focus:outline-none transition-colors"
            />
            <button
              type="submit"
              disabled={!customModel.trim()}
              className="px-2 py-1 rounded-lg text-[0.65rem] font-medium bg-synapse/20 text-synapse border border-synapse/30 hover:bg-synapse/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Go
            </button>
          </form>
        </div>

        {/* Provider options (thinking level, temperature, etc.) */}
        {providerOptions.length > 0 && (
          <>
            <div className="border-t border-slate-mid/30" />
            <div className="px-3 pt-2 pb-1">
              <span className="text-[0.65rem] text-text-muted uppercase tracking-wide">Options</span>
            </div>
            <div className="px-2 pb-2 space-y-2">
              {providerOptions
                .filter((opt) => !opt.hideForModelPattern || !effectiveModel || !new RegExp(opt.hideForModelPattern, 'i').test(effectiveModel))
                .map((opt) => (
                  <OptionControl
                    key={opt.key}
                    option={opt}
                    model={effectiveModel}
                    value={optionValues[opt.key]}
                    onChange={(val) => setOptionValues((prev) => ({ ...prev, [opt.key]: val }))}
                    compact
                  />
                ))}
            </div>
            {optionsDirty && (
              <div className="px-2 pb-3">
                <button
                  onClick={handleApplyOptions}
                  className="w-full py-1.5 rounded-lg text-[0.65rem] font-medium bg-synapse/20 text-synapse border border-synapse/30 hover:bg-synapse/30 transition-colors"
                >
                  Apply options
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}


