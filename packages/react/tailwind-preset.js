/** @type {import('tailwindcss').Config} */
module.exports = {
  theme: {
    extend: {
      colors: {
        obsidian: '#0a0a0f',
        'slate-darker': '#0f0f17',
        'slate-deep': '#12121a',
        'slate-base': '#13131b',
        'slate-dark': '#16161f',
        'slate-mid': '#1a1a2e',
        'slate-light': '#2a2a42',
        synapse: '#6366f1',
        pulse: '#8b5cf6',
        neural: '#06b6d4',
        'text-primary': '#f8fafc',
        'text-secondary': '#94a3b8',
        'text-muted': '#64748b',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      animation: {
        'breathe': 'breathe 3s ease-in-out infinite',
        'glow-breathe': 'glow-breathe 2s ease-in-out infinite',
        'particle-float': 'particle-float 3s ease-in-out infinite',
        'particle-glow': 'particle-glow 2s ease-in-out infinite',
        'spin-slow': 'spin 8s linear infinite',
        'spin-reverse': 'spin-reverse 12s linear infinite',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'slide-in': 'slide-in 0.3s ease-out',
        'slide-up': 'slide-up 0.3s ease-out',
        'fade-in': 'fade-in 0.2s ease-out',
        'glow-pulse': 'glow-pulse 2s ease-in-out infinite',
        'shimmer': 'shimmer 2s ease-in-out infinite',
        'twinkle': 'twinkle 2s ease-in-out infinite',
        'spin-galaxy': 'galaxy-spin 14s linear infinite',
        'spin-galaxy-fast': 'galaxy-spin 8s linear infinite',
        'bust-breathe': 'bust-breathe 3.5s ease-in-out infinite',
        'bust-thinking': 'bust-thinking 3s ease-in-out infinite',
        'bust-speaking': 'bust-speaking 2s ease-in-out infinite',
        'bust-shake': 'bust-shake 0.6s ease-in-out',
      },
      keyframes: {
        breathe: {
          '0%, 100%': { transform: 'scale(1)', opacity: '1' },
          '50%': { transform: 'scale(1.05)', opacity: '0.9' },
        },
        'glow-breathe': {
          '0%, 100%': { transform: 'scale(1)', opacity: '0.6' },
          '50%': { transform: 'scale(1.3)', opacity: '0.3' },
        },
        'particle-float': {
          '0%, 100%': { transform: 'translateY(0) scale(1)', opacity: '0.6' },
          '50%': { transform: 'translateY(-10px) scale(1.2)', opacity: '1' },
        },
        'slide-in': {
          '0%': { transform: 'translateX(100%)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
        'slide-up': {
          '0%': { transform: 'translateY(20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'glow-pulse': {
          '0%, 100%': { transform: 'scale(1)', opacity: '1' },
          '50%': { transform: 'scale(1.2)', opacity: '0.7' },
        },
        shimmer: {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(100%)' },
        },
        'particle-glow': {
          '0%, 100%': { opacity: '0.4', transform: 'scale(1)' },
          '50%': { opacity: '1', transform: 'scale(1.5)' },
        },
        'spin-reverse': {
          '0%': { transform: 'rotate(360deg)' },
          '100%': { transform: 'rotate(0deg)' },
        },
        'twinkle': {
          '0%, 100%': { opacity: '0.4', transform: 'scale(1)' },
          '50%': { opacity: '1', transform: 'scale(1.5)' },
        },
        'galaxy-spin': {
          '0%': { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(360deg)' },
        },
        'bust-breathe': {
          '0%, 100%': { transform: 'translateY(2.8%) scale(1)' },
          '50%': { transform: 'translateY(calc(2.8% - 4px)) scale(1.006)' },
        },
        'bust-thinking': {
          '0%, 100%': { transform: 'translateY(2.8%) rotate(0deg)' },
          '30%': { transform: 'translateY(calc(2.8% - 7px)) rotate(-1.2deg)' },
          '70%': { transform: 'translateY(calc(2.8% - 3px)) rotate(0.8deg)' },
        },
        'bust-speaking': {
          '0%, 100%': { transform: 'translateY(2.8%) scale(1)' },
          '50%': { transform: 'translateY(2.8%) scale(1.015)' },
        },
        'bust-shake': {
          '0%, 100%': { transform: 'translateY(2.8%) translateX(0)' },
          '15%': { transform: 'translateY(2.8%) translateX(-8px)' },
          '30%': { transform: 'translateY(2.8%) translateX(8px)' },
          '45%': { transform: 'translateY(2.8%) translateX(-6px)' },
          '60%': { transform: 'translateY(2.8%) translateX(6px)' },
          '75%': { transform: 'translateY(2.8%) translateX(-3px)' },
          '90%': { transform: 'translateY(2.8%) translateX(3px)' },
        },
      },
      backdropBlur: {
        '2xl': '40px',
      },
    },
  },
}
