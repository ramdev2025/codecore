import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from '@tanstack/react-table'
import { AlertTriangle, ArrowDown, ArrowUp, CheckCircle, ChevronsUpDown, Eye, Pencil } from 'lucide-react'
import { useMemo, useState } from 'react'
import clsx from 'clsx'
import type { LockOut } from '../api/client'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { conflictingHolders, formatRange, secondsRemaining } from '../lib/conflicts'
import { ExpiryMeter } from './ExpiryMeter'
import { StatusBadge } from './StatusBadge'

interface Props {
  locks: LockOut[]
  ttl: number
  nowMs: number
  emptyMessage?: string
  /** Opens the conflict modal. Every row is inspectable, not just conflicted ones. */
  onInspect?: (lock: LockOut) => void
}

const col = createColumnHelper<LockOut>()

/**
 * Claims, as a sortable table on desktop and a stacked card list on phones.
 *
 * The two presentations carry the same information — a horizontally scrolling
 * five-column table is unusable on a 360px screen, so below 640px each claim
 * becomes its own card instead. Desktop keeps real `<table>` semantics with
 * `<th scope="col">`, since claims are genuinely tabular data.
 */
export function ClaimsTable({
  locks, ttl, nowMs,
  emptyMessage = 'No files are currently claimed by anyone.',
  onInspect,
}: Props) {
  const isMobile = useMediaQuery('(max-width: 639px)')
  const [sorting, setSorting] = useState<SortingState>([])

  const columns = useMemo(() => [
    col.accessor('file_path', {
      header: 'File',
      cell: info => {
        const lock = info.row.original
        return (
          <div className="min-w-0">
            <span className="break-all font-mono text-xs text-ui-text">{lock.file_path}</span>
            <span className="ml-1.5 whitespace-nowrap font-mono text-xs text-ui-text-2">
              {lock.line_start === null ? '(whole file)' : `:${lock.line_start}${lock.line_end && lock.line_end !== lock.line_start ? `-${lock.line_end}` : ''}`}
            </span>
            {lock.note && <p className="mt-1 text-xs italic text-ui-text-2">{lock.note}</p>}
          </div>
        )
      },
    }),
    col.accessor('intent', {
      header: 'Intent',
      cell: info => info.getValue() === 'editing'
        ? <StatusBadge label="editing" variant="info" icon={<Pencil className="h-3 w-3" />} />
        : <StatusBadge label="reading" variant="neutral" icon={<Eye className="h-3 w-3" />} />,
    }),
    col.accessor('member', { header: 'Held by' }),
    col.display({
      id: 'status',
      header: 'Status',
      cell: info => {
        const lock = info.row.original
        const clashes = conflictingHolders(lock, locks)
        return clashes.length > 0
          ? <StatusBadge label={`conflict: ${clashes.map(c => c.member).join(', ')}`} variant="error" icon={<AlertTriangle className="h-3 w-3" />} />
          : <StatusBadge label="clear" variant="success" icon={<CheckCircle className="h-3 w-3" />} />
      },
    }),
    col.accessor('expires_at', {
      header: 'Expires in',
      cell: info => <ExpiryMeter seconds={secondsRemaining(info.getValue(), nowMs)} ttl={ttl} />,
    }),
  ], [locks, nowMs, ttl])

  const table = useReactTable({
    data: locks,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (locks.length === 0) {
    return (
      <div className="rounded-xl border border-ui-border bg-ui-surface p-10 text-center text-ui-text-2 shadow-card">
        {emptyMessage}
      </div>
    )
  }

  if (isMobile) {
    return (
      <ul className="space-y-2">
        {locks.map(lock => {
          const clashes = conflictingHolders(lock, locks)
          const conflicted = clashes.length > 0
          return (
            <li key={lock.lock_id}>
              <button
                type="button"
                onClick={() => onInspect?.(lock)}
                className={clsx(
                  'w-full rounded-xl border bg-ui-surface p-4 text-left shadow-card',
                  'min-h-[44px] active:bg-ui-hover focus-visible:ring-2 focus-visible:ring-ui-accent',
                  conflicted ? 'border-ui-error/30' : 'border-ui-border',
                )}
                aria-label={`Inspect claim on ${lock.file_path}`}
              >
                <div className="mb-2 break-all font-mono text-xs text-ui-text">
                  {lock.file_path}
                  <span className="text-ui-text-2">
                    {lock.line_start === null ? ' (whole file)' : `:${lock.line_start}${lock.line_end && lock.line_end !== lock.line_start ? `-${lock.line_end}` : ''}`}
                  </span>
                </div>
                {lock.note && <p className="mb-2 text-xs italic text-ui-text-2">{lock.note}</p>}
                <dl className="space-y-1.5 text-xs">
                  <div className="flex items-center gap-2">
                    <dt className="sr-only">Held by</dt>
                    <dd className="text-ui-text">{lock.member}</dd>
                    <dd>
                      {lock.intent === 'editing'
                        ? <StatusBadge label="editing" variant="info" icon={<Pencil className="h-3 w-3" />} />
                        : <StatusBadge label="reading" variant="neutral" icon={<Eye className="h-3 w-3" />} />}
                    </dd>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <dt className="sr-only">Status</dt>
                    <dd>
                      {conflicted
                        ? <StatusBadge label={`conflict: ${clashes.map(c => c.member).join(', ')}`} variant="error" icon={<AlertTriangle className="h-3 w-3" />} />
                        : <StatusBadge label="clear" variant="success" icon={<CheckCircle className="h-3 w-3" />} />}
                    </dd>
                  </div>
                  <div>
                    <dt className="sr-only">Expires in</dt>
                    <dd><ExpiryMeter seconds={secondsRemaining(lock.expires_at, nowMs)} ttl={ttl} /></dd>
                  </div>
                </dl>
              </button>
            </li>
          )
        })}
      </ul>
    )
  }

  return (
    <div className="w-full overflow-x-auto rounded-xl border border-ui-border bg-ui-surface shadow-card">
      <table className="w-full text-sm">
        <caption className="sr-only">Files currently claimed across the team. Select a row to inspect it.</caption>
        <thead>
          {table.getHeaderGroups().map(group => (
            <tr key={group.id} className="border-b border-ui-border bg-ui-elevated">
              {group.headers.map(header => {
                const sortable = header.column.getCanSort()
                const dir = header.column.getIsSorted()
                return (
                  <th
                    key={header.id}
                    scope="col"
                    aria-sort={dir === 'asc' ? 'ascending' : dir === 'desc' ? 'descending' : undefined}
                    className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-ui-text-2"
                  >
                    {sortable ? (
                      <button
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                        className="inline-flex items-center gap-1 rounded hover:text-ui-text focus-visible:ring-2 focus-visible:ring-ui-accent"
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {dir === 'asc' ? <ArrowUp className="h-3 w-3" aria-hidden="true" />
                          : dir === 'desc' ? <ArrowDown className="h-3 w-3" aria-hidden="true" />
                          : <ChevronsUpDown className="h-3 w-3 opacity-50" aria-hidden="true" />}
                      </button>
                    ) : (
                      flexRender(header.column.columnDef.header, header.getContext())
                    )}
                  </th>
                )
              })}
            </tr>
          ))}
        </thead>
        <tbody className="divide-y divide-ui-border">
          {table.getRowModel().rows.map(row => (
            <tr
              key={row.id}
              onClick={() => onInspect?.(row.original)}
              className={clsx('align-top transition-colors', onInspect && 'cursor-pointer hover:bg-ui-hover')}
            >
              {row.getVisibleCells().map((cell, i) => (
                <td key={cell.id} className={clsx('px-4 py-3', i > 0 && 'whitespace-nowrap')}>
                  {i === 0 && onInspect ? (
                    // A real control on the first cell, so the row is reachable
                    // by keyboard and announced as actionable — not a div with
                    // an onClick.
                    <button
                      type="button"
                      onClick={e => { e.stopPropagation(); onInspect(row.original) }}
                      className="text-left focus-visible:ring-2 focus-visible:ring-ui-accent"
                      aria-label={`Inspect claim on ${row.original.file_path}`}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </button>
                  ) : (
                    flexRender(cell.column.columnDef.cell, cell.getContext())
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
