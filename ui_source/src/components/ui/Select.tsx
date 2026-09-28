import clsx from 'clsx'
import { ChevronDown } from 'lucide-react'

interface SelectOption { label: string; value: string }
interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  options: SelectOption[]
  error?: string
  hint?: string
}

export function Select({ label, options, error, hint, className, id, ...props }: SelectProps) {
  const selectId = id ?? label?.toLowerCase().replace(/\s+/g, '-')
  return (
    <div className="flex flex-col gap-1.5">
      {label && <label htmlFor={selectId} className="text-sm font-medium text-ui-text">{label}</label>}
      <div className="relative">
        <select id={selectId} {...props}
          className={clsx('w-full appearance-none rounded-lg border bg-ui-surface px-3 py-2 pr-8 text-sm text-ui-text',
            'focus:outline-none focus:ring-2 focus:ring-ui-accent focus:border-ui-accent',
            'disabled:bg-ui-elevated disabled:text-ui-muted disabled:cursor-not-allowed transition-colors',
            error ? 'border-ui-error' : 'border-ui-border hover:border-ui-border-strong', className)}>
          {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ui-text-2 pointer-events-none" />
      </div>
      {error && <p className="text-xs text-ui-error">{error}</p>}
      {hint && !error && <p className="text-xs text-ui-text-2">{hint}</p>}
    </div>
  )
}
