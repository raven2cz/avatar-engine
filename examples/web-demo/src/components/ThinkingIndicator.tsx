/**
 * Thinking indicator — shows AI thinking phase with breathing orb.
 *
 * Displays: animated orb + phase label + subject + elapsed time.
 * Color-coded by thinking phase (matches CLI PHASE_STYLES).
 */

import { useEffect, useState } from 'react'
import { Brain, Code, Eye, Lightbulb, Search, Wrench } from 'lucide-react'
import { BreathingOrb } from './BreathingOrb'
import type { ThinkingPhase } from '../api/types'

interface ThinkingIndicatorProps {
  active: boolean
  phase: ThinkingPhase
  subject: string
  startedAt: number
}

const PHASE_CONFIG: Record<ThinkingPhase, { label: string; icon: typeof Brain; color: string }> = {
  general: { label: 'Thinking', icon: Brain, color: 'text-cyan-400' },
  analyzing: { label: 'Analyzing', icon: Search, color: 'text-blue-400' },
  planning: { label: 'Planning', icon: Lightbulb, color: 'text-violet-400' },
  coding: { label: 'Coding', icon: Code, color: 'text-emerald-400' },
  reviewing: { label: 'Reviewing', icon: Eye, color: 'text-amber-400' },
  tool_planning: { label: 'Preparing tools', icon: Wrench, color: 'text-orange-400' },
}

export function ThinkingIndicator({ active, phase, subject, startedAt }: ThinkingIndicatorProps) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!active || !startedAt) {
      setElapsed(0)
      return
    }
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000))
    }, 1000)
    return () => clearInterval(interval)
  }, [active, startedAt])

  if (!active) return null

  const config = PHASE_CONFIG[phase] || PHASE_CONFIG.general
  const Icon = config.icon

  return (
    <div className="flex items-center gap-4 px-4 py-3 animate-fade-in">
      <BreathingOrb size="sm" active={active} phase={phase} />

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <Icon className={`w-4 h-4 ${config.color}`} />
          <span className={`text-sm font-medium ${config.color}`}>
            {subject || config.label}
          </span>
        </div>
        {subject && (
          <span className="text-xs text-text-muted">{config.label}</span>
        )}
      </div>

      <span className="text-xs text-text-muted tabular-nums">{elapsed}s</span>
    </div>
  )
}
