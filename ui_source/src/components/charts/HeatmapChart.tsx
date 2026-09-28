import { useChartTheme } from '../../hooks/useChartTheme'

interface HeatmapCell { x: string; y: string; value: number }
interface HeatmapChartProps {
  data: HeatmapCell[]
  xLabels: string[]
  yLabels: string[]
  colorLow?: string
  colorHigh?: string
  height?: number
  className?: string
}

export function HeatmapChart({ data, xLabels, yLabels, colorLow, colorHigh, height, className }: HeatmapChartProps) {
  const ct = useChartTheme()
  const low = colorLow ?? ct.gridColor
  const high = colorHigh ?? ct.colors[0]
  const maxVal = Math.max(...data.map(d => d.value), 1)
  const cellH = height ? Math.floor((height - 28) / yLabels.length) : 32
  const cellW = `${100 / xLabels.length}%`

  function lerp(a: string, b: string, t: number) {
    const hex = (s: string) => [parseInt(s.slice(1,3),16), parseInt(s.slice(3,5),16), parseInt(s.slice(5,7),16)]
    const ca = hex(a), cb = hex(b)
    return `rgb(${Math.round(ca[0]+(cb[0]-ca[0])*t)},${Math.round(ca[1]+(cb[1]-ca[1])*t)},${Math.round(ca[2]+(cb[2]-ca[2])*t)})`
  }

  const cellMap: Record<string, number> = {}
  data.forEach(d => { cellMap[`${d.y}|${d.x}`] = d.value })

  return (
    <div className={className} style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'separate', borderSpacing: 2, width: '100%' }}>
        <thead>
          <tr>
            <th style={{ width: 80 }} />
            {xLabels.map(x => (
              <th key={x} scope="col" style={{ color: ct.textColor, fontSize: 11, opacity: 0.7, fontWeight: 500, textAlign: 'center', paddingBottom: 4, width: cellW }}>{x}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {yLabels.map(y => (
            <tr key={y}>
              <td style={{ color: ct.textColor, fontSize: 11, opacity: 0.7, paddingRight: 8, whiteSpace: 'nowrap' }}>{y}</td>
              {xLabels.map(x => {
                const v = cellMap[`${y}|${x}`] ?? 0
                return (
                  <td key={x} title={`${y} / ${x}: ${v}`}
                    style={{ height: cellH, backgroundColor: lerp(low, high, v / maxVal), borderRadius: 3, cursor: 'default', transition: 'opacity 0.15s' }} />
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
