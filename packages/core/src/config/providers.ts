/**
 * Provider & model configuration for the web UI.
 *
 * Edit this file to add/remove providers or update available models.
 */

// === Provider option definitions ===

export interface ProviderOption {
  key: string
  label: string
  type: 'select' | 'slider' | 'number'
  choices?: { value: string; label: string; modelPattern?: string }[]
  hideForModelPattern?: string
  min?: number
  max?: number
  step?: number
  defaultValue?: string | number
  optionsPath?: string
  featured?: boolean
}

export interface ProviderConfig {
  id: string
  label: string
  defaultModel: string
  models: string[]
  gradient: string
  dotColor: string
  options?: ProviderOption[]
}

export const PROVIDERS: ProviderConfig[] = [
  {
    id: 'gemini',
    label: 'Gemini',
    defaultModel: 'gemini-3-pro-preview',
    models: [
      'gemini-3-pro-preview',
      'gemini-3-flash-preview',
      'gemini-2.5-flash',
    ],
    gradient: 'from-blue-500/20 to-cyan-500/20 border-blue-400/40',
    dotColor: 'bg-blue-400',
    options: [
      {
        key: 'thinking_level',
        label: 'Thinking Level',
        type: 'select',
        hideForModelPattern: 'image',
        choices: [
          { value: 'minimal', label: 'Minimal', modelPattern: 'flash' },
          { value: 'low', label: 'Low' },
          { value: 'medium', label: 'Medium', modelPattern: 'flash' },
          { value: 'high', label: 'High' },
        ],
        defaultValue: 'high',
        optionsPath: 'generation_config.thinking_level',
        featured: true,
      },
      {
        key: 'temperature',
        label: 'Temperature',
        type: 'slider',
        min: 0,
        max: 2,
        step: 0.1,
        defaultValue: 1,
        optionsPath: 'generation_config.temperature',
      },
      {
        key: 'max_output_tokens',
        label: 'Max Tokens',
        type: 'number',
        min: 1,
        max: 65536,
        step: 1,
        defaultValue: 8192,
        optionsPath: 'generation_config.max_output_tokens',
      },
    ],
  },
  {
    id: 'claude',
    label: 'Claude',
    defaultModel: 'claude-opus-4-6',
    models: [
      'claude-opus-4-6',
      'claude-sonnet-4-5',
      'claude-haiku-4-5',
    ],
    gradient: 'from-amber-500/20 to-orange-500/20 border-amber-400/40',
    dotColor: 'bg-amber-400',
    options: [
      {
        key: 'max_budget_usd',
        label: 'Budget ($)',
        type: 'number',
        min: 0.01,
        max: 100,
        step: 0.01,
        defaultValue: 5,
      },
      {
        key: 'max_turns',
        label: 'Max Turns',
        type: 'number',
        min: 1,
        max: 100,
        step: 1,
        defaultValue: 10,
      },
    ],
  },
  {
    id: 'codex',
    label: 'Codex',
    defaultModel: 'gpt-5.3-codex',
    models: [
      'gpt-5.3-codex',
      'gpt-5.3-codex-spark',
      'gpt-5.2-codex',
      'gpt-5.1-codex-mini',
    ],
    gradient: 'from-emerald-500/20 to-green-500/20 border-emerald-400/40',
    dotColor: 'bg-emerald-400',
  },
]

export function getProvider(id: string): ProviderConfig | undefined {
  return PROVIDERS.find((p) => p.id === id)
}

export function getModelsForProvider(id: string): string[] {
  return getProvider(id)?.models ?? []
}

export function getOptionsForProvider(id: string): ProviderOption[] {
  return getProvider(id)?.options ?? []
}

export function isImageModel(model: string): boolean {
  return /image/i.test(model)
}

export function filterChoicesForModel(
  choices: NonNullable<ProviderOption['choices']>,
  model: string | null,
): NonNullable<ProviderOption['choices']> {
  return choices.filter(
    (c) => !c.modelPattern || (model && new RegExp(c.modelPattern, 'i').test(model)),
  )
}

export function buildOptionsDict(
  providerId: string,
  values: Record<string, string | number>,
): Record<string, unknown> {
  const options = getOptionsForProvider(providerId)
  const result: Record<string, unknown> = {}

  for (const [key, value] of Object.entries(values)) {
    const opt = options.find((o) => o.key === key)
    const path = opt?.optionsPath || key

    const parts = path.split('.')
    if (parts.length === 1) {
      result[parts[0]] = value
    } else {
      let current = result
      for (let i = 0; i < parts.length - 1; i++) {
        if (!current[parts[i]] || typeof current[parts[i]] !== 'object') {
          current[parts[i]] = {}
        }
        current = current[parts[i]] as Record<string, unknown>
      }
      current[parts[parts.length - 1]] = value
    }
  }

  return result
}

export function getFeaturedLabel(
  providerId: string,
  values: Record<string, string | number>,
): string {
  const opts = getOptionsForProvider(providerId)
  const parts: string[] = []
  for (const opt of opts) {
    if (!opt.featured) continue
    const val = values[opt.key] ?? opt.defaultValue
    if (val === undefined) continue
    if (opt.type === 'select' && opt.choices) {
      const choice = opt.choices.find((c) => c.value === String(val))
      if (choice) parts.push(choice.label)
    } else {
      parts.push(String(val))
    }
  }
  return parts.join(', ')
}

export function getModelDisplayName(
  providerId: string,
  model: string | null,
  defaultModel?: string,
  activeOptions: Record<string, string | number> = {},
): { modelName: string | null; featuredLabel: string } {
  const modelName = model || defaultModel || null
  const featuredLabel = getFeaturedLabel(providerId, activeOptions)
  return { modelName, featuredLabel }
}
