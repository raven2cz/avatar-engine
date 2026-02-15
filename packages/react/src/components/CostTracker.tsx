/**
 * Cost tracker — displays total USD, token counts.
 *
 * Only visible when cost tracking is enabled by the provider.
 */

import { Coins, ArrowDown, ArrowUp } from 'lucide-react'
import type { CostInfo } from '@avatar-engine/core'

interface CostTrackerProps {
  cost: CostInfo
  visible: boolean
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

export function CostTracker({ cost, visible }: CostTrackerProps) {
  if (!visible || (cost.totalCostUsd === 0 && cost.totalInputTokens === 0)) return null

  return (
    <div className="flex items-center gap-4 px-4 py-2 glass-light rounded-xl border border-slate-mid/20 animate-fade-in">
      <div className="flex items-center gap-1.5">
        <Coins className="w-3.5 h-3.5 text-amber-400" />
        <span className="text-xs font-medium text-amber-300">
          ${cost.totalCostUsd.toFixed(4)}
        </span>
      </div>

      <div className="w-px h-3 bg-slate-mid/50" />

      <div className="flex items-center gap-1">
        <ArrowDown className="w-3 h-3 text-text-muted" />
        <span className="text-xs text-text-muted tabular-nums">
          {formatTokens(cost.totalInputTokens)}
        </span>
      </div>

      <div className="flex items-center gap-1">
        <ArrowUp className="w-3 h-3 text-text-muted" />
        <span className="text-xs text-text-muted tabular-nums">
          {formatTokens(cost.totalOutputTokens)}
        </span>
      </div>
    </div>
  )
}
