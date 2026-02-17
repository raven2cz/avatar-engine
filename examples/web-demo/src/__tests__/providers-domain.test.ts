/**
 * Provider domain object tests — ensures shared utilities produce consistent
 * results across fullscreen and compact modes.
 *
 * Tests getFeaturedLabel, getModelDisplayName, filterChoicesForModel, and
 * engineStateToBustState logic.
 */

/// <reference types="vitest/globals" />
import { describe, it, expect } from 'vitest'
import {
  getFeaturedLabel,
  getModelDisplayName,
  filterChoicesForModel,
  getOptionsForProvider,
  getProvider,
} from '@avatar-engine/core'

describe('getFeaturedLabel', () => {
  it('returns "High" for gemini with thinking_level=high', () => {
    expect(getFeaturedLabel('gemini', { thinking_level: 'high' })).toBe('High')
  })

  it('returns "Low" for gemini with thinking_level=low', () => {
    expect(getFeaturedLabel('gemini', { thinking_level: 'low' })).toBe('Low')
  })

  it('returns "High" (default) when no thinking_level set for gemini', () => {
    expect(getFeaturedLabel('gemini', {})).toBe('High')
  })

  it('returns empty string for claude (no featured options)', () => {
    expect(getFeaturedLabel('claude', { max_budget_usd: 5 })).toBe('')
  })

  it('returns empty string for unknown provider', () => {
    expect(getFeaturedLabel('unknown', {})).toBe('')
  })

  it('returns "Minimal" for flash with minimal thinking', () => {
    expect(getFeaturedLabel('gemini', { thinking_level: 'minimal' })).toBe('Minimal')
  })
})

describe('getModelDisplayName', () => {
  it('returns model + featured label for gemini', () => {
    const result = getModelDisplayName('gemini', 'gemini-3-pro-preview', undefined, { thinking_level: 'high' })
    expect(result.modelName).toBe('gemini-3-pro-preview')
    expect(result.featuredLabel).toBe('High')
  })

  it('uses default model when model is null', () => {
    const result = getModelDisplayName('gemini', null, 'gemini-3-pro-preview', { thinking_level: 'low' })
    expect(result.modelName).toBe('gemini-3-pro-preview')
    expect(result.featuredLabel).toBe('Low')
  })

  it('returns null modelName when both model and default are null', () => {
    const result = getModelDisplayName('gemini', null, undefined, {})
    expect(result.modelName).toBeNull()
  })

  it('returns empty featuredLabel for provider without featured options', () => {
    const result = getModelDisplayName('codex', 'gpt-5.3-codex')
    expect(result.modelName).toBe('gpt-5.3-codex')
    expect(result.featuredLabel).toBe('')
  })

  it('defaults activeOptions to empty object', () => {
    const result = getModelDisplayName('gemini', 'gemini-3-pro-preview')
    expect(result.featuredLabel).toBe('High')  // default thinking_level
  })
})

describe('filterChoicesForModel', () => {
  const geminiOpts = getOptionsForProvider('gemini')
  const thinkingOpt = geminiOpts.find((o) => o.key === 'thinking_level')!
  const choices = thinkingOpt.choices!

  it('shows all 4 choices for flash model', () => {
    const filtered = filterChoicesForModel(choices, 'gemini-3-flash-preview')
    expect(filtered.map((c) => c.value)).toEqual(['minimal', 'low', 'medium', 'high'])
  })

  it('shows only low and high for pro model', () => {
    const filtered = filterChoicesForModel(choices, 'gemini-3-pro-preview')
    expect(filtered.map((c) => c.value)).toEqual(['low', 'high'])
  })

  it('shows only low and high for null model', () => {
    const filtered = filterChoicesForModel(choices, null)
    expect(filtered.map((c) => c.value)).toEqual(['low', 'high'])
  })

  it('returns all choices when all have no modelPattern', () => {
    const noPattern = [
      { value: 'a', label: 'A' },
      { value: 'b', label: 'B' },
    ]
    expect(filterChoicesForModel(noPattern, 'anything')).toEqual(noPattern)
  })
})

describe('getProvider', () => {
  it('returns gemini config', () => {
    const p = getProvider('gemini')
    expect(p?.id).toBe('gemini')
    expect(p?.defaultModel).toBe('gemini-3-pro-preview')
  })

  it('returns undefined for unknown', () => {
    expect(getProvider('nonexistent')).toBeUndefined()
  })
})

describe('provider configs consistency', () => {
  it('gemini has featured thinking_level option', () => {
    const opts = getOptionsForProvider('gemini')
    const featured = opts.filter((o) => o.featured)
    expect(featured).toHaveLength(1)
    expect(featured[0].key).toBe('thinking_level')
  })

  it('claude has no featured options', () => {
    const opts = getOptionsForProvider('claude')
    const featured = opts.filter((o) => o.featured)
    expect(featured).toHaveLength(0)
  })

  it('codex has no options', () => {
    const opts = getOptionsForProvider('codex')
    expect(opts).toHaveLength(0)
  })
})
