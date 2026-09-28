import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { useChartTheme } from '../../hooks/useChartTheme'

interface DonutSlice { name: string; value: number; color?: string }
interface DonutChartProps {
  data: DonutSlice[]
  height?: number
  innerRadius?: number | string
  outerRadius?: number | string
  showLegend?: boolean
  centerLabel?: string
  centerValue?: string | number
  className?: string
}

export function DonutChart({ data, height = 240, innerRadius = '60%', outerRadius = '80%', showLegend = true, centerLabel, centerValue, className }: DonutChartProps) {
  const ct = useChartTheme()
  return (
    <div className={className} style={{ height, position: 'relative' }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} cx="50%" cy="50%" innerRadius={innerRadius} outerRadius={outerRadius} paddingAngle={2} dataKey="value">
            {data.map((entry, i) => (
              <Cell key={entry.name} fill={entry.color ?? ct.colors[i % ct.colors.length]} />
            ))}
          </Pie>
          <Tooltip contentStyle={{ background: ct.tooltipBg, border: `1px solid ${ct.tooltipBorder}`, borderRadius: 8, color: ct.tooltipText }} />
          {showLegend && <Legend wrapperStyle={{ color: ct.textColor, fontSize: 12 }} />}
        </PieChart>
      </ResponsiveContainer>
      {(centerLabel || centerValue !== undefined) && (
        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', textAlign: 'center', pointerEvents: 'none' }}>
          {centerValue !== undefined && <div style={{ fontSize: 24, fontWeight: 700, color: ct.textColor, lineHeight: 1 }}>{centerValue}</div>}
          {centerLabel && <div style={{ fontSize: 11, color: ct.textColor, opacity: 0.6, marginTop: 4 }}>{centerLabel}</div>}
        </div>
      )}
    </div>
  )
}
