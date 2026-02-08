/**
 * Status bar — connection state, provider, engine state, capabilities.
 *
 * Glassmorphism header bar with Synapse styling.
 */

import { Activity, Bot, Cpu, Wifi, WifiOff, Zap } from 'lucide-react'
import type { EngineState, ProviderCapabilities } from '../api/types'

interface StatusBarProps {
  connected: boolean
  provider: string
  engineState: EngineState
  capabilities: ProviderCapabilities | null
  sessionId: string | null
}

const STATE_LABELS: Record<EngineState, { label: string; color: string }> = {
  idle: { label: 'Ready', color: 'text-emerald-400' },
  thinking: { label: 'Thinking', color: 'text-cyan-400' },
  responding: { label: 'Responding', color: 'text-synapse' },
  tool_executing: { label: 'Executing', color: 'text-amber-400' },
  waiting_approval: { label: 'Awaiting approval', color: 'text-violet-400' },
  error: { label: 'Error', color: 'text-red-400' },
}

const PROVIDER_BADGES: Record<string, { label: string; gradient: string }> = {
  gemini: { label: 'Gemini', gradient: 'from-blue-500/20 to-cyan-500/20 border-blue-400/40' },
  claude: { label: 'Claude', gradient: 'from-amber-500/20 to-orange-500/20 border-amber-400/40' },
  codex: { label: 'Codex', gradient: 'from-emerald-500/20 to-green-500/20 border-emerald-400/40' },
}

export function StatusBar({ connected, provider, engineState, capabilities, sessionId }: StatusBarProps) {
  const stateConfig = STATE_LABELS[engineState] || STATE_LABELS.idle
  const providerBadge = PROVIDER_BADGES[provider]

  return (
    <header className="sticky top-0 z-50 glass border-b border-slate-mid/30">
      <div className="flex items-center justify-between h-14 px-6">
        {/* Left: Logo + Title */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-synapse to-pulse flex items-center justify-center">
            <Bot className="w-5 h-5 text-white" />
          </div>
          <h1 className="text-lg font-semibold gradient-text">Avatar Engine</h1>
        </div>

        {/* Center: State + Provider */}
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

          {/* Provider badge */}
          {providerBadge && (
            <div
              className={`px-2.5 py-1 rounded-lg text-xs font-medium bg-gradient-to-r ${providerBadge.gradient} border`}
            >
              {providerBadge.label}
            </div>
          )}

          {/* Engine state */}
          <div className="flex items-center gap-1.5">
            <Activity className={`w-3.5 h-3.5 ${stateConfig.color}`} />
            <span className={`text-xs font-medium ${stateConfig.color}`}>
              {stateConfig.label}
            </span>
          </div>
        </div>

        {/* Right: Capabilities + Session */}
        <div className="flex items-center gap-2">
          {capabilities?.thinking_supported && (
            <div className="px-2 py-0.5 rounded-full text-xs bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              <Cpu className="w-3 h-3 inline mr-1" />
              Thinking
            </div>
          )}
          {capabilities?.cost_tracking && (
            <div className="px-2 py-0.5 rounded-full text-xs bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <Zap className="w-3 h-3 inline mr-1" />
              Cost
            </div>
          )}
          {sessionId && (
            <span className="text-xs text-text-muted font-mono">
              {sessionId.slice(0, 8)}
            </span>
          )}
        </div>
      </div>
    </header>
  )
}
