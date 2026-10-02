import { useCallback, useEffect, useState } from 'react'
import { api, type HistoryLockOut } from '../api/client'

/**
 * Closed claims, for the Log page.
 *
 * Refetched when the set of *live* claim ids changes rather than on a timer.
 * A claim entering or leaving `/api/activity` is exactly the moment history
 * gains a row, and the SSE stream already tells us when that happens — so
 * this costs one request per real event instead of one every N seconds.
 *
 * A failure here is swallowed into `error` and leaves the last good list in
 * place: the live half of the log must still render if history is unreachable.
 */
export function useClaimHistory(liveKey: string) {
  const [claims, setClaims] = useState<HistoryLockOut[]>([])
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setClaims((await api.history()).claims)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    void refresh()
    // `liveKey` is the dependency that matters — `refresh` is stable.
  }, [refresh, liveKey])

  return { claims, error, refresh }
}
