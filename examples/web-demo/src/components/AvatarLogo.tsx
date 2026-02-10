/**
 * Avatar Engine logo — inline SVG.
 *
 * AI face with antenna, curved ^ eyes, and smile.
 * Accepts size via className (e.g. "w-5 h-5", "w-8 h-8").
 */

interface AvatarLogoProps {
  className?: string
}

export function AvatarLogo({ className = 'w-6 h-6' }: AvatarLogoProps) {
  return (
    <svg
      viewBox="24 16 80 80"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <defs>
        <linearGradient id="avatar-grad" x1="24" y1="16" x2="104" y2="96">
          <stop offset="0%" stopColor="#58a6ff" />
          <stop offset="100%" stopColor="#bc8cff" />
        </linearGradient>
      </defs>
      <rect x="34" y="42" width="60" height="46" rx="12" fill="url(#avatar-grad)" opacity="0.12" />
      <rect x="34" y="42" width="60" height="46" rx="12" stroke="url(#avatar-grad)" strokeWidth="2.5" fill="none" />
      <path d="M41 60 Q49 51 57 60" stroke="#58a6ff" strokeWidth="3" fill="none" strokeLinecap="round" />
      <path d="M71 60 Q79 51 87 60" stroke="#58a6ff" strokeWidth="3" fill="none" strokeLinecap="round" />
      <path d="M44 74 Q64 87 84 74" stroke="#58a6ff" strokeWidth="2.5" fill="none" strokeLinecap="round" />
      <line x1="64" y1="42" x2="64" y2="28" stroke="url(#avatar-grad)" strokeWidth="2.5" strokeLinecap="round" />
      <circle cx="64" cy="25" r="4" fill="#58a6ff" />
    </svg>
  )
}
