/**
 * Status bar — connection state, provider, model, engine state, capabilities.
 *
 * Glassmorphism header bar with Synapse styling.
 * Left: logo + title + version. Center: connection + provider + model + state.
 * Right: capabilities + usage button + session.
 */

import { useState, useEffect, useCallback } from 'react'
import { Activity, History, Info, Wifi, WifiOff, X, Zap } from 'lucide-react'
import type { CostInfo, EngineState, ProviderCapabilities } from '../api/types'
import { AvatarLogo } from './AvatarLogo'
import { ProviderModelSelector } from './ProviderModelSelector'
import { SessionPanel } from './SessionPanel'
import { getProvider } from '../config/providers'

interface StatusBarProps {
  connected: boolean
  provider: string
  model: string | null
  version: string
  cwd?: string
  engineState: EngineState
  capabilities: ProviderCapabilities | null
  sessionId: string | null
  sessionTitle?: string | null
  cost: CostInfo
  switching?: boolean
  activeOptions?: Record<string, string | number>
  availableProviders?: Set<string> | null
  onSwitch?: (provider: string, model?: string, options?: Record<string, string | number>) => void
  onResume?: (sessionId: string) => void
  onNewSession?: () => void
}

const STATE_LABELS: Record<EngineState, { label: string; color: string }> = {
  idle: { label: 'Ready', color: 'text-emerald-400' },
  thinking: { label: 'Thinking', color: 'text-cyan-400' },
  responding: { label: 'Responding', color: 'text-synapse' },
  tool_executing: { label: 'Executing', color: 'text-amber-400' },
  waiting_approval: { label: 'Awaiting approval', color: 'text-violet-400' },
  error: { label: 'Error', color: 'text-red-400' },
}


interface UsageData {
  total_requests: number
  successful_requests: number
  failed_requests: number
  total_duration_ms: number
  total_cost_usd: number
  total_input_tokens: number
  total_output_tokens: number
  provider: string
  session_id: string | null
  budget_usd?: number
  budget_remaining_usd?: number
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(s / 60)
  const rs = Math.floor(s % 60)
  return `${m}m ${rs}s`
}

// REST API base — matches Vite proxy config
const API_BASE =
  import.meta.env.DEV
    ? `http://${window.location.hostname}:5173/api/avatar`
    : `/api/avatar`

export function StatusBar({
  connected,
  provider,
  model,
  version,
  cwd,
  engineState,
  capabilities,
  sessionId,
  sessionTitle,
  cost,
  switching = false,
  activeOptions,
  availableProviders,
  onSwitch,
  onResume,
  onNewSession,
}: StatusBarProps) {
  const stateConfig = STATE_LABELS[engineState] || STATE_LABELS.idle
  const providerConfig = getProvider(provider)
  const [showDetail, setShowDetail] = useState(false)
  const [showSessions, setShowSessions] = useState(false)
  const [usage, setUsage] = useState<UsageData | null>(null)
  const [localTitle, setLocalTitle] = useState<string | null>(null)

  // Clear local override only when server confirms the rename (sessionTitle matches)
  // or when there's no local override. Don't wipe localTitle on unrelated sessionTitle changes.
  useEffect(() => {
    setLocalTitle(prev => {
      if (prev === null || sessionTitle === prev) return null
      return prev
    })
  }, [sessionTitle])

  const displayTitle = localTitle ?? sessionTitle

  // Fetch usage from REST API when detail panel opens
  useEffect(() => {
    if (!showDetail || !connected) return
    let cancelled = false
    fetch(`${API_BASE}/usage`)
      .then((r) => r.json())
      .then((data) => { if (!cancelled) setUsage(data) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [showDetail, connected])

  // Close detail panel on Escape
  useEffect(() => {
    if (!showDetail) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setShowDetail(false)
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [showDetail])

  const toggleDetail = useCallback(() => setShowDetail((v) => !v), [])

  return (
    <>
      <header className="sticky top-0 z-50 glass border-b border-slate-mid/30">
        <div className="flex items-center justify-between h-14 px-6">
          {/* Left: Logo + Title + Version */}
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-synapse/20 to-pulse/20 border border-synapse/30 flex items-center justify-center">
              <AvatarLogo className="w-7 h-7" />
            </div>
            <div className="flex items-baseline gap-2">
              <h1 className="text-lg font-semibold gradient-text">Avatar Engine</h1>
              {version && (
                <span className="text-xs text-text-muted font-mono">v{version}</span>
              )}
            </div>
          </div>

          {/* Center: Connection + Provider + Model + State */}
          <div className="flex items-center gap-3">
            {/* Connection indicator */}
            <div className="flex items-center gap-1.5">
              {connected ? (
                <Wifi className="w-3.5 h-3.5 text-emerald-400" />
              ) : (
                <WifiOff className="w-3.5 h-3.5 text-red-400" />
              )}
              <div
                className={`w-2 h-2 rounded-full ${
                  connected ? 'bg-emerald-400 animate-glow-pulse' : 'bg-red-400'
                }`}
              />
            </div>

            {/* Provider + Model selector */}
            {onSwitch ? (
              <ProviderModelSelector
                currentProvider={provider}
                currentModel={model}
                switching={switching}
                activeOptions={activeOptions}
                availableProviders={availableProviders}
                onSwitch={onSwitch}
              />
            ) : (
              <>
                {providerConfig && (
                  <div
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium bg-gradient-to-r ${providerConfig.gradient} border`}
                  >
                    {providerConfig.label}
                  </div>
                )}
                {model && (
                  <span className="text-xs text-text-secondary font-mono truncate max-w-[200px]">
                    {model}
                  </span>
                )}
              </>
            )}

            {/* Engine state */}
            <div className="flex items-center gap-1.5">
              <Activity className={`w-3.5 h-3.5 ${stateConfig.color}`} />
              <span className={`text-xs font-medium ${stateConfig.color}`}>
                {stateConfig.label}
              </span>
            </div>
          </div>

          {/* Right: Capabilities + Info button + Session */}
          <div className="flex items-center gap-2">
            {capabilities?.cost_tracking && cost.totalCostUsd > 0 && (
              <div className="px-2 py-0.5 rounded-full text-xs bg-amber-500/10 text-amber-400 border border-amber-500/20">
                <Zap className="w-3 h-3 inline mr-1" />
                ${cost.totalCostUsd.toFixed(4)}
              </div>
            )}

            {/* Info / detail button */}
            <button
              onClick={toggleDetail}
              className="p-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-slate-mid/30 transition-colors"
              title="Session details"
            >
              <Info className="w-4 h-4" />
            </button>

            {/* Session management button — always visible */}
            {onResume && onNewSession && (
              <button
                onClick={() => setShowSessions((v) => !v)}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs hover:bg-slate-mid/30 border border-slate-mid/30 hover:border-slate-mid/50 transition-colors max-w-[180px]"
                title={displayTitle || sessionId || 'Sessions'}
              >
                <History className="w-3.5 h-3.5 flex-shrink-0 text-text-muted" />
                {displayTitle ? (
                  <span className="truncate text-text-primary">{displayTitle.length > 30 ? displayTitle.slice(0, 28) + '...' : displayTitle}</span>
                ) : sessionId ? (
                  <span className="truncate text-text-secondary font-mono">{sessionId.slice(0, 8)}</span>
                ) : (
                  <span className="text-text-muted">Sessions</span>
                )}
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Overlays rendered OUTSIDE header to escape its stacking context */}

      {/* Session management modal */}
      {onResume && onNewSession && (
        <SessionPanel
          open={showSessions}
          onClose={() => setShowSessions(false)}
          provider={provider}
          cwd={cwd || ''}
          capabilities={capabilities}
          onResume={onResume}
          onNewSession={onNewSession}
          onTitleUpdated={setLocalTitle}
        />
      )}

      {/* Floating detail panel */}
      {showDetail && (
        <>
          {/* Backdrop */}
          <div className="fixed inset-0 z-[60]" onClick={() => setShowDetail(false)} />

          {/* Panel */}
          <div className="fixed right-4 top-16 z-[70] w-80 glass-panel rounded-2xl border border-slate-mid/40 shadow-2xl shadow-black/60 animate-slide-up overflow-hidden">
            {/* Header with gradient accent */}
            <div className="relative px-5 py-4 border-b border-slate-mid/30">
              <div className="absolute inset-x-0 top-0 h-[1px] bg-gradient-to-r from-transparent via-synapse/50 to-transparent" />
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold gradient-text">Session Details</h3>
                <button
                  onClick={() => setShowDetail(false)}
                  className="p-1 rounded-lg text-text-muted hover:text-text-secondary hover:bg-slate-mid/30 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="px-5 py-4 space-y-4 text-sm">
              {/* Provider + Model */}
              <div className="space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-text-muted text-xs">Provider</span>
                  {providerConfig ? (
                    <div className={`px-2 py-0.5 rounded-md text-xs font-medium bg-gradient-to-r ${providerConfig.gradient} border`}>
                      {providerConfig.label}
                    </div>
                  ) : (
                    <span className="text-text-secondary">{provider || '-'}</span>
                  )}
                </div>
                <DetailRow label="Model" value={model || providerConfig?.defaultModel || '-'} mono />
                <DetailRow label="Engine" value={version ? `v${version}` : '-'} />
                <div className="flex items-center justify-between">
                  <span className="text-text-muted text-xs">State</span>
                  <span className={`text-xs font-medium ${stateConfig.color}`}>{stateConfig.label}</span>
                </div>
              </div>

              {/* Session */}
              <div className="rounded-lg bg-slate-mid/20 border border-slate-mid/30 px-3 py-2.5 space-y-1">
                <span className="text-xs text-text-muted">Session</span>
                {displayTitle && (
                  <p className="text-xs text-text-secondary truncate">{displayTitle}</p>
                )}
                <p className="text-xs text-text-muted font-mono">{sessionId ? sessionId.slice(0, 24) : '-'}</p>
              </div>

              {/* Capabilities */}
              {capabilities && (
                <div className="space-y-2">
                  <SectionLabel label="Capabilities" />
                  <div className="flex flex-wrap gap-1.5">
                    {capabilities.thinking_supported && <CapBadge label="Thinking" />}
                    {capabilities.cost_tracking && <CapBadge label="Cost" />}
                    {capabilities.streaming && <CapBadge label="Streaming" />}
                    {capabilities.mcp_supported && <CapBadge label="MCP" />}
                    {capabilities.parallel_tools && <CapBadge label="Parallel tools" />}
                    {capabilities.can_list_sessions && <CapBadge label="Sessions" />}
                  </div>
                </div>
              )}

              {/* Usage stats (fetched from REST API) */}
              {usage && usage.total_requests > 0 && (
                <div className="space-y-2.5">
                  <SectionLabel label="Usage" />
                  <DetailRow
                    label="Requests"
                    value={`${usage.successful_requests}/${usage.total_requests}${usage.failed_requests ? ` (${usage.failed_requests} failed)` : ''}`}
                  />
                  <DetailRow
                    label="Avg latency"
                    value={formatDuration(Math.round(usage.total_duration_ms / usage.total_requests))}
                  />
                  {(usage.total_input_tokens > 0 || usage.total_output_tokens > 0) && (
                    <>
                      <DetailRow label="Input tokens" value={formatTokens(usage.total_input_tokens)} />
                      <DetailRow label="Output tokens" value={formatTokens(usage.total_output_tokens)} />
                    </>
                  )}
                  {usage.total_cost_usd > 0 && (
                    <DetailRow label="Cost" value={`$${usage.total_cost_usd.toFixed(4)}`} />
                  )}
                  {usage.budget_usd !== undefined && (
                    <DetailRow
                      label="Budget"
                      value={`$${(usage.budget_remaining_usd ?? 0).toFixed(2)} / $${usage.budget_usd.toFixed(2)}`}
                    />
                  )}
                </div>
              )}
              {!usage && showDetail && connected && (
                <div className="pt-1">
                  <span className="text-xs text-text-muted animate-pulse">Loading usage...</span>
                </div>
              )}
              {usage && usage.total_requests === 0 && (
                <div className="pt-1">
                  <span className="text-xs text-text-muted">No requests yet</span>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </>
  )
}

function DetailRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-text-muted text-xs">{label}</span>
      <span className={`text-text-secondary text-xs ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  )
}

function SectionLabel({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-[1px] flex-1 bg-gradient-to-r from-slate-mid/50 to-transparent" />
      <span className="text-[10px] text-text-muted uppercase tracking-widest">{label}</span>
      <div className="h-[1px] flex-1 bg-gradient-to-l from-slate-mid/50 to-transparent" />
    </div>
  )
}

function CapBadge({ label }: { label: string }) {
  return (
    <span className="px-2 py-0.5 rounded-md text-[10px] bg-synapse/8 text-text-secondary border border-synapse/15">
      {label}
    </span>
  )
}
