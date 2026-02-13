/**
 * i18n configuration — i18next + react-i18next.
 *
 * - Browser language detection with localStorage persistence
 * - Default: English, additional: Czech
 * - localStorage key: avatar-engine-language
 */

import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import { LS_LANGUAGE } from '../types/avatar'
import en from './locales/en.json'
import cs from './locales/cs.json'

export const AVAILABLE_LANGUAGES = [
  { code: 'en', label: 'English', flag: '🇬🇧' },
  { code: 'cs', label: 'Čeština', flag: '🇨🇿' },
] as const

function detectLanguage(): string {
  const stored = localStorage.getItem(LS_LANGUAGE)
  if (stored && ['en', 'cs'].includes(stored)) return stored
  return 'en'
}

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    cs: { translation: cs },
  },
  lng: detectLanguage(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})

export function changeLanguage(lng: string) {
  i18n.changeLanguage(lng)
  localStorage.setItem(LS_LANGUAGE, lng)
}

export function getCurrentLanguage(): string {
  return i18n.language
}

export default i18n
