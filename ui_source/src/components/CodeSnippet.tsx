import { FileLock2, Loader2, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ApiError, api, type SnippetOut } from '../api/client'
import clsx from 'clsx'

interface Props {
  lockId: number
  hasSnippet: boolean
  /** Lines to tint as the overlapping region, when known. */
  highlight?: { start: number; end: number } | null
}

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ready'; snippet: SnippetOut }
  | { kind: 'absent' }
  | { kind: 'error'; message: string }

/**
 * The stored code for a claimed range.
 *
 * Snippet storage is opt-in server-side (`JUPITER_STORE_SNIPPETS`), so "no
 * snippet" is the ordinary case, not a failure — it gets a plain explanation
 * rather than an error. Code is fetched only when this mounts, which is only
 * when someone opens a conflict, so source never rides along in the activity
 * payload or the SSE stream.
 */
export function CodeSnippet({ lockId, hasSnippet, highlight }: Props) {
  const [state, setState] = useState<State>({ kind: 'idle' })

  useEffect(() => {
    if (!hasSnippet) {
      setState({ kind: 'absent' })
      return
    }
    let cancelled = false
    setState({ kind: 'loading' })
    api.snippet(lockId)
      .then(snippet => { if (!cancelled) setState({ kind: 'ready', snippet }) })
      .catch(e => {
        if (cancelled) return
        if (e instanceof ApiError && e.status === 404) setState({ kind: 'absent' })
        else setState({ kind: 'error', message: e instanceof Error ? e.message : String(e) })
      })
    return () => { cancelled = true }
  }, [lockId, hasSnippet])

  if (state.kind === 'loading') {
    return (
      <p className="flex items-center gap-2 text-sm text-ui-text-2">
        <Loader2 className="h-4 w-4 animate-spin text-ui-accent" aria-hidden="true" />
        Loading the claimed lines…
      </p>
    )
  }

  if (state.kind === 'absent') {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-ui-border bg-ui-elevated p-3 text-sm text-ui-text-2">
        <FileLock2 className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
        <span>
          No code stored for this claim. Jupiter keeps snippets only when{' '}
          <code className="font-mono text-xs text-ui-text">JUPITER_STORE_SNIPPETS</code> is enabled —
          by default it records which lines were claimed, not what they contain.
        </span>
      </div>
    )
  }

  if (state.kind === 'error') {
    return (
      <p className="flex items-start gap-2 text-sm text-ui-error">
        <TriangleAlert className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
        <span>Could not load the snippet: {state.message}</span>
      </p>
    )
  }

  if (state.kind !== 'ready') return null

  const { snippet } = state
  const first = snippet.line_start ?? 1
  const lines = snippet.code.replace(/\n$/, '').split('\n')

  return (
    <figure className="overflow-hidden rounded-lg border border-ui-border bg-ui-elevated">
      <figcaption className="border-b border-ui-border px-3 py-2 font-mono text-xs text-ui-text-2">
        {snippet.file_path}
        {snippet.line_start !== null && (
          <span>:{snippet.line_start}{snippet.line_end && snippet.line_end !== snippet.line_start ? `-${snippet.line_end}` : ''}</span>
        )}
      </figcaption>
      <div className="max-h-72 overflow-auto">
        <table className="w-full border-collapse font-mono text-xs">
          <caption className="sr-only">Claimed lines of {snippet.file_path}</caption>
          <tbody>
            {lines.map((text, i) => {
              const n = first + i
              const lit = !!highlight && n >= highlight.start && n <= highlight.end
              return (
                <tr key={n} className={clsx(lit && 'bg-ui-error-bg')}>
                  <th
                    scope="row"
                    className={clsx(
                      'select-none border-r border-ui-border px-2 py-0.5 text-right align-top font-normal tabular-nums',
                      lit ? 'text-ui-error' : 'text-ui-muted',
                    )}
                  >
                    {n}
                  </th>
                  <td className={clsx('whitespace-pre px-3 py-0.5', lit ? 'text-ui-text' : 'text-ui-text')}>
                    {text || ' '}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </figure>
  )
}
