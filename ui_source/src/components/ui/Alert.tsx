import clsx from 'clsx'
import { CheckCircle, AlertTriangle, XCircle, Info, X } from 'lucide-react'

type AlertVariant = 'success' | 'warning' | 'error' | 'info'
interface AlertProps { variant: AlertVariant; title?: string; message: string; onDismiss?: () => void }

const config: Record<AlertVariant, { bg: string; border: string; text: string; iconColor: string; Icon: React.ElementType }> = {
  success: { bg: 'bg-ui-success-bg', border: 'border-emerald-500/20', text: 'text-emerald-600',  iconColor: 'text-emerald-500', Icon: CheckCircle },
  warning: { bg: 'bg-ui-warning-bg', border: 'border-amber-500/20',   text: 'text-amber-600',    iconColor: 'text-amber-500',   Icon: AlertTriangle },
  error:   { bg: 'bg-ui-error-bg',   border: 'border-ui-error/20',    text: 'text-ui-error',     iconColor: 'text-ui-error',    Icon: XCircle },
  info:    { bg: 'bg-ui-info-bg',    border: 'border-ui-info/20',     text: 'text-ui-info',      iconColor: 'text-ui-info',     Icon: Info },
}

export function Alert({ variant, title, message, onDismiss }: AlertProps) {
  const { bg, border, text, iconColor, Icon } = config[variant]
  return (
    <div className={clsx('flex gap-3 p-4 rounded-xl border text-sm', bg, border, text)}>
      <Icon className={clsx('w-5 h-5 flex-shrink-0 mt-0.5', iconColor)} />
      <div className="flex-1 min-w-0">
        {title && <p className="font-semibold mb-0.5">{title}</p>}
        <p className="opacity-90 leading-relaxed">{message}</p>
      </div>
      {onDismiss && (
        <button onClick={onDismiss} className="flex-shrink-0 opacity-50 hover:opacity-100 transition-opacity">
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  )
}
