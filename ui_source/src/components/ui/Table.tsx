import clsx from 'clsx'

interface Column<T> { key: keyof T; label: string; render?: (value: T[keyof T], row: T) => React.ReactNode; className?: string }
interface TableProps<T extends Record<string, unknown>> {
  columns: Column<T>[]; rows: T[]; onRowClick?: (row: T) => void; emptyMessage?: string; loading?: boolean
}

export function Table<T extends Record<string, unknown>>({ columns, rows, onRowClick, emptyMessage = 'No data to display', loading }: TableProps<T>) {
  return (
    <div className="w-full overflow-x-auto rounded-xl border border-ui-border bg-ui-surface shadow-card">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-ui-border bg-ui-elevated">
            {columns.map(col => (
              <th key={String(col.key)} scope="col" className={clsx('px-4 py-3 text-left text-xs font-semibold text-ui-text-2 uppercase tracking-wide', col.className)}>
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-ui-border">
          {loading ? (
            <tr><td colSpan={columns.length} className="px-4 py-8 text-center text-ui-text-2">
              <div className="flex items-center justify-center gap-2">
                <div className="w-4 h-4 border-2 border-ui-accent border-t-transparent rounded-full animate-spin" />Loading…
              </div>
            </td></tr>
          ) : rows.length === 0 ? (
            <tr><td colSpan={columns.length} className="px-4 py-10 text-center text-ui-text-2">{emptyMessage}</td></tr>
          ) : rows.map((row, i) => (
            <tr key={i} onClick={() => onRowClick?.(row)}
              className={clsx('transition-colors', onRowClick && 'cursor-pointer hover:bg-ui-hover')}>
              {columns.map(col => (
                <td key={String(col.key)} className={clsx('px-4 py-3 text-ui-text', col.className)}>
                  {col.render ? col.render(row[col.key], row) : String(row[col.key] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
