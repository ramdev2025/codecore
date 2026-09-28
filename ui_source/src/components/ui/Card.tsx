import clsx from 'clsx'

type CardVariant = 'elevated' | 'outlined' | 'flat'
interface CardProps {
  variant?: CardVariant
  padding?: 'sm' | 'md' | 'lg' | 'none'
  className?: string
  children: React.ReactNode
  onClick?: () => void
}

const variants: Record<CardVariant, string> = {
  elevated: 'bg-ui-surface shadow-card border border-ui-border',
  outlined: 'bg-ui-surface border border-ui-border',
  flat:     'bg-ui-elevated',
}
const paddings = { none: '', sm: 'p-3', md: 'p-5', lg: 'p-6' }

export function Card({ variant = 'elevated', padding = 'md', className, children, onClick }: CardProps) {
  return (
    <div onClick={onClick}
      className={clsx('rounded-xl', variants[variant], paddings[padding],
        onClick && 'cursor-pointer hover:shadow-dropdown transition-shadow duration-150', className)}>
      {children}
    </div>
  )
}
