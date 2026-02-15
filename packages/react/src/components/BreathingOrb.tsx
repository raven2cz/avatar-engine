/**
 * Galaxy Spiral — intelligent logo for Avatar Engine.
 *
 * Miniature galaxy with two spiral arms of twinkling stars,
 * a bright white core with colored glow, and phase-specific
 * color schemes. Spins faster when the AI is actively thinking.
 */

interface BreathingOrbProps {
  size?: 'sm' | 'md' | 'lg'
  active?: boolean
  phase?: string
}

interface SizeConfig {
  containerPx: number
  corePx: number
  coreGlowPx: number
  stars: number
  innerR: number
  starSpread: number
  maxStarPx: number
}

interface PhaseColors {
  c1: string
  c2: string
  c3: string
}

const SIZES: Record<string, SizeConfig> = {
  sm:  { containerPx: 90,  corePx: 10, coreGlowPx: 22, stars: 8,  innerR: 10, starSpread: 3, maxStarPx: 4 },
  md:  { containerPx: 140, corePx: 18, coreGlowPx: 36, stars: 12, innerR: 15, starSpread: 4, maxStarPx: 5 },
  lg:  { containerPx: 200, corePx: 24, coreGlowPx: 48, stars: 16, innerR: 20, starSpread: 5, maxStarPx: 6 },
}

const PHASE_COLORS: Record<string, PhaseColors> = {
  general:       { c1: '#6366f1', c2: '#8b5cf6', c3: '#a78bfa' },
  idle:          { c1: '#6366f1', c2: '#8b5cf6', c3: '#a78bfa' },
  thinking:      { c1: '#3b82f6', c2: '#6366f1', c3: '#06b6d4' },
  analyzing:     { c1: '#06b6d4', c2: '#3b82f6', c3: '#8b5cf6' },
  coding:        { c1: '#10b981', c2: '#06b6d4', c3: '#34d399' },
  planning:      { c1: '#8b5cf6', c2: '#c084fc', c3: '#e879f9' },
  reviewing:     { c1: '#f59e0b', c2: '#f97316', c3: '#fbbf24' },
  tool_planning: { c1: '#f59e0b', c2: '#f97316', c3: '#ef4444' },
  responding:    { c1: '#818cf8', c2: '#a78bfa', c3: '#c084fc' },
  success:       { c1: '#22c55e', c2: '#10b981', c3: '#06b6d4' },
  error:         { c1: '#ef4444', c2: '#f97316', c3: '#fbbf24' },
}

export function BreathingOrb({ size = 'md', active = true, phase = 'general' }: BreathingOrbProps) {
  const s = SIZES[size]
  const colors = PHASE_COLORS[phase] || PHASE_COLORS.general

  if (!active) return null

  const isActive = !['idle', 'general'].includes(phase)
  const center = s.containerPx / 2

  const generateArm = (armIndex: number) =>
    Array.from({ length: s.stars }).map((_, i) => {
      const angle = (i / s.stars) * Math.PI * 1.5 + armIndex * Math.PI
      const r = s.innerR + i * s.starSpread
      const starSize = Math.max(2, s.maxStarPx - i * 0.3)
      const x = center + Math.cos(angle) * r - starSize / 2
      const y = center + Math.sin(angle) * r - starSize / 2
      const color = i % 3 === 0 ? colors.c1 : i % 3 === 1 ? colors.c2 : colors.c3
      return (
        <div
          key={i}
          className="absolute rounded-full animate-twinkle"
          style={{
            left: x,
            top: y,
            width: starSize,
            height: starSize,
            background: color,
            boxShadow: `0 0 ${starSize + 2}px ${color}`,
            animationDelay: `${(i * 0.2 + armIndex * 0.1).toFixed(1)}s`,
          }}
        />
      )
    })

  return (
    <div
      className="relative flex items-center justify-center"
      style={{ width: s.containerPx, height: s.containerPx }}
    >
      {/* Core glow */}
      <div
        className="absolute rounded-full animate-breathe"
        style={{
          width: s.coreGlowPx,
          height: s.coreGlowPx,
          background: `radial-gradient(circle, ${colors.c1}, ${colors.c2})`,
          filter: 'blur(6px)',
        }}
      />

      {/* Core bright */}
      <div
        className="absolute rounded-full animate-breathe"
        style={{
          width: s.corePx,
          height: s.corePx,
          background: 'white',
          boxShadow: `0 0 15px white, 0 0 30px ${colors.c1}`,
        }}
      />

      {/* Spiral arm 1 */}
      <div className={`absolute inset-0 ${isActive ? 'animate-spin-galaxy-fast' : 'animate-spin-galaxy'}`}>
        {generateArm(0)}
      </div>

      {/* Spiral arm 2 (offset by half period) */}
      <div
        className={`absolute inset-0 ${isActive ? 'animate-spin-galaxy-fast' : 'animate-spin-galaxy'}`}
        style={{ animationDelay: isActive ? '-4s' : '-7s' }}
      >
        {generateArm(1)}
      </div>
    </div>
  )
}
