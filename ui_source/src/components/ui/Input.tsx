import clsx from 'clsx'

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  hint?: string
  icon?: React.ReactNode
}

export function Input({ label, error, hint, icon, className, id, ...props }: InputProps) {
  const inputId = id ?? label?.toLowerCase().replace(/\s+/g, '-')
  return (
    <div className="flex flex-col gap-1.5">
      {label && <label htmlFor={inputId} className="text-sm font-medium text-ui-text">{label}</label>}
      <div className="relative">
        {icon && <span className="absolute left-3 top-1/2 -translate-y-1/2 text-ui-text-2 pointer-events-none">{icon}</span>}
        <input id={inputId} {...props}
          className={clsx('w-full rounded-lg border bg-ui-surface px-3 py-2 text-sm text-ui-text',
            'placeholder:text-ui-muted transition-colors',
            'focus:outline-none focus:ring-2 focus:ring-ui-accent focus:border-ui-accent',
            'disabled:bg-ui-elevated disabled:text-ui-muted disabled:cursor-not-allowed',
            error ? 'border-ui-error focus:ring-ui-error' : 'border-ui-border hover:border-ui-border-strong',
            icon && 'pl-9', className)} />
      </div>
      {error && <p className="text-xs text-ui-error">{error}</p>}
      {hint && !error && <p className="text-xs text-ui-text-2">{hint}</p>}
    </div>
  )
}
