import { useTheme } from './useTheme'

interface ChartTheme {
  colors: string[]
  background: string
  textColor: string
  gridColor: string
  tooltipBg: string
  tooltipBorder: string
  tooltipText: string
}

const CHART_THEMES: Record<string, ChartTheme> = {
  light: {
    colors: ['#2563eb','#10b981','#f59e0b','#ef4444','#8b5cf6','#06b6d4'],
    background: 'transparent',
    textColor: '#64748b',
    gridColor: '#e2e8f0',
    tooltipBg: '#ffffff',
    tooltipBorder: '#e2e8f0',
    tooltipText: '#0f172a',
  },
  dark: {
    colors: ['#4c8ef8','#34d399','#fbbf24','#f87171','#a78bfa','#22d3ee'],
    background: 'transparent',
    textColor: '#8896ae',
    gridColor: '#1e2535',
    tooltipBg: '#1a1f2b',
    tooltipBorder: '#2a3347',
    tooltipText: '#eef2f7',
  },
}

export function useChartTheme(): ChartTheme {
  const { resolvedTheme } = useTheme()
  return CHART_THEMES[resolvedTheme] ?? CHART_THEMES.light
}
