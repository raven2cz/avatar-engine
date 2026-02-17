/**
 * Floating Action Button — dark, subdued, shows avatar face in circle.
 *
 * Positioned bottom-right. Opacity 0.6 → 1 on hover.
 * Responsive: smaller on narrow screens (<768px).
 * Click opens compact mode.
 */

import { useTranslation } from 'react-i18next'

export interface AvatarFabProps {
  onClick: () => void
  avatarThumbUrl?: string
}

export function AvatarFab({ onClick, avatarThumbUrl }: AvatarFabProps) {
  const { t } = useTranslation()

  return (
    <button
      onClick={onClick}
      className="
        fixed bottom-6 left-6 z-50
        w-20 h-20 sm:w-20 sm:h-20
        rounded-full
        bg-slate-dark border border-white/10
        opacity-60 hover:opacity-100
        transition-all duration-300 ease-out
        hover:scale-105 hover:border-synapse/40
        hover:shadow-[0_6px_24px_rgba(0,0,0,0.5),0_0_0_2px_rgb(var(--ae-accent-rgb)_/_0.12)]
        active:scale-95
        shadow-lg shadow-black/40
        flex items-center justify-center
        cursor-pointer overflow-hidden
        group
      "
      title={t('fab.openChat')}
      aria-label={t('fab.openChatPanel')}
    >
      {avatarThumbUrl ? (
        <img
          src={avatarThumbUrl}
          alt="Avatar"
          className="w-[72px] h-[72px] rounded-full object-cover object-top border-2 border-white/10"
          draggable={false}
        />
      ) : (
        <svg
          className="w-8 h-8 text-text-secondary group-hover:text-synapse transition-colors"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M8.625 12a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 0 1-2.555-.337A5.972 5.972 0 0 1 5.41 20.97a5.969 5.969 0 0 1-.474-.065 4.48 4.48 0 0 0 .978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25Z"
          />
        </svg>
      )}
    </button>
  )
}
