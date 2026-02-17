/**
 * i18n configuration — i18next (framework-agnostic).
 *
 * - Browser language detection with localStorage persistence
 * - Default: English, additional: Czech
 * - localStorage key: avatar-engine-language
 */

import i18n from 'i18next'
import { LS_LANGUAGE } from '../types'
import en from './locales/en.json'
import cs from './locales/cs.json'

export const AVAILABLE_LANGUAGES = [
  { code: 'en', label: 'English', flag: '\u{1F1EC}\u{1F1E7}' },
  { code: 'cs', label: '\u010Ce\u0161tina', flag: '\u{1F1E8}\u{1F1FF}' },
] as const

function detectLanguage(): string {
  if (typeof localStorage === 'undefined') return 'en'
  const stored = localStorage.getItem(LS_LANGUAGE)
  if (stored && ['en', 'cs'].includes(stored)) return stored
  return 'en'
}

/**
 * Initialize i18next for Avatar Engine.
 * Call once at app startup. Returns the i18n instance for use with framework bindings.
 *
 * @param plugins - Optional i18next plugins to register (e.g. initReactI18next)
 */
export function initAvatarI18n(plugins?: { type: string }[]): typeof i18n {
  if (i18n.isInitialized) return i18n

  if (plugins) {
    for (const plugin of plugins) {
      i18n.use(plugin as any)
    }
  }

  i18n.init({
    resources: {
      en: { translation: en },
      cs: { translation: cs },
    },
    lng: detectLanguage(),
    fallbackLng: 'en',
    interpolation: { escapeValue: false },
  })

  return i18n
}

export function changeLanguage(lng: string): void {
  i18n.changeLanguage(lng)
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(LS_LANGUAGE, lng)
  }
}

export function getCurrentLanguage(): string {
  return i18n.language
}

export { i18n }
