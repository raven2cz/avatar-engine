import avatarPreset from '@avatar-engine/react/tailwind-preset'

/** @type {import('tailwindcss').Config} */
export default {
  presets: [avatarPreset],
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
    // npm workspaces: symlinks resolve to packages/ — scan both paths
    '../../packages/react/src/**/*.{ts,tsx}',
    '../../node_modules/@avatar-engine/react/dist/**/*.js',
  ],
  plugins: [],
}
