import type { ReactNode } from 'react'
interface Props { title: string; subtitle?: string; actions?: ReactNode; className?: string }
export function PageHeader({ title, subtitle, actions, className }: Props) {
  return (
    <div className={`flex items-start justify-between px-6 pt-6 pb-0 ${className ?? ''}`}>
      <div>
        <h1 className="text-xl font-semibold text-ui-text">{title}</h1>
        {subtitle && <p className="text-sm text-ui-text-2 mt-0.5">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 flex-shrink-0 ml-4">{actions}</div>}
    </div>
  )
}
