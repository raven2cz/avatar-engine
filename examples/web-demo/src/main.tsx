import React from 'react'
import ReactDOM from 'react-dom/client'
import { initAvatarI18n } from '@avatar-engine/react'
import { initReactI18next } from 'react-i18next'
import App from './App'
import '@avatar-engine/react/styles.css'
import './index.css'

// Initialize i18n with react-i18next binding (plugins must be passed before init)
initAvatarI18n([initReactI18next])

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
