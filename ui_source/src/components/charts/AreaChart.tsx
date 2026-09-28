import { AreaChart as RechartsArea, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { useChartTheme } from '../../hooks/useChartTheme'

interface DataPoint { [key: string]: string | number }
interface Series { key: string; label?: string; color?: string }
interface AreaChartProps {
  data: DataPoint[]
  series: Series[]
  xKey: string
  height?: number
  gradient?: boolean
  stacked?: boolean
  className?: string
}

export function AreaChart({ data, series, xKey, height = 240, gradient = true, stacked = false, className }: AreaChartProps) {
  const ct = useChartTheme()
  return (
    <div className={className} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RechartsArea data={data}>
          <defs>
            {series.map((s, i) => (
              <linearGradient key={s.key} id={`grad-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={s.color ?? ct.colors[i % ct.colors.length]} stopOpacity={0.3} />
                <stop offset="95%" stopColor={s.color ?? ct.colors[i % ct.colors.length]} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={ct.gridColor} />
          <XAxis dataKey={xKey} tick={{ fill: ct.textColor, fontSize: 12 }} axisLine={{ stroke: ct.gridColor }} tickLine={false} />
          <YAxis tick={{ fill: ct.textColor, fontSize: 12 }} axisLine={false} tickLine={false} />
          <Tooltip contentStyle={{ background: ct.tooltipBg, border: `1px solid ${ct.tooltipBorder}`, borderRadius: 8, color: ct.tooltipText }} />
          <Legend wrapperStyle={{ color: ct.textColor, fontSize: 12 }} />
          {series.map((s, i) => (
            <Area key={s.key} type="monotone" dataKey={s.key} name={s.label ?? s.key}
              stroke={s.color ?? ct.colors[i % ct.colors.length]} strokeWidth={2}
              fill={gradient ? `url(#grad-${s.key})` : 'transparent'}
              stackId={stacked ? 'stack' : undefined} />
          ))}
        </RechartsArea>
      </ResponsiveContainer>
    </div>
  )
}
