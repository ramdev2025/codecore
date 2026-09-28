import { BarChart as RechartsBar, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { useChartTheme } from '../../hooks/useChartTheme'

interface DataPoint { [key: string]: string | number }
interface Series { key: string; label?: string; color?: string }
interface BarChartProps {
  data: DataPoint[]
  series: Series[]
  xKey: string
  height?: number
  horizontal?: boolean
  stacked?: boolean
  rounded?: boolean
  className?: string
}

export function BarChart({ data, series, xKey, height = 240, horizontal = false, stacked = false, rounded = true, className }: BarChartProps) {
  const ct = useChartTheme()
  const radius: [number, number, number, number] = rounded ? [4, 4, 0, 0] : [0, 0, 0, 0]
  return (
    <div className={className} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RechartsBar data={data} layout={horizontal ? 'vertical' : 'horizontal'}>
          <CartesianGrid strokeDasharray="3 3" stroke={ct.gridColor} />
          {horizontal
            ? <><YAxis type="category" dataKey={xKey} tick={{ fill: ct.textColor, fontSize: 12 }} axisLine={false} tickLine={false} width={90} /><XAxis type="number" tick={{ fill: ct.textColor, fontSize: 12 }} axisLine={false} tickLine={false} /></>
            : <><XAxis dataKey={xKey} tick={{ fill: ct.textColor, fontSize: 12 }} axisLine={{ stroke: ct.gridColor }} tickLine={false} /><YAxis tick={{ fill: ct.textColor, fontSize: 12 }} axisLine={false} tickLine={false} /></>
          }
          <Tooltip contentStyle={{ background: ct.tooltipBg, border: `1px solid ${ct.tooltipBorder}`, borderRadius: 8, color: ct.tooltipText }} />
          <Legend wrapperStyle={{ color: ct.textColor, fontSize: 12 }} />
          {series.map((s, i) => (
            <Bar key={s.key} dataKey={s.key} name={s.label ?? s.key}
              fill={s.color ?? ct.colors[i % ct.colors.length]}
              radius={radius} stackId={stacked ? 'stack' : undefined} />
          ))}
        </RechartsBar>
      </ResponsiveContainer>
    </div>
  )
}
