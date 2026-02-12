/**
 * Shared option control — single source of truth for select / slider / number
 * UI in both fullscreen (ProviderModelSelector) and compact (CompactHeader)
 * dropdowns.
 *
 * Supports two visual sizes via the `compact` prop:
 *   compact=true  → smaller text, tighter padding (compact drawer)
 *   compact=false → standard size (fullscreen dropdown)
 */

import { useEffect } from 'react'
import type { ProviderOption } from '../config/providers'
import { filterChoicesForModel } from '../config/providers'

interface OptionControlProps {
  option: ProviderOption
  model: string | null
  value: string | number | undefined
  onChange: (value: string | number) => void
  compact?: boolean
}

export function OptionControl({
  option,
  model,
  value,
  onChange,
  compact = false,
}: OptionControlProps) {
  const current = value ?? option.defaultValue
  const filteredChoices = option.choices ? filterChoicesForModel(option.choices, model) : []

  // Auto-reset if current value is no longer available for this model
  useEffect(() => {
    if (option.type !== 'select' || !filteredChoices.length) return
    const isValid = filteredChoices.some((c) => c.value === String(current))
    if (!isValid) onChange(option.defaultValue as string | number)
  }, [model]) // eslint-disable-line react-hooks/exhaustive-deps

  const labelCls = compact
    ? 'text-[0.65rem] text-text-secondary font-medium block mb-1'
    : 'text-xs text-text-secondary font-medium block mb-1'

  const btnCls = compact
    ? 'flex-1 px-1.5 py-0.5 rounded-md text-[0.6rem] transition-colors'
    : 'flex-1 px-2 py-1 rounded-md text-xs transition-colors'

  const sliderH = compact ? 'h-1' : 'h-1.5'
  const sliderValCls = compact
    ? 'text-[0.6rem] text-text-secondary font-mono w-6 text-right'
    : 'text-xs text-text-secondary font-mono w-8 text-right'

  const numberCls = compact
    ? 'w-full px-2 py-1 rounded-lg text-xs font-mono bg-obsidian/50 border border-slate-mid/40 text-text-primary focus:border-synapse/50 focus:outline-none transition-colors'
    : 'w-full px-2.5 py-1.5 rounded-lg text-sm font-mono bg-obsidian/50 border border-slate-mid/40 text-text-primary focus:border-synapse/50 focus:outline-none transition-colors'

  return (
    <div className="px-1">
      <label className={labelCls}>{option.label}</label>

      {option.type === 'select' && filteredChoices.length > 0 && (
        <div className="flex gap-0.5 rounded-lg bg-obsidian/50 p-0.5 border border-slate-mid/30">
          {filteredChoices.map((c) => (
            <button
              key={c.value}
              onClick={() => onChange(c.value)}
              className={`${btnCls} ${
                String(current) === c.value
                  ? 'bg-synapse/20 text-synapse border border-synapse/30'
                  : 'text-text-muted hover:text-text-secondary'
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
      )}

      {option.type === 'slider' && (
        <div className="flex items-center gap-2">
          <input
            type="range"
            min={option.min ?? 0}
            max={option.max ?? 1}
            step={option.step ?? 0.1}
            value={Number(current)}
            onChange={(e) => onChange(parseFloat(e.target.value))}
            className={`flex-1 accent-synapse ${sliderH}`}
          />
          <span className={sliderValCls}>
            {Number(current).toFixed(1)}
          </span>
        </div>
      )}

      {option.type === 'number' && (
        <input
          type="number"
          min={option.min}
          max={option.max}
          step={option.step}
          value={current ?? ''}
          onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
          className={numberCls}
        />
      )}
    </div>
  )
}
