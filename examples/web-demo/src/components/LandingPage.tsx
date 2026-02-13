/**
 * === DEMO LANDING PAGE ===
 *
 * This LandingPage component is specific to the web demo.
 * When integrating Avatar Engine into your own application,
 * replace this with your app's content. The AvatarWidget
 * wraps your existing UI — just pass chat props and it handles
 * FAB, compact drawer, and fullscreen overlay automatically.
 *
 * Example integration:
 *   <AvatarWidget chat={useAvatarChat(wsUrl)} providers={availableProviders}>
 *     <YourApp />
 *   </AvatarWidget>
 */

import type { WidgetMode } from '../types/avatar'

interface LandingPageProps {
  showFabHint: boolean
  defaultMode: WidgetMode
  onDefaultModeChange: (mode: WidgetMode) => void
}

const FEATURES = [
  {
    icon: (
      <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456Z" />
      </svg>
    ),
    title: 'Multi-Provider',
    desc: 'Gemini, Claude, OpenAI — switch on the fly',
  },
  {
    icon: (
      <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
      </svg>
    ),
    title: 'Animated Bust',
    desc: '8 characters with sprite sheet mouth animation',
  },
  {
    icon: (
      <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75Z" />
      </svg>
    ),
    title: 'Live Streaming',
    desc: 'Real-time token streaming with thinking phases',
  },
  {
    icon: (
      <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M11.42 15.17l-5.655 5.653a2.548 2.548 0 1 1-3.586-3.586l5.652-4.655M17.5 6.5l-1 1M15.5 8.5l4.586-4.586a2 2 0 0 1 2.828 2.828L18.33 11.41" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 3.5l4 4" />
      </svg>
    ),
    title: 'Tool Execution',
    desc: 'Watch AI use tools in real-time with status tracking',
  },
  {
    icon: (
      <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
      </svg>
    ),
    title: 'File Upload',
    desc: 'Drag & drop images, PDFs, audio for multimodal input',
  },
  {
    icon: (
      <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 0 1-.825-.242m9.345-8.334a2.126 2.126 0 0 0-.476-.095 48.64 48.64 0 0 0-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0 0 11.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
      </svg>
    ),
    title: 'Session History',
    desc: 'Resume conversations, track costs across sessions',
  },
]

const SHORTCUTS = [
  { keys: 'Ctrl+Shift+A', action: 'Toggle compact chat' },
  { keys: 'Ctrl+Shift+F', action: 'Toggle fullscreen' },
  { keys: 'Ctrl+Shift+H', action: 'Toggle bust visibility' },
  { keys: 'Escape', action: 'Close / minimize' },
  { keys: 'Enter', action: 'Send message' },
  { keys: 'Shift+Enter', action: 'New line in message' },
]

const MODE_OPTIONS: { value: WidgetMode; label: string }[] = [
  { value: 'fab', label: 'FAB' },
  { value: 'compact', label: 'Compact' },
  { value: 'fullscreen', label: 'Fullscreen' },
]

export function LandingPage({ showFabHint, defaultMode, onDefaultModeChange }: LandingPageProps) {
  return (
    <div className="min-h-screen bg-obsidian flex flex-col items-center justify-center px-6 relative overflow-auto"
      style={{
        background: `
          radial-gradient(ellipse at 20% 50%, rgba(99, 102, 241, 0.06) 0%, transparent 50%),
          radial-gradient(ellipse at 80% 20%, rgba(6, 182, 212, 0.04) 0%, transparent 50%),
          linear-gradient(180deg, #0a0a0f 0%, #0f0f17 50%, #0a0a0f 100%)
        `,
      }}
    >
      {/* Hero */}
      <div className="text-center mb-12 animate-fade-in">
        <h1 className="text-4xl sm:text-5xl font-bold mb-3 pb-1 gradient-text tracking-tight">
          Avatar Engine
        </h1>
        <p className="text-text-secondary text-lg max-w-lg mx-auto leading-relaxed">
          AI-powered conversational assistant with animated avatars,
          multi-provider support, and real-time streaming.
        </p>
      </div>

      {/* Feature grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 max-w-3xl w-full mb-12">
        {FEATURES.map((f) => (
          <div
            key={f.title}
            className="rounded-2xl bg-white/[0.02] border border-white/[0.05] p-5
              hover:bg-white/[0.04] hover:border-white/[0.08] hover:-translate-y-0.5
              transition-all duration-200"
          >
            <div className="text-synapse mb-2">{f.icon}</div>
            <h3 className="text-text-primary font-semibold text-sm mb-1">{f.title}</h3>
            <p className="text-text-muted text-xs leading-relaxed">{f.desc}</p>
          </div>
        ))}
      </div>

      {/* Keyboard shortcuts */}
      <div className="max-w-md w-full mb-8">
        <h2 className="text-text-secondary text-xs font-semibold uppercase tracking-widest mb-3 text-center">
          Keyboard Shortcuts
        </h2>
        <div className="rounded-xl bg-white/[0.02] border border-white/[0.04] overflow-hidden">
          {SHORTCUTS.map((s, i) => (
            <div
              key={s.keys}
              className={`flex items-center justify-between px-4 py-2 ${
                i < SHORTCUTS.length - 1 ? 'border-b border-white/[0.03]' : ''
              }`}
            >
              <kbd className="px-2 py-0.5 rounded bg-slate-dark border border-slate-mid/50 text-text-secondary text-xs font-mono">
                {s.keys}
              </kbd>
              <span className="text-text-muted text-xs">{s.action}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Startup mode selector */}
      <div className="max-w-md w-full mb-8">
        <h2 className="text-text-secondary text-xs font-semibold uppercase tracking-widest mb-3 text-center">
          Startup Mode
        </h2>
        <div className="flex justify-center gap-2">
          {MODE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => onDefaultModeChange(opt.value)}
              className={`px-4 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 ${
                defaultMode === opt.value
                  ? 'bg-synapse/20 border border-synapse/40 text-synapse'
                  : 'bg-white/[0.02] border border-white/[0.05] text-text-muted hover:bg-white/[0.04] hover:border-white/[0.08] hover:text-text-secondary'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <p className="text-text-muted/50 text-[0.6rem] text-center mt-2">
          Widget opens in this mode on first visit
        </p>
      </div>

      {/* Documentation link */}
      <div className="mb-16">
        <a
          href="https://github.com/anthropics/avatar-engine"
          target="_blank"
          rel="noopener noreferrer"
          className="text-text-muted hover:text-synapse text-xs transition-colors duration-200"
        >
          Documentation & README →
        </a>
      </div>

      {/* Blinking arrow pointing to FAB (bottom-left) — high contrast for dark theme */}
      {showFabHint && (
        <div className="fixed bottom-28 left-[64px] z-40 flex flex-col items-center animate-bounce -translate-x-1/2">
          <span className="text-synapse text-sm font-semibold mb-1.5 drop-shadow-[0_0_8px_rgba(99,102,241,0.6)]">
            Open chat
          </span>
          <svg className="w-7 h-7 text-synapse drop-shadow-[0_0_10px_rgba(99,102,241,0.7)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 13.5L12 21m0 0l-7.5-7.5M12 21V3" />
          </svg>
        </div>
      )}

      {/* Footer */}
      <div className="fixed bottom-4 right-4 text-text-muted/40 text-[0.6rem]">
        Avatar Engine Web Demo
      </div>
    </div>
  )
}
