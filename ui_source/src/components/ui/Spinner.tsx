import clsx from 'clsx'
import { Loader2 } from 'lucide-react'

interface SpinnerProps { size?: 'sm' | 'md' | 'lg'; label?: string; className?: string }
const sizes = { sm: 'w-4 h-4', md: 'w-6 h-6', lg: 'w-8 h-8' }

export function Spinner({ size = 'md', label, className }: SpinnerProps) {
  return (
    <div className={clsx('inline-flex items-center gap-2 text-ui-text-2', className)}>
      <Loader2 className={clsx('animate-spin text-ui-accent', sizes[size])} />
      {label && <span className="text-sm">{label}</span>}
    </div>
  )
}
