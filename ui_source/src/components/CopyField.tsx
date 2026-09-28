import { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import clsx from 'clsx'

interface Props {
  value: string
  label?: string
  multiline?: boolean
  className?: string
}

export function CopyField({ value, label, multiline, className }: Props) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
    } catch {
      // Clipboard API needs a secure context; fall back to a temporary selection.
      const ta = document.createElement('textarea')
      ta.value = value
      document.body.appendChild(ta)
      ta.select()
      try { document.execCommand('copy') } catch { /* nothing else to try */ }
      document.body.removeChild(ta)
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className={clsx('flex flex-col gap-1.5', className)}>
      {label && <span className="text-sm font-medium text-ui-text">{label}</span>}
      <div className="flex items-stretch gap-2">
        <pre className={clsx(
          'flex-1 min-w-0 rounded-lg border border-ui-border bg-ui-elevated px-3 py-2',
          'font-mono text-xs text-ui-text overflow-x-auto',
          multiline ? 'whitespace-pre' : 'whitespace-nowrap',
        )}>{value}</pre>
        <button onClick={copy} aria-label={copied ? 'Copied' : 'Copy to clipboard'}
          className={clsx('flex-shrink-0 inline-flex items-center gap-1.5 px-3 rounded-lg border text-xs font-medium transition-colors',
            copied
              ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-500'
              : 'border-ui-border bg-ui-surface text-ui-text-2 hover:bg-ui-hover hover:text-ui-text')}>
          {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
    </div>
  )
}
