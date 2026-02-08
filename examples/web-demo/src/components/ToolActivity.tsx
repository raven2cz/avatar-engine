/**
 * Tool activity display — shows tool executions with status icons.
 *
 * Mirrors CLI ToolGroupDisplay but rendered as React components.
 */

import { useEffect, useState } from 'react'
import { Check, Loader2, X, Wrench } from 'lucide-react'
import type { ToolInfo } from '../api/types'

interface ToolActivityProps {
  tools: ToolInfo[]
}

function ToolEntry({ tool }: { tool: ToolInfo }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (tool.status !== 'started') return
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - tool.startedAt) / 1000))
    }, 1000)
    return () => clearInterval(interval)
  }, [tool.status, tool.startedAt])

  const completedElapsed = tool.completedAt
    ? ((tool.completedAt - tool.startedAt) / 1000).toFixed(1)
    : null

  return (
    <div className="flex items-center gap-2 py-1 animate-slide-up">
      {tool.status === 'started' && (
        <Loader2 className="w-3.5 h-3.5 text-amber-400 animate-spin flex-shrink-0" />
      )}
      {tool.status === 'completed' && (
        <Check className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
      )}
      {tool.status === 'failed' && (
        <X className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
      )}

      <span
        className={`text-xs font-medium ${
          tool.status === 'started'
            ? 'text-amber-300'
            : tool.status === 'completed'
            ? 'text-emerald-300'
            : 'text-red-300'
        }`}
      >
        {tool.name}
      </span>

      {tool.params && tool.status === 'started' && (
        <span className="text-xs text-text-muted truncate max-w-[200px]">{tool.params}</span>
      )}

      {tool.status === 'started' && (
        <span className="text-xs text-text-muted tabular-nums ml-auto">{elapsed}s</span>
      )}
      {completedElapsed && tool.status !== 'started' && (
        <span className="text-xs text-text-muted tabular-nums ml-auto">{completedElapsed}s</span>
      )}

      {tool.error && (
        <span className="text-xs text-red-400 truncate max-w-[200px]">{tool.error}</span>
      )}
    </div>
  )
}

export function ToolActivity({ tools }: ToolActivityProps) {
  if (tools.length === 0) return null

  const active = tools.filter((t) => t.status === 'started').length
  const total = tools.length

  return (
    <div className="glass-light rounded-xl border border-slate-mid/30 px-3 py-2 my-1 animate-fade-in">
      <div className="flex items-center gap-2 mb-1">
        <Wrench className="w-3.5 h-3.5 text-text-muted" />
        <span className="text-xs text-text-muted font-medium">
          Tools{' '}
          <span className="text-text-secondary">
            [{total - active}/{total}]
          </span>
        </span>
      </div>
      <div className="space-y-0.5">
        {tools.map((tool) => (
          <ToolEntry key={tool.toolId} tool={tool} />
        ))}
      </div>
    </div>
  )
}
