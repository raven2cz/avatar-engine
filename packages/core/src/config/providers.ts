/**
 * Provider & model configuration for the web UI.
 *
 * Edit this file to add/remove providers or update available models.
 */

// === Provider option definitions ===

/**
 * A single configurable option exposed by a provider (e.g. temperature, thinking level).
 *
 * @property key - Unique option key used as the form field name.
 * @property label - Human-readable label shown in the UI.
 * @property type - Input control type: "select" dropdown, "slider", or "number" spinner.
 * @property choices - Available choices for "select" type options.
 * @property hideForModelPattern - Regex pattern; hides this option when the active model matches.
 * @property min - Minimum value for "slider" and "number" types.
 * @property max - Maximum value for "slider" and "number" types.
 * @property step - Step increment for "slider" and "number" types.
 * @property defaultValue - Default value used when the user has not set one.
 * @property optionsPath - Dot-separated path for nesting in the provider options dict (e.g. "generation_config.temperature").
 * @property featured - When true, the option's value is shown in the provider badge label.
 */
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

/**
 * Full configuration for an AI provider (models, UI styling, and options).
 *
 * @property id - Unique provider identifier sent to the server (e.g. "gemini", "claude").
 * @property label - Human-readable provider name shown in the UI.
 * @property defaultModel - Model selected by default when the user picks this provider.
 * @property models - List of all available model names for this provider.
 * @property gradient - Tailwind CSS gradient classes for the provider card background.
 * @property dotColor - Tailwind CSS class for the provider status dot color.
 * @property options - Optional list of configurable provider options.
 */
export interface ProviderConfig {
  id: string
  label: string
  defaultModel: string
  models: string[]
  gradient: string
  dotColor: string
  options?: ProviderOption[]
}

/** Registry of all available AI providers and their configurations. */
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

/**
 * Look up a provider configuration by its identifier.
 *
 * @param id - Provider identifier (e.g. "gemini", "claude").
 * @returns The matching provider config, or undefined if not found.
 */
export function getProvider(id: string): ProviderConfig | undefined {
  return PROVIDERS.find((p) => p.id === id)
}

/**
 * Get the list of available model names for a provider.
 *
 * @param id - Provider identifier.
 * @returns Array of model names, or an empty array if the provider is unknown.
 */
export function getModelsForProvider(id: string): string[] {
  return getProvider(id)?.models ?? []
}

/**
 * Get the configurable options for a provider.
 *
 * @param id - Provider identifier.
 * @returns Array of provider options, or an empty array if the provider has none.
 */
export function getOptionsForProvider(id: string): ProviderOption[] {
  return getProvider(id)?.options ?? []
}

/**
 * Check whether a model name indicates an image-generation model.
 *
 * @param model - Model name to test.
 * @returns True if the model name contains "image" (case-insensitive).
 */
export function isImageModel(model: string): boolean {
  return /image/i.test(model)
}

/**
 * Filter select-option choices to only those compatible with the active model.
 *
 * Choices without a `modelPattern` are always included. Choices with a
 * `modelPattern` are included only when the pattern matches the current model.
 *
 * @param choices - Full list of select choices to filter.
 * @param model - Currently active model name, or null.
 * @returns Filtered array of compatible choices.
 */
export function filterChoicesForModel(
  choices: NonNullable<ProviderOption['choices']>,
  model: string | null,
): NonNullable<ProviderOption['choices']> {
  return choices.filter(
    (c) => !c.modelPattern || (model && new RegExp(c.modelPattern, 'i').test(model)),
  )
}

/**
 * Build a nested options dictionary from flat key-value pairs.
 *
 * Uses each option's `optionsPath` to nest values at the correct depth
 * (e.g. `{ temperature: 0.7 }` becomes `{ generation_config: { temperature: 0.7 } }`).
 *
 * @param providerId - Provider identifier used to resolve option paths.
 * @param values - Flat map of option keys to their current values.
 * @returns Nested options dictionary ready to send to the server.
 */
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

/**
 * Build a human-readable label from the provider's featured option values.
 *
 * @param providerId - Provider identifier.
 * @param values - Current option values keyed by option key.
 * @returns Comma-separated string of featured option labels (e.g. "High").
 */
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

/**
 * Resolve the display name and featured label for a provider's active model.
 *
 * @param providerId - Provider identifier.
 * @param model - Currently active model, or null.
 * @param defaultModel - Fallback model name if `model` is null.
 * @param activeOptions - Current option values for featured label computation.
 * @returns Object with `modelName` (resolved model or null) and `featuredLabel` string.
 */
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
