import { useChartTheme } from '../../hooks/useChartTheme'

interface GaugeChartProps {
  value: number
  max?: number
  label?: string
  sublabel?: string
  size?: number
  color?: string
  trackColor?: string
  className?: string
}

export function GaugeChart({ value, max = 100, label, sublabel, size = 120, color, trackColor, className }: GaugeChartProps) {
  const ct = useChartTheme()
  const pct = Math.min(Math.max(value / max, 0), 1)
  const r = (size / 2) - 10
  const circumference = Math.PI * r
  const arc = pct * circumference
  const strokeColor = color ?? (pct >= 0.8 ? '#ef4444' : pct >= 0.6 ? '#f59e0b' : '#22c55e')
  const track = trackColor ?? ct.gridColor
  return (
    <div className={className} style={{ width: size, position: 'relative', display: 'inline-block' }}>
      <svg width={size} height={size / 2 + 16} viewBox={`0 0 ${size} ${size / 2 + 16}`}>
        <path d={`M ${10} ${size / 2} A ${r} ${r} 0 0 1 ${size - 10} ${size / 2}`}
          fill="none" stroke={track} strokeWidth={8} strokeLinecap="round" />
        <path d={`M ${10} ${size / 2} A ${r} ${r} 0 0 1 ${size - 10} ${size / 2}`}
          fill="none" stroke={strokeColor} strokeWidth={8} strokeLinecap="round"
          strokeDasharray={`${arc} ${circumference}`}
          style={{ transition: 'stroke-dasharray 0.6s ease' }} />
      </svg>
      <div style={{ position: 'absolute', bottom: 4, left: 0, right: 0, textAlign: 'center' }}>
        {label && <div style={{ fontSize: 18, fontWeight: 700, color: ct.textColor, lineHeight: 1 }}>{label}</div>}
        {sublabel && <div style={{ fontSize: 10, color: ct.textColor, opacity: 0.6, marginTop: 2 }}>{sublabel}</div>}
      </div>
    </div>
  )
}
