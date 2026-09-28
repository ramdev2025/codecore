import { LineChart, Line, ResponsiveContainer, Tooltip } from 'recharts'
import { useChartTheme } from '../../hooks/useChartTheme'

interface SparkLineProps {
  data: number[]
  color?: string
  height?: number
  width?: number | string
  showTooltip?: boolean
  trend?: 'up' | 'down' | 'neutral'
  className?: string
}

export function SparkLine({ data, color, height = 40, width = '100%', showTooltip = false, trend, className }: SparkLineProps) {
  const ct = useChartTheme()
  const autoColor = trend === 'up' ? '#22c55e' : trend === 'down' ? '#ef4444' : (color ?? ct.colors[0])
  const chartData = data.map((v, i) => ({ i, v }))
  return (
    <div className={className} style={{ height, width }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <Line type="monotone" dataKey="v" stroke={autoColor} strokeWidth={1.5} dot={false} />
          {showTooltip && <Tooltip contentStyle={{ background: ct.tooltipBg, border: `1px solid ${ct.tooltipBorder}`, borderRadius: 6, color: ct.tooltipText, fontSize: 11, padding: '2px 8px' }} />}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
