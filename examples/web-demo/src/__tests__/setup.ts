/// <reference types="vitest/globals" />
import '@testing-library/jest-dom'
import { initAvatarI18n } from '@avatar-engine/react'
import { initReactI18next } from 'react-i18next'

// Initialize i18n for tests
initAvatarI18n([initReactI18next])

// Mock localStorage
const store: Record<string, string> = {}
const localStorageMock = {
  getItem: (key: string) => store[key] ?? null,
  setItem: (key: string, value: string) => { store[key] = value },
  removeItem: (key: string) => { delete store[key] },
  clear: () => { Object.keys(store).forEach((k) => delete store[k]) },
  get length() { return Object.keys(store).length },
  key: (i: number) => Object.keys(store)[i] ?? null,
}
Object.defineProperty(window, 'localStorage', { value: localStorageMock })

// Mock matchMedia
Object.defineProperty(window, 'matchMedia', {
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
})

// Mock scrollIntoView (not available in jsdom)
Element.prototype.scrollIntoView = () => {}

// Reset localStorage between tests
beforeEach(() => {
  localStorageMock.clear()
})
