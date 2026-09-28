import { LineChart as RechartsLine, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { useChartTheme } from '../../hooks/useChartTheme'

interface DataPoint { [key: string]: string | number }
interface Series { key: string; label?: string; color?: string; dashed?: boolean }
interface LineChartProps {
  data: DataPoint[]
  series: Series[]
  xKey: string
  height?: number
  className?: string
}

export function LineChart({ data, series, xKey, height = 240, className }: LineChartProps) {
  const ct = useChartTheme()
  return (
    <div className={className} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RechartsLine data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke={ct.gridColor} />
          <XAxis dataKey={xKey} tick={{ fill: ct.textColor, fontSize: 12 }} axisLine={{ stroke: ct.gridColor }} tickLine={false} />
          <YAxis tick={{ fill: ct.textColor, fontSize: 12 }} axisLine={false} tickLine={false} />
          <Tooltip contentStyle={{ background: ct.tooltipBg, border: `1px solid ${ct.tooltipBorder}`, borderRadius: 8, color: ct.tooltipText }} />
          <Legend wrapperStyle={{ color: ct.textColor, fontSize: 12 }} />
          {series.map((s, i) => (
            <Line key={s.key} type="monotone" dataKey={s.key} name={s.label ?? s.key}
              stroke={s.color ?? ct.colors[i % ct.colors.length]} strokeWidth={2}
              strokeDasharray={s.dashed ? '5 5' : undefined}
              dot={false} activeDot={{ r: 4 }} />
          ))}
        </RechartsLine>
      </ResponsiveContainer>
    </div>
  )
}
