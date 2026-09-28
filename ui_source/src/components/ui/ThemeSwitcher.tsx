import { Sun, Moon, type LucideIcon } from 'lucide-react'
import clsx from 'clsx'
import { useTheme, type Theme } from '../../hooks/useTheme'

const themes: { value: Theme; label: string; icon: LucideIcon }[] = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark',  label: 'Dark',  icon: Moon },
]

export function ThemeSwitcher({ compact = false, className }: { compact?: boolean; className?: string }) {
  const { theme, setTheme } = useTheme()
  return (
    <div className={clsx('inline-flex items-center gap-0.5 p-0.5 bg-ui-elevated border border-ui-border rounded-lg', className)}>
      {themes.map(({ value, label, icon: Icon }) => (
        <button key={value} onClick={() => setTheme(value)} title={label} aria-label={`${label} theme`}
          className={clsx('inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium transition-all',
            theme === value ? 'bg-ui-accent text-ui-on-accent shadow-sm' : 'text-ui-text-2 hover:bg-ui-hover hover:text-ui-text')}>
          <Icon size={12} />
          {!compact && <span>{label}</span>}
        </button>
      ))}
    </div>
  )
}
